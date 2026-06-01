@echo off
title Set OZON PVZ Session

cd /d "%~dp0"

python app\save_ozon_session.py
pause
