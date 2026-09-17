# Research Ingestion for AETHERIUS-REPOSITORY-PROVISIONING
# Sub-task E: Ingest planned apps from Adobe/Autodesk/Microsoft research,
# Simulation/Game/Video research, and Poietek research

# Read the existing registry
$registry = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\AETHERIUS_REPOSITORY_REGISTRY.json' | ConvertFrom-Json

# New repository entries to ingest from research workstreams
$newRepos = @()

# === Adobe/Autodesk/Microsoft 365 Research ===
# Enterprise productivity and creative suite applications
$adobeMicrosoftResearch = @(
    @{ repo_name = "adobe/photoshop"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "CREATIVE" },
    @{ repo_name = "adobe/illustrator"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "CREATIVE" },
    @{ repo_name = "adobe/premiere-pro"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "CREATIVE" },
    @{ repo_name = "adobe/after-effects"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "CREATIVE" },
    @{ repo_name = "adobe/dreamweaver"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "CREATIVE" },
    @{ repo_name = "autodesk/autoCAD"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "ENGINEERING" },
    @{ repo_name = "autodesk/revit"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "ENGINEERING" },
    @{ repo_name = "autodesk/maya"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "CREATIVE" },
    @{ repo_name = "autodesk/3ds-max"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "CREATIVE" },
    @{ repo_name = "autodesk/fusion-360"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "ENGINEERING" },
    @{ repo_name = "microsoft/365"; new_type = "SERVICE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "PRODUCTIVITY" },
    @{ repo_name = "microsoft/teams"; new_type = "SERVICE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "COMMUNICATION" },
    @{ repo_name = "microsoft/office"; new_type = "SERVICE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "PRODUCTIVITY" }
)

# === Simulation/Game/Video Engine Research ===
$simGameVideoResearch = @(
    @{ repo_name = "unity/editor"; new_type = "ENGINE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "GAME ENGINE" },
    @{ repo_name = "unity/analytics"; new_type = "SERVICE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "GAME ENGINE" },
    @{ repo_name = "unity/collaboration"; new_type = "SERVICE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "GAME ENGINE" },
    @{ repo_name = "unreal-engine"; new_type = "ENGINE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "GAME ENGINE" },
    @{ repo_name = "godot-engine"; new_type = "ENGINE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "MIT"; new_domain = "GAME ENGINE" },
    @{ repo_name = "cryengine"; new_type = "ENGINE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "GAME ENGINE" },
    @{ repo_name = "langyard"; new_type = "ENGINE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "GAME ENGINE" },
    @{ repo_name = "ffmpeg"; new_type = "ENGINE"; new_status = "DEVELOPMENT_ACTIVE"; new_visibility = "public"; new_license = "GPL-3.0"; new_domain = "VIDEO ENGINE" },
    @{ repo_name = "gstreamer"; new_type = "ENGINE"; new_status = "DEVELOPMENT_ACTIVE"; new_visibility = "public"; new_license = "LGPL-2.1"; new_domain = "VIDEO ENGINE" },
    @{ repo_name = "avid"; new_type = "ENGINE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "VIDEO EDITING" },
    @{ repo_name = "da-vinci-resolve"; new_type = "ENGINE"; new_status = "DEVELOPMENT_ACTIVE"; new_visibility = "public"; new_license = "PROPRIETARY"; new_domain = "VIDEO EDITING" },
    @{ repo_name = "nuke"; new_type = "ENGINE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "COMPOSITING" }
)

# === Poietek Research ===
# Extend existing poietek entries with specific plugin format repos
$poietekExtends = @(
    @{ repo_name = "clap-plugin-host"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "MIT"; new_domain = "AUDIO" },
    @{ repo_name = "vst3-sdk"; new_type = "SDK"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "AUDIO" },
    @{ repo_name = "au-plugin-bridge"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "MIT"; new_domain = "AUDIO" },
    @{ repo_name = "lv2-plugin-registry"; new_type = "EXTENSION"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "MIT"; new_domain = "AUDIO" },
    @{ repo_name = "aax-bridge"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "PROPRIETARY"; new_domain = "AUDIO" },
    @{ repo_name = "surge-synth"; new_type = "ENGINE"; new_status = "DEVELOPMENT_ACTIVE"; new_visibility = "private"; new_license = "MIT"; new_domain = "AUDIO" },
    @{ repo_name = "dexed-synth"; new_type = "ENGINE"; new_status = "DEVELOPMENT_ACTIVE"; new_visibility = "private"; new_license = "MIT"; new_domain = "AUDIO" },
    @{ repo_name = "vitalium-synth"; new_type = "ENGINE"; new_status = "DEVELOPMENT_ACTIVE"; new_visibility = "private"; new_license = "MIT"; new_domain = "AUDIO" },
    @{ repo_name = "helm-synth"; new_type = "ENGINE"; new_status = "DEVELOPMENT_ACTIVE"; new_visibility = "private"; new_license = "MIT"; new_domain = "AUDIO" },
    @{ repo_name = "drum-machine-kit"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "MIT"; new_domain = "AUDIO" },
    @{ repo_name = "piano-roll-editor"; new_type = "APP"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "MIT"; new_domain = "AUDIO" },
    @{ repo_name = "stem-separation-engine"; new_type = "SERVICE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "MIT"; new_domain = "AUDIO" },
    @{ repo_name = "voice-processing-engine"; new_type = "SERVICE"; new_status = "CANDIDATE"; new_visibility = "private"; new_license = "MIT"; new_domain = "AUDIO" }
)

# Process Adobe/Microsoft research repos
Write-Host "Ingesting Adobe/Autodesk/Microsoft research repos..."
foreach ($repo in $adobeMicrosoftResearch) {
    $repoId = "commercial/" + $repo.repo_name -replace '/', '/'
    # Check if already exists
    if (-not ($registry | Where-Object { $_.NAME -eq $repo.repo_name })) {
        $newRepo = [pscustomobject]@{
            REPO_ID = $repoId
            NAME = $repo.repo_name
            TYPE = $repo.new_type
            STATUS = $repo.new_status
            VISIBILITY = $repo.new_visibility
            LICENSE = $repo.new_license
            DEPENDENCIES = @()
            PROVENANCE = @{
                ORIGINAL_OWNER = "commercial-research"
                ORIGINAL_DATE = (Get-Date).ToString("o")
                CLASSIFIED_DATE = (Get-Date).ToString("o")
                CLASSIFICATION_SCHEME = "AETHERIUS_REPOSITORY_PROVISIONING_v1"
            }
            CREATED_DATE = (Get-Date).ToString("o")
            LAST_UPDATED = (Get-Date).ToString("o")
            DESCRIPTION = ""
            DOCUMENTATION = ""
            TESTING_STATUS = "pending"
            OWNER = "commercial-research"
            TAGS = @($repo.new_domain)
        }
        $registry += $newRepo
    }
}

# Process Simulation/Game/Video research repos
Write-Host "Ingesting Simulation/Game/Video research repos..."
foreach ($repo in $simGameVideoResearch) {
    $repoId = "enginestudio/" + $repo.repo_name -replace '/', '/'
    if (-not ($registry | Where-Object { $_.NAME -eq $repo.repo_name })) {
        $newRepo = [pscustomobject]@{
            REPO_ID = $repoId
            NAME = $repo.repo_name
            TYPE = $repo.new_type
            STATUS = $repo.new_status
            VISIBILITY = $repo.new_visibility
            LICENSE = $repo.new_license
            DEPENDENCIES = @()
            PROVENANCE = @{
                ORIGINAL_OWNER = "sim-research"
                ORIGINAL_DATE = (Get-Date).ToString("o")
                CLASSIFIED_DATE = (Get-Date).ToString("o")
                CLASSIFICATION_SCHEME = "AETHERIUS_REPOSITORY_PROVISIONING_v1"
            }
            CREATED_DATE = (Get-Date).ToString("o")
            LAST_UPDATED = (Get-Date).ToString("o")
            DESCRIPTION = ""
            DOCUMENTATION = ""
            TESTING_STATUS = "pending"
            OWNER = "sim-research"
            TAGS = @($repo.new_domain)
        }
        $registry += $newRepo
    }
}

# Process Poietek research extensions
Write-Host "Ingesting Poietek research repos..."
foreach ($repo in $poietekExtends) {
    $repoId = "poietek/" + $repo.repo_name -replace '/', '/'
    if (-not ($registry | Where-Object { $_.NAME -eq $repo.repo_name })) {
        $newRepo = [pscustomobject]@{
            REPO_ID = $repoId
            NAME = $repo.repo_name
            TYPE = $repo.new_type
            STATUS = $repo.new_status
            VISIBILITY = $repo.new_visibility
            LICENSE = $repo.new_license
            DEPENDENCIES = @()
            PROVENANCE = @{
                ORIGINAL_OWNER = "poietek-research"
                ORIGINAL_DATE = (Get-Date).ToString("o")
                CLASSIFIED_DATE = (Get-Date).ToString("o")
                CLASSIFICATION_SCHEME = "AETHERIUS_REPOSITORY_PROVISIONING_v1"
            }
            CREATED_DATE = (Get-Date).ToString("o")
            LAST_UPDATED = (Get-Date).ToString("o")
            DESCRIPTION = ""
            DOCUMENTATION = ""
            TESTING_STATUS = "pending"
            OWNER = "poietek-research"
            TAGS = @($repo.new_domain)
        }
        $registry += $newRepo
    }
}

# Write updated registry
Write-Host "Writing updated registry with $($registry.Count) entries..."
$registry | ConvertTo-Json -Depth 12 | Out-File -FilePath 'C:\Users\jpowe\Desktop\Agent-Bridge\AETHERIUS_REPOSITORY_REGISTRY.json' -Encoding UTF8

# Write summary
$typeStats = @{}
$statusStats = @{}
foreach ($entry in $registry) {
    $t = $entry.TYPE
    $s = $entry.STATUS
    if (-not $typeStats.ContainsKey($t)) { $typeStats.$t = 0 }
    if (-not $statusStats.ContainsKey($s)) { $statusStats.$s = 0 }
    $typeStats.$t++
    $statusStats.$s++
}

Write-Host "=== Research Ingestion Complete ==="
Write-Host "Total repos in registry: $($registry.Count)"
Write-Host "=== Summary by TYPE ==="
foreach ($kv in $typeStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}
Write-Host "=== Summary by STATUS ==="
foreach ($kv in $statusStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}
Write-Host "Output: C:\Users\jpowe\Desktop\Agent-Bridge\AETHERIUS_REPOSITORY_REGISTRY.json"