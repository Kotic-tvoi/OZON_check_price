"""On-demand, read-only Selenium scraping. Browser lives only during each request."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from core import PriceItem, PriceResult, utc_now

LOG = logging.getLogger("ozon.scraper")
HOME = "https://www.ozon.ru/"
PAGE_TIMEOUT = int(os.getenv("OZON_PAGE_TIMEOUT", "30"))
PRICE_WAIT = float(os.getenv("OZON_PRICE_WAIT", "4"))
# Five total attempts per package. Fresh Chrome each time; no fixed sleep.
MAX_BATCH_ATTEMPTS = 5
RETRYABLE_BATCH_STATUSES = frozenset(
    ("blocked", "skipped_blocked", "pvz_error", "pvz_unverified")
)
PRICE_XPATHS = (
    ("webPrice", "//*[contains(@data-widget,'webPrice')]//span[contains(.,'₽')]"),
    ("legacy", "//span[contains(@class,'tsHeadline600Large') and contains(.,'₽')]"),
)
BLOCK_PHRASES = (
    "проверка безопасности", "доступ ограничен", "подтвердите, что вы не робот",
    "captcha", "antibot captcha", "сопоставьте пазл", "двигая ползунок",
    "похоже, нет соединения",
)
UNAVAILABLE_PHRASES = ("не доставляется в ваш регион", "товара нет в наличии", "товар закончился")
IGNORE_ADDRESS_TOKENS = {
    "россия", "москва", "санкт", "петербург", "город", "область", "улица", "ул", "пункт",
    "пункте", "озон", "ozon", "пвз", "проспект", "шоссе", "пр", "д", "дом", "корпус",
}


class PickupPointError(RuntimeError):
    pass


class BlockedError(PickupPointError):
    """Ozon showed a human verification or access restriction; do not retry automatically."""
    pass


@dataclass(frozen=True)
class PriceCandidate:
    price: int
    source: str
    near_text: str


def create_driver(*, headed: bool = False):
    # Selenium Manager finds/downloads ChromeDriver automatically when needed.
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    # Configuration that was successful in the user's local Selenium test.
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-proxy-server")
    if not headed:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    opts.page_load_strategy = "eager"
    binary = os.getenv("OZON_CHROME_BINARY", "").strip()
    if binary:
        opts.binary_location = binary
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(PAGE_TIMEOUT)
    return driver


def _text_tokens(text: str) -> list[str]:
    return re.findall(r"[а-яёa-z0-9]+", text.casefold())


def _identity_parts(address: str) -> tuple[list[str], str]:
    """Conservatively identify street word and house number from geo-page address."""
    text = address.casefold()
    # Example: Россия, Москва, Палехская улица, 21
    houses = re.findall(r"\b\d+(?:[а-я])?(?:к\d+)?\b", text)
    words = [word for word in _text_tokens(text) if len(word) >= 5 and word not in IGNORE_ADDRESS_TOKENS]
    if not houses or not words:
        raise PickupPointError(f"Не удалось выделить улицу и дом из адреса: {address!r}")
    return words, houses[-1]


def address_matches(address: str, visible_ui: str) -> bool:
    """Require street and house within one short visible location UI segment."""
    try:
        words, house = _identity_parts(address)
    except PickupPointError:
        return False
    for segment in re.split(r"[\n|]", visible_ui.casefold()):
        normalized = " ".join(_text_tokens(segment))
        for word in words:
            pos = normalized.find(word)
            if pos >= 0 and re.search(rf"\b{re.escape(house)}\b", normalized[pos:pos+110]):
                return True
    return False


def geo_page_address(driver) -> str | None:
    """Try to read the destination address from the official geo landing page."""
    title = (driver.title or "").strip()
    # Ozon page titles: 'Пункт Ozon: Россия, Москва, Палехская улица, 21 - ...'
    match = re.search(r"пункт\s+ozon\s*:\s*(.+?)(?:\s+-\s+|\s+—\s+|$)", title, re.I)
    if match:
        address = match.group(1).strip()
        try:
            _identity_parts(address)
            return address
        except PickupPointError:
            pass
    return None


def visible_location_text(driver) -> str:
    """Read only visible header/navigation address controls; not the geo page body."""
    return driver.execute_script("""
        const nodes = document.querySelectorAll(
          'header, [data-widget*="Header"], [data-widget*="header"],'
          + '[data-widget*="Address"], [data-widget*="address"],'
          + '[data-widget*="Location"], [data-widget*="location"]');
        const result = [];
        for (const el of nodes) {
          const rect = el.getBoundingClientRect();
          if (!rect.width || !rect.height) continue;
          const txt = (el.innerText || '').trim();
          if (txt && txt.length < 3000) result.push(txt);
        }
        for (const el of document.querySelectorAll('button,a')) {
          const rect = el.getBoundingClientRect();
          if (!rect.width || !rect.height || rect.top > 250 || rect.bottom < 0) continue;
          const txt = (el.innerText || '').trim();
          if (txt && txt.length < 180) result.push(txt);
        }
        return result.join(' | ').slice(0,15000);
    """) or ""


def check_visible_pvz(driver, expected_address: str, *, timeout: int = 8):
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import TimeoutException
    # Ozon may initially report an anti-bot title for an otherwise loading page.
    # Wait for real header content, rather than rejecting the first title.
    if "/geo/" in driver.current_url:
        raise PickupPointError("Не удалось выйти со страницы ПВЗ")

    def address_ready(d):
        return address_matches(expected_address, visible_location_text(d))

    try:
        WebDriverWait(driver, timeout, poll_frequency=0.2).until(address_ready)
    except TimeoutException as exc:
        if is_blocked(driver):
            raise BlockedError("Ozon продолжает показывать CAPTCHA/ограничение доступа") from exc
        txt = visible_location_text(driver)[:230].replace("\n", " ")
        raise PickupPointError(f"ПВЗ не подтверждён в шапке Ozon: {txt!r}") from exc


def set_pvz(driver, pvz_url: str, explicit_address: str | None = None) -> str:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import TimeoutException
    driver.get(pvz_url)
    # A transient Antibot Challenge Page must not stop the run on its first frame.
    if explicit_address:
        expected = explicit_address
    else:
        try:
            def geo_ready(d):
                return geo_page_address(d)
            expected = WebDriverWait(driver, 8, poll_frequency=0.2).until(geo_ready)
        except TimeoutException as exc:
            if is_blocked(driver):
                raise BlockedError("Ozon продолжает показывать CAPTCHA на странице ПВЗ") from exc
            expected = None
    if not expected:
        raise PickupPointError("Ozon не сообщил адрес ПВЗ на geo-странице; передайте pvz_address")
    xpath = ("//*[self::button or self::a or @role='button']"
             "[contains(normalize-space(.),'Сохранить адрес') and contains(normalize-space(.),'покупкам')]")
    try:
        def find_button(d):
            return next((x for x in d.find_elements(By.XPATH, xpath) if x.is_displayed() and x.is_enabled()), False)
        button = WebDriverWait(driver, 12, poll_frequency=0.2).until(find_button)
    except TimeoutException as exc:
        if is_blocked(driver):
            raise BlockedError("Ozon продолжает показывать CAPTCHA на странице ПВЗ") from exc
        raise PickupPointError("Не найдена кнопка «Сохранить адрес и перейти к покупкам»") from exc
    # Ozon can save the PVZ in a single-page transition without changing /geo/.
    # Stop waiting as soon as the button disappears or the URL changes.
    def after_click(d):
        if "/geo/" not in d.current_url:
            return "navigated"
        visible = [el for el in d.find_elements(By.XPATH, xpath)
                   if el.is_displayed() and el.is_enabled()]
        if not visible:
            return "submitted"
        return False

    for attempt in range(2):
        button.click()
        try:
            state = WebDriverWait(driver, 1.5, poll_frequency=0.15).until(after_click)
            break
        except TimeoutException as exc:
            if is_blocked(driver):
                raise BlockedError("Ozon продолжает показывать CAPTCHA при выборе ПВЗ") from exc
            if attempt == 1:
                raise PickupPointError("Кнопка выбора ПВЗ не реагирует на нажатие") from exc
            try:
                button = WebDriverWait(driver, 0.7, poll_frequency=0.15).until(find_button)
            except TimeoutException as btn_exc:
                raise PickupPointError("Не удалось подтвердить применение ПВЗ после нажатия") from btn_exc

    # If the button vanished but Ozon stayed on /geo/, visit the storefront.
    # This is NOT proof of success: verify the selected address in the header.
    if state == "submitted" and "/geo/" in driver.current_url:
        driver.get(HOME)
    check_visible_pvz(driver, expected, timeout=4)
    return expected


def price_as_int(text: str) -> int | None:
    if not text:
        return None
    cleaned = text.replace("\u2009", " ").replace("\xa0", " ").replace("\u202f", " ")
    match = re.fullmatch(r"\s*([0-9][0-9 ]*)\s*₽?\s*", cleaned)
    return int(match.group(1).replace(" ", "")) if match else None


def collect_candidates(driver) -> list[PriceCandidate]:
    """Read visible prices only. We don't assume the first price is Ozon Card price."""
    from selenium.webdriver.common.by import By
    out: list[PriceCandidate] = []
    keys: set[tuple[str, int]] = set()
    for source, xpath in PRICE_XPATHS:
        for el in driver.find_elements(By.XPATH, xpath):
            if not el.is_displayed():
                continue
            value = price_as_int(el.text.strip())
            if value is None or (source, value) in keys:
                continue
            keys.add((source, value))
            try:
                # Smaller ancestor text is more dependable than a whole price widget.
                nearby = el.find_element(By.XPATH, "./..").text.strip()[:160]
            except Exception:
                nearby = ""
            out.append(PriceCandidate(value, source, nearby))
    return out[:20]


def visible_body_excerpt(driver, limit: int = 2500) -> str:
    """Sample visible page content without asking Selenium for every DOM element."""
    try:
        return (driver.execute_script(
            "return (document.body && document.body.innerText || '').slice(0, arguments[0]);",
            limit
        ) or "")
    except Exception:
        return ""


def is_blocked(driver) -> bool:
    """Fast captcha/block detection even when body text is not rendered yet."""
    try:
        if any(term in (driver.title or "").casefold() for term in ("antibot", "captcha")):
            return True
        return any(phrase in visible_body_excerpt(driver).casefold() for phrase in BLOCK_PHRASES)
    except Exception:
        return False


def product_redirected(driver, article: str) -> bool:
    """Do not mistake prices in Ozon search/recommendations for the requested item."""
    current = urlparse(driver.current_url)
    path = current.path.rstrip("/")
    if path.startswith("/search"):
        return True
    # Accept product id URLs, possibly canonical URLs of the form /product/name-12345.
    if path == f"/product/{article}":
        return False
    if path.startswith("/product/") and re.search(rf"(?:^|[-/]){re.escape(article)}$", path):
        return False
    return True


def read_article(driver, item: PriceItem, expected_address: str) -> PriceResult:
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import TimeoutException
    result = PriceResult(index=item.index, article=item.article, pvz_url=item.pvz_url,
                         pvz_address=expected_address, checked_at=utc_now())
    url = f"https://www.ozon.ru/product/{item.article}/"
    try:
        driver.get(url)
        # A brief anti-bot interstitial can appear before the product page renders.
        # Check real page content and the selected pickup point before deciding.
        if product_redirected(driver, item.article):
            result.status = "unavailable"
            result.message = "Ozon перенаправил с карточки товара; цена похожих предложений не учитывается"
            return result
        body = visible_body_excerpt(driver).casefold()
        if any(phrase in body for phrase in UNAVAILABLE_PHRASES):
            result.status = "unavailable"
            result.message = "Товар недоступен для выбранного ПВЗ"
            return result
        # Check selected pickup point before accepting any value.
        check_visible_pvz(driver, expected_address, timeout=6)

        def price_or_terminal(d):
            if product_redirected(d, item.article):
                return "unavailable"
            page = visible_body_excerpt(d).casefold()
            if any(phrase in page for phrase in UNAVAILABLE_PHRASES):
                return "unavailable"
            candidates = collect_candidates(d)
            return candidates if candidates else False

        try:
            state = WebDriverWait(driver, PRICE_WAIT, poll_frequency=0.2).until(price_or_terminal)
        except TimeoutException:
            # Classify persistent access restrictions only after waiting for the price.
            if is_blocked(driver):
                raise BlockedError("Ozon продолжает показывать CAPTCHA на карточке товара")
            state = None
        if state == "unavailable":
            result.status = "unavailable"
            result.message = "Товар недоступен либо карточка перенаправила на поиск"
        elif state:
            chosen = next((c for c in state if c.source == "webPrice"), state[0])
            result.price = chosen.price
            result.status = "ok"
            result.source = chosen.source
            result.checked_at = utc_now()
        else:
            result.status = "no_price"
            result.message = f"Цена не появилась за {PRICE_WAIT:g} сек"
        return result
    except BlockedError as exc:
        result.status = "blocked"
        result.message = str(exc)
    except PickupPointError as exc:
        result.status = "pvz_unverified"
        result.message = str(exc)
    except TimeoutException:
        result.status = "timeout"
        result.message = "Не удалось загрузить карточку за отведённое время"
    except Exception as exc:
        result.status = "error"
        result.message = f"{type(exc).__name__}: {str(exc)[:160]}"
        LOG.warning("SKU %s: %s", item.article, result.message)
    # No automatic rapid retries: blocked sessions are not usable, and repeated
    # requests could aggravate anti-bot restrictions. Retry transient errors later.
    return result


def scan_pvz_group(pvz_url: str, items: list[PriceItem], headed: bool = False) -> list[PriceResult]:
    """Up to five full-package attempts, always starting from the first SKU.

    Completed earlier packages are unaffected. Failed-attempt prices are discarded.
    CAPTCHA and PVZ-selection failures are retried in a fresh Chrome session,
    without a mandatory pause. Persistent failures stop after the fifth attempt.
    """
    for attempt in range(1, MAX_BATCH_ATTEMPTS + 1):
        LOG.info("ПВЗ %s: попытка пакета %d/%d (%d SKU)",
                 pvz_url, attempt, MAX_BATCH_ATTEMPTS, len(items))
        results = _scan_pvz_group_once(pvz_url, items, headed=headed)
        failures = [row for row in results if row.status in RETRYABLE_BATCH_STATUSES]
        if not failures:
            return results
        if attempt < MAX_BATCH_ATTEMPTS:
            LOG.warning("Попытка пакета %d/%d завершилась с %s. "
                        "Закрываем Chrome и повторяем все %d SKU.",
                        attempt, MAX_BATCH_ATTEMPTS, failures[0].status, len(items))
            continue

        last_error = failures[0]
        LOG.error("Пакет не завершён после %d попыток; последний статус %s",
                  MAX_BATCH_ATTEMPTS, last_error.status)
        return [PriceResult(index=item.index, article=item.article, pvz_url=item.pvz_url,
                            checked_at=utc_now(), status=last_error.status,
                            message=f"Пакет не завершён после {MAX_BATCH_ATTEMPTS} попыток: "
                                    f"{(last_error.message or last_error.status)[:190]}")
                for item in items]
    raise AssertionError("Недостижимо")


def _scan_pvz_group_once(pvz_url: str, items: list[PriceItem], headed: bool = False) -> list[PriceResult]:
    """One attempt: one Chrome and one PVZ for every SKU in the package."""
    driver = None
    try:
        driver = create_driver(headed=headed)
        expected_values = {item.pvz_address for item in items if item.pvz_address}
        if len(expected_values) > 1:
            raise PickupPointError("Для одного ПВЗ заданы разные ожидаемые адреса")
        expected = set_pvz(driver, pvz_url, next(iter(expected_values), None))
        results: list[PriceResult] = []
        for position, item in enumerate(items):
            value = read_article(driver, item, expected)
            results.append(value)
            if value.status in ("blocked", "pvz_unverified"):
                for remaining in items[position + 1:]:
                    results.append(PriceResult(index=remaining.index, article=remaining.article,
                        pvz_url=remaining.pvz_url, pvz_address=expected, checked_at=utc_now(),
                        status="skipped_blocked", message="Сбор приостановлен после проверки доступа"))
                break
        return results
    except Exception as exc:
        LOG.warning("ПВЗ %s: %s", pvz_url, exc)
        status = "blocked" if isinstance(exc, BlockedError) else "pvz_error"
        return [PriceResult(index=item.index, article=item.article, pvz_url=item.pvz_url,
                            pvz_address=item.pvz_address, checked_at=utc_now(),
                            status=status, message=f"{type(exc).__name__}: {str(exc)[:230]}")
                for item in items]
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                LOG.warning("Не удалось закрыть Chrome", exc_info=True)


def scan_items(items: list[PriceItem], headed: bool = False) -> list[PriceResult]:
    """One request = one pickup point, one browser, any number of SKUs."""
    if not items:
        return []
    pvz_url = items[0].pvz_url
    if any(item.pvz_url != pvz_url for item in items):
        raise ValueError("В одном запросе разрешён только один ПВЗ")
    return sorted(scan_pvz_group(pvz_url, items, headed), key=lambda result: result.index)


def diagnose_price(item: PriceItem, headed: bool = False) -> dict:
    """Manual price audit; no screenshots or history are stored automatically."""
    driver = None
    try:
        driver = create_driver(headed=headed)
        expected = set_pvz(driver, item.pvz_url, item.pvz_address)
        driver.get(f"https://www.ozon.ru/product/{item.article}/")
        check_visible_pvz(driver, expected, timeout=6)
        from selenium.webdriver.support.ui import WebDriverWait
        WebDriverWait(driver, 12).until(lambda d: bool(collect_candidates(d)) or is_blocked(d))
        candidates = [c.__dict__ for c in collect_candidates(driver)]
        return {"article": item.article, "pvz_url": item.pvz_url, "pvz_address": expected,
                "candidates": candidates, "blocked": is_blocked(driver),
                "warning": "Только диагностические кандидаты; требуется сверка с ценой на витрине Ozon"}
    finally:
        if driver is not None:
            driver.quit()