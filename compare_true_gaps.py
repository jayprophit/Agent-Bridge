#!/usr/bin/env python3
"""MASTER_REQUIREMENTS_GITHUB_COMPARISON with reduction pipeline.

For each TRUE gap ID (1..1040 present set):
  GAP -> items -> capability match vs owned repos -> classification
  -> owning project -> shared? -> coverage state -> next action.

No foundations/repos are created here. This is classification only.
"""
import json
import re

SRC = r"C:\Users\jpowe\Documents\openCDE-agent\master reequirements.txt"
INV = (r"C:\Users\jpowe\Desktop\Agent-Bridge"
       r"\jayprophit_repository_inventory.json")
OUTDIR = r"E:\OpenCode-Data\Repository-Governance"

# ---- capability equivalence seeds (documented, capability not name) ----
EQUIV = {
    # vector/memory stores
    "lancedb": ["qdrant"], "milvus": ["qdrant"], "weaviate": ["qdrant"],
    "chroma": ["qdrant"], "qdrant": ["qdrant"],
    "graphiti": ["graphiti"], "mem0": ["mem0"], "mem0ai": ["mem0"],
    "llamaindex": ["llama_index"], "llama-index": ["llama_index"],
    # agent protocols / SDKs
    "model context protocol": ["typescript-sdk", "python-sdk"],
    "mcp sdk": ["typescript-sdk", "python-sdk"],
    "mcp sdks": ["typescript-sdk", "python-sdk"],
    "mcp": ["typescript-sdk", "python-sdk", "inspector"],
    "a2a": ["a2a"], "agent2agent": ["a2a"],
    "a2ui": ["a2a"], "ag-ui": ["a2a"],
    # agent frameworks
    "crewai": ["crewai"], "langgraph": ["langgraph"],
    "autogen": ["agent-framework"], "agent framework": ["agent-framework"],
    # inference
    "llama.cpp": ["llama.cpp"], "llamacpp": ["llama.cpp"],
    "vllm": ["vllm"], "tvm": ["tvm"], "iree": ["iree"],
    "onnx": ["onnxruntime"], "onnx runtime": ["onnxruntime"],
    "executorch": ["executorch"],
    # speech/audio
    "whisper": ["whisper.cpp", "sherpa-onnx"],
    "sherpa": ["sherpa-onnx"], "sherpa-onnx": ["sherpa-onnx"],
    "kokoro": ["sherpa-onnx"], "piper": ["sherpa-onnx"],
    "rtaudio": ["rtaudio"], "csound": ["csound"],
    "supercollider": ["supercollider"],
    "pipewire": ["pipewire"], "jack": ["rtaudio"],
    # cad/engineering
    "freecad": ["freecad"], "openscad": ["openscad"],
    "cadquery": ["freecad"], "build123d": ["freecad"],
    "occt": ["freecad"], "opencascade": ["freecad"],
    "kicad": ["kicad-source-mirror"],
    # cae/sim
    "openfoam": ["su2"], "calculix": ["su2", "mfem"],
    "fenics": ["dolfinx"], "dolfinx": ["dolfinx"],
    "mfem": ["mfem"], "petsc": ["petsc"], "moose": ["moose"],
    "su2": ["su2"], "sofa": ["sofa"],
    "gazebo": ["gz-sim"], "gz-sim": ["gz-sim"],
    "webots": ["webots"], "mujoco": ["mujoco"],
    "isaac": ["isaaclab"], "isaaclab": ["isaaclab"],
    # robotics middleware
    "ros2": ["ros2"], "ros": ["ros2"],
    "navigation2": ["navigation2"], "nav2": ["navigation2"],
    "px4": ["px4-autopilot"], "ardupilot": ["ardupilot"],
    "mavsdk": ["px4-autopilot", "ardupilot"],
    "lerobot": ["lerobot"], "leRobot": ["lerobot"],
    "behaviortree": ["drake"], "behavior tree": ["drake"],
    # quantum
    "qiskit": ["qiskit"], "pennylane": ["pennylane"],
    "cirq": ["qiskit"], "qutip": ["qiskit"],
    # crypto/pqc/fhe
    "openfhe": ["openfhe-development"], "tfhe": ["tfhe-rs"],
    # materials/chem
    "aiida": ["aiida-core"], "pymatgen": ["pymatgen-core"],
    "pyscf": ["pyscf"], "openmm": ["openmm"],
    "cantera": ["cantera"], "lammps": ["lammps"],
    "quantum espresso": ["pyscf"], "gpaW": ["pyscf"],
    # bio
    "gatk": ["gatk"], "samtools": ["samtools"],
    "scanpy": ["scanpy"], "scikit-bio": ["scikit-bio"],
    "crispresso": ["crispresso2"],
    "nrn": ["nrn"], "neuron": ["nrn"],
    "nest": ["nest-simulator"], "brian2": ["nest-simulator"],
    "deeplabcut": ["deeplabcut"], "sleap": ["sleap"],
    "mne": ["mne-python"], "brainflow": ["mne-python"],
    "spikeinterface": ["spikeinterface"],
    # geo/space
    "gdal": ["gdal"], "pdal": ["pdal"], "cesium": ["cesium"],
    "orekit": ["orekit"], "cfs": ["cfs"], "satdump": ["satdump"],
    "colmap": ["colmap"], "open3d": ["open3d"], "pcl": ["pcl"],
    "rtabmap": ["rtabmap"], "gtsam": ["gtsam"],
    # media
    "ffmpeg": ["ffmpeg"], "gstreamer": ["ffmpeg"],
    "blender": ["blender"], "godot": ["godot-official"],
    "c2pa": ["c2pa-rs"],
    # data/infra
    "sqlite": ["sqlite"], "postgres": ["timescaledb"],
    "timescaledb": ["timescaledb"], "influxdb": ["influxdb"],
    "prometheus": ["prometheus"], "grafana": ["grafana"],
    "opentelemetry": ["opentelemetry-collector"],
    "kafka": ["redpanda"], "redpanda": ["redpanda"],
    "nats": ["nats-server"], "mqtt": ["esphome"],
    "zenoh": ["zenoh"], "dds": ["zenoh"],
    "neo4j": ["neo4j"], "duckdb": ["duckdb---community"],
    "arrow": ["arrow"],
    # containers/orchestration
    "kubernetes": ["k3s", "helm"], "k3s": ["k3s"], "helm": ["helm"],
    "containerd": ["containerd"], "firecracker": ["firecracker"],
    "gvisor": ["gvisor"], "kata": ["firecracker", "gvisor"],
    "moby": ["moby"], "docker": ["moby"],
    "temporal": ["temporal"], "dagster": ["dagster"],
    "n8n": ["n8n"], "ray": ["ray"],
    # edge/iot
    "esphome": ["esphome"], "home assistant": ["core"],
    "matter": ["connectedhomeip"], "openthread": ["openthread"],
    "zephyr": ["zephyr"], "tock": ["tock"],
    # silicon/eda
    "yosys": ["yosys"], "verilator": ["verilator"],
    "cocotb": ["cocotb"], "circt": ["circt"], "chisel": ["chisel"],
    "litex": ["litex"], "openroad": ["openroad"],
    "xls": ["xls"], "cva6": ["cva6"],
    "riscv": ["riscv-isa-sim", "cva6"],
    "verible": ["verible"],
    # compilers/toolchain
    "llvm": ["llvm-project"], "emscripten": ["emscripten"],
    "wasmtime": ["wasmtime"], "wasm": ["wasmtime", "emscripten"],
    "tree-sitter": ["tree-sitter"], "protobuf": ["protobuf"],
    "grpc": ["grpc"], "meson": ["meson"], "cmake": ["cmake"],
    "bazel": ["bazel"], "vcpkg": ["vcpkg"], "conan": ["conan"],
    "ruff": ["ruff"], "uv": ["uv"],
    # ide/dev
    "vscode": ["vscode"], "theia": ["theia"],
    "monaco": ["vscode", "theia"], "open vsx": ["openvsx"],
    "playwright": ["playwright"], "xterm": ["xterm.js"],
    "code-server": ["code-server"],
    # identity/policy/secrets
    "keycloak": ["keycloak"], "opa": ["opa"],
    "openbao": ["openbao"], "vault": ["openbao"],
    # os/boot/fw
    "u-boot": ["u-boot"], "uboot": ["u-boot"],
    "coreboot": ["coreboot"], "edk2": ["edk2"],
    "systemd": ["systemd"], "bootc": ["bootc"],
    "sel4": ["sel4"], "redox": ["redox"], "9front": ["9front"],
    "tock": ["tock"], "qemu": ["qemu"], "renode": ["renode"],
    "libp2p": ["rust-libp2p"],
    # ml frameworks
    "transformers": ["transformers"], "diffusers": ["diffusers"],
    "peft": ["peft"], "litellm": ["litellm"], "ollama": ["ollama"],
    "ggml": ["ggml"], "comfyui": ["comfyui"],
    "open-webui": ["open-webui"], "ultralytics": ["ultralytics"],
    "yolo": ["ultralytics"], "opencv": ["opencv"],
    "mediapipe": ["mediapipe"], "opensim": ["opensim-core"],
    # misc owned
    "ansible": ["ansible"], "tauri": ["tauri"],
    "syncthing": ["syncthing"], "rclone": ["rclone"],
    "seaweedfs": ["seaweedfs"], "ceph": ["ceph"],
    "scylladb": ["scylladb"], "valkey": ["valkey"],
    "yugabyte": ["yugabyte-db"], "rxdb": ["rxdb"],
    " Ditto": ["ditto"], "ditto": ["ditto"],
    "automerge": ["automerge"], "tracktion": ["tracktion_engine"],
    "openvoiceos": ["openvoiceos"], "mycroft": ["openvoiceos"],
    "energyplus": ["energyplus"], "cura": ["curaengine"],
    "drake": ["drake"], "kokkos": ["kokkos"],
    "sp1": ["sp1"], "pyocd": ["pyocd"],
    "libarchive": ["libarchive"], "pyinstaller": ["pyinstaller"],
    "scipy": ["scipy-community"], "nextflow": ["nextflow"],
    "libremidi": ["libremidi"], "midi": ["libremidi"],
    "inspector": ["inspector"], "alp-data": ["alp-data"],
    "genesis-world": ["genesis-world"],
    "skillspector": ["skillspector"],
    "agent-bridge": ["agent-bridge"],
    # cad interchange / bim
    "ifcopenshell": ["ifcopenshell"], "ifc": ["ifcopenshell"],
    # space/flight
    "basilisk": ["cfs"], "gmat": ["orekit"],
    # health standards handled as STANDARD below
}

STANDARD_HINTS = ["iso ", "ieee ", "rfc ", "w3c", "khronos", "ogc",
                  "hl7", "fhir", "dicom", "sbom", "spdx", "cyclonedx",
                  "sysml", "bpmn", "gs1", "opcf", "opc ua", "mqtt ",
                  "matter ", "thread ", "zigbee", "dids", "verifiable credential",
                  "openapi", "asyncapi", "json schema", "smtlib",
                  "ccsd", "ecss", "misra", "autosar", "do-178", "do-254"]
BENCH_HINTS = ["bench", "leaderboard", "gaia", "swe-bench", "tau-bench",
               "agentbench", "osworld", "terminal-bench", "mmlu",
               "human-eval", "big-bench", "helm ", "lm-eval"]
DATASET_HINTS = ["dataset", "corpus", "open x-embodiment", "rlds",
                 "laion", "common crawl", "the pile", "materials project",
                 "oqmd", "aflow", "nomad ", "microns", "eeg-bids",
                 "openneuro", "physionet", "imagenet", "coco ", "kitti",
                 "nuscenes", "waymo open"]
RESEARCH_HINTS = ["hypothesis", "theoretical", "speculative", "unproven",
                  "conjecture", "thought experiment", "interpretation of",
                  "consciousness", "whole-brain emulation", "propulsion claims",
                  "warp ", "antigravity", "free energy", "cold fusion",
                  "quantum consciousness"]

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


def norm(s):
    return re.sub(r"[^a-z0-9+.#/ ]", " ", s.lower()).strip()


def load_inventory():
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
    # token index from names + descriptions
    index = {}
    for short, info in repos.items():
        text = norm(short + " " + info.get("desc", ""))
        for tok in set(text.split()):
            index.setdefault(tok, set()).add(short)
    return repos, index


def parse_gaps():
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


def classify_item(item, repos, index):
    n = norm(item)
    if not n:
        return "NOT_APPLICABLE", []
    low = item.lower()
    for h in RESEARCH_HINTS:
        if h in low:
            return "RESEARCH_ONLY", []
    for h in BENCH_HINTS:
        if h in low:
            return "BENCHMARK", []
    for h in DATASET_HINTS:
        if h in low:
            return "DATASET", []
    for h in STANDARD_HINTS:
        if h in low:
            return "STANDARD", []
    # direct repo-name hit (compare normalized forms both ways)
    hits = set()
    for short in repos:
        ns = norm(short)
        if ns and (ns in n or n in ns):
            hits.add(short)
    # token overlap (need >=2 shared tokens or exact multiword)
    toks = [t for t in n.split() if len(t) > 2]
    cand = {}
    for t in toks:
        for s in index.get(t, ()): 
            cand[s] = cand.get(s, 0) + 1
    for s, c in cand.items():
        if c >= 2:
            hits.add(s)
    # equivalence seeds
    for key, shorts in EQUIV.items():
        if key in n:
            for s in shorts:
                if s in repos:
                    hits.add(s)
    owned = sorted(hits)
    if not owned:
        return "NOT_COVERED", []
    forks = [s for s in owned if repos[s]["fork"]]
    canon = [s for s in owned if not repos[s]["fork"]]
    if canon:
        return "EXISTING_CANONICAL", owned
    return "EXISTING_FORK", owned


def own_project(title, items):
    text = (title + " " + " ".join(items[:12])).lower()
    for key, proj in DOMAIN_PROJECT:
        if key in text:
            return proj
    return "GENESIS"  # default intelligence-architecture owner pending triage


def main():
    repos, index = load_inventory()
    gaps = parse_gaps()
    print("repos:", len(repos), "gaps:", len(gaps))

    rows = []
    item_counts = {}
    gap_status = {}
    for tid in sorted(gaps):
        g = gaps[tid]
        per_item = []
        covered = 0
        owned_all = set()
        for it in g["items"]:
            cls, owned = classify_item(it, repos, index)
            per_item.append({"item": it, "class": cls, "owned": owned})
            item_counts[cls] = item_counts.get(cls, 0) + 1
            if cls in ("EXISTING_FORK", "EXISTING_CANONICAL"):
                covered += 1
                owned_all.update(owned)
        n = len(g["items"])
        frac = (covered / n) if n else 0
        if n == 0:
            status = "RESEARCH_ONLY"
        elif frac >= 0.8:
            status = "MOSTLY_COVERED"
        elif frac >= 0.4:
            status = "PARTIALLY_COVERED"
        elif covered > 0:
            status = "REFERENCE_ONLY"
        else:
            # any standard/dataset/benchmark/research items?
            kinds = {p["class"] for p in per_item}
            if kinds <= {"STANDARD", "SPECIFICATION_SOURCE"}:
                status = "REFERENCE_ONLY"
            elif "RESEARCH_ONLY" in kinds and len(kinds) == 1:
                status = "RESEARCH_ONLY"
            else:
                status = "NOT_COVERED"
        gap_status[status] = gap_status.get(status, 0) + 1
        # next action
        if status in ("MOSTLY_COVERED", "PARTIALLY_COVERED", "REFERENCE_ONLY"):
            nxt = "REUSE_OWNED"
        elif status == "RESEARCH_ONLY":
            nxt = "RESEARCH_LANE"
        elif status == "NOT_COVERED":
            kinds = {p["class"] for p in per_item}
            if "STANDARD" in kinds:
                nxt = "ADOPT_STANDARD"
            elif "DATASET" in kinds or "BENCHMARK" in kinds:
                nxt = "ADD_DATASET_BENCHMARK_REF"
            else:
                nxt = "FIRST_PARTY_TRIAGE"
        else:
            nxt = "TRIAGE"
        rows.append({"gap_id": tid, "title": g["title"],
                     "project": own_project(g["title"], g["items"]),
                     "n_items": n, "n_covered": covered,
                     "coverage_pct": round(100 * frac, 1),
                     "status": status, "next_action": nxt,
                     "owned_repos": sorted(owned_all),
                     "items": per_item})

    import os
    os.makedirs(OUTDIR, exist_ok=True)
    with open(OUTDIR + "\\MASTER_REQUIREMENTS_GITHUB_COMPARISON.json",
              "w", encoding="utf-8") as f:
        json.dump({"total_gaps": len(rows), "repos": len(repos),
                   "rows": rows}, f, indent=1)
    # owned capability map
    ocap = {s: {"full": v["full"], "fork": v["fork"],
                "source": v["source"]} for s, v in repos.items()}
    with open(OUTDIR + "\\OWNED_REPOSITORY_CAPABILITY_MAP.json",
              "w", encoding="utf-8") as f:
        json.dump(ocap, f, indent=1)

    print("== item classes ==")
    for k, v in sorted(item_counts.items(), key=lambda x: -x[1]):
        print("  %-22s %d" % (k, v))
    print("== gap status ==")
    for k, v in sorted(gap_status.items(), key=lambda x: -x[1]):
        print("  %-20s %d" % (k, v))
    # top NOT_COVERED P0-ish (gap<=8 or P0 in title)
    print("== sample NOT_COVERED ==")
    shown = 0
    for r in rows:
        if r["status"] == "NOT_COVERED" and shown < 15:
            print("  %d %s (%s)" % (r["gap_id"], r["title"][:65],
                                    r["project"]))
            shown += 1


if __name__ == "__main__":
    main()
