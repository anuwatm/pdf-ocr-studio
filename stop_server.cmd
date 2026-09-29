@echo off
setlocal EnableExtensions
set "PORT=8000"

where curl.exe >nul 2>nul
if errorlevel 1 (
  echo Error: curl.exe was not found. Windows 10/11 includes curl by default.
  exit /b 1
)

curl.exe --silent --fail --max-time 2 "http://127.0.0.1:%PORT%/api/health" >nul 2>nul
if errorlevel 1 (
  echo OCR server is not running at http://127.0.0.1:%PORT%
  exit /b 0
)

set "SERVER_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:"127.0.0.1:%PORT% .*LISTENING"') do set "SERVER_PID=%%P"

if not defined SERVER_PID (
  echo Error: OCR server responded, but its process ID could not be found.
  exit /b 1
)

echo Stopping OCR server process %SERVER_PID%...
taskkill /PID %SERVER_PID% /T /F
if errorlevel 1 (
  echo Error: Windows denied access to the server process.
  echo Run stop_server.cmd from the same Windows account that started the server.
  exit /b 1
)
echo OCR server stopped.
exit /b 0
