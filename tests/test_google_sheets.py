import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from config import DEFAULT_STORE, DEFAULT_PVZ
from google_sheets import upload_catalog
from gui import resolved_urls


class TestIntegration(unittest.TestCase):
    def test_default_urls(self):
        self.assertEqual(resolved_urls("", ""), (DEFAULT_STORE, DEFAULT_PVZ))

    def test_custom_urls(self):
        self.assertEqual(resolved_urls("https://www.ozon.ru/seller/example/",
                                       "https://www.ozon.ru/geo/moskva/12345/"),
                         ("https://www.ozon.ru/seller/example/",
                          "https://www.ozon.ru/geo/moskva/12345/"))

    def test_invalid_url(self):
        with self.assertRaises(ValueError):
            resolved_urls("https://example.com/", "")

    def test_sheet_only_columns_a_b(self):
        catalog = SimpleNamespace(items=[{"article": "123456789", "price": 50}],
                                  complete=False, store_url=DEFAULT_STORE,
                                  pvz_url=DEFAULT_PVZ, pvz_address="Москва")
        with patch("google_sheets.session_for") as session, \
             patch("google_sheets.check_target"), \
             patch("google_sheets.read_range", return_value=[["old"], ["old"]]), \
             patch("google_sheets.write_ranges") as write:
            response = upload_catalog({"sheet_id": "dummy"}, catalog)
        self.assertEqual(response["rows"], 1)
        rows = write.call_args.args[2]
        self.assertEqual([area for area, _ in rows], ["A1:B3"])
        self.assertEqual(rows[0][1], [
            ["Артикул товара", "Конечная цена"], ["123456789", 50], ["", ""]])

    def test_no_products_refuses_to_erase(self):
        catalog = SimpleNamespace(items=[], complete=False)
        with self.assertRaises(ValueError):
            upload_catalog({"sheet_id": "dummy"}, catalog)


if __name__ == "__main__":
    unittest.main()
