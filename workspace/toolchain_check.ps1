$results = @()
$results += "cl.exe: " + (where.exe cl 2>$null)
$results += "clang++: " + (where.exe clang++ 2>$null)
$results += "clang: " + (where.exe clang 2>$null)
$results += "cmake: " + (cmake --version 2>$null)
$results += "ninja: " + (where.exe ninja 2>$null)

Write-Host "=== TOOLCHAIN LOCATIONS ===" -ForegroundColor Yellow
foreach ($r in $results) { Write-Host $r }

Write-Host "`=== PATH segments with LLVM/Clang ===`" -ForegroundColor Cyan
$llvm_path = "C:\Users\jpowe\AppData\Local\Programs\LLVM\bin"
if (Test-Path $llvm_path) {
    Write-Host "LLVM path exists: $llvm_path"
    $dll = dir "$llvm_path\*.exe" 2>$null
    if ($dll) { Write-Host "  Executables: $($dll.Name -join ", ")" }
} else { Write-Host "LLVM path NOT found" }

Write-Host "`=== Visual Studio IDE ===`" -ForegroundColor Cyan
$vs_community = "C:\Program Files\Microsoft Visual Studio\Community\IDE\cl.exe"
$vs_professional = "C:\Program Files\Microsoft Visual Studio\Professional\IDE\cl.exe"
$vs_enterprise = "C:\Program Files\Microsoft Visual Studio\Enterprise\IDE\cl.exe"
foreach ($vs_path in @($vs_community, $vs_professional, $vs_enterprise)) {
    if (Test-Path $vs_path) { Write-Host "  VS IDE found: $vs_path" }
}