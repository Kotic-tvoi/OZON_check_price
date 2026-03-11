@echo off
title OZON Price Parser

cd /d "%~dp0"

if not exist reports (
    mkdir reports
)
python app\main.py
pause