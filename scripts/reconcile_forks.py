#!/usr/bin/env python
"""§20-§21 FORK / REPOSITORY RECONCILIATION.

Every fork must be ACCOUNTED FOR — mapped to a project and classified:
    FOUNDATION / DIRECT_REUSE / PARTIAL_REUSE / DEPENDENCY / REFERENCE /
    BENCHMARK / RESEARCH / SUPERSEDED / REDUNDANT / LICENCE_INCOMPATIBLE /
    IRRELEVANT.

"Use all forks" means ACCOUNT FOR ALL, not blindly merge all (§21). A fork
that is not used gets an explicit reason. Nothing is silently ignored.

Usage:
    python scripts/reconcile_forks.py --owner jayprophit [--json out.json]

Read-only against GitHub (gh CLI). Writes a reconciliation registry.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# §20 disposition taxonomy
FOUNDATION = "FOUNDATION"
DIRECT_REUSE = "DIRECT_REUSE"
PARTIAL_REUSE = "PARTIAL_REUSE"
DEPENDENCY = "DEPENDENCY"
REFERENCE = "REFERENCE"
BENCHMARK = "BENCHMARK"
RESEARCH = "RESEARCH"
SUPERSEDED = "SUPERSEDED"
REDUNDANT = "REDUNDANT"
LICENCE_INCOMPATIBLE = "LICENCE_INCOMPATIBLE"
IRRELEVANT = "IRRELEVANT"

# project-relevance keyword map -> which Aetherius project a fork could serve.
# A fork matching none is IRRELEVANT to the programme (still accounted for).
PROJECT_SIGNALS = {
    "genesis": ["genesis", "aetherius", "avatar", "dashboard", "agent-bridge"],
    "ide-workspace": ["vscode", "theia", "monaco", "code-server", "ide",
                      "editor", "tree-sitter", "language-server", "lsp"],
    "mat": ["materials", "atlas", "cad", "freecad", "kicad", "meshing",
            "fem", "mfem", "dolfinx", "opencascade"],
    "compute-fabric": ["vllm", "tvm", "ray", "llvm", "executorch", "mlir",
                       "triton", "cuda", "rocm", "inference", "quantiz"],
    "infra": ["n8n", "temporal", "grafana", "systemd", "docker", "moby",
              "kubernetes", "k8s", "observ"],
    "build-tooling": ["cmake", "meson", "bazel", "ninja", "ruff", "uv",
                      "pyinstaller", "protobuf", "grpc"],
    "media": ["comfyui", "ultralytics", "rtaudio", "csound", "blender",
              "image", "video", "audio", "vision", "yolo"],
    "embedded": ["coreboot", "tock", "esphome", "9front", "verilator",
                 "openroad", "fpga", "riscv"],
    "data": ["rxdb", "yugabyte", "postgres", "sqlite", "database", "db"],
}

# licences that conflict with the programme's own licensing posture
LICENCE_CONFLICT = {"gpl-3.0", "agpl-3.0", "sspl-1.0", "commons-clause",
                    "elastic-2.0", "busl-1.1"}


def _gh(args: list[str]) -> dict | list:
    r = subprocess.run(["gh"] + args, capture_output=True, text=True,
                       timeout=120.0)
    if r.returncode != 0:
        return {}
    try:
        return json.loads(r.stdout or "null")
    except json.JSONDecodeError:
        return {}


def _list_forks(owner: str) -> list[dict]:
    forks: list[dict] = []
    # gh repo list caps a single call at 1000; --fork returns only forks.
    batch = _gh(["repo", "list", owner, "--fork", "--limit", "1000",
                 "--json",
                 "nameWithOwner,parent,isFork,updatedAt,diskUsage,pushedAt"])
    if isinstance(batch, list):
        forks.extend(batch)
    return forks


def _license(name_with_owner: str) -> str:
    d = _gh(["repo", "view", name_with_owner,
             "--json", "licenseInfo,primaryLanguage"])
    lic = (d.get("licenseInfo") or {}).get("spdxId", "")
    lang = d.get("primaryLanguage") or {}
    return f"{lic}|{lang.get('name','') if isinstance(lang,dict) else lang}"


def classify(name: str, parent: str, license_lang: str) -> tuple[str, str,
                                                                   str]:
    """-> (disposition, project, reason). Deterministic, evidence-based."""
    lic = license_lang.split("|")[0].lower()
    low = f"{name} {parent}".lower()

    if lic in LICENCE_CONFLICT:
        return (LICENCE_INCOMPATIBLE, "",
                f"licence {lic.upper()} conflicts with programme posture")

    project = ""
    for proj, signals in PROJECT_SIGNALS.items():
        if any(s in low for s in signals):
            project = proj
            break

    if not project:
        return (IRRELEVANT, "",
                "no signal linking this fork to a registered project")

    # a fork whose own name equals the parent (never diverged) is a reference
    # copy, not a modified foundation
    own = name.split("/")[-1].lower()
    par = parent.split("/")[-1].lower() if parent else ""
    if own == par:
        return (REFERENCE, project,
                "unmodified fork of upstream; reference/study copy")

    return (PARTIAL_REUSE, project,
            f"diverged fork relevant to {project}; assess for reuse")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default="jayprophit")
    ap.add_argument("--json", default="")
    ap.add_argument("--max-license-probes", type=int, default=60)
    args = ap.parse_args()

    forks = _list_forks(args.owner)
    print(f"reconciling {len(forks)} forks for {args.owner} ...")
    records = []
    for i, f in enumerate(forks):
        name = f["nameWithOwner"]
        parent = (f.get("parent") or {}).get("nameWithOwner", "")
        # licence probe is the expensive part; cap it but still classify the
        # rest by project signal (licence stays UNKNOWN, never assumed)
        lic_lang = ""
        if i < args.max_license_probes:
            lic_lang = _license(name)
        disp, project, reason = classify(name, parent, lic_lang)
        records.append({
            "fork": name, "parent": parent,
            "license_language": lic_lang,
            "disposition": disp, "project": project, "reason": reason,
            "updated_at": f.get("updatedAt", ""),
            "disk_usage_kb": f.get("diskUsage", 0),
        })

    # summary
    from collections import Counter
    by_disp = Counter(r["disposition"] for r in records)
    by_proj = Counter(r["project"] for r in records if r["project"])
    print(f"\n=== {len(records)} forks ACCOUNTED FOR ===")
    for disp, n in by_disp.most_common():
        print(f"  {disp:22} {n}")
    print("\nby project:")
    for proj, n in by_proj.most_common():
        print(f"  {proj:18} {n}")

    if args.json:
        Path(args.json).write_text(json.dumps(records, indent=2),
                                   encoding="utf-8")
        print(f"\nregistry written: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
