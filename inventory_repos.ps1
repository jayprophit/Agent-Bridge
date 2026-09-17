# Comprehensive jayprophit Repository Inventory
# Sub-task A: AETHERIUS-REPOSITORY-PROVISIONING

# Read the existing github_repos.txt (200 entries)
$localRepos = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\github_repos.txt' | ForEach-Object { 
    $_ -split '\t' | Select-Object -First 1 
} | Sort-Object -Unique

# Read the repos_categorization.json 
$catJson = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\repos_categorization.json' | ConvertFrom-Json

# Extract all repo names from each category
$allNames = @()

# Personal projects
foreach ($proj in $catJson.personal_projects) {
    $allNames += $proj.name
}

# Forks
foreach ($fork in $catJson.forks) {
    $allNames += $fork.name
}

# Standalone non-fork
foreach ($standalone in $catJson.standalone_non_fork) {
    $allNames += $standalone.name
}

# Deduplicate
$uniqueNames = $allNames | Sort-Object -Unique

# Combine with local repos
$combined = @($localRepos + $uniqueNames) | Sort-Object -Unique

# Output results
Write-Host "Total local repos: $($localRepos.Count)"
Write-Host "Total categorized repos: $($uniqueNames.Count)"
Write-Host "Total combined (deduplicated): $($combined.Count)"

# Write the comprehensive inventory
$combined | Out-File -FilePath 'C:\Users\jpowe\Desktop\Agent-Bridge\all_jayprophit_repos.txt' -Encoding UTF8

# Also create a categorized inventory
$inventory = @{
    personal_projects = $catJson.personal_projects
    forks = $catJson.forks
    standalone_non_fork = $catJson.standalone_non_fork
    local_from_txt = $localRepos
}

$inventory | ConvertTo-Json -Depth 10 | Out-File -FilePath 'C:\Users\jpowe\Desktop\Agent-Bridge\jayprophit_repository_inventory.json' -Encoding UTF8

Write-Host "Inventory complete. Total unique repos: $($combined.Count)"