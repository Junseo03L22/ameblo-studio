$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($compiler) { $iscc = $compiler.Source }
else { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (!(Test-Path $iscc)) { throw "Install Inno Setup 6 from https://jrsoftware.org/isinfo.php first." }
if (!(Test-Path "dist\AmebloStudio\AmebloStudio.exe")) { throw "Build the app using scripts/build.py first." }
& $iscc installer\windows.iss
if ($LASTEXITCODE -ne 0) { throw "Installer compilation failed" }
