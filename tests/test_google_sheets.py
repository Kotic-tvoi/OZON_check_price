import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from config import DEFAULT_STORE, DEFAULT_PVZ
from google_sheets import merge, prepare_rows
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
    def test_full_replace(self):
        self.assertEqual(merge([["123456789", 100]],
                               [{"article":"987654321","price":200}], True, False),
                         [["987654321", 200]])
    def test_partial_merge(self):
        self.assertEqual(merge([["123456789", 100]],
                               [{"article":"987654321","price":200}], False, True),
                         [["123456789", 100], ["987654321", 200]])
    def test_partial_other_store_fails(self):
        with self.assertRaises(ValueError):
            merge([["123456789", 100]],
                  [{"article":"987654321","price":200}], False, False)
    def test_output_cells_only(self):
        catalog = SimpleNamespace(items=[{"article":"123456789","price":50}],
            complete=True, pvz_url=DEFAULT_PVZ, store_url=DEFAULT_STORE,
            pvz_address="Москва")
        changes, _ = prepare_rows([], [], catalog)
        self.assertEqual([r for r, _ in changes], ["A1:B2", "D3:E10"])

if __name__ == "__main__":
    unittest.main()
