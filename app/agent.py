"""Background checker: one Windows PC; all controls live in Google Sheets."""
import logging
import sys
import time

from config import DEFAULT_STORE, DEFAULT_PVZ
from google_sheets import SheetAgent, load_connection, parse_links, read_range, upload_catalog
from scraper import AccessError, CatalogError, collect

logging.basicConfig(level=logging.INFO, format="%(message)s")
LOG = logging.getLogger("ozon.agent")
POLL_SECONDS = 10


def run():
    connection = load_connection()
    agent = SheetAgent(connection)
    try:
        agent.prepare_interface()
        print("Агент готов. В Google Таблице установите флажок E2 для проверки.")
        print("Оставьте эту программу запущенной. Проверка ожидается каждые 10 секунд.")
        while True:
            try:
                if not agent.requested():
                    time.sleep(POLL_SECONDS)
                    continue
                # Claim the request before Selenium starts: avoid duplicate jobs.
                agent.report("В работе", "Открываем каталог Ozon", clear_request=True)
                links = read_range(agent.http, agent.sid, "H2:H3")
                store, pvz = parse_links(links)
                LOG.info("Проверяем магазин %s, ПВЗ %s", store, pvz)
                catalog = collect(store, pvz, headed=True)
                # Upload via a separate API session. Current control state remains unchanged.
                result = upload_catalog(connection, catalog)
                agent.report("Готово" if catalog.complete else "Неполный каталог",
                             f"Собрано {result['checked']} артикулов; записано {result['rows']}. "
                             + ("Конец каталога подтверждён." if catalog.complete else
                                "Остаток каталога не подтверждён, старые цены могут быть неактуальны."))
            except (AccessError, CatalogError, ValueError, OSError) as exc:
                LOG.error("Ошибка: %s", exc)
                agent.report("Ошибка", str(exc), clear_request=True)
            except Exception:
                LOG.exception("Неожиданная ошибка")
                agent.report("Ошибка", "Непредвиденная ошибка; проверьте окно агента.", clear_request=True)
            time.sleep(POLL_SECONDS)
    finally:
        agent.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        run()
    except KeyboardInterrupt:
        print("Агент остановлен.")
    except Exception as exc:
        print("Не удалось запустить агент:", exc)
        if getattr(sys, "frozen", False):
            input("Нажмите Enter...")
        raise
