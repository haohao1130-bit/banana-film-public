@echo off
setlocal
title BANANA FILM 5070 STUDIO - F Drive
set "BOOT=%~dp0Bootstrap_BANANA_FILM_5070.ps1"
if not exist "%BOOT%" set "BOOT=%~dp0tools\bootstrap_film_v2_5070.ps1"
if not exist "%BOOT%" (
  echo ERROR: Bootstrap PowerShell script is missing. Extract the whole ZIP first.
  pause
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%BOOT%" %*
if errorlevel 1 (
  echo.
  echo BANANA FILM 5070 STUDIO could not start. The original models and projects were not deleted.
  echo See F:\BANANA_FILM_5070_STUDIO\Media\logs for diagnostic logs.
  pause
  exit /b 1
)
exit /b 0
