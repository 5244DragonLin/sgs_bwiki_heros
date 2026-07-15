#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量复核（终版）：缓存实时 HTML，对比"真实技能集合"与解析结果。

真实技能集合 = classic section 内 非阵亡、行内不含 bikit-audio 的标签，
按"去重后的技能名"计（同一技能被新版模板渲染成两行相同描述时只算 1 个）。
解析结果 = parse_character_page(...).versions['classic']['skills'] 的技能名集合。
缺漏的技能若其描述含 '/' 即为 _row_content_is_line 误判所致（源码 bug）。
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
from bs4 import BeautifulSoup
from sgs_bwiki_heros import (
    url_encode_chinese, parse_character_page, clean_text, HEADERS, INDEX_URL,
    _row_content_is_line,
)

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_cache")
os.makedirs(CACHE, exist_ok=True)

NAMES = [
    "卢弈", "SP太史慈", "典韦", "卞夫人", "卫温诸葛直", "孙霸", "宫百万",
    "张翼", "徐琨", "文钦", "胡班", "华雄", "孟优", "张瑾云", "徐庶",
]


def fetch(name):
    p = os.path.join(CACHE, f"{name}.html")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read()
    for _ in range(3):
        try:
            r = SESSION.get(
                "https://wiki.biligame.com/sgs/" + url_encode_chinese(name),
                timeout=30,
            )
            if r.status_code == 200:
                r.encoding = "utf-8"
                open(p, "w", encoding="utf-8").write(r.text)
                return r.text
            if r.status_code == 567:
                time.sleep(5)
                continue
            return None
        except Exception:
            time.sleep(2.5)
    return None


def classic_section(main):
    h2s = main.find_all("h2")
    classic_pos = -1
    for h2 in h2s:
        sp = h2.find("span", class_="mw-headline")
        if sp and sp.get_text(strip=True) == "经典版本":
            classic_pos = str(main).find(str(h2))
            break
    for s in main.find_all("div", class_="character-lines-and-skills-section"):
        if str(main).find(str(s)) > classic_pos:
            return s
    return None


def analyze(name, html):
    soup = BeautifulSoup(html, "html.parser")
    c = soup.find("div", id="mw-content-text")
    main = c.find("div", class_="mw-parser-output") if c else soup
    sec = classic_section(main)
    true_skills = {}  # name -> description (first seen)
    for lab in sec.find_all("div", class_="basic-info-row-label", recursive=True):
        nm = clean_text(lab.get_text().replace("\xa0", " "))
        if not nm or nm == "阵亡":
            continue
        rc = lab.find_parent(
            lambda t: t.name == "div" and t.get("class")
            and "flex-container" in (t.get("class") or [])
        )
        if rc and rc.find("span", class_="bikit-audio"):
            continue  # 语音行
        if nm not in true_skills:
            desc = ""
            if rc:
                for child in rc.find_all(recursive=False):
                    if child != lab and child.get_text(strip=True):
                        dt = clean_text(child.get_text())
                        if dt and dt != nm:
                            desc = dt
                            break
            true_skills[nm] = desc
    data = parse_character_page(html, name)
    parsed = [s["name"] for s in data.get("versions", {}).get("classic", {}).get("skills", [])]
    parsed_set = set(parsed)
    missing = []
    for nm, desc in true_skills.items():
        if nm not in parsed_set:
            missing.append((nm, "/" in desc))
    return sorted(true_skills.keys()), parsed, missing


def main():
    SESSION.get(INDEX_URL, timeout=30)  # warmup
    report = {}
    print("=" * 78)
    for name in NAMES:
        html = fetch(name)
        time.sleep(2.0)
        if html is None:
            print(f"{name}: 限流未验"); report[name] = "限流未验"; continue
        true_set, parsed, missing = analyze(name, html)
        real = len(true_set)
        if not missing and real == len(parsed):
            concl = "OK"
        elif missing:
            concl = "BUG(缺失:" + ",".join(n for n, _ in missing) + ")"
        else:
            concl = "异常"
        report[name] = {"true": real, "parsed": len(parsed), "missing": missing, "concl": concl}
        miss_str = "; ".join(f"{n}(desc含'/')" if d else f"{n}(desc无'/')" for n, d in missing) or "无"
        print(f"{name} | 真实={real} 解析={len(parsed)} | 缺={miss_str} | {concl}")
    bugs = [n for n, v in report.items() if isinstance(v, dict) and v["missing"]]
    print("=" * 78)
    print("真 bug（技能被 '/' 误判丢弃）:", bugs)
    print("限流未验:", [n for n, v in report.items() if v == "限流未验"])


if __name__ == "__main__":
    main()
