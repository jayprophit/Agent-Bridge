# Model Lifecycle Callsite Matrix — POST-CONSOLIDATION

Generated: 2026-10-09 (live repository scan)
Directive: PROVIDER V2 CONSOLIDATION (§consolidation)

## Why this document exists

The residency leak was fixed once at `compute/local_team_executor.py` and
then reappeared through other Ollama call sites. The cause was structural:
residency is a property of the *runtime*, but the ownership decision was
being made by individual *callers*. Every new call site reintroduced the
leak, and no caller could know whether another live worker still needed the
same weights.

The fix moved ownership to the provider boundary
(`compute/ollama_provider_v2.py`). This document is the **after-state**: the
evidence that all nine previously-unleased load paths now route through the
one canonical lease-aware transport.

## The nine paths — migration disposition

| # | File | Was | Now | Lease policy |
|---|------|-----|-----|--------------|
| 1 | `compute/ollama_provider_v2.py` | `infer()` `/api/generate` | canonical (owns) | SESSION default |
| 2 | `compute/ollama_provider_v2.py` | `embed()` `/api/embeddings` | canonical (owns) | SESSION default |
| 3 | `compute/ollama_provider_v2.py` | — | **NEW** `chat()` `/api/chat` | SESSION default |
| 4 | `compute/ollama_provider_v2.py` | — | **NEW** `infer_stream()` `/api/generate` stream | SESSION default |
| 5 | `models/providers/ollama_provider.py` | `_ollama_request` `/api/chat` x3 | delegates to `_v2.chat()` | SESSION (interface preserved) |
| 6 | `providers.py` | `OllamaProvider._post` `/api/chat` | delegates to `_v2.chat()` | SESSION (interface preserved) |
| 7 | `genesis_runtime.py` | raw `/api/generate` ping | `_v2.infer()` | **EPHEMERAL** (probe) |
| 8 | `worker_main.py` | raw `/api/generate` | `_v2.infer()` | **EPHEMERAL** (bounded worker) |
| 9 | `model_lifecycle.py` | `_ollama_generate` raw | `_v2.infer()` | **EPHEMERAL** (probe) |

Plus the four acceptance scripts, each now routing through the canonical
provider (EPHEMERAL for non-streaming probes; true streaming via
`infer_stream()` for the two realtime/resource tests that measure TTFT):

- `scripts/run_compat_acceptance.py` → `_v2.infer()` EPHEMERAL
- `scripts/run_default_agent_autonomy.py` → `_v2.infer()` EPHEMERAL
- `scripts/run_realtime_acceptance.py` → `_v2.infer_stream()` (TTFT preserved)
- `scripts/run_real_resource_acceptance.py` → `_v2.infer_stream()` (TTFT preserved)

### Why the two new V2 methods exist

`chat()` completes V2's coverage of the `/api/chat` (messages) endpoint that
the legacy adapters used — same lease/keep_alive discipline and error taxonomy
as `infer()`, differing only in payload/response shape. `infer_stream()` is
the canonical home for true token streaming: it holds a lease, yields
`(chunk, meta)` tuples, and reports TTFT/wall/tokens-per-sec. The realtime and
resource acceptance tests measure time-to-first-token, so streaming was
**preserved, not degraded to a non-streaming call** (§15).

### Interface preservation

The two legacy adapter *classes* (`providers.OllamaProvider`,
`models.providers.OllamaProvider`) keep their exact public contract —
`chat()->str` raising `ProviderError`; `generate()/tool_call()/stream()`
returning `{ok, content, ...}`. Internally they delegate to `_v2`. Their ~10
consumers (bridge.py, runtime.py, worker_adapters.py, tools/cat_*, the
benchmark runner) required **no rewrite**. V2's normalized errors are
translated back to `ProviderError` at the boundary so no caller sees a new
exception type.

## Duplicate HTTP clients — retired

Before: three independent Ollama HTTP clients (`ollama_provider_v2._get`,
`models/providers/ollama_provider._ollama_request`, `providers._post/_get`)
plus raw `urllib` in `genesis_runtime.py`, `worker_main.py`, `model_lifecycle.py`
and the four scripts.

After: **one** canonical transport (`OllamaProviderV2._get`) for every
weight-loading call. `models/providers/ollama_provider._ollama_request`
survives only as a **read-only discovery** client (`/api/tags`, `/api/show`,
`/api/version`) and now **raises** if asked for `/api/generate`, `/api/chat`
or `/api/embeddings` — the boundary is enforced in code, not by convention.

## Static bypass guard

`tests/test_ollama_bypass_guard.py` scans tracked production source for direct
construction of Ollama load-triggering URLs and fails on any new one not on an
explicit allowlist. It ignores comments, release calls (`keep_alive=0`), display
labels, and tests (a unit test may legitimately exercise the raw boundary). This
is what stops the architecture drifting back: a tenth bypass now fails CI.

## Lease policy (§6)

| Policy | keep_alive | Used for |
|--------|-----------|----------|
| EPHEMERAL | 0 | tests, bounded measurements, probes, benchmarks, acceptance |
| SHORT_LIVED | 300 s | repeatedly reused lightweight model |
| SESSION | -1 (retain) | interactive Genesis session — **default** |
| PERSISTENT | -1, never auto-released | owner-pinned hot model |

Default is SESSION, unchanged. Migrated probe/worker/acceptance paths request
EPHEMERAL **explicitly** — the product default was not weakened to make tests
easier.

## Ownership classes (§4, §5)

| Class | Meaning | Releasable |
|-------|---------|-----------|
| AETHERIUS_LOADED | loaded because our lease asked | YES, at refcount 0 |
| PREEXISTING | resident before our baseline — includes Hermes' own llama-server | **NEVER** |
| SHARED | another live lease holds these weights | NO, until last release |
| UNKNOWN | resident, unattributable | NO — fails safe (§5) |

`capture_baseline()` is taken once, before any leased inference. That single
boundary is what keeps Hermes' own llama-server (PID 2072) alive.

## Verification

    tests/test_model_lifecycle_leases.py    29 passed  (§9 A–J)
    tests/test_ollama_bypass_guard.py        3 passed  (static guard)
    tests/test_compute_runtime_audit.py     21 passed

## Honest limitations

1. **No live team run has executed through the new `chat()`/`infer_stream()`.**
   All migrated paths are covered by the deterministic lease tests and the
   static guard, but a real A→B→C inference chain through `chat()` and a real
   streaming TTFT measurement through `infer_stream()` remain to be exercised
   live. The full-suite run exercises `infer()`/`embed()` live.
2. **`infer_stream()` error normalization is narrower than `_get()`'s.** It
   normalizes `URLError`/`TimeoutError` but lets a mid-stream JSON parse issue
   surface as a `ValueError` rather than a taxonomy class. Acceptable because
   the lease is still released on any exception, but not yet as complete as the
   non-streaming path.
3. **Streaming does not carry capability gating** the way `infer()`/`chat()` do
   (temperature check only). Tool-calling is not exposed on the streaming path
   because no current streaming caller needs it.

## Next dependency-ready task

Run a live streaming TTFT measurement through `infer_stream()` (one bounded
call against a resident model) to close limitation 1, then continue the
compute-runtime fork audit (llama.cpp / ollama / vllm / ggml per §28–§32).
