"""Параметры парсера Ozon. Меняйте значения здесь, без правки логики."""

# Магазин и пункт выдачи по умолчанию
DEFAULT_STORE = "https://www.ozon.ru/seller/jkeratin/"
DEFAULT_PVZ = "https://www.ozon.ru/geo/moskva/442329/"

# Ограничения HTTP API
MAX_ARTICLES = 100
MAX_REQUEST_BYTES = 120_000

# Прокрутка каталога
LOAD_TIMEOUT = 2.0              # максимальное ожидание новых карточек, секунды
SCROLL_POLL_INTERVAL = 0.1      # как часто проверять появление карточек, секунды
IDLE_LIMIT = 4                 # шагов без новых SKU до остановки
MAX_SCROLLS = 100              # ограничение количества шагов прокрутки

# CAPTCHA: ОБЩЕЕ число запусков браузера, включая первую попытку
# Например, 5 = 1 первоначальный запуск + максимум 4 повтора.
CAPTCHA_MAX_ATTEMPTS = 2

# Браузер и выбор ПВЗ
CHROME_WINDOW_SIZE = "1920,1080"
PAGE_LOAD_TIMEOUT = 30
PVZ_READY_TIMEOUT = 6.0
PVZ_POLL_INTERVAL = 0.15
PVZ_CLICK_TIMEOUT = 1.2
PVZ_RETRY_TIMEOUT = 0.8
STORE_READY_TIMEOUT = 8.0
STORE_POLL_INTERVAL = 0.2
