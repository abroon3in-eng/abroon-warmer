#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
آبرون — گرم‌کننده کش LiteSpeed (جایگزین Crawler برای هاست اشتراکی)
هر اجرا: همه URLهای نقشه سایت را با UA دسکتاپ و موبایل درخواست می‌کند
تا نسخه کش «مهمان» همه صفحات قبل از رسیدن بازدیدکننده واقعی ساخته شود.

ترتیب اولویت (در صورت قطع شدن وسط کار، مهم‌ترین‌ها گرم شده‌اند):
  ۱) صفحه اصلی + صفحات فروشگاه  ۲) محصولات  ۳) دسته‌بندی‌ها  ۴) برگه‌ها  ۵) مقالات
"""
import re
import sys
import time
import gzip
import urllib.request

SITE = "https://abroonco.com"
SITEMAP_INDEX = SITE + "/sitemap_index.xml"

DESKTOP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
             "Mobile/15E148 Safari/604.1")

SLEEP_BETWEEN = 0.15   # ثانیه — ملاحظه هاست اشتراکی
TIMEOUT = 20
RETRY = 1              # هر درخواست خطادار یک‌بار دیگر تلاش می‌شود

LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)

# صفحات حیاتی — همیشه اول از همه گرم می‌شوند (صفحه اصلی و فروشگاه)
PRIORITY_URLS = [
    SITE + "/",
    SITE + "/%D9%81%D8%B1%D9%88%D8%B4%DA%AF%D8%A7%D9%87-%D8%A2%D8%A8%D8%B1%D9%88%D9%86/",
    SITE + "/%d9%81%d8%b1%d9%88%d8%b4%da%af%d8%a7%d9%87-%da%a9%d8%b4%d8%a7%d9%88%d8%b1%d8%b2%db%8c/",
    SITE + "/%d9%85%d8%ad%d8%B5%d9%88%d9%84%d8%A7%d8%AA-%d9%81%d8%B1%d9%88%D8%B4%da%af%D8%A7%D9%87/",
]

# ترتیب نقشه‌های سایت = ترتیب اولویت گرم‌کردن
SITEMAP_ORDER = (
    "product-sitemap",          # محصولات (پرفروش‌ترها جلوی لیست هستند)
    "product_cat-sitemap",      # دسته‌بندی محصولات
    "product_brand-sitemap",
    "page-sitemap",             # برگه‌ها
    "post-sitemap",             # مقالات
    "category-sitemap",         # دسته‌های وبلاگ
)


def fetch(url, ua):
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return resp.status, resp.headers.get("X-LiteSpeed-Cache", "-")
    except Exception as e:
        return 0, str(e)[:60]


def fetch_retry(url, ua):
    status, cache = fetch(url, ua)
    tries = 0
    while status == 0 and tries < RETRY:
        tries += 1
        time.sleep(1)
        status, cache = fetch(url, ua)
    return status, cache


def _sitemap_urls(sm):
    req = urllib.request.Request(sm, headers={"User-Agent": DESKTOP_UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        body = r.read().decode("utf-8", "ignore")
    return LOC_RE.findall(body)


def collect_urls():
    urls = list(PRIORITY_URLS)
    try:
        req = urllib.request.Request(SITEMAP_INDEX, headers={"User-Agent": DESKTOP_UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            index_body = r.read().decode("utf-8", "ignore")
        sitemaps = LOC_RE.findall(index_body)
    except Exception as e:
        print("sitemap index error:", e)
        sitemaps = []
    # فقط نقشه‌های مهم (برچسب‌ها و بقیه لازم نیست) — به ترتیب اولویت
    for w in SITEMAP_ORDER:
        for sm in sitemaps:
            if w in sm:
                try:
                    found = _sitemap_urls(sm)
                    print(f"  {sm.split('/')[-1]}: {len(found)} URL")
                    urls.extend(found)
                except Exception as e:
                    print("  error", sm, e)
                break
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def warm_pass(ua_name, ua, urls, stats):
    print(f"--- pass {ua_name} ---")
    for i, u in enumerate(urls, 1):
        status, cache = fetch_retry(u, ua)
        if status == 200 and cache.upper().startswith("HIT"):
            stats["hit"] += 1
        elif status == 200:
            stats["miss"] += 1
        else:
            stats["err"] += 1
            print(f"  [{ua_name}] ERR {status} {cache} {u}")
        if i % 50 == 0:
            print(f"  [{ua_name}] {i}/{len(urls)} ...")
        time.sleep(SLEEP_BETWEEN)


def main():
    t0 = time.time()
    urls = collect_urls()
    print(f"TOTAL URLs: {len(urls)}")
    stats = {"hit": 0, "miss": 0, "err": 0}
    for ua_name, ua in (("DESKTOP", DESKTOP_UA), ("MOBILE", MOBILE_UA)):
        warm_pass(ua_name, ua, urls, stats)
    mins = round((time.time() - t0) / 60, 1)
    print(f"WARMING DONE hit={stats['hit']} miss={stats['miss']} "
          f"err={stats['err']} minutes={mins}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
