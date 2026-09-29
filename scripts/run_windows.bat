@echo off
cd /d "%~dp0\.."
if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
  if errorlevel 1 goto fail
  .venv\Scripts\python.exe -m pip install -e .
  if errorlevel 1 goto fail
  .venv\Scripts\python.exe -m playwright install chromium
  if errorlevel 1 goto fail
)
.venv\Scripts\python.exe -m ameblo_studio
if errorlevel 1 goto fail
exit /b 0
:fail
echo Installation or startup failed. See README.md.
pause
exit /b 1
