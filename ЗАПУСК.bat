@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
    echo Setting up local Python environment...
    py -3 -m venv ".venv"
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import selenium, google.auth" >nul 2>&1
if errorlevel 1 (
    echo Installing required libraries into .venv...
    ".venv\Scripts\python.exe" -m pip install -r "app\requirements.txt"
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" "app\gui.py"
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Error. Please send a screenshot of this window to your administrator.
pause
exit /b 1
