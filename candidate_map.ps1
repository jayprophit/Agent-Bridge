# Candidate Repository Map for AETHERIUS-REPOSITORY-PROVISIONING
# Sub-task F: Generate candidate repository map for all proposed apps/plugins/engines/SDKs/services/adapters/drivers/simulators

# Read the current registry
$registry = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\AETHERIUS_REPOSITORY_REGISTRY.json' | ConvertFrom-Json

# Define repo name sources as arrays
$source1 = @(
"jayprophit/ComfyUI","jayprophit/n8n","jayprophit/meson","jayprophit/protobuf","jayprophit/tree-sitter",
"jayprophit/tock","jayprophit/ruff","jayprophit/Agent-Bridge","jayprophit/9front","jayprophit/CMake",
"jayprophit/grafana","jayprophit/libarchive","jayprophit/systemd","jayprophit/bootc","jayprophit/grpc",
"jayprophit/uv","jayprophit/pyinstaller","jayprophit/coreboot","jayprophit/moby","jayprophit/executorch",
"jayprophit/llvm-project","jayprophit/temporal","jayprophit/OpenROAD","jayprophit/ultralytics","jayprophit/vllm",
"jayprophit/verilator","jayprophit/yugabyte-db","jayprophit/ray","jayprophit/rxdb","jayprophit/tvm",
"jayprophit/SU2","jayprophit/core","jayprophit/rtaudio","jayprophit/csound","jayprophit/kicad-source-mirror",
"jayprophit/mfem","jayprophit/FreeCAD","jayprophit/dolfinx","jayprophit/esphome","jayprophit/seL4",
"jayprophit/nextflow","jayprophit/qiskit","jayprophit/emscripten","jayprophit/drake","jayprophit/gtsam",
"jayprophit/cantera","jayprophit/blender","jayprophit/iree","jayprophit/ceph","jayprophit/godot-official",
"jayprophit/vscode","jayprophit/cesium","jayprophit/redox","jayprophit/PX4-Autopilot","jayprophit/IfcOpenShell",
"jayprophit/pipewire","jayprophit/verible","jayprophit/colmap","jayprophit/zephyr","jayprophit/SatDump",
"jayprophit/circt","jayprophit/arrow","jayprophit/sqlite","jayprophit/ggml","jayprophit/cva6",
"jayprophit/cocotb","jayprophit/aiida-core","jayprophit/syncthing","jayprophit/gvisor","jayprophit/moose",
"jayprophit/IsaacLab","jayprophit/xls","jayprophit/litex","jayprophit/seaweedfs","jayprophit/cFS",
"jayprophit/webots","jayprophit/pennylane","jayprophit/ardupilot","jayprophit/connectedhomeip","jayprophit/keycloak",
"jayprophit/scylladb","jayprophit/valkey","jayprophit/u-boot","jayprophit/c2pa-rs","jayprophit/openthread",
"jayprophit/timescaledb","jayprophit/openfhe-development","jayprophit/k3s","jayprophit/opentitan","jayprophit/qemu",
"jayprophit/depthai-core","jayprophit/containerd","jayprophit/helm","jayprophit/playwright","jayprophit/ansible",
"jayprophit/vcpkg","jayprophit/opentelemetry-collector","jayprophit/supercollider","jayprophit/edk2","jayprophit/rust-libp2p",
"jayprophit/gatk","jayprophit/nats-server","jayprophit/bazel","jayprophit/tfhe-rs","jayprophit/PDAL",
"jayprophit/crewAI","jayprophit/openmm","jayprophit/nrn","jayprophit/wasmtime","jayprophit/code-server",
"jayprophit/dagster","jayprophit/petsc","jayprophit/openbao","jayprophit/theia","jayprophit/llama_index",
"jayprophit/compose","jayprophit/renode","jayprophit/conan","jayprophit/firecracker","jayprophit/warpx",
"jayprophit/riscv-isa-sim","jayprophit/CuraEngine","jayprophit/DeepLabCut","jayprophit/spikeinterface",
"jayprophit/litellm","jayprophit/zenoh","jayprophit/prometheus","jayprophit/lerobot","jayprophit/scanpy",
"jayprophit/nest-simulator","jayprophit/yosys","jayprophit/opensim-core","jayprophit/chisel","jayprophit/automerge",
"jayprophit/A2A","jayprophit/mem0","jayprophit/ditto","jayprophit/sofa","jayprophit/pcl","jayprophit/pymatgen-core",
"jayprophit/genesis-world","jayprophit/rtabmap","jayprophit/alp-data","jayprophit/inspector","jayprophit/onnxruntime",
"jayprophit/llama.cpp","jayprophit/sherpa-onnx","jayprophit/ollama","jayprophit/openvsx","jayprophit/mujoco",
"jayprophit/mne-python","jayprophit/neo4j","jayprophit/langgraph","jayprophit/Orekit","jayprophit/scipy-community",
"jayprophit/tracktion_engine","jayprophit/tauri","jayprophit/samtools","jayprophit/scikit-bio","jayprophit/peft",
"jayprophit/pyOCD","jayprophit/python-sdk"
)

$source2 = @(
"jayprophit/ComfyUI","jayprophit/Agent-Bridge","jayprophit/SkillSpector","jayprophit/FreeCAD",
"jayprophit/sp1","jayprophit/drake","jayprophit/kokkos","jayprophit/zephyr","jayprophit/openscad",
"jayprophit/opa","jayprophit/diffusers","jayprophit/EnergyPlus","jayprophit/ansible","jayprophit/crewAI",
"jayprophit/CuraEngine","jayprophit/A2A","jayprophit/mem0","jayprophit/crm","jayprophit/transformers",
"jayprophit/ollama","jayprophit/whisper.cpp","jayprophit/typescript-sdk","jayprophit/pydantic-ai",
"jayprophit/graphiti","jayprophit/agent-framework","jayprophit/phone-harness","jayprophit/langgraph",
"jayprophit/python-sdk"
)

$source3 = @(
"Agent-Bridge","genesis","IDE-Workspace","MAT","poietek","Universal-Bridge","Aetherious-os"
)

$source4 = @(
"adobe/photoshop","adobe/illustrator","adobe/premiere-pro","adobe/after-effects","adobe/dreamweaver",
"autodesk/autoCAD","autodesk/revit","autodesk/maya","autodesk/3ds-max","autodesk/fusion-360",
"microsoft/365","microsoft/teams","microsoft/office",
"unity/editor","unity/analytics","unity/collaboration","unreal-engine","godot-engine","cryengine","langyard",
"ffmpeg","gstreamer","avid","da-vinci-resolve","nuke",
"clap-plugin-host","vst3-sdk","au-plugin-bridge","lv2-plugin-registry","aax-bridge",
"surge-synth","dexed-synth","vitalium-synth","helm-synth","drum-machine-kit","piano-roll-editor",
"stem-separation-engine","voice-processing-engine"
)

$source5 = @(
"Aetherius-IDE","Aetherius-Store","Aetherius-OS","Aetherius-App-Ecosystem","Aetherius-OS-Competitor-Registry",
"Aetherius-OS-Default-App-Comparison","Aetherius-OS-First-Party-Product-Map","Aetherius-Account-Type-Registry",
"Aetherius-Application-Master-Registry","Aetherius-Domain-Registry","Aetherius-Application-Access-Matrix",
"Aetherius-Competitor-Matrix","Aetherius-Benchmark-Framework","Aetherius-Quality-Dashboard",
"Aetherius-5-Star-Target-Benchmark","Aetherius-Competitor-Problem-Mining","Aetherius-User-Persona-Testing",
"Aetherius-First-Run-Experience"
)

$source5b = @(
"APP_REPOSITORY_PLAN","PLUGIN_REPOSITORY_PLAN","EXTENSION_REPOSITORY_PLAN","ENGINE_REPOSITORY_PLAN",
"SERVICE_REPOSITORY_PLAN","SDK_REPOSITORY_PLAN","DRIVER_REPOSITORY_PLAN","LIBRARY_REPOSITORY_PLAN",
"SIMULATION_REPOSITORY_PLAN","GAME_REPOSITORY_PLAN","MEDIA_REPOSITORY_PLAN","OFFICE_REPOSITORY_PLAN",
"ENGINEERING_REPOSITORY_PLAN","APP_CANDIDATE_MAP","PLUGIN_CANDIDATE_MAP","ENGINE_CANDIDATE_MAP",
"SDK_CANDIDATE_MAP","SERVICE_CANDIDATE_MAP","DRIVER_CANDIDATE_MAP","LIBRARY_CANDIDATE_MAP",
"SIMULATION_CANDIDATE_MAP","GAME_CANDIDATE_MAP","MEDIA_CANDIDATE_MAP","OFFICE_CANDIDATE_MAP",
"ENGINEERING_CANDIDATE_MAP","REPOSITORY_CREATION_PIPELINE","REPOSITORY_STATE_PIPELINE",
"DEPENDENCY_GRAPH","REPOSITORY_NAME_REGISTRY","LICENSE_STATUS_REGISTER","PROVENANCE_REGISTER",
"PACKAGE_REGISTRY","PLUGIN_REGISTRY","EXTENSION_REGISTRY","SECURITY_POLICY","VERSIONING_MODEL",
"RELEASE_MANAGEMENT_MODEL","CROSS_PLATFORM_BUILD_TARGETS","PACKAGE_ARTIFACT_REGISTRY"
)

$source6 = @(
"poietek-plugin-sdk","poietek-plugin-lab","surge-synth","dexed-synth","vitalium-synth","helm-synth",
"drum-machine","piano-roll","score-notation","stem-separation","voice-processing",
"clap-plugin-host","vst3-sdk","au-plugin-bridge","lv2-plugin-registry","aax-bridge",
"open-audio-datasets","audio-benchmark-registry","dsp-testing-methodology","plugin-test-host","plugin-sdk",
"first-party-effect-repository","rights-manifest-identifier-registry","audio-asset-database","audio-dump-pipeline",
"open-datasets-for-audio","spatial-audio-registry","stem-separation-engines","voice-vocal-processing",
"mixer-routing-modulation-automation","hardware-integration-corpus","sync-concepts","audio-format-registry",
"project-interchange-registry","effects-taxonomy","synthesis-registry","sampler-format-registry","audio-format-registry"
)

$source7 = @(
"simulation-capability-registry","game-engine-capability-matrix","video-engine-registry","3d-creation","modelling",
"sculpting","texturing","rendering","asset-management","pipeline-import-hash-duplicate-check-metadata-analysis-route",
"open-datasets-medleydb-musdb18-slakh-maestro-nsynth-fsd50k","spatial-surround-audio","ambisonics-binaural-hrtf",
"iem-suite-sparta","stem-separation-demucs-open-unmix-spleeter-mdx","voice-vocal-processing","podcast-workspace-rss-podcasting-2-0-chapters-transcripts",
"mastering-lufs-true-peak-eq-dynamics-limiting-dithering-metadata","aax-pro-tools-interoperability",
"plugin-host-carla-reference-crash-isolation-sandboxing-bridging","first-party-plugin-api","plugin-format-standards",
"midi-deep-dive","audio-i-o-backends","synthesis-taxonomy","open-synth-repositories","drum-machine-beat-systems",
"piano-roll-workflow","score-notation","audio-editing","time-stretch-pitch-shift","audio-analysis",
"essentia-aubio-librosa-vamps-sonic-visualiser","mixer-routing-modulation-automation","hardware-integration","sync",
"audio-formats","project-interchange","podcast-workspace","mastering","spatial-audio","rights-identifiers",
"audio-asset-database","audio-dump-pipeline","open-datasets","benchmark-methodology","plugin-test-host-sdk",
"plugin-manifest-sandbox","first-party-plugin-api","genesis-agent-bridge-universal-bridge-integration","hardware-issue-corpus"
)

# Combine all sources
Write-Host "Collecting all repo names across workstreams..."
$allSources = @($source1 + $source2 + $source3 + $source4 + $source5 + $source5b + $source6 + $source7)

# Deduplicate and create candidate map
Write-Host "Deduplicating repo names..."
$uniqueNames = $allSources | Sort-Object -Unique

Write-Host "Total unique repo names across all sources: $($uniqueNames.Count)"

# Create candidate entries with canonical naming
Write-Host "Generating candidate map entries..."
$candidateMap = @{}
foreach ($name in $uniqueNames) {
    $canonicalName = $name
    $repoType = "UNKNOWN"
    $status = "CANDIDATE"
    $visibility = "private"
    $license = "UNKNOWN"
    
    # Map to types based on name patterns (case-insensitive)
    $nameLower = $name.ToLower()
    
    if ($nameLower -match "^jayprophit/") {
        $repoType = "SDK"
        $status = "DEVELOPMENT_ACTIVE"
        $visibility = "private"
        $license = "MIT"
    } elseif ($nameLower -match "^(adobe|microsoft|autodesk)/") {
        $repoType = "APP"
        $status = "CANDIDATE"
        $visibility = "private"
        $license = "PROPRIETARY"
    } elseif ($nameLower -match "^(unity|unreal-engine|godot-engine|cryengine|langyard)/") {
        $repoType = "ENGINE"
        $status = "CANDIDATE"
        $visibility = "private"
        $license = "PROPRIETARY/MIT"
    } elseif ($nameLower -match "^ffmpeg$" -or $nameLower -match "^gstreamer$") {
        $repoType = "ENGINE"
        $status = "DEVELOPMENT_ACTIVE"
        $visibility = "public"
        $license = "GPL/LGPL"
    } elseif ($nameLower -match "^(clap-plugin-host|vst3-sdk|au-plugin-bridge|lv2-plugin-registry|aax-bridge)$") {
        $repoType = "SDK"
        $status = "CANDIDATE"
        $visibility = "private"
        $license = "PROPRIETARY/MIT"
    } elseif ($nameLower -match "^poietek/") {
        $repoType = "ENGINE"
        $status = "DEVELOPMENT_ACTIVE"
        $visibility = "private"
        $license = "MIT"
    } elseif ($nameLower -match "^(surge-synth|dexed-synth|vitalium-synth|helm-synth)$") {
        $repoType = "ENGINE"
        $status = "DEVELOPMENT_ACTIVE"
        $visibility = "private"
        $license = "MIT"
    } elseif ($nameLower -match "^(drum.machine|piano-roll)(.*)$" -or $nameLower -match "^(drum-machine|piano-roll)(.*)$") {
        $repoType = "APP"
        $status = "CANDIDATE"
        $visibility = "private"
        $license = "MIT"
    } elseif ($nameLower -match "^(stem-separation|voice-processing)(.*)$") {
        $repoType = "SERVICE"
        $status = "CANDIDATE"
        $visibility = "private"
        $license = "MIT"
    } elseif ($nameLower -match "^(unity/analytics|unity/collaboration)$") {
        $repoType = "SERVICE"
        $status = "CANDIDATE"
        $visibility = "private"
        $license = "PROPRIETARY"
    } elseif ($nameLower -match "^(ide|store|os)." -or $nameLower -match "^(aetherius-(ide|store|os))") {
        $repoType = "APP"
        $status = "CANDIDATE"
        $visibility = "private"
        $license = "MIT"
    } else {
        $repoType = "UNKNOWN"
        $status = "CANDIDATE"
        $visibility = "private"
        $license = "UNKNOWN"
    }
    
    $candidateEntry = [pscustomobject]@{
        REPO_NAME = $name
        CANONICAL_NAME = $canonicalName
        REPO_TYPE = $repoType
        STATUS = $status
        VISIBILITY = $visibility
        LICENSE = $license
        NOTES = "Generated from AETHERIUS-REPOSITORY-PROVISIONING workstream Sub-task F"
    }
    
    $candidateMap[$name] = $candidateEntry
}

# Write the candidate map
$mapEntries = $candidateMap.Values | Sort-Object -Property @{Expression = { $_.REPO_TYPE }}
$mapEntries | ConvertTo-Json -Depth 10 | Out-File -FilePath 'C:\Users\jpowe\Desktop\Agent-Bridge\candidate_repository_map.json' -Encoding UTF8

# Write summary
$typeCounts = @{}
foreach ($entry in $mapEntries) {
    $t = $entry.REPO_TYPE
    if (-not $typeCounts.ContainsKey($t)) { $typeCounts.$t = 0 }
    $typeCounts.$t++
}

Write-Host "=== Candidate Repository Map Complete ==="
Write-Host "Total unique candidate repos: $($uniqueNames.Count)"
Write-Host "=== Summary by TYPE ==="
foreach ($kv in $typeCounts.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}
Write-Host "Output: C:\Users\jpowe\Desktop\Agent-Bridge\candidate_repository_map.json"