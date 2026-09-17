# Repository Classification for AETHERIUS-REPOSITORY-PROVISIONING
# Sub-task B: Classify all jayprophit repositories

# Classification schema:
# - ACTIVE_CANONICAL: Primary, actively maintained first-party repos
# - ACTIVE_SUPPORT: Actively maintained support/utility repos
# - MIGRATION_SOURCE: Repos being migrated to new system
# - HISTORICAL: Historical/archive repos
# - LEARNING: Repos for learning/research purposes
# - REFERENCE: Reference/repo for design patterns
# - FORK: Forked repositories from other organizations
# - DUPLICATE: Duplicate/redundant repos
# - OBSOLETE: Deprecated/obsolete repos
# - UNKNOWN: Category not clearly determined

# Read the categorized inventory
$catJson = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\repos_categorization.json' | ConvertFrom-Json

# Known forked repo names (from the forks category)
$knownForkNames = @(
    "n8n", "meson", "protobuf", "tree-sitter", "tock", "ruff",
    "9front", "CMake", "grafana", "libarchive", "systemd", "bootc", "grpc",
    "uv", "pyinstaller", "coreboot", "moby", "executorch", "llvm-project",
    "temporal", "OpenROAD", "ultralytics", "vllm", "verilator", "yugabyte-db",
    "ray", "rxdb", "tvm", "SU2", "core", "rtaudio", "csound", "kicad-source-mirror",
    "mfem", "FreeCAD", "dolfinx", "esphome", "seL4", "nextflow", "qiskit",
    "emscripten", "drake", "gtsam", "cantera", "blender", "iree", "ceph",
    "godot-official", "vscode", "cesium", "redox", "PX4-Autopilot", "IfcOpenShell",
    "pipewire", "kokkos", "verible", "colmap", "zephyr", "SatDump", "circt",
    "arrow", "sqlite", "ggml", "cva6", "cocotb", "aiida-core", "syncthing",
    "gvisor", "moose", "IsaacLab", "xls", "openscad", "litex", "seaweedfs",
    "cFS", "webots", "pennylane", "ardupilot", "connectedhomeip", "keycloak",
    "scylladb", "valkey", "u-boot", "diffusers", "c2pa-rs", "openthread",
    "timescaledb", "openfhe-development", "k3s", "opentitan", "qemu",
    "depthai-core", "containerd", "EnergyPlus", "helm", "playwright", "ansible",
    "vcpkg", "opentelemetry-collector", "supercollider", "edk2", "rust-libp2p",
    "gatk", "nats-server", "bazel", "tfhe-rs", "PDAL", "crewAI", "openmm",
    "nrn", "wasmtime", "code-server", "dagster", "petsc", "openbao", "theia",
    "llama_index", "compose", "renode", "conan", "firecracker", "warpx",
    "riscv-isa-sim", "CuraEngine", "DeepLabCut", "spikeinterface", "litellm",
    "zenoh", "prometheus", "lerobot", "scanpy", "nest-simulator", "yosys",
    "opensim-core", "chisel", "automerge", "A2A", "mem0", "ditto", "sofa",
    "pcl", "pymatgen-core", "genesis-world", "rtabmap", "alp-data", "inspector",
    "onnxruntime", "llama.cpp", "sherpa-onnx", "ollama", "openvsx", "agent-framework",
    "phone-harness", "mujoco", "mne-python", "neo4j", "langgraph", "Orekit",
    "scipy-community", "tracktion_engine", "tauri", "samtools", "scikit-bio",
    "peft", "pyOCD", "python-sdk"
)

# Classify based on existing categories
$classifications = @()

# Personal projects -> ACTIVE_CANONICAL
Write-Host "Classifying personal_projects ($($catJson.personal_projects.Count) repos)..."
foreach ($proj in $catJson.personal_projects) {
    $isKnownFork = $false
    foreach ($forkName in $knownForkNames) {
        if ($proj.name.ToLower() -contains "$forkName") {
            $isKnownFork = $true
            break
        }
    }
    
    $classification = "ACTIVE_CANONICAL"
    if ($isKnownFork) {
        $classification = "FORK"
    }
    
    $classifications += [pscustomobject]@{
        repo_name = $proj.name
        existing_category = "personal_projects"
        new_classification = $classification
        description = $proj.description
        visibility = $proj.visibility
        fork = $proj.fork
        date = $proj.date
    }
}

# Forks -> FORK classification
Write-Host "Classifying forks ($($catJson.forks.Count) repos)..."
foreach ($fork in $catJson.forks) {
    $classifications += [pscustomobject]@{
        repo_name = $fork.name
        existing_category = "forks"
        new_classification = "FORK"
        description = $fork.description
        visibility = $fork.visibility
        fork = $fork.fork
        date = $fork.date
    }
}

# Standalone non-fork -> LEARNING
Write-Host "Classifying standalone_non_fork ($($catJson.standalone_non_fork.Count) repos)..."
foreach ($standalone in $catJson.standalone_non_fork) {
    $classifications += [pscustomobject]@{
        repo_name = $standalone.name
        existing_category = "standalone_non_fork"
        new_classification = "LEARNING"
        description = $standalone.description
        visibility = $standalone.visibility
        fork = $standalone.fork
        date = $standalone.date
    }
}

# Also read the local github_repos.txt and classify those not already classified
Write-Host "Reading local github_repos.txt for classification..."
$localRepos = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\github_repos.txt' | ForEach-Object { 
    $_ -split '\t' | Select-Object -First 2 
} | Sort-Object -Unique

# Get already classified repo names
$alreadyClassified = $classifications | Select-Object -ExpandProperty repo_name

$newClassifications = @()
foreach ($repo in $localRepos) {
    $repoName = $repo[0]  # first column is owner/repo
    if (-not ($alreadyClassified -contains $repoName)) {
        # Default classification: UNKNOWN
        # Check if it matches known fork patterns by name
        $isKnownFork = $false
        foreach ($forkName in $knownForkNames) {
            if ($repoName.ToLower() -contains $forkName.ToLower()) {
                $isKnownFork = $true
                break
            }
        }
        
        $classification = "UNKNOWN"
        if ($isKnownFork) {
            $classification = "FORK"
        } elseif ($repoName -match "^\Qjayprophit/Aetherial\E" -or $repoName -match "^\Qjayprophit/genesis-world\E") {
            $classification = "LEARNING"
        } elseif ($repoName -match "^\Qjayprophit/Agent-Bridge\E" -or $repoName -match "^\Qjayprophit/genesis\E") {
            $classification = "ACTIVE_CANONICAL"
        }
        
        $newClassifications += [pscustomobject]@{
            repo_name = $repoName
            existing_category = "local_txt"
            new_classification = $classification
        }
    }
}

# Combine all classifications
$allClassifications = $classifications + $newClassifications | Sort-Object -Property new_classification

# Write the classification report
$allClassifications | ConvertTo-Json -Depth 10 | Out-File -FilePath 'C:\Users\jpowe\Desktop\Agent-Bridge\repository_classification.json' -Encoding UTF8

# Generate summary statistics
$stats = @{
    ACTIVE_CANONICAL = ($allClassifications | Where-Object { $_.new_classification -eq "ACTIVE_CANONICAL" }).Count
    ACTIVE_SUPPORT = ($allClassifications | Where-Object { $_.new_classification -eq "ACTIVE_SUPPORT" }).Count
    MIGRATION_SOURCE = ($allClassifications | Where-Object { $_.new_classification -eq "MIGRATION_SOURCE" }).Count
    HISTORICAL = ($allClassifications | Where-Object { $_.new_classification -eq "HISTORICAL" }).Count
    LEARNING = ($allClassifications | Where-Object { $_.new_classification -eq "LEARNING" }).Count
    REFERENCE = ($allClassifications | Where-Object { $_.new_classification -eq "REFERENCE" }).Count
    FORK = ($allClassifications | Where-Object { $_.new_classification -eq "FORK" }).Count
    DUPLICATE = ($allClassifications | Where-Object { $_.new_classification -eq "DUPLICATE" }).Count
    OBSOLETE = ($allClassifications | Where-Object { $_.new_classification -eq "OBSOLETE" }).Count
    UNKNOWN = ($allClassifications | Where-Object { $_.new_classification -eq "UNKNOWN" }).Count
}

Write-Host "=== Repository Classification Summary ==="
Write-Host "ACTIVE_CANONICAL: $($stats.ACTIVE_CANONICAL)"
Write-Host "ACTIVE_SUPPORT: $($stats.ACTIVE_SUPPORT)"
Write-Host "MIGRATION_SOURCE: $($stats.MIGRATION_SOURCE)"
Write-Host "HISTORICAL: $($stats.HISTORICAL)"
Write-Host "LEARNING: $($stats.LEARNING)"
Write-Host "REFERENCE: $($stats.REFERENCE)"
Write-Host "FORK: $($stats.FORK)"
Write-Host "DUPLICATE: $($stats.DUPLICATE)"
Write-Host "OBSOLETE: $($stats.OBSOLETE)"
Write-Host "UNKNOWN: $($stats.UNKNOWN)"
Write-Host "Total: $($stats.ACTIVE_CANONICAL + $stats.ACTIVE_SUPPORT + $stats.MIGRATION_SOURCE + $stats.HISTORICAL + $stats.LEARNING + $stats.REFERENCE + $stats.FORK + $stats.DUPLICATE + $stats.OBSOLETE + $stats.UNKNOWN)"

Write-Host "Classification complete. Output: C:\Users\jpowe\Desktop\Agent-Bridge\repository_classification.json"