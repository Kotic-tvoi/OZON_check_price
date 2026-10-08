import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from scraper import PickupPointError, set_pvz

PVZ = 'https://www.ozon.ru/geo/moskva/442329/'
ADDRESS = 'Россия, Москва, Палехская улица, 21'

class FakeTimeoutException(Exception):
    pass

class FakeStaleElementReferenceException(Exception):
    pass

class ImmediateWait:
    '''Synchronous stand-in for Selenium polling, no network or delays.'''
    def __init__(self, driver, timeout, poll_frequency=None):
        self.driver = driver
    def until(self, condition):
        value = condition(self.driver)
        if value:
            return value
        raise FakeTimeoutException('not ready')

def selenium_modules():
    '''These tests do not require Selenium to be installed in the test container.'''
    paths = ['selenium', 'selenium.webdriver', 'selenium.webdriver.common',
             'selenium.webdriver.common.by', 'selenium.webdriver.support',
             'selenium.webdriver.support.ui', 'selenium.common',
             'selenium.common.exceptions']
    mods = {path: types.ModuleType(path) for path in paths}
    mods['selenium.webdriver.common.by'].By = types.SimpleNamespace(XPATH='xpath')
    mods['selenium.webdriver.support.ui'].WebDriverWait = ImmediateWait
    mods['selenium.common.exceptions'].TimeoutException = FakeTimeoutException
    mods['selenium.common.exceptions'].StaleElementReferenceException = FakeStaleElementReferenceException
    return mods

class TestPvzSelection(unittest.TestCase):
    def make_driver(self, navigates):
        driver = MagicMock()
        driver.current_url = PVZ
        driver.get.side_effect = lambda url: setattr(driver, 'current_url', url)
        button = MagicMock()
        button.is_displayed.return_value = True
        button.is_enabled.return_value = True
        driver.find_elements.return_value = [button]
        if navigates:
            button.click.side_effect = lambda: setattr(driver, 'current_url', 'https://www.ozon.ru/')
        return driver, button

    def test_successful_selection_navigates_once(self):
        driver, button = self.make_driver(navigates=True)
        with patch.dict(sys.modules, selenium_modules()), patch('scraper.check_visible_pvz') as verify:
            result = set_pvz(driver, PVZ, ADDRESS)
        self.assertEqual(result, ADDRESS)
        driver.get.assert_called_once_with(PVZ)
        self.assertEqual(button.click.call_count, 1)
        verify.assert_not_called()

    def test_stale_button_after_click_is_not_fatal(self):
        driver, button = self.make_driver(navigates=False)
        # The first lookup succeeds; Ozon removes the node after the click.
        driver.find_elements.side_effect = [[button], []]
        with patch.dict(sys.modules, selenium_modules()):
            result = set_pvz(driver, PVZ, ADDRESS)
        self.assertEqual(result, ADDRESS)
        self.assertEqual(button.click.call_count, 1)

    def test_stale_reference_during_polling_is_retried(self):
        driver, button = self.make_driver(navigates=True)
        stale = MagicMock()
        stale.is_displayed.side_effect = FakeStaleElementReferenceException()
        driver.find_elements.side_effect = [[stale, button]]
        with patch.dict(sys.modules, selenium_modules()):
            result = set_pvz(driver, PVZ, ADDRESS)
        self.assertEqual(result, ADDRESS)

    def test_no_home_navigation_without_url_change(self):
        driver, button = self.make_driver(navigates=False)
        with patch.dict(sys.modules, selenium_modules()):
            with self.assertRaisesRegex(PickupPointError, 'не подтвердил'):
                set_pvz(driver, PVZ, ADDRESS)
        driver.get.assert_called_once_with(PVZ)
        self.assertEqual(button.click.call_count, 2)

if __name__ == '__main__':
    unittest.main()