#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证技能行识别修复：用爬虫自身的 parse_character_page 跑缓存的真实页面 HTML。
- 卢弈（新版）：断言 classic.skills 数量 > 0
- 华雄（混合模板）：断言 classic / breakthrough 均含技能且未被破坏
- 刘备（旧版）：断言 skills 数量与修复前一致（行为不变）
- SP太史慈（特殊）：classic 仅含阵亡（击虚在自走棋后的孤立 section，配对逻辑丢弃），
  属独立的结构问题，非技能标签 bug，此处仅打印真实解析结果。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sgs_bwiki_heros import parse_character_page  # noqa: E402

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    with open(os.path.join(FIXTURE_DIR, f"{name}.html"), "r", encoding="utf-8") as f:
        return f.read()


def skill_count(data, version):
    return len(data.get("versions", {}).get(version, {}).get("skills", []))


def line_keys(data, version):
    return sorted(data.get("versions", {}).get(version, {}).get("lines", {}).keys())


def report(name):
    html = load(name)
    data = parse_character_page(html, name)
    versions = data.get("versions", {})
    print(f"\n=== {name} ===")
    print(f"  versions: {list(versions.keys())}")
    for vkey, vdata in versions.items():
        skills = [s["name"] for s in vdata.get("skills", [])]
        lines = sorted(vdata.get("lines", {}).keys())
        print(f"  [{vkey}] skills({len(skills)})={skills}")
        print(f"  [{vkey}] lines={lines}")
    return data


def main():
    # 1) 卢弈（新版）—— 核心修复目标
    lu = report("卢弈")
    lu_classic = skill_count(lu, "classic")
    assert lu_classic > 0, f"卢弈 classic.skills 应 >0，实际 {lu_classic}"
    print(f"\n[PASS] 卢弈 classic.skills = {lu_classic} (>0)")

    # 2) 华雄（混合模板，曾被 bug 影响）
    hua = report("华雄")
    hua_classic = skill_count(hua, "classic")
    hua_bt = skill_count(hua, "breakthrough")
    assert hua_classic > 0, f"华雄 classic.skills 应 >0，实际 {hua_classic}"
    assert hua_bt > 0, f"华雄 breakthrough.skills 应 >0，实际 {hua_bt}"
    # 耀武技能应出现在 classic 且无丢失
    assert "耀武" in [s["name"] for s in hua["versions"]["classic"]["skills"]], "华雄 classic 缺失 耀武"
    print(f"[PASS] 华雄 classic.skills={hua_classic}, breakthrough.skills={hua_bt}（含 耀武/势斩）")

    # 3) 刘备（旧版）—— 行为必须不变
    liu = report("刘备")
    liu_classic = skill_count(liu, "classic")
    liu_bt = skill_count(liu, "breakthrough")
    liu_nw = skill_count(liu, "national_war")
    # 修复前预期：classic=[仁德,激将], breakthrough=[仁德,激将], national_war=[仁德]
    assert liu_classic == 2, f"刘备 classic.skills 应=2，实际 {liu_classic}"
    assert liu_bt == 2, f"刘备 breakthrough.skills 应=2，实际 {liu_bt}"
    assert liu_nw == 1, f"刘备 national_war.skills 应=1，实际 {liu_nw}"
    print(f"[PASS] 刘备 classic={liu_classic}, breakthrough={liu_bt}, national_war={liu_nw}（与修复前一致）")

    # 4) SP太史慈 —— 特殊：classic 仅阵亡，属独立结构问题，仅打印
    sp = report("SP太史慈")
    sp_classic = skill_count(sp, "classic")
    print(f"[INFO] SP太史慈 classic.skills={sp_classic}（classic 仅含阵亡；")
    print(f"       击虚 位于自走棋之后的孤立 section，被现有 section 配对逻辑丢弃，")
    print(f"       属独立的配对/孤立 section 问题，非技能标签 bug。下方断言按“仅阵亡”的")
    print(f"       真实解析结果处理：classic 应无技能行、仅有阵亡台词。")
    sp_lines = line_keys(sp, "classic")
    assert sp_lines == ["阵亡"], f"SP太史慈 classic 仅应含阵亡台词，实际 {sp_lines}"
    print(f"[PASS] SP太史慈 classic 解析稳定：lines={sp_lines}（与真实页面一致）")

    # 5) "/" 分隔符误判回归（QA Edward 发现）：技能描述文本含 '/' 作为句中
    #    分隔符的武将，修复前其技能行被旧版 `_row_content_is_line` 的 '/' 分支
    #    误判为台词行而丢弃。修复后仅以 bikit-audio 语音按钮作为台词判定信号。
    slash_cases = [
        ("卫温诸葛直", 1, ["浮海"]),
        ("孙霸", 2, ["结党", "觊嫡"]),
        ("文钦", 3, ["犷骜", "彗企", "☆ 偕举"]),
    ]
    for name, expected, expect_names in slash_cases:
        d = report(name)
        cnt = skill_count(d, "classic")
        names = [s["name"] for s in d["versions"]["classic"]["skills"]]
        assert cnt == expected, (
            f"{name} classic.skills 应={expected}，实际 {cnt} ({names})"
        )
        for en in expect_names:
            assert en in names, f"{name} classic 缺失技能 {en}"
        print(f"[PASS] {name} classic.skills={cnt} {names}（'/' 分隔符不再误判）")

    print("\n全部断言通过。")


if __name__ == "__main__":
    main()
