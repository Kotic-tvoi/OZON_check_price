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


def merge(old, items, complete, same_source):
    found = normalize(items)
    if not complete and old and not same_source:
        raise ValueError("Каталог неполный и магазин/ПВЗ изменён. Старые цены не перезаписаны.")
    output = {}
    if not complete:
        for row in old:
            if row and SKU.fullmatch(str(row[0])):
                output[str(row[0])] = row[1] if len(row) > 1 else "Нет данных"
    for article, price in found.items():
        if price is not None or article not in output:
            output[article] = price if price is not None else "Нет данных"
    return [[key, output[key]] for key in sorted(output, key=int)]


def prepare_rows(old, previous, catalog):
    """Update article/price columns, status fields; never touch employee controls."""
    previous_store = previous[0][0] if len(previous) >= 1 and previous[0] else ""
    previous_pvz = previous[1][0] if len(previous) >= 2 and previous[1] else ""
    same = previous_store == catalog.store_url and previous_pvz == catalog.pvz_url
    items = merge(old, catalog.items, catalog.complete, same)
    count = max(len(old), len(items))
    table = [["Артикул товара", "Конечная цена"]] + items + [["", ""]] * (count - len(items))
    state = "Готово" if catalog.complete else "Неполный каталог"
    details = [
        ["Состояние", state],
        ["Время проверки", datetime.now().astimezone().isoformat(timespec="seconds")],
        ["Проверено артикулов", len(catalog.items)],
        ["Полнота", "Подтверждена" if catalog.complete else "Не подтверждена"],
        ["Сообщение", "Проверка завершена" if catalog.complete else
         "Старые отсутствующие позиции сохранены, их цены могут быть неактуальны"],
        ["Адрес ПВЗ", catalog.pvz_address],
        ["Магазин URL", catalog.store_url],
        ["ПВЗ URL", catalog.pvz_url],
    ]
    ranges = [(f"A1:B{count + 1}", table), ("D3:E10", details)]
    return ranges, {"checked": len(catalog.items), "rows": len(items),
                    "complete": catalog.complete, "sheet": TAB}


def upload_catalog(connection, catalog):
    session = session_for(connection)
    try:
        sid = connection["sheet_id"]
        check_target(session, sid)
        old = read_range(session, sid, "A2:B")
        prev = read_range(session, sid, "E9:E10")
        ranges, result = prepare_rows(old, prev, catalog)
        write_ranges(session, sid, ranges)
        return result
    finally:
        session.close()
