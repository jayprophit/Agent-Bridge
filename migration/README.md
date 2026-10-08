# Aetherius Fork + Predecessor Migration Programme

**Status:** ACTIVE — live audit in progress, **zero deletions authorised**

**Basis:** `Aetherius_GitHub_Repository_Inventory_2026-10-02.csv` — 394 repos
(44 ORIGINAL + 350 FORK_CANDIDATE, all marked `NOT_CHECKED`).

---

## The rule this programme exists to enforce

> **Deleting the personal fork must never delete the provenance trail.**

Aetherius keeps the upstream URL / SHA / license and the destination
implementation + test evidence **permanently**. If a fork is still an active
dependency or holds unique unported changes, it is **not** safe to delete.

The provenance record is the permanent artefact. The fork is disposable.

## Ownership corrections (owner-verified)

| Source | Classification |
|---|---|
| **Veyra / VRA** | Aetherius OS predecessor / failed attempt — not a canonical project |
| **First-Party Application Ecosystem** | **Active Aetherius programme** — not a predecessor |
| **Avatar / Digital Twin** | Genesis predecessor/input — not an Aetherius OS subsystem |
| **Forks generally** | Engineering source pool feeding canonical owners, not products |

## Predecessor chain

```
aetherium → Aetherial → aetherial-platform → Niche_platform
→ Quantum-OS → Crossplatform---multiplatform → QVA-merged
→ Veyra / VRA
        │  mine / reconcile / test
        ▼
   AETHERIUS OS
```

The October 2026 inventory **supersedes** the earlier "404/missing" audit:
`aetherium`, `Aetherial`, `Niche_platform`, `aetherial-platform`,
`QVA-merged`, `Crossplatform---multiplatform`, `Quantum-OS` and
`VirtualAssistant` are inventoried as real repositories. Their branch/content
state still requires live inspection.

**QVA-merged must be decomposed, not migrated wholesale** — it crosses the
Aetherius/Genesis boundary the owner has since corrected:

- OS/platform/runtime concepts → **Aetherius OS**
- model/tool access → **Agent Bridge / Hybrid Compute**
- assistant/avatar/identity → **Genesis**

## The 10-step mandatory gate

```
FORK / PREDECESSOR
   → 1  VERIFY UPSTREAM      (live: relationship, branch, SHA, license)
   → 2  IDENTIFY UNIQUE CAPABILITY (dedupe against canonical owners)
   → 3  MAP CANONICAL OWNER
   → 4  CHOOSE STRATEGY      (REFERENCE_ONLY / DEPENDENCY / ADAPTER /
                              PORT / CLEAN-ROOM / FIRST-PARTY)
   → 5  IMPLEMENT IN CANONICAL REPO
   → 6  ADD TESTS / BENCHMARKS
   → 7  COMMIT + PUSH
   → 8  VERIFY REMOTE SHA    (local commit != remote preservation)
   → 9  PRESERVE UNIQUE COMMITS (patchset or archival bundle)
   → 10 PRODUCE MIGRATION MANIFEST
   → SAFE_TO_DELETE
   → DELETE PERSONAL FORK
```

Gates are **strictly ordered and cannot be skipped** — enforced in code, not
by convention.

### Terminal dispositions

| Disposition | Fork may be deleted |
|---|---|
| `MIGRATED` | yes, after full gate |
| `REJECTED` | yes |
| `SUPERSEDED` | yes |
| `NOT_APPLICABLE` | yes |
| `KEEP_AS_UPSTREAM_DEPENDENCY` | **no — HOLD** |
| `BLOCKED_LICENSE` | **no — HOLD** |
| `BLOCKED_TECHNICAL` | **no — HOLD** |
| `PENDING_AUDIT` | **no — HOLD** |

## Code

| File | Role |
|---|---|
| `migration/provenance.py` | ProvenanceRecord, gate machinery, deletion authority, catalog ingestion |
| `migration/auditor.py` | Live read-only `gh` audit (gate 1) |
| `migration/manifest.py` | Migration manifest (§10 step 8) |
| `scripts/run_fork_audit.py` | Bounded read-only audit runner |
| `scripts/check_unique_commits.py` | Fork-vs-upstream diff (gate 9 precheck) |
| `tests/test_migration_provenance.py` | 55 tests incl. adversarial deletion attempts |

## Deletion authority — all of these must hold

1. Every gate passed, including `SAFE_TO_DELETE`
2. Disposition is one of the four deletable states
3. Unique-commit status is **known** (never delete on unknown)
4. Unique commits have a preservation reference, if any exist
5. Destination commit **verified on the remote** — a local commit is not enough

## Audit progress

**Batch 1 — the 10 `VERIFY_UPSTREAM` rows (LOW confidence), live-verified:**

| Fork | Upstream | License | Unique commits |
|---|---|---|---|
| `jayprophit/servers` | modelcontextprotocol/servers | other | none |
| `jayprophit/fastapi` | fastapi/fastapi | MIT | none |
| `jayprophit/compose` | docker/compose | Apache-2.0 | none |
| `jayprophit/sofa` | sofa-framework/sofa | LGPL-2.1 | none |
| `jayprophit/link` | Ableton/link | other | none |
| `jayprophit/alp-data` | earthspecies/alp-data | MIT | none |
| `jayprophit/genesis-world` | Genesis-Embodied-AI/genesis-world | Apache-2.0 | none |
| `jayprophit/core` | home-assistant/core | Apache-2.0 | none |
| `jayprophit/avex` | earthspecies/avex | MIT | none |
| `jayprophit/hello-world-1` | G1ne/hello-world | none | none |

All 10 resolved to real upstreams with **zero unique commits** — the
`LOW` confidence was a naming problem, not a content problem.

**Remaining:** 340 of 350 fork candidates still `NOT_CHECKED`.

**Deletions authorised: 0.** Every record currently sits at
`GATE_1_UPSTREAM_VERIFIED` with disposition `PENDING_AUDIT`.

## Next actions

1. Continue bounded live audits (10–25 repos per run) to clear the estate
2. For each verified fork, assign canonical owner + strategy (gates 2–4)
3. Where a capability is genuinely needed, port it and remote-verify (5–8)
4. Preserve any unique commits before any deletion (9)
5. Regenerate the manifest and review the `SAFE_TO_DELETE` queue

Deletion is a **human-gated decision**, taken per repository, after the
manifest is reviewed. There is no bulk-delete path in this programme.
