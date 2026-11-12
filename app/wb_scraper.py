"""Public Wildberries seller-catalog reader for local price checks.

This prototype deliberately sends no login cookies, bearer token, browser profile,
or other account credentials. It uses the public storefront catalog endpoint and
stops with a clear error when Wildberries denies or rate-limits access.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

LOG = logging.getLogger("wb.catalog")
CATALOG_URL = "https://www.wildberries.ru/__internal/catalog/sellers/v4/catalog"
DEFAULT_DEST = "-1257786"
MAX_PAGES = 100
REQUEST_TIMEOUT = 20
PAGE_DELAY = 0.25

DESTINATIONS = {
    "Москва": "-1257786",
    "Санкт-Петербург": "-1205339",
    "Казань": "-2133462",
    "Сыктывкар": "123585595",
}


class WBAccessError(RuntimeError):
    """The public catalog endpoint is blocked, rate-limited, or unavailable."""


class WBCatalogError(RuntimeError):
    """The catalog response is missing or cannot be parsed."""


@dataclass
class WBCatalog:
    store_url: str
    destination: str
    items: list[dict]
    elapsed_seconds: float


def normalize_store_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Укажите ссылку на магазин Wildberries.")
    parsed = urlparse(value.strip())
    if (parsed.scheme != "https" or parsed.hostname not in
            ("wildberries.ru", "www.wildberries.ru") or parsed.username or
            parsed.password or parsed.port or parsed.query or parsed.fragment):
        raise ValueError("Нужна ссылка вида https://www.wildberries.ru/seller/123456/")
    match = re.fullmatch(r"/seller/(\d+)/?", parsed.path)
    if not match:
        raise ValueError("Ссылка магазина должна быть вида https://www.wildberries.ru/seller/123456/")
    return f"https://www.wildberries.ru/seller/{match.group(1)}/"


def normalize_destination(value: str) -> str:
    raw = str(value).strip()
    if not re.fullmatch(r"-?\d{1,12}", raw):
        raise ValueError("Укажите регион WB числовым кодом dest, например -1257786.")
    return raw


def _price_rubles(value):
    if value is None:
        return None
    try:
        return round(int(value) / 100)
    except (TypeError, ValueError, OverflowError):
        return None


def _read_products(payload: dict) -> list[dict]:
    products = payload.get("products")
    if not isinstance(products, list):
        raise WBCatalogError("WB вернул каталог в неизвестном формате.")
    rows = []
    for product in products:
        if not isinstance(product, dict):
            continue
        sizes = product.get("sizes") or []
        price = sizes[0].get("price") if sizes and isinstance(sizes[0], dict) else {}
        if not isinstance(price, dict):
            price = {}
        article = product.get("id")
        if article is None:
            continue
        rows.append({
            "article": str(article),
            "name": str(product.get("name") or ""),
            "price": _price_rubles(price.get("product")),
            "old_price": _price_rubles(price.get("basic")),
        })
    return rows


def collect(store: str, destination: str = DEFAULT_DEST, *,
            max_pages: int = MAX_PAGES, timeout: int = REQUEST_TIMEOUT) -> WBCatalog:
    store = normalize_store_url(store)
    destination = normalize_destination(destination)
    if not 1 <= max_pages <= MAX_PAGES:
        raise ValueError(f"Число страниц должно быть от 1 до {MAX_PAGES}.")
    seller_id = re.search(r"/seller/(\d+)/", store).group(1)
    session = requests.Session()
    # No Cookie / Authorization headers and no browser session are used.
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
        "Referer": store,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/131.0.0.0 Safari/537.36",
    })
    started = time.monotonic()
    seen: dict[str, dict] = {}
    try:
        for page in range(1, max_pages + 1):
            params = {
                "ab_testing": "false",
                "appType": "64",
                "curr": "rub",
                "dest": destination,
                "hide_dtype": "15",
                "hide_vflags": "4294967296",
                "lang": "ru",
                "page": page,
                "sort": "popular",
                "spp": "30",
                "supplier": seller_id,
                "uclusters": "3",
            }
            try:
                response = session.get(CATALOG_URL, params=params, timeout=timeout)
            except requests.RequestException as exc:
                raise WBAccessError("Не удалось подключиться к Wildberries. Проверьте интернет и повторите попытку.") from exc
            if response.status_code in (401, 403, 429):
                raise WBAccessError(
                    f"Wildberries ограничил публичный запрос (HTTP {response.status_code}). "
                    "Парсер остановлен без обхода ограничения; попробуйте позже."
                )
            if response.status_code != 200:
                raise WBAccessError(f"Wildberries вернул HTTP {response.status_code}.")
            try:
                payload = response.json()
            except ValueError as exc:
                raise WBCatalogError("WB вернул не JSON. Возможно, показана страница ограничения доступа.") from exc
            if not isinstance(payload, dict):
                raise WBCatalogError("WB вернул каталог в неизвестном формате.")
            products = _read_products(payload)
            if not products:
                break
            for row in products:
                seen[row["article"]] = row
            LOG.info("WB page %s: %s products; total %s", page, len(products), len(seen))
            time.sleep(PAGE_DELAY)
        if not seen:
            raise WBCatalogError("В открытом каталоге не найдены товары с ценами.")
        return WBCatalog(
            store_url=store,
            destination=destination,
            items=sorted(seen.values(), key=lambda row: int(row["article"])),
            elapsed_seconds=round(time.monotonic() - started, 2),
        )
    finally:
        session.close()
