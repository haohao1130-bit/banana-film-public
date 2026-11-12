@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install_Shortcut.ps1"
if errorlevel 1 (
 echo.
 echo Installation failed. No Git reset, model install or data deletion was performed.
)
echo.
pause
