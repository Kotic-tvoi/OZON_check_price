import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from config import DEFAULT_STORE, DEFAULT_PVZ
from google_sheets import parse_links, merge, prepare_rows

class TestGoogleIntegration(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(parse_links([]), (DEFAULT_STORE, DEFAULT_PVZ))

    def test_custom_store(self):
        self.assertEqual(parse_links([["https://www.ozon.ru/seller/example/"], []])[0],
                         "https://www.ozon.ru/seller/example/")

    def test_invalid_url(self):
        with self.assertRaises(ValueError):
            parse_links([["https://other.example.org/"]])

    def test_merge_complete(self):
        self.assertEqual(merge([["123456789", 999]], [{"article": "987654321", "price": 500}], True, False),
                         [["987654321", 500]])

    def test_merge_incomplete_same_source(self):
        self.assertEqual(merge([["123456789", 999]], [{"article": "987654321", "price": 500}], False, True),
                         [["123456789", 999], ["987654321", 500]])

    def test_merge_incomplete_different_source(self):
        with self.assertRaises(ValueError):
            merge([["123456789", 999]], [{"article": "987654321", "price": 500}], False, False)

    def test_does_not_touch_input_links(self):
        catalog = SimpleNamespace(items=[{"article": "123456789", "price": 50}],
            complete=True, pvz_url=DEFAULT_PVZ, store_url=DEFAULT_STORE, pvz_address="Москва")
        updates, _ = prepare_rows([], [], catalog)
        self.assertFalse(any(area.startswith("H") for area, _ in updates))

if __name__ == "__main__":
    unittest.main()
