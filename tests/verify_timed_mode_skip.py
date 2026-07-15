#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证限时玩法（限时地主 / 喵喵杀）排除逻辑的两层改动：

  A. section 级跳过（parse_character_page 内「最近前置 h2 配对」）
     加载合成 fixture（tests/fixtures/限时模式页面.html），其 DOM 顺序为：
       经典版本(真实技能) → 限时地主(限时技能) → 界限突破版本(正常技能) → 喵喵杀(限时技能)
     断言解析后：
       - versions 含 classic 技能（耀武，取自真实 DOM 复刻）
       - versions 含 breakthrough 技能（势斩，未被 限时地主 错位吞掉）
       - 任何版本都不含 限时地主/喵喵杀 技能（天降/喵喵叫 被整块跳过）

  B. 武将级跳过（crawl 中整将不入库）
     直接测 is_timed_mode_character 谓词：
       - pack == "限时地主" / "喵喵杀" → True（整将跳过）
       - 名字含「（限时地主）」/「（喵喵杀）」标记（冗余保险）→ True
       - 常驻武将（含普通 pack / 无标记）→ False（不误杀）

 说明：tests/fixtures/限时模式页面.html 为「合成 fixture」—— 从真实页面 DOM 结构
 复刻 经典版本 section，并补入 限时地主 / 喵喵杀 h2 与对应 skill section，用于稳定
 回归、避免被线上限流(567)拖住（符合「优先手工 fixture」要求）。若日后抓到真实页
 tests/fixtures/吴懿（限时地主）.html，test_pack_skip_real_fixture 会自动用其验证 B。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sgs_bwiki_heros import parse_character_page, is_timed_mode_character  # noqa: E402

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SYNTHETIC_FIXTURE = "限时模式页面"  # 合成 fixture（非真实页）


def load(name):
    with open(os.path.join(FIXTURE_DIR, f"{name}.html"), "r", encoding="utf-8") as f:
        return f.read()


def all_skill_names(data):
    """汇总所有版本下的技能名，便于断言限时玩法技能未入库。"""
    names = set()
    for vdata in data.get("versions", {}).values():
        for s in vdata.get("skills", []):
            names.add(s["name"])
    return names


def test_section_skip():
    """A. section 级：限时地主/喵喵杀 区块被整块跳过，经典/界限突破照常。"""
    html = load(SYNTHETIC_FIXTURE)
    data = parse_character_page(html, "测试武将（合成）")
    versions = data.get("versions", {})

    print("\n=== 合成 fixture 解析结果（section 级跳过）===")
    print(f"  versions: {list(versions.keys())}")
    for vkey, vdata in versions.items():
        print(f"  [{vkey}] skills={[s['name'] for s in vdata.get('skills', [])]}")

    # classic 必须含真实技能（取自真实 DOM 复刻）
    assert "classic" in versions, "应解析出经典版本 classic"
    classic_skills = [s["name"] for s in versions["classic"].get("skills", [])]
    assert "耀武" in classic_skills, f"classic 应含 耀武，实际 {classic_skills}"

    # 界限突破应照常解析（这是本次修复的核心：限时地主 夹在中间曾错位吞掉它）
    assert "breakthrough" in versions, "界限突破版本 应正常解析"
    bt_skills = [s["name"] for s in versions["breakthrough"].get("skills", [])]
    assert "势斩" in bt_skills, f"breakthrough 应含 势斩（未被限时地主错位），实际 {bt_skills}"

    # 限时玩法技能不得出现在任何版本
    all_names = all_skill_names(data)
    assert "天降" not in all_names, "限时地主 技能『天降』不应被解析入库"
    assert "喵喵叫" not in all_names, "喵喵杀 技能『喵喵叫』不应被解析入库"

    print("[PASS] A. section 级跳过：经典/界限突破正常，限时地主/喵喵杀 技能均未入库")


def test_pack_skip_predicate():
    """B. 武将级：pack 过滤谓词正确识别限时玩法武将，不误杀常驻武将。"""
    # pack 直接命中
    assert is_timed_mode_character({"pack": "限时地主"}, "吴懿（限时地主）") is True
    assert is_timed_mode_character({"pack": "喵喵杀"}, "可爱之神") is True
    # 名字含限时标记（冗余保险），即使 pack 缺失
    assert is_timed_mode_character({"pack": ""}, "SP蒲元（限时地主）") is True
    assert is_timed_mode_character({"pack": ""}, "某神（喵喵杀）") is True
    # 常驻武将不被误杀
    assert is_timed_mode_character({"pack": "标准-勇冠三军"}, "华雄") is False
    assert is_timed_mode_character({"pack": "神话再临-风包"}, "张角") is False
    assert is_timed_mode_character({"pack": ""}, "典韦") is False
    print("[PASS] B. 武将级 pack 过滤谓词：正确识别限时玩法武将，不误杀常驻武将")


def test_pack_skip_real_fixture():
    """B(可选). 若有真实 吴懿（限时地主） fixture，验证其 pack 命中且会被跳过。"""
    real_path = os.path.join(FIXTURE_DIR, "吴懿（限时地主）.html")
    if not os.path.exists(real_path):
        print("[SKIP] 真实 fixture tests/fixtures/吴懿（限时地主）.html 不存在，跳过真实页验证")
        return
    html = load("吴懿（限时地主）")
    data = parse_character_page(html, "吴懿（限时地主）")
    assert data.get("pack") in ("限时地主", "喵喵杀"), (
        f"pack 应命中限时玩法，实际 {data.get('pack')}"
    )
    assert is_timed_mode_character(data, "吴懿（限时地主）") is True, (
        "该武将应被判为限时玩法（crawl 会整将跳过）"
    )
    print("[PASS] B(真实页) 吴懿（限时地主）pack 命中，crawl 会整将跳过")


def main():
    test_section_skip()
    test_pack_skip_predicate()
    test_pack_skip_real_fixture()
    print("\n全部断言通过。")


if __name__ == "__main__":
    main()
