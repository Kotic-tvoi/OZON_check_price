"""Deterministic tests for dynamic page readiness, with no external browser/network."""
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import scraper
from core import PriceItem


class FakeTimeoutException(Exception):
    pass


class FakeWait:
    def __init__(self, driver, timeout, poll_frequency=0.5):
        self.driver = driver
        self.timeout = timeout

    def until(self, fn):
        for _ in range(6):
            result = fn(self.driver)
            if result:
                return result
            self.driver.tick()
        raise FakeTimeoutException('fixture timeout')


class FakeButton:
    def __init__(self, driver):
        self.driver = driver

    def is_displayed(self):
        return True

    def is_enabled(self):
        return True

    def click(self):
        self.driver.phase = 'shopping'
        self.driver.current_url = 'https://www.ozon.ru/'


class FakeDriver:
    def __init__(self, resolve_after=2):
        self.resolve_after = resolve_after
        self.ticks = 0
        self.phase = 'challenge'
        self.current_url = 'https://www.ozon.ru/geo/moskva/442329/'

    def tick(self):
        self.ticks += 1

    def get(self, url):
        self.current_url = url
        self.phase = 'challenge'
        self.ticks = 0

    @property
    def title(self):
        if self.phase == 'challenge' and self.ticks < self.resolve_after:
            return 'Antibot Challenge Page'
        return 'Пункт Ozon: Россия, Москва, Палехская улица, 21 - время работы'

    def find_elements(self, by, xpath):
        if self.ticks < self.resolve_after:
            return []
        return [FakeButton(self)]

    def execute_script(self, source, *args):
        if self.phase == 'shopping':
            return 'Пункт Ozon: Палехская ул., 21 | Корзина'
        return ''


def selenium_shim():
    ui = types.ModuleType('selenium.webdriver.support.ui')
    ui.WebDriverWait = FakeWait
    common = types.ModuleType('selenium.common.exceptions')
    common.TimeoutException = FakeTimeoutException
    by = types.ModuleType('selenium.webdriver.common.by')
    by.By = types.SimpleNamespace(XPATH='xpath')
    # Imports are local inside scraper's functions, so the mock modules are enough.
    return patch.dict(sys.modules, {
        'selenium': types.ModuleType('selenium'),
        'selenium.webdriver': types.ModuleType('selenium.webdriver'),
        'selenium.webdriver.support': types.ModuleType('selenium.webdriver.support'),
        'selenium.webdriver.support.ui': ui,
        'selenium.common': types.ModuleType('selenium.common'),
        'selenium.common.exceptions': common,
        'selenium.webdriver.common': types.ModuleType('selenium.webdriver.common'),
        'selenium.webdriver.common.by': by,
    })


class TestTransientChallenge(unittest.TestCase):
    def test_transient_title_resolves_without_fixed_sleep(self):
        driver = FakeDriver(resolve_after=2)
        with selenium_shim():
            start = time.monotonic()
            address = scraper.set_pvz(driver, 'https://www.ozon.ru/geo/moskva/442329/')
            elapsed = time.monotonic() - start
        self.assertEqual(address, 'Россия, Москва, Палехская улица, 21')
        self.assertEqual(driver.ticks, 2)
        self.assertLess(elapsed, 0.5)

    def test_persistent_challenge_is_blocked_after_timeout(self):
        driver = FakeDriver(resolve_after=100)
        with selenium_shim(), self.assertRaises(scraper.BlockedError):
            scraper.set_pvz(driver, 'https://www.ozon.ru/geo/moskva/442329/')
        self.assertEqual(driver.ticks, 6)

    def test_immediately_ready_page_does_not_wait(self):
        driver = FakeDriver(resolve_after=0)
        with selenium_shim():
            address = scraper.set_pvz(driver, 'https://www.ozon.ru/geo/moskva/442329/')
        self.assertEqual(address, 'Россия, Москва, Палехская улица, 21')
        self.assertEqual(driver.ticks, 0)


if __name__ == '__main__':
    unittest.main()