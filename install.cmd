@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); & '%~dp0install.ps1'"
exit /b %ERRORLEVEL%
