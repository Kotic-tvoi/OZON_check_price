"""Настройки локального сбора цен Ozon."""

DEFAULT_STORE = "https://www.ozon.ru/seller/jkeratin/"
DEFAULT_PVZ = "https://www.ozon.ru/geo/moskva/442329/"

# Время в секундах. Значения — максимальные ожидания, не фиксированные паузы.
LOAD_TIMEOUT = 1.5
SCROLL_POLL_INTERVAL = 0.1
IDLE_LIMIT = 4
MAX_SCROLLS = 100
CAPTCHA_MAX_ATTEMPTS = 2

CHROME_WINDOW_SIZE = "1920,1080"
PAGE_LOAD_TIMEOUT = 30

PVZ_READY_TIMEOUT = 4.0
PVZ_POLL_INTERVAL = 0.15
PVZ_CLICK_TIMEOUT = 1.2
PVZ_RETRY_TIMEOUT = 0.8

STORE_READY_TIMEOUT = 5.0
STORE_POLL_INTERVAL = 0.2
