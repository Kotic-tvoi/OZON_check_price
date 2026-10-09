@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Первоначальная установка локального агента...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv ".venv"
    ) else (
        python -m venv ".venv"
    )
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "app\requirements.txt"
if errorlevel 1 goto fail
echo.
echo Агент запускается. Оставьте это окно открытым.
".venv\Scripts\python.exe" "app\agent.py"
if errorlevel 1 goto fail
echo.
pause
exit /b 0
:fail
echo ОШИБКА. Проверьте Python, интернет и настройки Google.
pause
exit /b 1
