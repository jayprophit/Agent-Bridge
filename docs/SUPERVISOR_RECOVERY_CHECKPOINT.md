# Supervisor Recovery Checkpoint — post power-failure (2026-10-12)

**Recovery mode:** entered after electrical power loss. Durable state (Git) is
truth. This file is the write-ahead journal + worker table (§19/§20 of the
recovery directive) so a future reboot reconstructs the workforce without the
owner.

**Recovered at:** 2026-10-12 (session start). **Checkpoint verified, not assumed.**

---

## 1. Durable-state verification (all VERIFIED via git, not assumed)

| Repo | Branch | HEAD | origin | ahead/behind | tracked-dirty | untracked | locks |
|---|---|---|---|---|---|---|---|
| Agent-Bridge | main | `3083ae7` | `3083ae7` | 0/0 | 0 | 0 | none |
| IDE-Workspace | master | `af2af48` | `af2af48` | 0/0 | 18 | 2 | none |
| MAT (Codex) | main | `cc805f8` | `cc805f8` | 0/0 | 530 | 698 | none |

**Agent-Bridge `3083ae7` checkpoint HOLDS:** supervisor dashboard backend intact.
Smoke test re-run: **31/31 supervisor tests pass** on main. No rebuild needed.

**IDE-Workspace P0-A INTERRUPTED** by the outage: `GenesisShell.tsx` +
`index.ts` modified, `runtime/` + `docs/handoffs/` untracked. tsc re-check
running (cold cache); historical state was 3 tsc errors — being re-verified.

**MAT Codex INTERRUPTED-in-flight:** last commit `cc805f8` pushed; 530 dirty +
698 untracked = large uncommitted write-set. Codex still owns this write-set.

---

## 2. Worker ownership table (§4)

| worker_id | type | application | role | project | unit | repo | branch | write_set | status | phase | heartbeat |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HERMES | OWNER/SUPERVISOR | Hermes | master supervisor | all | recovery | Agent-Bridge | main | Agent-Bridge docs | ACTIVE | RECOVERING | now |
| H-SA-ARCH | HERMES_INTERNAL | (subagent) | architecture/reconcile | all | recovery | read-only | — | none | READY | — | — |
| H-SA-BACKEND | HERMES_INTERNAL | (subagent) | dashboard/AB backend | dashboard | backend | Agent-Bridge | main | nodes/supervisor.py | READY | — | — |
| H-SA-QA | HERMES_INTERNAL | (subagent) | tests/evidence | all | recovery | read-only | — | none | READY | — | — |
| H-SA-SECURITY | HERMES_INTERNAL | (subagent) | security/privacy | all | audit | read-only | — | none | READY | — | — |
| H-SA-UI | HERMES_INTERNAL | (subagent) | dashboard/IDE UI | dashboard | UI | IDE-Workspace-dashboard | unit/supervisor-dashboard-ui | (reserved) | READY | — | — |
| H-SA-RESEARCH | HERMES_INTERNAL | (subagent) | MAT research/provenance | MAT | support | read-only | — | none | READY | — | — |
| H-SA-DEVOPS | HERMES_INTERNAL | (subagent) | runtime recovery | infra | recovery | read-only | — | none | READY | — | — |
| H-SA-PROVENANCE | HERMES_INTERNAL | (subagent) | registry/checkpoint | all | recovery | Agent-Bridge | main | this doc | ACTIVE | — | now |
| CODEX | EXTERNAL_AI_APP | Codex | MAT writer | MAT | thermal-data-enrichment | MAT | main | **MAT (530+698 dirty)** | RUNNING | IMPLEMENTING? | VERIFY |
| OPENCODE | EXTERNAL_AI_APP | OpenCode | IDE/UI worker | IDE-Workspace | P0-A binding | IDE-Workspace | master | GenesisShell+runtime | RUNNING | FIXING? | VERIFY |

---

## 3. External worker baselines (do NOT compete with write-sets)

- **CODEX / MAT:** baseline `cc805f8` (pushed, clean). Write-set = MAT working
  tree (530 dirty + 698 untracked, thermal-data/book/catalog work). **Codex is
  the sole MAT writer.** Hermes monitors read-only; no writes to MAT until
  Codex completes or is confirmed interrupted.
- **OPENCODE / IDE-Workspace:** baseline `af2af48` (pushed, clean). Write-set =
  GenesisShell.tsx + index.ts + runtime/ (P0-A binding, interrupted mid-fix).
  OpenCode owns this until its unit completes or is confirmed interrupted.

---

## 4. Runtime services (post-power-cut state)

| Service | State | Action |
|---|---|---|
| Codex.exe (x2 + helpers) | RUNNING | monitor, don't interfere while generating |
| OpenCode.exe (x5) | RUNNING | recover P0-A session; input channel historically unreliable |
| Hermes (me) | RUNNING | supervising |
| Ollama | OFFLINE (died in cut) | restart needed — `ollama serve` (local, free) |
| Docker | daemon DOWN | restart needed if used |
| WSL (docker-desktop, Ubuntu, OpenClawGateway) | Stopped | restart if needed |
| LM Studio / llama-server | not running | optional |
| node.exe (x3) | RUNNING | dev/build |

None of these are programme blockers; all are `ENVIRONMENT_PERMISSION_GATE` /
restart-needed. Recorded, not re-asked.

---

## 5. Interrupted units to resume (do NOT restart — continue)

1. **Supervisor Dashboard UI** (IDE-Workspace-dashboard worktree, af2af48,
   branch `unit/supervisor-dashboard-ui`) — backend is DONE & merged (`3083ae7`);
   UI slice is `READY_FOR_DELIVERY`, was blocked on OpenCode input channel.
2. **P0-A runtime binding** (IDE-Workspace master) — OpenCode's fix interrupted;
   3 historical tsc errors; re-verify then let OpenCode finish or Hermes
   supplements in an isolated worktree.
3. **MAT thermal-data enrichment** (Codex) — in flight; monitor only.

## 6. Next actions (autonomous loop)

- Recreate 5–8 Hermes subagents for READY work (architecture audit, backend
  extension, QA, security, UI review, MAT research support, devops recovery,
  provenance).
- Verify P0-A tsc result; if OpenCode still owns it, queue correction; else
  Hermes supplements in `IDE-Workspace-dashboard` (isolated write-set).
- Register Codex as external worker with live heartbeat (git mtimes + process).
- Continue dashboard backend deferred adapters (worker heartbeat/staleness,
  live/OpenCode runtime sections) — unblocked, independent of Codex.
- Checkpoint after each bounded unit.

**continuation_required = true** (recovery complete; loop continues).

---

| OPENCODE / IDE-Workspace | 11:0x | 2026-10-12 11:0x | RECOVERING → RUNNING |

OpenCode was open but the agent was IDLE/INTERRUPTED (chat last active 8:00
PM pre-power-cut; no Stop/Working button; composer empty). Resumed by Hermes
via computer control: clipboard-paste (cat file | clip) + ctrl+a/ctrl+v into
the composer (per-keystroke typing was lossy — only 1 of 308 chars landed —
clipboard-paste is the reliable channel for this rich-text editor) + click
Send. Verified: message committed to transcript AND Stop button appeared
(agent generating). Resume prompt = "resume from exact pre-power-failure
state, do not redo completed work, recover uncommitted changes, rerun tests,
continue the bounded runtime-binding task, commit/push/remote-verify,
report evidence."

IMPORTANT (§49): the P0-A runtime-binding task OpenCode was interrupted on is
ALREADY COMPLETE — Hermes finished it in the isolated worktree
(IDE-Workspace/unit/supervisor-dashboard-ui @647c6e7, remote-verified, tsc
clean, 24/24 tests). OpenCode's resume should therefore re-inspect and
reconcile (not duplicate). Hermes will independently QA whatever OpenCode
produces against 647c6e7.

OpenCode confirmed WORKING: session message_count grew 343 → 351 (my resume
registered), and a live edit `GenesisShell.tsx +5 -1` appeared near the
honest-DOM-state region. §20 acceptance demo re-run post-recovery: ALL
adapters LIVE_VERIFIED against real data (Ollama 0.34.4 recovered, git, 2
team-registry workers, OpenCode session, SSE framing). One honest degradation:
`opencode` HTTP adapter = OFFLINE (serve :56993 still Basic-auth-gated; CLI
path works) — correct §15 honesty, not a defect.

---

## 8. Units delivered after the resume (2026-10-12 ~11:30-12:00)

| unit | branch | commit | evidence |
|---|---|---|---|
| External-worker telemetry (Codex rollout adapter + OpenCode liveness monitor) | unit/external-worker-telemetry | **fb14a89** (pushed) | 39/39 tests; both adapters smoke-tested LIVE (codex ACTIVE/43 rollouts, opencode ACTIVE) |
| Quota-aware hive scheduler | (pending push) | 09b7e3d | 65/65 targeted tests; honesty gates proven |

Telemetry adapters: `read_codex_state` (rollout JSONL, never touches
auth/config/secrets) + `read_opencode_liveness` (sanctioned `opencode db`
channel — plain sqlite3 deadlocks the live WAL, verified). `_run_cli` fixed
to use `subprocess.list2cmdline` (shlex.quote mangled SQL args through
cmd.exe — a real rc=1 bug). Heartbeats reuse `worker.heartbeat`, coalesced
to verdict changes.

Hive scheduler (`compute/hive_scheduler.py`): quota ledger with
VERIFIED/OBSERVED/ESTIMATED/UNKNOWN honesty (§38 — UNKNOWN never becomes an
invented %), WORKER_SCORE router with hard gates: FREE_FIRST_STRICT (PAID
ineligible at budget 0), PRIVACY BEFORE QUOTA (SECRET never leaves local),
ONE WRITER PER WRITE-SET (§13), exhausted-quota skip (§27), large-task
penalty on scarce quota (§8), reservation (§25). Reallocation excludes the
old worker and emits structured JSON handoffs (§14). Full save/load
persistence (§37 power-failure recovery). Extends team_registry +
app_registry — no parallel systems (§49). Dashboard: `hive` section exposes
overview/workers/quotas/waiting_for_quota/handoffs.

NEXT UNITS (queued): (a) full-repo regression + merge both branches to main;
(b) live tier/quota audit of external apps (gradual, no logins/changes);
(c) dashboard workforce view rendering the hive section (UI slice);
(d) Codex MAT QA on completion.

---

## 7. Live worker heartbeats (verified this session, 2026-10-12 ~11:0x)

| worker | evidence | state |
|---|---|---|
| CODEX / MAT | git index mtime 10:03, `MAT-ADVANCED-RESUME.md` mtime 10:31, HEAD `cc805f8` | **ACTIVE** (writing ~14 min ago) — monitor read-only, do NOT touch write-set |
| OPENCODE / IDE-Workspace | P0-A files last modified 2026-10-09 20:25 (3 days), nothing in last 10 min | **IDLE/ABANDONED** write-set → Hermes finishing P0-A in isolated worktree |
| Ollama | restarted this session, `/api/version` → 0.34.4, dashboard adapter LIVE_VERIFIED | **RECOVERED** |
| Docker / WSL / LM Studio | down (power cut) | RESTART_NEEDED (not blockers) |

## 8. P0-A fix in progress (Hermes, isolated worktree `IDE-Workspace-dashboard`)

OpenCode's P0-A runtime binding was interrupted with 3 tsc errors. OpenCode has
been idle 3 days → per §11(B) Hermes is finishing it in the isolated worktree
(branch `unit/supervisor-dashboard-ui`), NOT touching OpenCode's master checkout.

Fixes applied (verified: the 3 GenesisShell errors are gone from tsc):
1. import `./runtime/types` → `./runtime/runtimeTypes` (+ `RuntimeBinding`).
2. removed duplicate `messages` useState; local echo is now a separate
   `localEcho` buffer merged (de-duped by id) with binding-derived `messages`.
3. `runtime?: RuntimeBinding` added to `ViewCommonProps` (optional, so tests /
   minimal embeds still render). HomeView/ChatView accept it.

Pending: worktree `npm install` (done) → `tsc --noEmit` + `vitest run` must be
clean before commit. Then commit + push + remote-verify on
`unit/supervisor-dashboard-ui`.

---

## 9. Knowledge Layer + Resource Governor + Permanent Supervision (2026-10-12, Agent-Bridge-dashboard @ 9355779)

Delivered on branch `unit/external-worker-telemetry` (Agent-Bridge-dashboard),
all pushed + remote-verified: 3e31f97 (knowledge+governor+toolchain fix) →
9355779 (supervision+dashboard wiring). 140/140 targeted tests green
(26 supervision + 23 knowledge + 22 governor + 24 hive + 45 dashboard).

### 9.1 Project Knowledge Layer — `compute/knowledge_index.py`
One indexed, provenance-preserving knowledge base over the AUTHORISED corpus
so hive workers retrieve task-relevant context instead of re-reading
everything (§15-§20). Pipeline: discover → sha256 content-hash → parse →
extract (summary = actual opening, speaker markers kept inline) → classify →
dedupe → map-to-project (keyword evidence; "unmapped" rather than guessing)
→ extract requirement tokens (AETH-IDE-441 / MAT-124) → index → retrieve.
Incremental sync (§19): NEW/CHANGED/DELETED by hash; deleted files recorded.
Runtime artifact `knowledge_index.json` is gitignored (personal paths).
**LIVE EVIDENCE:** 604 files scanned → 534 objects (70 deduped), 0 errors,
all VERIFIED confidence; mapped genesis 147 / agent-bridge 49 /
ide-workspace 39 / mat 26 / unmapped 273. Task-scoped retrieval returns
precise hits with provenance hashes; re-sync is a perfect no-op (604
unchanged). Sources resolved via %USERPROFILE%/%EXTERNAL_DRIVE% placeholders.

### 9.2 Resource Governor — `compute/resource_governor.py`
MAXIMUM USEFUL THROUGHPUT not max processes (§10-§14, §31-§35). Live sampling
(cpu/ram/gpu/vram/disk) with per-axis honest confidence (UNKNOWN never a
fabricated 0%). Pressure HEALTHY/ELEVATED/PRESSURE/CRITICAL; admission admits
a task only if all axes stay within gates after demand + reserve; reserve
SCALES with class so LIGHT work is never vetoed (§25 BLOCKED TASK != BLOCKED
PROGRAMME). **LIVE:** at 70% RAM/ELEVATED — LIGHT admitted, MEDIUM/HEAVY/
GPU_HEAVY deferred. Adaptive throttling + explainable verdicts with
privacy-aware offload hints.

### 9.3 Toolchain discovery fix — `machine_capability.py`
`_run_probe` gained the list2cmdline shell fallback (npm/.cmd shims raise
FileNotFoundError under shell=False). **LIVE:** 28 of 30 tools WORKING
(clang 22.1.8, MinGW, cmake 4.4.2, python 3.11+3.14, uv, node 24/npm 11,
rust 1.98, dotnet, OpenJDK 21, Go 1.27, git 2.55, docker 29.7.2,
arduino-cli, sqlite3, wsl); lld/lldb honestly AVAILABLE_BUT_BROKEN.

### 9.4 Permanent Active Supervision — `compute/supervision.py`
Hermes is the ACTIVE SUPERVISOR, not a dispatcher (§1-§38). WorkerRecord with
the FULL §2 vocabulary (19 states); heartbeat + stall detection (§4
investigate-then-act: INTERRUPTED at checkpoint, never assumed dead);
mandatory structured Handoff (§5); review queue that drains every handoff —
none left unread (§30); verdicts (§6) ACCEPT/CORRECTION_REQUIRED/
CONTINUE_SAME_WORKER/EXTEND_SCOPE/REASSIGN/CROSS_AGENT_REVIEW/BLOCKED, and
**ACCEPT WITH ZERO EVIDENCE IS REFUSED** (§2: completion is evidence-backed);
gap analysis creates tasks (§7/§19, CRITICAL/HIGH/MEDIUM/LOW/DEFERRED);
auto-assignment (§8/§25); JSON persistence with continuation_required (§32).

### 9.5 Dashboard wiring — `nodes/supervisor.py`
`refresh_snapshot` gained three optional sections: supervision (workers by
status, handoffs pending, gaps by severity, continuation_required),
resources (pressure + live sample + throttle actions), knowledge (objects,
by_type, by_project, by_confidence). Each fact carries SourceFact honesty
(LIVE_VERIFIED / DEGRADED on adapter error — never fatal).

## 10. OPENCODE RECOVERED + QA'D — cb1eb26 is canonical P0-A (2026-10-12 ~13:0x)

Per §46 (inspect both workers; ACT, don't just report):
- **OpenCode was IDLE** 38 min (last session update ~12:26) — but it had
  FINISHED its bounded unit on its own: commit `cb1eb26` "P0-A: bind the
  Genesis UI to real Agent Bridge runtime state", local == origin/master 0/0.
  Read its AX tree: no Stop button, composer idle, last edits
  conference.test.tsx + GenesisShell + views + index.ts, running
  vitest/tsc/vite.
- **Hermes independent QA of cb1eb26:** `npx vitest run src/genesis-ui
  --maxWorkers=1 --fileParallelism=false` → **12 files, 175 tests passed,
  exit 0**. Its implementation has `useGenesisRuntime` as the single network
  boundary + `bounds.test.ts` architecture enforcement (better than my
  worktree version).
- **Codex was ACTIVE** (rollout mtime 12:56 today) working on MAT — left
  alone (read-only monitoring).

### 10.1 RECONCILIATION — 647c6e7 marked SUPERSEDED (§49 no duplicate systems)
My worktree fix `647c6e7` (unit/supervisor-dashboard-ui) and OpenCode's
`cb1eb26` solve the same P0-A problem with equivalent mechanisms (local
message echo). OpenCode's version is committed, pushed, independently QA'd
(175 green) and adds the `__GENESIS_RUNTIME_SOURCE__` debug override mine
lacks. **Ruling: cb1eb26 (master) is canonical; 647c6e7 is SUPERSEDED —
kept as provenance, not deleted.** No merge needed; do not resurrect the
worktree for P0-A.

## 11. Remaining work (next actions, in order)
1. OpenCode next task (§8/§25): send continuation — P0-A accepted; assign
   the next READY unit (dashboard UI slice per scratch/opencode_dashboard_ui_prompt.md,
   now deliverable via clipboard-paste) and verify it resumes.
2. Codex MAT QA when its current unit completes (ACTIVE, rollout 12:56).
3. Regression: full 2218-test suite cannot complete as one run (420s host
   foreground limit + host kills background jobs; slow files are live-CLI
   tests 8-11s each). Verified green: 140 targeted + 175 IDE-Workspace
   genesis-ui. Known pre-existing env failure: test_acquisition_queue.py
   `test_fallback_skips_dead_model` pings live Ollama qwen3 (ollama was
   DOWN at check time) — environment state, not a code regression.
4. Ollama restart pending (serve died again this session).

---

## 12. §46 SUPERVISOR ACTION — OpenCode check-in + next-task assignment (2026-10-12 ~13:2x)

Per §45/§46 (ACT, don't just report): OpenCode was IDLE 38 min after
FINISHING cb1eb26. Hermes QA'd it (175/175 green, ACCEPT), then assigned the
next READY unit — **Supervisor Dashboard UI V1** (React frontend for the
/v1/supervisor/* API; honesty-vocabulary chips; shadcn/ui + Radix; new
src/supervisor-ui/ tree; genesis-ui untouched; TDD).

Delivery: clipboard-paste channel (2807-byte prompt staged via cat|clip,
foreground ctrl+a/ctrl+v — background key-combo delivery is dropped by the
Chromium surface per tool verdict; escalated correctly). Verified RESUMPTION
two ways: (1) opencode db time_updated 2s fresh, (2) AX tree shows composer
cleared + Send gone + OpenCode actively writing src/supervisor-ui/components/
index.ts (Panel/Badge/StatusDot/Tabs/EmptyState/Progress ui exports +
TeamStrip/ConferenceGrid re-exports) — i.e. it understood the assignment and
started the component layer.

Codex verified ACTIVE (rollout mtime 12:56, MAT) — left alone (read-only).

SUPERVISION STATE: both external workers RUNNING. No idle workers, no unread
handoffs, no uncorrected failures. Hermes continues the §33 loop: QA OpenCode
on its next completion, QA Codex on MAT completion.

---

## 13. PERSISTENT SUPERVISOR RUNTIME — the chat no longer hosts the loop (2026-10-12 ~14:4x)

THE CHAT MAY END. THE SUPERVISOR MUST NOT. (§runtime directive)

Delivered on Agent-Bridge-dashboard `unit/external-worker-telemetry`, pushed
+ remote-verified: aa41dc0 (runtime + quota pools) -> ed317ab (honesty
contract + logon launcher).

### 13.1 compute/supervisor_runtime.py — the durable process
- §33 cycle: adapters observe workers -> heartbeats -> idle/stall detect ->
  handoff review -> fast gap -> watchdogs -> atomic checkpoint -> sleep.
- §9 Universal ExternalWorkerAdapter: status() / send_instruction() /
  current_task() / quota_state(). Real adapters, both live-verified:
  * OpenCodeAdapter — `opencode db` telemetry; `opencode run` headless
    instruction. GUI-composer clipboard limitation recorded, not hidden.
  * CodexAdapter — rollout-JSONL newest-by-mtime (a resumed old session
    writing NOW is correctly RUNNING); `codex exec resume --last` = the
    session-preserving CONTINUE channel (§36).
- §45.8: idle -> automatic check-in (CONTINUE THE CURRENT BOUNDED TASK) ->
  _pending_verification until the worker verifiably RUNS again. One honest
  continuation computation.
- §11-§14 watchdogs: unread handoffs / idle-without-reason (SUPERVISOR
  DEFECT) / ready-work-with-idle-workers; scans ALL supervised workers so a
  vanished adapter never drops a worker (§32).
- §18/§32: atomic checkpoint (tmp+replace); recover() reloads state, marks
  stale heartbeats INTERRUPTED. continuation_required computed FRESH at
  persist — a power-cut checkpoint is always truthful (§27).
- CLI: --once / --status / daemon; --with-opencode --with-codex.

### 13.2 Quota pools — compute/hive_scheduler.py (§quota directive)
Independent windows, never one number (§2): SHORT_WINDOW (Codex five-hour) /
WEEKLY / MONTHLY / CREDIT_PERIOD / MODEL_SPECIFIC / REQUEST_RATE /
CONCURRENCY / BANKED_RESET / PROMOTIONAL. QuotaLedgerEntry gains pool /
pool_id (shared pools, §15) / paid_option_available (recorded, NEVER acted
on, §10). worker_capacity() = MOST RESTRICTIVE known pool (§4: 80%
five-hour + 18% weekly is an 18% worker); any known-empty pool = hard skip;
UNKNOWN never treated as exhausted (§38). record_plan() = full PlanProfile.
New OWNED_PAID_ENTITLEMENT tier for the owner's existing Codex/ChatGPT sub.

### 13.3 LIVE EVIDENCE (§30/§32 acceptance)
- Daemon RUNNING as a background process (pid 22072, 120s cycles,
  checkpointing). Started WITHOUT elevation — no chat turn required.
- Single-cycle run against the REAL workers: both detected IDLE past their
  windows -> automatic check-in fired for BOTH without any chat message.
- Headless delivery verified end-to-end: runtime sent an instruction via
  `opencode run`; the model replied exactly RUNTIME-CHECK-OK ->
  delivered=True with real response evidence. §30 D/E proven.
- Honest failure captured earlier in the session: with Ollama down, both
  headless deliveries returned delivered=False ('Cannot connect to API' —
  opencode run defaults to the local qwen model). The runtime did NOT
  fabricate success; Ollama was restarted (0.34.4 UP) and delivery then
  worked. The honesty contract is test-pinned (17/17 runtime tests).

### 13.4 OWNER GATE (the one unavoidable gate, §20/§27)
`schtasks /Create` needs an elevated shell (Access denied otherwise). The
single owner action is documented in
docs/SUPERVISOR_RUNTIME_STARTUP.md (one elevated PowerShell command). It
blocks ONLY auto-start-at-logon; the runtime is built, tested, live-verified
and RUNNING without it. Start-now/status/uninstall need no elevation.
