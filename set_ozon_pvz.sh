#!/usr/bin/env bash

cd "$(dirname "$0")"

python app/save_ozon_session.py
read -p "Press Enter to exit..."
