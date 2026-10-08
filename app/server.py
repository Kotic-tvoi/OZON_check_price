#!/usr/bin/env python3
"""On-demand Ozon price JSON service for Google Apps Script, Python stdlib HTTP server."""
from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from core import DEFAULT_PVZ, InputError, PriceItem, normalize_pvz_url, validate_request

LOG = logging.getLogger('ozon.api')
REQUEST_LOCK = threading.Lock()
MAX_BODY_BYTES = 120_000


class APIHandler(BaseHTTPRequestHandler):
    server_version = 'OzonPriceReadOnly/1.0'

    def log_message(self, fmt, *args):
        # Never log request payload, tokens, or price data.
        LOG.info('%s %s', self.address_string(), fmt % args)

    def respond(self, status: int, payload: dict):
        self.respond_bytes(status, json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                           'application/json; charset=utf-8')

    def respond_bytes(self, status: int, payload: bytes, content_type: str, disposition: str | None = None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Pragma', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if disposition:
            self.send_header('Content-Disposition', disposition)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == '/health':
            self.respond(200, {'status': 'ready', 'read_only': True})
        else:
            self.respond(404, {'error': 'not_found'})

    def _authorize(self) -> bool:
        expected = os.environ.get('OZON_API_TOKEN', '')
        provided = self.headers.get('Authorization', '')
        if not expected or not hmac.compare_digest(provided, f'Bearer {expected}'):
            self.respond(401, {'error': 'unauthorized'})
            return False
        return True

    def _read_payload(self) -> dict:
        try:
            length = int(self.headers.get('Content-Length', ''))
        except ValueError as exc:
            raise InputError('Неверный Content-Length') from exc
        if not (1 <= length <= MAX_BODY_BYTES):
            raise InputError('JSON-запрос слишком большой либо пустой')
        try:
            content = self.rfile.read(length).decode('utf-8')
            result = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InputError('Неверный JSON') from exc
        if not isinstance(result, dict):
            raise InputError('JSON должен быть объектом')
        return result

    def do_POST(self):
        paths = ('/v1/prices', '/v1/prices.xlsx', '/v1/pvz/check', '/v1/diagnostics/price')
        if urlparse(self.path).path not in paths or urlparse(self.path).query:
            return self.respond(404, {'error': 'not_found'})
        if not self._authorize():
            return
        if not REQUEST_LOCK.acquire(blocking=False):
            return self.respond(409, {'error': 'busy', 'message': 'Предыдущий сбор ещё выполняется'})
        held = True
        def unlock():
            nonlocal held
            if held:
                held = False
                REQUEST_LOCK.release()

        try:
            body = self._read_payload()
            path = self.path
            if path in ('/v1/prices', '/v1/prices.xlsx'):
                items = validate_request(body)
                from scraper import scan_items
                result_rows = scan_items(items)
                if path.endswith('.xlsx'):
                    from xlsx_export import to_xlsx
                    data = to_xlsx(result_rows)
                    unlock()
                    return self.respond_bytes(200, data,
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        'attachment; filename="ozon_prices.xlsx"')
                response = {
                    'read_only': True,
                    'pvz_url': items[0].pvz_url,
                    'summary': {
                        'total': len(result_rows),
                        'found': sum(r.price is not None for r in result_rows),
                    },
                    # One PVZ at the root, no repeated link for each SKU in JSON.
                    'results': [{key: value for key, value in r.to_dict().items() if key != 'pvz_url'}
                                for r in result_rows],
                }
                unlock()
                return self.respond(200, response)
            elif path == '/v1/pvz/check':
                from scraper import create_driver, set_pvz
                pvz_url = normalize_pvz_url(body.get('pvz_url', DEFAULT_PVZ))
                address = body.get('pvz_address')
                driver = create_driver()
                try:
                    selected = set_pvz(driver, pvz_url, address)
                    unlock()
                    return self.respond(200, {'status': 'verified', 'pvz_url': pvz_url,
                                              'pvz_address': selected})
                finally:
                    driver.quit()
            else:
                items = validate_request(body)
                if len(items) != 1:
                    raise InputError('Для диагностики укажите ровно один SKU')
                from scraper import diagnose_price
                diagnostic = diagnose_price(items[0])
                unlock()
                return self.respond(200, diagnostic)
        except (InputError, ValueError) as exc:
            unlock()
            self.respond(400, {'error': 'invalid_request', 'message': str(exc)})
        except Exception as exc:
            LOG.exception('Ошибка обработки запроса')
            unlock()
            self.respond(500, {'error': 'scraper_error', 'message': f'{type(exc).__name__}: {str(exc)[:240]}'})
        finally:
            unlock()


def main():
    parser = argparse.ArgumentParser(description='Ozon price reader (no DB, JSON on demand)')
    parser.add_argument('--bind', default='127.0.0.1', help='Слушать локально за HTTPS-прокси')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--check-pvz', metavar='URL', help='Локальная проверка ПВЗ без HTTP-сервера')
    parser.add_argument('--article', help='SKU для проверки после установки ПВЗ')
    parser.add_argument('--headed', action='store_true', help='Видимый Chrome при локальном тесте')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.check_pvz:
        from scraper import create_driver, set_pvz, read_article
        from core import normalize_article
        url = normalize_pvz_url(args.check_pvz)
        driver = create_driver(headed=args.headed)
        try:
            address = set_pvz(driver, url)
            print(json.dumps({'status': 'pvz_verified', 'pvz_url': url, 'address': address}, ensure_ascii=False))
            if args.article:
                item = PriceItem(index=0, article=normalize_article(args.article), pvz_url=url)
                print(json.dumps(read_article(driver, item, address).to_dict(), ensure_ascii=False))
        finally:
            driver.quit()
        return
    if not os.environ.get('OZON_API_TOKEN'):
        parser.error('Перед запуском установите OZON_API_TOKEN (секретный API-токен)')
    LOG.info('Ozon price service, read-only, no database; http://%s:%s', args.bind, args.port)
    ThreadingHTTPServer((args.bind, args.port), APIHandler).serve_forever()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)