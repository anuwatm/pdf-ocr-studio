@echo off
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
  echo Python virtual environment not found. Run install.ps1 first.
  exit /b 1
)

"venv\Scripts\python.exe" -m uvicorn src.server:app --host 127.0.0.1 --port 8000 %*
