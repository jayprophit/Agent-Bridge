#!/usr/bin/env python3
"""Analyze NOT_COVERED gaps to determine true implementation requirements.

For each NOT_COVERED gap, determine:
1. Is this genuinely FIRST_PARTY_REPO_REQUIRED?
2. Or is it DEPENDENCY_ONLY?
3. Or FORK_REQUIRED?
4. Or SHARED_COMPONENT?
5. Or should it be REJECTED (license/security/obsolete)?
"""
import json
import os

OUTDIR = r"E:\OpenCode-Data\Repository-Governance"
COMPARISON_FILE = os.path.join(OUTDIR, "MASTER_REQUIREMENTS_GITHUB_COMPARISON.json")

# Gaps that are likely dependencies (external software we should use, not build)
DEPENDENCY_CANDIDATES = [
    "networking foundations",
    "web server",
    "database",
    "file system",
    "driver",
    "compiler",
    "runtime",
    "interpreter",
    "virtual machine",
    "container",
    "orchestrator",
    "message queue",
    "cache",
    "search engine",
    "monitoring",
    "logging",
    "authentication",
    "authorization",
    "encryption",
    "compression",
    "serialization",
    "protocol",
    "standard",
    "specification",
    "reference implementation"
]

# Gaps that might be shared components
SHARED_COMPONENT_CANDIDATES = [
    "identity",
    "permissions",
    "storage",
    "sync",
    "observability",
    "plugin sdk",
    "media engine",
    "simulation orchestration",
    "evidence",
    "provenance",
    "model routing",
    "agent protocol",
    "gateway"
]

# Gaps that should be rejected
REJECTION_CANDIDATES = [
    "quantum consciousness",
    "warp drive",
    "antigravity",
    "free energy",
    "cold fusion",
    "perpetual motion",
    "alchemy",
    "astrology",
    "numerology"
]


def analyze_gap(gap):
    """Analyze a single NOT_COVERED gap."""
    title = gap["title"].lower()
    items = [item["item"].lower() for item in gap["items"]]
    
    analysis = {
        "gap_id": gap["gap_id"],
        "title": gap["title"],
        "project": gap["project"],
        "n_items": gap["n_items"],
        "current_status": gap["status"],
        "proposed_status": "NOT_COVERED",
        "proposed_action": "FIRST_PARTY_TRIAGE",
        "evidence": [],
        "reasoning": []
    }
    
    # Check for rejection candidates
    for candidate in REJECTION_CANDIDATES:
        if candidate in title or any(candidate in item for item in items):
            analysis["proposed_status"] = "REJECTED"
            analysis["proposed_action"] = "SKIP"
            analysis["evidence"].append(f"Rejected candidate: {candidate}")
            analysis["reasoning"].append(f"Contains rejected concept: {candidate}")
            return analysis
    
    # Check for dependency candidates
    for candidate in DEPENDENCY_CANDIDATES:
        if candidate in title or any(candidate in item for item in items):
            analysis["proposed_status"] = "DEPENDENCY_ONLY"
            analysis["proposed_action"] = "ADD_DEPENDENCY"
            analysis["evidence"].append(f"Dependency candidate: {candidate}")
            analysis["reasoning"].append(f"Likely external dependency: {candidate}")
            return analysis
    
    # Check for shared component candidates
    for candidate in SHARED_COMPONENT_CANDIDATES:
        if candidate in title or any(candidate in item for item in items):
            analysis["proposed_status"] = "SHARED_COMPONENT"
            analysis["proposed_action"] = "CREATE_SHARED_COMPONENT"
            analysis["evidence"].append(f"Shared component candidate: {candidate}")
            analysis["reasoning"].append(f"Likely shared across projects: {candidate}")
            return analysis
    
    # Check for research-only items
    research_indicators = [
        "research", "theoretical", "experimental", "speculative",
        "hypothesis", "prototype", "proof of concept"
    ]
    for indicator in research_indicators:
        if indicator in title or any(indicator in item for item in items):
            analysis["proposed_status"] = "RESEARCH_ONLY"
            analysis["proposed_action"] = "RESEARCH_LANE"
            analysis["evidence"].append(f"Research indicator: {indicator}")
            analysis["reasoning"].append(f"Research/experimental nature: {indicator}")
            return analysis
    
    # Check for standard/specification
    standard_indicators = [
        "standard", "specification", "protocol", "interface",
        "iso", "ieee", "rfc", "w3c"
    ]
    for indicator in standard_indicators:
        if indicator in title or any(indicator in item for item in items):
            analysis["proposed_status"] = "STANDARD"
            analysis["proposed_action"] = "ADOPT_STANDARD"
            analysis["evidence"].append(f"Standard indicator: {indicator}")
            analysis["reasoning"].append(f"Standard/specification: {indicator}")
            return analysis
    
    # Check for benchmark/dataset
    benchmark_indicators = ["benchmark", "test suite", "evaluation", "metrics"]
    dataset_indicators = ["dataset", "corpus", "training data", "data collection"]
    
    for indicator in benchmark_indicators:
        if indicator in title or any(indicator in item for item in items):
            analysis["proposed_status"] = "BENCHMARK"
            analysis["proposed_action"] = "ADD_BENCHMARK_REF"
            analysis["evidence"].append(f"Benchmark indicator: {indicator}")
            analysis["reasoning"].append(f"Benchmark/test suite: {indicator}")
            return analysis
    
    for indicator in dataset_indicators:
        if indicator in title or any(indicator in item for item in items):
            analysis["proposed_status"] = "DATASET"
            analysis["proposed_action"] = "ADD_DATASET_REF"
            analysis["evidence"].append(f"Dataset indicator: {indicator}")
            analysis["reasoning"].append(f"Dataset/corpus: {indicator}")
            return analysis
    
    # Default to FIRST_PARTY_REPO_REQUIRED
    analysis["proposed_status"] = "FIRST_PARTY_REPO_REQUIRED"
    analysis["proposed_action"] = "BUILD_FIRST_PARTY"
    analysis["evidence"].append("No dependency/shared component/rejection indicators found")
    analysis["reasoning"].append("Genuinely requires first-party implementation")
    
    return analysis


def main():
    """Main function."""
    print("Loading comparison data...")
    with open(COMPARISON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Analyze NOT_COVERED gaps
    not_covered = [row for row in data["rows"] if row["status"] == "NOT_COVERED"]
    print(f"Analyzing {len(not_covered)} NOT_COVERED gaps...")
    
    analyses = []
    for gap in not_covered:
        analysis = analyze_gap(gap)
        analyses.append(analysis)
    
    # Count proposed statuses
    proposed_counts = {}
    for analysis in analyses:
        status = analysis["proposed_status"]
        proposed_counts[status] = proposed_counts.get(status, 0) + 1
    
    print("\n== Proposed Status Counts ==")
    for k, v in sorted(proposed_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    
    # Count proposed actions
    action_counts = {}
    for analysis in analyses:
        action = analysis["proposed_action"]
        action_counts[action] = action_counts.get(action, 0) + 1
    
    print("\n== Proposed Action Counts ==")
    for k, v in sorted(action_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    
    # Save detailed analysis
    analysis_file = os.path.join(OUTDIR, "NOT_COVERED_GAP_ANALYSIS.json")
    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(analyses, f, indent=1)
    
    print(f"\nDetailed analysis saved to: {analysis_file}")
    
    # Show sample analyses
    print("\n== Sample Analyses ==")
    for analysis in analyses[:10]:
        print(f"\nGap {analysis['gap_id']}: {analysis['title'][:50]}...")
        print(f"  Proposed: {analysis['proposed_status']} -> {analysis['proposed_action']}")
        print(f"  Evidence: {analysis['evidence'][:2]}")
        print(f"  Reasoning: {analysis['reasoning'][:2]}")


if __name__ == "__main__":
    main()
