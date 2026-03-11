#!/usr/bin/env bash

cd "$(dirname "$0")"

mkdir -p reports
python app/main.py
read -p "Press Enter to exit..."