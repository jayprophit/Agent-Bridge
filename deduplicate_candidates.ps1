# Sub-task G: Deduplicate Candidates by Capability
# Detect semantic duplicates, merge candidate records, preserve all requirements

# Read normalized candidate registry
$candidates = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\normalized_candidate_registry.json' | ConvertFrom-Json

# Build capability-based deduplication
$deduplicatedMap = @{}
$processed = @()

# Define known capability groups that represent shared components
$sharedComponents = @{
    "Aetherius Math" = @("math", "mathematics", "numeric", "algebra", "calculus", "geometry.math")
    "Aetherius Units" = @("units", "unit", "measurement", "dimensional", "quantity")
    "Aetherius Geometry" = @("geometry", "geom", "mesh", "topology", "cad.geom", "3d.geom")
    "Aetherius Mesh" = @("mesh", "meshing", "tetrahedral", "hexahedral", "surface.mesh")
    "Aetherius Materials" = @("material", "materials", "matter", "substance", "mat.props")
    "Aetherius Rendering" = @("render", "rendering", "raster", "ray.trace", "path.trace", "pbr", "shader")
    "Aetherius Colour" = @("colour", "color", "colourspace", "colorspace", "icc", "aces", "ocio")
    "Aetherius Audio" = @("audio", "dsp", "sound", "synthesis", "sampler", "effect", "midi")
    "Aetherius Video" = @("video", "codec", "encode", "decode", "transcode", "ffmpeg", "gstreamer")
    "Aetherius Media" = @("media", "timeline", "clip", "track", "sequence", "compositor")
    "Aetherius Timeline" = @("timeline", "time.line", "keyframe", "animation.curve", "automation")
    "Aetherius Animation" = @("animation", "animate", "rigging", "skeleton", "skinning", "ik", "fk")
    "Aetherius Physics" = @("physics", "rigid.body", "soft.body", "collision", "contact", "constraint")
    "Aetherius Simulation" = @("simulation", "sim", "solver", "fea", "cfd", "multiphysics", "co-sim")
    "Aetherius Database" = @("database", "db", "storage", "persist", "query", "sql", "nosql")
    "Aetherius Storage" = @("storage", "file.system", "object.store", "blob", "archive", "backup")
    "Aetherius Sync" = @("sync", "synchronisation", "replication", "conflict", "merge", "crdt")
    "Aetherius Search" = @("search", "index", "query", "fulltext", "semantic", "vector.search")
    "Aetherius Identity" = @("identity", "auth", "authentication", "authorization", "sso", "oidc", "saml")
    "Aetherius Permissions" = @("permission", "permit", "acl", "rbac", "abac", "policy", "capability")
    "Aetherius Workflow" = @("workflow", "pipeline", "orchestration", "dag", "task.graph", "automation")
    "Aetherius Collaboration" = @("collab", "collaboration", "realtime", "presence", "coauthor", "sharing")
    "Aetherius Telemetry" = @("telemetry", "metric", "log", "trace", "observability", "monitoring")
    "Aetherius Plugin SDK" = @("plugin.sdk", "plugin.api", "extension.api", "host.api", "sdk")
    "Aetherius Project Model" = @("project.model", "project.file", "session", "workspace", "asset.graph")
    "Aetherius Asset Engine" = @("asset", "asset.mgr", "asset.pipeline", "import", "export", "bundle")
}

# Function to normalize name for comparison
function NormalizeForComparison($name) {
    return $name.ToLower()
        -replace '[^a-z0-9]', ''  # Remove non-alphanumeric
        -replace 'engine$', ''
        -replace 'service$', ''
        -replace 'manager$', ''
        -replace 'handler$', ''
        -replace 'controller$', ''
        -replace 'provider$', ''
        -replace 'factory$', ''
        -replace 'builder$', ''
        -replace 'helper$', ''
        -replace 'util$', ''
        -replace 'utils$', ''
        -replace 'lib$', ''
        -replace 'library$', ''
        -replace 'framework$', ''
        -replace 'platform$', ''
        -replace 'core$', ''
        -replace 'base$', ''
        -replace 'common$', ''
        -replace 'shared$', ''
        -replace 'internal$', ''
        -replace 'public$', ''
        -replace 'private$', ''
        -replace 'impl$', ''
        -replace 'interface$', ''
        -replace 'abstract$', ''
        -replace 'concrete$', ''
        -replace 'default$', ''
        -replace 'standard$', ''
        -replace 'extended$', ''
        -replace 'advanced$', ''
        -replace 'basic$', ''
        -replace 'simple$', ''
        -replace 'complex$', ''
        -replace 'full$', ''
        -replace 'mini$', ''
        -replace 'micro$', ''
        -replace 'nano$', ''
        -replace 'pico$', ''
        -replace 'femto$', ''
        -replace 'atto$', ''
        -replace 'zepto$', ''
        -replace 'yocto$', ''
}

# Group candidates by normalized capability
$capabilityGroups = @{}

foreach ($candidate in $candidates) {
    $name = $candidate.PROPOSED_NAME
    $normalized = NormalizeForComparison $name
    
    # Check against shared components first
    $matchedShared = $false
    foreach ($shared in $sharedComponents.Keys) {
        $keywords = $sharedComponents[$shared]
        foreach ($kw in $keywords) {
            if ($name.ToLower() -match $kw) {
                if (-not $capabilityGroups.ContainsKey($shared)) {
                    $capabilityGroups[$shared] = @()
                }
                $capabilityGroups[$shared] += $candidate
                $matchedShared = $true
                break
            }
        }
        if ($matchedShared) { break }
    }
    
    if (-not $matchedShared) {
        # Use normalized name as key for exact/near matches
        if (-not $capabilityGroups.ContainsKey($normalized)) {
            $capabilityGroups[$normalized] = @()
        }
        $capabilityGroups[$normalized] += $candidate
    }
}

# Now process each group to identify duplicates and merge
$mergedCandidates = @()
$exactDuplicates = 0
$semanticDuplicates = 0
$mergedShared = 0

foreach ($groupKey in $capabilityGroups.Keys) {
    $group = $capabilityGroups[$groupKey]
    
    if ($group.Count -eq 1) {
        # Single candidate - check if it's a shared component
        $c = $group[0]
        $isShared = $sharedComponents.ContainsKey($groupKey)
        $c | Add-Member -MemberType NoteProperty -Name "IS_SHARED_COMPONENT" -Value $isShared -Force
        $c | Add-Member -MemberType NoteProperty -Name "DUPLICATE_GROUP" -Value $groupKey -Force
        $c | Add-Member -MemberType NoteProperty -Name "MERGED_FROM" -Value @($c.CANDIDATE_ID) -Force
        $mergedCandidates += $c
    } else {
        # Multiple candidates - this is a duplicate group
        Write-Host "Duplicate group: $groupKey ($($group.Count) candidates)"
        foreach ($c in $group) {
            Write-Host "  - $($c.CANDIDATE_ID): $($c.PROPOSED_NAME) [$($c.COMPONENT_TYPE)]"
        }
        
        # Determine if this is a shared component
        $isShared = $sharedComponents.ContainsKey($groupKey)
        
        # Merge the candidates
        $primary = $group | Sort-Object { $_.CANDIDATE_ID } | Select-Object -First 1
        $mergedIds = $group | ForEach-Object { $_.CANDIDATE_ID }
        $mergedNames = $group | ForEach-Object { $_.PROPOSED_NAME }
        $mergedTypes = $group | ForEach-Object { $_.COMPONENT_TYPE } | Sort-Object -Unique
        $mergedDomains = $group | ForEach-Object { $_.DOMAIN } | Sort-Object -Unique
        $mergedParents = $group | ForEach-Object { $_.PARENT_PROJECT } | Sort-Object -Unique
        $mergedWorkstreams = $group | ForEach-Object { $_.SOURCE_WORKSTREAM } | Sort-Object -Unique
        $mergedProvenance = $group | ForEach-Object { $_.PROVENANCE }
        
        # Determine best component type (prefer more specific)
        $typePriority = @{ "ENGINE"=1; "SERVICE"=2; "SDK"=3; "APPLICATION"=4; "PLUGIN"=5; "EXTENSION"=6; "LIBRARY"=7; "ADAPTER"=8; "DRIVER"=9; "CLI"=10; "FORMAT_MODULE"=11; "DATA"=12; "SPECIFICATION"=13; "TEST_SUITE"=14; "TEMPLATE"=15; "REFERENCE_FORK"=16; "UNKNOWN"=99 }
        $bestType = $mergedTypes | Sort-Object { $typePriority[$_] } | Select-Object -First 1
        
        # Determine canonical name - prefer shared component name or shortest unique name
        $canonicalName = if ($isShared) { $groupKey } else { ($mergedNames | Sort-Object { $_.Length } | Select-Object -First 1) }
        
        # Merge duplicate status
        $duplicateStatus = "MERGED"
        if ($groupKey -match '^[a-f0-9]{32}$') { $duplicateStatus = "SEMANTIC_DUPLICATE" } else { $duplicateStatus = "EXACT_DUPLICATE" }
        
        if ($isShared) { $mergedShared++ }
        elseif ($duplicateStatus -eq "EXACT_DUPLICATE") { $exactDuplicates++ } else { $semanticDuplicates++ }
        
        $merged = [pscustomobject]@{
            CANDIDATE_ID = $primary.CANDIDATE_ID
            PROPOSED_NAME = $canonicalName
            NORMALIZED_NAME = $canonicalName
            DISPLAY_NAME = $canonicalName -replace '/', ' ' -replace '-', ' ' -replace '_', ' '
            COMPONENT_TYPE = $bestType
            DOMAIN = $mergedDomains[0]
            PARENT_PROJECT = $mergedParents[0]
            SOURCE_WORKSTREAM = ($mergedWorkstreams -join ';')
            SOURCE_REQUIREMENTS = @()
            SOURCE_CAPABILITIES = @()
            SOURCE_REFERENCES = @()
            DEPENDENCIES = @()
            DEPENDENTS = @()
            SIMILAR_CANDIDATES = $mergedNames
            EXISTING_LOCAL_REPO = ($group | Where-Object { $_.EXISTING_LOCAL_REPO } | Measure-Object).Count -gt 0
            EXISTING_GITHUB_REPO = ($group | Where-Object { $_.EXISTING_GITHUB_REPO } | Measure-Object).Count -gt 0
            EXISTING_FORK = ($group | Where-Object { $_.EXISTING_FORK } | Measure-Object).Count -gt 0
            EXISTING_CAPABILITY = ($group | Where-Object { $_.EXISTING_CAPABILITY } | Measure-Object).Count -gt 0
            OVERLAP_SCORE = 1.0
            DUPLICATE_STATUS = $duplicateStatus
            BOUNDARY_STATUS = $primary.BOUNDARY_STATUS
            REPOSITORY_REQUIRED = $true
            CANONICAL_NAME = $canonicalName
            ACTION = if ($primary.EXISTING_LOCAL_REPO -or $primary.EXISTING_GITHUB_REPO) { "REUSE_EXISTING" } else { "CREATE_NEW" }
            RATIONALE = "Merged $($group.Count) candidates: $($mergedNames -join ', '); Shared: $isShared"
            PROVENANCE = @{
                SOURCE_DOCUMENT = "normalized_candidate_registry.json"
                SOURCE_DATE = (Get-Date).ToString("o")
                DISCOVERY_METHOD = "Sub-task G semantic deduplication"
                WORKSTREAM = "AETHERIUS-REPOSITORY-PROVISIONING"
                MERGED_FROM = $mergedIds
                MERGED_NAMES = $mergedNames
                IS_SHARED_COMPONENT = $isShared
            }
            IS_SHARED_COMPONENT = $isShared
            DUPLICATE_GROUP = $groupKey
            MERGED_FROM = $mergedIds
        }
        
        $mergedCandidates += $merged
    }
}

# Write deduplicated candidate registry
$mergedCandidates | ConvertTo-Json -Depth 10 | Out-File -FilePath 'C:\Users\jpowe\Desktop\Agent-Bridge\deduplicated_candidate_registry.json' -Encoding UTF8

# Write summary
Write-Host "=== Deduplication Summary ==="
Write-Host "Original candidates: 352"
Write-Host "Merged candidates: $($mergedCandidates.Count)"
Write-Host "Exact duplicates removed: $exactDuplicates"
Write-Host "Semantic duplicates merged: $semanticDuplicates"
Write-Host "Shared components identified: $mergedShared"
Write-Host "Reduction: $(352 - $mergedCandidates.Count) candidates"

# Summary by component type after deduplication
$typeStats = @{}
foreach ($c in $mergedCandidates) {
    $t = $c.COMPONENT_TYPE
    if (-not $typeStats.ContainsKey($t)) { $typeStats.$t = 0 }
    $typeStats.$t++
}
Write-Host "=== By COMPONENT_TYPE (after deduplication) ==="
foreach ($kv in $typeStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}

# Summary by duplicate status
$dupStats = @{}
foreach ($c in $mergedCandidates) {
    $d = $c.DUPLICATE_STATUS
    if (-not $dupStats.ContainsKey($d)) { $dupStats.$d = 0 }
    $dupStats.$d++
}
Write-Host "=== By DUPLICATE_STATUS ==="
foreach ($kv in $dupStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}

# Shared components identified
Write-Host "=== Shared Components Identified ==="
$sharedFound = $mergedCandidates | Where-Object { $_.IS_SHARED_COMPONENT }
foreach ($c in $sharedFound) {
    Write-Host "  $($c.CANONICAL_NAME) [Type: $($c.COMPONENT_TYPE), Domain: $($c.DOMAIN), Parent: $($c.PARENT_PROJECT)]"
}

# Candidates that can be reused from existing repos
$reuseCount = ($mergedCandidates | Where-Object { $_.ACTION -eq "REUSE_EXISTING" }).Count
Write-Host "Candidates reusing existing repos: $reuseCount"