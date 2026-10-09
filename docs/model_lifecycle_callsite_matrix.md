# Model Lifecycle Callsite Matrix

Generated: 2026-10-09 (live repository scan)
Directive: PROVIDER-LEVEL MODEL LIFECYCLE FIX (§2)

## Why this document exists

The residency leak was fixed once at `compute/local_team_executor.py` and
then reappeared through other Ollama call sites. The cause was structural:
residency is a property of the *runtime*, but the ownership decision was
being made by individual *callers*. Every new call site reintroduced the
leak, and no caller could know whether another live worker still needed the
same weights.

The fix moves ownership to the provider boundary
(`compute/ollama_provider_v2.py`). This matrix is the before-state: the
evidence that the leak was architectural, not incidental.

## Method

Scanned the repository for every path capable of making a model resident:

    api/(generate|chat|embed|embeddings|show|ps)
    keep_alive
    ollama run | ollama serve
    provider.infer | provider.embed | provider._get
    direct HTTP Ollama calls

40 matches across 16 files. The 8 paths below are those that actually
trigger a model load.

A later, wider scan found **four acceptance scripts** that also load models
directly — `scripts/run_compat_acceptance.py`, `scripts/run_default_agent_autonomy.py`,
`scripts/run_realtime_acceptance.py` and `scripts/run_real_resource_acceptance.py`
(each `POST /api/generate`). The original count of 5 remaining legacy adapters
was therefore an undercount: the true figure is **9 unleased load paths**, and
all 9 are live import paths, not dead code.

## Callsites

| # | File | Function / line | Loads model | Owned lifecycle | Released before | Released after |
|---|------|-----------------|-------------|-----------------|-----------------|----------------|
| 1 | `compute/ollama_provider_v2.py` | `infer()` `/api/generate` | YES | **now owns** | NO | YES — lease |
| 2 | `compute/ollama_provider_v2.py` | `embed()` `/api/embeddings` | YES | **now owns** | NO | YES — lease |
| 3 | `models/providers/ollama_provider.py` | `_ollama_request` `/api/chat` x3 | YES | no | NO | UNCHANGED |
| 4 | `providers.py` | `OllamaProvider._post` `/api/chat` | YES | no | NO | UNCHANGED |
| 5 | `genesis_runtime.py` | `/api/generate` | YES | no | NO | UNCHANGED |
| 6 | `worker_main.py` | `/api/generate` | YES | no | NO | UNCHANGED |
| 7 | `model_lifecycle.py` | `ModelCapabilityProfiler._ollama_generate` | YES | no | NO | UNCHANGED |
| 8 | `compute/local_team_executor.py` | `run_worker` + `release_models()` | YES | caller | YES (manual) | DELEGATED to provider |

## Interpretation

**Callsites 1 and 2 are the canonical adapter.** Everything that should route
through a single provider interface does. These now lease (§3) and release on
both success and failure paths (§9-H).

**Callsites 3–7 are separate legacy adapters** that predate Provider V2 and
each speak to Ollama directly. They are *not* covered by this change and
remain open leakage paths. They are recorded honestly rather than silently
ignored: they are separate adapters, not duplicates of Provider V2's job, and
retiring them is a distinct migration task requiring each caller's usage to
be traced. Consolidating them onto Provider V2 is the follow-up.

**Callsite 8 is the delegation.** `release_models()` no longer issues
`keep_alive=0` itself — that would unload weights another live worker might
hold (§4). It calls `provider.release_all()`, which knows the refcount and
the ownership class.

## Honest limitation

`genesis_runtime.py`, `worker_main.py`, `providers.py`,
`models/providers/ollama_provider.py`, `model_lifecycle.py` and the four
acceptance scripts still load models without a lease. This change closes the
canonical path and adds a failing test if anything regresses on it; it does
not claim those nine legacy paths are now safe.

**A structural note, not just a lifecycle one:** the repository contains
**three independent Ollama HTTP clients** — `compute/ollama_provider_v2.py`
(leases, taxonomy, tracing), `models/providers/ollama_provider.py`
(`_ollama_request`, `/api/chat` x3) and `providers.py`
(`_post`, `/api/chat`) — plus raw `urllib` calls in `genesis_runtime.py`,
`worker_main.py`, `model_lifecycle.py` and the four scripts. That is §57's
"do not create a duplicate model router" showing up in the transport layer:
each client has its own timeout, error handling and (absent) lifecycle. The
next unit should consolidate them onto Provider V2 rather than bolt leases
onto each one.

## Lease policy (§6)

| Policy | keep_alive | Used for |
|--------|-----------|----------|
| EPHEMERAL | 0 | tests, bounded measurements, benchmarks |
| SHORT_LIVED | 300 s | repeatedly reused lightweight model |
| SESSION | -1 (retain) | interactive Genesis session — **default** |
| PERSISTENT | -1, never auto-released | owner-pinned hot model |

Default is SESSION, not EPHEMERAL: production inference wants the weights
warm for the next turn, and only the caller knows whether that is wanted.

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

    tests/test_model_lifecycle_leases.py
      29 passed  (27 deterministic fake-transport + 2 bounded live)

Covering §9 A–J: ephemeral release, intentional retention, shared-model
safety, final-lease release, pre-existing protection, failure/timeout/
exception paths, no bypass, hygiene.

## Post-fix full-suite baseline

    verify venv (Python 3.13.14), no source edits during the run
    2037 passed, 1 skipped, 49 subtests, 0 failed in 3497.31s (58:17)

This is the trustworthy baseline. An earlier full-suite run reported 4
failures that were `inspect.getsource()` structural checks racing commits
landing 23 minutes into a 70-minute run; all 4 passed in 6.29 s in isolation.
The green run above had no concurrent edits.

Its residency evidence found one more leak this document had not accounted
for: `RealLocalTeamTests` in `tests/test_local_team_execution.py` loaded
weights in `setUpClass` and had no `tearDownClass`, so the class-level run
left `qwen3:1.7b` resident. Fixed at the fixture boundary, matching the
`test_conversation_and_ollama_v2.py` fix.
