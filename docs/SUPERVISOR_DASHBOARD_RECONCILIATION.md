# Aetherius Live Supervisor Dashboard — Architecture Reconciliation & Data-Source Map

**Status:** DESIGNED (bounded unit 1 of the dashboard programme). No code written yet.
**Author:** Hermes (supervisor). Per §22: begin with architecture reconciliation and
real data-source mapping, then build the first live end-to-end slice.
**Governing law:** §49 — no duplicate systems without justification. This unit RECONCILES
against existing canonical infrastructure before proposing anything new.

---

## 0. Reconciliation verdict (the whole point of this doc)

The dashboard is **NOT greenfield**. Agent-Bridge already owns a canonical event bus,
an HTTP+SSE surface, and an append-only worker/team identity registry. The dashboard is
an **adapter + normaliser + read-model + presentation layer over those**, plus a small
number of genuinely-new telemetry adapters. Building a parallel bus/registry/transport
would violate §49 and §3 ("do not duplicate existing event buses unnecessarily").

---

## 1. Existing canonical systems — REUSE, do not rebuild

| Concern | Canonical system (file) | What it already provides | Dashboard relationship |
|---|---|---|---|
| Event bus / pub-sub | `events.py::EventBus` | `subscribe(event, fn)`, `emit(event, payload)`, `of(event)`, in-memory `history`; wildcard `"*"` subscribers | **Primary event source.** Dashboard normaliser subscribes to `"*"`. |
| Event persistence | `events.py::EventLogger` | JSONL sink; **already strips `api_key/token/password/secret`** (§14 no-secrets satisfied) | Telemetry log tail / provenance. |
| HTTP transport | `nodes/node_server.py` | stdlib `ThreadingHTTPServer`, binds `127.0.0.1` (refuses `0.0.0.0`), routes `/v1/node/*` | Extend with dashboard routes on the SAME server (loopback-only). |
| **SSE transport** | `nodes/node_server.py::_send_sse` | **Already emits `text/event-stream`** with `id:`/`event:` framing, per-delegation event streams (`/v1/node/delegations/{id}/events`) | **Reuse the SSE pattern.** Add a supervisor-wide `/v1/supervisor/events` stream. |
| Audit / history | `node_server.NodeServerState.audit` + `.events` | append audit list + per-delegation event lists, timestamped | Snapshot + replay source (§13 reconnect). |
| Worker/team identity | `compute/team_registry.py::TeamRegistry` | append-only provenance + canonical layer; teams, members, RACI, worker career state; **`MODEL != WORKER != PROVIDER`** enforced; `schema_version` | **Worker identity source** for WorkerRecord (§3). |
| Node identity + routing | `nodes/node_registry.py`, `node_router.py` | node descriptors, trust, privacy filtering, `OWNER_NODE`/trusted nodes | Node/worker roster + trust state. |
| Orchestration runtime | `orchestrator.py`, `runtime.py`, `bridge.py` | emit lifecycle events onto the bus | Upstream event producers. |

**Confirmed absences (so we don't pretend they exist):**
- **No third-party HTTP framework** (no FastAPI/Flask/Starlette/aiohttp). Transport is
  stdlib `http.server` only. The dashboard backend extends `node_server`'s stdlib server;
  it does NOT introduce a new framework.
- No existing WebSocket (SSE is the established streaming pattern — keep it).

---

## 2. Canonical supervisor event contract (§2)

Reconcile with existing `EventBus` vocabulary. Existing event names already in use
(see `events.py` constants + `node_server` emit calls):
`approval.requested/approved/denied`, `execution.started/completed/failed`,
`review.started/completed`, `rollback.started/completed`, plus node events
`handshake`, `pairing_request`, `PAIRING_REQUESTED`, `CHALLENGE_SENT`, `PAIRED`,
`heartbeat`, and delegation status events surfaced over SSE.

**Rule:** reuse those names verbatim. New event families are added ONLY where no existing
name covers them, and they are namespaced to avoid collision:

- worker.*  → `worker.registered|started|status_changed|heartbeat|blocked|completed|failed|stopped`
- task.*    → `task.created|assigned|started|progress|blocked|completed|failed`
- git.*     → `git.commit_created|push_completed|remote_verified|branch_changed`
- test.*    → `test.started|passed|failed` (suite-level + current-test)
- app.*     → `application.opened|active|closed`
- model.*   → `model.selected|loaded|released|provider.changed`
- source-state enum (§1 of the brief): `LIVE_VERIFIED|LIVE|STALE|DEGRADED|OFFLINE|FIXTURE|DEMO|UNKNOWN|BLOCKED`
  plus honest placeholders `NOT_EXPOSED`, `DEFERRED_BACKEND_INTERFACE`.

Every event carries: `event`, `timestamp`, `session_id`, `worker_id?`, `project_id?`,
`unit_id?`, `source` (which adapter produced it), `evidence_state`. Secrets are stripped
at the `EventLogger` boundary already; adapters must not introduce new secret fields.

---

## 3. Standard worker identity (§3) — WorkerRecord

Composed from `TeamRegistry` (org facts) + node registry (trust) + adapter-observed
runtime facts. Identity axes kept separate per the existing invariant:

```
worker_id, parent_worker_id, worker_type (hermes_subagent|opencode|external_ai|tool|model),
role_id, display_name, avatar_profile_id, application_id, model_id, provider_id,
execution_target, project_id, unit_id, task_id, status, started_at, heartbeat_at,
capabilities, source, evidence_state
```
`WORKER != ROLE != AVATAR != APPLICATION != MODEL != PROVIDER != INSTANCE` — already
enforced by TeamRegistry; the dashboard read-model preserves it.

---

## 4. Adapters (source → normaliser) — what is real vs deferred

| Adapter | Real data source | V1 status |
|---|---|---|
| **Agent Bridge** | `node_server` `/v1/node/health`, delegations, SSE events, audit | **LIVE (loopback)** |
| **Event bus** | `events.py::EventBus` `"*"` subscription + `history` | **LIVE** |
| **Worker/team identity** | `TeamRegistry` canonical + provenance | **LIVE** |
| **Git telemetry** (§7) | `git` CLI per active repo (HEAD, origin, ahead/behind, dirty, untracked, last commit) | **NEW adapter** (stdlib subprocess; read-only) |
| **Test/build telemetry** (§8) | test-runner JSON/exit + parsed counts; never infer green from exit alone | **NEW adapter** (parses real runner output) |
| **Hermes supervisor** (§4) | this Hermes session: spawned subagents, active unit, task, heartbeat, branch ownership | **NEW adapter** (Hermes self-telemetry) |
| **OpenCode worker** (§5) | **VERIFIED CLI-first:** `opencode session list` (structured: id/title/updated) + `opencode export <sessionID>` → JSON `{info:{id,slug,projectID,directory,title,agent,model,version,cost,tokens,time}, messages:[{info,parts}...]}` on stdout. Also `opencode stats` (tokens/cost), `serve`/`acp`/`attach`. The `serve` HTTP API on :56993 is Basic-auth gated (401) — the CLI bypasses it, so **no screen-scraping, no auth needed.** | **NEW adapter** (CLI `session list` + `export`; GUI/computer-use is fallback only, never primary) |
| **Local models** (§10) | Ollama `:11434/api/ps` + `/api/version` (already verified live) | **NEW adapter** (HTTP to loopback) |
| **Live team roster / active speaker** | `/v1/runtime` returns empty teams today (OpenCode recon) | **DEFERRED_BACKEND_INTERFACE** — show honest empty/unknown, never fabricate |

Backend gaps to keep recording until real: live team roster, active speaker, handoff
event exposure, execution-target HTTP exposure, call/media state, canonical Genesis
identity binding. (§6 "do not fake currently missing interfaces".)

---

## 5. Transport & reconnect (§13)

```
SOURCE ADAPTERS → NORMALISER → EventBus(subscribe "*") → STATE STORE/EVENT LOG
   → REST snapshot (/v1/supervisor/state) + SSE stream (/v1/supervisor/events)
   → DASHBOARD (React, reuses af2af48 design system)
```
Reconnect = snapshot + `last-event-id` cursor + incremental events (the SSE handler
already frames `id:`; extend to supervisor stream). Loopback-only, matching node_server.

---

## 6. Presentation (§11, §12) — reuse, don't rebuild

Lives in **IDE-Workspace** (the accepted `af2af48` Genesis Avatar-First UI foundation),
NOT in Agent-Bridge. Views A–J (Mission Control, Team Room, Conference, Worker, Project,
Activity Stream, Agent Comms, Application/Workforce, Repository, Owner-Gate) are built
from the existing component/theme system (ABYSS/AURORA/EMBER/GRAPHITE/FROST). A
`LIVE WORKFORCE | DESIGN/DEMO` toggle makes fixture-vs-real unambiguous (§1).
**Separation:** supervisor data protocol (Agent-Bridge) ≠ presentation components
(IDE-Workspace) ≠ host app — so IDE and Aetherius OS can host the same control plane (§16).

---

## 7. First live end-to-end slice (V1, §17/§20)

Smallest slice that is genuinely LIVE and demonstrable:
1. Normaliser subscribing to `EventBus` → `/v1/supervisor/state` (REST snapshot) +
   `/v1/supervisor/events` (SSE), loopback, on the existing node_server.
2. Git adapter (real) + Ollama adapter (real, already-verified endpoint) + WorkerRecord
   from TeamRegistry.
3. Dashboard Mission Control + Repository + Activity Stream views in IDE-Workspace,
   consuming the real endpoints, honest UNKNOWN/DEFERRED for the rest.
4. **Acceptance demo (§20):** assign OpenCode a bounded task; dashboard shows
   ASSIGNED→WORKING→FILES CHANGED→TESTING→COMMITTING→PUSHING→REMOTE VERIFIED→
   AWAITING QA→ACCEPTED, produced by real telemetry (git adapter + event bus), with a
   Hermes subagent reviewing in parallel. No manufactured status.

**Not in V1:** controls beyond read-only (§15 Phase 1), WebSocket (SSE suffices),
active-speaker (no backend), cloud workers (BLOCKED_OWNER creds).

---

## 8. Tests required (§19)

worker register/remove, heartbeat + stale detection, task lifecycle, project mapping,
event ordering, reconnect/replay, duplicate-event handling, git-state parsing,
test-telemetry parsing, **source honesty (fixture never shown as live)**, fixture/live
separation, disconnect/reconnect, multi-worker concurrency, no-secrets-in-telemetry,
permission boundaries. Plus a real integration run: Hermes + ≥1 subagent + OpenCode.

---

## 9. V1 SLICE — BUILT (branch `unit/supervisor-dashboard`, SHA `bd5ec3b`)

Implemented as an **adapter/normaliser/read-model**, not a parallel system (§49):

- `nodes/supervisor.py` — source-state vocabulary (LIVE_VERIFIED/LIVE/STALE/
  DEGRADED/OFFLINE/FIXTURE/UNKNOWN/BLOCKED/NOT_EXPOSED/DEFERRED_BACKEND_INTERFACE),
  `SourceFact` (freshness-degrades LIVE→STALE, never upgrades OFFLINE),
  `read_git_state` (real git, LIVE_VERIFIED), `read_ollama_state` (loopback),
  `SupervisorState` normaliser (subscribes `EventBus("*")`, bounded event ring,
  thread-safe snapshot), `refresh_snapshot`, and a loopback
  `ThreadingHTTPServer` (`build_supervisor_server`, refuses 0.0.0.0) mirroring
  node_server's `_send`/`_send_sse` framing so one client parser works.
- Routes: `GET /v1/supervisor/health`, `/v1/supervisor/state`,
  `/v1/supervisor/events?since=<seq>` (SSE).
- `tests/test_supervisor_dashboard.py` — 20 tests (honesty contract, adapters,
  normaliser, API contract, SSE framing, public-bind refusal, refresh wiring).

**Evidence:** `20 passed` (new) + `205 passed` (node/team/policy/routing cluster,
no regression). Pushed to `origin/unit/supervisor-dashboard`; local==origin,
0/0, tracked-clean. Remote-verified.

**MERGED TO MAIN:** ff-merged `origin/unit/supervisor-dashboard` (`bf53506`)
into `main`; main==origin/main==`bf53506`, 0/0, remote-verified. Four commits:
`bd5ec3b` (read-model+API), `4529961` (TeamRegistry wiring + list_workers/
list_teams), `b712503` (OpenCode CLI adapter), `bf53506` (§20 acceptance demo).
Dashboard backend slice: 29 tests pass; §20 bounded-live demo confirms every
value LIVE_VERIFIED against real sources (agent-bridge@7d24feb, ollama 0.34.4,
2 workers, opencode session 343 msgs).

**Deferred (honest, not fabricated):** live/OpenCode runtime sections beyond the
two adapters, the TeamRegistry worker reader wiring (`NOT_EXPOSED` until wired),
and the React presentation layer (IDE-Workspace, separate write-set).

---

## 10. Open questions / risks

- ~~OpenCode structured telemetry~~ **RESOLVED (VERIFIED):** CLI-first via `opencode
  session list` + `opencode export <id>` (JSON on stdout); `serve` HTTP API is Basic-auth
  gated so the CLI is the clean channel. No screen-scraping needed.
- Event volume: SSE must not flood; normaliser should coalesce heartbeats.
- Writer isolation: Agent-Bridge (dashboard backend) and IDE-Workspace (dashboard UI)
  are separate repos → separate worktrees, one writer each (§4/§18).

---

## 11. VERIFIED EventBus vocabulary (reconnaissance, deleg_41d9ae13 task-2)

Complete production (non-test) bus-side event names a dashboard can subscribe to via
`bus.subscribe("*", ...)`. Reconcile — do NOT invent a parallel vocabulary:

**Lifecycle (bridge.py, via EXECUTION_*/REVIEW_* constants):**
`execution.started`, `execution.completed`, `execution.failed`, `review.started`,
`review.completed`.

**Runtime session (runtime.py, inline literals):**
`approval.requested`, `approval.resolved`, `approval.approved`, `approval.denied`
(policy.py too), `task.deduplicated`, `task.started`, `task.failed`, `task.completed`,
`planning.started`, `planning.completed`, `gate.waiting`, `gate.timeout`,
`gate.resolved`, `revision.requested`, `task.cancelled`, `rollback.started`,
`rollback.completed`, `session.created`, `session.recovered`.
(Ignore `selfcheck` — synthetic probe on a throwaway bus.)

**Bus-injected only (voice/pipeline.py, comms/telephone.py — reach the bus only when a
bus is passed in; not wired in the default run):**
`listening`, `speech_final`, `agent_message`, `stop_speaking`, `mute`, `call_event`.

**NOT on the shared bus (separate stores — dashboard must read these directly, not via
EventBus):**
- `node_server.py` `st.emit`/`st.log` → NodeServerState per-delegation SSE list + audit
  (names: `PAIRING_REQUESTED`, `CHALLENGE_SENT`, `PAIRED`, `CANCELLED`, `RUNNING`,
  `COMPLETED`, `handshake`, `pairing_request`, `paired`, `remote_owner_denied`,
  `replay_rejected`, `untrusted_rejected`, `data_policy_denied`, `delegation_completed`).
  Served over `GET /v1/node/delegations/{id}/events`.
- `genesis_runtime.py` → own `GenesisEvent` list (`session.started`, `model.selected`,
  `fallback.triggered`, `model.unavailable`, `model.ready`, `objective.received`,
  `task.created`, `worker.assigned`, `task.observed`, `verification.passed`,
  `test.failed`, `task.completed`).
- `bridge.py` `EventLogger.event()` → JSONL only (`start`, `step`, `end`, `review`,
  `ollama-error`); bus events whose names start `approval./execution./review./rollback.`
  are forwarded into that JSONL as `bus_event=<name>`.

**Existing subscribers (proves the pattern works):** `runtime.py` subscribes `"*"` →
session history; `EventLogger` subscribes `"*"`. A dashboard normaliser subscribes `"*"`
the same way.

**Known hygiene note:** `APPROVAL_*`/`ROLLBACK_*` constants exist but the equivalent
names are emitted as inline literals by runtime.py/policy.py (duplication to reconcile
later, not a dashboard blocker).
