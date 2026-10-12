@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  echo First run УСТАНОВКА.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "app\gui.py"
if errorlevel 1 pause
