import json, os

# Read the repos file with proper encoding handling
with open(r"E:\OpenCode-Data\Repository-Governance\github_repos.txt", "r", encoding="utf-16") as f:
    content = f.read()

# Parse the repos - format: name description visibility fork date
# Each line has tabs separating fields, but file is UTF-16
repos = []
for line in content.split('\n'):
    if not line.strip():
        continue
    # Remove BOM if present at start of first line
    line = line.strip()
    if not line:
        continue
    parts = line.split('\t')
    if len(parts) >= 5:
        name = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else ""
        visibility_type = parts[2].strip() if len(parts) > 2 else ""
        fork_info = parts[3].strip() if len(parts) > 3 else ""
        date = parts[4].strip() if len(parts) > 4 else ""
        
        # Parse visibility - could be "public" or "private" 
        visibility = visibility_type.split()[0] if visibility_type else "unknown"
        
        # Parse fork status - check for "fork" in the info
        fork_status = "fork" in fork_info.lower()
        
        # Clean date
        date = date.strip()
        
        repos.append({
            "name": name,
            "description": description,
            "visibility": visibility,
            "fork": fork_status,
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
    "agent", "bridge", "IDE", "IDE-WORKSPACE", "model", "coder", "reasoner"
]

personal_projects = []
other_forks = []
standalone_non_fork = []

for r in repos:
    name_lower = r["name"].lower()
    is_personal_name = r["name"] in known_personal_names
    is_personal_desc = any(k in (r["description"] or "").lower() for k in known_personal_keywords_in_desc)
    
    if is_personal_name or is_personal_desc:
        personal_projects.append(r)
    elif r["fork"]:
        other_forks.append(r)
    else:
        standalone_non_fork.append(r)

print("=" * 70)
print("PERSONAL PROJECTS ({}):".format(len(personal_projects)))
print("=" * 70)
for p in personal_projects:
    print(f"  {p['name']} - {p['visibility']} - fork={p['fork']} - {p['date']}")

print(f"\n" + "=" * 70)
print("FORKS ({}):".format(len(other_forks)))
print("=" * 70)
for f in other_forks[:50]:
    print(f"  {f['name']} - {f['visibility']} - {f['date']}")
print(f"  ... and {len(other_forks)-50} more")

print(f"\n" + "=" * 70)
print("STANDALONE NON-FORK REPOS ({}):".format(len(standalone_non_fork)))
print("=" * 70)
shown = 0
for s in standalone_non_fork:
    # Only show repos that aren't obviously external tools/infrastructure
    obvious_external = ["flatpak", "bubblewrap", "ostree", "tuf", "smithay", "wgpu",
                        "slint", "servo", "lvgl", "NixOS", "fwupd", "wireplumber",
                        "ag-ui", "spire", "docling", "tika", "pandoc", "tesseract",
                        "tantivy", "fulcio", "rekor", "syft", "trivy", "cosign",
                        "in-toto", "actualbudget", "medusa", "mastodon", "discourse",
                        "element", "moodle", "optimade", "deep_research", "openhands",
                        "whisper", "open-webui", "sherpa", "transformers", "onnx",
                        "safetensors", "cuda", "tf", "tfjs", "pex", "babel",
                        "colmap", "zephyr", "px4", "ifc", "pipewire", "ag", "ui-protocol",
                        "spiffe", "mcp", "context", "registry", "e2b", "infra", "otel",
                        "collector", "quickwit", "datafusion", "pop-os", "cosmic",
                        "screen", "window", "window-manager", "window-management",
                        "visual", "avatar", "Aetherius", "Genesis", "MAT", "Poietek",
                        "Universal", "Bridge", "DAW", "Veyra", "Signalsmith",
                        "signalsmith-stretch", "Ardour"]
    is_obvious = s["name"].lower() in [x.lower() for x in obvious_external]
    if not is_obvious and shown < 50:
        print(f"  {s['name']} - {s['visibility']} - {s['date']}")
        shown += 1
if shown >= len(standalone_non_fork) and len(standalone_non_fork) > 0:
    print(f"  (all {shown} repos shown)")
elif len(standalone_non_fork) == 0:
    print(f"  (no standalone non-fork repos found)")

# Save categorization
output = {
    "personal_projects": [{"name": p["name"], "visibility": p["visibility"], "fork": p["fork"], "date": p["date"]} for p in personal_projects],
    "forks": [{"name": f["name"], "visibility": f["visibility"], "fork": f["fork"], "date": f["date"]} for f in other_forks],
    "standalone_non_fork": [{"name": s["name"], "visibility": s["visibility"], "fork": s["fork"], "date": s["date"]} for s in standalone_non_fork]
}

with open(r"E:\OpenCode-Data\Repository-Governance\repos_categorization.json", "w") as f:
    json.dump(output, f, indent=2)

total = len(repos)
print(f"\n" + "=" * 70)
print(f"CATALOGUE COMPLETE")
print(f"=" * 70)
print(f"Total repos parsed: {total}")
print(f"Personal projects: {len(personal_projects)}")
print(f"Forks (GitHub forks): {len(other_forks)}")
print(f"Standalone non-fork: {len(standalone_non_fork)}")

print(f"\nKey personal repos found:")
for p in personal_projects:
    if p['name'] in ["Agent-Bridge", "IDE-WORKSPACE", "Aetherius-OS", "Aetherius",
                     "Quantum-OS", "MAT", "Universal-Bridge", "Veyra",
                     "THE-ARCHITECTURE-OF-SHADOWS", "genesis-world"]:
        print(f"  *** {p['name']} ***")