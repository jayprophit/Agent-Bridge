# GENESIS LOCAL / CLOUD / HYBRID RUNTIME READINESS — AUDIT

**Unit:** Local/Cloud/Hybrid Runtime Readiness & Deployment Audit
**Role:** Hermes architecture/research/audit (reconciliation — NOT a build unit)
**Repo:** Agent-Bridge, worktree branch `unit/cloud-hybrid-runtime`, HEAD `e3a628a`
**Date:** 2026-10-09
**Method:** 4 parallel read-only cluster audits (runtimes/providers, execution/placement/
registries, routing/privacy/vault, avatar/realtime/voice). Every classification carries
file:line evidence. Claims marked **[verified]** were reproduced directly by the
orchestrator; others are cluster-audited and attributed.

**Evidence-state vocabulary:** REPRESENTABLE (the registry can describe it) · TESTED
(a passing test exercises it) · LIVE_VERIFIED (actual execution demonstrated) ·
BLOCKED (owner/external gate). A capability is only VERIFIED when a passing test
exercises it. An adapter existing is never "usable."

---

## The one invariant this audit is measured against

From the owner's master spec (`GENESIS DIGITAL ORGANISM, NANOBRAIN & VIRTUAL COMPUTE
ARCHITECTURE`):

> **VM-A = Genesis Digital Organism** — identity/state (brain, physiology, Nanobrain
> runtime, internal memory, signalling). **VM-B = Virtual Computer / Compute Lab** —
> completely separate, *external to Genesis anatomy* (vCPU/vGPU/vNPU/vRAM/storage/…).
> "VM-A can connect to/use VM-B. VM-B is NOT part of Genesis's anatomy."

**Compute location (VM-B, local or cloud) must never define Genesis identity (VM-A).**
Switching LOCAL→CLOUD→HYBRID, changing provider, or changing model must not create a
new Genesis. This audit tests whether the code enforces that boundary or only
describes it.

---

## 1. CURRENT STATE AUDIT — headline

Aetherius has a **genuinely capable, rigorously-tested local execution core** and a
**well-modelled but largely unwired cloud/hybrid abstraction layer**. The gap is not
missing components — it is **missing wiring**: several complete, tested libraries have
zero production call sites, so the system can *describe* distributed execution in
detail but only *prove* local execution.

| Dimension | Verdict |
|---|---|
| Local inference (Ollama) | **LIVE_VERIFIED** — 33/33 lease tests incl. 2 live |
| Local team execution (through registry) | **LIVE_VERIFIED** — 38/38 live, real A→B handoff |
| Node transport (HTTP + real TLS, 2 processes) | **LIVE_VERIFIED** for transport; execution synthetic |
| Cloud provider execution | **REPRESENTABLE only** — BLOCKED_OWNER creds |
| Hybrid execution | **REPRESENTABLE only** — and the split is discarded (defect) |
| Team logical-size vs concurrency separation | **VERIFIED** — declared, enforced, measured |
| Cost/budget engine (default paid = $0) | **VERIFIED** — fails closed |
| VM-A/VM-B identity boundary | **PARTIAL** — VM-B coded, no Genesis identity object |
| Privacy routing enforcement | **PARTIAL** — enforced on 2 paths, fail-open default |
| Data policy / residency / retention | **MISSING as deployed** — engine exists, 0 call sites |
| Execution checkpoint/resume | **MISSING** — only a file-manifest rollback + a stub `resume()` |
| Avatar render tiers T0–T4 | **MISSING** in this repo (exists only in the IDE-Workspace UI scaffold) |
| Capability-based provider selection | **PARTIAL** — mechanism tested, vocabulary absent, unwired |

---

## 2–4. THE THREE EXECUTION PROFILES

### LOCAL_PROFILE — **LIVE_VERIFIED**
The only profile with demonstrated execution.
- Inference: `OllamaProviderV2` lease-aware (EPHEMERAL/SESSION/SHORT_LIVED/PERSISTENT),
  ownership classes prevent evicting pre-existing models. `test_model_lifecycle_leases.py`
  33/33 incl. 2 live tests.
- Team execution: `LocalTeamExecutor` → `OllamaProviderV2` → lease lifecycle.
  `test_local_team_execution.py` 38/38 live (not skipped), 3 logical workers, distinct
  worker_ids, real structured handoff, independent reviewer, one trace_id.
- Placement: `resources/` (pool/classifier/scheduler/balancer/monitor) is RAM/GPU/CPU
  aware, 17 tests green — **but imported only by `scripts/` acceptance runners, never a
  production path** [cluster 2].

### CLOUD_PROFILE — **REPRESENTABLE, BLOCKED_OWNER**
- Adapters exist for OpenAI/Gemini/DeepSeek; OpenRouter/Groq are capability-declaration
  only (no adapter file). All 5 cloud providers `probe_state=BLOCKED_OWNER`,
  `requires_credentials=True` (credentials previously exposed; owner rotation required).
- `form_team_cloud` (enterprise_team.py:962) forms a TEAM_CLOUD whose only test asserts
  the mode *string*, not execution. The cloud WorkerPool is an empty counter; no cloud
  worker calls a provider.
- **BLOCKED for live use** regardless of adapter presence — the five `MISSING_ROTATION`
  credential refs (owner must rotate into KeePass).

### HYBRID_PROFILE — **REPRESENTABLE, and defective**
- `form_team_hybrid` (enterprise_team.py:973-982) accepts `local_roles`/`cloud_roles`
  then **discards the split**: `form_team(objective, local_roles + cloud_roles, …,
  allow_cloud=True, TEAM_HYBRID)`. Every worker is placed as cloud [verified]. The test
  only asserts the three pool *keys exist*, never which pool workers landed in, so it
  passes green [cluster 2].
- Blocked by cloud creds anyway, so the defect is latent — but the *placement intent* is
  already lost before creds would matter.

**All three are ONE Genesis identity in design; only LOCAL has a proven runtime.** No
code object represents Genesis identity to prove the "switching doesn't create a new
Genesis" invariant (see §14).

---

## 5. PROVIDER MATRIX

| Provider | Adapter | Credential state | Local-first eligible | Live use |
|---|---|---|---|---|
| ollama-local | `ollama_provider_v2.py` | none needed | yes | **LIVE_VERIFIED** |
| llama-cpp-local | `llama_cpp_provider.py` | none | yes (adapter only) | runtime absent (`llama-server` not on PATH) |
| lm-studio-local | `lm_studio_provider.py` | none | NOT_CONFIGURED | not installed |
| openai | `openai_provider.py` | BLOCKED_OWNER | no | blocked |
| gemini | `gemini_provider.py` | BLOCKED_OWNER | no | blocked |
| deepseek | `deepseek_provider.py` | BLOCKED_OWNER | no | blocked |
| openrouter | none (declaration only) | BLOCKED_OWNER | no | blocked |
| groq | none (declaration only) | BLOCKED_OWNER | no | blocked |
| huggingface | none | BLOCKED_OWNER | no | blocked |
| vllm / sglang | none | n/a | excluded from desktop default by test | not installed |

Free-vs-paid gating: `cost_engine.default_cost_engine` = FREE_ONLY, all caps $0,
`owner_approved_paid=False`, fails closed on unverified providers [cluster 1, VERIFIED].
Only `local` is registered eligible by default.

---

## 6. FREE-QUOTA MATRIX

Not yet populated with live free-tier numbers — that requires the rotated cloud
credentials (BLOCKED_OWNER) to *probe* actual quotas. What is VERIFIED is the **policy
enforcement**: `Budget` (daily/monthly/per_task/per_provider), all-zero default,
`check_eligible` fails closed, alerts at 50/80/95/100% (test_hybrid_cloud_p0.py:316-468).
**Actual free-tier limits per provider are NOT VERIFIED — cannot be without creds.**

---

## 7. CAPABILITY MATRIX

**Key finding:** the requested capability vocabulary (`MATRIX_COMPUTE`, `LLM_INFERENCE`,
`STT`, `TTS`, `EMBEDDING`, `VISION`, `AVATAR_RENDER`) **does not exist anywhere in the
repo** (grep = 0). A *correct, tested* capability-selection mechanism does exist —
`compute/provider_adapters.py:90-104 find_for_capability()`, proven by
`test_registry_finds_providers_for_capability` — but **nothing imports it**. The
canonical gateway routes by task-type + vendor/provider name (`model_router.py:174-208`),
not by capability [cluster 1].

| Capability | Selection mechanism | Status |
|---|---|---|
| LLM inference | vendor/task-type router | PARTIAL (works, not capability-typed) |
| Vision | model registry `vision` flag | EXISTS |
| Streaming / tools / structured output | `error_taxonomy.py:225-245` vocab | EXISTS |
| STT | NOT_INSTALLED (honest) | MISSING |
| TTS | System.Speech (Windows) | VERIFIED-E2E local |
| Embedding | via ollama | VERIFIED |
| AVATAR_RENDER / MATRIX_COMPUTE | — | vocabulary absent |

---

## 8. EXECUTION-TARGET MATRIX

`compute/execution_target_registry.py` — 11 target types (local_pc, wsl, docker, vm,
ssh, vps, local_ollama, api_provider, serverless, gpu_cloud, cpu_cloud), capability- and
privacy-typed, 29 test defs [cluster 2]. **But:** seeded into `ai_gateway.py:81` and then
**never queried** (`execution_targets.` = 0 hits in the gateway);
`routing_decision_target()` (ai_gateway.py:497-502) **fabricates**
`EXEC-<PROVIDER>-001` instead of resolving a registered target — so responses carry
execution-target IDs that may name no registered target, undermining the audit trail
[clusters 1 & 2].

| Target | Representable | Executed |
|---|---|---|
| local_pc / local_ollama | yes | **LIVE_VERIFIED** (team + inference) |
| node (remote, via transport) | yes | transport LIVE_VERIFIED, work synthetic |
| wsl / docker / vm / ssh / vps | yes (typed) | NOT TESTED |
| gpu_cloud / cpu_cloud / serverless / api_provider | yes (typed) | BLOCKED_OWNER / NOT TESTED |

---

## 9. ROUTING POLICY (zero-cost-first)

Two parallel routers exist: `compute/providers.route_compute` (LOCAL_FIRST) and
`models/model_router.route` (LOCAL_FIRST filter). Policy intent is correct and tested
(`test_compute_routing.py` 11/11): PRIVATE/SECRET → local; SMALL → local; HEAVY
non-sensitive → free cloud; GPU → free GPU target; FREE exhausted → degraded local or
owner approval; PAID → disabled unless owner authorises. **Gap:** the policy is not
consumed by the capability/execution-target layers (see §7, §8), and `cost_engine` has
no dedicated test file.

## 10. FALLBACK POLICY

`model_router.set_fallback_chain()` writes `self.fallback_chains`; **nothing ever reads
it** (only the setter, the field init, one test) [cluster 4]. `inference_contract`
declares `local_fallback: True` in a policy dict no dispatcher consumes. So
"large→small→local" is **configuration, not runtime behaviour**. Avatar-side fallback is
binary 2D↔3D only (`ui/app.js:47-48`), no intermediate tiers. **Fallback is aspirational,
not implemented as a traversal.**

## 11. AVATAR T0–T4 RESOURCE MATRIX

**T0–T4 does not exist in this repo** — exhaustive grep across all file types = 0 hits
[cluster 4]. The only renderers are 2D (`ui/avatar.js`) and 3D (`ui/avatar-three.js`),
selected by `window.THREE` presence. The T0–T4 concept and the `registerAvatarRenderer`
seam live in the **IDE-Workspace UI scaffold** (separate repo, placeholder renderer,
`isLive=false`). Identity↔appearance separation *is* modelled here
(`avatar/protocol.py AvatarProfile`, presentation never pitch-derived, tested), but
"survives tier change" is untestable because tiers don't exist. **Recommendation: adopt
the IDE-Workspace renderer seam as the canonical avatar abstraction and define T0–T4
against it — do not rebuild.**

## 12. STATE-MIGRATION DESIGN

**MISSING.** No snapshot/checkpoint/migration path moves agent state or data between
LOCAL, CLOUD, HYBRID. `data_service_adapter.py` backup/restore is local-filesystem only
(SHA-256 manifest, no locality dimension). `checkpoints.py` is task-level file rollback,
not execution state. `team_execution_fabric.py:308 resume()` is an unimplemented Protocol
stub. `ExecutionLocation.LOCAL/CLOUD/HYBRID` exists as a rule *filter key* only. The
VM-A identity invariant (survives compute-location change) therefore has **no mechanism
to test it against**. This is the largest design-to-implementation gap.

## 13. REALTIME CONNECTION DESIGN

`voice/realtime.py` is real and good: bounded jitter buffer with drop accounting,
backpressure controller, turn state machine that raises on illegal transitions, working
barge-in, `RealtimePipeline.run_streaming_turn` starts TTS on first phrase. **But:** 2 of
5 loop stages are fixtures (listen = hard-coded 1.0 ms; transcribe = caller-supplied
strings); STT backend NOT_INSTALLED; TTS is real System.Speech (Windows-only, no
streaming); no reconnect/backoff for a dropped stream; nothing in the shipping runtime
calls `RealtimePipeline`; no HTTP route. Transport is stdlib HTTP(S)+SSE; WebSocket
honestly NOT_INSTALLED; no WebRTC. Live report exists (real Ollama stream + real TTS +
verified barge-in) but it blew its own latency budget (TTFT 27× target) while the
acceptance script still printed "PASS" because its gate never consults the budget
[cluster 4].

## 14. PRIVACY / TRUST-BOUNDARY MAP

**Strength — the node trust boundary is real and adversarially shaped**
(node_server.py:277-346): remote-owner gate runs first (local OWNER_FULL_ACCESS never
implies remote privilege); pairing uses `secrets`, SHA-256 token hashes, single-use,
HMAC `compare_digest`; privacy checked *before* private content is serialized; plaintext
refused for non-loopback before any body; `TlsConfig` reports CONFIGURATION_REQUIRED
rather than faking availability. Two-process TLS test (33/33).

**Gaps:**
- `privacy_allows_send` (node_transport.py:190-201) **fails open**: only LOCAL_ONLY /
  CURRENT_DEVICE_ONLY / LOCAL_FIRST / TRUSTED_NODES are handled; BALANCED /
  REMOTE_ALLOWED / SPECIFIC_PROVIDER **fall through to `return True`** [verified]. A
  permissive default on a privacy gate.
- `DataPolicyEngine` (data_fabric/data_policy_engine.py, default-deny, retention, data
  classes) and `ContextBroker` (knowledge_fabric) each have **zero production call
  sites** — retrieval is correct-but-unreachable, retention is inert metadata.
- `WindowsCredentialManagerStore` is `NotImplementedError` on all 3 methods — no
  production-grade at-rest secret store on Windows.
- Three non-overlapping privacy policy sources (gateway inference_contract vs node_server
  strings vs data_policy_engine) are never reconciled.

## 15. FAILURE / RECOVERY MATRIX

| Failure | Behaviour | Status |
|---|---|---|
| Cloud provider unavailable | failover taxonomy exists (13 classes, FAILOVER_ELIGIBLE) | taxonomy VERIFIED, traversal untested |
| Quota exhausted | cost engine fails closed, degraded local | VERIFIED (policy) |
| Model unavailable | `fallback_chains` written, never read | **not implemented** |
| Remote worker crashes | no execution checkpoint/resume | **MISSING** |
| Realtime stream drops | no reconnect/backoff | **MISSING** |
| Avatar renderer fails | binary 2D↔3D swap | PARTIAL (no tiers) |
| Internet unavailable | local-first path proven for inference+team | VERIFIED (local) |

## 16. TEAM-TO-COMPUTE MAPPING — **the strongest result**

`logical_team_size` vs `active_concurrency_limit` is declared as separate fields
(team_registry.py:273-274), **enforced in code** (enterprise_team.py:538 skips work at the
cap and counts `resource_blocked`), and **measured live** (local_team_executor.py:362-367
reports them separately), with a test that asserts they are not equal. This is exactly the
discipline a 16 GB host requires — a 12-worker logical team does not mean 12 simultaneous
heavy models. Caveat: `WorkerPool.acquire()` (team_execution_fabric.py:175-183) returns
`True` for an unregistered worker without incrementing `active_workers` → unbounded
[verified].

## 17. CURRENT BLOCKERS

- **Cloud credentials BLOCKED_OWNER** — 5 `MISSING_ROTATION` refs (OpenRouter, Groq,
  Gemini, HuggingFace, DeepSeek). Owner must rotate into KeePass. Blocks: all cloud/hybrid
  LIVE claims, the free-quota matrix, hybrid migration verification. Does NOT block the
  local work above.
- No production-grade at-rest secret store on Windows (WindowsCredentialManagerStore is
  NotImplementedError; KeePass production unlock is owner-entered).
- Aetherial GPL-3.0 licence call (owner) — separate from this unit.

## 18. TEST PLAN (for the gaps this audit found)

1. **Execution-resume test:** interrupt a team run, resume, assert identity + state
   continuity (closes §12). Currently no mechanism → this test defines the mechanism.
2. **Capability-selection wiring test:** request `AVATAR_RENDER`/`LLM_INFERENCE` by
   capability name through the gateway; assert a capability-satisfying provider is chosen
   (closes §7). Requires naming the vocabulary + wiring `build_default_registry()`.
3. **Hybrid placement test (strengthen):** assert workers land in the *correct* pool
   (local vs cloud), not merely that pool keys exist — this would have caught the
   `form_team_hybrid` defect.
4. **Privacy fail-closed test:** assert `privacy_allows_send` denies (not allows) an
   unhandled policy like BALANCED — would have caught the fail-open default.
5. **Fallback traversal test:** exhaust a provider, assert the chain advances to the next.
6. **Reconnect test:** drop a realtime stream mid-turn, assert resume.

## 19. IMPLEMENTATION GAPS (prioritised)

| # | Gap | Kind | Severity |
|---|---|---|---|
| G1 | Execution checkpoint/resume missing | new capability | high |
| G2 | Data policy / ContextBroker unwired (0 call sites) | wiring | high |
| G3 | Capability vocabulary absent + registry unwired | new + wiring | high |
| G4 | `privacy_allows_send` fails open | defect | high (privacy) |
| G5 | `form_team_hybrid` discards local/cloud split | defect | medium (latent, cred-blocked) |
| G6 | `WorkerPool.acquire()` unbounded for unregistered id | defect | medium |
| G7 | `routing_decision_target()` fabricates target IDs | defect | medium (audit trail) |
| G8 | Execution-target registry never queried for selection | wiring | medium |
| G9 | Model fallback chain written, never read | wiring | medium |
| G10 | Realtime reconnect absent | new capability | medium |
| G11 | No Genesis identity object enforcing VM-A/VM-B | new capability | medium |
| G12 | Avatar T0–T4 tiers absent (adopt IDE-Workspace seam) | new capability | medium |
| G13 | `node_registry.trusted_nodes()` OWNER_NODE NameError | defect | low (latent) |
| G14 | `test_realtime.py:143` TTFT==0.0 (clock granularity) | test bug | low (pre-existing) |

**Rejected during audit (not defects):** `comms/fabric.py` "syntax error" — a rendering
artifact from a stray carriage return; `compile()` parses the file cleanly. Verified and
excluded so it is not carried forward as a false finding.

## 20. RECOMMENDED NEXT BUILD UNIT

**Not a large build.** Per the reconciliation mandate, specify the next bounded unit:

> **Bounded unit A — "Make the local execution core the canonical path and close the
> fail-open gaps."** Small, high-value, no cloud dependency:
> 1. Fix G4 (privacy fail-open → fail-closed) and G6 (WorkerPool.acquire) and G13
>    (OWNER_NODE import) — three small, well-localised, test-backed fixes.
> 2. Wire `DataPolicyEngine` + `ContextBroker` into the gateway request path (G2) so
>    privacy/retention are enforced systemically, not per-hand-wired-path.
> 3. Strengthen the hybrid + privacy tests (Test Plan 3 & 4) so the defects above cannot
>    ship green again.
>
> This needs no rotated credentials and touches no OpenCode UI files. Cloud/hybrid LIVE
> verification (G1, §6 free-quota, §12 state migration) stays BLOCKED_OWNER until the
> owner rotates the five credential refs into KeePass.

---

## FINAL GATE (per capability)

```
LOCAL inference .................. LIVE_VERIFIED
LOCAL team execution ............ LIVE_VERIFIED
Node transport ................... LIVE_VERIFIED (execution synthetic)
CLOUD execution .................. BLOCKED_OWNER (representable only)
HYBRID execution ................. REPRESENTABLE (split defect, cred-blocked)
Cost/budget (paid off default) ... VERIFIED
Team size vs concurrency ......... VERIFIED
Capability-based selection ....... PARTIAL (vocab absent, unwired)
Privacy routing .................. PARTIAL (2 paths, fail-open default)
Data residency / retention ....... MISSING as deployed (unwired)
Execution checkpoint/resume ...... MISSING
Model fallback traversal ......... NOT IMPLEMENTED (dead state)
Avatar T0–T4 tiers ............... MISSING in repo (adopt UI-scaffold seam)
VM-A/VM-B identity boundary ...... PARTIAL (VM-B only, no identity object)

OVERALL: LOCAL core VERIFIED · CLOUD/HYBRID BLOCKED_OWNER ·
         abstraction layer well-modelled but largely unwired · 3 real defects to fix
```

**Honesty statement:** no runtime was installed, no model pulled, no cloud path claimed
live. Cloud providers are not called usable because an adapter exists; they are
BLOCKED_OWNER. Local execution is LIVE_VERIFIED because tests demonstrate it. The four
cluster audits were independently spot-verified by the orchestrator (one claimed defect —
a comms/fabric.py syntax error — was disproven and excluded).
