import json, os

# Read the repos file
with open(r"E:\OpenCode-Data\Repository-Governance\github_repos.txt", "r") as f:
    content = f.read()

# Parse the repos - each line is: name description public/fork date
repos = []
for line in content.strip().split('\n'):
    parts = line.split('\t')
    if len(parts) >= 3:
        name = parts[0]
        desc = parts[1] if len(parts) > 1 else ""
        visibility = parts[2] if len(parts) > 2 else "unknown"
        fork_marker = parts[3] if len(parts) > 3 else ""
        date = parts[4] if len(parts) > 4 else ""
        repos.append({
            "name": name,
            "description": desc,
            "visibility": visibility,
            "fork": "true" in fork_marker.lower(),
            "date": date
        })

# Known personal project names
known_personal_names = [
    "Agent-Bridge", "IDE-WORKSPACE", "Aetherius-OS", "Aetherius", "Quantum-OS",
    "aetherial-platform", "genesis-world", "MAT", "Universal-Bridge", "Veyra",
    "THE-ARCHITECTURE-OF-SHADOWS", "profile", "learning"
]

known_personal_keywords_in_desc = [
    "MAT", "Poietek", "Universal-Bridge", "Veyra", "architecture", "genesis",
    "agent", "bridge", "IDE", "IDE-WORKSPACE"
]

personal_projects = []
other_forks = []
standalone_repos = []

for r in repos:
    name_lower = r["name"].lower()
    is_personal_name = r["name"] in known_personal_names
    is_personal_desc = any(k in (r["description"] or "").lower() for k in known_personal_keywords_in_desc)
    
    if is_personal_name or is_personal_desc:
        personal_projects.append(r)
    elif r["fork"]:
        other_forks.append(r)
    else:
        standalone_repos.append(r)

print(f"=" * 60)
print(f"PERSONAL PROJECTS ({len(personal_projects)}):")
print(f"=" * 60)
for p in personal_projects:
    print(f"  {p['name']} - {p['visibility']} - fork={p['fork']} - {p['date']}")

print(f"\n" + "=" * 60)
print(f"FORKS ({len(other_forks)}):")
print(f"=" * 60)
for f in other_forks[:30]:
    print(f"  {f['name']} - {f['visibility']} - {f['date']}")
print(f"  ... and {len(other_forks)-30} more")

print(f"\n" + "=" * 60)
print(f"STANDALONE REPOS (not fork, not personal-name) ({len(standalone_repos)}):")
print(f"=" * 60)
for s in standalone_repos[:30]:
    print(f"  {s['name']} - {s['visibility']} - {s['date']}")
print(f"  ... and {len(standalone_repos)-30} more")

# Check for specific known repos
print(f"\n" + "=" * 60)
print(f"SPECIFIC REPO CHECKS:")
print(f"=" * 60)
specific_checks = ["Agent-Bridge", "IDE-WORKSPACE", "Aetherius-OS", "Aetherius", 
                   "Quantum-OS", "MAT", "Universal-Bridge", "Veyra",
                   "THE-ARCHITECTURE-OF-SHADOWS", "genesis-world",
                   "flatpak", "bubblewrap", "ow", "ostree", "tuf", "smithay", "wgpu",
                   "slint", "servo", "lvgl", "NixOS", "fwupd", "wireplumber", "ag-ui",
                   "spire", "docling", "tika", "pandoc", "tesseract", "tantivy",
                   "signalfx", "fulcio", "rekor", "syft", "trivy", "cosign", "in-toto",
                   "open-webui", "ollama", "qdrant", "llama_cpp", "llama_index",
                   "pop-os", "cosmic", "lvgl", "neo4j", "langgraph", "sigstore",
                   "polkadot", "actualbudget", "medusa", "mastodon", "discourse",
                   "element", "moodle", "optimade", "pyopen", "deep_research",
                   "openhands", "whisper", "open-webui", "sherpa", "transformers",
                   "onnx", "safetensors", "cuda", "tf", "tfjs", "pex", "babel",
                   "colmap", "zephyr", "px4", "ifc", "pipewire", "ag", "ui-protocol",
                   "spiffe", "mcp", "context", "registry", "e2b", "infra", "otel",
                   "collector", "docling", "quickwit", "datafusion", "pop-os", "cosmic",
                   "screen", "window", "window-manager", "window-management",
                   "visual", "avatar", "Aetherius", "Genesis", "MAT", "Poietek",
                   "Universal", "Bridge", "DAW", "Veyra", "Signalsmith", "signalsmith",
                   "Ardour", "signalsmith-stretch"]
check_found = 0
check_total = len(specific_checks)
for check in specific_checks:
    found = any(r["name"] == check or r["description"] and check.lower() in (r["description"] or "").lower() for r in repos)
    if found:
        check_found += 1
print(f"  Found {check_found}/{check_total} specific repos checked")

# Save categorization
output = {
    "personal_projects": [{"name": p["name"], "visibility": p["visibility"], "fork": p["fork"], "date": p["date"]} for p in personal_projects],
    "forks": [{"name": f["name"], "visibility": f["visibility"], "fork": f["fork"], "date": f["date"]} for f in other_forks],
    "standalone": [{"name": s["name"], "visibility": s["visibility"], "fork": s["fork"], "date": s["date"]} for s in standalone_repos]
}

with open(r"E:\OpenCode-Data\Repository-Governance\repos_categorization.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\n" + "=" * 60)
print(f"CATALOGUE SAVED")
print(f"=" * 60)
print(f"Personal: {len(personal_projects)}, Forks: {len(other_forks)}, Standalone: {len(standalone_repos)}")