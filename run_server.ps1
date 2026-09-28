# เริ่ม Local Thai OCR Web จากโฟลเดอร์นี้
# ใช้: .\run_server.ps1

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'ยังไม่พบ venv กำลังติดตั้ง dependencies...'
    try {
        & (Join-Path $PSScriptRoot 'install.ps1')
    } catch {
        throw 'ติดตั้งอัตโนมัติไม่สำเร็จ: ต้องมี Python 3.10+ แบบ 64-bit และเชื่อมต่ออินเทอร์เน็ตเพื่อติดตั้ง dependencies'
    }
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw 'ติดตั้งไม่สำเร็จ: ไม่พบ venv\Scripts\python.exe'
    }
}

& $venvPython -m uvicorn src.server:app --host 127.0.0.1 --port 8000
