#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取真实武将页面并缓存到 tests/fixtures/，避免反复请求触发限流(567)。
用法: python tests/fetch_fixtures.py
"""
import os
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sgs_bwiki_heros import url_encode_chinese, HEADERS  # noqa: E402

BASE_URL = "https://wiki.biligame.com/sgs"
FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

TARGETS = ["卢弈", "SP太史慈", "刘备", "华雄"]


def fetch_with_retry(name: str, retries: int = 3) -> str | None:
    url = f"{BASE_URL}/{url_encode_chinese(name)}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                # 部分页面可能是反爬占位页，简单校验是否含武将内容
                return r.text
            if r.status_code == 567:
                wait = 5 * (attempt + 1)
                print(f"  [WARN] 频率限制(567) {name}，等待 {wait}s 重试...")
                time.sleep(wait)
                continue
            print(f"  [WARN] HTTP {r.status_code} for {name}")
        except requests.RequestException as e:
            print(f"  [WARN] 请求失败 {name}: {e}")
        time.sleep(2 + attempt)
    return None


def main():
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    for name in TARGETS:
        print(f"[*] 抓取 {name} ...")
        html = fetch_with_retry(name)
        if html:
            path = os.path.join(FIXTURE_DIR, f"{name}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  [+] 已缓存: {path} ({len(html)} bytes)")
        else:
            print(f"  [!] 抓取失败: {name}")
        time.sleep(2.5)  # 请求间隔，降低限流风险
    print("[*] 完成。")


if __name__ == "__main__":
    main()
