"""Resolve upstream parent for every fork (§4, §51 step 5) — READ-ONLY.

The REST list endpoint OMITS the `parent` field, so a bulk fetch cannot
classify forks. This resolves parents individually via `repos/<owner>/<repo>`,
which does return it.

Runs concurrently and is bounded: fork count is fixed by the estate, and
each lookup is a cheap REST call.

Writes resolved data to live_estate_resolved.json, which is a SEPARATE file
from the raw enumeration (§17). Before this split both stages wrote
live_estate.json, so re-running the fetch alone silently replaced resolved
upstream data with raw data that has no `parent` field at all.
"""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from migration.evidence_paths import (
    LEGACY_ESTATE, RAW_ESTATE, RESOLVED_ESTATE,
)

# §17 — reads raw, writes resolved. Never the reverse.
ESTATE = RESOLVED_ESTATE
JQ = ("{parent: (if .parent then .parent.full_name else null end),"
      " parent_branch: (if .parent then .parent.default_branch else null end),"
      " license: .license.spdx_id}")


def resolve(repo: dict) -> dict:
    url = f"repos/jayprophit/{repo['name']}"
    try:
        proc = subprocess.run(
            ["gh", "api", url, "--jq", JQ],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            repo.update(data)
            return repo
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    repo["parent"] = repo.get("parent")
    repo["_error"] = True
    return repo


def main() -> int:
    # §17 read the RAW enumeration, write the RESOLVED dataset. Reading and
    # writing the same file is what allowed one stage to clobber the other.
    if RAW_ESTATE.exists():
        repos = json.loads(RAW_ESTATE.read_text(encoding="utf-8"))
    else:
        # Backwards compatibility: no raw file yet, so fall back to the legacy
        # path rather than failing on an estate that predates the split.
        repos = json.loads(LEGACY_ESTATE.read_text(encoding="utf-8"))
    forks = [r for r in repos if r["fork"]]
    print(f"resolving upstream for {len(forks)} forks...")

    with ThreadPoolExecutor(max_workers=8) as pool:
        resolved = list(pool.map(resolve, forks))

    by_name = {r["name"]: r for r in resolved}
    for r in repos:
        if r["name"] in by_name:
            r.update(by_name[r["name"]])

    ESTATE.write_text(json.dumps(repos, indent=2), encoding="utf-8")

    linked = [r for r in repos if r["fork"] and r.get("parent")]
    orphan = [r for r in repos if r["fork"] and not r.get("parent")]
    errors = [r for r in repos if r.get("_error")]

    print()
    print(f"forks WITH upstream  {len(linked)}")
    print(f"forks WITHOUT        {len(orphan)}")
    print(f"lookup errors        {len(errors)}")
    if orphan:
        print("\nGenuinely unlinkable (NOT a fetch artifact):")
        for r in sorted(orphan, key=lambda x: x["name"])[:30]:
            print(f"  {r['name']:44} {r.get('license')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
