import io
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from core import InputError, PriceResult, normalize_pvz_url, validate_request
from scraper import address_matches, geo_page_address, price_as_int, scan_items
from xlsx_export import to_xlsx
from server import APIHandler, ThreadingHTTPServer

MOSCOW = 'https://www.ozon.ru/geo/moskva/442329/'
ALT = 'https://www.ozon.ru/geo/moskva/511288/'


class TestInput(unittest.TestCase):
    def test_normalize_url(self):
        self.assertEqual(normalize_pvz_url('https://ozon.ru/geo/moskva/442329'), MOSCOW)
        self.assertEqual(normalize_pvz_url(ALT), ALT)

    def test_reject_external_and_bad_urls(self):
        for url in ('http://www.ozon.ru/geo/moskva/442329/',
                    'https://www.ozon.ru.evil.test/geo/moskva/442329/',
                    'https://www.ozon.ru/product/123/',
                    'https://www.ozon.ru/geo/moskva/442329/?x=1',
                    'file:///etc/passwd'):
            with self.subTest(url=url), self.assertRaises(InputError):
                normalize_pvz_url(url)

    def test_one_pvz_for_entire_request(self):
        items = validate_request({'pvz_url': ALT,
                                  'articles': [380181277, '380181277', '2624769265']})
        self.assertEqual(len(items), 3)
        self.assertEqual({x.pvz_url for x in items}, {ALT})
        self.assertEqual([x.article for x in items], ['380181277', '380181277', '2624769265'])
        self.assertEqual([x.index for x in items], [0, 1, 2])

    def test_default_pvz(self):
        items = validate_request({'articles': ['380181277']})
        self.assertEqual(items[0].pvz_url, MOSCOW)

    def test_reject_row_based_pvz_urls(self):
        with self.assertRaises(InputError):
            validate_request({'items': [{'article': '123', 'pvz_url': ALT}]})
        with self.assertRaises(InputError):
            validate_request({'articles': [{'article': '123', 'pvz_url': ALT}]})
        with self.assertRaises(InputError):
            validate_request({'articles': ['=SUM(A:A)']})

    def test_address_matching(self):
        title = 'Россия, Москва, Палехская улица, 21'
        self.assertTrue(address_matches(title, 'Доставка по адресу: Москва, Палехская ул., 21 | Корзина'))
        self.assertFalse(address_matches(title, 'Москва, Палехская улица, 27 | Акция до 21 октября'))
        self.assertTrue(address_matches('Москва, Варшавское шоссе, 282к3', 'Москва, Варшавское ш., 282к3'))

    def test_geo_page_title(self):
        obj = MagicMock()
        obj.title = 'Пункт Ozon: Россия, Москва, Палехская улица, 21 - время работы, условия доставки'
        self.assertEqual(geo_page_address(obj), 'Россия, Москва, Палехская улица, 21')

    def test_price_value(self):
        self.assertEqual(price_as_int('1\u202f234 ₽'), 1234)
        self.assertIsNone(price_as_int('от 1 234 ₽'))
        self.assertIsNone(price_as_int('1 234 ₽ 2 000 ₽'))


class TestScraper(unittest.TestCase):
    @patch('scraper.read_article')
    @patch('scraper.set_pvz')
    @patch('scraper.create_driver')
    def test_reuse_one_browser_for_entire_request(self, new_driver, set_pvz, read_article):
        driver = MagicMock()
        new_driver.return_value = driver
        set_pvz.return_value = 'Москва, Палехская улица, 21'
        read_article.side_effect = lambda drv, item, address: PriceResult(
            index=item.index, article=item.article, pvz_url=item.pvz_url, price=200,
            status='ok_unverified_price_type')
        items = validate_request({'articles': ['123', '456', '789']})
        results = scan_items(items)
        self.assertEqual([r.price for r in results], [200, 200, 200])
        self.assertEqual(new_driver.call_count, 1)
        self.assertEqual(driver.quit.call_count, 1)
        self.assertEqual(read_article.call_count, 3)

    def test_reject_multiple_pvz_even_from_direct_call(self):
        items = validate_request({'articles': ['123']}) + validate_request({'articles': ['456'], 'pvz_url': ALT})
        with self.assertRaises(ValueError):
            scan_items(items)


class TestExcel(unittest.TestCase):
    def test_optional_excel_in_memory(self):
        output = to_xlsx([PriceResult(index=0, article='000123', pvz_url=MOSCOW, price=350,
                                      status='ok_unverified_price_type')])
        self.assertTrue(output.startswith(b'PK'))
        with zipfile.ZipFile(io.BytesIO(output)) as workbook:
            xml = workbook.read('xl/worksheets/sheet1.xml')
            root = ET.fromstring(xml)
            ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            self.assertEqual(root.find('.//x:c[@r="A2"]/x:is/x:t', ns).text, '000123')
            self.assertEqual(root.find('.//x:c[@r="B2"]/x:v', ns).text, '350')


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), APIHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.old_token = os.environ.get('OZON_API_TOKEN')
        os.environ['OZON_API_TOKEN'] = 'test-api-token'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()
        if cls.old_token is None:
            os.environ.pop('OZON_API_TOKEN', None)
        else:
            os.environ['OZON_API_TOKEN'] = cls.old_token

    def post(self, path, body, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(self.base + path, method='POST',
                                         data=json.dumps(body).encode(), headers=headers)
        return urllib.request.urlopen(request, timeout=5)

    def test_health(self):
        with urllib.request.urlopen(self.base + '/health') as response:
            self.assertEqual(json.load(response)['status'], 'ready')

    def test_unauthorized(self):
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.post('/v1/prices', {'articles': ['123']})
        self.assertEqual(exc.exception.code, 401)

    @patch('scraper.scan_items')
    def test_prices_api_and_no_persistence(self, scan):
        scan.return_value = [PriceResult(index=0, article='123', pvz_url=MOSCOW,
                                         price=500, status='ok_unverified_price_type')]
        with self.post('/v1/prices', {'pvz_url': MOSCOW, 'articles': ['123']}, 'test-api-token') as response:
            result = json.load(response)
        self.assertEqual(result['results'][0]['price'], 500)
        self.assertEqual(result['pvz_url'], MOSCOW)
        self.assertNotIn('pvz_url', result['results'][0])
        self.assertEqual(result['summary']['verified_ozon_card_prices'], 0)
        scan.assert_called_once()
        self.assertEqual({x.pvz_url for x in scan.call_args.args[0]}, {MOSCOW})

    def test_invalid_body(self):
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.post('/v1/prices', {'items': [{'article': 'abc'}]}, 'test-api-token')
        self.assertEqual(exc.exception.code, 400)

    @patch('scraper.scan_items')
    def test_multiple_articles_same_pvz(self, scan):
        scan.return_value = [PriceResult(index=index, article=article, pvz_url=ALT, price=100 + index,
                                         status='ok_unverified_price_type')
                             for index, article in enumerate(['123', '456'])]
        with self.post('/v1/prices', {'pvz_url': ALT, 'articles': ['123', '456']}, 'test-api-token') as response:
            result = json.load(response)
        self.assertEqual(len(result['results']), 2)
        self.assertEqual(result['pvz_url'], ALT)
        self.assertEqual({x.pvz_url for x in scan.call_args.args[0]}, {ALT})


if __name__ == '__main__':
    unittest.main()