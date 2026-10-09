"""Resolve upstream parent for every fork (§4, §51 step 5) — READ-ONLY.

The REST list endpoint OMITS the `parent` field, so a bulk fetch cannot
classify forks. This resolves parents individually via `repos/<owner>/<repo>`,
which does return it.

Runs concurrently and is bounded: fork count is fixed by the estate, and
each lookup is a cheap REST call. Writes parent data back into
live_estate.json so the classification stage never re-hits the network.
"""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ESTATE = REPO_ROOT / "migration" / "evidence" / "live_estate.json"
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
    repos = json.loads(ESTATE.read_text(encoding="utf-8"))
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
