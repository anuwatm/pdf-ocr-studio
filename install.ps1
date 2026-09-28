# ติดตั้ง Local Thai OCR Web บน Windows เครื่องใหม่
# ใช้: .\install.ps1

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not [Environment]::Is64BitOperatingSystem) {
    throw 'ต้องใช้ Windows 64-bit เพราะ OneOCR DLL เป็น 64-bit'
}

$launcher = Get-Command py -ErrorAction SilentlyContinue
if (-not $launcher) {
    throw 'ไม่พบ Python Launcher (py) กรุณาติดตั้ง Python 3.10+ แบบ 64-bit แล้วเปิด PowerShell ใหม่'
}

$available = & $launcher.Source -0p 2>$null
$candidates = foreach ($line in $available) {
    if ($line -match '-V:(\d+\.\d+).*?([A-Za-z]:\\.*python\.exe)\s*$') {
        $version = [version]$Matches[1]
        if ($version -ge [version]'3.10') {
            [pscustomobject]@{ Version = $version; Path = $Matches[2] }
        }
    }
}
$selected = $candidates | Sort-Object Version -Descending | Select-Object -First 1
if (-not $selected) {
    throw 'ไม่พบ Python 3.10+ กรุณาติดตั้ง Python 3.10+ แบบ 64-bit'
}

if (-not (Test-Path -LiteralPath '.\venv\Scripts\python.exe')) {
    & $selected.Path -m venv venv
}

$venvPython = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}

New-Item -ItemType Directory -Path data, files -Force | Out-Null
Write-Host ''
Write-Host 'ติดตั้งเสร็จแล้ว'
Write-Host '1. ตั้งค่า Local LLM ที่ http://127.0.0.1:8000/config.html หลังเปิด server'
Write-Host '2. เริ่มระบบด้วย .\run_server.ps1'
