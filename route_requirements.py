#!/usr/bin/env python3
"""Route extracted requirements to appropriate projects and build REQUIREMENT_REGISTRY."""

import json
import hashlib
import os
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Configuration
ANALYSIS_OUTPUT = Path("E:/OpenCode-Data/conversation-analysis")
DATA_ROOT = Path("E:/external drive/ai chat conversations")

# Project keyword mappings for requirement classification
PROJECT_KEYWORDS = {
    "GENESIS": {
        "technical": ["holographic", "3d display", "volumetric", "light field"],
        "system": ["AI agent", "autonomous AI", "coding agent", "framework"],
        "execution": ["cognition", "plan", "execution", "contract"],
        "memory": ["ledger", "memory", "session", "identity"],
    },
    "AGENT_BRIDGE": {
        "agentic": ["agent", "coding", "development", "workflow"],
        "productivity": ["IDE", "prompt", "rule", "cursor"],
        "automation": ["deployment", "CI/CD", "test", "automation"],
    },
    "IDE_WORKSPACE": {
        "interface": ["interface", "UI", "screen", "display"],
        "rendering": ["window", "viewport", "render", "graphics"],
        "visual": ["visual", "layout", "component"],
    },
    "MAT": {
        "modular": ["modular", "task", "workflow", "graph"],
        "dependency": ["dependency", "dag", "graph"],
        "execution": ["execution", "state", "transition"],
    },
    "POIETEK": {
        "audio": ["audio", "daw", "plugin", "effect", "instrument"],
        "music": ["synthesis", "sampler", "midi", "mixing", "mastering"],
        "engine": ["engine", "processor", "effect"],
    },
    "UNIVERSAL_BRIDGE": {
        "integration": ["bridge", "integration", "connect", "bind"],
        "adapter": ["adapter", "link", "interface", "bindings"],
    },
    "ATHENA": {
        "autonomous": ["autonomous", "reasoning", "planning"],
        "cognitive": ["cognitive", "intelligence"],
    },
}

# Project mapping: requirement keywords -> target project
PROJECT_MAPPING = {
    "GENESIS": [
        "holographic", "3d display", "volumetric", "light field",
        "AI agent", "autonomous AI", "coding agent",
        "framework", "model", "neural", "architecture",
        "cognition", "plan", "execution", "contract",
        "ledger", "memory", "session", "identity",
    ],
    "AGENT_BRIDGE": [
        "agent", "coding", "development", "workflow",
        "IDE", "prompt", "rule", "cursor",
        "deployment", "CI/CD", "test", "automation",
    ],
    "IDE_WORKSPACE": [
        "interface", "UI", "screen", "display",
        "window", "viewport", "render", "graphics",
        "visual", "layout", "component",
    ],
    "MAT": [
        "modular", "task", "workflow", "graph",
        "dependency", "dag", "graph",
        "execution", "state", "transition",
    ],
    "POIETEK": [
        "audio", "daw", "plugin", "effect",
        "instrument", "synthesis", "sampler",
        "midi", "mixing", "mastering",
        "engine", "processor", "effect",
    ],
    "UNIVERSAL_BRIDGE": [
        "bridge", "integration", "connect", "bind",
        "adapter", "link", "interface", "bindings",
    ],
    "ATHENA": [
        "autonomous", "reasoning", "planning",
        "decision", "cognitive", "intelligence",
    ],
}


def hash_content(content: str) -> str:
    """Compute SHA256 hash of content for stable IDs."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def load_analysis_records() -> dict:
    """Load all analysis records from the three corpus directories."""
    records = {
        "deepseek": [],
        "chatgpt": [],
        "claude": [],
    }

    # Load deepseek records
    deepseek_dir = ANALYSIS_OUTPUT / "deepseek_analysis"
    if deepseek_dir.exists():
        for f in deepseek_dir.glob("deepseek_record_*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    records["deepseek"].append(json.load(fh))
            except Exception as e:
                print(f"  ERROR loading {f}: {e}")

    # Load chatgpt records
    chatgpt_dir = ANALYSIS_OUTPUT / "chatgpt_analysis"
    if chatgpt_dir.exists():
        for f in chatgpt_dir.glob("chatgpt_record_*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    records["chatgpt"].append(json.load(fh))
            except Exception as e:
                print(f"  ERROR loading {f}: {e}")

    # Load claude records
    claude_dir = ANALYSIS_OUTPUT / "claude_analysis"
    if claude_dir.exists():
        for f in claude_dir.glob("claude_record_*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    records["claude"].append(json.load(fh))
            except Exception as e:
                print(f"  ERROR loading {f}: {e}")

    return records


def classify_requirement(req_text: str) -> dict:
    """Classify a requirement into a project and capability category."""
    req_lower = req_text.lower()
    result = {
        "project": "UNKNOWN",
        "capability_category": "general",
        "confidence": 0.0,
        "matched_keywords": [],
    }

    project_scores = {}

    for project, keywords in PROJECT_KEYWORDS.items():
        score = 0
        matched = []

        for category, kws in keywords.items():
            for kw in kws:
                if kw.lower() in req_lower:
                    score += 1
                    matched.append(kw)

        if score > 0:
            project_scores[project] = (score, matched)

    if project_scores:
        best_project = max(project_scores, key=lambda p: project_scores[p][0])
        score, matched = project_scores[best_project]
        result["project"] = best_project
        result["capability_category"] = "technical" if best_project in ["GENESIS", "POIETEK"] else "general"
        result["confidence"] = min(score / 3.0, 1.0)
        result["matched_keywords"] = matched

    return result


def extract_atomic_capability(req_text: str, classification: dict,
                              model: str = "deepseek") -> dict:
    """Extract atomic capability from a requirement.

    model must be the corpus the record was analysed from
    (deepseek|chatgpt|claude); BUG-002 was a hardcoded "deepseek" here
    which misattributed every chatgpt/claude requirement.
    """
    return {
        "capability_id": hash_content(req_text),
        "requirement_text": req_text,
        "project": classification["project"],
        "capability_category": classification["capability_category"],
        "confidence": classification["confidence"],
        "matched_keywords": classification["matched_keywords"],
        "extracted_at": datetime.utcnow().isoformat() + "Z",
        "source": "chat_corpus_analysis",
        "provenance": {
            "model": model,
            "source_file": None,
        },
        "atomic_capability": req_text.strip(),
    }


def route_requirements(analysis_records: dict) -> dict:
    """Route all requirements to target projects and build registry."""
    registry = {
        "requirements": [],
        "capabilities": [],
        "projects": defaultdict(list),
        "statistics": {
            "total_requirements": 0,
            "routed_requirements": 0,
            "by_project": defaultdict(int),
            "by_category": defaultdict(int),
        },
    }

    # Collect all requirements from all records
    all_requirements = []

    for model, records in analysis_records.items():
        for record in records:
            requirements = record.get("requirements", [])
            for req in requirements:
                req_text = req.get("text", "")
                if len(req_text) > 10:
                    classification = classify_requirement(req_text)
                    capability = extract_atomic_capability(req_text, classification, model=model)
                    capability["provenance"]["source_file"] = record.get("filename", "")
                    all_requirements.append(capability)

    registry["statistics"]["total_requirements"] = len(all_requirements)

    # Route each requirement to a project
    print(f"DEBUG: registry stats before loop: {dict(registry['statistics'])}")
    for capability in all_requirements:
        project = capability["project"]
        cap_category = capability["capability_category"]
        print(f"DEBUG: processing capability, project={project}, category={cap_category}")
        print(f"DEBUG: by_project before: {dict(registry['statistics']['by_project'])}")
        print(f"DEBUG: by_category before: {dict(registry['statistics']['by_category'])}")
        registry["statistics"]["by_project"][project] += 1
        registry["statistics"]["by_category"][cap_category] += 1
        print(f"DEBUG: by_project after: {dict(registry['statistics']['by_project'])}")
        registry["projects"][project].append(capability)
        registry["requirements"].append(capability)

    # Build capabilities list (deduplicate by ID)
    seen_ids = set()
    for capability in registry["requirements"]:
        cap_id = capability["capability_id"]
        if cap_id not in seen_ids:
            seen_ids.add(cap_id)
            registry["capabilities"].append(capability)

    registry["statistics"]["routed_requirements"] = len(registry["capabilities"])

    return registry


def cross_reference_with_code_task_graph(registry: dict) -> dict:
    """Cross-reference requirements with current code and task graph."""
    codebase_indicators = {
        "GENESIS": ["cognition", "plan", "execution", "contract", "ledger", "memory"],
        "AGENT_BRIDGE": ["agent", "coding", "deployment", "workflow", "IDE"],
        "IDE_WORKSPACE": ["interface", "UI", "display", "render", "graphics"],
        "MAT": ["modular", "task", "workflow", "graph", "dependency"],
        "POIETEK": ["audio", "daw", "plugin", "effect", "instrument"],
        "UNIVERSAL_BRIDGE": ["bridge", "integration", "connect", "bind"],
        "ATHENA": ["autonomous", "reasoning", "planning"],
    }

    for capability in registry["capabilities"]:
        project = capability["project"]
        cap_text = capability["requirement_text"].lower()

        matched_indicators = []
        for proj, indicators in codebase_indicators.items():
            for indicator in indicators:
                if indicator in cap_text:
                    matched_indicators.append(f"{proj}:{indicator}")

        capability["codebase_cross_reference"] = {
            "matched_indicators": list(set(matched_indicators)),
            "relevance_score": min(len(set(matched_indicators)) / 2.0, 1.0),
        }

    return registry


def build_requirement_registry() -> dict:
    """Build the complete REQUIREMENT_REGISTRY."""
    print("=" * 60)
    print("BUILDING REQUIREMENT REGISTRY")
    print("=" * 60)
    print()

    # Load analysis records
    analysis_records = load_analysis_records()
    print("Loaded analysis records:")
    print(f"  DeepSeek: {len(analysis_records['deepseek'])} record sets")
    print(f"  ChatGPT: {len(analysis_records['chatgpt'])} record sets")
    print(f"  Claude: {len(analysis_records['claude'])} record sets")
    print()

    # Route requirements
    registry = route_requirements(analysis_records)

    print("Routing statistics:")
    print(f"  Total requirements extracted: {registry['statistics']['total_requirements']}")
    print(f"  Unique capabilities registered: {registry['statistics']['routed_requirements']}")
    print()

    # By project
    print("Requirements by project:")
    for project, count in sorted(registry["statistics"]["by_project"].items(),
                                  key=lambda x: x[1], reverse=True):
        print(f"  {project}: {count}")
    print()

    # By category
    print("Requirements by category:")
    for category, count in sorted(registry["statistics"]["by_category"].items(),
                                   key=lambda x: x[1], reverse=True):
        print(f"  {category}: {count}")
    print()

    # Cross-reference with code/task graph
    print("Cross-referencing with code and task graph...")
    registry = cross_reference_with_code_task_graph(registry)

    # Print cross-reference summary (first 5)
    print("Codebase cross-reference summary:")
    counted = 0
    for cap in registry["capabilities"]:
        if cap["codebase_cross_reference"]["matched_indicators"] and counted < 5:
            print(f"  {cap['project']}: {cap['codebase_cross_reference']['matched_indicators'][:3]}")
            counted += 1

    # Save registry
    output_dir = ANALYSIS_OUTPUT / "requirement_registry"
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "requirement_registry.json", "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, default=str)

    # Save per-project files
    for project, capabilities in registry["projects"].items():
        project_dir = output_dir / project.lower()
        project_dir.mkdir(exist_ok=True)

        with open(project_dir / "capabilities.json", "w", encoding="utf-8") as f:
            json.dump(capabilities, f, indent=2, default=str)

    # Save summary
    summary = {
        "total_requirements_extracted": registry["statistics"]["total_requirements"],
        "unique_capabilities_registered": registry["statistics"]["routed_requirements"],
        "by_project": dict(registry["statistics"]["by_project"]),
        "by_category": dict(registry["statistics"]["by_category"]),
        "projects_with_requirements": list(registry["projects"].keys()),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "analyzer_version": "1.0",
    }

    with open(output_dir / "registry_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print()
    print("=" * 60)
    print("REQUIREMENT REGISTRY BUILD COMPLETE")
    print("=" * 60)
    print(f"Output directory: {output_dir}")
    print(f"Total requirements: {registry['statistics']['total_requirements']}")
    print(f"Unique capabilities: {registry['statistics']['routed_requirements']}")
    print(f"Projects: {', '.join(registry['projects'].keys())}")
    print()

    return registry


def main():
    """Main entry point."""
    registry = build_requirement_registry()

    print()
    print("=" * 60)
    print("PROJECT DISTRIBUTION DETAIL")
    print("=" * 60)
    for project, capabilities in sorted(registry["projects"].items(),
                                        key=lambda x: len(x[1]), reverse=True):
        print(f"\n{project} ({len(capabilities)} requirements):")
        for cap in capabilities[:3]:
            cap_text = cap["requirement_text"][:80] + "..." if len(cap["requirement_text"]) > 80 else cap["requirement_text"]
            print(f"  - {cap_text}")
        if len(capabilities) > 3:
            print(f"  ... and {len(capabilities) - 3} more")

    # Save cross-reference data
    cross_ref_path = ANALYSIS_OUTPUT / "requirement_registry" / "code_cross_reference.json"
    with open(cross_ref_path, "w", encoding="utf-8") as f:
        ref_data = [
            {
                "capability_id": c["capability_id"],
                "project": c["project"],
                "matched_indicators": c["codebase_cross_reference"]["matched_indicators"],
                "relevance_score": c["codebase_cross_reference"]["relevance_score"],
            }
            for c in registry["capabilities"]
        ]
        json.dump(ref_data, f, indent=2, default=str)

    print(f"\nCross-reference data saved to: {cross_ref_path}")


if __name__ == "__main__":
    main()