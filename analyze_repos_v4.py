import json, os

# Read the repos file - it's UTF-16 LE with BOM
with open(r"E:\OpenCode-Data\Repository-Governance\github_repos.txt", "r", encoding="utf-16") as f:
    content = f.read()

# Parse the repos
repos = []
for line in content.split('\n'):
    if not line.strip():
        continue
    tab_count = line.count('\t')
    
    if tab_count >= 3:
        parts = line.split('\t')
        name = parts[0].strip()
        
        if tab_count == 3:
            description = parts[1].strip() if len(parts) > 1 else ""
            visibility_fork = parts[2].strip() if len(parts) > 2 else ""
            date = parts[3].strip() if len(parts) > 3 else ""
        elif tab_count == 4:
            description = parts[1].strip() if len(parts) > 1 else ""
            visibility_fork = parts[2].strip() if len(parts) > 2 else ""
            date = parts[4].strip() if len(parts) > 4 else parts[3].strip() if len(parts) > 3 else ""
        else:
            continue
        
        visibility_fork = visibility_fork.strip()
        
        if visibility_fork.startswith("public"):
            visibility = "public"
        elif visibility_fork.startswith("private"):
            visibility = "private"
        else:
            visibility = "unknown"
        
        fork_status = "fork" in visibility_fork.lower()
        date = date.strip()
        description = parts[1].strip() if tab_count >= 3 else ""
        
        repos.append({
            "name": name,
            "description": description,
            "visibility": visibility,
            "fork": fork_status,
            "date": date
        })
    else:
        pass  # skip lines with fewer tabs

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
for f in other_forks[:60]:
    print(f"  {f['name']} - {f['visibility']} - {f['date']}")
print(f"  ... and {len(other_forks)-60} more")

print(f"\n" + "=" * 70)
print("STANDALONE NON-FORK REPOS ({}):".format(len(standalone_non_fork)))
print("=" * 70)
shown = 0
for s in standalone_non_fork:
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
    if not is_obvious and shown < 60:
        desc_preview = s["description"][:50] if s["description"] else ""
        print(f"  {s['name']} - {s['visibility']} - {s['date']}")
        if desc_preview:
            print(f"    desc: {desc_preview}")
        shown += 1
if shown >= len(standalone_non_fork) and len(standalone_non_fork) > 0:
    print(f"  (all {shown} repos shown)")

output = {
    "personal_projects": [{"name": p["name"], "visibility": p["visibility"], "fork": p["fork"], "date": p["date"], "description": p["description"]} for p in personal_projects],
    "forks": [{"name": f["name"], "visibility": f["visibility"], "fork": f["fork"], "date": f["date"], "description": f["description"]} for f in other_forks],
    "standalone_non_fork": [{"name": s["name"], "visibility": s["visibility"], "fork": s["fork"], "date": s["date"], "description": s["description"]} for s in standalone_non_fork]
}

with open(r"E:\OpenCode-Data\Repository-Governance\repos_categorization.json", "w") as f:
    json.dump(output, f, indent=2)

total = len(repos)
total_personal = len(personal_projects)
total_forks = len(other_forks)
total_standalone = len(standalone_non_fork)

print(f"\n" + "=" * 70)
print(f"CATALOGUE COMPLETE")
print(f"=" * 70)
print(f"Total repos parsed: {total}")
print(f"Personal projects: {total_personal}")
print(f"Forks (GitHub forks): {total_forks}")
print(f"Standalone non-fork: {total_standalone}")

print(f"\nKey personal repos found:")
for p in personal_projects:
    if p['name'] in ["Agent-Bridge", "IDE-WORKSPACE", "Aetherius-OS", "Aetherius",
                     "Quantum-OS", "MAT", "Universal-Bridge", "Veyra",
                     "THE-ARCHITECTURE-OF-SHADOWS", "genesis-world"]:
        print(f"  *** {p['name']} ***")

print(f"\nCandidate repos from prompt (checking presence):")
candidates = [
    "flatpak", "bubblewrap", "ostree", "theupdateframework", "python-tuf",
    "smithay", "wgpu", "slint", "servo", "lvgl", "NixOS", "fwupd", "wireplumber",
    "ag-ui", "spiffe", "e2b", "infra", "sigstore", "rekor", "docling", "tesseract",
    "tantivy", "apache", "datafusion", "quickwit", "rdkit", "Materials-Consortia",
    "materialsproject", "Signalsmith", "Ardour", "paritytech", "polkadot",
    "actualbudget", "medusa", "mastodon", "discourse", "element", "moodle",
    "optimade", "openhands", "whisper", "open-webui", "sherpa", "transformers",
    "onnx", "safetensors", "cuda", "tf", "tfjs", "bazel", "vcpkg", "opentelemetry",
    "collector", "compose", "renode", "conan", "firecracker", "warpx", "riscv",
    "chisel", "automerge", "A2A", "mem0", "ditto", "sofa", "pcl", "pymatgen",
    "langgraph", "Orekit", "scipy", "tracktion", "tauri", "samtools", "scikit",
    "peft", "pyOCD", "python-sdk", "duckdb", "gdal", "xterm", "buildkit",
    "sleap", "qdrant", "gz-sim", "open-webui", "lammps", "ros2", "pyscf",
    "CRISPResso2", "graphiti", "influxdb", "mediapipe", "openvsx", "agent-framework",
    "phone-harness", "mujoco", "mne", "neo4j", "sofa", "matrix", "scikit-bio",
    "peft", "pyOCD", "python-sdk", "duckdb", "gdal", "xterm", "buildkit",
    "sleap", "qdrant", "gz-sim", "open-webui", "lammps", "ros2", "pyscf",
    "CRISPResso2", "graphiti", "influxdb", "mediapipe", "openvsx", "agent-framework",
    "phone-harness", "mujoco", "mne", "neo4j", "sofa"
]
found_count = 0
for c in candidates:
    found = any(r["name"] == c or (r["description"] and c.lower() in r["description"].lower()) for r in repos)
    if found:
        found_count += 1
print(f"  Found {found_count}/{len(candidates)} candidate repos present")