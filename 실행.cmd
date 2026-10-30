@echo off
cd /d "%~dp0"
echo Open http://127.0.0.1:8765 in your browser after the server starts.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
pause
