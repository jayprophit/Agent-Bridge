"""MATERIALS-ATLAS-TABLE-CODEX (MAT) FORK MIGRATION CATALOG

Repository: jayprophit/Materials-Atlas-Table-Codex---MAT
Spec refs: Documents/aetherius hybrid cloud.txt §55, §119;
          Knowledge Fabric addendum §20-22; Repository Policy §4-5

RECONCILIATION
==============

Only ONE MAT repository exists in the jayprophit account:

  jayprophit/Materials-Atlas-Table-Codex---MAT

The alternate name "Materials-Atlas-Table-Codex-MAT" (without triple-dash)
does NOT exist. No fork/predecessor/sibling MAT repositories were found.

DECISION: EXTEND_CANONICAL

The existing repository is the canonical MAT home. No new MAT repository
should be created.

Classification of all 17 jayprophit repositories:
"""

FORK_MIGRATION_CATALOG = {
    "Materials-Atlas-Table-Codex---MAT": {
        "repo_url": "https://github.com/jayprophit/Materials-Atlas-Table-Codex---MAT",
        "classification": "ACTIVE_CANONICAL",
        "project": "MAT",
        "decision": "EXTEND_CANONICAL",
        "notes": "Canonical MAT repository. Only one exists. Extend, do not duplicate.",
        "mat_status": "CANONICAL_OWNER",
    },
    "Agent-Bridge": {
        "repo_url": "https://github.com/jayprophit/Agent-Bridge",
        "classification": "ACTIVE_CANONICAL",
        "project": "Genesis / Hybrid Cloud",
        "decision": "EXTEND_CANONICAL",
        "notes": "Current working repository for Hybrid Cloud + Knowledge Fabric + Enterprise Team.",
        "mat_status": "NOT_MAT",
    },
    "Aetherius-OS": {
        "repo_url": "https://github.com/jayprophit/Aetherius-OS",
        "classification": "ACTIVE_CANONICAL",
        "project": "Aetherius OS",
        "decision": "EXTEND_CANONICAL",
        "mat_status": "NOT_MAT",
    },
    "Genesis": {
        "repo_url": "https://github.com/jayprophit/Genesis",
        "classification": "ACTIVE_CANONICAL",
        "project": "Genesis",
        "decision": "EXTEND_CANONICAL",
        "mat_status": "NOT_MAT",
    },
    "IDE-Workspace": {
        "repo_url": "https://github.com/jayprophit/IDE-Workspace",
        "classification": "ACTIVE_SUPPORTING",
        "project": "IDE Workspace",
        "decision": "REUSE",
        "mat_status": "NOT_MAT",
    },
    "Universal-Bridge": {
        "repo_url": "https://github.com/jayprophit/Universal-Bridge",
        "classification": "ACTIVE_SUPPORTING",
        "project": "Universal Bridge",
        "decision": "REUSE",
        "mat_status": "NOT_MAT",
    },
    "Niche_platform": {
        "repo_url": "https://github.com/jayprophit/Niche_platform",
        "classification": "UNKNOWN",
        "project": "Unknown",
        "decision": "REVIEW_REQUIRED",
        "mat_status": "NOT_MAT",
    },
    "self-building-ai": {
        "repo_url": "https://github.com/jayprophit/self-building-ai",
        "classification": "EXPERIMENT",
        "project": "Research",
        "decision": "REFERENCE_ONLY",
        "mat_status": "NOT_MAT",
    },
    "Poietek": {
        "repo_url": "https://github.com/jayprophit/Poietek",
        "classification": "FORK",
        "project": "Poietek",
        "decision": "FORK_UPSTREAM_DERIVED",
        "mat_status": "NOT_MAT",
    },
    "ComfyUI": {
        "repo_url": "https://github.com/jayprophit/ComfyUI",
        "classification": "FORK",
        "project": "ComfyUI",
        "decision": "TEMPORARY_FORK_BASE",
        "mat_status": "POTENTIAL_DEPENDENCY",
    },
    "colmap": {
        "repo_url": "https://github.com/jayprophit/colmap",
        "classification": "FORK",
        "project": "COLMAP",
        "decision": "DEPENDENCY",
        "mat_status": "POTENTIAL_DEPENDENCY",
    },
    "OpenROAD": {
        "repo_url": "https://github.com/jayprophit/OpenROAD",
        "classification": "FORK",
        "project": "OpenROAD",
        "decision": "DEPENDENCY",
        "mat_status": "POTENTIAL_DEPENDENCY",
    },
    "godot-official": {
        "repo_url": "https://github.com/jayprophit/godot-official",
        "classification": "FORK",
        "project": "Godot",
        "decision": "REFERENCE_ONLY",
        "mat_status": "POTENTIAL_DEPENDENCY",
    },
    "openscad": {
        "repo_url": "https://github.com/jayprophit/openscad",
        "classification": "FORK",
        "project": "OpenSCAD",
        "decision": "ALGORITHM_REFERENCE",
        "mat_status": "POTENTIAL_DEPENDENCY",
    },
    "FreeCAD": {
        "repo_url": "https://github.com/jayprophit/FreeCAD",
        "classification": "FORK",
        "project": "FreeCAD",
        "decision": "REFERENCE_ONLY",
        "mat_status": "POTENTIAL_DEPENDENCY",
    },
    "blender": {
        "repo_url": "https://github.com/jayprophit/blender",
        "classification": "FORK",
        "project": "Blender",
        "decision": "REFERENCE_ONLY",
        "mat_status": "NOT_MAT",
    },
    "kicad-source-mirror": {
        "repo_url": "https://github.com/jayprophit/kicad-source-mirror",
        "classification": "FORK",
        "project": "KiCad",
        "decision": "REFERENCE_ONLY",
        "mat_status": "NOT_MAT",
    },
}

MAT_CANONICAL_REPO = "jayprophit/Materials-Atlas-Table-Codex---MAT"
MAT_ALTERNATE_DOES_NOT_EXIST = "jayprophit/Materials-Atlas-Table-Codex-MAT"


def get_repo_classification(repo_name: str) -> str:
    return FORK_MIGRATION_CATALOG.get(repo_name, {}).get("classification", "UNKNOWN")


def get_repo_decision(repo_name: str) -> str:
    return FORK_MIGRATION_CATALOG.get(repo_name, {}).get("decision", "REVIEW_REQUIRED")


def list_mat_repos() -> list[str]:
    return [name for name, info in FORK_MIGRATION_CATALOG.items()
            if info.get("mat_status") != "NOT_MAT"]
