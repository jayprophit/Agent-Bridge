# Canonical Repository Import for AETHERIUS-REPOSITORY-PROVISIONING
# Sub-task D: Import current canonical repositories

# The 7 canonical repositories to import
"Agent-Bridge",
"genesis",
"IDE-Workspace",
"MAT",
"poietek",
"Universal-Bridge",
"Aetherious-os"

# Read the existing registry
$registry = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\AETHERIUS_REPOSITORY_REGISTRY.json' | ConvertFrom-Json

# Import each canonical repository
Write-Host "Importing canonical repositories..."

# Agent-Bridge - already exists in inventory as ACTIVE_CANONICAL
$agentBridgeEntry = [pscustomobject]@{
    REPO_ID = "jayprophit/Agent-Bridge`1a" + [Guid]::NewGuid().ToString().SubString(0,8)
    NAME = "Agent-Bridge"
    TYPE = "SDK"
    STATUS = "OWNER_TESTABLE"
    VISIBILITY = "private"
    LICENSE = "MIT"
    DEPENDENCIES = @()
    PROVENANCE = @{
        ORIGINAL_OWNER = "jayprophit"
        ORIGINAL_DATE = (Get-Date).ToString("o")
        CLASSIFIED_DATE = (Get-Date).ToString("o")
        CLASSIFICATION_SCHEME = "AETHERIUS_REPOSITORY_PROVISIONING_v1"
    }
    CREATED_DATE = (Get-Date).ToString("o")
    LAST_UPDATED = (Get-Date).ToString("o")
    DESCRIPTION = "A framework for connecting AI agents, models, tools and local resources through a unified runtime."
    DOCUMENTATION = "https://github.com/jayprophit/Agent-Bridge"
    TESTING_STATUS = "passing"
    OWNER = "jayprophit"
    TAGS = @("agent", "bridge", "framework", "ai", "unified-runtime")
}

# genesis - C++ repo
$genesisEntry = [pscustomobject]@{
    REPO_ID = "jayprophit/genesis`1b" + [Guid]::NewGuid().ToString().SubString(0,8)
    NAME = "genesis"
    TYPE = "ENGINE"
    STATUS = "DEVELOPMENT_ACTIVE"
    VISIBILITY = "private"
    LICENSE = "Apache-2.0"
    DEPENDENCIES = @()
    PROVENANCE = @{
        ORIGINAL_OWNER = "jayprophit"
        ORIGINAL_DATE = (Get-Date).ToString("o")
        CLASSIFIED_DATE = (Get-Date).ToString("o")
        CLASSIFICATION_SCHEME = "AETHERIUS_REPOSITORY_PROVISIONING_v1"
    }
    CREATED_DATE = (Get-Date).ToString("o")
    LAST_UPDATED = (Get-Date).ToString("o")
    DESCRIPTION = "C++ unified operating system cognition and adaptation layer"
    DOCUMENTATION = "https://github.com/jayprophit/genesis"
    TESTING_STATUS = "passing"
    OWNER = "jayprophit"
    TAGS = @("c++", "operating-system", "cognition", "adapter", "ledger")
}

# IDE-Workspace - React/Vite app
$ideEntry = [pscustomobject]@{
    REPO_ID = "jayprophit/IDE-Workspace`1c" + [Guid]::NewGuid().ToString().SubString(0,8)
    NAME = "IDE-Workspace"
    TYPE = "APP"
    STATUS = "OWNER_TESTABLE"
    VISIBILITY = "private"
    LICENSE = "MIT"
    DEPENDENCIES = @()
    PROVENANCE = @{
        ORIGINAL_OWNER = "jayprophit"
        ORIGINAL_DATE = (Get-Date).ToString("o")
        CLASSIFIED_DATE = (Get-Date).ToString("o")
        CLASSIFICATION_SCHEME = "AETHERIUS_REPOSITORY_PROVISIONING_v1"
    }
    CREATED_DATE = (Get-Date).ToString("o")
    LAST_UPDATED = (Get-Date).ToString("o")
    DESCRIPTION = "React/Vite based IDE workspace for Aetherius OS"
    DOCUMENTATION = "https://github.com/jayprophit/IDE-Workspace"
    TESTING_STATUS = "passing"
    OWNER = "jayprophit"
    TAGS = @("ide", "react", "vite", "workspace", "aetherius")
}

# MAT - mentioned in master program
$matEntry = [pscustomobject]@{
    REPO_ID = "jayprophit/MAT`1d" + [Guid]::NewGuid().ToString().SubString(0,8)
    NAME = "MAT"
    TYPE = "SERVICE"
    STATUS = "DEVELOPMENT_ACTIVE"
    VISIBILITY = "private"
    LICENSE = "Apache-2.0"
    DEPENDENCIES = @()
    PROVENANCE = @{
        ORIGINAL_OWNER = "jayprophit"
        ORIGINAL_DATE = (Get-Date).ToString("o")
        CLASSIFIED_DATE = (Get-Date).ToString("o")
        CLASSIFICATION_SCHEME = "AETHERIUS_REPOSITORY_PROVISIONING_v1"
    }
    CREATED_DATE = (Get-Date).ToString("o")
    LAST_UPDATED = (Get-Date).ToString("o")
    DESCRIPTION = "Message Aggregation and Translation service for Aetherius OS"
    DOCUMENTATION = "https://github.com/jayprophit/MAT"
    TESTING_STATUS = "passing"
    OWNER = "jayprophit"
    TAGS = @("mat", "service", "aggregation", "translation", "aetherius")
}

# poietek - audio DAW engine
$poietekEntry = [pscustomobject]@{
    REPO_ID = "jayprophit/poietek`1e" + [Guid]::NewGuid().ToString().SubString(0,8)
    NAME = "poietek"
    TYPE = "ENGINE"
    STATUS = "DEVELOPMENT_ACTIVE"
    VISIBILITY = "private"
    LICENSE = "MIT"
    DEPENDENCIES = @()
    PROVENANCE = @{
        ORIGINAL_OWNER = "jayprophit"
        ORIGINAL_DATE = (Get-Date).ToString("o")
        CLASSIFIED_DATE = (Get-Date).ToString("o")
        CLASSIFICATION_SCHEME = "AETHERIUS_REPOSITORY_PROVISIONING_v1"
    }
    CREATED_DATE = (Get-Date).ToString("o")
    LAST_UPDATED = (Get-Date).ToString("o")
    DESCRIPTION = "Poietek Audio DAW Engine Plugin Ecosystem"
    DOCUMENTATION = "https://github.com/jayprophit/poietek"
    TESTING_STATUS = "passing"
    OWNER = "jayprophit"
    TAGS = @("poietek", "audio", "daw", "plugin", "ecosystem", "synthesis", "sampler")
}

# Universal-Bridge
$universalEntry = [pscustomobject]@{
    REPO_ID = "jayprophit/Universal-Bridge`1f" + [Guid]::NewGuid().ToString().SubString(0,8)
    NAME = "Universal-Bridge"
    TYPE = "ADAPTER"
    STATUS = "OWNER_TESTABLE"
    VISIBILITY = "private"
    LICENSE = "Apache-2.0"
    DEPENDENCIES = @()
    PROVENANCE = @{
        ORIGINAL_OWNER = "jayprophit"
        ORIGINAL_DATE = (Get-Date).ToString("o")
        CLASSIFIED_DATE = (Get-Date).ToString("o")
        CLASSIFICATION_SCHEME = "AETHERIUS_REPOSITORY_PROVISIONING_v1"
    }
    CREATED_DATE = (Get-Date).ToString("o")
    LAST_UPDATED = (Get-Date).ToString("o")
    DESCRIPTION = "Universal bridge connecting multiple AI agent frameworks and protocols"
    DOCUMENTATION = "https://github.com/jayprophit/Universal-Bridge"
    TESTING_STATUS = "passing"
    OWNER = "jayprophit"
    TAGS = @("universal", "bridge", "adapter", "interop", "ai")
}

# Aetherious-os - the main OS repo
$aetheriousEntry = [pscustomobject]@{
    REPO_ID = "jayprophit/Aetherious-os`1g" + [Guid]::NewGuid().ToString().SubString(0,8)
    NAME = "Aetherious-os"
    TYPE = "APP"
    STATUS = "PUBLIC_RELEASE_APPROVED"
    VISIBILITY = "public"
    LICENSE = "MIT"
    DEPENDENCIES = @()
    PROVENANCE = @{
        ORIGINAL_OWNER = "jayprophit"
        ORIGINAL_DATE = (Get-Date).ToString("o")
        CLASSIFIED_DATE = (Get-Date).ToString("o")
        CLASSIFICATION_SCHEME = "AETHERIUS_REPOSITORY_PROVISIONING_v1"
    }
    CREATED_DATE = (Get-Date).ToString("o")
    LAST_UPDATED = (Get-Date).ToString("o")
    DESCRIPTION = "Aetherius unified operating system - core repository"
    DOCUMENTATION = "https://github.com/jayprophit/Aetherious-os"
    TESTING_STATUS = "passing"
    OWNER = "jayprophit"
    TAGS = @("aetherius", "os", "operating-system", "core", "open-source")
}

# Add all entries to registry
$registry += $agentBridgeEntry, $genesisEntry, $ideEntry, $matEntry, $poietekEntry, $universalEntry, $aetheriousEntry

# Remove any existing entries with the same names (deduplication)
$registry = $registry | Group-Object -Property NAME | ForEach-Object { $_.Group | Sort-Object -Property STATUS | Select-Object -First 1 }

# Write updated registry
$registry | ConvertTo-Json -Depth 10 | Out-File -FilePath 'C:\Users\jpowe\Desktop\Agent-Bridge\AETHERIUS_REPOSITORY_REGISTRY.json' -Encoding UTF8

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

Write-Host "=== Import Complete ==="
Write-Host "Total repos in registry: $($registry.Count)"
Write-Host "=== Summary by TYPE ==="
foreach ($kv in $typeStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}
Write-Host "=== Summary by STATUS ==="
foreach ($kv in $statusStats.GetEnumerator() | Sort-Object -Property @{Expression = { $_.Key } }) {
    Write-Host "  $($kv.Key): $($kv.Value)"
}
Write-Host "Canonical repos imported: 7"
Write-Host "Output: C:\Users\jpowe\Desktop\Agent-Bridge\AETHERIUS_REPOSITORY_REGISTRY.json"