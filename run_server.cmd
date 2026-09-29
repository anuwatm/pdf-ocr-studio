@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

where curl.exe >nul 2>nul
if not errorlevel 1 (
  curl.exe --silent --fail --max-time 2 "http://127.0.0.1:8000/api/health" >nul 2>nul
  if not errorlevel 1 (
    echo OCR server is already running: http://127.0.0.1:8000
    exit /b 0
  )
)

if not exist "venv\Scripts\python.exe" (
  call "%SCRIPT_DIR%install.cmd"
  if errorlevel 1 exit /b %ERRORLEVEL%
)

"venv\Scripts\python.exe" -m uvicorn src.server:app --host 127.0.0.1 --port 8000
exit /b %ERRORLEVEL%
