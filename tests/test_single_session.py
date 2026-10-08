"""Mock test: one browser and one PVZ, even for a hundred article inputs."""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from core import validate_request, InputError, PriceResult
from scraper import scan_items

class TestSingleSession(unittest.TestCase):
    @patch('scraper.read_article')
    @patch('scraper.set_pvz',return_value='Москва, Палехская улица, 21')
    @patch('scraper.create_driver')
    def test_100_articles_one_chrome(self, driver_factory, set_pvz, reader):
        driver_factory.return_value=MagicMock()
        reader.side_effect=lambda drv,item,address:PriceResult(index=item.index,article=item.article,pvz_url=item.pvz_url,price=100+item.index,status='ok')
        items=validate_request({'articles':[str(380000000+i) for i in range(100)]})
        result=scan_items(items, headed=True)
        self.assertEqual(len(result),100)
        self.assertEqual(result[-1].price,199)
        self.assertEqual(driver_factory.call_count,1)
        self.assertEqual(set_pvz.call_count,1)
        self.assertEqual(reader.call_count,100)
        self.assertEqual(driver_factory.return_value.quit.call_count,1)
    def test_over_100_rejected(self):
        with self.assertRaises(InputError):
            validate_request({'articles':[str(i) for i in range(101)]})

if __name__=='__main__': unittest.main()