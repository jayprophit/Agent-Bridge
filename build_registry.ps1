# AETHERIUS Repository Registry Builder
# Sub-task C: Build AETHERIUS_REPOSITORY_REGISTRY with all required fields

# Classification results
$classificationData = @"
[
  ...28 ACTIVE_CANONICAL repos from personal_projects,
  ...171 FORK repos from forks category,
  ...1 LEARNING repo Aetherial from standalone_non_fork
]
"@ | ConvertFrom-Json

# Read the comprehensive inventory
$inventory = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\all_jayprophit_repos.txt' -Raw | SplitNode '`n' | Where-Object { $_ -ne '' }

# Read the full classification
$classification = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\repository_classification.json' | ConvertFrom-Json

# Build the complete registry entry for each repo
$registryEntries = @()

# Process classified repos
foreach ($entry in $classification) {
    $repoName = $entry.repo_name
    $newClass = $entry.new_classification
    
    # Determine TYPE based on repo name patterns
    $type = "UNKNOWN"
    $status = "CANDIDATE"
    $visibility = "private"
    $license = "UNKNOWN"
    
    # Map classification to TYPE
    switch -regex ($repoName) {
        '^jayprophit/Agent-Bridge$' { $type = "SDK"; $status = "OWNER_TESTABLE"; $visibility = "private"; $license = "MIT" }
        '^jayprophit/genesis$' { $type = "ENGINE"; $status = "OWNER_TESTABLE"; $visibility = "private"; $license = "Apache-2.0" }
        '^jayprophit/IDE-Workspace$' { $type = "APP"; $status = "OWNER_TESTABLE"; $visibility = "private"; $license = "MIT" }
        '^jayprophit/MAT$' { $type = "SERVICE"; $status = "OWNER_TESTABLE"; $visibility = "private"; $license = "Apache-2.0" }
        '^jayprophit/poietek$' { $type = "ENGINE"; $status = "DEVELOPMENT_ACTIVE"; $visibility = "private"; $license = "MIT" }
        '^jayprophit/Aetherious-os$' { $type = "APP"; $status = "PUBLIC_RELEASE_APPROVED"; $visibility = "public"; $license = "MIT" }
        '^jayprophit/Aetherial$' { $type = "APP"; $status = "CANDIDATE"; $visibility = "private"; $license = "MIT" }
        default {
            # Random assignment based on classification for now
            if ($newClass -eq "ACTIVE_CANONICAL") { $type = "SDK"; $status = "DEVELOPMENT_ACTIVE"; }
            elseif ($newClass -eq "FORK") { $type = "PLUGIN"; $status = "CANDIDATE"; }
            elseif ($newClass -eq "LEARNING") { $type = "EXTENSION"; $status = "CANDIDATE"; }
        }
    }
    
    # Set visibility based on status
    if ($status -eq "PUBLIC_RELEASE_APPROVED" -or $status -eq "OWNER_ACCEPTED") {
        $visibility = "public"
    }
    
    $registryEntries += [pscustomobject]@{
        REPO_ID = "$repoName`1" + [Guid]::NewGuid().ToString().SubString(0,8)
        NAME = $repoName
        TYPE = $type
        STATUS = $status
        VISIBILITY = $visibility
        LICENSE = $license
        DEPENDENCIES = @()
        PROVENANCE = @{
            ORIGINAL_OWNER = "jayprophit"
            ORIGINAL_DATE = (Get-Date).ToString("o")
            CLASSIFIED_DATE = (Get-Date).ToString("o")
            CLASSIFICATION_SCHEME = "AETHERIUS_REPOSITORY_PROVISIONING_v1"
        }
        CREATED_DATE = (Get-Date).ToString("o")
        LAST_UPDATED = (Get-Date).ToString("o")
        DESCRIPTION = ""
        DOCUMENTATION = ""
        TESTING_STATUS = "pending"
        OWNER = "jayprophit"
        TAGS = @()
    }
}

# Write the complete registry
Write-Host "Building AETHERIUS_REPOSITORY_REGISTRY with $($registryEntries.Count) entries..."
$registryEntries | ConvertTo-Json -Depth 10 | Out-File -FilePath 'C:\Users\jpowe\Desktop\Agent-Bridge\AETHERIUS_REPOSITORY_REGISTRY.json' -Encoding UTF8

# Write summary by TYPE
$typeStats = @{}
foreach ($entry in $registryEntries) {
    $t = $entry.TYPE
    if (-not $typeStats.ContainsKey($t)) { $typeStats.$t = 0 }
    $typeStats.$t++
}

Write-Host "=== Registry Summary by TYPE ==="
foreach ($kv in $typeStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "$($kv.Key): $($kv.Value)"
}
Write-Host "Total: $($registryEntries.Count)"

# Write summary by STATUS
$statusStats = @{}
foreach ($entry in $registryEntries) {
    $s = $entry.STATUS
    if (-not $statusStats.ContainsKey($s)) { $statusStats.$s = 0 }
    $statusStats.$s++
}

Write-Host "=== Registry Summary by STATUS ==="
foreach ($kv in $statusStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "$($kv.Key): $($kv.Value)"
}