"""Upload the locally collected catalog to a Google Apps Script web app.

The secret stays in config.local.json, never in the GitHub repository.
No Google Cloud project, background service, or public PC port required.
"""
from __future__ import annotations

import getpass
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

CONNECTION_FILE = Path(__file__).resolve().parent.parent / 'config.local.json'
SCRIPT_PATH = re.compile(r'^/macros/s/[^/]+/exec/?$')


def _validate_url(url: str) -> str:
    p = urlsplit(url.strip())
    if (p.scheme != 'https' or p.hostname != 'script.google.com'
            or p.username or p.password or p.port or p.query or p.fragment
            or not SCRIPT_PATH.fullmatch(p.path)):
        raise ValueError('Нужна ссылка Apps Script вида https://script.google.com/macros/s/.../exec')
    return url.strip()


def _validate_connection(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError('Некорректный config.local.json')
    url = _validate_url(data.get('web_app_url', ''))
    token = data.get('upload_token', '')
    if not isinstance(token, str) or len(token.strip()) < 32:
        raise ValueError('Ключ загрузки должен содержать не менее 32 символов')
    return {'web_app_url': url, 'upload_token': token.strip()}


def load_connection() -> dict:
    if CONNECTION_FILE.exists():
        try:
            return _validate_connection(json.loads(CONNECTION_FILE.read_text(encoding='utf-8')))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(
                'Ошибка в config.local.json: ' + str(exc)
                + '. Исправьте его или удалите файл для повторной настройки.'
            ) from exc

    print('\nПЕРВАЯ НАСТРОЙКА GOOGLE ТАБЛИЦЫ')
    print('Попросите ответственного за таблицу дать ссылку веб-приложения и ключ загрузки.')
    url = input('Вставьте ссылку Apps Script (.../exec): ').strip()
    token = getpass.getpass('Вставьте секретный ключ загрузки (не отображается): ').strip()
    connection = _validate_connection({'web_app_url': url, 'upload_token': token})
    CONNECTION_FILE.write_text(
        json.dumps(connection, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print('Настройки сохранены только на этом компьютере.\n')
    return connection


def upload_catalog(connection: dict, catalog) -> dict:
    config = _validate_connection(connection)
    payload = json.dumps({
        'token': config['upload_token'],
        'complete': bool(catalog.complete),
        'store_url': catalog.store_url,
        'pvz_url': catalog.pvz_url,
        'pvz_address': catalog.pvz_address,
        'items': catalog.items,
    }, ensure_ascii=False).encode('utf-8')

    request = Request(
        config['web_app_url'],
        data=payload,
        headers={'Content-Type': 'application/json; charset=utf-8'},
        method='POST',
    )
    try:
        with urlopen(request, timeout=60) as response:
            raw = response.read(1024 * 1024).decode('utf-8', errors='replace')
    except HTTPError as exc:
        raise ValueError(f'Google вернул HTTP {exc.code}. Проверьте доступ к веб-приложению.') from exc
    except URLError as exc:
        raise ValueError('Нет соединения с Google Apps Script: ' + str(exc.reason)) from exc

    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(
            'Google вернул не JSON. Проверьте публикацию веб-приложения '
            '(выполнение от вашего аккаунта, доступ «Все»), '
            'ссылку /exec и разрешения скрипта.'
        ) from exc
    if not isinstance(result, dict) or result.get('ok') is not True:
        detail = result.get('error', 'неизвестная ошибка') if isinstance(result, dict) else 'неизвестный ответ'
        raise ValueError('Google Таблица не приняла данные: ' + str(detail))
    if not isinstance(result.get('sheet'), str) or not isinstance(result.get('count'), int):
        raise ValueError('Некорректное подтверждение записи от Google')
    return result
