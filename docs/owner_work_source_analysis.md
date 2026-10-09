# Owner-Work Source Analysis (§16–§18)

Generated: 2026-10-09 by `scripts/analyse_owner_work_source.py`
Report: `migration/reports/owner_work_source_analysis.json`

**Deletion remains DENY for all three HOLD forks.** Nothing here deletes,
ports or modifies anything. This is analysis input for the owner's decision.

---

## 1. Why the first analysis was wrong

The first run reported "13 substantive source changes" and then
"recommendation: ARCHIVE — no substantive source change" in the same output.
Two defects, both fixed:

1. `recommend()` re-derived its decision from a category filter instead of
   reading the `source_changes` list it was handed, so a non-empty list could
   still reach ARCHIVE. A pattern miss now yields `INSPECT_MANUALLY`.
2. `classify_patch()` matched keywords on added lines and labelled 613 of
   IsaacLab's ~800 changes `unclassified`, including a +1658/-341 test
   utility. Keyword luck reported the **most** substantial changes as the
   **least** certain — backwards for a keep/port/archive decision.

Classification now reads the **shape** of the diff: definition counts,
assertion density, import churn, add/remove balance, test-path detection.
`unclassified` is unreachable for any patch with added lines. Pinned by 20
tests in `tests/test_owner_work_classifier.py`, including a regression test
that substantive changes never recommend ARCHIVE.

---

## 2. neo4j — 7 commits, 189 files, 13 genuine `.java` files

### What the files actually contain

| Category | Files | ± |
|---|---|---|
| `feature` | 5 | +145 / -143 |
| `test_addition` | 5 | +117 / -29 |
| `bug_fix` | 7 | +18 / -48 |
| `compatibility_patch` | 1 | — |
| `formatting_only` | 1 | — |

The other 176 changed files are `pom.xml` and similar build metadata
(`config_or_docs`) — the §13 distinction holds: 170 version bumps vs 13 real
source files.

### Two commit groups, and they are NOT the same kind of work

**`f213380f` — a REVERT, not new code.** Message: *Revert "More native
handling of UTF8StringValue in block format (…94)"* — it reverts upstream
`a6083627…`. Touching 7 files (`UTF8StringValue.java` +58/-119,
`ShortStringCodec.java` +13/-30, `ValueWriter.java` +1/-12, `Values.java`
+7/-13, `TextType.java` +2/-3, `PackstreamValueWriter.java` +1/-1,
`GenericKey.java` +1/-1). This is **removing** upstream behaviour on the
fork's `2026.09` branch. The 13 `.java` files are real source changes, but
this group is a *rejection* of upstream work, not authored work.

**`430e13de` — explicitly a CHERRY-PICK.** Message: *[neo4j-admin-database-upload]
Add --to-dbid flag and instance-based URI support* — *"Cherry-picks
`475259cdcddaee421fb76cf41d7c5b0b471d33d5` onto `2026.07`."*
`AuraURLFactory.java` +62/-10 plus its test.

**Honest caveat:** upstream `475259cd…` returns **422 "No commit found"** on
`neo4j/neo4j`. The commit self-describes as a cherry-pick, but the source ref
is not on the default upstream — it may live on an internal Aura branch. So
this is upstream-*derived by the commit's own account*, but not independently
verifiable against `neo4j/neo4j`.

**`88a7ceb7` — genuine owner-authored bug fix.** *"Import: Fix relationship
id-type inheritance across multiple relationship files"* — a node `:ID` column
declares its id space's type; relationship `:START_ID`/`:END_ID` columns
inherit it so the id extractor agrees with the encoder. `DataFactories.java`
+10/-0 with a matching 41-line `DataFactoriesTest.java`. This is original work
with its own test.

### neo4j conclusion

**INSPECT_THEN_PORT**, but the port candidates are narrower than the file
count suggests: `DataFactories.java` + its test is the one clearly
owner-authored fix. The `f213380f` group is a deliberate revert of upstream
UTF8StringValue work — a decision to understand before either re-applying or
discarding, not code to harvest. `430e13de` is upstream-derived.

**Recommendation: preserve the provenance trail, port `88a7ceb7`, and treat
`f213380f` as a recorded architectural decision.** Deleting the fork would
destroy the record of *why* upstream's native UTF8StringValue handling was
rejected.

---

## 3. IsaacLab — 154 commits, 300 files, 355 substantive source changes

### Distribution

| Category | Files | ± |
|---|---|---|
| `feature` | 91 | **+8587 / -2863** |
| `bug_fix` | 101 | +528 / -849 |
| `test_addition` | 153 | large |
| `compatibility_patch` | 42 | +613 / -363 |
| `formatting_only` | 149 | — |
| `config_or_docs` | 75 | — |
| `metadata_only` | 60 | — |
| `deletion` | 29 | — |

### Capability clusters (§16)

| Cluster | Files |
|---|---|
| environment | 195 |
| simulation | 188 |
| sensor_perception | 52 |
| tests | 43 |
| build_config | 41 |
| training | 39 |
| experiments | 28 |
| robot_control | 22 |
| unclustered | 243 |

### The critical finding: the largest changes are upstream-derived

The top three changes by size are cherry-picks and backports, by their own
commit messages:

- **`a84e02b5`** — *"Cherry-picks fixes for visualizers, SKRL template,
  digit limitations, teleop/mimic dependency (#5829)"* — *"Cherry pick bug
  fix PRs from develop"*. Includes the +1658/-341
  `visualizer_integration_util` change.
- **`5144c765`** — *"Cherry-picks RLinf/compass doc updates, visualizer
  fixes, presets and imports fixes, Newton 1.2.1rc2 pin (#6014)"*.
- **`bffdce9d`** — *"[Backport release/3.0.0-beta2] FrameView local poses
  (#5677) + view-scoped Fabric selections (#6805)"* — *"Backports two
  already-merged FrameView PRs … cherry-picked in merge order"*. Covers
  `fabric_frame_` +876/-224 and `newton_site` +554/-791.

**So "355 substantive source changes" overstates the owner's original
contribution.** A shape-based classifier correctly identifies these as
substantial *code*; it cannot tell authored work from backported work. The
commit messages can, and they say: these are backports of already-merged
upstream PRs onto release branches.

That is normal fork maintenance — a release branch carrying fixes forward —
but it is **not** unique owner work, and it must not be harvested as if it
were.

### IsaacLab conclusion

**INSPECT_THEN_PORT**, with the port surface much smaller than 355 files.
The genuinely interesting clusters for Aetherius are `sensor_perception`
(52 files, incl. `scripts/demos/sensors/ppisp_camera.py` +601/-0) and
`robot_control` (22 files) — those are where Genesis embodiment work would
live. Everything in `build_config` is backport tooling
(`resolve_backport_conflicts.py` +426, `backport.py` +276) and is of no
value to Aetherius.

**Next step:** classify each of the 154 commits by message intent
(cherry-pick / backport / original) before deciding what to port. The file
count alone would send the owner reading 355 diffs, most of which are
upstream's own code coming back.

---

## 4. What this means for SAFE_TO_DELETE

`SAFE_TO_DELETE = 0`, unchanged, and correctly so. The analysis makes the
case stronger rather than weaker: neo4j's fork records a *rejection* of
upstream work whose rationale exists nowhere else, and IsaacLab's fork
carries release-branch backport history. Both are provenance, not clutter.

Deletion is the outcome of completed migration, not a progress KPI.

---

## 5. Method note — a limit worth recording

The classifier's job is to decide *what kind* of change a diff is. It does
that from shape, and it now does it without falling through to
`unclassified`. What it structurally **cannot** do is distinguish
owner-authored code from upstream code carried on a fork — that distinction
lives in commit messages, not diffs.

A future pass should classify commits by message intent. Reporting
"355 substantive source changes" without that qualifier would let a reader
conclude the owner wrote 355 files' worth of original code, which the
evidence does not support.
