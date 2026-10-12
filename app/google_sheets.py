"""Direct Google Sheets API access. No Apps Script or public endpoint."""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

DOCUMENT = "Проверка цен"
TAB = "Проверка цен OZON"
ACCOUNT = "sheets-server@fresh-forest-436813-i5.iam.gserviceaccount.com"
API = "https://sheets.googleapis.com/v4/spreadsheets"
SKU = re.compile(r"\d{7,12}\Z")


def folder():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def load_connection():
    config_file, secret = folder() / "config.local.json", folder() / "service-account.json"
    if not config_file.is_file() or not secret.is_file():
        raise ValueError("Нет настроек Google: распакуйте полный закрытый комплект от администратора.")
    config = json.loads(config_file.read_text(encoding="utf-8-sig"))
    key = json.loads(secret.read_text(encoding="utf-8-sig"))
    sheet_id = config.get("spreadsheet_id", "")
    if not isinstance(sheet_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,}", sheet_id):
        raise ValueError("Неверный spreadsheet_id.")
    if key.get("type") != "service_account" or key.get("client_email") != ACCOUNT:
        raise ValueError("Неверный ключ сервисного аккаунта.")
    return {"sheet_id": sheet_id, "key": secret}


def session_for(connection):
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(
        str(connection["key"]), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return AuthorizedSession(creds)


def response_json(response, action):
    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("Неожиданный ответ Google: " + action) from exc
    if not response.ok:
        message = data.get("error", {}).get("message", str(response.status_code)) if isinstance(data, dict) else response.status_code
        raise ValueError(f"Ошибка Google ({action}): {message}")
    return data


def check_target(session, sid):
    meta = response_json(session.get(API + "/" + sid, params={
        "fields": "properties(title),sheets(properties(title))"}, timeout=30), "проверка документа")
    if meta["properties"]["title"] != DOCUMENT:
        raise ValueError("Подключена не та Google Таблица. Ожидается «Проверка цен».")
    if TAB not in [s.get("properties", {}).get("title") for s in meta.get("sheets", [])]:
        raise ValueError("Нет листа «Проверка цен OZON».")


def read_range(session, sid, cell_range):
    url = API + "/" + sid + "/values/" + quote("'" + TAB + "'!" + cell_range, safe="!")
    return response_json(session.get(url, timeout=30), "чтение таблицы").get("values", [])


def write_ranges(session, sid, ranges):
    response_json(session.post(API + "/" + sid + "/values:batchUpdate", timeout=60,
        json={"valueInputOption": "RAW", "data": [
            {"range": "'" + TAB + "'!" + area, "values": rows} for area, rows in ranges
        ]}), "запись цен")


def normalize(items):
    output = {}
    for row in items:
        article = row.get("article")
        price = row.get("price")
        if not isinstance(article, str) or not SKU.fullmatch(article):
            raise ValueError("Неверный артикул.")
        if price is not None and (type(price) is not int or price < 0):
            raise ValueError("Некорректная цена товара " + article)
        output[article] = price
    if not output:
        raise ValueError("Нет товаров для выгрузки.")
    return output


def upload_catalog(connection, catalog):
    """Replace only A:B in the selected sheet. Never modify C or any later column."""
    rows = normalize(catalog.items)
    items = [[sku, "Нет данных" if price is None else price]
             for sku, price in sorted(rows.items(), key=lambda x: int(x[0]))]
    session = session_for(connection)
    try:
        sid = connection["sheet_id"]
        check_target(session, sid)
        old = read_range(session, sid, "A2:A")
        rows_to_clear = max(len(old), len(items))
        output = [["Артикул товара", "Конечная цена"]] + items
        output.extend([["", ""]] * (rows_to_clear - len(items)))
        write_ranges(session, sid, [(f"A1:B{rows_to_clear + 1}", output)])
        return {"checked": len(catalog.items), "rows": len(items), "sheet": TAB}
    finally:
        session.close()
