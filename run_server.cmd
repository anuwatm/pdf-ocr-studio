@echo off
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
  echo ยังไม่ได้ติดตั้งระบบ กรุณารัน install.ps1 ก่อน
  exit /b 1
)

"venv\Scripts\python.exe" -m uvicorn src.server:app --host 127.0.0.1 --port 8000 %*
