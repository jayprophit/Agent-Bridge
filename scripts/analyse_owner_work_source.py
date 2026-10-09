"""Source-level owner-work analysis (§16–§18).

Reads the ACTUAL DIFFS behind the three HOLD forks rather than inferring
from filenames. "Do not infer from filenames alone" — a file called
`DataFactories.java` could hold a one-line whitespace change or a genuine
protocol fix, and only the patch says which.

Fetches per-file patches through the GitHub compare API, so no local clone
of a 452-commit-behind upstream is required. Each change is then classified
by what it DOES, not what it is called.

Nothing is deleted, ported or modified. This is analysis input for the
owner's keep/port/adapt decision (§15).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# §15 — deletion DENY for all three. This script never proposes deletion.
HOLD_FORKS = ("jayprophit/neo4j", "jayprophit/IsaacLab",
              "jayprophit/devops-directive-docker-course")

# §16 — IsaacLab capability clusters. 154 commits is too many to treat as
# one unit, so divergence is grouped by what it touches.
ISAACLAB_CLUSTERS = {
    "simulation": ("simulation", "sim", "physx", "physics", "isaacgym"),
    "robot_control": ("robot", "articulation", "actuator", "controller",
                      "joint"),
    "training": ("train", "rl_games", "rsl_rl", "skrl", "runner", "vecenv"),
    "environment": ("env", "task", "terrain", "scene"),
    "sensor_perception": ("sensor", "camera", "lidar", "ray_caster",
                          "tiled_camera", "perception"),
    "genesis_embodiment": ("genesis", "embodiment", "avatar"),
    "aetherius_integration": ("aetherius", "agent_bridge", "bridge"),
    "tests": ("test", "tests/", "_test.py"),
    "build_config": (".github", "dockerfile", "setup.py", "pyproject",
                     "requirements", "ci", "workflow"),
    "experiments": ("experiment", "scripts/", "notebook", "demo"),
}


def gh(*args: str) -> dict | list | None:
    """Run a gh api call, returning parsed JSON or None on failure."""
    proc = subprocess.run(["gh", "api", *args],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def default_branch(full_name: str) -> str | None:
    data = gh(f"repos/{full_name}")
    return (data or {}).get("default_branch")


def fetch_compare(fork: str, upstream: str,
                  fork_branch: str | None = None,
                  upstream_branch: str | None = None) -> dict | None:
    """Compare endpoint on the UPSTREAM repo (404s on the fork)."""
    fb = fork_branch or default_branch(fork)
    ub = upstream_branch or default_branch(upstream)
    if not fb or not ub:
        return None
    return gh(f"repos/{upstream}/compare/{ub}...{fork.split('/')[0]}:{fb}")


# --------------------------------------------------------------------------
# Patch classification — what the change DOES
#
# Classification reads the SHAPE of the diff (definition counts, assertion
# counts, import churn, add/remove balance) rather than matching keywords on
# added lines. See classify_patch() for why shape beats keywords here.
# --------------------------------------------------------------------------


def classify_patch(filename: str, patch: str) -> tuple[str, str]:
    """Classify one file's diff. Returns (category, reason).

    FORMATTING_ONLY is determined structurally: a patch whose added and
    removed lines are identical after stripping whitespace changed nothing
    semantic. That check runs FIRST, because a formatting-only diff that
    happens to contain the word "fix" in a comment is still formatting.

    The remaining categories are decided by what the diff DOES, measured
    from its shape rather than from keyword luck. An earlier version
    pattern-matched for words like "fix" and "def " on added lines and
    labelled 613 of IsaacLab's largest changes `unclassified` — real work
    like +1658/-341 in a test utility carries no such keyword, so a
    keyword-only classifier reports the most substantial changes as the
    least certain. Shape is what a diff actually tells you.
    """
    added = [ln[1:] for ln in patch.splitlines() if ln.startswith("+")
             and not ln.startswith("+++")]
    removed = [ln[1:] for ln in patch.splitlines() if ln.startswith("-")
               and not ln.startswith("---")]

    def strip(ln: str) -> str:
        return re.sub(r"\s+", "", ln)

    if added and removed and sorted(map(strip, added)) == \
            sorted(map(strip, removed)):
        return ("formatting_only",
                "added and removed lines are identical ignoring whitespace")

    if not added:
        return ("deletion", "lines removed, none added")

    lang = classify_language(filename)
    test_path = bool(re.search(r"(^|/)(tests?|spec)/|_test\.|test_.*\.py$"
                               r"|Test\.java$", filename))

    # Structure counts: what KIND of code the diff adds.
    defs = sum(1 for ln in added
               if re.match(r"\s*(def |class |public |private |protected |"
                           r"static |async def |@Test|@pytest|TEST\(|"
                           r"TEST_F\()", ln))
    asserts = sum(1 for ln in added
                  if re.search(r"\b(assert|expect|ASSERT_|EXPECT_|self\.assert)"
                               r"\w*\s*\(", ln))
    imports = sum(1 for ln in added
                  if re.match(r"\s*(import |from |using |#include |package )",
                              ln))
    docish = sum(1 for ln in added if re.match(r"\s*(#|\"\"\"|//|\*)", ln))

    # A test file, or a diff dominated by assertions, is test work —
    # whatever else it happens to contain.
    if test_path or (asserts >= 3 and asserts >= defs):
        return ("test_addition",
                f"test-shaped diff: {asserts} assertion(s), {defs} "
                f"definition(s)")

    # Declarative config/markup: a structural edit, not a behaviour change.
    if lang in ("config", "docs") or (
            defs == 0 and docish >= max(1, len(added) // 2)):
        return ("config_or_docs",
                f"declarative content: {defs} definitions, {docish} "
                f"comment/doc lines")

    # New definitions with real bodies = a feature. Keyword-free, so it
    # catches the substantial work a keyword search missed.
    if defs >= 3:
        return ("feature",
                f"{defs} new definition(s) added")

    # Imports plus a handful of changed lines: a dependency or
    # compatibility adjustment rather than new behaviour.
    if imports >= 2 and len(added) <= 40:
        return ("compatibility_patch",
                f"{imports} import change(s) with a small diff")

    # Small, surgical edit to existing code — the classic bug-fix shape.
    if len(added) <= 20 and removed and len(added) <= len(removed) * 2 + 5:
        return ("bug_fix",
                f"surgical edit: +{len(added)}/-{len(removed)}")

    if added:
        return ("feature",
                f"substantive addition: +{len(added)}/-{len(removed)} with "
                f"{defs} definition(s)")
    return ("metadata_only", "no textual diff")


def classify_language(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".java": "java", ".py": "python", ".cpp": "cpp", ".h": "cpp",
        ".hpp": "cpp", ".cu": "cuda", ".md": "docs", ".yml": "config",
        ".yaml": "config", ".json": "config", ".toml": "config",
        ".xml": "config", ".gradle": "build", ".txt": "config",
    }.get(ext, ext.lstrip(".") or "unknown")


def cluster_isaaclab(path: str) -> str:
    """§16 — group IsaacLab divergence by capability."""
    low = path.lower()
    for cluster, needles in ISAACLAB_CLUSTERS.items():
        if any(n in low for n in needles):
            return cluster
    return "unclustered"


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def analyse(fork: str, upstream: str, limit: int = 200) -> dict:
    """Read the real diffs for a HOLD fork and classify each change."""
    cmp_data = fetch_compare(fork, upstream)
    if not isinstance(cmp_data, dict):
        return {"fork": fork, "error": "compare endpoint unavailable",
                "deletion": "DENY"}

    commits = cmp_data.get("commits") or []
    files = cmp_data.get("files") or []

    # Per-file patches are NOT in the compare payload; they come from the
    # commits themselves. Reading each commit's files is what turns
    # "300 files changed" into "these 13 Java files changed like this".
    per_file: dict[str, dict] = {}
    for commit in commits[:limit]:
        sha = commit.get("sha", "")
        detail = gh(f"repos/{upstream}/commits/{sha}")
        if not isinstance(detail, dict):
            continue
        for f in detail.get("files") or []:
            path = f.get("filename", "")
            entry = per_file.setdefault(path, {
                "path": path,
                "language": classify_language(path),
                "commits": [],
                "additions": 0,
                "deletions": 0,
                "patches": [],
            })
            entry["commits"].append(sha[:8])
            entry["additions"] += f.get("additions", 0)
            entry["deletions"] += f.get("deletions", 0)
            patch = f.get("patch")
            if patch:
                entry["patches"].append(patch)

    classified = []
    for path, entry in per_file.items():
        patch = "\n".join(entry["patches"])
        category, reason = (classify_patch(path, patch)
                            if patch else ("metadata_only",
                                           "no textual diff (binary or mode)"))
        classified.append(OrderedDict([
            ("path", path),
            ("language", entry["language"]),
            ("commits", entry["commits"]),
            ("commit_count", len(entry["commits"])),
            ("additions", entry["additions"]),
            ("deletions", entry["deletions"]),
            ("category", category),
            ("reason", reason),
            ("cluster", cluster_isaaclab(path) if "IsaacLab" in fork else ""),
        ]))

    classified.sort(key=lambda r: (-r["additions"], r["path"]))

    # A source change is one that is neither formatting nor build metadata.
    # This is the distinction §13 turns on: 170 pom.xml edits are mostly
    # version bumps, while 13 .java files with real bodies are real work.
    # `config_or_docs` is excluded for the same reason — declarative churn
    # is not behaviour change.
    source_changes = [c for c in classified
                      if c["language"] in ("java", "python", "cpp", "cuda")
                      and c["category"] not in ("formatting_only",
                                                "config_or_docs")]

    return OrderedDict([
        ("fork", fork),
        ("upstream", upstream),
        ("deletion", "DENY"),
        ("commits_ahead", len(commits)),
        ("files_changed", len(files)),
        ("by_language", dict(Counter(c["language"] for c in classified)
                             .most_common())),
        ("by_category", dict(Counter(c["category"] for c in classified)
                             .most_common())),
        ("by_cluster", dict(Counter(c["cluster"] for c in classified
                                    if c["cluster"]).most_common())),
        ("source_change_count", len(source_changes)),
        ("source_changes", source_changes),
        ("all_changes", classified),
        ("recommendation", recommend(classified, source_changes)),
    ])


def recommend(classified: list[dict], source_changes: list[dict]) -> dict:
    """§16 keep/port/adapt decision, evidence-based.

    `source_changes` is pre-filtered to substantive source edits, so a
    non-empty list can never yield ARCHIVE. The decision reads that list
    rather than re-deriving it — deriving it twice is how the two answers
    drifted apart.
    """
    real = [c for c in source_changes
            if c["category"] in ("bug_fix", "feature",
                                 "compatibility_patch")]
    unclassified = [c for c in source_changes
                    if c["category"] == "unclassified"]
    if not real and not unclassified:
        return OrderedDict([
            ("decision", "ARCHIVE"),
            ("reason", "no substantive source change; formatting and build "
                       "metadata only"),
        ])
    if not real and unclassified:
        # Changes are substantive but no signal matched. That is a limit of
        # the classifier, not evidence of triviality — say so rather than
        # archiving real work on a pattern-matching miss.
        return OrderedDict([
            ("decision", "INSPECT_MANUALLY"),
            ("reason", f"{len(unclassified)} substantive source change(s) "
                       f"matched no automatic signal; classify by reading "
                       f"the diffs (§17)"),
            ("candidates", [c["path"] for c in unclassified[:25]]),
            ("owner_action", "read each diff before any port (§17)"),
        ])
    return OrderedDict([
        ("decision", "INSPECT_THEN_PORT"),
        ("reason", f"{len(real)} substantive source change(s) across "
                   f"{len({c['language'] for c in real})} language(s)"),
        ("candidates", [c["path"] for c in real[:25]]),
        ("owner_action", "read each diff before any port (§17)"),
    ])


def main() -> int:
    targets = [
        ("jayprophit/neo4j", "neo4j/neo4j"),
        ("jayprophit/IsaacLab", "isaac-sim/IsaacLab"),
    ]
    out_dir = REPO_ROOT / "migration" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for fork, upstream in targets:
        print(f"analysing {fork} vs {upstream} ...", flush=True)
        results.append(analyse(fork, upstream))

    report = OrderedDict([
        ("generated_by", "scripts/analyse_owner_work_source.py"),
        ("purpose", "§16–§18 source-level classification of HOLD forks"),
        ("deletion_policy", "DENY for all HOLD forks (§15) — nothing is "
                            "deleted, ported or modified by this script"),
        ("aetherial_gpl", "ARCHITECTURE_REFERENCE unless the owner "
                          "authorises GPL-compatible reuse (§18)"),
        ("forks", results),
    ])
    out = out_dir / "owner_work_source_analysis.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")

    for res in results:
        if "error" in res:
            print(f"  {res['fork']}: {res['error']}")
            continue
        print(f"\n{res['fork']}: {res['commits_ahead']} commits, "
              f"{res['files_changed']} files")
        print(f"  languages : {res['by_language']}")
        print(f"  categories: {res['by_category']}")
        if res["by_cluster"]:
            print(f"  clusters  : {res['by_cluster']}")
        print(f"  substantive source changes: {res['source_change_count']}")
        print(f"  recommendation: {res['recommendation']['decision']} — "
              f"{res['recommendation']['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
