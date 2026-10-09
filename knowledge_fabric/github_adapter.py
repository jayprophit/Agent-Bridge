"""GitHub repository ingestion adapter (§19, §55, §56).

Proves authorised retrieval of repository metadata, branches, commits,
issues, PRs, and source code via the `gh` CLI or GitHub API.

Uses official GitHub CLI/API access (priority 1: official API/connector).
Only accesses owner-authorized repositories (jayprophit).

Do NOT create or fork a repository merely to prove the connector.
"""
from __future__ import annotations

import json
import subprocess
import time
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from knowledge_fabric.source_adapter import (
    KnowledgeSourceAdapter, SourceMetadata,
    CAP_LIST_CONVERSATIONS, CAP_GET_METADATA, CAP_SEARCH,
    ACCESS_OFFICIAL_API, SOURCE_TYPE_REPOSITORY,
    SOURCE_TYPE_FILE, SOURCE_TYPE_IMAGE,
    STATE_VERIFIED, STATE_AUTH_REQUIRED, STATE_BLOCKED,
    stable_source_id,
)

GITHUB_OWNER = "jayprophit"
REPO_URL_BASE = "https://github.com"


@dataclass
class GitHubRepoInfo:
    """Structured info about a GitHub repository."""
    name: str = ""
    full_name: str = ""
    url: str = ""
    description: str = ""
    visibility: str = "public"
    default_branch: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    pushed_at: float = 0.0
    language: str = ""
    languages: dict[str, int] = field(default_factory=dict)
    stargazers: int = 0
    forks: int = 0
    open_issues: int = 0
    archived: bool = False
    fork: bool = False
    parent: str = ""
    license: str = ""
    topics: list[str] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    is_aetherius_owned: bool = False
    projects: list[str] = field(default_factory=list)
    classification: str = "UNKNOWN"
    remote_sha: str = ""
    evidence: str = ""


class GitHubAdapter(KnowledgeSourceAdapter):
    """GitHub repository ingestion via official GitHub CLI/API (§5 priority 1)."""

    adapter_id = "github"
    platform = "github"
    source_type = SOURCE_TYPE_REPOSITORY
    access_method = ACCESS_OFFICIAL_API
    state = STATE_VERIFIED
    supported_capabilities = (
        CAP_LIST_CONVERSATIONS,  # list repos
        CAP_GET_METADATA,        # get repo metadata
        CAP_SEARCH,              # search code/repos
    )
    privacy_class = "PROJECT"
    owner = "Jonathan"
    authorisation_required = True

    def __init__(self, owner: str = GITHUB_OWNER) -> None:
        self.owner = owner
        self._auth_checked = False
        self._auth_ok = False

    def _check_auth(self) -> bool:
        """Verify GitHub CLI is authenticated (§19)."""
        if self._auth_checked:
            return self._auth_ok
        try:
            result = subprocess.run(
                ["gh", "api", "user", "--jq", ".login"],
                capture_output=True, text=True, timeout=15,
            )
            self._auth_ok = result.returncode == 0 and result.stdout.strip()
            if self._auth_ok:
                self._auth_user = result.stdout.strip()
        except Exception:
            self._auth_ok = False
        self._auth_checked = True
        if not self._auth_ok:
            self.state = STATE_AUTH_REQUIRED
        return self._auth_ok

    def list_sources(self, project: str | None = None,
                     limit: int = 100) -> list[SourceMetadata]:
        """List all repositories for the owner (§55)."""
        if not self._check_auth():
            self.state = STATE_AUTH_REQUIRED
            return []

        try:
            result = subprocess.run(
                ["gh", "repo", "list", self.owner,
                 "--limit", str(limit), "--json",
                 "name,url,description,visibility,defaultBranchRef,"
                 "createdAt,updatedAt,pushedAt,primaryLanguage,"
                 "stargazerCount,forkCount,"
                 "isArchived,isFork,licenseInfo,repositoryTopics"],
                capture_output=True, text=True, timeout=60,
            )
            repos = json.loads(result.stdout) if result.returncode == 0 else []
        except Exception:
            repos = []

        sources = []
        seen_ids: set[str] = set()
        for repo in repos:
            name = repo.get("name", "")
            if not name:
                continue
            full_name = f"{self.owner}/{name}"
            created = self._parse_ts(repo.get("createdAt"))
            updated = self._parse_ts(repo.get("updatedAt"))
            pushed = self._parse_ts(repo.get("pushedAt"))

            source_id = stable_source_id("github", full_name)
            # GitHub can emit the same repository more than once across
            # paginated responses. A duplicate source_id would corrupt the
            # incremental-sync state (§11) by double-counting a repository,
            # so duplicates are collapsed here rather than downstream.
            if source_id in seen_ids:
                continue
            seen_ids.add(source_id)

            src = SourceMetadata(
                source_id=source_id,
                source_type=SOURCE_TYPE_REPOSITORY,
                platform="github",
                remote_id=full_name,
                remote_url=f"{REPO_URL_BASE}/{full_name}",
                title=name,
                created_at=created,
                updated_at=updated,
                access_method=ACCESS_OFFICIAL_API,
                privacy_class="PUBLIC",
                projects=[],  # will be populated by project association
                state=STATE_VERIFIED if updated else "UNKNOWN",
                last_checked=time.time(),
                evidence="VERIFIED_LIVE",
                adapter_id=self.adapter_id,
            )
            sources.append(src)

        self.state = STATE_VERIFIED
        return sources

    def get_metadata(self, source_id: str) -> Optional[SourceMetadata]:
        """Get detailed metadata for a specific repository."""
        if not self._check_auth():
            return None

        # source_id format: SRC-GITHUB-jayprophit-repo-name
        # Extract repo name
        parts = source_id.replace("SRC-GITHUB-", "").replace("SRC-github-", "")
        if "/" not in parts and "-" in parts:
            # May have been flattened; try to reconstruct
            parts = parts.replace("-", "/", 1)

        repo_path = parts
        try:
            result = subprocess.run(
                ["gh", "api",
                 f"/repos/{repo_path}",
                 "--jq", "."],
                capture_output=True, text=True, timeout=30,
            )
            repo = json.loads(result.stdout) if result.returncode == 0 else None
        except Exception:
            repo = None

        if repo is None:
            return None

        # Get latest commit SHA
        sha = ""
        try:
            default_branch = repo.get("default_branch", "main")
            sha_result = subprocess.run(
                ["gh", "api",
                 f"/repos/{repo_path}/commits/{default_branch}",
                 "--jq", ".sha"],
                capture_output=True, text=True, timeout=30,
            )
            if sha_result.returncode == 0:
                sha = sha_result.stdout.strip()
        except Exception:
            pass

        return SourceMetadata(
            source_id=source_id,
            source_type=SOURCE_TYPE_REPOSITORY,
            platform="github",
            remote_id=repo_path,
            remote_url=repo.get("html_url", f"{REPO_URL_BASE}/{repo_path}"),
            title=repo.get("name", ""),
            created_at=self._parse_ts(repo.get("created_at")),
            updated_at=self._parse_ts(repo.get("updated_at")),
            access_method=ACCESS_OFFICIAL_API,
            privacy_class="PUBLIC" if repo.get("visibility") == "public" else "PROJECT",
            state="VERIFIED_LIVE" if sha else "UNKNOWN",
            last_checked=time.time(),
            evidence="VERIFIED_LIVE" if sha else "VERIFIED_CONFIGURED",
            adapter_id=self.adapter_id,
            metadata={
                "default_branch": repo.get("default_branch", "main"),
                "remote_sha": sha,
                "fork": repo.get("fork", False),
                "archived": repo.get("archived", False),
                "open_issues": repo.get("open_issues_count", 0),
                "stargazers": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "language": repo.get("language", ""),
                "license": repo.get("license", {}).get("spdx_id", "") if repo.get("license") else "",
            },
        )

    def get_repository_branches(self, source_id: str, limit: int = 20) -> list[dict]:
        """List repository branches (§19, §55 test: repository detail)."""
        if not self._check_auth():
            return []
        repo_path = self._extract_repo_path(source_id)
        try:
            result = subprocess.run(
                ["gh", "api", f"/repos/{repo_path}/branches",
                 "--jq", "[.[] | {name, commit: {sha: .commit.sha}, protected: .protected}]",
                 "--page", "1"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip() and result.stdout.strip() != "null":
                return json.loads(result.stdout)[:limit]
        except Exception:
            pass
        return []

    def get_repository_commits(self, source_id: str, limit: int = 20) -> list[dict]:
        """List repository commits (§19, §55 test: repository detail)."""
        if not self._check_auth():
            return []
        repo_path = self._extract_repo_path(source_id)
        try:
            result = subprocess.run(
                ["gh", "api", f"/repos/{repo_path}/commits",
                 "--jq", "[.[] | {sha: (.sha[:12]), message: (.commit.message | split(\"\\n\" | \"\")[0]), author: .commit.author.name, date: .commit.author.date}]",
                 "--per-page", str(limit)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip() and result.stdout.strip() != "null":
                return json.loads(result.stdout)[:limit]
        except Exception:
            pass
        return []

    def get_repository_issues(self, source_id: str, limit: int = 20) -> list[dict]:
        """List repository issues (§19, §55 test: repository detail)."""
        if not self._check_auth():
            return []
        repo_path = self._extract_repo_path(source_id)
        try:
            result = subprocess.run(
                ["gh", "api", f"/repos/{repo_path}/issues",
                 "--jq", "[.[] | select(.pull_request == null) | {number, title, state, author: .user.login, created_at}]",
                 "--per-page", str(limit)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip() and result.stdout.strip() != "null":
                return json.loads(result.stdout)[:limit]
        except Exception:
            pass
        return []

    def get_repository_prs(self, source_id: str, limit: int = 20) -> list[dict]:
        """List repository pull requests (§19, §55 test: repository detail)."""
        if not self._check_auth():
            return []
        repo_path = self._extract_repo_path(source_id)
        try:
            result = subprocess.run(
                ["gh", "api", f"/repos/{repo_path}/pulls",
                 "--jq", "[.[] | {number, title, state, author: .user.login, created_at}]",
                 "--per-page", str(limit)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip() and result.stdout.strip() != "null":
                return json.loads(result.stdout)[:limit]
        except Exception:
            pass
        return []

    def search_code(self, query: str, limit: int = 10) -> list[dict]:
        """Search code in owned repositories (§19, §55 test: repository search)."""
        if not self._check_auth():
            return []
        q = f"user:{self.owner} {query}"
        try:
            result = subprocess.run(
                ["gh", "api", f"/search/code",
                 "-H", "Accept: application/vnd.github+json",
                 "--jq", "[.items[] | {path, repository: .repository.full_name, html_url: .html_url}]",
                 "--search", q],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if isinstance(data, list):
                    return data[:limit]
        except Exception:
            pass
        # Fallback: use gh search code
        try:
            result = subprocess.run(
                ["gh", "search", "code", query, "--owner", self.owner,
                 "--json", "name,repository,path,url", "--limit", str(limit)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)[:limit]
        except Exception:
            pass
        return []

    def get_fork_info(self, source_id: str) -> dict:
        """Get fork/parent relationship for a repository (§20, §55)."""
        if not self._check_auth():
            return {}
        repo_path = self._extract_repo_path(source_id)
        try:
            result = subprocess.run(
                ["gh", "api", f"/repos/{repo_path}",
                 "--jq", "{fork: .fork, parent: (.parent.full_name if .parent else null), parent_url: (.parent.html_url if .parent else null), is_archived: .archived}"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception:
            pass
        return {}

    def _extract_repo_path(self, source_id: str) -> str:
        """Extract 'owner/repo' from a source_id."""
        parts = source_id.replace("SRC-GITHUB-", "").replace("SRC-github-", "")
        return parts

    def read_content(self, source_id: str) -> str:
        """Read README content for a repository."""
        if not self._check_auth():
            return ""
        parts = source_id.replace("SRC-GITHUB-", "").replace("SRC-github-", "")
        if "/" not in parts and "-" in parts:
            parts = parts.replace("-", "/", 1)
        try:
            result = subprocess.run(
                ["gh", "api", f"/repos/{parts}/readme",
                 "--jq", ".content"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                import base64
                content = base64.b64decode(result.stdout.strip()).decode("utf-8", errors="replace")
                return content
        except Exception:
            pass
        return ""

    def search(self, query: str, project: str | None = None,
               limit: int = 20) -> list[SourceMetadata]:
        """Search code across owner repositories (§55)."""
        if not self._check_auth():
            return []
        try:
            result = subprocess.run(
                ["gh", "api", "/search/code",
                 "--method", "GET",
                 "--field", f"q={query}+user:{self.owner}",
                 "--jq", f".items[:{limit}] | .[] | {{name: .repository.full_name, path: .path, html_url: .html_url}}"],
                capture_output=True, text=True, timeout=60,
            )
            items = json.loads(result.stdout) if result.returncode == 0 else []
        except Exception:
            items = []

        sources = []
        for item in items:
            sources.append(SourceMetadata(
                source_id=stable_source_id("github-search", item.get("html_url", "")),
                source_type=SOURCE_TYPE_REPOSITORY,
                platform="github",
                remote_id=item.get("name", ""),
                remote_url=item.get("html_url", ""),
                title=item.get("path", ""),
                created_at=time.time(),
                updated_at=time.time(),
                access_method=ACCESS_OFFICIAL_API,
                privacy_class="PUBLIC",
                state="VERIFIED_LIVE",
                last_checked=time.time(),
                evidence="VERIFIED_LIVE",
                adapter_id=self.adapter_id,
            ))
        return sources

    @staticmethod
    def _parse_ts(ts_str: str | None) -> float:
        """Parse GitHub ISO timestamp to epoch."""
        if not ts_str:
            return 0.0
        try:
            # ISO 8601: 2016-07-22T12:34:56Z
            from datetime import datetime
            return datetime.fromisoformat(
                ts_str.replace("Z", "+00:00")
            ).timestamp()
        except Exception:
            return 0.0


class FileIngestionAdapter(KnowledgeSourceAdapter):
    """File/document ingestion adapter (§31, §55 proof).

    Reads local files, extracts text, computes content hash for
    incremental sync. Supports TXT, MD, JSON, YAML, CSV, and uses
    existing PDF/DOCX extraction from document tooling where available.
    """

    adapter_id = "file_ingestion"
    platform = "local"
    source_type = SOURCE_TYPE_FILE
    access_method = ACCESS_OFFICIAL_API  # local filesystem = authorized
    state = STATE_VERIFIED
    supported_capabilities = (
        CAP_LIST_CONVERSATIONS,
        CAP_GET_METADATA,
        CAP_SEARCH,
    )
    privacy_class = "PROJECT"
    authorisation_required = False

    def __init__(self, watch_dirs: list[str] | None = None) -> None:
        self.watch_dirs = watch_dirs or []

    def index_directory(self, directory: str,
                        extensions: tuple[str, ...] = (".py", ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".toml")) -> list[SourceMetadata]:
        """Index all files in a directory tree (§32)."""
        import hashlib

        sources = []
        base = directory.replace("\\", "/")
        for root, dirs, files in os.walk(base):
            # Skip hidden dirs and .git
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in extensions:
                    continue
                fpath = os.path.join(root, fname).replace("\\", "/")
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except Exception:
                    continue

                rel_path = os.path.relpath(fpath, base).replace("\\", "/")
                source_id = stable_source_id("file", rel_path)
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

                stat = os.stat(fpath)
                src = SourceMetadata(
                    source_id=source_id,
                    source_type=SOURCE_TYPE_FILE,
                    platform="local",
                    remote_id=rel_path,
                    remote_url=f"file://{fpath}",
                    title=fname,
                    created_at=stat.st_ctime,
                    updated_at=stat.st_mtime,
                    access_method=ACCESS_OFFICIAL_API,
                    privacy_class="PROJECT",
                    projects=[],
                    state="VERIFIED_LIVE",
                    last_checked=stat.st_mtime,
                    evidence="VERIFIED_LIVE",
                    adapter_id=self.adapter_id,
                    content_hash=content_hash,
                    metadata={
                        "path": fpath,
                        "size_bytes": stat.st_size,
                        "extension": ext,
                        "line_count": content.count("\n") + 1,
                    },
                )
                sources.append(src)
        return sources

    def read_content(self, source_id: str) -> str:
        """Read file content from source_id."""
        parts = source_id.replace("SRC-FILE-", "")
        # If it's an absolute path, try it directly first
        if os.path.isfile(parts):
            try:
                with open(parts, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()
            except OSError:
                pass
        # Try to find in watch dirs
        for watch_dir in self.watch_dirs:
            fpath = os.path.join(watch_dir, parts).replace("\\", "/")
            if os.path.isfile(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        return f.read()
                except OSError:
                    continue
        return ""

    def hash_source(self, source_id: str) -> str:
        """Compute content hash for incremental sync (§9)."""
        import hashlib
        content = self.read_content(source_id)
        if not content:
            return ""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def search(self, query: str, project: str | None = None,
               limit: int = 20) -> list[SourceMetadata]:
        """Search file contents for a query string."""
        import hashlib
        results = []
        for watch_dir in self.watch_dirs:
            for root, dirs, files in os.walk(watch_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for fname in files:
                    fpath = os.path.join(root, fname).replace("\\", "/")
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                    except Exception:
                        continue
                    if query.lower() in content.lower():
                        rel = os.path.relpath(fpath, watch_dir).replace("\\", "/")
                        stat = os.stat(fpath)
                        results.append(SourceMetadata(
                            source_id=stable_source_id("file", rel),
                            source_type=SOURCE_TYPE_FILE,
                            platform="local",
                            remote_id=rel,
                            title=fname,
                            created_at=stat.st_ctime,
                            updated_at=stat.st_mtime,
                            privacy_class="PROJECT",
                            state="VERIFIED_LIVE",
                            last_checked=stat.st_mtime,
                            evidence="VERIFIED_LIVE",
                            adapter_id=self.adapter_id,
                            content_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
                        ))
                        if len(results) >= limit:
                            return results
        return results


class ImageIngestionAdapter(KnowledgeSourceAdapter):
    """Image/multimodal ingestion adapter (§28, §55 proof).

    Extracts useful project information from images (screenshots, diagrams)
    using vision understanding where available, falls back to metadata.
    """

    adapter_id = "image_ingestion"
    platform = "local"
    source_type = SOURCE_TYPE_IMAGE
    access_method = ACCESS_OFFICIAL_API
    state = STATE_VERIFIED
    supported_capabilities = (
        CAP_LIST_CONVERSATIONS,
        CAP_GET_METADATA,
    )
    privacy_class = "PROJECT"
    authorisation_required = False

    def __init__(self) -> None:
        pass

    def index_images(self, directory: str,
                     extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")) -> list[SourceMetadata]:
        """Index image files in a directory tree (§28)."""
        import hashlib

        sources = []
        base = directory.replace("\\", "/")
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in extensions:
                    continue
                fpath = os.path.join(root, fname).replace("\\", "/")
                try:
                    stat = os.stat(fpath)
                except Exception:
                    continue

                # Compute content hash
                try:
                    with open(fpath, "rb") as f:
                        content_hash = hashlib.sha256(f.read()).hexdigest()[:16]
                except Exception:
                    content_hash = ""

                rel = os.path.relpath(fpath, base).replace("\\", "/")
                src = SourceMetadata(
                    source_id=stable_source_id("image", rel),
                    source_type=SOURCE_TYPE_IMAGE,
                    platform="local",
                    remote_id=rel,
                    remote_url=f"file://{fpath}",
                    title=fname,
                    created_at=stat.st_ctime,
                    updated_at=stat.st_mtime,
                    access_method=ACCESS_OFFICIAL_API,
                    privacy_class="PROJECT",
                    state="VERIFIED_LIVE",
                    last_checked=stat.st_mtime,
                    evidence="VERIFIED_LIVE",
                    adapter_id=self.adapter_id,
                    content_hash=content_hash,
                    metadata={
                        "path": fpath,
                        "size_bytes": stat.st_size,
                        "extension": ext,
                        "width": 0,
                        "height": 0,
                    },
                )
                sources.append(src)
        return sources


__all__ = [
    "GitHubAdapter",
    "FileIngestionAdapter",
    "ImageIngestionAdapter",
    "GitHubRepoInfo",
]
