#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证「限时玩法武将跳过」日志行为的最小改动（纯日志，不动业务逻辑）：

  改动前：crawl() 在跳过限时玩法武将会单独 print 一行
          print(f"  [skip] 限时玩法武将，跳过: {name}")
          该 print 会打断 tqdm 进度条连续性。
  改动后：
    1) 该 print 被移除；
    2) 新增 skip_count 计数器，并在进度条 set_postfix(...) 中增加
       skip=skip_count 字段（与 success / fail / current 并列）。

本测试不依赖网络，全部依赖项用 monkeypatch 替换：

  - extract_character_list：返回含几个「限时玩法」名字与一个普通名字的小列表。
  - fetch_page：返回一段非空假 HTML 字符串。
  - parse_character_page：返回含 name/faction/pack 的假 dict。
  - is_timed_mode_character：按名字判定（限时玩法名字 -> True，其余 False）。
  - load_checkpoint：返回 {"characters":[], "page_hashes":{}}。
  - save_checkpoint / save_json：留空实现，捕获传入的 characters 列表。
  - time.sleep：置为空操作以加速。

断言：
  a) 捕获的 stdout 中**不含** "[skip]"（不再单独打印跳过行）；
  b) 传给 save_checkpoint 的 characters 列表中**不含**限时玩法名字，但**包含**普通名字；
  c) 列表长度 == 普通名字数量（skip 不入库、success 计数正确）。

支持两种运行方式（无网络依赖，秒级跑通）：
  $ python tests/verify_skip_log.py
  $ python -m pytest tests/ -q
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sgs_bwiki_heros as mod  # noqa: E402

# 限时玩法名字（crawl 应整将跳过、不入库、不打印 [skip]）
TIMED_NAMES = ["SP蒲元", "东海龙王"]
# 普通名字（应正常入库）
NORMAL_NAMES = ["曹操", "刘备"]


def _fake_extract_character_list():
    """返回含限时玩法与普通名字的小列表，元素为 {"name":..., "url":...}。

    第二个返回值 index_html 为带 <body> 的假 HTML，使 crawl 内
    extract_pack_structure(index_html) 能安全返回 {}（无 wikitable），
    避免干扰本日志行为测试。
    """
    names = list(TIMED_NAMES) + list(NORMAL_NAMES)
    return (
        [{"name": n, "url": f"http://example.test/{n}"} for n in names],
        "<html><body><p>fake index page</p></body></html>",
    )


def _fake_fetch_page(url):
    """返回一段非空假 HTML 字符串（不必可解析，parse 由 monkeypatch 接管）。"""
    return "<html><body>fake page for %s</body></html>" % url


def _fake_parse_character_page(html, char_name):
    """返回含 name/faction/pack 的假 dict。"""
    return {"name": char_name, "faction": "魏", "pack": "标准包"}


def _fake_is_timed_mode_character(data, name):
    """按名字判定：限时玩法名字返回 True，其余 False。"""
    return name in set(TIMED_NAMES)


def _fake_load_checkpoint():
    """返回空检查点（不依赖磁盘）。"""
    return {"characters": [], "page_hashes": {}}


_CAPTURED = {}


def _fake_save_checkpoint(characters):
    """留空实现，捕获传入的 characters 列表。"""
    _CAPTURED["checkpoint"] = [dict(c) for c in characters]


def _fake_save_json(characters, filepath):
    """留空实现，捕获传入的 characters 列表。"""
    _CAPTURED["json"] = [dict(c) for c in characters]


def _fake_sleep(*args, **kwargs):
    """空操作，加速测试。"""
    return None


def _run(mp):
    """执行 monkeypatch + crawl 调用 + 断言。mp 需提供 .setattr(obj, name, value)。"""
    mp.setattr(mod, "extract_character_list", _fake_extract_character_list)
    mp.setattr(mod, "fetch_page", _fake_fetch_page)
    mp.setattr(mod, "parse_character_page", _fake_parse_character_page)
    mp.setattr(mod, "is_timed_mode_character", _fake_is_timed_mode_character)
    mp.setattr(mod, "load_checkpoint", _fake_load_checkpoint)
    mp.setattr(mod, "save_checkpoint", _fake_save_checkpoint)
    mp.setattr(mod, "save_json", _fake_save_json)
    mp.setattr(mod.time, "sleep", _fake_sleep)

    _CAPTURED.clear()

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mod.crawl(skip_existing=False, save_every=9999)
    out = buf.getvalue()

    # a) 不再单独打印跳过行
    assert "[skip]" not in out, (
        f"捕获的 stdout 不应包含 '[skip]'，实际包含：{out!r}"
    )

    # b/c) 入库列表不含限时玩法名字、含普通名字，长度 == 普通名字数量
    checkpoint = _CAPTURED.get("checkpoint", [])
    stored_names = {c["name"] for c in checkpoint}

    for tname in TIMED_NAMES:
        assert tname not in stored_names, (
            f"限时玩法武将 {tname} 不应入库，实际入库列表：{stored_names}"
        )
    for nname in NORMAL_NAMES:
        assert nname in stored_names, (
            f"普通武将 {nname} 应入库，实际入库列表：{stored_names}"
        )
    assert len(checkpoint) == len(NORMAL_NAMES), (
        f"入库数量应 == 普通名字数量({len(NORMAL_NAMES)})，"
        f"实际 {len(checkpoint)}：{stored_names}"
    )

    print("[PASS] a. stdout 不含 '[skip]'（不再单独打印跳过行）")
    print(f"[PASS] b. 入库列表不含限时玩法名字，含普通名字：{sorted(stored_names)}")
    print(f"[PASS] c. 入库数量 == 普通名字数量：{len(checkpoint)}")


def test_skip_log_no_print_and_not_stored(monkeypatch):
    """pytest 收集入口：用 pytest 的 monkeypatch fixture 验证新行为。"""
    _run(monkeypatch)


class _SimpleMonkeyPatcher:
    """standalone 用的最小 monkeypatch 实现（.setattr 接口与 pytest 一致）。"""

    def setattr(self, obj, name, value):
        setattr(obj, name, value)


def main():
    _run(_SimpleMonkeyPatcher())
    print("\n全部断言通过。")


if __name__ == "__main__":
    main()
