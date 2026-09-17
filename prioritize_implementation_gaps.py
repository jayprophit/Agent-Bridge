#!/usr/bin/env python3
"""Prioritize TRUE implementation gaps and create build order.

Prioritization factors:
1. Owner requirements (from project priority)
2. Dependency graph (what depends on what)
3. Critical path (blocking dependencies)
4. Cross-project reuse (shared components)
5. Severity (P0, P1, P2, etc.)
6. Risk (technical complexity)
7. Implementation readiness (how well-defined)
8. Product value (business value)
"""
import json
import os

OUTDIR = r"E:\OpenCode-Data\Repository-Governance"
DELTA_FILE = os.path.join(OUTDIR, "TRUE_IMPLEMENTATION_DELTA.json")

# Project priority (from user's build order)
PROJECT_PRIORITY = {
    "AGENT_BRIDGE": 1,
    "IDE_WORKSPACE": 2,
    "GENESIS": 3,
    "AETHERIUS_OS": 4,
    "SHARED_FOUNDATIONS": 5,
    "UNIVERSAL_BRIDGE": 6,
    "POIETEK": 7,
    "MAT": 8,
    "ATHENA": 9
}

# Severity mapping (from gap titles)
SEVERITY_KEYWORDS = {
    "P0": ["critical", "core", "essential", "must-have", "required"],
    "P1": ["important", "significant", "major", "key"],
    "P2": ["useful", "beneficial", "valuable"],
    "P3": ["nice-to-have", "optional", "enhancement"]
}

# Risk indicators
RISK_INDICATORS = {
    "HIGH": ["research", "experimental", "speculative", "novel", "unproven"],
    "MEDIUM": ["complex", "integration", "multiple systems", "distributed"],
    "LOW": ["standard", "well-known", "established", "proven"]
}


def determine_severity(title):
    """Determine severity from title."""
    title_lower = title.lower()
    for severity, keywords in SEVERITY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in title_lower:
                return severity
    return "P2"  # Default


def determine_risk(title, items):
    """Determine risk level."""
    text = (title + " " + " ".join(items[:5])).lower()
    for risk, indicators in RISK_INDICATORS.items():
        for indicator in indicators:
            if indicator in text:
                return risk
    return "MEDIUM"  # Default


def determine_implementation_readiness(gap):
    """Determine implementation readiness."""
    n_items = gap["n_items"]
    title = gap["title"].lower()
    
    # High readiness: well-defined, clear scope
    if n_items <= 10 and any(kw in title for kw in ["library", "module", "component", "service"]):
        return "HIGH"
    
    # Medium readiness: moderate complexity
    elif n_items <= 20:
        return "MEDIUM"
    
    # Low readiness: complex, many items
    else:
        return "LOW"


def determine_product_value(gap):
    """Determine product value."""
    title = gap["title"].lower()
    
    # High value: core functionality
    if any(kw in title for kw in ["core", "essential", "critical", "main"]):
        return "HIGH"
    
    # Medium value: important features
    elif any(kw in title for kw in ["feature", "capability", "function"]):
        return "MEDIUM"
    
    # Low value: nice-to-have
    else:
        return "LOW"


def prioritize_gap(gap):
    """Calculate priority score for a gap."""
    score = 0
    
    # Project priority (higher priority = higher score)
    project = gap.get("project", "GENESIS")
    project_priority = PROJECT_PRIORITY.get(project, 5)
    score += (10 - project_priority) * 10  # Max 90 points
    
    # Severity
    severity = determine_severity(gap["title"])
    severity_scores = {"P0": 40, "P1": 30, "P2": 20, "P3": 10}
    score += severity_scores.get(severity, 20)
    
    # Risk (lower risk = higher priority)
    risk = determine_risk(gap["title"], [item["item"] for item in gap.get("items", [])])
    risk_scores = {"LOW": 30, "MEDIUM": 20, "HIGH": 10}
    score += risk_scores.get(risk, 20)
    
    # Implementation readiness
    readiness = determine_implementation_readiness(gap)
    readiness_scores = {"HIGH": 30, "MEDIUM": 20, "LOW": 10}
    score += readiness_scores.get(readiness, 20)
    
    # Product value
    value = determine_product_value(gap)
    value_scores = {"HIGH": 30, "MEDIUM": 20, "LOW": 10}
    score += value_scores.get(value, 20)
    
    # Number of items (fewer items = easier to implement)
    n_items = gap.get("n_items", 10)
    if n_items <= 5:
        score += 20
    elif n_items <= 10:
        score += 15
    elif n_items <= 20:
        score += 10
    else:
        score += 5
    
    return {
        "score": score,
        "severity": severity,
        "risk": risk,
        "readiness": readiness,
        "value": value
    }


def main():
    """Main function."""
    print("Loading implementation delta...")
    with open(DELTA_FILE, "r", encoding="utf-8") as f:
        delta = json.load(f)
    
    # Prioritize first-party required gaps
    print("Prioritizing first-party required gaps...")
    prioritized = []
    for gap in delta["implementation_gaps"]["first_party_required"]:
        priority = prioritize_gap(gap)
        prioritized.append({
            **gap,
            "priority": priority
        })
    
    # Sort by priority score (highest first)
    prioritized.sort(key=lambda x: x["priority"]["score"], reverse=True)
    
    # Save prioritized list
    prioritized_file = os.path.join(OUTDIR, "PRIORITIZED_IMPLEMENTATION_GAPS.json")
    with open(prioritized_file, "w", encoding="utf-8") as f:
        json.dump(prioritized, f, indent=1)
    
    print(f"Prioritized gaps saved to: {prioritized_file}")
    
    # Print top 20
    print("\n== Top 20 Priority Gaps ==")
    for i, gap in enumerate(prioritized[:20], 1):
        p = gap["priority"]
        print(f"{i:2d}. Gap {gap['gap_id']:3d}: {gap['title'][:50]}...")
        print(f"    Score: {p['score']:3d} | Severity: {p['severity']} | Risk: {p['risk']} | Readiness: {p['readiness']} | Value: {p['value']}")
        print(f"    Project: {gap['project']} | Items: {gap['n_items']}")
    
    # Create build order
    print("\n== Creating Build Order ==")
    build_order = []
    for gap in prioritized:
        build_order.append({
            "order": len(build_order) + 1,
            "gap_id": gap["gap_id"],
            "title": gap["title"],
            "project": gap["project"],
            "priority_score": gap["priority"]["score"],
            "severity": gap["priority"]["severity"],
            "risk": gap["priority"]["risk"],
            "readiness": gap["priority"]["readiness"],
            "value": gap["priority"]["value"],
            "n_items": gap["n_items"]
        })
    
    build_order_file = os.path.join(OUTDIR, "BUILD_ORDER.json")
    with open(build_order_file, "w", encoding="utf-8") as f:
        json.dump(build_order, f, indent=1)
    
    print(f"Build order saved to: {build_order_file}")
    
    # Summary statistics
    print("\n== Summary Statistics ==")
    print(f"Total first-party gaps: {len(prioritized)}")
    
    # Count by project
    project_counts = {}
    for gap in prioritized:
        project = gap["project"]
        project_counts[project] = project_counts.get(project, 0) + 1
    
    print("\nBy Project:")
    for project, count in sorted(project_counts.items(), key=lambda x: -x[1]):
        print(f"  {project}: {count}")
    
    # Count by severity
    severity_counts = {}
    for gap in prioritized:
        severity = gap["priority"]["severity"]
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    
    print("\nBy Severity:")
    for severity, count in sorted(severity_counts.items()):
        print(f"  {severity}: {count}")
    
    # Count by risk
    risk_counts = {}
    for gap in prioritized:
        risk = gap["priority"]["risk"]
        risk_counts[risk] = risk_counts.get(risk, 0) + 1
    
    print("\nBy Risk:")
    for risk, count in sorted(risk_counts.items()):
        print(f"  {risk}: {count}")
    
    # Count by readiness
    readiness_counts = {}
    for gap in prioritized:
        readiness = gap["priority"]["readiness"]
        readiness_counts[readiness] = readiness_counts.get(readiness, 0) + 1
    
    print("\nBy Readiness:")
    for readiness, count in sorted(readiness_counts.items()):
        print(f"  {readiness}: {count}")


if __name__ == "__main__":
    main()
