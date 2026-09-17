# Sub-task G: Refined Deduplication + Repository Threshold + Canonical Naming + Creation Queue

# Read deduplicated candidates
$candidates = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\deduplicated_candidate_registry.json' | ConvertFrom-Json

# Read existing registry
$existingRegistry = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\AETHERIUS_REPOSITORY_REGISTRY.json' | ConvertFrom-Json
$jayprophitRepos = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\github_repos.txt' | ForEach-Object { $_ -split '\t' | Select-Object -First 1 } | Sort-Object -Unique

# Refined shared components - only well-defined ones
$verifiedSharedComponents = @(
    @{ NAME = "Aetherius Math"; KEYWORDS = @("math", "mathematics"); TYPE = "LIBRARY"; DOMAIN = "SHARED"; PARENT = "AETHERIUS_SHARED" }
    @{ NAME = "Aetherius Units"; KEYWORDS = @("units", "unit", "measurement"); TYPE = "LIBRARY"; DOMAIN = "SHARED"; PARENT = "AETHERIUS_SHARED" }
    @{ NAME = "Aetherius Geometry"; KEYWORDS = @("geometry", "geom", "cad.geom"); TYPE = "ENGINE"; DOMAIN = "ENGINEERING"; PARENT = "AETHERIUS_CAD" }
    @{ NAME = "Aetherius Mesh"; KEYWORDS = @("mesh", "meshing"); TYPE = "ENGINE"; DOMAIN = "ENGINEERING"; PARENT = "AETHERIUS_CAD" }
    @{ NAME = "Aetherius Materials"; KEYWORDS = @("material", "materials", "mat.props"); TYPE = "SERVICE"; DOMAIN = "ENGINEERING"; PARENT = "MAT" }
    @{ NAME = "Aetherius Rendering"; KEYWORDS = @("render", "rendering", "raster", "ray.trace"); TYPE = "ENGINE"; DOMAIN = "GAMING"; PARENT = "AETHERIUS_GAME_ENGINE" }
    @{ NAME = "Aetherius Colour"; KEYWORDS = @("colour", "color", "colourspace", "icc", "aces"); TYPE = "ENGINE"; DOMAIN = "CREATIVE"; PARENT = "AETHERIUS_CREATIVE" }
    @{ NAME = "Aetherius Audio"; KEYWORDS = @("audio.engine", "dsp.engine"); TYPE = "ENGINE"; DOMAIN = "AUDIO"; PARENT = "POIETEK" }
    @{ NAME = "Aetherius Video"; KEYWORDS = @("video.engine", "codec.engine"); TYPE = "ENGINE"; DOMAIN = "VIDEO"; PARENT = "AETHERIUS_MEDIA" }
    @{ NAME = "Aetherius Media"; KEYWORDS = @("media.engine", "timeline.engine"); TYPE = "ENGINE"; DOMAIN = "VIDEO"; PARENT = "AETHERIUS_MEDIA" }
    @{ NAME = "Aetherius Timeline"; KEYWORDS = @("timeline", "keyframe", "automation"); TYPE = "ENGINE"; DOMAIN = "VIDEO"; PARENT = "AETHERIUS_MEDIA" }
    @{ NAME = "Aetherius Animation"; KEYWORDS = @("animation.engine", "rigging", "skinning"); TYPE = "ENGINE"; DOMAIN = "GAMING"; PARENT = "AETHERIUS_GAME_ENGINE" }
    @{ NAME = "Aetherius Physics"; KEYWORDS = @("physics.engine", "rigid.body", "collision"); TYPE = "ENGINE"; DOMAIN = "GAMING"; PARENT = "AETHERIUS_GAME_ENGINE" }
    @{ NAME = "Aetherius Simulation"; KEYWORDS = @("simulation.engine", "solver", "fea", "cfd"); TYPE = "ENGINE"; DOMAIN = "ENGINEERING"; PARENT = "AETHERIUS_CAD" }
    @{ NAME = "Aetherius Database"; KEYWORDS = @("database.engine", "storage.engine"); TYPE = "ENGINE"; DOMAIN = "SYSTEM"; PARENT = "AETHERIUS_OS" }
    @{ NAME = "Aetherius Storage"; KEYWORDS = @("storage", "file.system", "object.store"); TYPE = "SERVICE"; DOMAIN = "DATA"; PARENT = "AETHERIUS_FILES" }
    @{ NAME = "Aetherius Sync"; KEYWORDS = @("sync.engine", "replication", "crdt"); TYPE = "SERVICE"; DOMAIN = "CLOUD"; PARENT = "AETHERIUS_CLOUD" }
    @{ NAME = "Aetherius Search"; KEYWORDS = @("search.engine", "index", "vector.search"); TYPE = "SERVICE"; DOMAIN = "DATA"; PARENT = "AETHERIUS_FILES" }
    @{ NAME = "Aetherius Identity"; KEYWORDS = @("identity", "auth", "sso", "oidc"); TYPE = "SERVICE"; DOMAIN = "SECURITY"; PARENT = "AETHERIUS_SECURITY" }
    @{ NAME = "Aetherius Permissions"; KEYWORDS = @("permission", "acl", "rbac", "policy"); TYPE = "SERVICE"; DOMAIN = "SECURITY"; PARENT = "AETHERIUS_SECURITY" }
    @{ NAME = "Aetherius Workflow"; KEYWORDS = @("workflow.engine", "orchestration", "dag"); TYPE = "ENGINE"; DOMAIN = "DEVELOPER"; PARENT = "AETHERIUS_IDE" }
    @{ NAME = "Aetherius Collaboration"; KEYWORDS = @("collab.engine", "realtime", "coauthor"); TYPE = "SERVICE"; DOMAIN = "COMMUNICATION"; PARENT = "AETHERIUS_COMMUNICATION" }
    @{ NAME = "Aetherius Telemetry"; KEYWORDS = @("telemetry", "metric", "trace", "observability"); TYPE = "SERVICE"; DOMAIN = "DEVELOPER"; PARENT = "AETHERIUS_IDE" }
    @{ NAME = "Aetherius Plugin SDK"; KEYWORDS = @("plugin.sdk", "plugin.api", "extension.api"); TYPE = "SDK"; DOMAIN = "DEVELOPER"; PARENT = "AETHERIUS_IDE" }
    @{ NAME = "Aetherius Project Model"; KEYWORDS = @("project.model", "session", "workspace"); TYPE = "LIBRARY"; DOMAIN = "DEVELOPER"; PARENT = "AETHERIUS_IDE" }
    @{ NAME = "Aetherius Asset Engine"; KEYWORDS = @("asset.engine", "asset.pipeline", "import.export"); TYPE = "ENGINE"; DOMAIN = "CREATIVE"; PARENT = "AETHERIUS_CREATIVE" }
)

# Function to apply repository threshold
function Test-RepositoryThreshold($candidate) {
    $type = $candidate.COMPONENT_TYPE
    $domain = $candidate.DOMAIN
    $name = $candidate.PROPOSED_NAME
    
    # Always create repo for these types if they're substantial
    if ($type -in @("APPLICATION", "ENGINE", "SERVICE", "SDK", "PLUGIN", "EXTENSION", "ADAPTER", "DRIVER")) {
        # Check if it's too trivial
        $trivialPatterns = @("^test", "^example", "^demo", "^sample", "^template", "^hello", "^placeholder", "^dummy", "^mock", "^stub", "^fake", "^temp", "^tmp")
        foreach ($p in $trivialPatterns) {
            if ($name.ToLower() -match $p) { return $false }
        }
        return $true
    }
    
    # For LIBRARY, FORMAT_MODULE, DATA, SPECIFICATION - only if independently versioned
    if ($type -in @("LIBRARY", "FORMAT_MODULE", "DATA", "SPECIFICATION")) {
        # These need explicit justification
        return $false  # Default to false, require explicit approval
    }
    
    # CLI, TEMPLATE, TEST_SUITE, REFERENCE_FORK - generally no repo
    return $false
}

# Function to assign canonical name
function Get-CanonicalName($candidate, $isShared) {
    $name = $candidate.PROPOSED_NAME
    $type = $candidate.COMPONENT_TYPE
    $parent = $candidate.PARENT_PROJECT
    
    if ($isShared) {
        return $candidate.NORMALIZED_NAME
    }
    
    # Determine naming family
    $family = "aetherius"
    switch ($parent) {
        "POIETEK" { $family = "poietek" }
        "GENESIS" { $family = "genesis" }
        "UNIVERSAL_BRIDGE" { $family = "universal-bridge" }
        "ATHENA" { $family = "athena" }
        "MAT" { $family = "mat" }
        "AETHERIUS_GAME_ENGINE" { $family = "aetherius" }
        "AETHERIUS_MEDIA" { $family = "aetherius" }
        "AETHERIUS_CAD" { $family = "aetherius" }
        "AETHERIUS_CREATIVE" { $family = "aetherius" }
        "AETHERIUS_OFFICE" { $family = "aetherius" }
        "AETHERIUS_IDE" { $family = "aetherius" }
        "AETHERIUS_SHARED" { $family = "aetherius" }
        default { $family = "aetherius" }
    }
    
    # Normalize the name
    $baseName = $name.ToLower()
        -replace '^jayprophit/', ''
        -replace '^adobe/', ''
        -replace '^microsoft/', ''
        -replace '^autodesk/', ''
        -replace '^unity/', ''
        -replace '^poietek/', ''
        -replace '^aetherius-', ''
        -replace '^poietek-', ''
        -replace '^genesis-', ''
        -replace '^universal-bridge-', ''
        -replace '^atheena-', ''
        -replace '[^a-z0-9]+', '-'
        -replace '^-+|-+$', ''
    
    # Remove common suffixes that don't add meaning
    $baseName = $baseName -replace '-(engine|service|sdk|app|lib|tool|manager|handler|controller|provider|factory|builder|helper|util|utils|core|base|common|shared|internal|public|private|impl|interface|abstract|concrete|default|standard|extended|advanced|basic|simple|complex|full|mini|micro|nano|pico|femto|atto|zepto|yocto)$', ''
    
    if ($baseName -eq $family) {
        return "$family-$type".ToLower()
    }
    
    return "$family-$baseName"
}

# Function to check name collisions
function Test-NameCollision($canonicalName, $existingRegistry, $jayprophitRepos) {
    $collisions = @()
    
    # Check existing registry
    $existingNames = $existingRegistry | ForEach-Object { $_.NAME }
    if ($existingNames -contains $canonicalName) {
        $collisions += "EXISTING_REGISTRY: $canonicalName"
    }
    
    # Check jayprophit repos
    if ($jayprophitRepos -contains "jayprophit/$canonicalName") {
        $collisions += "JAYPROPHIT_GITHUB: jayprophit/$canonicalName"
    }
    
    # Check package identifiers (common package names)
    $commonPackages = @("math", "geometry", "units", "mesh", "render", "audio", "video", "database", "storage", "sync", "search", "identity", "permissions", "workflow", "telemetry", "plugin-sdk", "asset", "simulation", "physics", "animation", "rendering", "colour", "colour", "materials")
    if ($commonPackages -contains $canonicalName) {
        $collisions += "COMMON_PACKAGE: $canonicalName"
    }
    
    return $collisions
}

# Process each candidate
$finalCandidates = @()
$creationQueue = @()
$priorityCounter = 1

foreach ($candidate in $candidates) {
    # Check if shared component
    $isShared = $false
    $sharedInfo = $null
    foreach ($sc in $verifiedSharedComponents) {
        $match = $true
        foreach ($kw in $sc.KEYWORDS) {
            if (-not ($candidate.PROPOSED_NAME.ToLower() -match $kw)) {
                $match = $false
                break
            }
        }
        if ($match) {
            $isShared = $true
            $sharedInfo = $sc
            break
        }
    }
    
    # Apply repository threshold
    $repoRequired = Test-RepositoryThreshold $candidate
    
    if (-not $repoRequired) {
        $candidate | Add-Member -MemberType NoteProperty -Name "FINAL_ACTION" -Value "NOT_REPOSITORY" -Force
        $candidate | Add-Member -MemberType NoteProperty -Name "FINAL_RATIONALE" -Value "Below repository threshold for type $($candidate.COMPONENT_TYPE)" -Force
        $finalCandidates += $candidate
        continue
    }
    
    # Assign canonical name
    $canonicalName = Get-CanonicalName $candidate $isShared
    $candidate.CANONICAL_NAME = $canonicalName
    
    # Check name collisions
    $collisions = Test-NameCollision $canonicalName $existingRegistry $jayprophitRepos
    $candidate.NAME_COLLISIONS = $collisions
    
    if ($collisions.Count -gt 0) {
        # Try alternative naming
        $altName = "$canonicalName-v2"
        $altCollisions = Test-NameCollision $altName $existingRegistry $jayprophitRepos
        if ($altCollisions.Count -eq 0) {
            $candidate.CANONICAL_NAME = $altName
            $candidate.NAME_COLLISIONS = @()
            Write-Host "Name collision resolved: $canonicalName -> $altName"
        } else {
            $candidate | Add-Member -MemberType NoteProperty -Name "NAMING_RISK" -Value "HIGH" -Force
        }
    }
    
    # Determine creation priority
    $priority = "P6_RESEARCH_FUTURE"
    if ($candidate.PARENT_PROJECT -in @("GENESIS", "AGENT_BRIDGE", "AETHERIUS_IDE", "AETHERIUS_OS") -and $candidate.COMPONENT_TYPE -in @("ENGINE", "SERVICE", "SDK")) {
        $priority = "P0_CURRENT_CRITICAL_PATH"
    } elseif ($isShared -or $candidate.COMPONENT_TYPE -in @("ENGINE", "SERVICE", "SDK")) {
        $priority = "P1_FOUNDATION_SHARED"
    } elseif ($candidate.PARENT_PROJECT -in @("AETHERIUS_IDE", "GENESIS", "AGENT_BRIDGE", "UNIVERSAL_BRIDGE", "MAT", "POIETEK", "ATHENA") -and $candidate.COMPONENT_TYPE -in @("APPLICATION", "PLUGIN", "EXTENSION")) {
        $priority = "P2_ACTIVE_PROJECT_REQUIREMENT"
    } elseif ($candidate.COMPONENT_TYPE -eq "APPLICATION") {
        $priority = "P3_FIRST_PARTY_APP"
    } elseif ($candidate.COMPONENT_TYPE -in @("PLUGIN", "EXTENSION")) {
        $priority = "P4_PLUGIN_EXTENSION"
    } elseif ($candidate.COMPONENT_TYPE -in @("ADAPTER", "DRIVER", "LIBRARY", "FORMAT_MODULE")) {
        $priority = "P5_SPECIALIST"
    }
    
    # Determine action
    $action = $candidate.ACTION
    if ($candidate.EXISTING_LOCAL_REPO -or $candidate.EXISTING_GITHUB_REPO) {
        $action = "REUSE_EXISTING"
    } elseif ($isShared) {
        $action = "CREATE_SHARED"
    }
    
    # Repository required flag
    $repoRequired = $true
    
    # Determine visibility
    $visibility = "private"
    if ($candidate.EXISTING_GITHUB_REPO -and ($jayprophitRepos -contains "jayprophit/$($candidate.PROPOSED_NAME)" -or $jayprophitRepos -contains "jayprophit/$($candidate.CANONICAL_NAME)")) {
        # Check if public in existing
        $existing = $existingRegistry | Where-Object { $_.NAME -eq $candidate.PROPOSED_NAME }
        if ($existing -and $existing.VISIBILITY -eq "public") { $visibility = "public" }
    }
    
    # Update candidate
    $candidate.FINAL_ACTION = $action
    $candidate.PRIORITY = $priority
    $candidate.REPOSITORY_REQUIRED = $repoRequired
    $candidate.VISIBILITY = $visibility
    $candidate.IS_SHARED = $isShared
    
    $finalCandidates += $candidate
    
    # Add to creation queue if new repo needed
    if ($action -in @("CREATE_NEW", "CREATE_SHARED")) {
        $queueEntry = [pscustomobject]@{
            REPO_ID = "REPO-$($priorityCounter.ToString("000"))"
            CANONICAL_NAME = $canonicalName
            DISPLAY_NAME = $canonicalName -replace '-', ' ' | ForEach-Object { $_.Split(' ') | ForEach-Object { $_.Substring(0,1).ToUpper() + $_.Substring(1) } -join ' ' }
            TYPE = $candidate.COMPONENT_TYPE
            PARENT = $candidate.PARENT_PROJECT
            DOMAIN = $candidate.DOMAIN
            PRIORITY = $priority
            REPOSITORY_REQUIRED = $repoRequired
            LOCAL_CREATE = $true
            REMOTE_CREATE = $true
            VISIBILITY = $visibility
            SCAFFOLD_TEMPLATE = "$($candidate.COMPONENT_TYPE.ToLower())-template"
            DEPENDENCIES = $candidate.DEPENDENCIES
            SOURCE_REQUIREMENTS = $candidate.SOURCE_REQUIREMENTS
            RATIONALE = $candidate.RATIONALE
            STATUS = "CANDIDATE"
        }
        $creationQueue += $queueEntry
        $priorityCounter++
    }
}

# Write final candidate registry
$finalCandidates | ConvertTo-Json -Depth 10 | Out-File -FilePath 'C:\Users\jpowe\Desktop\Agent-Bridge\final_candidate_registry.json' -Encoding UTF8

# Write creation queue
$creationQueue | ConvertTo-Json -Depth 10 | Out-File -FilePath 'C:\Users\jpowe\Desktop\Agent-Bridge\repository_creation_queue.json' -Encoding UTF8

# Write summary
Write-Host "=== Final Candidate Registry Summary ==="
Write-Host "Total candidates after threshold: $($finalCandidates.Count)"
Write-Host "Candidates requiring repo creation: $($creationQueue.Count)"

$actionStats = @{}
foreach ($c in $finalCandidates) {
    $a = $c.FINAL_ACTION
    if (-not $actionStats.ContainsKey($a)) { $actionStats.$a = 0 }
    $actionStats.$a++
}
Write-Host "=== By FINAL_ACTION ==="
foreach ($kv in $actionStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}

$priorityStats = @{}
foreach ($c in $finalCandidates) {
    if ($c.PRIORITY) {
        $p = $c.PRIORITY
        if (-not $priorityStats.ContainsKey($p)) { $priorityStats.$p = 0 }
        $priorityStats.$p++
    }
}
Write-Host "=== By PRIORITY ==="
foreach ($kv in $priorityStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}

$typeStats = @{}
foreach ($c in $finalCandidates) {
    $t = $c.COMPONENT_TYPE
    if (-not $typeStats.ContainsKey($t)) { $typeStats.$t = 0 }
    $typeStats.$t++
}
Write-Host "=== By COMPONENT_TYPE ==="
foreach ($kv in $typeStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}

# Creation queue summary
$queueTypeStats = @{}
foreach ($q in $creationQueue) {
    $t = $q.TYPE
    if (-not $queueTypeStats.ContainsKey($t)) { $queueTypeStats.$t = 0 }
    $queueTypeStats.$t++
}
Write-Host "=== Creation Queue by TYPE ==="
foreach ($kv in $queueTypeStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}

Write-Host "Outputs written:"
Write-Host "  C:\Users\jpowe\Desktop\Agent-Bridge\final_candidate_registry.json"
Write-Host "  C:\Users\jpowe\Desktop\Agent-Bridge\repository_creation_queue.json"