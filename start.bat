@echo off
setlocal
cd /d "%~dp0"

echo Checking for an already-running Webcam Tools server...
set STATUS_CODE=
for /f %%i in ('curl -s -o nul -w "%%{http_code}" http://localhost:8000/api/status 2^>nul') do set STATUS_CODE=%%i

if "%STATUS_CODE%"=="200" (
    echo Webcam Tools is already running at http://localhost:8000 - nothing to do.
    goto :eof
)

set NEEDS_BUILD=0
if not exist "frontend\dist\index.html" set NEEDS_BUILD=1
if "%NEEDS_BUILD%"=="0" (
    for /f %%i in ('powershell -NoProfile -Command "$dist = (Get-Item 'frontend\dist\index.html').LastWriteTime; $newest = (Get-ChildItem 'frontend\src','frontend\index.html','frontend\package.json' -Recurse -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime; if ($newest -gt $dist) { 'stale' } else { 'fresh' }"') do set BUILD_CHECK=%%i
    if "%BUILD_CHECK%"=="stale" set NEEDS_BUILD=1
)
if "%NEEDS_BUILD%"=="1" (
    echo Frontend source has changed since the last build - rebuilding...
    pushd frontend
    call npm run build
    popd
)

echo Starting Webcam Tools on http://webcam-tools.local:8000 and http://%COMPUTERNAME%:8000
echo (runs headless from here -- no window to keep open; logs go to data\server.log)
cd backend
start "" .venv\Scripts\pythonw.exe run.py
