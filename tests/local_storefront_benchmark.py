#!/usr/bin/env python3
"""Experimental JKeratin storefront price collection (separate from product parser)."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from core import DEFAULT_PVZ
from scraper import create_driver, set_pvz, check_visible_pvz, is_blocked

STORE_URL = "https://www.ozon.ru/seller/jkeratin/"
# Only this catalog subtree is allowed. Recommendations are OUTSIDE it.
CATALOG = "#contentScrollPaginator"
EXTRACT = r"""
const root=document.querySelector('#contentScrollPaginator');
if(!root) return {found:false, rows:[], reached_end:false};
const rows=[];
for(const tile of root.querySelectorAll('.tile-root')){
 const a=tile.querySelector('a[href*="/product/"]');
 if(!a) continue;
 const match=new URL(a.href).pathname.match(/-(\d{7,12})\/?$/);
 if(!match) continue;
 const priceEl=tile.querySelector('.c35_6_0-a0 span.c35_6_0-a1');
 const nameLink=tile.querySelector('a[href*="/product/"] .tsBody500Medium');
 const priceText=priceEl?.textContent||'';
 const digits=priceText.replace(/[^0-9]/g,'');
 rows.push({article:match[1],price:digits?Number(digits):null,
            name:nameLink?.textContent?.trim()||'',url:a.href});
}
const grids=Array.from(root.querySelectorAll('[data-widget="tileGridDesktop"]'));
const last=grids.at(-1)||root.lastElementChild||root;
const r=last.getBoundingClientRect();
const headings=Array.from(document.querySelectorAll('span,h1,h2,h3,div'))
 .filter(e=>e.children.length===0 && e.textContent?.trim()==='Возможно, вам понравится');
const end=headings.some(e=>e.getBoundingClientRect().top <= innerHeight);
return {found:true,rows, reached_end:end,
        last_bottom:r.bottom,viewport_height:innerHeight,
        scroll_height:document.documentElement.scrollHeight};
"""

def run(headed: bool, pvz: str, max_scrolls: int, idle_limit: int):
    driver=create_driver(headed=headed)
    collected={}
    try:
        expected=set_pvz(driver,pvz)
        driver.get(STORE_URL)
        check_visible_pvz(driver,expected,timeout=6)
        print(f"PVZ verified: {expected}", flush=True)
        idle=0
        prev_count=0
        reached_end=False
        for step in range(max_scrolls):
            if is_blocked(driver):
                raise RuntimeError("Ozon показал CAPTCHA: сбор прерван, цены не считаются подтверждёнными")
            data=driver.execute_script(EXTRACT)
            if not data["found"]:
                if step>20:
                    raise RuntimeError("Не найден основной контейнер каталога")
                time.sleep(.2)
                continue
            for row in data["rows"]:
                if row["price"] is not None and row["price"]>0:
                    collected[row["article"]]=row
            size=len(collected)
            print(f"Scroll {step}: {size} SKU, recommendation_seen={data['reached_end']}",flush=True)
            if data["reached_end"]:
                reached_end=True
                break
            idle=idle+1 if size==prev_count else 0
            prev_count=size
            if idle>=idle_limit:
                # No progress: do not label the catalog complete unless end is visible.
                break
            driver.execute_script("window.scrollBy(0, Math.round(window.innerHeight*0.8));")
            time.sleep(.25)
        payload={"store_url":STORE_URL,"pvz":pvz,"pvz_address":expected,
                 "complete":reached_end,"count":len(collected),
                 "items":sorted(collected.values(),key=lambda x:int(x["article"]))}
        outfile=ROOT/"storefront_prices_test.json"
        outfile.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"Collected: {len(collected)}; catalog_end_seen: {reached_end}")
        print(f"Saved: {outfile}")
        if not reached_end:
            print("WARNING: каталог мог быть загружен не полностью!")
    finally:
        driver.quit()

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--headed",action="store_true")
    p.add_argument("--pvz",default=DEFAULT_PVZ)
    p.add_argument("--max-scrolls",type=int,default=100)
    p.add_argument("--idle-limit",type=int,default=15)
    a=p.parse_args()
    run(a.headed,a.pvz,a.max_scrolls,a.idle_limit)
