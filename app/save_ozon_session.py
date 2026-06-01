#!/usr/bin/env python3

import json
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

BASE_DIR = Path(__file__).resolve().parent      # app/
ROOT_DIR = BASE_DIR.parent                      # корень проекта
SESSION_FILE = ROOT_DIR / "ozon_session.json"
OZON_HOME_URL = "https://www.ozon.ru/"


def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
    )

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )


def get_local_storage(driver):
    return driver.execute_script(
        """
        const result = {};
        for (let i = 0; i < window.localStorage.length; i++) {
            const key = window.localStorage.key(i);
            result[key] = window.localStorage.getItem(key);
        }
        return result;
        """
    )


def save_session(driver):
    session = {
        "cookies": driver.get_cookies(),
        "localStorage": get_local_storage(driver),
        "savedAt": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(SESSION_FILE, "w", encoding="utf-8") as file:
        json.dump(session, file, ensure_ascii=False, indent=2)

    print(f"\nOZON session saved to: {SESSION_FILE}")


def main():
    driver = create_driver()
    try:
        driver.get(OZON_HOME_URL)
        print("\nОткрылся Ozon.")
        print("1) Выбери нужный город/ПВЗ в Москве.")
        print("2) Дождись, пока на сайте отобразится выбранный адрес.")
        print("3) Вернись в эту консоль и нажми ENTER.\n")
        input("Нажми ENTER после выбора ПВЗ: ")
        save_session(driver)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
