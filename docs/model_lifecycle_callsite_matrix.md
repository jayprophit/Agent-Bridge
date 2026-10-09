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
`models/providers/ollama_provider.py` and `model_lifecycle.py` still load
models without a lease. This change closes the canonical path and adds a
failing test if anything regresses on it; it does not claim those five legacy
adapters are now safe.

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
      24 passed  (22 deterministic fake-transport + 2 bounded live)

Covering §9 A–J: ephemeral release, intentional retention, shared-model
safety, final-lease release, pre-existing protection, failure/timeout/
exception paths, no bypass, hygiene.
