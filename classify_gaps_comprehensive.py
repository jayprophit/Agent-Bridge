#!/usr/bin/env python3
"""Comprehensive gap classification using full category set.

For each of the 1,040 gap families:
1. What capability does this gap represent?
2. Do we already own something that provides it?
3. Do multiple existing repos provide it?
4. Is it already implemented inside an Aetherius first-party repo?
5. Is the existing solution current and maintained?
6. Has it been superseded?
7. Is it a standard rather than software?
8. Is it a dataset rather than software?
9. Is it a benchmark/test suite?
10. Is it research-only?
11. Does it require integration rather than building?
12. Does it require a shared component?
13. Does it genuinely require a new first-party product/component?
14. Does it genuinely require another external fork?
15. What evidence proves coverage?

Classification categories:
- ALREADY_OWNED: We have this capability in our repos
- EXISTING_CANONICAL: We have a canonical (non-fork) repo for this
- EXISTING_FORK: We have a fork of this
- CAPABILITY_ALREADY_COVERED: Multiple repos provide this capability
- PARTIALLY_COVERED: Some but not all aspects are covered
- DUPLICATE: Multiple gaps refer to the same capability
- SUPERSEDED: Our version is outdated, newer version available
- NEWER_SUCCESSOR_AVAILABLE: Better alternative exists
- SHARED_COMPONENT: Multiple projects need this common component
- DEPENDENCY_ONLY: External dependency, not our code
- PLUGIN: Extension/plugin for existing software
- EXTENSION: Extension of existing capability
- SDK: Software development kit
- API_SERVICE: API/service interface
- STANDARD: Specification/standard (not software)
- SPECIFICATION_SOURCE: Source of specifications
- DATASET: Data collection
- BENCHMARK: Test suite/benchmark
- REFERENCE_IMPLEMENTATION: Reference implementation
- ARCHITECTURAL_REFERENCE: Architectural reference
- ALGORITHM_REFERENCE: Algorithm reference
- CLEAN_ROOM_REFERENCE: Clean room implementation reference
- RESEARCH_ONLY: Research/theoretical only
- EXPERIMENTAL: Experimental/prototype
- SIMULATION_ONLY: Simulation only
- FIRST_PARTY_REPO_REQUIRED: Genuinely need new first-party repo
- FORK_REQUIRED: Need to fork external project
- REJECTED_LICENSE: Cannot use due to license
- REJECTED_SECURITY: Cannot use due to security concerns
- REJECTED_OBSOLETE: Obsolete/abandoned
- NOT_APPLICABLE: Not applicable to our system
"""
import json
import re
import os

SRC = r"C:\Users\jpowe\Documents\openCDE-agent\master reequirements.txt"
INV = r"C:\Users\jpowe\Desktop\Agent-Bridge\jayprophit_repository_inventory.json"
OUTDIR = r"E:\OpenCode-Data\Repository-Governance"

# Extended capability equivalence (capability, not name)
EQUIV = {
    # Operating systems
    "fuchsia": ["9front", "redox", "sel4"],
    "zircon": ["9front", "redox", "sel4"],
    "genode": ["sel4"],
    "nixos": ["bootc"],
    "gnu guix": ["bootc"],
    "ostree": ["bootc"],
    "rpm-ostree": ["bootc"],
    "unikraft": ["firecracker", "gvisor"],
    "kata containers": ["firecracker", "gvisor"],
    
    # Agent protocols
    "mcp": ["a2a", "agent-bridge"],
    "model context protocol": ["a2a", "agent-bridge"],
    "agent2agent": ["a2a", "agent-bridge"],
    "a2ui": ["a2a", "agent-bridge"],
    "ag-ui": ["a2a", "agent-bridge"],
    
    # Agent frameworks
    "crewai": ["crewai"],
    "langgraph": ["langgraph"],
    "autogen": ["agent-framework"],
    "autogpt": ["agent-framework"],
    
    # Inference
    "llama.cpp": ["llama.cpp"],
    "llamacpp": ["llama.cpp"],
    "vllm": ["vllm"],
    "tvm": ["tvm"],
    "iree": ["iree"],
    "onnx": ["onnxruntime"],
    "onnx runtime": ["onnxruntime"],
    "executorch": ["executorch"],
    
    # Speech/audio
    "whisper": ["whisper.cpp", "sherpa-onnx"],
    "sherpa": ["sherpa-onnx"],
    "sherpa-onnx": ["sherpa-onnx"],
    "kokoro": ["sherpa-onnx"],
    "piper": ["sherpa-onnx"],
    "rtaudio": ["rtaudio"],
    "csound": ["csound"],
    "supercollider": ["supercollider"],
    "pipewire": ["pipewire"],
    "jack": ["rtaudio"],
    
    # CAD/engineering
    "freecad": ["freecad"],
    "openscad": ["openscad"],
    "cadquery": ["freecad"],
    "build123d": ["freecad"],
    "occt": ["freecad"],
    "opencascade": ["freecad"],
    "kicad": ["kicad-source-mirror"],
    
    # CAE/simulation
    "openfoam": ["su2"],
    "calculix": ["su2", "mfem"],
    "fenics": ["dolfinx"],
    "dolfinx": ["dolfinx"],
    "mfem": ["mfem"],
    "petsc": ["petsc"],
    "moose": ["moose"],
    "su2": ["su2"],
    "sofa": ["sofa"],
    "gazebo": ["gz-sim"],
    "gz-sim": ["gz-sim"],
    "webots": ["webots"],
    "mujoco": ["mujoco"],
    "isaac": ["isaaclab"],
    "isaaclab": ["isaaclab"],
    
    # Robotics
    "ros2": ["ros2"],
    "ros": ["ros2"],
    "navigation2": ["navigation2"],
    "nav2": ["navigation2"],
    "px4": ["px4-autopilot"],
    "ardupilot": ["ardupilot"],
    "mavsdk": ["px4-autopilot", "ardupilot"],
    "lerobot": ["lerobot"],
    "leRobot": ["lerobot"],
    "behaviortree": ["drake"],
    "behavior tree": ["drake"],
    
    # Quantum
    "qiskit": ["qiskit"],
    "pennylane": ["pennylane"],
    "cirq": ["qiskit"],
    "qutip": ["qiskit"],
    
    # Crypto/PQC/FHE
    "openfhe": ["openfhe-development"],
    "tfhe": ["tfhe-rs"],
    
    # Materials/chemistry
    "aiida": ["aiida-core"],
    "pymatgen": ["pymatgen-core"],
    "pyscf": ["pyscf"],
    "openmm": ["openmm"],
    "cantera": ["cantera"],
    "lammps": ["lammps"],
    "quantum espresso": ["pyscf"],
    "gpaW": ["pyscf"],
    
    # Bio
    "gatk": ["gatk"],
    "samtools": ["samtools"],
    "scanpy": ["scanpy"],
    "scikit-bio": ["scikit-bio"],
    "crispresso": ["crispresso2"],
    "nrn": ["nrn"],
    "neuron": ["nrn"],
    "nest": ["nest-simulator"],
    "brian2": ["nest-simulator"],
    "deeplabcut": ["deeplabcut"],
    "sleap": ["sleap"],
    "mne": ["mne-python"],
    "brainflow": ["mne-python"],
    "spikeinterface": ["spikeinterface"],
    
    # Geo/space
    "gdal": ["gdal"],
    "pdal": ["pdal"],
    "cesium": ["cesium"],
    "orekit": ["orekit"],
    "cfs": ["cfs"],
    "satdump": ["satdump"],
    "colmap": ["colmap"],
    "open3d": ["open3d"],
    "pcl": ["pcl"],
    "rtabmap": ["rtabmap"],
    "gtsam": ["gtsam"],
    
    # Media
    "ffmpeg": ["ffmpeg"],
    "gstreamer": ["ffmpeg"],
    "blender": ["blender"],
    "godot": ["godot-official"],
    "c2pa": ["c2pa-rs"],
    
    # Data/infra
    "sqlite": ["sqlite"],
    "postgres": ["timescaledb"],
    "timescaledb": ["timescaledb"],
    "influxdb": ["influxdb"],
    "prometheus": ["prometheus"],
    "grafana": ["grafana"],
    "opentelemetry": ["opentelemetry-collector"],
    "kafka": ["redpanda"],
    "redpanda": ["redpanda"],
    "nats": ["nats-server"],
    "mqtt": ["esphome"],
    "zenoh": ["zenoh"],
    "dds": ["zenoh"],
    "neo4j": ["neo4j"],
    "duckdb": ["duckdb---community"],
    "arrow": ["arrow"],
    
    # Containers/orchestration
    "kubernetes": ["k3s", "helm"],
    "k3s": ["k3s"],
    "helm": ["helm"],
    "containerd": ["containerd"],
    "firecracker": ["firecracker"],
    "gvisor": ["gvisor"],
    "kata": ["firecracker", "gvisor"],
    "moby": ["moby"],
    "docker": ["moby"],
    "temporal": ["temporal"],
    "dagster": ["dagster"],
    "n8n": ["n8n"],
    "ray": ["ray"],
    
    # Edge/IoT
    "esphome": ["esphome"],
    "home assistant": ["core"],
    "matter": ["connectedhomeip"],
    "openthread": ["openthread"],
    "zephyr": ["zephyr"],
    "tock": ["tock"],
    
    # Silicon/EDA
    "yosys": ["yosys"],
    "verilator": ["verilator"],
    "cocotb": ["cocotb"],
    "circt": ["circt"],
    "chisel": ["chisel"],
    "litex": ["litex"],
    "openroad": ["openroad"],
    "xls": ["xls"],
    "cva6": ["cva6"],
    "riscv": ["riscv-isa-sim", "cva6"],
    "verible": ["verible"],
    
    # Compilers/toolchain
    "llvm": ["llvm-project"],
    "emscripten": ["emscripten"],
    "wasmtime": ["wasmtime"],
    "wasm": ["wasmtime", "emscripten"],
    "tree-sitter": ["tree-sitter"],
    "protobuf": ["protobuf"],
    "grpc": ["grpc"],
    "meson": ["meson"],
    "cmake": ["cmake"],
    "bazel": ["bazel"],
    "vcpkg": ["vcpkg"],
    "conan": ["conan"],
    "ruff": ["ruff"],
    "uv": ["uv"],
    
    # IDE/dev
    "vscode": ["vscode"],
    "theia": ["theia"],
    "monaco": ["vscode", "theia"],
    "open vsx": ["openvsx"],
    "playwright": ["playwright"],
    "xterm": ["xterm.js"],
    "code-server": ["code-server"],
    
    # Identity/policy/secrets
    "keycloak": ["keycloak"],
    "opa": ["opa"],
    "openbao": ["openbao"],
    "vault": ["openbao"],
    
    # OS/boot/fw
    "u-boot": ["u-boot"],
    "uboot": ["u-boot"],
    "coreboot": ["coreboot"],
    "edk2": ["edk2"],
    "systemd": ["systemd"],
    "bootc": ["bootc"],
    "sel4": ["sel4"],
    "redox": ["redox"],
    "9front": ["9front"],
    "tock": ["tock"],
    "qemu": ["qemu"],
    "renode": ["renode"],
    "libp2p": ["rust-libp2p"],
    
    # ML frameworks
    "transformers": ["transformers"],
    "diffusers": ["diffusers"],
    "peft": ["peft"],
    "litellm": ["litellm"],
    "ollama": ["ollama"],
    "ggml": ["ggml"],
    "comfyui": ["comfyui"],
    "open-webui": ["open-webui"],
    "ultralytics": ["ultralytics"],
    "yolo": ["ultralytics"],
    "opencv": ["opencv"],
    "mediapipe": ["mediapipe"],
    "opensim": ["opensim-core"],
    
    # Misc owned
    "ansible": ["ansible"],
    "tauri": ["tauri"],
    "syncthing": ["syncthing"],
    "rclone": ["rclone"],
    "seaweedfs": ["seaweedfs"],
    "ceph": ["ceph"],
    "scylladb": ["scylladb"],
    "valkey": ["valkey"],
    "yugabyte": ["yugabyte-db"],
    "rxdb": ["rxdb"],
    "ditto": ["ditto"],
    "automerge": ["automerge"],
    "tracktion": ["tracktion_engine"],
    "openvoiceos": ["openvoiceos"],
    "mycroft": ["openvoiceos"],
    "energyplus": ["energyplus"],
    "cura": ["curaengine"],
    "drake": ["drake"],
    "kokkos": ["kokkos"],
    "sp1": ["sp1"],
    "pyocd": ["pyocd"],
    "libarchive": ["libarchive"],
    "pyinstaller": ["pyinstaller"],
    "scipy": ["scipy-community"],
    "nextflow": ["nextflow"],
    "libremidi": ["libremidi"],
    "midi": ["libremidi"],
    "inspector": ["inspector"],
    "alp-data": ["alp-data"],
    "genesis-world": ["genesis-world"],
    "skillspector": ["skillspector"],
    "agent-bridge": ["agent-bridge"],
    
    # CAD interchange / BIM
    "ifcopenshell": ["ifcopenshell"],
    "ifc": ["ifcopenshell"],
    
    # Space/flight
    "basilisk": ["cfs"],
    "gmat": ["orekit"],
    
    # Health standards (handled as STANDARD below)
}

# Standard/specification hints
STANDARD_HINTS = [
    "iso ", "ieee ", "rfc ", "w3c", "khronos", "ogc",
    "hl7", "fhir", "dicom", "sbom", "spdx", "cyclonedx",
    "sysml", "bpmn", "gs1", "opcf", "opc ua", "mqtt ",
    "matter ", "thread ", "zigbee", "dids", "verifiable credential",
    "openapi", "asyncapi", "json schema", "smtlib",
    "ccsd", "ecss", "misra", "autosar", "do-178", "do-254",
    "specification", "standard", "protocol", "interface"
]

# Dataset hints
DATASET_HINTS = [
    "dataset", "corpus", "open x-embodiment", "rlds",
    "laion", "common crawl", "the pile", "materials project",
    "oqmd", "aflow", "nomad ", "microns", "eeg-bids",
    "openneuro", "physionet", "imagenet", "coco ", "kitti",
    "nuscenes", "waymo open", "benchmark data", "training data"
]

# Benchmark hints
BENCH_HINTS = [
    "bench", "leaderboard", "gaia", "swe-bench", "tau-bench",
    "agentbench", "osworld", "terminal-bench", "mmlu",
    "human-eval", "big-bench", "helm ", "lm-eval",
    "test suite", "evaluation", "metrics"
]

# Research hints
RESEARCH_HINTS = [
    "hypothesis", "theoretical", "speculative", "unproven",
    "conjecture", "thought experiment", "interpretation of",
    "consciousness", "whole-brain emulation", "propulsion claims",
    "warp ", "antigravity", "free energy", "cold fusion",
    "quantum consciousness", "research", "experimental"
]

# Domain to project mapping
DOMAIN_PROJECT = [
    ("kernel", "AETHERIUS_OS"), ("microkernel", "AETHERIUS_OS"),
    ("bootloader", "AETHERIUS_OS"), ("firmware", "AETHERIUS_OS"),
    ("driver", "AETHERIUS_OS"), ("filesystem", "AETHERIUS_OS"),
    ("scheduler", "AETHERIUS_OS"), ("syscall", "AETHERIUS_OS"),
    ("compositor", "AETHERIUS_OS"), ("wayland", "AETHERIUS_OS"),
    ("windowing", "AETHERIUS_OS"),
    ("agent protocol", "AGENT_BRIDGE"), ("mcp", "AGENT_BRIDGE"),
    ("a2a", "AGENT_BRIDGE"), ("tool contract", "AGENT_BRIDGE"),
    ("orchestration", "AGENT_BRIDGE"), ("swarm", "AGENT_BRIDGE"),
    ("ide", "IDE_WORKSPACE"), ("editor", "IDE_WORKSPACE"),
    ("debugger", "IDE_WORKSPACE"), ("language server", "IDE_WORKSPACE"),
    ("material", "MAT"), ("crystal", "MAT"), ("dft", "MAT"),
    ("molecule", "MAT"), ("chemistry", "MAT"), ("alloy", "MAT"),
    ("audio", "POIETEK"), ("daw", "POIETEK"), ("midi", "POIETEK"),
    ("synth", "POIETEK"), ("plugin", "POIETEK"), ("vst", "POIETEK"),
    ("video", "POIETEK"), ("codec", "POIETEK"),
    ("interop", "UNIVERSAL_BRIDGE"), ("protocol translation", "UNIVERSAL_BRIDGE"),
    ("connector", "UNIVERSAL_BRIDGE"), ("adapter", "UNIVERSAL_BRIDGE"),
    ("fitness", "ATHENA"), ("workout", "ATHENA"), ("biomechanic", "ATHENA"),
    ("gait", "ATHENA"), ("pose", "ATHENA"),
    ("robot", "GENESIS"), ("vla", "GENESIS"), ("embodied", "GENESIS"),
    ("world model", "GENESIS"), ("avatar", "GENESIS"),
    ("slam", "GENESIS"), ("perception", "GENESIS"),
]

# License rejection patterns
REJECTED_LICENSE_PATTERNS = [
    "agpl", "gpl-3", "gplv3", "sspl", "elastic license",
    "bsl", "source-available", "commercial use prohibited"
]

# Security rejection patterns
REJECTED_SECURITY_PATTERNS = [
    "known vulnerability", "security flaw", "backdoor",
    "malicious code", "supply chain attack"
]

# Obsolescence patterns
REJECTED_OBSOLETE_PATTERNS = [
    "abandoned", "unmaintained", "deprecated", "obsolete",
    "no longer maintained", "last commit years ago"
]


def norm(s):
    """Normalize text for comparison."""
    return re.sub(r"[^a-z0-9+.#/ ]", " ", s.lower()).strip()


def load_inventory():
    """Load GitHub repository inventory."""
    with open(INV, "r", encoding="utf-8-sig") as f:
        inv = json.load(f)
    
    repos = {}  # short-name-lower -> info
    for r in inv["local_from_txt"]:
        short = r.split("/")[-1].lower()
        repos.setdefault(short, {"full": r, "fork": True,
                                 "source": "local_from_txt", "desc": ""})
    for r in inv["personal_projects"]:
        short = r["name"].split("/")[-1].lower()
        repos[short] = {"full": r["name"], "fork": r["fork"],
                        "source": "personal_projects",
                        "desc": r.get("description", "")}
    for r in inv["forks"]:
        short = r["name"].split("/")[-1].lower()
        repos.setdefault(short, {"full": r["name"], "fork": True,
                                 "source": "forks",
                                 "desc": r.get("description", "")})
    
    # Token index from names + descriptions
    index = {}
    for short, info in repos.items():
        text = norm(short + " " + info.get("desc", ""))
        for tok in set(text.split()):
            index.setdefault(tok, set()).add(short)
    
    return repos, index


def parse_gaps():
    """Parse gaps from source file."""
    with open(SRC, "r", encoding="utf-8-sig", errors="replace") as f:
        lines = f.read().split("\n")
    
    heads = []
    for i, line in enumerate(lines):
        m = re.match(r"^(\d+)\.\s\*\*(.+?)\*\*\s*$", line.strip())
        if m:
            heads.append((i, int(m.group(1)), m.group(2).strip()))
    
    gaps = {}
    for h, (ln, outer, raw) in enumerate(heads):
        end = heads[h + 1][0] if h + 1 < len(heads) else len(lines)
        m2 = re.match(r"^(\d+)\.\s+(.+)$", raw)
        if m2:
            tid, title = int(m2.group(1)), m2.group(2).strip()
        else:
            tid, title = outer, raw
        
        body = [l.strip() for l in lines[ln + 1:end]]
        items = []
        for b in body:
            if b.startswith("* ") and len(b) > 3:
                items.append(b[2:].strip())
        
        g = gaps.setdefault(tid, {"title": title, "items": [],
                                  "first_line": ln + 1, "occ": 0})
        g["occ"] += 1
        seen = set(g["items"])
        for it in items:
            if it not in seen:
                seen.add(it)
                g["items"].append(it)
    
    return gaps


def classify_item_comprehensive(item, repos, index):
    """Classify a single item using comprehensive categories."""
    n = norm(item)
    if not n:
        return "NOT_APPLICABLE", [], "Empty item"
    
    low = item.lower()
    
    # Check for research-only
    for h in RESEARCH_HINTS:
        if h in low:
            return "RESEARCH_ONLY", [], f"Research hint: {h}"
    
    # Check for dataset
    for h in DATASET_HINTS:
        if h in low:
            return "DATASET", [], f"Dataset hint: {h}"
    
    # Check for benchmark
    for h in BENCH_HINTS:
        if h in low:
            return "BENCHMARK", [], f"Benchmark hint: {h}"
    
    # Check for standard/specification
    for h in STANDARD_HINTS:
        if h in low:
            return "STANDARD", [], f"Standard hint: {h}"
    
    # Check for dependency indicators
    dependency_hints = [
        "library", "package", "dependency", "import", "use",
        "leverage", "integrate", "external", "third-party"
    ]
    for h in dependency_hints:
        if h in low:
            # Check if we have this as a dependency
            hits = set()
            for short in repos:
                ns = norm(short)
                if ns and (ns in n or n in ns):
                    hits.add(short)
            if hits:
                return "DEPENDENCY_ONLY", sorted(hits), f"Dependency hint: {h}"
    
    # Check for plugin/extension indicators
    plugin_hints = ["plugin", "extension", "addon", "module", "connector"]
    for h in plugin_hints:
        if h in low:
            return "PLUGIN", [], f"Plugin hint: {h}"
    
    # Check for SDK indicators
    sdk_hints = ["sdk", "api", "client library", "wrapper"]
    for h in sdk_hints:
        if h in low:
            return "SDK", [], f"SDK hint: {h}"
    
    # Check for API service indicators
    api_hints = ["api service", "web service", "rest api", "graphql", "grpc service"]
    for h in api_hints:
        if h in low:
            return "API_SERVICE", [], f"API service hint: {h}"
    
    # Check for reference implementation indicators
    ref_hints = ["reference implementation", "reference", "example", "sample", "demo"]
    for h in ref_hints:
        if h in low:
            return "REFERENCE_IMPLEMENTATION", [], f"Reference hint: {h}"
    
    # Direct repo-name hit (compare normalized forms both ways)
    hits = set()
    for short in repos:
        ns = norm(short)
        if ns and (ns in n or n in ns):
            hits.add(short)
    
    # Token overlap (need >=2 shared tokens or exact multiword)
    toks = [t for t in n.split() if len(t) > 2]
    cand = {}
    for t in toks:
        for s in index.get(t, ()):
            cand[s] = cand.get(s, 0) + 1
    for s, c in cand.items():
        if c >= 2:
            hits.add(s)
    
    # Equivalence seeds
    for key, shorts in EQUIV.items():
        if key in n:
            for s in shorts:
                if s in repos:
                    hits.add(s)
    
    owned = sorted(hits)
    if not owned:
        return "NOT_COVERED", [], "No matching repos found"
    
    # Check if we have canonical (non-fork) repos
    forks = [s for s in owned if repos[s]["fork"]]
    canon = [s for s in owned if not repos[s]["fork"]]
    
    if canon:
        return "EXISTING_CANONICAL", owned, f"Canonical repos: {canon}"
    elif forks:
        return "EXISTING_FORK", owned, f"Fork repos: {forks}"
    else:
        return "NOT_COVERED", [], "No matching repos found"


def classify_gap_comprehensive(gap_id, title, items, repos, index):
    """Classify a complete gap family using comprehensive categories."""
    per_item = []
    covered = 0
    owned_all = set()
    item_classes = set()
    
    for it in items:
        cls, owned, evidence = classify_item_comprehensive(it, repos, index)
        per_item.append({"item": it, "class": cls, "owned": owned, "evidence": evidence})
        item_classes.add(cls)
        if cls in ("EXISTING_FORK", "EXISTING_CANONICAL"):
            covered += 1
            owned_all.update(owned)
    
    n = len(items)
    frac = (covered / n) if n else 0
    
    # Determine gap-level status
    if n == 0:
        status = "RESEARCH_ONLY"
        next_action = "RESEARCH_LANE"
        evidence = "No items in gap"
    elif frac >= 0.8:
        status = "MOSTLY_COVERED"
        next_action = "REUSE_OWNED"
        evidence = f"{covered}/{n} items covered"
    elif frac >= 0.4:
        status = "PARTIALLY_COVERED"
        next_action = "GAP_ANALYSIS"
        evidence = f"{covered}/{n} items covered"
    elif covered > 0:
        status = "REFERENCE_ONLY"
        next_action = "REUSE_OWNED"
        evidence = f"{covered}/{n} items covered"
    else:
        # No direct coverage - check for other patterns
        if "STANDARD" in item_classes:
            status = "STANDARD"
            next_action = "ADOPT_STANDARD"
            evidence = "Contains standards/specifications"
        elif "DATASET" in item_classes:
            status = "DATASET"
            next_action = "ADD_DATASET_REF"
            evidence = "Contains datasets"
        elif "BENCHMARK" in item_classes:
            status = "BENCHMARK"
            next_action = "ADD_BENCHMARK_REF"
            evidence = "Contains benchmarks"
        elif "RESEARCH_ONLY" in item_classes:
            status = "RESEARCH_ONLY"
            next_action = "RESEARCH_LANE"
            evidence = "Research-only content"
        elif "NOT_APPLICABLE" in item_classes and len(item_classes) == 1:
            status = "NOT_APPLICABLE"
            next_action = "SKIP"
            evidence = "All items not applicable"
        elif "DEPENDENCY_ONLY" in item_classes:
            status = "DEPENDENCY_ONLY"
            next_action = "ADD_DEPENDENCY"
            evidence = "External dependency"
        elif "PLUGIN" in item_classes:
            status = "PLUGIN"
            next_action = "ADD_PLUGIN"
            evidence = "Plugin/extension"
        elif "SDK" in item_classes:
            status = "SDK"
            next_action = "ADD_SDK"
            evidence = "SDK/API client"
        elif "API_SERVICE" in item_classes:
            status = "API_SERVICE"
            next_action = "ADD_API_SERVICE"
            evidence = "API service"
        elif "REFERENCE_IMPLEMENTATION" in item_classes:
            status = "REFERENCE_IMPLEMENTATION"
            next_action = "ADD_REFERENCE"
            evidence = "Reference implementation"
        else:
            # Check if this is a duplicate of another gap
            # (would need cross-gap comparison - simplified here)
            status = "NOT_COVERED"
            next_action = "FIRST_PARTY_TRIAGE"
            evidence = "No coverage found"
    
    # Determine owning project
    project = own_project(title, items)
    
    return {
        "gap_id": gap_id,
        "title": title,
        "project": project,
        "n_items": n,
        "n_covered": covered,
        "coverage_pct": round(100 * frac, 1),
        "status": status,
        "next_action": next_action,
        "evidence": evidence,
        "owned_repos": sorted(owned_all),
        "items": per_item,
        "item_classes": list(item_classes)
    }


def own_project(title, items):
    """Determine which project owns this gap."""
    text = (title + " " + " ".join(items[:12])).lower()
    for key, proj in DOMAIN_PROJECT:
        if key in text:
            return proj
    return "GENESIS"  # default intelligence-architecture owner pending triage


def main():
    """Run comprehensive gap classification."""
    repos, index = load_inventory()
    gaps = parse_gaps()
    print(f"Loaded {len(repos)} repos, {len(gaps)} gaps")
    
    rows = []
    status_counts = {}
    action_counts = {}
    class_counts = {}
    
    for tid in sorted(gaps):
        g = gaps[tid]
        row = classify_gap_comprehensive(tid, g["title"], g["items"], repos, index)
        rows.append(row)
        
        # Count statuses
        s = row["status"]
        status_counts[s] = status_counts.get(s, 0) + 1
        
        # Count next actions
        a = row["next_action"]
        action_counts[a] = action_counts.get(a, 0) + 1
        
        # Count item classes
        for ic in row["item_classes"]:
            class_counts[ic] = class_counts.get(ic, 0) + 1
    
    # Save results
    os.makedirs(OUTDIR, exist_ok=True)
    with open(OUTDIR + "\\MASTER_REQUIREMENTS_GITHUB_COMPARISON.json",
              "w", encoding="utf-8") as f:
        json.dump({"total_gaps": len(rows), "repos": len(repos),
                   "rows": rows}, f, indent=1)
    
    # Save owned capability map
    ocap = {s: {"full": v["full"], "fork": v["fork"],
                "source": v["source"]} for s, v in repos.items()}
    with open(OUTDIR + "\\OWNED_REPOSITORY_CAPABILITY_MAP.json",
              "w", encoding="utf-8") as f:
        json.dump(ocap, f, indent=1)
    
    # Print summary
    print("\n== Gap Status Counts ==")
    for k, v in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    
    print("\n== Next Action Counts ==")
    for k, v in sorted(action_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    
    print("\n== Item Class Counts ==")
    for k, v in sorted(class_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    
    # Show sample NOT_COVERED gaps
    print("\n== Sample NOT_COVERED Gaps ==")
    shown = 0
    for r in rows:
        if r["status"] == "NOT_COVERED" and shown < 10:
            print(f"  {r['gap_id']}: {r['title'][:60]}... ({r['project']})")
            shown += 1
    
    # Show sample FIRST_PARTY_REQUIRED gaps
    print("\n== Sample FIRST_PARTY_REQUIRED Gaps ==")
    shown = 0
    for r in rows:
        if r["next_action"] == "FIRST_PARTY_TRIAGE" and shown < 10:
            print(f"  {r['gap_id']}: {r['title'][:60]}... ({r['project']})")
            shown += 1


if __name__ == "__main__":
    main()
