#!/usr/bin/env python3
"""Manual local benchmark of multi-batch Selenium, no database or persisted prices."""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'app'))

from core import DEFAULT_PVZ, PriceItem, normalize_article, normalize_pvz_url
from scraper import scan_items


def main():
    parser = argparse.ArgumentParser(description='Ozon: local batch benchmark, read-only')
    parser.add_argument('--batch', type=int, default=16, help='Number of SKU per Chrome session (default: 16)')
    parser.add_argument('--limit', type=int, default=0, help='Test first N SKUs; 0 = all')
    parser.add_argument('--sku-file', type=Path, default=PROJECT / 'SKU_Ozon.txt')
    parser.add_argument('--pvz', default=DEFAULT_PVZ)
    parser.add_argument('--headed', action='store_true', help='Show browser windows')
    args = parser.parse_args()
    if not 1 <= args.batch <= 100:
        parser.error('--batch must be in 1..100')
    url = normalize_pvz_url(args.pvz)
    articles = [normalize_article(x.strip()) for x in
                args.sku_file.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    if args.limit > 0:
        articles = articles[:args.limit]
    if not articles:
        parser.error('No articles in SKU file')
    counters = Counter()
    started = time.perf_counter()
    print(f'Total SKU: {len(articles)}; batch size: {args.batch}; PVZ: {url}', flush=True)
    for offset in range(0, len(articles), args.batch):
        pack = articles[offset:offset + args.batch]
        items = [PriceItem(index=offset + i, article=sku, pvz_url=url) for i, sku in enumerate(pack)]
        begun = time.perf_counter()
        print(f'\nPACKAGE {offset // args.batch + 1}; SKU {offset + 1}-{offset + len(pack)}', flush=True)
        results = scan_items(items, headed=args.headed)
        for row in results:
            counters[row.status] += 1
            print(f'{row.article}: {row.price if row.price is not None else "null"} | {row.status}'
                  + (f' | {row.message}' if row.message else ''), flush=True)
        print(f'Package seconds: {time.perf_counter() - begun:.2f}', flush=True)
        if any(r.status in {'blocked', 'skipped_blocked', 'pvz_unverified', 'pvz_error'} for r in results):
            print('Paused: access restriction or pickup-point verification error.', flush=True)
            break
    print('\nSummary:', dict(counters), flush=True)
    print(f'Total seconds: {time.perf_counter() - started:.2f}', flush=True)


if __name__ == '__main__':
    main()