@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if "%PROCESSOR_ARCHITECTURE%"=="x86" if "%PROCESSOR_ARCHITEW6432%"=="" (
  echo Error: Windows 64-bit is required by OneOCR.
  exit /b 1
)

if exist "venv\Scripts\python.exe" goto install_dependencies

where py.exe >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys; assert sys.version_info >= (3, 10) and sys.maxsize > 2**32" >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv venv
    if not errorlevel 1 goto install_dependencies
  )
)

where python.exe >nul 2>nul
if not errorlevel 1 (
  python -c "import sys; assert sys.version_info >= (3, 10) and sys.maxsize > 2**32" >nul 2>nul
  if not errorlevel 1 (
    python -m venv venv
    if not errorlevel 1 goto install_dependencies
  )
)

echo Error: Python 3.10+ 64-bit was not found.
echo Install Python from https://www.python.org/downloads/ and run this command again.
exit /b 1

:install_dependencies
echo Installing dependencies...
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

if not exist ".env" copy /y ".env.example" ".env" >nul
if not exist "data" mkdir "data"
if not exist "files" mkdir "files"

echo.
echo Installation complete.
echo Start the server with: run_server.cmd
exit /b 0
