@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv ".venv"
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r "app\requirements.txt"
if errorlevel 1 goto failed
echo.
echo Setup complete. Run ЗАПУСК.bat.
pause
exit /b 0
:failed
echo Installation failed. Verify Python 3 and Internet connection.
pause
exit /b 1
