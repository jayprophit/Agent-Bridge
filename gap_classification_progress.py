#!/usr/bin/env python3
"""Track progress of gap classification across all 1,040 gaps.

Tracks:
- TOTAL_GAPS = 1040
- PROCESSED
- FULLY_COVERED
- PARTIALLY_COVERED
- NOT_COVERED
- RESEARCH_ONLY
- STANDARD
- DATASET
- BENCHMARK
- DEPENDENCY_ONLY
- FORK_REQUIRED
- FIRST_PARTY_REQUIRED
- SHARED_COMPONENT
- REJECTED
- UNRESOLVED
"""
import json
import os

OUTDIR = r"E:\OpenCode-Data\Repository-Governance"
PROGRESS_FILE = os.path.join(OUTDIR, "GAP_CLASSIFICATION_PROGRESS.json")

# All valid classification categories
VALID_CATEGORIES = {
    "ALREADY_OWNED",
    "EXISTING_CANONICAL",
    "EXISTING_FORK",
    "CAPABILITY_ALREADY_COVERED",
    "PARTIALLY_COVERED",
    "MOSTLY_COVERED",
    "DUPLICATE",
    "SUPERSEDED",
    "NEWER_SUCCESSOR_AVAILABLE",
    "SHARED_COMPONENT",
    "DEPENDENCY_ONLY",
    "PLUGIN",
    "EXTENSION",
    "SDK",
    "API_SERVICE",
    "STANDARD",
    "SPECIFICATION_SOURCE",
    "DATASET",
    "BENCHMARK",
    "REFERENCE_IMPLEMENTATION",
    "ARCHITECTURAL_REFERENCE",
    "ALGORITHM_REFERENCE",
    "CLEAN_ROOM_REFERENCE",
    "RESEARCH_ONLY",
    "EXPERIMENTAL",
    "SIMULATION_ONLY",
    "FIRST_PARTY_REPO_REQUIRED",
    "FORK_REQUIRED",
    "REJECTED_LICENSE",
    "REJECTED_SECURITY",
    "REJECTED_OBSOLETE",
    "NOT_APPLICABLE",
    "NOT_COVERED"
}

# Categories that require action
ACTION_CATEGORIES = {
    "FIRST_PARTY_REPO_REQUIRED": "Build new first-party component",
    "FORK_REQUIRED": "Fork external project",
    "SHARED_COMPONENT": "Create shared component",
    "NOT_COVERED": "Triage for first-party or dependency"
}

# Categories that are informational
INFO_CATEGORIES = {
    "ALREADY_OWNED": "We already have this",
    "EXISTING_CANONICAL": "We have canonical repo",
    "EXISTING_FORK": "We have fork",
    "CAPABILITY_ALREADY_COVERED": "Multiple repos provide this",
    "DUPLICATE": "Duplicate of another gap",
    "SUPERSEDED": "Outdated, newer version available",
    "NEWER_SUCCESSOR_AVAILABLE": "Better alternative exists",
    "DEPENDENCY_ONLY": "External dependency",
    "PLUGIN": "Plugin/extension",
    "EXTENSION": "Extension of existing capability",
    "SDK": "Software development kit",
    "API_SERVICE": "API/service interface",
    "STANDARD": "Specification/standard",
    "SPECIFICATION_SOURCE": "Source of specifications",
    "DATASET": "Data collection",
    "BENCHMARK": "Test suite/benchmark",
    "REFERENCE_IMPLEMENTATION": "Reference implementation",
    "ARCHITECTURAL_REFERENCE": "Architectural reference",
    "ALGORITHM_REFERENCE": "Algorithm reference",
    "CLEAN_ROOM_REFERENCE": "Clean room implementation reference",
    "RESEARCH_ONLY": "Research/theoretical only",
    "EXPERIMENTAL": "Experimental/prototype",
    "SIMULATION_ONLY": "Simulation only",
    "REJECTED_LICENSE": "Cannot use due to license",
    "REJECTED_SECURITY": "Cannot use due to security concerns",
    "REJECTED_OBSOLETE": "Obsolete/abandoned",
    "NOT_APPLICABLE": "Not applicable to our system"
}


def load_progress():
    """Load existing progress."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_progress(progress):
    """Save progress."""
    os.makedirs(OUTDIR, exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=1)


def initialize_progress():
    """Initialize progress tracker."""
    return {
        "total_gaps": 1040,
        "processed": 0,
        "missing_from_source": 80,  # 801-880 missing
        "classifications": {},
        "next_actions": {},
        "projects": {},
        "coverage_stats": {
            "fully_covered": 0,
            "partially_covered": 0,
            "not_covered": 0,
            "research_only": 0,
            "standard": 0,
            "dataset": 0,
            "benchmark": 0,
            "dependency_only": 0,
            "fork_required": 0,
            "first_party_required": 0,
            "shared_component": 0,
            "rejected": 0,
            "unresolved": 0
        },
        "missing_gaps": list(range(801, 881)),  # 801-880
        "processed_gaps": []
    }


def update_progress_from_comparison(progress):
    """Update progress from comparison results."""
    comparison_file = os.path.join(OUTDIR, "MASTER_REQUIREMENTS_GITHUB_COMPARISON.json")
    if not os.path.exists(comparison_file):
        return progress
    
    with open(comparison_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    progress["processed"] = len(data["rows"])
    progress["processed_gaps"] = [r["gap_id"] for r in data["rows"]]
    
    # Reset counts to avoid double-counting
    progress["classifications"] = {}
    progress["next_actions"] = {}
    progress["projects"] = {}
    progress["coverage_stats"] = {
        "fully_covered": 0,
        "partially_covered": 0,
        "not_covered": 0,
        "research_only": 0,
        "standard": 0,
        "dataset": 0,
        "benchmark": 0,
        "dependency_only": 0,
        "fork_required": 0,
        "first_party_required": 0,
        "shared_component": 0,
        "rejected": 0,
        "unresolved": 0
    }
    
    # Count classifications from comparison
    for row in data["rows"]:
        status = row["status"]
        progress["classifications"][status] = progress["classifications"].get(status, 0) + 1
        
        next_action = row["next_action"]
        progress["next_actions"][next_action] = progress["next_actions"].get(next_action, 0) + 1
        
        project = row["project"]
        progress["projects"][project] = progress["projects"].get(project, 0) + 1
        
        # Update coverage stats from comparison
        if status == "MOSTLY_COVERED":
            progress["coverage_stats"]["fully_covered"] += 1
        elif status == "PARTIALLY_COVERED":
            progress["coverage_stats"]["partially_covered"] += 1
        elif status == "NOT_COVERED":
            progress["coverage_stats"]["not_covered"] += 1
        elif status == "RESEARCH_ONLY":
            progress["coverage_stats"]["research_only"] += 1
        elif status == "STANDARD":
            progress["coverage_stats"]["standard"] += 1
        elif status == "DATASET":
            progress["coverage_stats"]["dataset"] += 1
        elif status == "BENCHMARK":
            progress["coverage_stats"]["benchmark"] += 1
        elif status == "DEPENDENCY_ONLY":
            progress["coverage_stats"]["dependency_only"] += 1
        elif status == "FIRST_PARTY_REPO_REQUIRED":
            progress["coverage_stats"]["first_party_required"] += 1
        elif status == "FORK_REQUIRED":
            progress["coverage_stats"]["fork_required"] += 1
        elif status == "SHARED_COMPONENT":
            progress["coverage_stats"]["shared_component"] += 1
        elif status in ("REJECTED_LICENSE", "REJECTED_SECURITY", "REJECTED_OBSOLETE"):
            progress["coverage_stats"]["rejected"] += 1
    
    return progress


def generate_implementation_delta(progress):
    """Generate the true implementation delta."""
    delta = {
        "summary": {
            "total_gaps": progress["total_gaps"],
            "processed": progress["processed"],
            "missing_from_source": progress["missing_from_source"],
            "remaining": progress["total_gaps"] - progress["processed"]
        },
        "coverage_summary": progress["coverage_stats"],
        "next_action_summary": progress["next_actions"],
        "project_distribution": progress["projects"],
        "implementation_gaps": {
            "first_party_required": [],
            "fork_required": [],
            "shared_component": [],
            "dependency_gaps": [],
            "integration_gaps": []
        }
    }
    
    # Load comparison data to get details
    comparison_file = os.path.join(OUTDIR, "MASTER_REQUIREMENTS_GITHUB_COMPARISON.json")
    if os.path.exists(comparison_file):
        with open(comparison_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Load NOT_COVERED analysis
        analysis_file = os.path.join(OUTDIR, "NOT_COVERED_GAP_ANALYSIS.json")
        analyses = {}
        if os.path.exists(analysis_file):
            with open(analysis_file, "r", encoding="utf-8") as f:
                for a in json.load(f):
                    analyses[a["gap_id"]] = a
        
        for row in data["rows"]:
            gap_id = row["gap_id"]
            
            # Use refined analysis if available
            if gap_id in analyses:
                analysis = analyses[gap_id]
                proposed_status = analysis["proposed_status"]
                
                if proposed_status == "FIRST_PARTY_REPO_REQUIRED":
                    delta["implementation_gaps"]["first_party_required"].append({
                        "gap_id": gap_id,
                        "title": row["title"],
                        "project": row["project"],
                        "n_items": row["n_items"],
                        "evidence": analysis["evidence"],
                        "reasoning": analysis["reasoning"]
                    })
                elif proposed_status == "SHARED_COMPONENT":
                    delta["implementation_gaps"]["shared_component"].append({
                        "gap_id": gap_id,
                        "title": row["title"],
                        "project": row["project"],
                        "n_items": row["n_items"],
                        "evidence": analysis["evidence"],
                        "reasoning": analysis["reasoning"]
                    })
                elif proposed_status == "DEPENDENCY_ONLY":
                    delta["implementation_gaps"]["dependency_gaps"].append({
                        "gap_id": gap_id,
                        "title": row["title"],
                        "project": row["project"],
                        "n_items": row["n_items"],
                        "evidence": analysis["evidence"],
                        "reasoning": analysis["reasoning"]
                    })
            else:
                # Use original classification
                if row["next_action"] == "FIRST_PARTY_TRIAGE":
                    delta["implementation_gaps"]["first_party_required"].append({
                        "gap_id": gap_id,
                        "title": row["title"],
                        "project": row["project"],
                        "n_items": row["n_items"],
                        "evidence": row["evidence"]
                    })
                elif row["next_action"] == "FORK_REQUIRED":
                    delta["implementation_gaps"]["fork_required"].append({
                        "gap_id": gap_id,
                        "title": row["title"],
                        "project": row["project"],
                        "n_items": row["n_items"],
                        "evidence": row["evidence"]
                    })
                elif row["next_action"] == "SHARED_COMPONENT":
                    delta["implementation_gaps"]["shared_component"].append({
                        "gap_id": gap_id,
                        "title": row["title"],
                        "project": row["project"],
                        "n_items": row["n_items"],
                        "evidence": row["evidence"]
                    })
    
    return delta


def main():
    """Main function."""
    print("Loading progress...")
    progress = load_progress()
    if not progress:
        print("Initializing new progress tracker...")
        progress = initialize_progress()
    
    print("Updating progress from comparison...")
    progress = update_progress_from_comparison(progress)
    
    # Load NOT_COVERED analysis to refine classifications
    analysis_file = os.path.join(OUTDIR, "NOT_COVERED_GAP_ANALYSIS.json")
    if os.path.exists(analysis_file):
        print("Loading NOT_COVERED analysis to refine classifications...")
        with open(analysis_file, "r", encoding="utf-8") as f:
            analyses = json.load(f)
        
        # Update coverage stats based on analysis (replace NOT_COVERED with refined categories)
        refined_counts = {}
        for analysis in analyses:
            proposed_status = analysis["proposed_status"]
            refined_counts[proposed_status] = refined_counts.get(proposed_status, 0) + 1
        
        # Replace NOT_COVERED count with refined counts
        if "not_covered" in progress["coverage_stats"]:
            del progress["coverage_stats"]["not_covered"]
        
        # Add refined counts
        for status, count in refined_counts.items():
            if status == "FIRST_PARTY_REPO_REQUIRED":
                progress["coverage_stats"]["first_party_required"] = count
            elif status == "SHARED_COMPONENT":
                progress["coverage_stats"]["shared_component"] = count
            elif status == "DEPENDENCY_ONLY":
                progress["coverage_stats"]["dependency_only"] = count
            elif status == "RESEARCH_ONLY":
                progress["coverage_stats"]["research_only"] += count  # Add to existing
            elif status == "STANDARD":
                progress["coverage_stats"]["standard"] += count  # Add to existing
            elif status == "BENCHMARK":
                progress["coverage_stats"]["benchmark"] += count  # Add to existing
            elif status == "DATASET":
                progress["coverage_stats"]["dataset"] += count  # Add to existing
            elif status == "REJECTED":
                progress["coverage_stats"]["rejected"] = count
    
    print("Saving progress...")
    save_progress(progress)
    
    print("\n== Progress Summary ==")
    print(f"Total gaps: {progress['total_gaps']}")
    print(f"Processed: {progress['processed']}")
    print(f"Missing from source: {progress['missing_from_source']}")
    print(f"Remaining: {progress['total_gaps'] - progress['processed']}")
    
    print("\n== Coverage Stats ==")
    for k, v in sorted(progress["coverage_stats"].items()):
        print(f"  {k}: {v}")
    
    print("\n== Next Actions ==")
    for k, v in sorted(progress["next_actions"].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    
    print("\n== Project Distribution ==")
    for k, v in sorted(progress["projects"].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    
    # Generate implementation delta
    print("\nGenerating implementation delta...")
    delta = generate_implementation_delta(progress)
    
    delta_file = os.path.join(OUTDIR, "TRUE_IMPLEMENTATION_DELTA.json")
    with open(delta_file, "w", encoding="utf-8") as f:
        json.dump(delta, f, indent=1)
    
    print(f"Implementation delta saved to: {delta_file}")
    
    print("\n== Implementation Gaps ==")
    for gap_type, gaps in delta["implementation_gaps"].items():
        print(f"  {gap_type}: {len(gaps)}")
        for gap in gaps[:5]:  # Show first 5
            print(f"    - {gap['gap_id']}: {gap['title'][:50]}...")
        if len(gaps) > 5:
            print(f"    ... and {len(gaps) - 5} more")


if __name__ == "__main__":
    main()
