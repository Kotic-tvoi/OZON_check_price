"""Read-only JSON API for Ozon storefronts. No database or persistent cache."""
from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from config import DEFAULT_PVZ, DEFAULT_STORE, MAX_REQUEST_BYTES
from core import InputError, pvz_url, store_url
from scraper import AccessError, CatalogError, collect

LOG = logging.getLogger('ozon.api')
BUSY = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        LOG.info(fmt, *args)

    def send_json(self, status, data):
        content = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_bytes(status, content, 'application/json; charset=utf-8')

    def send_bytes(self, status, content, mime, filename=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.path == '/health':
            self.send_json(200, {'status': 'ready', 'read_only': True})
        else:
            self.send_json(404, {'error': 'not_found'})

    def do_POST(self):
        if self.path not in ('/v1/catalog', '/v1/catalog.xlsx'):
            return self.send_json(404, {'error': 'not_found'})
        token = os.getenv('OZON_API_TOKEN', '')
        if not token or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
            return self.send_json(401, {'error': 'unauthorized'})
        if not BUSY.acquire(blocking=False):
            return self.send_json(409, {'error': 'busy'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 1 <= length <= MAX_REQUEST_BYTES:
                raise InputError('Неверный размер запроса')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise InputError('Ожидается JSON-объект')
            # Ручной список артикулов больше не поддерживается: собираем весь магазин.
            if set(body) - {'store_url', 'pvz_url'}:
                raise InputError('Допустимы только store_url и pvz_url; список articles не нужен')
            store = store_url(body.get('store_url', DEFAULT_STORE))
            pvz = pvz_url(body.get('pvz_url', DEFAULT_PVZ))
            catalog = collect(store, pvz)
            if not catalog.complete:
                return self.send_json(503, {'error': 'catalog_incomplete',
                    'message': 'Не удалось подтвердить загрузку всего каталога',
                    'found': len(catalog.items)})
            if self.path == '/v1/catalog.xlsx':
                from xlsx_export import to_xlsx
                # Excel создаётся только в оперативной памяти и сразу отдаётся клиенту.
                return self.send_bytes(200, to_xlsx(catalog.items),
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    filename='ozon_catalog.xlsx')
            return self.send_json(200, catalog.as_dict())
        except (InputError, ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {'error':'invalid_request','message':str(exc)})
        except (AccessError, CatalogError) as exc:
            self.send_json(503, {'error':'ozon_unavailable','message':str(exc)})
        except Exception:
            LOG.exception('Internal scraping failure')
            self.send_json(500, {'error':'internal_error'})
        finally:
            BUSY.release()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bind', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8765)
    args = p.parse_args()
    if not os.getenv('OZON_API_TOKEN'):
        p.error('Сначала установите OZON_API_TOKEN')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    ThreadingHTTPServer((args.bind, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()