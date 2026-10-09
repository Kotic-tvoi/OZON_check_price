"""Local CLI for comparing another store and another PVZ before server deployment."""
import argparse
import json
import logging
from pathlib import Path

from config import (DEFAULT_STORE, DEFAULT_PVZ, LOAD_TIMEOUT, IDLE_LIMIT,
                    MAX_SCROLLS, CAPTCHA_MAX_ATTEMPTS)
from scraper import collect


def main():
    parser = argparse.ArgumentParser(description='Ozon: цены каталога магазина')
    parser.add_argument('--store', default=DEFAULT_STORE, help='https://www.ozon.ru/seller/название/')
    parser.add_argument('--pvz', default=DEFAULT_PVZ, help='https://www.ozon.ru/geo/город/id/')
    parser.add_argument('--headed', action='store_true', help='Показать Chrome')
    parser.add_argument('--json', type=Path, help='Дополнительно сохранить JSON-файл')
    parser.add_argument('--xlsx', type=Path, help='Дополнительно сохранить Excel (два столбца)')
    parser.add_argument('--load-timeout', type=float, default=LOAD_TIMEOUT)
    parser.add_argument('--idle-limit', type=int, default=IDLE_LIMIT)
    parser.add_argument('--max-scrolls', type=int, default=MAX_SCROLLS)
    parser.add_argument('--max-attempts', type=int, default=CAPTCHA_MAX_ATTEMPTS,
                        help='Всего попыток при CAPTCHA, включая первую')
    args = parser.parse_args()
    if args.xlsx and args.xlsx.suffix.lower() != '.xlsx':
        parser.error('Файл Excel должен иметь расширение .xlsx')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    catalog = collect(args.store, args.pvz, headed=args.headed,
                      load_timeout=args.load_timeout,
                      idle_limit=args.idle_limit, max_scrolls=args.max_scrolls,
                      max_attempts=args.max_attempts)
    print('Артикул товара | Конечная цена')
    for item in catalog.items:
        print(f"{item['article']} | {item['price'] if item['price'] is not None else 'Нет данных'}")
    print(f'Найдено: {len(catalog.items)}; время: {catalog.elapsed_seconds} с; '
          f'конец каталога подтверждён: {catalog.complete}')
    if args.json:
        args.json.write_text(json.dumps(catalog.as_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'JSON: {args.json}')
    if args.xlsx:
        from xlsx_export import to_xlsx
        args.xlsx.write_bytes(to_xlsx(catalog.items))
        print(f'Excel: {args.xlsx} ({len(catalog.items)} товаров)')
    if not catalog.complete:
        print('ВНИМАНИЕ: полнота каталога не подтверждена. '
              'Excel содержит только найденные товары; отсутствующие артикулы нельзя считать недоступными.')


if __name__ == '__main__':
    main()