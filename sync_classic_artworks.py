#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_classic_artworks.py — 同步经典形象原画和元数据到 BWIKI 素材目录

功能：
  1. 将 heros/artworks/ 中缺失的经典形象原画复制到 BWIKI/{势力}/ 目录下
  2. 补充 BWIKI/metadata.json 中缺失的经典形象元数据条目

使用方式：
  1. 根据实际路径修改下方 PATH 配置
  2. python sync_classic_artworks.py         # 预览
  3. python sync_classic_artworks.py --execute  # 执行

兼容性（统一约定）：
  - 输入的 characters.json 采用 heros 管线统一格式：{meta, data:[...]}，全中文字段，
    武将以「姓名」为锚点（势力在「势力」、故事在「武将故事」、台词在「版本.经典.武将台词」）。
  - 输出的 metadata.json 采用 skins 管线统一格式：{meta, data:[...]}，全中文字段，
    每条带 key/皮肤名/武将名，字段含 皮肤故事/皮肤台词/品质/收藏册/画师/皮肤上线时间/
    静态获取方式/动态获取方式/语音地址。
  - 复制后的图片会被 scan-skins.js 自动识别；
  - 补充的 metadata 条目使经典形象在画廊中展示完整。
"""

import os
import sys
import json
import shutil
import re
from collections import OrderedDict

# ============================================================
# 路径配置 —— 请根据你的实际目录修改
# ============================================================

# 武将数据目录（含 artworks/ 子目录和 characters.json）
HEROS_DIR = r"E:\BaiduSyncdisk\其他\三国杀皮肤\heros"

# BWIKI 皮肤素材目录（含 魏/蜀/吴/群/神 子目录）
BWIKI_DIR = r"E:\BaiduSyncdisk\其他\三国杀皮肤\BWIKI"

# ============================================================
# 以下无需修改
# ============================================================

ARTWORKS_DIR = os.path.join(HEROS_DIR, "artworks")
CHARACTERS_JSON = os.path.join(HEROS_DIR, "characters.json")
METADATA_JSON = os.path.join(BWIKI_DIR, "metadata.json")
FACTION_DIRS = ["魏", "蜀", "吴", "群", "神"]


def load_characters():
    """从 characters.json（统一格式 {meta, data}）加载武将信息，返回 姓名 -> 武将数据 的映射。

    兼容旧格式（{meta, characters} / 英文字段），便于过渡期使用。
    """
    if not os.path.exists(CHARACTERS_JSON):
        print(f"[!] 未找到: {CHARACTERS_JSON}")
        sys.exit(1)

    with open(CHARACTERS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 兼容新旧格式：新格式 data:[...]，旧格式 characters:[...]
    chars = data.get("data", data.get("characters", []))
    result = {}
    for c in chars:
        # 兼容中/英字段名
        name = c.get("姓名") or c.get("name", "")
        faction = c.get("势力") or c.get("faction", "未知")
        # 取主势力（如 "魏、晋" → "魏"）
        primary = faction.split("、")[0] if "、" in faction else faction
        c["_faction_primary"] = primary
        result[name] = c
    return result


def get_bwiki_files():
    """获取 BWIKI 中已有的所有文件名"""
    existing = set()
    for faction in FACTION_DIRS:
        fdir = os.path.join(BWIKI_DIR, faction)
        if os.path.isdir(fdir):
            for fname in os.listdir(fdir):
                existing.add(fname)
    return existing


def get_heros_artworks():
    """获取 heros/artworks 中所有经典形象原画文件"""
    files = []
    if not os.path.isdir(ARTWORKS_DIR):
        print(f"[!] 未找到目录: {ARTWORKS_DIR}")
        sys.exit(1)

    for fname in os.listdir(ARTWORKS_DIR):
        m = re.match(r"(.+)-经典形象\.(png|jpg|jpeg)$", fname)
        if m:
            files.append(fname)
    return files


def build_audio(char_data):
    """通过拼音规则生成语音 URL，并验证可访问性；通不过则返回空 dict。

    规律: https://web.sanguosha.com/10/pc/res/assets/runtime/voice/skin/{name_py}01/{CamelName}_{CamelSkill}_01.mp3
    从「版本.经典.武将台词」的技能名提取语音（与 skins 管线一致）。
    """
    lines = (char_data.get("版本", {}) or {}).get("经典", {}).get("武将台词", {}) or {}
    if not lines:
        return {}
    try:
        from pypinyin import pinyin as _pinyin, Style as _Style
        import requests as _requests

        name = char_data.get("姓名") or char_data.get("name", "")
        clean_name = name.replace("SP", "")
        name_py = "".join(p[0].lower() for p in _pinyin(clean_name, style=_Style.NORMAL))
        name_camel = (
            "SP" + "".join(p[0].capitalize() for p in _pinyin(clean_name, style=_Style.NORMAL))
            if name.startswith("SP")
            else "".join(p[0].capitalize() for p in _pinyin(clean_name, style=_Style.NORMAL))
        )
        folder = ("SP" if name.startswith("SP") else "") + name_py + "01"

        # 先验证一个代表性 URL 是否可访问
        sample_url = f"https://web.sanguosha.com/10/pc/res/assets/runtime/voice/skin/{folder}/{name_camel}_Dead.mp3"
        try:
            resp = _requests.head(sample_url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            audio_available = resp.status_code == 200
        except Exception:
            audio_available = False

        if not audio_available:
            return {}

        audio = {}
        for skill_name in list(lines.keys()):
            clean_skill = re.sub(r"[☆★◇◆]", "", skill_name).strip()
            skill_camel = "".join(p[0].capitalize() for p in _pinyin(clean_skill, style=_Style.NORMAL))

            if skill_name == "阵亡" or "阵亡" in skill_name:
                url = f"https://web.sanguosha.com/10/pc/res/assets/runtime/voice/skin/{folder}/{name_camel}_Dead.mp3"
                audio["阵亡"] = [url]
            else:
                url1 = f"https://web.sanguosha.com/10/pc/res/assets/runtime/voice/skin/{folder}/{name_camel}_{skill_camel}_01.mp3"
                url2 = f"https://web.sanguosha.com/10/pc/res/assets/runtime/voice/skin/{folder}/{name_camel}_{skill_camel}_02.mp3"
                audio[clean_skill] = [url1, url2]
        return audio
    except ImportError:
        return {}


def build_metadata_entry(char_data):
    """根据 characters.json（统一格式）中的武将数据，构建 metadata 条目。

    返回 dict（与 skins 管线 metadata.json 的统一格式对齐）：
    {key, 皮肤名, 武将名, 皮肤故事, 皮肤台词, 品质, 收藏册, 画师,
     皮肤上线时间, 静态获取方式, 语音地址}
    """
    name = char_data.get("姓名") or char_data.get("name", "")
    entry = OrderedDict()

    # 索引字段（与 skins 管线 metadata 每条一致）
    entry["key"] = f"经典形象*{name}"
    entry["皮肤名"] = "经典形象"
    entry["武将名"] = name

    # 皮肤故事 —— 来自武将的「武将故事」（经典形象故事，含 <br> 转为 \n）
    raw_story = char_data.get("武将故事") or char_data.get("classic_story", "") or ""
    entry["皮肤故事"] = raw_story.replace("<br>", "\n").replace("<br />", "\n").replace("<br/>", "\n")

    # 皮肤台词 —— 来自「版本.经典.武将台词」
    lines = (char_data.get("版本", {}) or {}).get("经典", {}).get("武将台词", {}) or {}
    voice_lines = {}
    for skill_name, line_list in lines.items():
        # 清理技能名中的特殊字符（如 "☆ 怒嗔" → "怒嗔"）
        clean_name = re.sub(r"[☆★◇◆]", "", skill_name).strip()
        # 台词以 "/" 连接，拆分为独立数组
        split_lines = []
        for line in line_list:
            for part in line.split("/"):
                part = part.strip()
                if part:
                    split_lines.append(part)
        if split_lines:
            voice_lines[clean_name] = split_lines
    entry["皮肤台词"] = voice_lines if voice_lines else {}

    # 品质 —— 固定为"原画"
    entry["品质"] = "原画"

    # 收藏册 —— 经典形象不在收藏册内
    entry["收藏册"] = "不在收藏册内"

    # 画师 —— 武将数据中无此字段，留空
    entry["画师"] = None

    # 皮肤上线时间 —— 来自武将的「武将上线时间」
    entry["皮肤上线时间"] = char_data.get("武将上线时间") or char_data.get("release_time", "")

    # 静态获取方式 —— 推断为"拥有武将{name}"
    entry["静态获取方式"] = f"拥有武将{name}"

    # 语音地址 —— 通过拼音规则生成语音 URL，并验证可访问性
    entry["语音地址"] = build_audio(char_data) or None

    return entry


def main():
    execute = "--execute" in sys.argv
    if execute:
        sys.argv.remove("--execute")

    print("=" * 60)
    print("经典形象同步工具（图片 + 元数据）")
    print("=" * 60)
    print()
    print(f"武将数据目录 (HEROS_DIR): {HEROS_DIR}")
    print(f"BWIKI 素材目录 (BWIKI_DIR): {BWIKI_DIR}")
    print()

    # 1. 加载武将数据
    char_map = load_characters()
    print(f"[*] 已加载 {len(char_map)} 个武将数据")

    # 2. 获取 heros 中所有经典形象
    heros_files = get_heros_artworks()
    print(f"[*] heros/artworks/ 中共 {len(heros_files)} 个经典形象原画")

    # 3. 获取 BWIKI 中已有文件
    bwiki_files = get_bwiki_files()
    print(f"[*] BWIKI/ 各势力目录下共 {len(bwiki_files)} 个已有文件")

    # 4. 加载现有 metadata.json（统一格式 {meta, data}），按 key 建索引
    existing_data = []
    existing_meta_by_key = {}
    if os.path.exists(METADATA_JSON):
        with open(METADATA_JSON, "r", encoding="utf-8") as f:
            m = json.load(f)
        existing_data = m.get("data", [])
        for e in existing_data:
            k = e.get("key")
            if k:
                existing_meta_by_key[k] = e
    print(f"[*] BWIKI/metadata.json 已有 {len(existing_data)} 条元数据")
    print()

    # 5. 计算需要处理的文件
    to_copy = []
    to_meta = []  # 需要新增 metadata 条目的武将名
    missing_faction = []
    meta_skip = 0  # metadata 已存在的跳过

    for fname in heros_files:
        m = re.match(r"(.+)-经典形象\.(png|jpg|jpeg)$", fname)
        name = m.group(1)
        char_data = char_map.get(name)
        faction = char_data.get("_faction_primary", "未知") if char_data else "未知"

        # 势力判断
        if faction not in FACTION_DIRS:
            missing_faction.append((fname, name, faction))
            continue

        # 图片是否需要复制
        if fname not in bwiki_files:
            to_copy.append((fname, name, faction))

        # metadata 是否需要补充（以 key 判断，避免重复）
        meta_key = f"经典形象*{name}"
        if meta_key not in existing_meta_by_key:
            if char_data:
                to_meta.append((name, char_data))
            else:
                print(f"  [!] 警告: {name} 在 characters.json 中无数据，跳过 metadata")
        else:
            meta_skip += 1

    # 6. 报告
    print(f"[*] 需要复制图片: {len(to_copy)} 个")
    if to_copy:
        for f in FACTION_DIRS:
            count = sum(1 for _, _, fac in to_copy if fac == f)
            if count > 0:
                print(f"      BWIKI/{f}/: {count} 个")

    print()
    print(f"[*] 需要补充 metadata 条目: {len(to_meta)} 个")
    print(f"[*] metadata 已存在的经典形象: {meta_skip} 个（跳过）")

    if to_meta:
        print()
        print("    metadata 条目数据来源说明（统一格式）：")
        print("    ├─ key/皮肤名/武将名  ← 固定为 经典形象*{name} / 经典形象 / {name}")
        print("    ├─ 皮肤故事           ← characters.json 的「武将故事」")
        print("    ├─ 皮肤台词           ← characters.json 的「版本.经典.武将台词」")
        print("    ├─ 品质               ← 固定为「原画」")
        print("    ├─ 收藏册             ← 固定为「不在收藏册内」")
        print("    ├─ 画师               ← 武将数据中无此字段 → 留空")
        print("    ├─ 皮肤上线时间       ← characters.json 的「武将上线时间」")
        print("    ├─ 静态获取方式       ← 推断为「拥有武将{name}」")
        print("    └─ 语音地址           ← 拼音规则生成 → HEAD 验证 → 通不过则留空")

    if missing_faction:
        print()
        print(f"[!] 以下 {len(missing_faction)} 个文件无法确定势力，已跳过:")
        for fname, name, faction in missing_faction[:10]:
            print(f"    {fname} (势力: {faction})")
        if len(missing_faction) > 10:
            print(f"    ... 共 {len(missing_faction)} 个")

    print()
    total = len(to_copy) + len(to_meta)
    if total == 0:
        print("[*] 全部已同步，无需操作。")
        return

    if not execute:
        print("=" * 60)
        print("预览模式 —— 未执行任何操作。")
        print("确认无误后，添加 --execute 参数运行:")
        print(f"  python {os.path.basename(__file__)} --execute")
        print()
        return

    # 7. 执行
    print("=" * 60)
    print("开始执行...")

    # 7a. 复制图片
    if to_copy:
        print(f"\n[1/2] 复制 {len(to_copy)} 个图片文件...")
        copied = 0
        for fname, name, faction in to_copy:
            src = os.path.join(ARTWORKS_DIR, fname)
            dst_dir = os.path.join(BWIKI_DIR, faction)
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, fname)
            shutil.copy2(src, dst)
            copied += 1
        print(f"  [+] 复制完成: {copied} 个")

    # 7b. 补充 metadata.json（统一格式 {meta, data}）
    if to_meta:
        print(f"\n[2/2] 补充 {len(to_meta)} 条 metadata 条目...")
        added = 0
        for name, char_data in to_meta:
            entry = build_metadata_entry(char_data)
            existing_data.append(entry)
            existing_meta_by_key[entry["key"]] = entry
            added += 1

        out = {
            "meta": {
                "total": len(existing_data),
                "source": "bilibili 三国杀 WIKI",
                "crawl_time": __import__("datetime").datetime.now().isoformat(),
            },
            "data": existing_data,
        }
        with open(METADATA_JSON, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"  [+] 补充完成: {added} 条")

    print()
    print("=" * 60)
    print("全部完成！")
    print()
    print("现在可在 sgs-skin-gallery 项目下运行:")
    print("  npm run scan")
    print("重新生成 skin-data.json 后刷新页面即可看到新增的经典形象。")


if __name__ == "__main__":
    main()
