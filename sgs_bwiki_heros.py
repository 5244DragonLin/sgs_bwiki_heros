#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三国杀武将信息爬虫
==================
爬取 bilibili 三国杀 WIKI 武将图鉴页面：
  https://wiki.biligame.com/sgs/武将图鉴

爬取字段：
  - 武将名、性别、势力、名将堂、别称
  - 武将包、上线时间、珠联璧合（国战专属）、战功、定位
  - 每种版本（经典 / 界限突破 / 国战）下的：技能名 + 技能描述 + 台词

功能特性：
  1. 多参数组合过滤：按武将包、势力、数量限制
  2. 增量爬取：跳过已爬取且未变化的武将
  3. 自动保存：每爬取 N 个武将自动写入磁盘
  4. 断点续爬：中断后可恢复
  5. 输出格式：JSON（结构化） + CSV（平铺表格）

用法：
  python sgs_bwiki_heros.py [--pack 标准-蜀汉虎将] [--faction 蜀] [--limit 10] [--auto-save 20]
"""

import os
import sys
import json
import re
import time
import hashlib
import argparse
import random
import yaml
from datetime import datetime
from typing import Optional

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("请先安装依赖: pip install beautifulsoup4 requests lxml")
    sys.exit(1)

# ============ 全局配置 ============

BASE_URL = "https://wiki.biligame.com/sgs"
INDEX_URL = f"{BASE_URL}/%E6%AD%A6%E5%B0%86%E5%9B%BE%E9%89%B4"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    # 补全浏览器常规头，避免只带 UA 被反爬识别为脚本
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    # 模拟从图鉴页点进武将详情，进一步贴近真实浏览器
    "Referer": INDEX_URL,
}
# 复用会话：自动保持 cookie / 复用 TCP 连接，使请求像同一浏览器，
# 降低被频率限制(567)的概率
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# 实际请求间隔 = DELAY_BASE + random.uniform(0, DELAY_JITTER)，二者均可在 config.yaml 设置
DELAY_BASE = 1.0             # 基础请求间隔（秒）
DELAY_JITTER = 2.0          # 随机抖动上限（秒）
MAX_RETRIES = 5              # 单个页面最大重试次数
REQUEST_TIMEOUT = 30        # 请求超时（秒）
SAVE_EVERY_N = 20            # 每爬取多少个武将自动保存

# 输出目录（可通过 -o 参数修改）
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# ============ 工具函数 ============


def safe_get_text(element, sep=" "):
    """安全地获取元素的纯文本，过滤掉 script/style 内容"""
    if element is None:
        return ""
    for tag in element.find_all(["script", "style"]):
        tag.decompose()
    return element.get_text(separator=sep, strip=True)


def clean_text(text: str) -> str:
    """清理文本：去除多余空白、HTML 实体"""
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("\xa0", " ").replace("\u3000", " ")
    return text


def compute_page_hash(html: str) -> str:
    """计算页面内容的 hash，用于增量检测"""
    return hashlib.md5(html.encode("utf-8")).hexdigest()


def fetch_page(url: str, retries: int = None) -> Optional[str]:
    """带重试的页面获取（指数退避 + 567 特殊处理）

    使用全局 SESSION（保持 cookie 与连接），请求头见 HEADERS。
    """
    if retries is None:
        retries = MAX_RETRIES
    for attempt in range(retries):
        try:
            r = SESSION.get(url, timeout=REQUEST_TIMEOUT)
            r.encoding = "utf-8"
            if r.status_code == 200:
                return r.text
            if r.status_code == 567:
                wait = 5 * (attempt + 1)  # 567 是频率限制，等更久
                print(f"  [WARN] 频率限制(567)，等待 {wait}s 后重试...")
                time.sleep(wait)
                continue
            print(f"  [WARN] HTTP {r.status_code} for {url}, retry {attempt + 1}")
        except requests.RequestException as e:
            print(f"  [WARN] Request failed: {e}, retry {attempt + 1}")
        # 指数退避（基数含随机抖动，避免机械节奏）
        time.sleep((DELAY_BASE + random.uniform(0, DELAY_JITTER)) * (2 ** attempt))
    return None


def url_encode_chinese(name: str) -> str:
    """对中文名字进行 URL 编码"""
    return requests.utils.quote(name, safe="")


# ============ 武将列表获取 ============


def extract_character_list() -> tuple[list[dict], str]:
    """
    从武将图鉴页面提取所有武将名字。
    名字存储在 JS 变量 var titles = "..." 中。
    同时提取势力/武将包的筛选信息（带数量）。
    返回 (武将列表, 页面 HTML)。
    """
    print("[*] 正在获取武将列表...")
    html = fetch_page(INDEX_URL)
    if not html:
        print("[!] 无法获取武将图鉴页面")
        return [], ""

    # 提取 JS 中的 titles 变量
    match = re.search(r'var titles\s*=\s*"([^"]+)"', html)
    if not match:
        print("[!] 未找到武将列表数据")
        return [], html

    names = [n.strip() for n in match.group(1).split(",") if n.strip()]
    print(f"[+] 共发现 {len(names)} 个武将")

    # 提取筛选区信息（势力及数量）
    soup = BeautifulSoup(html, "html.parser")
    factions = {}
    rows = soup.find_all("tr", attrs={"data-ask-key": "势力::"})
    for row in rows:
        for li in row.find_all("li", class_="queryParams"):
            cond = li.get("data-conditions", "")
            small = li.find("small")
            if cond and small:
                count = int(re.search(r"\d+", small.get_text()).group())
                factions[cond] = count

    print(f"[+] 势力分布: {factions}")

    # 提取武将包
    packs = {}
    pack_rows = soup.find_all("tr", attrs={"data-ask-key": "武将包::"})
    for row in pack_rows:
        for li in row.find_all("li", class_="queryParams"):
            cond = li.get("data-conditions", "")
            small = li.find("small")
            if cond and small:
                count = int(re.search(r"\d+", small.get_text()).group())
                packs[cond] = count

    print(f"[+] 武将包数量: {len(packs)}")

    characters = [{"name": n, "url": f"{BASE_URL}/{url_encode_chinese(n)}"} for n in names]
    return characters, html


# ============ 单个武将信息爬取 ============


def parse_character_page(html: str, char_name: str) -> dict:
    """
    解析单个武将页面的 HTML，返回结构化数据。
    """
    soup = BeautifulSoup(html, "html.parser")
    content_text = soup.find("div", id="mw-content-text") or soup.find(
        "div", class_="mw-content-text"
    )
    main = (
        content_text.find("div", class_="mw-parser-output") or content_text
        if content_text
        else soup.body
    )

    result = {
        "name": char_name,
        "gender": "",
        "faction": "",
        "hall_of_fame": "",
        "nickname": "",
        "title": "",
        "pack": "",
        "release_time": "",
        "alliances": [],       # 珠联璧合
        "achievements": [],    # 战功
        "position": "",        # 定位
        "versions": {},        # { "经典": {...}, "界限突破": {...}, "国战": {...} }
        "page_hash": compute_page_hash(html),
        "crawl_time": datetime.now().isoformat(),
    }

    # ---- 1. 基本信息：性别、势力、名将堂、别称 ----
    info_divs = main.find_all(
        "div",
        class_=lambda c: c
        and "flex-container" in (c if isinstance(c, str) else " ".join(c))
        and "col-direction" in (c if isinstance(c, str) else " ".join(c))
        and "themed-container" in (c if isinstance(c, str) else " ".join(c))
        and "center-on-x-axis" in (c if isinstance(c, str) else " ".join(c)),
    )
    for info_div in info_divs:
        label_text = safe_get_text(info_div)
        if "性别" in label_text or "势力" in label_text or "名将堂" in label_text:
            for row in info_div.find_all(
                "div", class_=lambda c: c and "flex-container" in str(c)
            ):
                label_el = row.find(
                    "p",
                    class_=lambda c: c and "gold-title-color" in str(c),
                )
                if label_el:
                    key = clean_text(label_el.get_text())
                    # value 是 label 后面的文本/节点
                    value_parts = []
                    for sibling in label_el.parent.children:
                        if sibling != label_el and sibling.name != "p":
                            value_parts.append(clean_text(str(sibling.string or "")))
                        elif sibling != label_el and sibling.name == "p":
                            continue
                    # Alternative: get all text and remove the label
                    full_text = clean_text(row.get_text())
                    value = full_text.replace(key, "").strip()

                    if "性别" in key:
                        result["gender"] = value
                    elif "势力" in key:
                        result["faction"] = value
                    elif "名将堂" in key:
                        result["hall_of_fame"] = value
                    elif "别称" in key:
                        result["nickname"] = value
            break  # 只处理第一个匹配的

    # ---- 2. 称号（武将称号） ----
    title_el = main.find("p", class_="title-font")
    if title_el:
        # 称号通常在 "武将称号：" 后面
        parent_div = title_el.find_parent("div")
        if parent_div:
            full_text = safe_get_text(parent_div)
            m = re.search(r"武将称号[：:]\s*(.+)", full_text)
            if m:
                result["title"] = m.group(1).strip()

    # ---- 3. 武将包、上线时间、珠联璧合 ----
    # 查找包含"武将包"文字的 div
    for div in main.find_all("div"):
        text = safe_get_text(div)
        if "武将包" in text and "上线时间" in text:
            # 找到相应的 flex-container 行
            rows = div.find_parent().find_all(
                "div",
                class_=lambda c: c and "flex-container" in str(c) and "equal-divide" in str(c),
            ) if div.find_parent() else []
            if not rows:
                rows = div.find_all(
                    "div",
                    class_=lambda c: c and "flex-container" in str(c) and "equal-divide" in str(c),
                )
            for row_container in rows:
                labels = row_container.find_all(
                    "div",
                    class_=lambda c: c and "gold-title-color" in str(c),
                )
                for label_el in labels:
                    key = clean_text(label_el.get_text())
                    # 获取 label 后面的所有内容
                    value_div = label_el.find_parent("div")
                    if value_div:
                        full = clean_text(value_div.get_text())
                        value = full.replace(key, "").strip()
                    else:
                        value = ""

                    if "武将包" in key:
                        result["pack"] = value
                    elif "上线时间" in key:
                        result["release_time"] = value
                    elif "珠联璧合" in key:
                        # 提取友方武将名（去重）
                        allies = []
                        seen_allies = set()
                        for a in row_container.find_all("a"):
                            ally_name = a.get("title") or a.get_text(strip=True)
                            if ally_name and ally_name != char_name and ally_name not in seen_allies:
                                seen_allies.add(ally_name)
                                allies.append(ally_name)
                        result["alliances"] = allies
                    elif "战功" in key:
                        achievements = []
                        for a in row_container.find_all("a"):
                            achievements.append(a.get_text(strip=True))
                        result["achievements"] = achievements
                    elif "定位" in key:
                        result["position"] = value
            break

    # ---- 4. 各版本技能与台词 ----
    # 版本标题（h2）和 skill section 在 find_all 中按 DOM 顺序返回。
    # 只需按顺序配对即可，跳过自走棋部分。
    version_map = {
        "经典版本": "classic",
        "界限突破版本": "breakthrough",
        "国战版本": "national_war",
    }

    # 收集版本标题按 DOM 顺序
    all_h2 = main.find_all('h2')
    versions_in_order = []
    for h2 in all_h2:
        span = h2.find('span', class_='mw-headline')
        if span:
            text = span.get_text(strip=True)
            if text in version_map:
                versions_in_order.append(version_map[text])

    # 收集所有 skill section
    all_sections = main.find_all('div', class_='character-lines-and-skills-section')

    # 找出自走棋标题
    chess_h2 = None
    for h2 in all_h2:
        span = h2.find('span', class_='mw-headline')
        if span and span.get_text(strip=True) == '自走棋':
            chess_h2 = h2
            break

    # 过滤掉自走棋之后的 section，然后取前 N 个（N=版本数）
    main_str = str(main)
    chess_pos = main_str.find(str(chess_h2)) if chess_h2 else float('inf')

    sections_in_order = []
    for sec in all_sections:
        sec_str = str(sec)
        sec_pos = main_str.find(sec_str)
        # 跳过自走棋之后的 section
        if sec_pos > chess_pos and chess_pos != float('inf'):
            continue
        sections_in_order.append(sec)
        if len(sections_in_order) >= len(versions_in_order):
            break

    # 配对
    for vkey, sec in zip(versions_in_order, sections_in_order):
        skills_data = {"skills": [], "lines": {}}
        _parse_skills_and_lines(sec, skills_data, result["name"])
        if skills_data["skills"] or skills_data["lines"]:
            result["versions"][vkey] = skills_data

    return result


def _parse_skills_and_lines(section, skills_data: dict, char_name: str):
    """
    从 character-lines-and-skills-section div 中解析技能和台词。
    """
    current_skill = None

    # 找到所有包含 basic-info-row-label 的行
    # 先找到所有 basic-info-row-label，然后定位到其父 flex-container 行
    labels = section.find_all("div", class_="basic-info-row-label", recursive=True)

    for label_el in labels:
        skill_name = clean_text(label_el.get_text().replace("\xa0", " "))
        if not skill_name:
            continue

        # 判断是技能行还是台词行
        label_classes = label_el.get("class", [])
        is_skill = "技能标签" in str(label_classes)
        is_death = skill_name == "阵亡"

        # 找到描述部分：label 的父 flex-container 中的同级兄弟 div
        row_container = label_el.find_parent(
            lambda tag: tag.name == "div"
            and tag.get("class")
            and "flex-container" in tag.get("class", [])
        )

        description = ""
        if row_container:
            # 找到 label 之外的那个 div（描述 div）
            for child in row_container.find_all(recursive=False):
                if child != label_el and child.get_text(strip=True):
                    desc_text = clean_text(child.get_text())
                    # 去掉 CSS style 中的占位文本
                    if desc_text and desc_text != skill_name:
                        description = desc_text
                        break

        if is_skill:
            skill_entry = {"name": skill_name, "description": description}
            # 去重：同 section 中同一个技能名只保留第一个
            if not any(s["name"] == skill_name for s in skills_data["skills"]):
                skills_data["skills"].append(skill_entry)
            current_skill = skill_name
        elif is_death:
            if description and "阵亡" not in description:
                skills_data["lines"]["阵亡"] = skills_data["lines"].get("阵亡", [])
                skills_data["lines"]["阵亡"].append(description)
        else:
            # 台词行：label 里的文字是技能名
            # 映射到已注册的技能名
            target_skill = skill_name
            found = any(s["name"] == target_skill for s in skills_data["skills"])
            if not found:
                target_skill = current_skill

            if target_skill and description:
                if target_skill not in skills_data["lines"]:
                    skills_data["lines"][target_skill] = []
                skills_data["lines"][target_skill].append(description)

# ============ 数据存储 ============


def save_json(characters: list[dict], filepath: str):
    """保存为 JSON 格式"""
    data = {
        "meta": {
            "total": len(characters),
            "crawl_time": datetime.now().isoformat(),
            "source": INDEX_URL,
        },
        "characters": characters,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============ 增量爬取管理 ============


def load_checkpoint() -> dict:
    """加载检查点（已爬取的武将数据）"""
    checkpoint_path = os.path.join(OUTPUT_DIR, "checkpoint.json")
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                print(f"[*] 加载检查点: {len(data.get('characters', []))} 个已爬取武将")
                return data
            except json.JSONDecodeError:
                print("[!] 检查点损坏，重新爬取")
    return {"characters": [], "processed_names": set(), "page_hashes": {}}


def save_checkpoint(characters: list[dict]):
    """保存检查点"""
    checkpoint_path = os.path.join(OUTPUT_DIR, "checkpoint.json")
    processed_names = {c["name"] for c in characters}
    page_hashes = {c["name"]: c["page_hash"] for c in characters}
    data = {
        "characters": characters,
        "processed_names": list(processed_names),
        "page_hashes": page_hashes,
        "updated_at": datetime.now().isoformat(),
    }
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def needs_update(
    char_name: str,
    processed_names: set,
    page_hashes: dict,
) -> bool:
    """检查武将是否需要更新（增量爬取）"""
    return char_name not in processed_names


# ============ 筛选功能 ============


def filter_characters(
    characters: list[dict],
    pack: str = None,
    faction: str = None,
    limit: int = None,
    version: str = None,
) -> list[dict]:
    """
    按条件筛选已爬取的武将。
    """
    result = characters

    if pack:
        result = [c for c in result if pack.lower() in c.get("pack", "").lower()]
        print(f"[*] 筛选武将包 '{pack}': {len(result)} 个")

    if faction:
        result = [c for c in result if faction in c.get("faction", "")]
        print(f"[*] 筛选势力 '{faction}': {len(result)} 个")

    if version:
        result = [c for c in result if version in c.get("versions", {})]
        print(f"[*] 筛选版本 '{version}': {len(result)} 个")

    if limit and limit > 0:
        result = result[:limit]
        print(f"[*] 限制数量: {limit} 个")

    return result


# ============ 武将包结构解析 ============


def extract_pack_structure(html: str) -> dict:
    """
    从武将图鉴页面提取武将包结构，按网站默认视图上的顺序返回。
    包含每个武将包及其所属大类的图标路径。
    """
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("div", class_="mw-parser-output") or soup.body
    table = main.find("table", class_="wikitable")
    if not table:
        return {}

    # 类别名映射
    category_map = {
        "标准包": "标准",
        "神话再临": "神话再临",
        "一将成名": "一将成名",
        "星火燎原": "星火燎原",
        "限定专属": "限定",
        "威震天下": "威震",
        "谋": "谋",
        "星河璀璨": "星河璀璨",
        "群英荟萃": "荟萃",
        "其他扩展包": "其他",
    }

    def parse_row(row):
        """解析单行，返回 (category_name, category_icon, list of pack dicts)"""
        ask_key = row.get("data-ask-key", "")
        if "武将包" not in ask_key:
            return None

        th = row.find("th")
        td = row.find("td")
        if not td:
            return None

        category_name = ""
        category_icon = ""
        if th:
            th_img = th.find("img")
            if th_img:
                alt = th_img.get("alt", "").replace(".png", "").strip()
                category_name = category_map.get(alt, alt)
                category_icon = th_img.get("src", "")

        packs = []
        for li in td.find_all("li", class_="queryParams"):
            pack_name = li.get("data-conditions", "").strip()
            if not pack_name:
                continue
            img = li.find("img")
            icon_url = img.get("src") if img else ""
            small = li.find("small")
            count = 0
            if small:
                count_match = re.search(r"(\d+)", small.get_text())
                count = int(count_match.group(1)) if count_match else 0
            packs.append({
                "name": pack_name,
                "icon": icon_url,
                "count": count,
            })

        return category_name, category_icon, packs

    # 先按默认视图（data-id="Default"）收集顺序和图标
    default_packs = []
    default_categories = []
    default_category_icons = {}

    all_packs = {}       # name -> pack info
    all_category_icons = {}

    for row in table.find_all("tr"):
        data_id = row.get("data-id", "")
        parsed = parse_row(row)
        if not parsed:
            continue
        category_name, category_icon, packs = parsed

        if category_name:
            all_category_icons[category_name] = category_icon

        for p in packs:
            all_packs[p["name"]] = p

        if data_id == "Default":
            if category_name and category_name not in default_categories:
                default_categories.append(category_name)
                default_category_icons[category_name] = category_icon

            for p in packs:
                if p["name"] not in [x["name"] for x in default_packs]:
                    default_packs.append(p)

    # 如果 Default 视图为空，则回退到所有行
    if not default_categories:
        default_categories = []
        for p in all_packs.values():
            cat = categorize_pack(p["name"])
            if cat not in default_categories:
                default_categories.append(cat)
        default_category_icons = all_category_icons

    pack_order = [p["name"] for p in default_packs]
    pack_icons = {p["name"]: p["icon"] for p in default_packs}
    pack_counts = {p["name"]: p["count"] for p in default_packs}

    # 补充非 Default 视图中的包（如 界限突破 视图可能有不同计数）
    for p in all_packs.values():
        if p["name"] not in pack_order:
            pack_order.append(p["name"])
            pack_icons[p["name"]] = p["icon"]
            pack_counts[p["name"]] = p["count"]

    return {
        "pack_order": pack_order,
        "pack_icons": pack_icons,
        "pack_counts": pack_counts,
        "category_icons": {**default_category_icons, **all_category_icons},
    }


def categorize_pack(pack_name: str) -> str:
    """根据武将包名推断所属大类"""
    if not pack_name:
        return "其他"
    if pack_name.startswith("标准-"):
        return "标准"
    if pack_name.startswith("神话再临-"):
        return "神话再临"
    if pack_name.startswith("一将成名-"):
        return "一将成名"
    if pack_name.startswith("星火燎原-"):
        return "星火燎原"
    if pack_name.startswith("限定-"):
        return "限定"
    if pack_name.startswith("威震-"):
        return "威震"
    if pack_name.startswith("谋定-"):
        return "谋"
    if pack_name.startswith("星河璀璨-"):
        return "星河璀璨"
    if pack_name.startswith("荟萃-"):
        return "荟萃"
    if pack_name.startswith("国战-"):
        return "国战"
    return "其他"


def generate_pack_mapping(characters: list[dict], pack_structure: dict) -> dict:
    """
    生成武将包与武将的映射文件。
    """
    pack_order = pack_structure.get("pack_order", [])
    pack_icons = pack_structure.get("pack_icons", {})
    pack_counts = pack_structure.get("pack_counts", {})
    category_icons = pack_structure.get("category_icons", {})

    # 按武将包聚合武将
    pack_to_characters = {}
    for char in characters:
        pack = char.get("pack", "")
        if not pack:
            continue
        if pack not in pack_to_characters:
            pack_to_characters[pack] = []
        pack_to_characters[pack].append(char["name"])

    # 武将 → 所属包
    character_to_pack = {}
    for char in characters:
        pack = char.get("pack", "")
        category = categorize_pack(pack)
        character_to_pack[char["name"]] = {
            "pack": pack,
            "pack_icon": pack_icons.get(pack, ""),
            "category": category,
            "category_icon": category_icons.get(category, ""),
        }

    # 按网站顺序构建大类 → 子包结构
    categories_seen = set()
    pack_categories = []
    category_pack_map = {}

    for pack in pack_order:
        category = categorize_pack(pack)
        if category not in category_pack_map:
            category_pack_map[category] = []
        category_pack_map[category].append(pack)

    for pack in pack_order:
        category = categorize_pack(pack)
        if category in categories_seen:
            continue
        categories_seen.add(category)

        packs = []
        for sub_pack in category_pack_map.get(category, []):
            packs.append({
                "name": sub_pack,
                "icon": pack_icons.get(sub_pack, ""),
                "count": pack_counts.get(sub_pack, 0),
                "characters": pack_to_characters.get(sub_pack, []),
            })

        pack_categories.append({
            "category": category,
            "category_icon": category_icons.get(category, ""),
            "packs": packs,
        })

    # 未在网站顺序中但实际数据里有的包
    for pack in sorted(pack_to_characters.keys()):
        if pack in pack_order:
            continue
        category = categorize_pack(pack)
        if category not in categories_seen:
            categories_seen.add(category)
            pack_categories.append({
                "category": category,
                "category_icon": category_icons.get(category, ""),
                "packs": [],
            })
        for cat in pack_categories:
            if cat["category"] == category:
                cat["packs"].append({
                    "name": pack,
                    "icon": pack_icons.get(pack, ""),
                    "count": len(pack_to_characters[pack]),
                    "characters": pack_to_characters[pack],
                })

    return {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "total_characters": len(characters),
            "total_packs": len(pack_to_characters),
            "source": INDEX_URL,
        },
        "pack_categories": pack_categories,
        "character_to_pack": character_to_pack,
        "pack_to_characters": pack_to_characters,
    }


def save_pack_mapping(mapping: dict, filepath: str):
    """保存武将包映射文件"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"[+] 武将包映射已保存: {filepath}")


# ============ 主爬取循环 ============


def crawl(
    pack_filter: str = None,
    faction_filter: str = None,
    limit: int = None,
    save_every: int = SAVE_EVERY_N,
    skip_existing: bool = True,
    resume: bool = True,
):
    """主爬取函数"""

    # ---- 1. 获取武将列表 ----
    all_characters, index_html = extract_character_list()
    if not all_characters:
        print("[!] 没有获取到武将列表，退出")
        return

    # 提取武将包结构（顺序 + 图标）
    pack_structure = extract_pack_structure(index_html)

    # ---- 2. 处理筛选条件 ----
    need_filter_after = bool(faction_filter or pack_filter)

    if faction_filter:
        print(f"[*] 爬取后只保留势力'{faction_filter}'的武将")

    if pack_filter:
        print(f"[*] 爬取后只保留武将包'{pack_filter}'的武将")

    if limit and limit > 0 and not need_filter_after:
        all_characters = all_characters[:limit]
        print(f"[*] 限制爬取数量: {limit} 个")

    # ---- 3. 加载检查点（增量爬取） ----
    checkpoint = load_checkpoint()
    existing = checkpoint.get("characters", [])
    existing_names = {c["name"] for c in existing}
    existing_hashes = checkpoint.get("page_hashes", {})

    # 如果启用增量，先用已有的数据
    characters = list(existing) if skip_existing else []

    # 需要爬取的武将
    to_crawl = []
    for ch in all_characters:
        if skip_existing and ch["name"] in existing_names:
            continue
        to_crawl.append(ch)

    print(f"[*] 需要爬取: {len(to_crawl)} 个武将（已存在 {len(existing_names)} 个）")

    # ---- 4. 逐个爬取（进度条） ----
    success_count = 0
    fail_count = 0
    matched_count = 0
    target_count = limit if limit and need_filter_after else None
    use_tqdm = tqdm is not None and len(to_crawl) > 1 and not target_count
    iterator = tqdm(to_crawl, desc="爬取武将", unit="个") if use_tqdm else to_crawl

    # 有筛选条件时手动显示进度
    if target_count:
        print(f"[*] 爬取中，目标: 收集 {target_count} 个符合条件的武将")
    current_name = ""

    for idx, ch in enumerate(iterator):
        name = ch["name"]
        current_name = name

        # 如果已达到目标筛选数量，提前结束
        if target_count and matched_count >= target_count:
            remaining = len(to_crawl) - idx
            print(f"\n[+] 已收集满 {matched_count} 个，剩余 {remaining} 个不再爬取")
            break

        if not use_tqdm and not target_count:
            print(f"\n[{idx + 1}/{len(to_crawl)}] 正在爬取: {name}...")

        html = fetch_page(ch["url"])
        if not html:
            if not use_tqdm and not target_count:
                print(f"  [!] 爬取失败: {name}，跳过")
            fail_count += 1
            continue

        try:
            data = parse_character_page(html, name)
            characters.append(data)
            success_count += 1

            # 检查是否符合筛选条件
            if need_filter_after:
                matches = True
                if faction_filter and data.get("faction", "") != faction_filter:
                    matches = False
                if pack_filter and pack_filter not in data.get("pack", ""):
                    matches = False
                if matches:
                    matched_count += 1
                    if target_count:
                        print(f"  ✓ 第{matched_count}/{target_count}个: {name} ({data['faction']}·{data['pack']})")
                else:
                    if target_count:
                        print(f"  ✗ 不匹配: {name} ({data['faction']}·{data['pack']})")

            if use_tqdm:
                iterator.set_postfix(
                    success=success_count,
                    fail=fail_count,
                    current=name,
                )
        except Exception as e:
            if not use_tqdm and not target_count:
                print(f"  [!] 解析失败: {name} - {e}")
            fail_count += 1
            continue

        # 自动保存
        if (idx + 1) % save_every == 0:
            save_checkpoint(characters)
            save_json(characters, os.path.join(OUTPUT_DIR, "characters.json"))

        time.sleep(DELAY_BASE + random.uniform(0, DELAY_JITTER))  # 加随机抖动

    if use_tqdm:
        iterator.close()

    # ---- 5. 应用筛选 ----
    if need_filter_after and characters:
        before = len(characters)
        filtered = []
        for c in characters:
            if faction_filter and c.get("faction", "") != faction_filter:
                continue
            if pack_filter and pack_filter not in c.get("pack", ""):
                continue
            filtered.append(c)
        characters = filtered
        if limit:
            characters = characters[:limit]
        print(f"[*] 筛选: {before} → {len(characters)} 个武将")

    # ---- 6. 最终保存 ----
    print("\n" + "=" * 50)
    print(f"[*] 爬取完成，共 {len(characters)} 个武将")

    save_checkpoint(characters)
    save_json(characters, os.path.join(OUTPUT_DIR, "characters.json"))

    # ---- 6. 生成武将包映射 ----
    if pack_structure and characters:
        mapping = generate_pack_mapping(characters, pack_structure)
        save_pack_mapping(mapping, os.path.join(OUTPUT_DIR, "pack_character_map.json"))

    return characters


# ============ 命令行入口 ============


def load_config(config_path: str = "config.yaml") -> dict:
    """从 YAML 配置文件加载配置并扁平化为 argparse 参数字典。

    优先级: config.yaml > config.example.yaml > 空字典
    自动处理 Windows 路径反斜杠在 YAML 中的转义问题。
    """
    import os as _os

    for path in (config_path, _os.path.splitext(config_path)[0] + ".example.yaml",
                  "config.example.yaml"):
        if _os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    raw = f.read()
                try:
                    data = yaml.safe_load(raw) or {}
                except yaml.YAMLError:
                    fixed = raw.replace("\\", "/")
                    data = yaml.safe_load(fixed) or {}
                return _flatten_config(data)
            except Exception:
                continue
    return {}


def _flatten_config(data: dict) -> dict:
    """将嵌套的 YAML 配置扁平化为 argparse 参数名。"""
    flat = {}

    output = data.get("output", {})
    if isinstance(output, dict):
        if output.get("dir"):
            flat["output"] = output["dir"]
        if output.get("save_every_n") is not None:
            flat["auto_save"] = output["save_every_n"]

    filters = data.get("filters", {})
    if isinstance(filters, dict):
        if filters.get("pack"):
            flat["pack"] = filters["pack"]
        if filters.get("faction"):
            flat["faction"] = filters["faction"]
        if filters.get("limit") and filters["limit"] > 0:
            flat["limit"] = filters["limit"]

    incremental = data.get("incremental", {})
    if isinstance(incremental, dict) and "enabled" in incremental:
        if not incremental["enabled"]:
            flat["no_skip"] = True

    # 网络请求参数（使 config.yaml 中的 request.* 真正生效）
    request = data.get("request", {})
    if isinstance(request, dict):
        if request.get("delay") is not None:
            flat["delay"] = request["delay"]
        if request.get("delay_jitter") is not None:
            flat["delay_jitter"] = request["delay_jitter"]
        if request.get("max_retries") is not None:
            flat["max_retries"] = request["max_retries"]
        if request.get("timeout") is not None:
            flat["timeout"] = request["timeout"]

    return flat


def main(argv=None):
    global DELAY_BASE, DELAY_JITTER, MAX_RETRIES, REQUEST_TIMEOUT, OUTPUT_DIR
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--yaml", "-y", default="config.yaml")
    pre_args, _ = pre_parser.parse_known_args(argv)
    yaml_defaults = load_config(pre_args.yaml)

    parser = argparse.ArgumentParser(
        description="三国杀武将信息爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 爬取所有武将
  python sgs_bwiki_heros.py

  # 爬取蜀势力武将，限制10个
  python sgs_bwiki_heros.py --faction 蜀 --limit 10

  # 按武将包筛选
  python sgs_bwiki_heros.py --pack 标准

  # 每爬取5个自动保存一次
  python sgs_bwiki_heros.py --auto-save 5

  # 不跳过已有武将（强制重新爬取）
  python sgs_bwiki_heros.py --no-skip

  # 从已有数据中筛选（不重新爬取）
  python sgs_bwiki_heros.py --query --faction 魏 --limit 5

  # 输出到指定目录
  python sgs_bwiki_heros.py -o D:/sgs_data
        """,
    )

    parser.add_argument(
        "--yaml", "-y",
        default="config.yaml",
        help="YAML 配置文件路径（CLI 参数优先级高于配置文件）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="输出目录（默认: 脚本所在目录下的 output/）",
    )
    parser.add_argument(
        "--pack", type=str, default=None, help="按武将包筛选（如：标准-蜀汉虎将）"
    )
    parser.add_argument(
        "--faction", type=str, default=None, help="按势力筛选（魏/蜀/吴/群/神）"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="限制爬取或查询数量"
    )
    parser.add_argument(
        "--auto-save",
        type=int,
        default=SAVE_EVERY_N,
        help=f"每 N 个武将自动保存（默认 {SAVE_EVERY_N}）",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="不跳过已爬取的武将（强制重新爬取）",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="不从检查点恢复",
    )
    parser.add_argument(
        "--query",
        action="store_true",
        help="仅查询已有数据，不重新爬取",
    )
    parser.add_argument(
        "--version", type=str, default=None, help="按武将版本筛选（classic/breakthrough/national_war）"
    )
    parser.add_argument(
        "--delay", type=float, default=DELAY_BASE,
        help=f"基础请求间隔（秒），实际间隔 = delay + random.uniform(0, delay_jitter)（默认 {DELAY_BASE}）",
    )
    parser.add_argument(
        "--delay-jitter", type=float, default=DELAY_JITTER,
        help=f"随机抖动上限（秒）（默认 {DELAY_JITTER}）",
    )
    parser.add_argument(
        "--max-retries", type=int, default=MAX_RETRIES,
        help=f"单个页面最大重试次数（默认 {MAX_RETRIES}）",
    )
    parser.add_argument(
        "--timeout", type=int, default=REQUEST_TIMEOUT,
        help=f"请求超时（秒）（默认 {REQUEST_TIMEOUT}）",
    )
    if yaml_defaults:
        parser.set_defaults(**yaml_defaults)

    args = parser.parse_args(argv)

    # 将配置/CLI 中的网络参数同步到全局变量，供 fetch_page / crawl 使用
    DELAY_BASE = args.delay
    DELAY_JITTER = args.delay_jitter
    MAX_RETRIES = args.max_retries
    REQUEST_TIMEOUT = args.timeout

    # 处理输出目录
    global OUTPUT_DIR
    if args.output:
        OUTPUT_DIR = os.path.abspath(args.output)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.query:
        # 仅查询模式
        checkpoint = load_checkpoint()
        characters = checkpoint.get("characters", [])
        if not characters:
            print("[!] 没有已爬取的数据，请先运行爬虫（不带 --query）")
            return

        print(f"[*] 从已有数据中查询...")
        filtered = filter_characters(
            characters,
            pack=args.pack,
            faction=args.faction,
            limit=args.limit,
            version=args.version,
        )
        if filtered:
            save_json(filtered, os.path.join(OUTPUT_DIR, "query_result.json"))
        else:
            print("[!] 没有匹配的武将")
        return

    # 爬取模式
    crawl(
        pack_filter=args.pack,
        faction_filter=args.faction,
        limit=args.limit,
        save_every=args.auto_save,
        skip_existing=not args.no_skip,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
