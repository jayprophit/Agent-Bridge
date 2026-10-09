"""Fetch the LIVE jayprophit repository estate (§3, §51 step 3) — READ-ONLY.

Uses the REST API via `gh api --paginate` because the GraphQL gateway is
returning 502. Stores raw JSON on disk so later stages never re-hit the
network and never put 394 READMEs into one model context (§48).

Per-repo fields follow the §26 use-case record schema where the API
provides them.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "migration" / "evidence" / "live_estate.json"
JQ = (
    "[.[] | {name, full_name, private, visibility, fork, archived,"
    " default_branch, license: .license.spdx_id,"
    " parent: (if .parent then .parent.full_name else null end),"
    " parent_default: (if .parent then .parent.default_branch else null end),"
    " pushed_at, created_at, size_kb, language,"
    " stars: .stargazers_count, forks: .forks_count,"
    " open_issues, url, description}]"
)


def fetch_page(page: int) -> list:
    """One page of 100 repos, with retry on transient 5xx."""
    url = f"users/jayprophit/repos?per_page=100&page={page}&sort=full_name"
    for attempt in range(4):
        proc = subprocess.run(
            ["gh", "api", url, "--jq", JQ],
            capture_output=True, text=True, timeout=180,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError:
                pass
        if "502" in proc.stderr or "503" in proc.stderr:
            time.sleep(4 * (attempt + 1))
            continue
        print(f"page {page} failed: {proc.stderr[:200]}", file=sys.stderr)
        break
    return []


def main() -> int:
    repos: list = []
    seen: set = set()
    page = 1
    while page <= 6:  # bounded: 394 repos = 4 pages
        batch = fetch_page(page)
        if not batch:
            break
        fresh = [r for r in batch if r["full_name"] not in seen]
        for r in fresh:
            seen.add(r["full_name"])
        repos.extend(fresh)
        print(f"page {page}: {len(batch)} repos (total {len(repos)})")
        if len(batch) < 100:
            break
        page += 1
        time.sleep(1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(repos, indent=2), encoding="utf-8")

    forks = [r for r in repos if r["fork"]]
    originals = [r for r in repos if not r["fork"]]
    no_parent = [r for r in forks if not r["parent"]]
    private = [r for r in repos if r["private"]]
    archived = [r for r in repos if r["archived"]]

    print()
    print(f"TOTAL        {len(repos)}")
    print(f"  original   {len(originals)}")
    print(f"  fork       {len(forks)}")
    print(f"    w/ parent {len(forks) - len(no_parent)}")
    print(f"    NO parent {len(no_parent)}  <- fork-flagged but unlinkable")
    print(f"  private    {len(private)}")
    print(f"  archived   {len(archived)}")
    if no_parent:
        print("\nfork-flagged but NO upstream (investigate):")
        for r in sorted(no_parent, key=lambda x: x["name"])[:25]:
            print(f"  {r['name']:42} {r['license']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
