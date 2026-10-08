#!/usr/bin/env python3
"""Experimental Ozon JKeratin storefront benchmark (catalog only)."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from core import DEFAULT_PVZ
from scraper import create_driver, set_pvz, check_visible_pvz, is_blocked

STORE_URL = 'https://www.ozon.ru/seller/jkeratin/'
CATALOG = '#contentScrollPaginator'
# Read only primary catalog tiles. Recommendation cards are never selected.
EXTRACT = r"""
const root = document.querySelector('#contentScrollPaginator');
if (!root) return {found:false, rows:[], raw_tiles:0, grid_count:0, recommendation_seen:false};
const tiles = Array.from(root.querySelectorAll('.tile-root'));
const rows = [];
for (const tile of tiles) {
    const a = tile.querySelector('a[href*="/product/"]');
    if (!a) continue;
    let pathname;
    try { pathname = new URL(a.href).pathname; } catch { continue; }
    const match = pathname.match(/-(\d{7,12})\/?$/);
    if (!match) continue;
    const priceEl = tile.querySelector('.c35_6_0-a0 span.c35_6_0-a1') ||
                    Array.from(tile.querySelectorAll('span'))
                         .find(s => /^\s*[\d\s\u2009\u202f\u00a0]+\s*₽\s*$/.test(s.textContent || ''));
    const priceText = priceEl?.textContent || '';
    const digits = priceText.replace(/[^0-9]/g, '');
    const nameEl = tile.querySelector('a[href*="/product/"] .tsBody500Medium');
    rows.push({article:match[1], price:digits ? Number(digits):null,
               name:nameEl?.textContent?.trim()||'', url:a.href});
}
const reco = Array.from(document.querySelectorAll('span,h1,h2,h3'))
     .find(e => e.textContent?.trim() === 'Возможно, вам понравится');
const recoTop = reco ? reco.getBoundingClientRect().top : null;
return {
    found:true, rows, raw_tiles:tiles.length,
    grid_count:root.querySelectorAll('[data-widget="tileGridDesktop"]').length,
    recommendation_seen:recoTop !== null && recoTop <= window.innerHeight,
    reco_top:recoTop, scroll_y:window.scrollY,
    scroll_height:document.documentElement.scrollHeight
};
"""

SCROLL_TO_CATALOG_END = r"""
const root = document.querySelector('#contentScrollPaginator');
if (!root) return false;
const tiles = root.querySelectorAll('.tile-root');
const last = tiles.length ? tiles[tiles.length - 1] : root;
last.scrollIntoView({behavior:'instant', block:'end'});
return true;
"""


def store_snapshot(driver):
    """Fetch a complete DOM snapshot once per poll rather than 1 Selenium call/tile."""
    return driver.execute_script(EXTRACT)


def wait_for_new_tiles(driver, old_tiles: int, timeout: float):
    """Adaptive loading: leave instantly if a new tile is inserted."""
    deadline = time.monotonic() + timeout
    latest = store_snapshot(driver)
    while latest['found'] and latest['raw_tiles'] <= old_tiles and time.monotonic() < deadline:
        if is_blocked(driver):
            raise RuntimeError('Ozon требует проверку доступа во время загрузки каталога')
        time.sleep(0.2)
        latest = store_snapshot(driver)
    return latest


def run(headed: bool, pvz: str, max_scrolls: int, idle_limit: int,
        expected_count: int, load_timeout: float):
    driver = create_driver(headed=headed)
    found_items = {}
    try:
        address = set_pvz(driver, pvz)
        driver.get(STORE_URL)
        check_visible_pvz(driver, address, timeout=6)
        print(f'PVZ verified: {address}', flush=True)

        last_raw = 0
        idle = 0
        reco_seen = False
        # Under an infinite scroll layout, recommendation heading can already be
        # visible while the next batch of products has not yet loaded.
        for step in range(max_scrolls):
            if is_blocked(driver):
                raise RuntimeError('Ozon показал CAPTCHA: каталог не подтверждён')
            snapshot = store_snapshot(driver)
            if not snapshot['found']:
                if step >= 15:
                    raise RuntimeError('Не найден основной контейнер каталога')
                time.sleep(0.3)
                continue
            for item in snapshot['rows']:
                previous = found_items.get(item['article'])
                if previous is None or item['price'] is not None:
                    found_items[item['article']] = item
            count = len(found_items)
            raw_tiles = snapshot['raw_tiles']
            reco_seen = reco_seen or snapshot['recommendation_seen']
            priced = sum(x['price'] is not None for x in found_items.values())
            print(f'Scroll {step}: products={count}; prices={priced}; cards={raw_tiles}; '
                  f'grids={snapshot["grid_count"]}; '
                  f'recommendation_seen={snapshot["recommendation_seen"]}', flush=True)

            if count >= expected_count > 0 and reco_seen:
                # Stable end: still give the last batch a short loading window.
                updated = wait_for_new_tiles(driver, raw_tiles, timeout=1.2)
                if updated['raw_tiles'] <= raw_tiles:
                    break
            if expected_count == 0 and reco_seen and idle >= 2:
                break

            idle = idle + 1 if raw_tiles <= last_raw else 0
            last_raw = raw_tiles
            # Touch the final catalog tile itself, not the recommendations.
            driver.execute_script(SCROLL_TO_CATALOG_END)
            # Allow the website to fetch/render the next lazy-loaded batch.
            # Short delay when it responds quickly; up to load_timeout otherwise.
            fresh = wait_for_new_tiles(driver, raw_tiles, timeout=load_timeout)
            if fresh['raw_tiles'] > raw_tiles:
                idle = 0
                continue
            if idle >= idle_limit:
                print('No new catalog tiles after repeated waits: stopping as incomplete', flush=True)
                break

        # Refresh final list after the last wait.
        snapshot = store_snapshot(driver)
        if snapshot['found']:
            for item in snapshot['rows']:
                previous = found_items.get(item['article'])
                if previous is None or item['price'] is not None:
                    found_items[item['article']] = item
        count = len(found_items)
        complete = bool(reco_seen and (not expected_count or count >= expected_count))
        payload = {
            'store_url':STORE_URL, 'pvz':pvz, 'pvz_address':address,
            'expected_count':expected_count, 'complete':complete,
            'count':count, 'with_price':sum(x['price'] is not None for x in found_items.values()),
            'catalog_cards':snapshot.get('raw_tiles', 0),
            'recommendations_excluded':True,
            'items':sorted(found_items.values(), key=lambda x:int(x['article'])),
        }
        output = ROOT / 'storefront_prices_test.json'
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Collected: {count}; with_price: {payload["with_price"]}; catalog_cards: {payload["catalog_cards"]}; '
              f'catalog_end_verified: {complete}', flush=True)
        print(f'Saved: {output}', flush=True)
        if not complete:
            print('WARNING: каталог загружен не полностью или ожидаемое количество не найдено; '
                  'результат предварительный.', flush=True)
    finally:
        driver.quit()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--headed', action='store_true')
    p.add_argument('--pvz', default=DEFAULT_PVZ)
    p.add_argument('--max-scrolls', type=int, default=60)
    p.add_argument('--idle-limit', type=int, default=3)
    p.add_argument('--expected-count', type=int, default=69,
                   help='Expected catalog size for this test; 0 disables size check')
    p.add_argument('--load-timeout', type=float, default=2.0,
                   help='Maximum wait for each lazy-loaded group of cards')
    args = p.parse_args()
    run(args.headed, args.pvz, args.max_scrolls, args.idle_limit,
        args.expected_count, args.load_timeout)