@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not defined LOCALAPPDATA (
    echo Windows user profile is unavailable.
    goto failed
)
set "APP_ENV=%LOCALAPPDATA%\JKeratinPriceParser\.venv"
if not exist "%APP_ENV%\Scripts\python.exe" (
    echo Creating a private Python environment for this Windows user...
    py -3 -m venv "%APP_ENV%"
    if errorlevel 1 goto failed
)
"%APP_ENV%\Scripts\python.exe" -c "import selenium, google.auth, requests" >nul 2>&1
if errorlevel 1 (
    echo Installing required libraries into the private virtual environment...
    "%APP_ENV%\Scripts\python.exe" -m pip install -r "%~dp0app\requirements.txt"
    if errorlevel 1 goto failed
)
"%APP_ENV%\Scripts\python.exe" "%~dp0app\gui.py"
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Error. Please send a screenshot of this window to your administrator.
pause
exit /b 1
