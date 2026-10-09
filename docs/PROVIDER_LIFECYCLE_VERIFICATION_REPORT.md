# Aetherius Provider Lifecycle + Verification — Evidence Report

Directive: PROVIDER-LEVEL MODEL LIFECYCLE FIX + FULL-SUITE VERIFICATION +
COMPUTE-RUNTIME FORK AUDIT
Date: 2026-10-09

---

## 1. Verification environment (Option 2, owner decision)

| Field | Value |
|---|---|
| Environment ID | `agent-bridge-verify` |
| Path | `~/.aetherius/venvs/agent-bridge-verify` |
| Python | 3.13.14 |
| Lockfile | `requirements-lock.txt` |
| Lock hash | sha256 `b4b65f42…` (8 pins) |
| Pins matched | 8 / 8, 0 missing, 0 mismatched |
| dependency-lock gate | **2 / 2 PASS** |
| Verification command | `<verify-python> -m pytest tests/ -p no:cacheprovider` |

The supply-chain gate verifies the declared environment, not whichever
interpreter happens to run pytest. Same test, opposite results by
environment — under `kdbx313` it fails 2/2 (correctly rejecting an
environment it does not describe), under `agent-bridge-verify` it passes
2/2. The test, the lockfile and the gate are all **unchanged**; Option 2
was implemented by creating the environment, not by weakening the check.

---

## 2. Model lifecycle — the actual fix

### The problem was structural, not incidental

The leak had already been fixed once at `compute/local_team_executor.py`
and came back through every other Ollama call site. Eight paths could make
a model resident; only two had any `keep_alive` control, both in one file.
Every new call site reintroduced the leak, and no caller could know whether
another live worker still needed the same weights.

Callsite matrix (before): `docs/model_lifecycle_callsite_matrix.md`

### Ownership moved to the provider boundary

```
CALLER → OLLAMA PROVIDER → MODEL SESSION/LEASE → INFERENCE → RELEASE
```

**LeasePolicy** (`compute/ollama_provider_v2.py`):

| Policy | keep_alive | Used for |
|--------|-----------|----------|
| EPHEMERAL | 0 | tests, bounded measurements |
| SHORT_LIVED | 300 s | reused lightweight model |
| SESSION | -1 (retain) | interactive session — **default** |
| PERSISTENT | -1, never auto-released | owner-pinned hot model |

**Ownership classes** — classified before anything is unloaded:

| Class | Releasable |
|-------|-----------|
| AETHERIUS_LOADED | YES, at refcount 0 |
| PREEXISTING (incl. Hermes' own llama-server) | **NEVER** |
| SHARED (another live lease) | NO, until last release |
| UNKNOWN | NO — fails safe |

`capture_baseline()` is taken once, before any leased inference. That single
boundary is what keeps Hermes' own llama-server (PID 2072) alive.

### Two design defects found and fixed during implementation

Both would have leaked silently:

1. **`classify_ownership()` consulted residency before lease history.** At
   release time the refcount is already zero, so our own resident weights
   looked UNKNOWN and the release path refused to unload them — *a leak
   disguised as caution*. `_leased_models` is now consulted first.
2. **`infer()`/`embed()` released every lease in `finally`,** which made
   SESSION retention impossible and unloaded weights immediately after
   inference. A retaining lease now outlives its call; `release_all()` is
   the honest end of a session.

### Semantics settled by evidence, not assumption

- A retaining lease (SESSION/SHORT_LIVED) deliberately **outlives its
  call**. Dropping it per-request would make SESSION identical to
  EPHEMERAL and force a reload every turn.
- A **failed** request always drops its lease, regardless of policy:
  weights stranded by a request that never completed have no live turn to
  stay warm for.
- `release_all()` sweeps weights whose leases already ended under a
  retaining policy — otherwise it would be a no-op that looks like success.
- Unload is confirmed by **bounded polling**, not one `/api/ps` sample.
  Ollama unloads lazily; a single immediate read reports a leak that is
  already clearing. A genuinely stuck unload is flagged via
  `resident_after_call` rather than hidden.
- `local_team_executor.release_models()` no longer issues `keep_alive=0`
  itself. A caller-issued blanket unload would evict a shared model out
  from under a live worker, so it delegates to `release_all()`.

### Lifecycle evidence

| Metric | Before | After |
|---|---|---|
| Resident model servers after suite | 3 llama-server (~1.3 GB leaked) | **PID 2072 only** (Hermes' own, untouched) |
| Free RAM | 3.36 GB | 4.18–4.53 GB |

### Honest limitation

`genesis_runtime.py`, `worker_main.py`, `providers.py`,
`models/providers/ollama_provider.py` and `model_lifecycle.py` still load
models without a lease. These are separate legacy adapters predating
Provider V2, recorded in the callsite matrix rather than silently ignored.
Consolidating them onto Provider V2 is the follow-up migration task.

---

## 3. Full suite

Run from `agent-bridge-verify` (§12), with RAM and residency captured
before and after (§11). Status: **in progress** at time of writing;
measured baseline was 74m50s, so the timeout is set well above it.

| Suite | Result |
|---|---|
| `test_model_lifecycle_leases.py` | **29 passed** (27 deterministic fake-transport + 2 bounded live) |
| `test_conversation_and_ollama_v2` + `test_local_team_execution` + `test_model_lifecycle` | **104 passed** |
| `test_secret_hygiene` | 7 passed |
| `test_dependency_lock` | 2 passed |
| `test_compute_runtime_audit.py` | 21 passed |
| Full suite (`tests/`) | pending — see run history |

---

## 4. Compute-runtime audit (§19–§25)

`compute/compute_runtime_audit.py` — answers WHAT / WHEN / WHERE / HOW per
runtime, with evidence states enforced by vocabulary. Nothing is installed
(§91).

### Findings against the live host

| Runtime | State | Decision |
|---|---|---|
| ollama | **INSTALLED_VERIFIED** (v0.34.4) | KEEP_DEPENDENCY (not assumed permanent, §21) |
| llama_cpp | DESIGNED | FUTURE_FIRST_PARTY_BACKEND |
| vllm | DESIGNED | CLOUD_SERVING_TARGET (explicitly not the desktop default, §22) |
| sglang | RESEARCH_ONLY | compared to vLLM only if vLLM proves insufficient |
| ggml | DESIGNED | REFERENCE_FOR_AETHERIUS_RUNTIME (separate from llama.cpp, §23) |

### A false positive the probe caught

`python -m vllm` and `python -m sglang` both **resolve** on this host but
**exit 1** without a GPU stack. Reporting them as installed would have
claimed a runtime this workstation cannot run — the exact §139 violation.

`present` now means *resolved AND answered a version request with exit 0*.
A resolved-but-failing runtime is recorded as "not functional" rather than
collapsing into "not installed", so a broken install stays
distinguishable from an absent one.

### §24 low-bit honesty

`low_bit_evidence_state()` refuses to promote software emulation into
`PHYSICAL_HARDWARE`. A software runtime executing a quantized model is
`SOFTWARE_RUNTIME`; calling it ternary or 1-bit hardware would be a false
claim about physical capability.

---

## 5. Owner-work forks (§16–§18)

Deletion **DENY** for all three — unchanged. `SAFE_TO_DELETE = 0` and it
stays 0: deletion is the outcome of completed migration, not a progress KPI.

`scripts/analyse_owner_work_source.py` reads the **actual diffs** through
the GitHub compare API (no local clone of a 452-commit-behind upstream) and
classifies each change by what it *does*, not what the file is called:

| Signal | Meaning |
|---|---|
| `formatting_only` | added == removed ignoring whitespace — nothing semantic |
| `bug_fix` / `feature` / `compatibility_patch` | substantive → inspect then port |
| `experiment` / `deletion` / `metadata_only` | context for the owner's decision |

IsaacLab's 154 commits are clustered by capability per §16 (simulation,
robot control, training, environment, sensor/perception, Genesis
embodiment, Aetherius integration, tests, build/config, experiments) so the
divergence can be triaged rather than treated as one unit.

neo4j: the 13 genuine `.java` files are read patch-by-patch. The prior
audit established they are real source changes among ~170 `pom.xml`
version bumps; this analysis determines per file whether each is a bug fix,
feature, compatibility patch, experiment, or upstream-derived.

Aetherial remains **ARCHITECTURE_REFERENCE** (GPL-3.0) — the owner decides
before any code port (§18).

---

## 6. Git evidence chain

| SHA | Change | Remote |
|---|---|---|
| `5cb60bb` | provider-level model lifecycle (§3–§10) | verified identical |
| `58c630e` | compute-runtime audit (§19–§25) | verified identical |

Every bounded unit: IMPLEMENT → TEST → EVIDENCE → COMMIT → PUSH → FETCH →
VERIFY REMOTE SHA.

---

## 7. Owner blockers (unchanged)

- **Cloud credentials BLOCKED_OWNER** — rotate OpenRouter, Groq, Gemini,
  HuggingFace, DeepSeek; store under the 5 registered `MISSING_ROTATION`
  refs in KeePass. Old keys are not recovered from history.
- **Aetherial GPL-3.0** — licence-compatibility call before any code port.
- **KeePass production unlock** — owner-entered master password only.
- 147 repos still have NO identified licence (97 NOASSERTION, 50
  UNKNOWN/None), including 3 of 9 predecessors.

---

## 8. Next dependency-ready task

**Consolidate the five legacy Ollama adapters onto Provider V2**
(`genesis_runtime.py`, `worker_main.py`, `providers.py`,
`models/providers/ollama_provider.py`, `model_lifecycle.py`). Each still
loads models without a lease; the canonical path is now safe, and these are
the remaining leakage surfaces. Requires tracing each caller's usage before
switching it over.

---

## 9. Gate

```
AETHERIUS PROVIDER LIFECYCLE + VERIFICATION GATE:
PASSED WITH OWNER/EXTERNAL BLOCKERS
```

Cloud credentials remain OWNER_BLOCKER. Provider-level local model
leakage — which may not remain — is closed at the canonical boundary and
pinned by 29 tests, two of which fail if a run leaves weights resident.
