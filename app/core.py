"""Input validation for the read-only Ozon storefront reader."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from config import MAX_ARTICLES
SKU_PATTERN = re.compile(r'\d{1,24}\Z')


class InputError(ValueError):
    pass


def _ozon_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError('Необходимо указать ссылку Ozon')
    parsed = urlparse(value.strip())
    if (parsed.scheme != 'https' or parsed.hostname not in ('ozon.ru', 'www.ozon.ru')
            or parsed.username or parsed.password or parsed.port
            or parsed.query or parsed.fragment):
        raise InputError('Нужна ссылка https://www.ozon.ru/ без дополнительных параметров')
    return parsed.path


def store_url(value: str) -> str:
    path = _ozon_path(value)
    if not re.fullmatch(r'/seller/[a-z0-9_-]+(?:/products)?/?', path, re.I):
        raise InputError('Ссылка магазина должна быть вида https://www.ozon.ru/seller/название/')
    return 'https://www.ozon.ru' + path.rstrip('/') + '/'


def pvz_url(value: str) -> str:
    path = _ozon_path(value)
    if not re.fullmatch(r'/geo/[a-z0-9-]+/\d+/?', path, re.I):
        raise InputError('Ссылка ПВЗ должна быть вида https://www.ozon.ru/geo/moskva/442329/')
    return 'https://www.ozon.ru' + path.rstrip('/') + '/'


def articles(value) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ARTICLES:
        raise InputError('articles: массив из 1–100 артикулов либо поле не передано')
    result = []
    for article in value:
        if isinstance(article, bool) or not SKU_PATTERN.fullmatch(str(article).strip()):
            raise InputError(f'Некорректный артикул: {str(article)[:70]}')
        result.append(str(article).strip())
    return result