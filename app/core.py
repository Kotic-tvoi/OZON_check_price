"""Input validation for the read-only Ozon storefront reader."""
from __future__ import annotations

import re
from urllib.parse import urlparse

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
