"""One-click Windows runner: Ozon catalog -> Google Sheet, or optional Excel."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from scraper import AccessError, CatalogError, collect

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent


def export_excel(catalog) -> Path:
    from xlsx_export import to_xlsx
    directory = ROOT / 'exports'
    directory.mkdir(parents=True, exist_ok=True)
    suffix = '' if catalog.complete else '_НЕПОЛНЫЙ'
    filename = 'ozon_' + datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + suffix + '.xlsx'
    path = directory / filename
    path.write_bytes(to_xlsx(catalog.items))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description='Сбор конечных цен Ozon')
    parser.add_argument('--excel-only', action='store_true',
                        help='Вместо Google Таблицы сохранить отдельный Excel')
    parser.add_argument('--check-build', action='store_true', help='Проверка EXE без браузера')
    args = parser.parse_args()
    if args.check_build:
        import selenium
        import google.auth
        print('OK: зависимости EXE загружены')
        return 0
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if args.excel_only:
        from config import DEFAULT_STORE, DEFAULT_PVZ
        store, pvz = DEFAULT_STORE, DEFAULT_PVZ

    try:
        if not args.excel_only:
            from google_sheets import load_connection, read_run_options
            connection = load_connection()
            store, pvz = read_run_options(connection)

        print('\nЗапускаем обычный Chrome. Не закрывайте окно до завершения сбора.\n', flush=True)
        catalog = collect(store, pvz, headed=True)
        with_price = sum(item['price'] is not None for item in catalog.items)
        print(f'\nНайдено артикулов: {len(catalog.items)}, с ценой: {with_price}.')
        print(f'Время: {catalog.elapsed_seconds} с. ПВЗ: {catalog.pvz_address}.')
        if not catalog.complete:
            print('ВНИМАНИЕ: конец каталога не подтверждён. Результат может быть неполным.')

        if args.excel_only:
            path = export_excel(catalog)
            print(f'Excel сохранён: {path}')
        else:
            from google_sheets import upload_catalog
            result = upload_catalog(connection, catalog)
            print(f'Готово! Google Таблица: лист «{result["sheet"]}», строк: {result["rows"]}.')
            if not catalog.complete:
                print('Неполный сбор записан отдельно и НЕ заменяет лист полного каталога.')
        return 0
    except (AccessError, CatalogError, OSError, ValueError) as exc:
        print(f'\nОШИБКА: {exc}')
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nОперация отменена.')
        return 1
    except Exception:
        # Unexpected exception: show traceback for support, without printing credentials.
        logging.exception('Неожиданная ошибка')
        return 1


if __name__ == '__main__':
    status = main()
    if getattr(sys, 'frozen', False) and '--check-build' not in sys.argv:
        try:
            input('\nНажмите Enter, чтобы закрыть окно...')
        except (EOFError, KeyboardInterrupt):
            pass
    raise SystemExit(status)
