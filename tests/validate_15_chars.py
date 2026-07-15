#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全量复核：对 15 个"classic 技能为空"武将逐个抓取实时页并解析。

- 用项目 url_encode_chinese 拼 URL，parse_character_page 解析。
- 独立测量"网站实际技能数"：classic section 内 非阵亡 且 行内不含
  <span class="bikit-audio"> 的标签行数（即网站真实技能行）。
- 与修复后解析的 classic.skills 数对比，给出分类结论。
- 限流(567/超时)重试 3 次，每次请求间隔 2-3s，UA=Mozilla/5.0。
"""
import sys
import os
import time
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bs4 import BeautifulSoup
from sgs_bwiki_heros import (
    url_encode_chinese, parse_character_page, clean_text, HEADERS, INDEX_URL,
)

BASE = "https://wiki.biligame.com/sgs/"
NAMES = [
    "卢弈", "SP太史慈", "典韦", "卞夫人", "卫温诸葛直", "孙霸", "宫百万",
    "张翼", "徐琨", "文钦", "胡班", "华雄", "孟优", "张瑾云", "徐庶",
]

# 用项目完整浏览器头；仅带 UA 会被 567 限流。先用索引页热身获取会话。
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
REQUEST_TIMEOUT = 30


def warmup():
    try:
        SESSION.get(INDEX_URL, timeout=REQUEST_TIMEOUT)
    except Exception:
        pass


def fetch(name):
    url = BASE + url_encode_chinese(name)
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r.text, None
            if r.status_code == 567:
                time.sleep(5 * (attempt + 1))
                continue
            return None, f"HTTP {r.status_code}"
        except requests.RequestException as e:
            if attempt == 2:
                return None, f"REQ {e}"
            time.sleep(2.5)
    return None, "限流/重试失败"


def classic_section(main):
    h2s = main.find_all("h2")
    classic_pos = -1
    for h2 in h2s:
        sp = h2.find("span", class_="mw-headline")
        if sp and sp.get_text(strip=True) == "经典版本":
            classic_pos = str(main).find(str(h2))
            break
    sections = main.find_all("div", class_="character-lines-and-skills-section")
    for s in sections:
        if str(main).find(str(s)) > classic_pos:
            return s
    return None


def website_actual_skills(html):
    """返回 (actual_non_audio_rows, distinct_skill_names, section_has_skill_tag)。"""
    soup = BeautifulSoup(html, "html.parser")
    c = soup.find("div", id="mw-content-text")
    main = c.find("div", class_="mw-parser-output") if c else soup
    sec = classic_section(main)
    if sec is None:
        return None, None, None
    labels = sec.find_all("div", class_="basic-info-row-label", recursive=True)
    has_tag = any("技能标签" in (el.get("class") or []) for el in labels)
    non_audio = 0
    names = set()
    names_include_audio = set()
    for lab in labels:
        nm = clean_text(lab.get_text().replace("\xa0", " "))
        if not nm:
            continue
        if nm == "阵亡":
            continue
        names_include_audio.add(nm)
        rc = lab.find_parent(
            lambda t: t.name == "div" and t.get("class")
            and "flex-container" in (t.get("class") or [])
        )
        audio = bool(rc and rc.find("span", class_="bikit-audio")) if rc else False
        if not audio:
            non_audio += 1
            names.add(nm)
    return non_audio, len(names_include_audio), has_tag


def main():
    warmup()
    rows = []
    for name in NAMES:
        html, err = fetch(name)
        time.sleep(random.uniform(2.0, 3.0))
        if html is None:
            rows.append((name, "限流未验", "-", "-", err or "fetch failed", "-"))
            print(f"[限流未验] {name} ({err})")
            continue
        non_audio, distinct, has_tag = website_actual_skills(html)
        data = parse_character_page(html, name)
        parsed = len(data.get("versions", {}).get("classic", {}).get("skills", []))
        if non_audio is None:
            rows.append((name, "无classic段落", "-", parsed, "页面结构异常", "-"))
            continue
        if non_audio > 0 and parsed > 0:
            concl = "真bug已修"
        elif non_audio == 0 and parsed == 0:
            concl = "网站本就空"
        elif non_audio > 0 and parsed == 0:
            concl = "仍未修复!"
        else:
            concl = "异常"
        note = ""
        if distinct is not None and distinct > non_audio:
            note = f"(网站含语音行技能名{distinct}个>非语音行{non_audio})"
        rows.append((name, non_audio, parsed, concl, "", note))
        print(f"[{concl}] {name}: 网站实际={non_audio} 解析={parsed} tag={has_tag} {note}")

    print("\n" + "=" * 78)
    print("武将 | 网站实际技能数 | 解析skills | 结论 | 备注")
    print("-" * 78)
    for r in rows:
        name, actual, parsed, concl, err, note = r
        print(f"{name} | {actual} | {parsed} | {concl} | {note or err}")
    print("=" * 78)


if __name__ == "__main__":
    main()
