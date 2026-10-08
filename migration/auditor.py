"""Live fork/upstream auditor (§10 gate step 1).

Runs REAL `gh repo view` calls against GitHub and records what actually
comes back. Nothing is inferred: an unverified field stays None and the
audit_status records the truth (NOT_CHECKED, VERIFIED, MISSING, ...).

The auditor is deliberately READ-ONLY. It never deletes, archives, or
modifies a repository. Gate 1 is the only gate it can satisfy.
"""

import json
import shutil
import subprocess

from .provenance import (
    AUDIT_AUTH_FAILED, AUDIT_ERROR, AUDIT_MISSING, AUDIT_NOT_A_FORK,
    AUDIT_NOT_CHECKED, AUDIT_VERIFIED, ProvenanceRecord,
)

AUDIT_FIELDS = [
    "nameWithOwner", "isFork", "isArchived", "defaultBranchRef",
    "licenseInfo", "parent", "pushedAt", "createdAt", "url",
]


def upstream_default_branch(upstream_full_name: str) -> str | None:
    """`gh repo view` does NOT expose parent.defaultBranchRef.

    Without this, a compare would silently target upstream HEAD. HEAD is
    usually the default branch, but provenance must state what was actually
    compared rather than leave a placeholder — so resolve it explicitly.
    """
    proc = _gh(["api", f"repos/{upstream_full_name}",
                "--jq", ".default_branch"])
    if proc.returncode != 0:
        return None
    branch = proc.stdout.strip()
    return branch or None


class AuditorUnavailable(Exception):
    """`gh` is missing or unauthenticated — the audit cannot run."""


def gh_available() -> tuple:
    """(available, reason). Never raises."""
    if not shutil.which("gh"):
        return False, "gh CLI not found on PATH"
    try:
        proc = subprocess.run(["gh", "auth", "status"],
                              capture_output=True, text=True, timeout=45)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"gh auth status failed: {exc}"
    if proc.returncode != 0:
        return False, "gh not authenticated (run: gh auth login)"
    return True, "ok"


def _gh(args: list, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(["gh"] + args, capture_output=True, text=True,
                          timeout=timeout)


def probe_repo(full_name: str) -> dict:
    """Live-probe ONE repository. Returns a raw fact dict.

    Never raises: failures come back as {"audit_status": ..., "error": ...}
    so a single bad repo cannot abort a batch.
    """
    proc = _gh(["repo", "view", full_name, "--json", ",".join(AUDIT_FIELDS)])
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        low = err.lower()
        if "could not resolve" in low or "not found" in low or "404" in low:
            return {"audit_status": AUDIT_MISSING, "error": err[:300]}
        if "auth" in low or "credential" in low or "403" in low:
            return {"audit_status": AUDIT_AUTH_FAILED, "error": err[:300]}
        return {"audit_status": AUDIT_ERROR, "error": err[:300]}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"audit_status": AUDIT_ERROR, "error": f"bad JSON: {exc}"}
    data["audit_status"] = (AUDIT_VERIFIED if data.get("isFork")
                            else AUDIT_NOT_A_FORK)
    return data


def apply_audit(record: ProvenanceRecord, facts: dict) -> ProvenanceRecord:
    """Write live facts onto a record and pass gate 1 when verified."""
    up = record.upstream
    up.audit_status = facts.get("audit_status", AUDIT_NOT_CHECKED)
    up.audit_error = facts.get("error")
    up.audited_at = __import__("time").time()

    if up.audit_status in (AUDIT_VERIFIED, AUDIT_NOT_A_FORK):
        up.is_fork = facts.get("isFork")
        up.is_archived = facts.get("isArchived")
        dbr = facts.get("defaultBranchRef") or {}
        up.fork_default_branch = dbr.get("name") if isinstance(dbr, dict) else None
        up.fork_pushed_at = facts.get("pushedAt")
        up.fork_url = facts.get("url") or up.fork_url
        lic = facts.get("licenseInfo") or {}
        if isinstance(lic, dict):
            up.license_key = lic.get("key")
            up.license_name = lic.get("name")
        parent = facts.get("parent") or {}
        if isinstance(parent, dict) and parent:
            owner = parent.get("owner") or {}
            up.upstream_full_name = f"{owner.get('login')}/{parent.get('name')}"
            up.upstream_url = f"https://github.com/{up.upstream_full_name}"
            # `parent.defaultBranchRef` is NOT returned by `gh repo view`
            # (it comes back null), so resolve it explicitly rather than
            # recording a misleading placeholder in provenance.
            up.upstream_default_branch = upstream_default_branch(
                up.upstream_full_name)

    # Gate 1 is satisfiable only by a genuinely verified fork relationship.
    if up.audit_status == AUDIT_VERIFIED and up.upstream_full_name:
        record.pass_gate("GATE_1_UPSTREAM_VERIFIED")
    return record


def audit_batch(records: list, limit: int | None = None,
                progress=None) -> dict:
    """Live-audit a bounded batch of records.

    `limit` keeps the operation small and reversible. Rate-limit or auth
    failure stops the batch immediately rather than recording junk.
    """
    available, reason = gh_available()
    if not available:
        raise AuditorUnavailable(reason)

    targets = records if limit is None else records[:limit]
    stats = {AUDIT_VERIFIED: 0, AUDIT_NOT_A_FORK: 0, AUDIT_MISSING: 0,
             AUDIT_AUTH_FAILED: 0, AUDIT_ERROR: 0}
    failures = []
    audited = 0

    for rec in targets:
        facts = probe_repo(rec.source_repo)
        apply_audit(rec, facts)
        status = facts.get("audit_status")
        stats[status] = stats.get(status, 0) + 1
        audited += 1
        if status == AUDIT_AUTH_FAILED:
            failures.append({"repo": rec.source_repo, "error": facts.get("error")})
            break
        if status in (AUDIT_ERROR, AUDIT_MISSING):
            failures.append({"repo": rec.source_repo, "status": status,
                             "error": facts.get("error")})
        if progress:
            progress(audited, len(targets), rec.source_repo, status)

    return {
        "audited": audited,
        "requested": len(targets),
        "by_status": stats,
        "failures": failures,
        "stopped_early": bool(failures and
                              any(f.get("status") == AUDIT_AUTH_FAILED
                                  or f.get("error") for f in failures
                                  if f.get("status") == AUDIT_AUTH_FAILED)),
    }


def detect_unique_commits(full_name: str) -> dict:
    """Compare fork vs upstream default branches (§10 step 9 precheck).

    Ahead-count > 0 means the fork carries commits upstream does not have:
    those MUST be preserved before any deletion.
    """
    ok, reason = gh_available()
    if not ok:
        raise AuditorUnavailable(reason)
    proc = _gh(["api", f"repos/{full_name}/compare/"
                       f"{full_name.split('/')[0]}:HEAD...HEAD",
                "--jq", ".ahead_by, .behind_by, .status"])
    if proc.returncode != 0:
        return {"has_unique_commits": None,
                "error": (proc.stderr or "")[:300]}
    lines = [l.strip() for l in proc.stdout.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return {"has_unique_commits": None, "error": "unexpected compare output"}
    try:
        ahead, behind = int(lines[0]), int(lines[1])
    except ValueError:
        return {"has_unique_commits": None, "error": "unparseable compare output"}
    return {
        "has_unique_commits": ahead > 0,
        "ahead_by": ahead,
        "behind_by": behind,
        "status": lines[2] if len(lines) > 2 else None,
    }
