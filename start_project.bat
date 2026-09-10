@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_project.ps1"
if errorlevel 1 (
  echo.
  echo Project startup failed. Review the message above and data log files.
  exit /b 1
)
