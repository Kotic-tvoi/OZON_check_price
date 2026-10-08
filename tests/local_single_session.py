#!/usr/bin/env python3
"""One Chrome, one PVZ, up to 100 SKUs; no packages, DB or saved price files."""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from core import DEFAULT_PVZ, MAX_ITEMS, PriceItem, normalize_article, normalize_pvz_url
from scraper import scan_items


def main():
    parser = argparse.ArgumentParser(description="Ozon: one browser for all requested SKUs")
    parser.add_argument("--limit", type=int, default=MAX_ITEMS,
                        help=f"Number of SKUs to check (default {MAX_ITEMS}, max {MAX_ITEMS})")
    parser.add_argument("--offset", type=int, default=0,
                        help="Skip this many lines in SKU file (default 0)")
    parser.add_argument("--sku-file", type=Path, default=ROOT / "SKU_Ozon.txt")
    parser.add_argument("--pvz", default=DEFAULT_PVZ)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.limit <= MAX_ITEMS:
        parser.error(f"--limit must be 1..{MAX_ITEMS}")
    if args.offset < 0:
        parser.error("--offset must be non-negative")
    url = normalize_pvz_url(args.pvz)
    raw = [line.strip() for line in args.sku_file.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    articles = [normalize_article(line) for line in raw[args.offset:args.offset + args.limit]]
    if not articles:
        parser.error("No SKUs in selected range")

    items = [PriceItem(index=i, article=sku, pvz_url=url) for i, sku in enumerate(articles)]
    print(f"One browser request: {len(items)} SKUs; PVZ: {url}", flush=True)
    print("In case of a confirmed block, the entire request may be retried in a fresh Chrome.", flush=True)
    started = time.perf_counter()
    results = scan_items(items, headed=args.headed)
    elapsed = time.perf_counter() - started

    counts = Counter()
    for result in results:
        counts[result.status] += 1
        value = result.price if result.price is not None else "Нет данных"
        note = f" | {result.message}" if result.message else ""
        print(f"{result.article}: {value} | {result.status}{note}", flush=True)

    print(f"\nSummary: {dict(counts)}", flush=True)
    print(f"Total seconds: {elapsed:.2f}; SKUs: {len(items)}; avg: {elapsed / len(items):.2f}s/SKU", flush=True)
    if any(r.status in {"blocked", "pvz_error", "pvz_unverified", "skipped_blocked"} for r in results):
        print("The request could not be completed. No results were persisted by this script.", flush=True)


if __name__ == "__main__":
    main()