# Aetherius Fork + Predecessor Reconciliation — Live Evidence

**Status:** LIVE ESTATE RECONCILED · **ZERO DELETIONS AUTHORISED**
**HEAD:** `2e737ab` (pushed, remote SHA verified)

Executes §51 FIRST ACTION using live GitHub evidence instead of trusting the
October inventory.

---

## 1. Live estate (§3)

| | Count |
|---|---|
| **Total repositories** | **396** (inventory claimed 394) |
| Original | 44 |
| Fork | 352 |
| — with resolved upstream | **352** |
| — without upstream | **0** |
| Public / private | 396 / 0 |
| Archived | 4 (`Arduino`, `cs50-Python`, `devops-directive-docker-course`, `hello-world-1`) |

### ⚠ The bug that would have ruined this audit

**The REST list endpoint omits the `parent` field entirely.** A bulk fetch
reports all 352 forks as having no upstream. Individual `repos/<owner>/<repo>`
calls *do* return it.

Without per-repo resolution, the entire estate would have been classified
wrong — 352 "orphans" with no upstream, no capability mapping, and no basis
for any migration decision. `scripts/resolve_upstreams.py` resolves parents
concurrently and writes them back into `live_estate.json`.

## 2. Reconciliation (§51 steps 4–8)

| | |
|---|---|
| Catalog rows | 350 |
| **Matched live** | **350** — zero phantom entries |
| Catalog rows not live | 0 |
| Live repos not in catalog | **46 — all originals** |

Those 46 include **every named predecessor**: `aetherium`, `Aetherial`,
`aetherial-platform`, `Niche_platform`, `Quantum-OS`,
`Crossplatform---multiplatform`, `QVA-merged`, `Veyra`, `VirtualAssistant`.

This confirms the October inventory supersedes the earlier "404/missing" audit.

The 10 catalog rows marked `VERIFY_UPSTREAM` are all confirmed real forks:

| Fork | Upstream |
|---|---|
| `servers` | modelcontextprotocol/servers |
| `fastapi` | fastapi/fastapi |
| `compose` | docker/compose |
| `sofa` | sofa-framework/sofa |
| `link` | Ableton/link |
| `alp-data` | earthspecies/alp-data |
| `genesis-world` | Genesis-Embodied-AI/genesis-world |
| `core` | home-assistant/core |
| `avex` | earthspecies/avex |
| `hello-world-1` | G1ne/hello-world |

## 3. Predecessor matrix (§9, §42)

9 predecessors, **all confirmed live**:

| Repo | License | Last push | Destination | Caution |
|---|---|---|---|---|
| `aetherium` | MIT | 2026-02-20 | Aetherius OS | — |
| `Aetherial` | GPL-3.0 | 2026-09-11 | Aetherius OS | — |
| `aetherial-platform` | *none* | 2026-03-27 | Aetherius OS + platform services | license unknown |
| `Niche_platform` | *none* | 2026-09-19 | Aetherius OS / First-Party Apps | license unknown |
| `Quantum-OS` | MIT | 2025-11-07 | Aetherius OS + VM-B | real-vs-simulated |
| `Crossplatform---multiplatform` | CC0-1.0 | 2024-12-19 | Aetherius OS SDK | — |
| `QVA-merged` | *none* | 2025-05-13 | **SPLIT** OS / Bridge / Genesis | **must decompose (§12)** |
| `Veyra` | MIT | 2026-05-23 | OS / Bridge / Hybrid Compute | **finance ≠ kernel (§11)** |
| `VirtualAssistant` | MIT | 2025-01-13 | Genesis Master Implementation | **one Genesis identity** |

**`migration_state = NOT_STARTED` for all nine.** This matrix records *what to
mine and where it goes*; capability extraction (§10) requires actual source
inspection and is downstream work. Nothing is marked `safe_to_delete`.

## 4. Unique-commit audit (§5) — 384 audited, 0 errors

**349 CLEAN · 3 HOLD OWNER WORK**

| Repo | Ahead | Class | Why it matters |
|---|---:|---|---|
| **`IsaacLab`** | **+154** | UNKNOWN | upstream `isaac-sim/IsaacLab`; substantial divergence |
| **`neo4j`** | +7 | UNKNOWN | includes real Java source: `PackstreamValueWriter.java` |
| **`devops-directive-docker-course`** | +2 | EXPERIMENTAL | Dockerfiles + Makefile changes |

**These three must not be deleted.**

The classifier deliberately escalates *any* code divergence to `UNKNOWN`
rather than judging load-bearing-ness from a filename list. A `pom.xml` diff
looks inert; the `neo4j` fork pairs `pom.xml` changes with an actual Java
source edit. Only a human inspecting the diff can decide.

## 5. §34 safe-delete gate

**15 conditions, all mandatory** — strictly stronger than the 10-step gate
implemented earlier:

```
1  live identity verified        6  each capability decided      11  replacement pushed
2  upstream identified           7  implementation complete      12  remote SHA verified
3  license recorded              8  tests passed                 13  no unresolved dependencies
4  unique commits checked        9  provenance registered        14  documentation updated
5  capabilities mapped          10  replacement committed        15  archive created if needed
```

**0 of 396 repositories pass.** The delete queue is **EMPTY BY DESIGN** and is
reported as empty rather than filled speculatively.

Note §34 condition 12: a *local* commit is not remote preservation. Replacement
work existing only locally does not qualify (§36).

## 6. License provenance (§6)

| License | Repos |
|---|---:|
| `NOASSERTION` | 97 |
| `Apache-2.0` | 87 |
| `MIT` | 70 |
| `UNKNOWN` / `None` | 50 |

**147 repositories have no identified license** and require manual
identification before any code use. 21 GPL-3.0, 21 BSD-3-Clause, 9 GPL-2.0,
9 LGPL-2.1, 6 AGPL-3.0 carry notice obligations.

## 7. §40 reporting artefacts

All ten in `migration/reports/`:

| | Artefact |
|---|---|
| A | `A_fork_master_inventory.json` |
| B | `B_predecessor_migration_matrix.json` |
| C | `C_fork_use_case_matrix.json` |
| D | `D_license_provenance_matrix.json` |
| E | `E_unique_commit_report.json` |
| F | `F_migration_todo_graph.json` |
| G | `G_active_dependency_register.json` |
| H | `H_safe_to_delete_queue.json` |
| I | `I_retained_fork_register.json` |
| J | `J_migration_history.json` |

**347 dependency-ready migration tasks** generated, ordered by §29 priority.
`G` is empty because nothing has been migrated yet — reported empty rather
than populated speculatively.

## 8. Verification

| Check | Result |
|---|---|
| New tests | **26/26** |
| Migration suite total | **81 passing** |
| Hygiene | **7/7** |
| Deletions | **0** |
| HEAD | `2e737ab`, pushed, remote verified, 0 behind / 0 ahead |

## 9. Next action (§47 — automatic continuation)

Per §29 the highest-priority work is **P0: current Hybrid Cloud dependencies**.
That means auditing the `AETHERIUS_COMPUTE_AI_RUNTIME` forks — `llama.cpp`,
`ollama`, `vllm`, `ggml` — against the execution-target abstraction, which
converts directly into unblocked Hybrid Cloud P0 work.

Before that, three items warrant owner attention:

1. **`IsaacLab` (+154 commits)** — the largest owner-authored divergence in the
   estate. Worth inspecting before anything else.
2. **147 unlicensed repos** — including 3 of 9 predecessors.
3. **`Aetherial` is GPL-3.0** — a copyleft predecessor feeding Aetherius OS.
   License compatibility needs a decision before any code is ported.
