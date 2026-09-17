$catJson = Get-Content 'C:\Users\jpowe\Desktop\Agent-Bridge\repos_categorization.json' | ConvertFrom-Json
Write-Host "personal_projects count: " $catJson.personal_projects.Count
Write-Host "forks count: " $catJson.forks.Count
Write-Host "standalone_non_fork count: " $catJson.standalone_non_fork.Count
Write-Host "total: " ($catJson.personal_projects.Count + $catJson.forks.Count + $catJson.standalone_non_fork.Count)