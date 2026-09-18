Write-Host "=== C++ TOOLCHAIN DETECTION ===" -ForegroundColor Yellow

# Check for MSVC / cl.exe
Write-Host "`n=== Microsoft Visual C++ ===" 
$vs_paths = @(
    "C:\Program Files\Microsoft Visual Studio\*",
    "C:\Program Files (x86)\Microsoft Visual Studio\*"
)
foreach ($vs_path in $vs_paths) {
    $dirs = Get-ChildItem $vs_path -ErrorAction SilentlyContinue
    if ($dirs) {
        Write-Host "  Found Visual Studio dirs: $($dirs.Name -join ", ")"
    }
}

# Check for MinGW / g++
Write-Host "`n=== MinGW / g++ ===" 
$mingw_paths = @(
    "C:\Program Files\mingw",
    "C:\Program Files (x86)\mingw",
    "C:\msys64\mingw64\bin"
)
foreach ($path in $mingw_paths) {
    if (Test-Path $path) {
        Write-Host "  Found MinGW: $path"
        $g = Resolve-Path "$path\g++.exe" -ErrorAction SilentlyContinue
        if ($g) { Write-Host "    g++.exe: $($g.Path)" }
    }
}

# Check for Clang
Write-Host "`n=== Clang / clang++ ===" 
$clang_paths = @(
    "C:\Program Files\LLVM",
    "C:\Program Files (x86)\LLVM"
)
foreach ($path in $clang_paths) {
    if (Test-Path $path) {
        Write-Host "  Found LLVM: $path"
        $clang = Resolve-Path "$path\bin\clang++.exe" -ErrorAction SilentlyContinue
        if ($clang) { Write-Host "    clang++.exe found" }
    }
}

# Check for CMake
Write-Host "`n=== CMake ===" 
$cmake = Resolve-Path "C:\Program Files\CMake\bin\cmake.exe" -ErrorAction SilentlyContinue
if ($cmake) {
    Write-Host "  cmake.exe: $($cmake.Path)"
    $ver = cmake --version 2>&1
    Write-Host "  version: $ver"
}

# Check for Ninja
Write-Host "`n=== Ninja ===" 
$ninja = where.exe ninja 2>$null
if ($ninja) { Write-Host "  ninja: $ninja" }
else { Write-Host "  ninja: NOT FOUND" }

# Check for Make
Write-Host "`n=== Make ===" 
$make = where.exe make 2>$null
if ($make) { Write-Host "  make: $make" }
else { Write-Host "  make: NOT FOUND" }

# Check for MSBuild
Write-Host "`n=== MSBuild ===" 
$msbuild = where.exe msbuild 2>$null
if ($msbuild) { Write-Host "  msbuild: $msbuild" }
else { Write-Host "  msbuild: NOT FOUND" }

Write-Host "`n=== Key PATH segments ===" -ForegroundColor Cyan
$env:PATH.Split(';') | ForEach-Object { 
    if ($_.Contains("Visual") -or $_.Contains("LLVM") -or $_.Contains("Mingw") -or $_.Contains("CMake")) {
        Write-Host "  $_"
    }
}