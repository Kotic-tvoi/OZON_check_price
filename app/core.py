"""Validation and lightweight data models. No database or persistent price cache."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

DEFAULT_PVZ = "https://www.ozon.ru/geo/moskva/442329/"
MAX_ITEMS = 100
GEO_PATH = re.compile(r"^/geo/([a-z0-9-]+)/([0-9]+)/?$", re.I)
SKU_RE = re.compile(r"^[0-9]{1,24}$")


class InputError(ValueError):
    pass


def normalize_pvz_url(value: str) -> str:
    """Allow only real Ozon geo URLs; never navigate Selenium to arbitrary URLs."""
    if not isinstance(value, str) or not value.strip():
        raise InputError("Нужна ссылка на ПВЗ Ozon")
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.hostname not in ("www.ozon.ru", "ozon.ru"):
        raise InputError("ПВЗ должен быть ссылкой https://www.ozon.ru/geo/...")
    if parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise InputError("В ссылке ПВЗ нельзя передавать дополнительные параметры")
    match = GEO_PATH.fullmatch(parsed.path)
    if not match:
        raise InputError("Ожидается ссылка вида https://www.ozon.ru/geo/moskva/442329/")
    city_slug, pvz_id = match.groups()
    return f"https://www.ozon.ru/geo/{city_slug.lower()}/{pvz_id}/"


def normalize_article(value) -> str:
    if isinstance(value, bool):
        raise InputError("Артикул должен состоять из цифр")
    article = str(value).strip()
    if not SKU_RE.fullmatch(article):
        raise InputError(f"Некорректный артикул: {article[:80]!r}")
    return article


@dataclass(frozen=True)
class PriceItem:
    index: int
    article: str
    pvz_url: str
    pvz_address: str | None = None


@dataclass
class PriceResult:
    index: int
    article: str
    pvz_url: str
    price: int | None = None
    price_type: str = "unknown"
    status: str = "error"
    pvz_address: str | None = None
    checked_at: str | None = None
    source: str | None = None
    message: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def validate_request(payload: object) -> list[PriceItem]:
    if not isinstance(payload, dict):
        raise InputError("Ожидается JSON-объект")
    if "items" in payload:
        raise InputError("Передайте один pvz_url для всего запроса и массив articles")
    articles = payload.get("articles")
    if not isinstance(articles, list) or not (1 <= len(articles) <= MAX_ITEMS):
        raise InputError(f"articles должен содержать от 1 до {MAX_ITEMS} артикулов")

    pvz_url = normalize_pvz_url(payload.get("pvz_url", DEFAULT_PVZ))
    pvz_address = payload.get("pvz_address")
    if pvz_address is not None:
        if not isinstance(pvz_address, str) or len(pvz_address.strip()) > 200:
            raise InputError("pvz_address должен быть текстом до 200 символов")
        pvz_address = pvz_address.strip() or None

    return [PriceItem(index=index, article=normalize_article(article),
                      pvz_url=pvz_url, pvz_address=pvz_address)
            for index, article in enumerate(articles)]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

