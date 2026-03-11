#!/usr/bin/env python3

import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from openpyxl import Workbook

# Пути проекта
BASE_DIR = Path(__file__).resolve().parent      # app/
ROOT_DIR = BASE_DIR.parent                      # корень проекта

SKU_FILE = ROOT_DIR / "SKU_Ozon.txt"
REPORTS_DIR = ROOT_DIR / "reports"


# ===============================
# Настройки Selenium
# ===============================

chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--window-size=1920,1080")

chrome_options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
)

chrome_options.add_argument("--disable-images")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-extensions")

chrome_prefs = {
    "profile.managed_default_content_settings.images": 2,
    "profile.managed_default_content_settings.stylesheets": 2,
    "profile.managed_default_content_settings.fonts": 2,
    "profile.managed_default_content_settings.javascript": 1
}

chrome_options.add_experimental_option("prefs", chrome_prefs)


# ===============================
# Вспомогательные функции
# ===============================

def load_links(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return [line.strip() for line in file if line.strip()]

def is_page_available(driver, timeout=5):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return True
    except Exception:
        return False

def get_element(driver, xpaths, default=None, timeout=5):
    for xpath in xpaths:
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            text = element.text.strip()

            if text:
                return text

        except Exception:
            continue

    return default

def clear_price(value: str):

    if not value:
        return None

    try:
        clean = (
            value.replace("₽", "")
                 .replace("\u2009", "")
                 .replace("\xa0", "")
                 .replace(" ", "")
                 .strip()
        )

        return int(clean)

    except ValueError:
        return None


# ===============================
# Excel
# ===============================

def make_output_filename():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H-%M_%d.%m.%Y")
    return REPORTS_DIR / f"{timestamp}.xlsx"


def save_to_excel(data, output_file):
    wb = Workbook()
    ws = wb.active
    ws.title = "OZON Prices"
    ws.append(["Артикул товара", "Конечная цена"])
    for row in data:
        ws.append([row["article"], row["card_price"]])
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 18
    wb.save(output_file)
    print(f"Date download to Excel: {output_file}")


# ===============================
# Парсинг карточек
# ===============================

def parse_product_page(driver, article):
    try:
        url = f"https://www.ozon.ru/product/{article}/"
        driver.get(url)
        if not is_page_available(driver, timeout=5):
            print(f"[WARNING] page don't load to {article}")
            return {
                "article": article,
                "card_price": None
            }
        xpaths = {
            "card_price": [
                "//span[contains(@class,'tsHeadline600Large')]",
                "//span[contains(@class,'pdp_bq9 tsHeadline600Large')]",
                "//div[contains(@data-widget,'webPrice')]//span[contains(text(),'₽')]"
            ]
        }
        card_price_raw = get_element(driver, xpaths["card_price"])
        card_price = clear_price(card_price_raw)
        print(f"{article}: final price {card_price}")
        return {
            "article": article,
            "card_price": card_price
        }

    except Exception as e:
        print(f"ERROR to download {article}: {e}")
        return {
            "article": article,
            "card_price": None
        }


# ===============================
# Selenium
# ===============================

def create_driver():
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )


# ===============================
# Основной процесс
# ===============================

def process_articles(articles, max_threads=3):
    results = []
    def worker(article):
        driver = create_driver()
        try:
            return parse_product_page(driver, article)
        finally:
            driver.quit()
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = [executor.submit(worker, article) for article in articles]
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
    article_order = {article: i for i, article in enumerate(articles)}
    results.sort(key=lambda x: article_order.get(str(x["article"]), 999999))
    print("All proces complite")
    return results

# ===============================
# MAIN
# ===============================

def main():
    output_file = make_output_filename()
    articles = load_links(SKU_FILE)

    print(f"Start parcing {len(articles)} articles...")
    results = process_articles(articles, max_threads=3)
    save_to_excel(results, output_file)

if __name__ == "__main__":
    start_time = time.perf_counter()
    main()
    end_time = time.perf_counter()
    elapsed = end_time - start_time
    print(f"Time to complete: {elapsed:.2f} sec ({elapsed / 60:.2f} min)")