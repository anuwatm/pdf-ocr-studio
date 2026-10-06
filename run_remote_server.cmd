@echo off
setlocal EnableExtensions
set "REMOTE_SERVER_DIR=%~dp0"
cd /d "%REMOTE_SERVER_DIR%"
if errorlevel 1 exit /b 1

where curl.exe >nul 2>nul
if errorlevel 1 goto prepare_runtime
curl.exe --silent --fail --max-time 2 "http://127.0.0.1:8000/api/health" >nul 2>nul
if errorlevel 1 goto prepare_runtime
echo OCR server is already running on port 8000.
echo Stop the existing server before starting remote mode.
exit /b 1

:prepare_runtime
if exist "venv\Scripts\python.exe" goto start_remote
call "%REMOTE_SERVER_DIR%install.cmd"
if errorlevel 1 exit /b 1

:start_remote
set "HOST=0.0.0.0"
set "PORT=8000"
set "LOCALHOST_ONLY=false"
echo Starting OCR remote server on port 8000.
echo The startup log below will show the available IP addresses.
echo Press Ctrl+C to stop.
"venv\Scripts\python.exe" -m src.run_remote_server
exit /b %ERRORLEVEL%
