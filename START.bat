@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
if errorlevel 1 goto failed

if not exist ".venv\Scripts\python.exe" (
    echo Первая установка: создаем Python-окружение...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv ".venv"
    ) else (
        python -m venv ".venv"
    )
    if errorlevel 1 goto python_missing
)

if not exist ".venv\deps.ok" (
    echo Устанавливаем зависимости, потребуется интернет...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "app\requirements.txt"
    if errorlevel 1 goto failed
    type nul > ".venv\deps.ok"
)

".venv\Scripts\python.exe" "app\main.py" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
    echo Программа завершилась с ошибкой. Передайте текст окна ответственному.
) else (
    echo Работа завершена.
)
echo.
pause
exit /b %EXIT_CODE%

:python_missing
echo Не удалось создать Python-окружение.
echo Установите Python 3.10 или новее с python.org и повторите запуск.
goto failed

:failed
echo Не удалось запустить программу. Проверьте Python и интернет.
pause
exit /b 1
