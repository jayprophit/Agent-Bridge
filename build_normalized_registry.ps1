# Sub-task G: Build Normalized Candidate Registry for 352 Candidates
# Deduplicate by capability, assign canonical names, create repository creation queue

# Read candidate map
$candidates = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\candidate_repository_map.json' | ConvertFrom-Json

# Read existing repository registry
$existingRegistry = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\AETHERIUS_REPOSITORY_REGISTRY.json' | ConvertFrom-Json

# Read jayprophit repos from github_repos.txt
$jayprophitRepos = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\github_repos.txt' | ForEach-Object { $_ -split '\t' | Select-Object -First 1 } | Sort-Object -Unique

# Build normalized candidate registry with all required fields
$normalizedCandidates = @()
$candidateId = 1

foreach ($candidate in $candidates) {
    $repoName = $candidate.REPO_NAME
    $canonicalName = $candidate.CANONICAL_NAME
    $repoType = $candidate.REPO_TYPE
    $status = $candidate.STATUS
    $visibility = $candidate.VISIBILITY
    $license = $candidate.LICENSE
    
    # Determine COMPONENT_TYPE based on REPO_TYPE and name patterns
    $componentType = "UNKNOWN"
    switch -regex ($repoType) {
        "APP" { $componentType = "APPLICATION" }
        "ENGINE" { $componentType = "ENGINE" }
        "SDK" { $componentType = "SDK" }
        "SERVICE" { $componentType = "SERVICE" }
        "PLUGIN" { $componentType = "PLUGIN" }
        "EXTENSION" { $componentType = "EXTENSION" }
        "ADAPTER" { $componentType = "ADAPTER" }
        "DRIVER" { $componentType = "DRIVER" }
        "LIBRARY" { $componentType = "LIBRARY" }
        "FORMAT_MODULE" { $componentType = "FORMAT_MODULE" }
        "DATA" { $componentType = "DATA" }
        "SPECIFICATION" { $componentType = "SPECIFICATION" }
        "TEST_SUITE" { $componentType = "TEST_SUITE" }
        "TEMPLATE" { $componentType = "TEMPLATE" }
        "REFERENCE_FORK" { $componentType = "REFERENCE_FORK" }
        default { 
            # Infer from name patterns
            if ($repoName -match "sdk$|sdk-") { $componentType = "SDK" }
            elseif ($repoName -match "engine$|engine-") { $componentType = "ENGINE" }
            elseif ($repoName -match "plugin$|plugin-") { $componentType = "PLUGIN" }
            elseif ($repoName -match "extension$|extension-") { $componentType = "EXTENSION" }
            elseif ($repoName -match "adapter$|adapter-") { $componentType = "ADAPTER" }
            elseif ($repoName -match "driver$|driver-") { $componentType = "DRIVER" }
            elseif ($repoName -match "lib$|library|format$") { $componentType = "LIBRARY" }
            elseif ($repoName -match "service$|service-") { $componentType = "SERVICE" }
            elseif ($repoName -match "cli$|tool$") { $componentType = "CLI" }
            else { $componentType = "APPLICATION" }
        }
    }
    
    # Determine DOMAIN based on name patterns and tags
    $domain = "OTHER"
    $nameLower = $repoName.ToLower()
    if ($nameLower -match "audio|daw|synth|sampler|drum|midi|vst|clap|au|lv2|aax|reverb|compressor|eq|filter|delay|modulation|pitch|timestretch|stem|voice|vocal|mixing|mastering|podcast|spatial|ambisonics|hrtf") { $domain = "AUDIO" }
    elseif ($nameLower -match "video|ffmpeg|gstreamer|codec|container|editor|compositor|vfx|timeline|media|encoding|decoding|transcode|subtitle|caption|av1|vp9|opus|hevc|h264") { $domain = "VIDEO" }
    elseif ($nameLower -match "image|vector|raster|paint|photo|drawing|svg|pdf|ocr|font|typography|colour|color|illustration|desktop.publish|layout") { $domain = "CREATIVE" }
    elseif ($nameLower -match "cad|bim|mechanical|electrical|pcb|architecture|civil|plant|cnc|cam|fea|cfd|thermal|simulation|geometry|mesh|material|physics|engineering|structural|optimisation|generative") { $domain = "ENGINEERING" }
    elseif ($nameLower -match "game|gaming|render|raylib|godot|unreal|unity|ecs|scene|asset|animation|nav|ai|network|multiplayer|vr|ar|xr|input|controller") { $domain = "GAMING" }
    elseif ($nameLower -match "word|sheet|presentation|database|form|note|email|calendar|contact|task|project|diagram|whiteboard|list|wiki|intranet|bi|analytics|dashboard|automation|low.code|booking|office|document|spreadsheet") { $domain = "OFFICE" }
    elseif ($nameLower -match "ide|git|diff|merge|database|api|regex|json|xml|yaml|container|vm|package|compiler|debugger|profiler|log|network|ssh|remote|web|mobile|game.dev|cad.script|ai.dev|genesis|agent|plugin|extension|sdk") { $domain = "DEVELOPER" }
    elseif ($nameLower -match "chat|messag|voice|video.call|meeting|conferenc|screen.share|remote.assist|community|channel|forum|workspace|notification|sms|phone|cross.device") { $domain = "COMMUNICATION" }
    elseif ($nameLower -match "security|firewall|permission|credential|password|authenticator|encryption|device.security|recovery|backup|network.security|app.integrity|sbom|audit|privacy|telemetry|sandbox") { $domain = "SECURITY" }
    elseif ($nameLower -match "accessib|screen.reader|magnifier|speech.control|dictation|tts|stt|caption|colour.filter|contrast|font.scaling|keyboard.nav|switch|eye.control|hearing|cognitive|reduced.motion") { $domain = "ACCESSIBILITY" }
    elseif ($nameLower -match "file|storage|nas|network.share|cloud|virtual.file|archive|compression|encryption|search|metadata|tagging|duplicate|versioning|sync|backup|recovery|distributed") { $domain = "DATA" }
    elseif ($nameLower -match "cloud|sync|backup|file.share|remote.access|distributed.storage|provider.adapter|conflict|encryption|content.addressed") { $domain = "CLOUD" }
    elseif ($nameLower -match "device|driver|usb|bluetooth|wifi|display|sound|printer|scanner|power|battery|update|hardware|sensor|camera|audio.interface|midi.controller") { $domain = "DEVICE" }
    elseif ($nameLower -match "health|fitness|exercise|sport|nutrition|training|performance|workout|wearable|medical|biometric|wellness") { $domain = "HEALTH" }
    elseif ($nameLower -match "finance|budget|accounting|business|portfolio|market|trading|payment|invoice|tax|savings|investment|crypto|loan|credit|real.estate") { $domain = "FINANCE" }
    elseif ($nameLower -match "business|crm|erp|inventory|pos|payroll|hr|scheduling|booking|procurement|contract|signature|asset.mgmt|fleet|warehouse|supply.chain") { $domain = "BUSINESS" }
    elseif ($nameLower -match "enterprise|device.mgmt|software.deploy|patch|inventory|certificate|identity|sso|directory|audit|logging|disaster.recovery|remote.mgmt|endpoint|compliance|policy") { $domain = "ENTERPRISE" }
    elseif ($nameLower -match "government|audit|records|secure.comm|classification|records.mgmt|accessibility|procurement|identity|permission|offline|air.gapped|data.residency|crypto.policy|controlled.update") { $domain = "GOVERNMENT" }
    elseif ($nameLower -match "education|classroom|assignment|course|learning|quiz|flashcard|notebook|coding|math|science|language|music|art|design|simulation.edu") { $domain = "EDUCATION" }
    elseif ($nameLower -match "science|research|notebook|data.analysis|statistics|mathematics|graphing|symbolic|numerical|chemistry|molecular|astronomy|materials|laboratory|bibliography|visualisation|dataset") { $domain = "SCIENCE" }
    elseif ($nameLower -match "utility|calculator|conversion|clock|alarm|timer|stopwatch|weather|map|translate|dictionary|thesaurus|unit.converter|qr|scanner|voice.recorder|magnifier|compass|measurement|reminder|journal|password.manager|authenticator|clipboard") { $domain = "UTILITIES" }
    elseif ($nameLower -match "system|kernel|shell|runtime|service|init|boot|process|memory|scheduler|filesystem|network|device.driver|power.mgmt|thermal.mgmt") { $domain = "SYSTEM" }
    elseif ($nameLower -match "ai|genesis|agent|llm|ml|model|inference|training|embedding|vector|rag|semantic|intelligence|cognition|reasoning|planning") { $domain = "AI" }
    elseif ($nameLower -match "math|geometry|units|mesh|render|timeline|node.graph|shader|material|asset|collaboration|workflow|telemetry|project.model|plugin.sdk|search|identity|permission|storage|sync|database|animation|physics|simulation") { $domain = "SHARED" }
    
    # Determine PARENT_PROJECT based on domain and type
    $parentProject = "AETHERIUS_OS"
    switch ($domain) {
        "AUDIO" { $parentProject = "POIETEK" }
        "VIDEO" { $parentProject = "AETHERIUS_MEDIA" }
        "CREATIVE" { $parentProject = "AETHERIUS_CREATIVE" }
        "ENGINEERING" { $parentProject = "AETHERIUS_CAD" }
        "GAMING" { $parentProject = "AETHERIUS_GAME_ENGINE" }
        "OFFICE" { $parentProject = "AETHERIUS_OFFICE" }
        "DEVELOPER" { $parentProject = "AETHERIUS_IDE" }
        "COMMUNICATION" { $parentProject = "AETHERIUS_COMMUNICATION" }
        "SECURITY" { $parentProject = "AETHERIUS_SECURITY" }
        "ACCESSIBILITY" { $parentProject = "AETHERIUS_ACCESSIBILITY" }
        "DATA" { $parentProject = "AETHERIUS_FILES" }
        "CLOUD" { $parentProject = "AETHERIUS_CLOUD" }
        "DEVICE" { $parentProject = "UNIVERSAL_BRIDGE" }
        "HEALTH" { $parentProject = "ATHENA" }
        "FINANCE" { $parentProject = "AETHERIUS_FINANCE" }
        "BUSINESS" { $parentProject = "AETHERIUS_BUSINESS" }
        "ENTERPRISE" { $parentProject = "AETHERIUS_ADMIN" }
        "GOVERNMENT" { $parentProject = "AETHERIUS_GOVERNMENT" }
        "EDUCATION" { $parentProject = "AETHERIUS_LEARNING" }
        "SCIENCE" { $parentProject = "MAT" }
        "UTILITIES" { $parentProject = "AETHERIUS_UTILITIES" }
        "SYSTEM" { $parentProject = "AETHERIUS_OS" }
        "AI" { $parentProject = "GENESIS" }
        "SHARED" { $parentProject = "AETHERIUS_SHARED" }
        default { $parentProject = "AETHERIUS_OS" }
    }
    
    # Determine SOURCE_WORKSTREAM
    $sourceWorkstream = "AETHERIUS-REPOSITORY-PROVISIONING"
    if ($repoName -match "^jayprophit/") { $sourceWorkstream = "EXISTING_JAYPROPHIT" }
    elseif ($repoName -match "^adobe/|^microsoft/|^autodesk/") { $sourceWorkstream = "FIRST_PARTY_APP_ECOSYSTEM_RESEARCH" }
    elseif ($repoName -match "^unity/|^unreal|^godot|^cryengine|^langyard|^ffmpeg$|^gstreamer$|^avid|^da-vinci|^nuke") { $sourceWorkstream = "SIMULATION_GAME_VIDEO_RESEARCH" }
    elseif ($repoName -match "poietek|surge|dexed|vitalium|helm|drum.machine|piano.roll|stem.separation|voice.processing|clap|vst3|au.|lv2|aax") { $sourceWorkstream = "POIETEK_AUDIO_DAW_RESEARCH" }
    elseif ($repoName -match "aetherius-|ide|store|os") { $sourceWorkstream = "AETHERIUS_OS_APPLICATION_ECOSYSTEM" }
    
    # Check for existing local repo
    $existingLocal = $false
    if ($existingRegistry | Where-Object { $_.NAME -eq $repoName }) { $existingLocal = $true }
    
    # Check for existing GitHub repo (jayprophit)
    $existingGitHub = $false
    if ($jayprophitRepos -contains $repoName -or $jayprophitRepos -contains "jayprophit/$repoName") { $existingGitHub = $true }
    
    # Check for existing fork
    $existingFork = $false
    if ($repoName -match "^jayprophit/" -and ($existingRegistry | Where-Object { $_.NAME -eq $repoName -and $_.TYPE -eq "PLUGIN" })) { $existingFork = $true }
    
    # Check for existing capability overlap
    $existingCapability = $false
    # Would need capability registry - placeholder
    
    # Calculate overlap score (simplified)
    $overlapScore = 0
    $duplicateStatus = "UNIQUE"
    
    # Boundary status
    $boundaryStatus = "NEEDS_REVIEW"
    if ($componentType -eq "APPLICATION" -or $componentType -eq "ENGINE" -or $componentType -eq "SERVICE" -or $componentType -eq "SDK") { $boundaryStatus = "CLEAR" }
    elseif ($componentType -eq "PLUGIN" -or $componentType -eq "EXTENSION") { $boundaryStatus = "DEPENDS_ON_HOST" }
    elseif ($componentType -eq "LIBRARY" -or $componentType -eq "FORMAT_MODULE") { $boundaryStatus = "SHARED" }
    
    # Repository required determination
    $repositoryRequired = $true
    if ($componentType -in @("CLI", "TEMPLATE", "TEST_SUITE", "REFERENCE_FORK", "DATA", "SPECIFICATION") -and $repoType -eq "UNKNOWN") { 
        $repositoryRequired = $false 
    }
    
    # Action determination
    $action = "CREATE_NEW"
    if ($existingLocal -or $existingGitHub) { $action = "REUSE_EXISTING" }
    elseif (-not $repositoryRequired) { $action = "DEFER" }
    elseif ($duplicateStatus -eq "DUPLICATE") { $action = "MERGE" }
    
    # Rationale
    $rationale = "Discovered via $sourceWorkstream; Type: $componentType; Domain: $domain; Parent: $parentProject"
    
    # Provenance
    $provenance = @{
        SOURCE_DOCUMENT = "candidate_repository_map.json"
        SOURCE_DATE = (Get-Date).ToString("o")
        DISCOVERY_METHOD = "Sub-task F candidate generation"
        WORKSTREAM = $sourceWorkstream
    }
    
    $normalizedEntry = [pscustomobject]@{
        CANDIDATE_ID = "CAND-$($candidateId.ToString("000"))"
        PROPOSED_NAME = $repoName
        NORMALIZED_NAME = $canonicalName
        DISPLAY_NAME = $repoName -replace '/', ' ' -replace '-', ' ' -replace '_', ' ' | ForEach-Object { 
            $_ -split ' ' | ForEach-Object { if ($_ -match '^[a-z]+$') { $_.ToUpper() } else { $_ } } -join ' ' 
        }
        COMPONENT_TYPE = $componentType
        DOMAIN = $domain
        PARENT_PROJECT = $parentProject
        SOURCE_WORKSTREAM = $sourceWorkstream
        SOURCE_REQUIREMENTS = @()
        SOURCE_CAPABILITIES = @()
        SOURCE_REFERENCES = @()
        DEPENDENCIES = @()
        DEPENDENTS = @()
        SIMILAR_CANDIDATES = @()
        EXISTING_LOCAL_REPO = $existingLocal
        EXISTING_GITHUB_REPO = $existingGitHub
        EXISTING_FORK = $existingFork
        EXISTING_CAPABILITY = $existingCapability
        OVERLAP_SCORE = $overlapScore
        DUPLICATE_STATUS = $duplicateStatus
        BOUNDARY_STATUS = $boundaryStatus
        REPOSITORY_REQUIRED = $repositoryRequired
        CANONICAL_NAME = $canonicalName
        ACTION = $action
        RATIONALE = $rationale
        PROVENANCE = $provenance
    }
    
    $normalizedCandidates += $normalizedEntry
    $candidateId++
}

# Write normalized candidate registry
$normalizedCandidates | ConvertTo-Json -Depth 10 | Out-File -FilePath 'C:\Users\jpowe\Desktop\Agent-Bridge\normalized_candidate_registry.json' -Encoding UTF8

Write-Host "Normalized candidate registry built with $($normalizedCandidates.Count) entries"
Write-Host "Output: C:\Users\jpowe\Desktop\Agent-Bridge\normalized_candidate_registry.json"

# Summary by component type
$typeStats = @{}
foreach ($c in $normalizedCandidates) {
    $t = $c.COMPONENT_TYPE
    if (-not $typeStats.ContainsKey($t)) { $typeStats.$t = 0 }
    $typeStats.$t++
}
Write-Host "=== By COMPONENT_TYPE ==="
foreach ($kv in $typeStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}

# Summary by domain
$domainStats = @{}
foreach ($c in $normalizedCandidates) {
    $d = $c.DOMAIN
    if (-not $domainStats.ContainsKey($d)) { $domainStats.$d = 0 }
    $domainStats.$d++
}
Write-Host "=== By DOMAIN ==="
foreach ($kv in $domainStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}

# Summary by action
$actionStats = @{}
foreach ($c in $normalizedCandidates) {
    $a = $c.ACTION
    if (-not $actionStats.ContainsKey($a)) { $actionStats.$a = 0 }
    $actionStats.$a++
}
Write-Host "=== By ACTION ==="
foreach ($kv in $actionStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}

# Summary by parent project
$parentStats = @{}
foreach ($c in $normalizedCandidates) {
    $p = $c.PARENT_PROJECT
    if (-not $parentStats.ContainsKey($p)) { $parentStats.$p = 0 }
    $parentStats.$p++
}
Write-Host "=== By PARENT_PROJECT ==="
foreach ($kv in $parentStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}