$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 설치를 확인하세요." }
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "의존성 설치 실패" }
& .\.venv\Scripts\python.exe scripts\build.py
if ($LASTEXITCODE -ne 0) { throw "패키징 실패" }
Compress-Archive -Path dist\AmebloStudio,dist\README.md,dist\LICENSE,dist\THIRD_PARTY.md -DestinationPath dist\AmebloStudio-Windows.zip -Force
Write-Host "완료: dist\AmebloStudio-Windows.zip"

& "$PSScriptRoot\installer_windows.ps1"
if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }
