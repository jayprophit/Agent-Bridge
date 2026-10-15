# GENESIS → AGENT-BRIDGE INTEGRATION RECON (Task 3)

**Recon ID:** AETH-R3-2026-10-15-001
**Operator:** OpenCode · **Date:** 2026-10-15
**Scope:** Minimum changes to give Genesis direct access to the existing Agent
Bridge skill registry, worker runtime and policy authority — without a new
orchestration framework, and without Genesis spawning another agent.
**Status:** RECON COMPLETE · IMPLEMENTATION NOT STARTED (two owner decisions below)

Evidence vocabulary: PROPOSED / FOUND / IMPLEMENTED / TESTED / NOT_FOUND / BLOCKED

---

## 1. HEADLINE — TWO PREMISES IN THE BRIEF NEED CORRECTING

**The transport is not missing.** A working, stdlib-only Genesis↔Agent-Bridge
HTTP transport exists and was built *for* Genesis. It is archived on the Genesis
side and absent from the C++ build. Integration cost on the transport side is
near zero.

**The skill registry is not "already-working."** `supply_chain_security.py:178`
is a *tested skeleton*: no persistence, no invocation method, no HTTP route,
and **zero production callers**. Verified directly — `SkillRegistry` is
referenced only by its own test.

So the honest scope is: the **policy/action path is real and can be reused
now**; the **skill registry needs building**, not merely wiring.

---

## 2. THE TRANSPORT EXISTS

| Half | Location | Evidence |
|---|---|---|
| Client SDK | `Agent-Bridge/client.py:20` — `base: str = "http://127.0.0.1:8471"` | FOUND |
| Server | `Agent-Bridge/service.py:796` `serve()`, loopback-only enforced | FOUND |
| Genesis-side client | `Genesis/integration-archive/` — 191 files | FOUND |
| Import seam | `integration-archive/genesis_runtime/v05client.py:13-26`, env-var only, no hardcoded paths | FOUND |

Agent-Bridge was authored as Genesis's runtime, not adapted to it later:

> `Agent-Bridge/runtime.py:1` — "GENESIS LOCAL AGENT RUNTIME — public Python API"
> `Agent-Bridge/client.py:1` — "The interface Genesis may use later."

Genesis C++ cannot use any of this today: `CMakeLists.txt` links no HTTP library
and no Python, and grep for `spawn|CreateProcess|fork(|exec(|popen` returns
**NOT_FOUND**. Genesis's own audit says so:

> `Genesis/docs/SEAM-AUDIT-2026-09-30.md:39` — "Bridge / P25 integration | ABSENT
> here | no HTTP client, no policy evaluation, no authority call."

---

## 3. THE MINIMUM VIABLE INTEGRATION

### RECOMMENDED: a thin Genesis-side adapter → `POST /v1/actions`

**~50-100 LOC, entirely in Genesis. Zero new Agent-Bridge code. No framework.**

Genesis already models the seam correctly — `ActionProposal`
(`include/genesis/agents/action_proposal.hpp:45-74`) maps almost 1:1 onto the
route schema (`service.py:759-766`):

| `ActionProposal` | `/v1/actions` |
|---|---|
| `proposal_id` | `action_id` |
| `action` / `resource` | `action` / `resource` |
| `genesis_id` | `principal: {"kind":"genesis","id":…}` — `"genesis"` is already a valid `PRINCIPAL_KINDS` (`aether_policy_bridge.py:516`) |
| `tool_id`, `capability_id`, `rationale`, digests | nested under `payload` |

**Reuses, all existing and tested:** HTTP transport, session/approval
lifecycle, `evaluate_capability_request` + default-deny `PolicyEngine`,
executor, journal, `/v1/actions/{id}` status polling.

Genesis's own audit already recommends this exact increment:
> `SEAM-AUDIT-2026-09-30.md:78-79` — "an evidence-bearing action-request record
> and proposal emitter … producing a request rather than performing anything."

And the C++ side already has a CMake target proving the proposal half never
authorizes: `CMakeLists.txt:132-137` — *"Genesis proposes; P25 authorizes;
Agent Bridge executes."*

### Rejected alternatives

| Option | Why not |
|---|---|
| New `GET /v1/skills` route | `SkillRegistry` has no persistence and no invocation — the route would expose an empty dict. Also: `PolicyEngine` is an **in-process singleton** (`get_policy_engine()` L356), so a Genesis-side direct call would hit a *different, empty* engine and default-deny everything. This argues **for** HTTP, not for a new route. |
| FFI / embedded Python | Genesis CMake links neither. New build infrastructure = a framework. Out of scope. |
| Shared-process | Impossible — zero spawn primitives in Genesis C++. |

---

## 4. TRUST BOUNDARY — ALREADY CORRECT ON BOTH SIDES

This is the part that most often goes wrong, and it is already right:

- Genesis's `ActionProposal` deliberately has **no** `authorized` field
  (`action_proposal.hpp:22-27, 40-43`) — `PROPOSAL != AUTHORIZATION` is encoded.
- Agent-Bridge's client docstring (`client.py:104-106`): *"this call only carries
  the decided action to them. **Never authorizes anything.**"*
- `PrincipalContext` (`aether_policy_bridge.py:519-533`): *"A principal is NEVER
  authority: it grants no capability, approves nothing, and cannot widen a grant."*
- `validate_principal` L568-571 blocks worker-impersonates-Genesis and
  collapses owner/Genesis.

**Status: NOT blocked — by design.**

---

## 5. BLOCKERS — TWO ARE OWNER-GATED

| # | Blocker | Status |
|---|---|---|
| 1 | Genesis **C++ core** has no transport and cannot call Agent-Bridge. | **BLOCKED — owner.** If the C++ core must be the caller, this is new build infrastructure. |
| 2 | Is Genesis's **Python application layer** a sanctioned entry point? Precedent exists (`integration-archive`; Agent-Bridge is literally "GENESIS LOCAL AGENT RUNTIME") but it was deliberately quarantined: *"This is NOT the real Genesis application."* | **BLOCKED — owner.** Lowest friction: a **new** Genesis-side module rather than un-archiving. |
| 3 | Language boundary C++↔Python. | Just work *if* blocker 1 resolves via the Python layer. |
| 4 | Skill registry is a skeleton (§1). | Work — scope explicitly. |
| 5 | `aether_policy_bridge.py` has **7 duplicate class definitions** (`EvalContext` ×4, `PermissionId` ×2, `Subject` ×2, `Grant` ×2, `Decision` ×3, `RoleId` ×3, `Role` ×2). Last-definition-wins. The surviving `EvalContext` (L287) hardcodes `network_origin=None` / `device_trust=None`, silently discarding args passed by `executor.py:323-324`. | Work — latent-bug risk, not a blocker. |

---

## 6. PRIOR ATTEMPTS EXIST AND STOPPED AT THE SAME SEAM

| Side | Artifact |
|---|---|
| Agent-Bridge | Six Genesis modules: `genesis_bridge.py`, `genesis_runtime.py` (`LocalGenesisRuntime` — **the only concrete impl, wired live** via `service.py:828-829`), `genesis_cognition.py`, `genesis_avatar.py`, `genesis_ledger_bridge.py`, `genesis_client_simulator*.py` |
| Genesis | `action_proposal.hpp` + emitter + CMake tests; `integration-archive/` (191 files); the honest `SEAM-AUDIT` |

Both attempts stopped at the same seam — not for lack of code, but because
(i) the C++ core has no transport and (ii) no Genesis↔Agent-Bridge entry point
has been sanctioned.

---

## 7. RECOMMENDED NEXT STEP

**Ask the owner two questions, then build one module:**

1. May Genesis's Python application layer call Agent-Bridge's loopback API?
2. May `integration-archive` be revived, or should a fresh Genesis-side module
   be written?

If yes → implement the adapter (≈1 module, Genesis-side, ~50-100 LOC) mapping
`ActionProposal` → `POST /v1/actions`, then demonstrate Genesis solo-executing
a task with no worker spawned (closes **AT-01** / gap **D01**).

**Do not** start by building the skill registry. Ship the real policy/action
path first; the registry is a separate, larger piece of work.

---

## 8. INTEGRITY

Read-only reconnaissance. No file created, modified or deleted outside this
document. No git state mutated. No credentials read. No external calls.