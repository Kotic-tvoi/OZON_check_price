"""No-network smoke checks for the combined local price checker.

Run from the project root:
  py -3 -m unittest discover -s tests -v
"""
import sys
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from gui import suggest_store_name
from wb_scraper import normalize_destination, normalize_store_url, _read_products
from xlsx_export import to_xlsx


class SmokeTests(unittest.TestCase):
    def test_defaults_and_store_names(self):
        self.assertEqual(suggest_store_name("WB", "https://www.wildberries.ru/seller/215484/"), "JKeratin")
        self.assertEqual(suggest_store_name("OZON", "https://www.ozon.ru/seller/jkeratin/"), "JKeratin")
        self.assertEqual(suggest_store_name("WB", "https://www.wildberries.ru/seller/1234/"), "seller_1234")

    def test_wb_url_validation(self):
        self.assertEqual(normalize_store_url("https://www.wildberries.ru/seller/215484/"), "https://www.wildberries.ru/seller/215484/")
        for invalid in ("http://www.wildberries.ru/seller/215484/", "https://other.example/seller/1/", "https://www.wildberries.ru/seller/1/?x=2"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                normalize_store_url(invalid)

    def test_destination_validation(self):
        self.assertEqual(normalize_destination("-1257786"), "-1257786")
        with self.assertRaises(ValueError):
            normalize_destination("Москва")

    def test_wb_prices_are_kopecks(self):
        result = _read_products({"products": [
            {"id": 1234567, "name": "Тест", "sizes": [{"price": {"product": 123400, "basic": 234500}}]},
            {"id": 4567890, "name": "Тест 2", "sizes": []}
        ]})
        self.assertEqual(result[0]["price"], 1234)
        self.assertEqual(result[0]["old_price"], 2345)
        self.assertIsNone(result[1]["price"])

    def test_excel_can_be_parsed(self):
        binary = to_xlsx([{"article": "1234567", "price": 1250}], sheet_name="Цены WB")
        with ZipFile(BytesIO(binary)) as zf:
            workbook = ET.fromstring(zf.read("xl/workbook.xml"))
            sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        self.assertEqual(workbook.find(f".//{namespace}sheet").attrib["name"], "Цены WB")
        self.assertIsNotNone(sheet.find(f".//{namespace}sheetData"))


if __name__ == "__main__":
    unittest.main()
