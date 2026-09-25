# World-State Audit (REQ-p21-world-state-audit, P21)

Full post-operation world audit generalizing detexec read-back
verification. Owner: Agent-Bridge.

## Seed (`executor.py`, untouched)

`do_write` writes atomically, then independently re-reads and
compares — VERIFICATION_FAILED on mismatch. This module generalizes
that pattern: execute → independently read world → audit(expected,
observed). The auditor never mutates.

## Contract (`world_audit.py`)

Inputs: operation_id; expected effects (object_ref + expected with
exact/hash/subset comparison); unchanged invariants (object_ref +
pre-state or pre-hash); prohibited effects (created/deleted evaluated
by presence, changed needs pre-state or stays INCONCLUSIVE);
policy evidence (consumed, never decided — P25 remains authority);
observations keyed by object_ref (missing = NOT OBSERVED, never
unchanged); explicit scope; `require_policy=True` default (absent
policy evidence blocks VERIFIED; opt out only for policy-free
audits).

Checks: EXPECTED_EFFECT, UNCHANGED_INVARIANT, PROHIBITED_EFFECT,
POLICY_ASSERTION, READBACK_AVAILABILITY — each with expected,
observed, verdict, reason. Verdicts: VERIFIED (all pass + policy
satisfied), FAILED (any contradiction: wrong value, unexpected
change, prohibited effect, explicit denial), INCONCLUSIVE (missing
read-back, missing policy, insufficient scope). Partial observation
never verifies. Extra changed objects reported, never ignored.
Deterministic ordering; `to_dict(hash_values=True)` redaction for
sensitive values (hashes, never raw secrets).

`read_filesystem` adapter: independent content+hash reads, no
mutation. Correct value on wrong object is impossible by
construction (observations keyed by ref); value mismatch fails.

Boundaries: auditor != actuator; mutation response != read-back;
agent/tool claims never count as evidence; world-verified !=
clean-room proof (clean-room stays BLOCKED); no LLM judge, no
simulated world, no event bus, no evidence database. Audit reports
can feed EvidenceGate as evidence references (gate unchanged).

## Tests

`tests/test_world_audit.py` — 16 tests: all verdict paths,
prohibited variants, honesty cases (missing read-back/policy,
contradicted claims, partial scope, hash/subset modes, extra
changes, determinism), validation, redaction, filesystem reader
(non-mutating). Detexec suites (`test_deterministic_execution`,
`test_executor_v01/v02`) still green: 51/51 combined.
