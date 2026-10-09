"""Read prices from one Ozon seller catalog; never visit individual product pages."""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass

from core import DEFAULT_PVZ, DEFAULT_STORE, pvz_url, store_url

LOG = logging.getLogger('ozon.storefront')

# The container is Ozon's seller catalog, not its recommendation section.
EXTRACT = r"""
const root = document.querySelector('#contentScrollPaginator');
if (!root) return {ready:false,items:[],boundary:false,visible:0};
const items = [];
for (const tile of root.querySelectorAll('.tile-root')) {
  const a = tile.querySelector('a[href*="/product/"]');
  if (!a) continue;
  let path;
  try { path = new URL(a.href).pathname; } catch { continue; }
  const id = path.match(/(?:-|\/)(\d{7,12})\/?$/)?.[1];
  if (!id) continue;
  // Prefer the current displayed price, not the crossed-out old price.
  const priceNode = tile.querySelector('.c35_6_0-a0 span.c35_6_0-a1') ||
    [...tile.querySelectorAll('span')].find(s =>
      /^\s*[\d\s\u2009\u202f\u00a0]+\s*₽\s*$/.test(s.textContent||'') &&
      !s.closest('s,del,[style*="line-through"]'));
  const digits = (priceNode?.textContent||'').replace(/\D/g,'');
  items.push({article:id,price:digits?Number(digits):null});
}
const header = [...document.querySelectorAll('h1,h2,h3,span')]
  .find(el => el.textContent?.trim() === 'Возможно, вам понравится');
const boundary = !!header && header.getBoundingClientRect().top <= innerHeight;
const rootBottom = root.getBoundingClientRect().bottom;
return {ready:true,items,boundary,visible:root.querySelectorAll('.tile-root').length,
        end_visible:rootBottom <= innerHeight,scroll_y:scrollY};
"""

SCROLL = r"""
const root = document.querySelector('#contentScrollPaginator');
if (!root) return;
const cards = root.querySelectorAll('.tile-root');
(cards.length ? cards[cards.length-1] : root).scrollIntoView({block:'end',behavior:'instant'});
"""


class AccessError(RuntimeError):
    pass


class CatalogError(RuntimeError):
    pass


@dataclass
class Catalog:
    store_url: str
    pvz_url: str
    pvz_address: str
    items: list[dict]
    complete: bool
    elapsed_seconds: float

    def as_dict(self) -> dict:
        return {
            'store_url': self.store_url, 'pvz_url': self.pvz_url,
            'pvz_address': self.pvz_address, 'complete': self.complete,
            'summary': {'total': len(self.items),
                        'with_price': sum(x['price'] is not None for x in self.items)},
            'items': self.items,
        }


def create_driver(headed: bool = False):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    options = Options()
    if not headed:
        options.add_argument('--headless=new')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--no-proxy-server')
    options.add_argument('--disable-extensions')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_experimental_option('prefs', {
        'profile.managed_default_content_settings.images': 2,
    })
    options.page_load_strategy = 'eager'
    if os.getenv('OZON_CHROME_BINARY'):
        options.binary_location = os.environ['OZON_CHROME_BINARY']
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver


def is_blocked(driver) -> bool:
    try:
        title = (driver.title or '').lower()
        if 'captcha' in title or 'antibot' in title:
            return True
        text = driver.execute_script(
            "return (document.body?.innerText||'').slice(0,1500).toLowerCase()") or ''
        return any(word in text for word in ('сопоставьте пазл', 'двигая ползунок',
                                             'подтвердите, что вы не робот',
                                             'похоже, нет соединения'))
    except Exception:
        return False


def _address(title: str) -> str | None:
    match = re.search(r'пункт\s+ozon\s*:\s*(.+?)(?:\s+-\s+|\s+—\s+|$)', title, re.I)
    return match.group(1).strip() if match else None


def _matches(address: str, header: str) -> bool:
    # Require identifiable street and house; city-only matches are unsafe.
    tokens = re.findall(r'[а-яёa-z0-9]+', address.casefold())
    words = [x for x in tokens if len(x) >= 5 and x not in
             {'россия','москва','петербург','санкт','улица','озон','ozon','область','пункт'}]
    numbers = re.findall(r'\b\d+[а-я]?\b', address.casefold())
    if not words or not numbers:
        return False
    normalized = ' '.join(re.findall(r'[а-яёa-z0-9]+', header.casefold()))
    return any(word in normalized and re.search(rf'\b{re.escape(numbers[-1])}\b', normalized)
               for word in words)


def _header_text(driver) -> str:
    return driver.execute_script("""
       return [...document.querySelectorAll('header,[data-widget*="Header"],'
         + '[data-widget*="Address"],[data-widget*="address"],'
         + '[data-widget*="Location"],[data-widget*="location"]')]
         .filter(e => e.getBoundingClientRect().width)
         .map(e => e.innerText).filter(Boolean).join(' | ').slice(0,12000);
    """) or ''


def set_pvz(driver, url: str) -> str:
    """Choose PVZ without opening tabs; storefront will verify actual selection."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

    driver.get(url)
    xpath = ("//*[self::button or self::a or @role='button']"
             "[contains(normalize-space(.),'Сохранить адрес') and contains(normalize-space(.),'покупкам')]")

    def ready(d):
        address = _address(d.title or '')
        if not address:
            return False
        for element in d.find_elements(By.XPATH, xpath):
            try:
                if element.is_displayed() and element.is_enabled():
                    return address, element
            except StaleElementReferenceException:
                continue
        return False

    try:
        address, button = WebDriverWait(driver, 6, poll_frequency=.15).until(ready)
    except TimeoutException as exc:
        if is_blocked(driver):
            raise AccessError('Ozon требует CAPTCHA при выборе ПВЗ') from exc
        raise CatalogError('Не удалось найти адрес и кнопку выбора ПВЗ') from exc

    def applied(d):
        if '/geo/' not in d.current_url:
            return True
        for el in d.find_elements(By.XPATH, xpath):
            try:
                if el.is_displayed() and el.is_enabled():
                    return False
            except StaleElementReferenceException:
                return False
        return True

    for _ in range(2):
        try:
            button.click()
            WebDriverWait(driver, 1.2, poll_frequency=.15).until(applied)
            return address
        except (TimeoutException, StaleElementReferenceException):
            if is_blocked(driver):
                raise AccessError('Ozon требует CAPTCHA при выборе ПВЗ')
            try:
                address, button = WebDriverWait(driver, .8, poll_frequency=.15).until(ready)
            except TimeoutException:
                if applied(driver):
                    return address
                break
    raise CatalogError('Не удалось подтвердить нажатие кнопки выбора ПВЗ')


def _wait_store(driver, address: str, timeout: float = 8):
    """Wait for the storefront header and target catalog to render."""
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import TimeoutException

    def ready(d):
        if not _matches(address, _header_text(d)):
            return False
        return bool(d.execute_script("return document.querySelector('#contentScrollPaginator')"))

    try:
        WebDriverWait(driver, timeout, poll_frequency=.2).until(ready)
    except TimeoutException as exc:
        if is_blocked(driver):
            raise AccessError('Ozon требует CAPTCHA при открытии магазина') from exc
        raise CatalogError('Не подтверждён ПВЗ или отсутствует каталог магазина') from exc


def _snapshot(driver) -> dict:
    return driver.execute_script(EXTRACT)


def collect(store: str = DEFAULT_STORE, pvz: str = DEFAULT_PVZ, *, headed: bool = False,
            load_timeout: float = 2.5, idle_limit: int = 4,
            max_scrolls: int = 100, max_attempts: int = 2) -> Catalog:
    """Read all visible/lazy-loaded catalog tiles in one Chrome, no database."""
    store, pvz = store_url(store), pvz_url(pvz)
    start = time.monotonic()
    for attempt in range(max_attempts):
        driver = None
        try:
            driver = create_driver(headed)
            address = set_pvz(driver, pvz)
            driver.get(store)
            _wait_store(driver, address)
            collected: dict[str, dict] = {}
            idle = 0
            boundary_seen = False
            last_signature = ()
            complete = False
            for step in range(max_scrolls):
                snap = _snapshot(driver)
                if not snap['ready']:
                    raise CatalogError('Контейнер каталога исчез')
                signature = tuple(row['article'] for row in snap['items'])
                before = len(collected)
                for row in snap['items']:
                    prev = collected.get(row['article'])
                    if prev is None or row['price'] is not None:
                        collected[row['article']] = row
                new = len(collected) - before
                boundary_seen |= bool(snap['boundary'] or snap['end_visible'])
                idle = 0 if new else idle + 1
                LOG.info('Каталог %s: шаг %d, товаров %d (+%d), карточек %d, конец %s',
                         store, step, len(collected), new, snap['visible'], boundary_seen)
                if boundary_seen and idle >= idle_limit:
                    complete = True
                    break
                if idle >= idle_limit and not boundary_seen:
                    break
                driver.execute_script(SCROLL)
                # Poll for a different window of cards, not a larger DOM tile count:
                # Ozon virtualizes the list and can keep only ~40 tiles in DOM.
                deadline = time.monotonic() + load_timeout
                while time.monotonic() < deadline:
                    time.sleep(.2)
                    fresh = _snapshot(driver)
                    if fresh['ready'] and tuple(x['article'] for x in fresh['items']) != signature:
                        break
                last_signature = signature
            if not collected:
                raise CatalogError('В каталоге не найдены товары с артикулами')
            return Catalog(store, pvz, address, sorted(collected.values(),key=lambda x:int(x['article'])),
                           complete, round(time.monotonic()-start, 2))
        except AccessError:
            if attempt + 1 >= max_attempts:
                raise
            LOG.warning('CAPTCHA: повторный запуск браузера (%d/%d)',attempt+2,max_attempts)
        finally:
            if driver is not None:
                driver.quit()
    raise CatalogError('Сбор не завершён')