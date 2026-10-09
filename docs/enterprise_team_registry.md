# Enterprise Multi-Agent Team Registry

Status: **IMPLEMENTED** (canonical + append-only provenance)
Directive: `Documents/multi agent setup.txt` §AK, §F, §N, §O, §P, §M, §AJ
Implementation: `compute/team_registry.py`
Tests: `tests/test_team_registry.py` — **31 passed**

## Why two layers

The organisational history used to be in-memory only. A session ended and
everything the enterprise fabric did — team formation, handoffs, promotions —
was gone. This module makes it durable in two deliberately separate layers:

| Layer | Mutable | Answers | Owns |
|---|---|---|---|
| **Canonical** (in-memory) | yes | "who is on team X *now*" | current state |
| **Provenance** (append-only JSONL) | **never** | "who reviewed task Y three weeks ago" | permanent trail |

A registry that only appends cannot answer the first question. A registry that
only mutates cannot answer the second. Both are real, so both exist.

**If the two ever disagree, provenance wins** — it is the one that cannot be
edited after the fact. `rebuild_from_provenance()` replays the trail to
reconstruct canonical state, which is what makes the split safe: the fast path
is always recoverable from the permanent record.

## §AK gate status — after this unit

| §AK clause | Before | After | Evidence |
|---|---|---|---|
| Team registry / canonical equivalent | PARTIAL | **PASS** | `TeamRegistry`, persisted + rebuildable |
| Min 2-worker team executes | PASS | PASS | pre-existing, 85 tests |
| 3–5 distinct roles demonstrated | PASS | PASS | 9 roles in `SPECIALIST_ROLES` |
| Every worker has explicit role | PASS | PASS | `WorkerCareerRecord.role_id` mandatory |
| Every task has accountable owner | PARTIAL | **PASS** | `set_task_owner()`, single owner enforced |
| Worker-to-worker handoff works | PASS | PASS | `register_handoff()` validates both ends |
| 3-role A→B→C chain proven | PASS | **PASS** | `handoff_chain()` ordered by timestamp |
| Collaboration without shared write state | PARTIAL | PARTIAL | declared in fabric; **still not proven by test** |
| Team survives optional-worker failure | PASS | **PASS** | `test_team_survives_demotion_of_an_optional_worker` |
| Team size vs active concurrency separate | PASS | **PASS** | `test_twelve_logical_workers_at_concurrency_three` |
| Architecture supports 10+ logical workers | PARTIAL | **PASS** | 12 logical @ concurrency 3, proven |
| Resource scheduler prevents unsafe concurrency | PARTIAL | PARTIAL | `concurrency_limit` gate; **not RAM-aware** |
| Team/department hierarchy representable | MISSING | **PASS** | `DEPARTMENTS`, `department_for_role()` |
| RACI-equivalent representable | MISSING | **PASS** | `RaciAssignment`, one ACCOUNTABLE enforced |
| Role selection is dynamic | PASS | PASS | `form_team()` by required roles |
| Agent/model/provider separate identities | PASS | **PASS** | `swap_worker_model()` keeps worker + role |
| Enterprise workflow documented | PARTIAL | **PASS** | this document |
| Hybrid Cloud 10+ elastic scaling | BLOCKED | **BLOCKED** | cloud creds `MISSING_ROTATION` (owner) |

**12 PASS / 2 PARTIAL / 1 BLOCKED.** Not a clean pass — see Honest Limitations.

## The 10+ worker proof (§AK)

§AK is explicit that the gate must **not** fail because a 16 GB workstation
cannot run ten large models at once. It *does* require that 10+ logical
workers be supported with active concurrency separately represented.

`test_twelve_logical_workers_at_concurrency_three` proves both numbers
survive as distinct facts rather than collapsing into one:

```
team_size             = 12   # logical specialists (§U)
active_concurrency    = 3    # what this host may actually run (§U)
```

`scale_team()` changes the logical size **without touching membership** —
scaling the team is an organisational decision, membership is a factual one.
A team can be declared 12 strong while 3 run at a time.

## Departments (§F)

Organisational metadata only — a grouping of roles, not a program, not a
second orchestration system.

| Department | Roles |
|---|---|
| ENGINEERING | coding_worker, reviewer, handoff_arbiter, routing_specialist |
| RESEARCH | research_worker, evidence_reviewer |
| QUALITY | test_runner, cost_specialist |
| OPERATIONS | coordinator |

An unknown role returns `None` rather than being filed somewhere plausible.
An unrecognised role must be surfaced, not guessed at.

## RACI and task ownership (§O, §P)

Every important task records who does the work and who accepts the outcome.

- **Exactly one** worker is ACCOUNTABLE — enforced in code, not by convention.
- Zero accountable owners is the bug §O exists to prevent.
- More than one is the other half: shared accountability is no accountability.
- Recording RACI sets task ownership to the ACCOUNTABLE worker, so the two
  can never disagree.

Re-assignment is allowed and recorded: ownership can move, but it is always
singular and always traceable. That is what prevents "everyone thought
someone else was doing it".

## Worker identity vs replaceable substrate (§M)

```
worker_id  →  persists forever
role_id    →  persists across model swaps
department →  derived from role
model_id   →  REPLACEABLE
provider_id→  REPLACEABLE
```

`swap_worker_model()` changes the model and provider while leaving worker_id,
role, department, specialisms, career state and evidence untouched. Both are
recorded so the distinction is *visible* rather than assumed.

## Evidence-based career (§AI, §AJ)

Promotion requires evidence and records what justified it:

```
success_rate = None   when untested   ← deliberately NOT 0.0
```

"Never tried" and "always fails" are different facts. An untested worker
ranks **last**, not first — ranking by inaction would reward doing nothing.

Demotion needs no ceremony: a failing worker must be pullable back
immediately, and demanding justification for a safety action discourages
taking it.

## Handoff contract (§H, §I)

A registered handoff validates that:

1. both ends are registered workers,
2. the receiving worker's actual role matches the declared `to_role`,
3. the sender's role matches `from_role`.

Rule 2 is the important one: a handoff to a role nobody holds is silently
dropped work — the exact failure §I exists to catch.

`handoff_chain(task_id)` returns the A→B→C sequence ordered by timestamp,
because a chain is a sequence and the receiver needs to know what came
before, not merely who was involved.

## Provenance rules

- Every canonical mutation appends **exactly one** event.
- Events are never edited or removed (§52: the trail outlives the thing it
  describes).
- Append happens **after** the canonical mutation is computed but **before**
  it is committed to the in-memory dict — so an unwritable trail raises
  `ProvenanceError` rather than leaving canonical state claiming a change
  with no permanent record.
- A schema-version mismatch raises rather than silently mis-parsing (§5).

## Honest limitations

1. **Collaboration without shared write state is still unproven.** Workspace
   isolation is declared in `team_execution_fabric.py` but no test
   demonstrates two workers writing without colliding. This is a real gap.
2. **The concurrency gate is not RAM-aware.** `concurrency_limit` caps worker
   count; it does not measure available RAM or VRAM. On this 16 GB host a
   3-worker cap is conservative by convention, not by measurement. §V asks
   for resource declaration per worker — not yet implemented.
3. **No live team run has executed through the registry.** All 31 tests are
   deterministic and in-process. A real A→B→C chain through live models
   remains to be demonstrated, and is partly blocked on credential rotation.
4. **Hybrid Cloud elastic scaling stays BLOCKED** — 5 credential refs are
   `MISSING_ROTATION` pending owner action.

## Next dependency-ready task

Close limitation 1: prove workspace isolation with a test where two workers
write concurrently and neither clobbers the other. That converts the last
PARTIAL that is not hardware- or credential-blocked.
