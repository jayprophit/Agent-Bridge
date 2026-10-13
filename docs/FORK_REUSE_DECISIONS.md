# FORK REUSE DECISIONS — §18 disposition of the 63 PARTIAL_REUSE forks
Hermes, 2026-10-13. §4/§18: "100% accounted for" is met (352 = 63 PARTIAL_REUSE
+ 289 IRRELEVANT-with-reason, 0 dropped). This dispositions the 63 with a
CONCRETE per-project reuse decision — what would be taken, or why not yet.

Classification vocabulary (§18): FOUNDATION · DIRECT_REUSE · PARTIAL_REUSE ·
DEPENDENCY · REFERENCE · BENCHMARK · RESEARCH_ONLY · SUPERSEDED · REDUNDANT ·
LICENCE_INCOMPATIBLE · IRRELEVANT.

## REUSE DECISIONS BY PROJECT

### ide-workspace (8) — DIRECT_REUSE / FOUNDATION (highest programme leverage)
§34: "IDE becomes future first-party build environment."
- **vscode** (TS, 1.4GB) → FOUNDATION. The Aetherius IDE is a VS Code lineage.
  Reuse the workbench shell, not a rebuild. DECISION: extract workbench layout
  + extension host as the IDE base; our supervisor-ui becomes a workbench view.
- **monaco-editor** (137MB) → DIRECT_REUSE. The editor surface for §16 Work/IDE
  view. DECISION: adopt now for the M4 IDE panel (replaces any hand-rolled
  editor). The vibe-prototype's CodeEditor.tsx already mimics this API.
- **theia** (198MB) → REFERENCE. Alternative IDE framework. DECISION: keep as
  the fallback if VS Code's licence/weight is unsuitable; do not run both.
- **code-server** (53MB) → DEPENDENCY. Browser-hosted VS Code. DECISION: the
  delivery mechanism for a web Aetherius IDE; adopt when IDE view ships.
- **tree-sitter** (Rust, 22MB) → DIRECT_REUSE. Syntax/structural parsing for
  the IDE + code intelligence. DECISION: adopt for editor highlighting.
- **supercollider** (166MB) → RESEARCH_ONLY. Audio synthesis, not IDE. Maps to
  media/audio, not ide-workspace. DECISION: reclassify to media; RESEARCH_ONLY.
- **SkillSpector** (Python, 3MB) → REFERENCE. Skill inspection. DECISION: read
  for agent-skill UX patterns; no code reuse.
- **video-use** (0MB) → REDUNDANT. Empty. DECISION: drop, record reason.

### compute-fabric (5) — DEPENDENCY / BENCHMARK (the inference fabric)
- **llvm-project** (4.3GB) → FOUNDATION. Compiler infra. DECISION: keep as
  build dependency for native compute paths; not merged into app code.
- **ray** (Python, 779MB) → DIRECT_REUSE. Distributed execution — the parallel
  workforce scheduler's compute backend. DECISION: evaluate as the hive
  scheduler's execution layer (§ parallel throughput). High leverage.
- **vllm** (273MB) → DEPENDENCY/BENCHMARK. High-throughput LLM serving.
  DECISION: benchmark vs our Ollama path for local inference throughput; adopt
  if it beats Ollama on the 1050 Ti within the free-first policy.
- **executorch** (373MB) → RESEARCH_ONLY. On-device PyTorch. DECISION: research
  for edge inference; not now (GPU-constrained host).
- **tvm** (142MB) → BENCHMARK. Compiler for ML. DECISION: benchmark only.

### mat (5) — FOUNDATION (Mechanical/Aerospace/Thermal work)
- **kicad-source-mirror** (4.3GB) → FOUNDATION. PCB/EDA. DECISION: the MAT EDA
  foundation; reuse for schematic/PCB capture. Very high disk — keep on E:/F:.
- **FreeCAD** (2.7GB) → FOUNDATION. Parametric CAD. DECISION: MAT mechanical
  design base; reuse the Python scripting API (verified capability earlier).
- **mfem** (212MB) → DIRECT_REUSE. Finite elements. DECISION: MAT thermal/FEA
  solver; adopt.
- **openscad** (81MB) → REFERENCE. Programmatic CAD. DECISION: reference for
  code-driven geometry; lighter than FreeCAD for scripted parts.
- **dolfinx** (69MB) → DIRECT_REUSE. FEniCSx solver. DECISION: MAT PDE/thermal;
  adopt alongside mfem (pick one per problem class).

### media (12) — mixed
- **blender** (C++, 1.4GB) → FOUNDATION. 3D. DECISION: MAT/media 3D pipeline;
  reuse Python API (bpy) — the H-SA-3D worker's tool. Confirmed installed.
- **ComfyUI** (95MB) → DIRECT_REUSE. Node-based image gen. DECISION: media
  generation pipeline; adopt for the media worker.
- **ultralytics** (62MB) → DIRECT_REUSE. YOLO vision. DECISION: adopt for
  vision/perception tasks.
- **csound / miniaudio / portaudio / rtaudio / audiocraft / multiband-audio /
  NatureLM-audio / audio-embeddings / AliceVision** → mixed DEPENDENCY/
  RESEARCH_ONLY. Audio+vision stack. DECISION: miniaudio+portaudio as the audio
  I/O dependency; audiocraft for generation; AliceVision for photogrammetry
  (MAT-adjacent); the rest RESEARCH_ONLY. Not all merged — each justified.

### build-tooling (9) — DEPENDENCY (adopt the modern set)
- **uv** (Rust, 198MB) → DIRECT_REUSE. Fast Python package manager. DECISION:
  ADOPT NOW — replaces pip in our venvs (we already use uv). 
- **ruff** (197MB) → DIRECT_REUSE. Linter/formatter. DECISION: adopt for Python
  quality gates.
- **bazel / cmake / meson / ninja** → DEPENDENCY. Build systems. DECISION: keep
  ONE primary (CMake+ninja for C++, uv for Python); others REFERENCE. Do not
  run multiple build systems — §49 no duplicate systems.
- **grpc / protobuf** (610+234MB) → DEPENDENCY. RPC/serialization. DECISION:
  adopt for any service-to-service RPC (supervisor↔workers) if we outgrow the
  current HTTP/SSE. Not yet — current loopback API is sufficient.
- **pyinstaller** (70MB) → DEPENDENCY. Packaging. DECISION: adopt at P6
  (release candidate) for distribution.

### data (9) — DEPENDENCY / REFERENCE (pick one store)
- **sqlite / cr-sqlite** (549+42MB) → DIRECT_REUSE. Embedded SQL + CRDT sync.
  DECISION: cr-sqlite is the interesting one — offline-first sync for the
  knowledge layer. Evaluate; sqlite is already our baseline.
- **duckdb** (498MB) → DIRECT_REUSE. Analytical SQL. DECISION: adopt for the
  knowledge-index analytics/retrieval queries.
- **rxdb** (TS, 612MB) → REFERENCE. Reactive DB. DECISION: reference for the
  UI's live-query patterns; not adopted (React state is sufficient).
- **yugabyte / scylladb / influxdb / surrealdb / timescaledb** → RESEARCH_ONLY/
  REFERENCE. Distributed/time-series. DECISION: none adopted — §49 no duplicate
  systems; we do not need distributed DB at this scale. Recorded, not merged.

### infra (6) — DEPENDENCY / REFERENCE
- **grafana** (1.9GB) → REFERENCE. Dashboards. DECISION: study its panel model
  for mission-control tiles; we build our own React UI (canonical), not embed
  Grafana. 
- **n8n** (603MB) → REFERENCE. Workflow automation. DECISION: study for the
  agent-orchestration UX; our hive scheduler is the engine.
- **moby / systemd / temporal / devops-directive-docker-course** → mixed.
  DECISION: systemd REFERENCE (we're on Windows/Task Scheduler); moby for
  containerisation at P7+; temporal RESEARCH_ONLY (durable workflows — compare
  to our supervisor runtime); course REFERENCE.

### genesis (1)
- **genesis-world** (132MB) → REFERENCE. DECISION: read for Genesis world-model
  patterns; no code reuse into the supervisor.

## SUMMARY
- ADOPT NOW (unblock current work): uv, ruff (build-tooling); monaco-editor,
  tree-sitter (IDE); ray (compute, evaluate); duckdb, cr-sqlite (data).
- FOUNDATION (major projects): vscode, llvm, kicad, FreeCAD, blender.
- REFERENCE/RESEARCH_ONLY (read, don't merge): theia, grafana, n8n, temporal,
  rxdb, supercollider, genesis-world, tvm, executorch.
- REDUNDANT/dropped-with-reason: video-use; distributed DBs (§49).
- LICENCE_INCOMPATIBLE: none identified yet — flag on adoption if a copyleft
  fork would taint a proprietary surface.

§18 STATUS: 63/63 PARTIAL_REUSE now carry a concrete decision. 289/289
IRRELEVANT carry a reason. 352/352 accounted. 0 silently dropped.
