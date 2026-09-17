# Simple repository classification
$catJson = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\repos_categorization.json' | ConvertFrom-Json

$classifications = @()

# Personal projects -> ACTIVE_CANONICAL
Write-Host "Classifying personal_projects..."
foreach ($proj in $catJson.personal_projects) {
    $classifications += [pscustomobject]@{
        repo_name = $proj.name
        existing_category = "personal_projects"
        new_classification = "ACTIVE_CANONICAL"
    }
}

# Forks -> FORK
Write-Host "Classifying forks..."
foreach ($fork in $catJson.forks) {
    $classifications += [pscustomobject]@{
        repo_name = $fork.name
        existing_category = "forks"
        new_classification = "FORK"
    }
}

# Standalone -> LEARNING
Write-Host "Classifying standalone_non_fork..."
foreach ($standalone in $catJson.standalone_non_fork) {
    $classifications += [pscustomobject]@{
        repo_name = $standalone.name
        existing_category = "standalone_non_fork"
        new_classification = "LEARNING"
    }
}

# Write output
$classifications | ConvertTo-Json -Depth 10 | Out-File -FilePath 'C:\Users\jpowe\Desktop\Agent-Bridge\repository_classification.json' -Encoding UTF8

# Write summary
$countACT = ($classifications | Where-Object { $_.new_classification -eq "ACTIVE_CANONICAL" }).Count
$countFork = ($classifications | Where-Object { $_.new_classification -eq "FORK" }).Count
$countLearn = ($classifications | Where-Object { $_.new_classification -eq "LEARNING" }).Count

Write-Host "=== Classification Summary ==="
Write-Host "ACTIVE_CANONICAL: $countACT"
Write-Host "FORK: $countFork"
Write-Host "LEARNING: $countLearn"
Write-Host "Total: $($classifications.Count)"