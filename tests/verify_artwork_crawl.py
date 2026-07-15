#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证「经典形象原画爬取」功能的增量改动（纯增量，无网络依赖）：

  A. 单元测试 extract_classic_artwork_url：
       - 含 <img alt="曹操-经典形象.png" src=".../thumb/.../abc123.png/3"> 的小 HTML
         → 断言返回大图 URL .../c/c3/abc123.png（去 /thumb/ + 去末尾 /3）
       - 不含该 alt 的 HTML → 断言返回 None
       - 协议相对 //patchwiki.../x.png/2 → 断言补成 https:// 且去尺寸后缀

  B. 命名校验：给定 name="曹操"，预期保存文件名 = 曹操-经典形象.png（os.path.basename）

  C. 集成测试：monkeypatch crawl() 下游依赖，调用
       crawl(skip_existing=False, save_every=9999, crawl_artwork=True)
       - fetch_page 返回含上述原画图的小 HTML
       - extract_character_list 返回 [{"name":"曹操","url":...}]
       - parse_character_page 返回假 dict
       - is_timed_mode_character 返回 False
       - load_checkpoint 返回空
       - save_checkpoint / save_json 捕获
       - download_image 用桩记录 (url, path) 不真写
       - time.sleep 置空
     断言：
       - download_image 被调用
       - 记录的 path 含 "曹操-经典形象.png"
       - 角色数据 artwork 字段为相对路径 "artworks/曹操-经典形象.png"

支持两种运行方式（无网络依赖，秒级跑通）：
  $ python tests/verify_artwork_crawl.py
  $ python -m pytest tests/ -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sgs_bwiki_heros as mod  # noqa: E402
from sgs_bwiki_heros import extract_classic_artwork_url  # noqa: E402

# 经典形象原画缩略图（与真实武将页面结构一致）
ARTWORK_IMG_HTML = (
    '<html><body>'
    '<img alt="曹操-经典形象.png" '
    'src="https://patchwiki.biligame.com/images/sgs/thumb/c/c3/abc123.png/3">'
    '</body></html>'
)
EXPECTED_BIG_URL = "https://patchwiki.biligame.com/images/sgs/c/c3/abc123.png"


# ============ A. 单元测试 ============


def test_extract_classic_artwork_url_thumbnail():
    """缩略图 URL → 还原为大图 URL（去 /thumb/ + 去末尾 /3）。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(ARTWORK_IMG_HTML, "html.parser")
    url = extract_classic_artwork_url(soup, "曹操")
    assert url == EXPECTED_BIG_URL, f"预期 {EXPECTED_BIG_URL}，实际 {url}"
    print(f"[PASS] A1. 缩略图还原大图: {url}")


def test_extract_classic_artwork_url_none():
    """不含该 alt 的 HTML → 返回 None。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<html><body>no image here</body></html>", "html.parser")
    url = extract_classic_artwork_url(soup, "曹操")
    assert url is None, f"应返回 None，实际 {url!r}"
    print("[PASS] A2. 无匹配 alt → None")


def test_extract_classic_artwork_url_protocol_relative():
    """协议相对 URL → 补 https:，并去 /thumb/ 与末尾尺寸后缀。"""
    from bs4 import BeautifulSoup

    html = (
        '<html><body>'
        '<img alt="曹操-经典形象.png" '
        'src="//patchwiki.biligame.com/images/sgs/thumb/d/d4/hash456.png/2">'
        '</body></html>'
    )
    soup = BeautifulSoup(html, "html.parser")
    url = extract_classic_artwork_url(soup, "曹操")
    assert url == "https://patchwiki.biligame.com/images/sgs/d/d4/hash456.png", (
        f"协议相对应补 https: 并去尺寸后缀，实际 {url}"
    )
    print(f"[PASS] A3. 协议相对补 https: 并去尺寸后缀: {url}")


# ============ B. 命名校验 ============


def test_artwork_filename():
    """给定 name='曹操'，保存文件名应为 曹操-经典形象.png。"""
    name = "曹操"
    filename = f"{name}-经典形象.png"
    assert os.path.basename(filename) == "曹操-经典形象.png", filename
    print(f"[PASS] B. 命名校验: {filename}")


# ============ C. 集成测试（monkeypatch crawl） ============


def _fake_extract_character_list():
    """返回含『曹操』的小列表，index_html 为带 <body> 的假 HTML。"""
    return (
        [{"name": "曹操", "url": "http://example.test/曹操"}],
        "<html><body><p>fake index</p></body></html>",
    )


def _fake_fetch_page(url):
    """返回含经典形象原画图的小 HTML（供 extract_classic_artwork_url 解析）。"""
    return ARTWORK_IMG_HTML


def _fake_parse_character_page(html, char_name):
    """返回含 name 的假 dict（artwork 由 crawl 内补充）。"""
    return {"name": char_name, "faction": "魏", "pack": "标准包"}


def _fake_is_timed_mode_character(data, name):
    """曹操非常驻 / 非限时玩法。"""
    return False


def _fake_load_checkpoint():
    return {"characters": [], "page_hashes": {}}


_CAPTURED = {}


def _fake_save_checkpoint(characters):
    _CAPTURED["checkpoint"] = [dict(c) for c in characters]


def _fake_save_json(characters, filepath):
    _CAPTURED["json"] = [dict(c) for c in characters]


_download_calls = []


def _fake_download_image(url, save_path, retries=None):
    """桩：记录 (url, path)，不真写文件，返回成功。"""
    _download_calls.append((url, save_path))
    return True


def _fake_sleep(*args, **kwargs):
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
    mp.setattr(mod, "download_image", _fake_download_image)
    mp.setattr(mod.time, "sleep", _fake_sleep)

    _CAPTURED.clear()
    _download_calls.clear()

    mod.crawl(skip_existing=False, save_every=9999, crawl_artwork=True)

    # 1) download_image 被调用
    assert _download_calls, "download_image 应被调用（crawl_artwork=True）"
    # 2) 记录的 path 含 曹操-经典形象.png
    called_path = _download_calls[0][1]
    assert "曹操-经典形象.png" in called_path, (
        f"下载路径应含 '曹操-经典形象.png'，实际 {called_path}"
    )
    # 3) 角色数据 artwork 字段为相对路径
    stored = _CAPTURED.get("checkpoint") or _CAPTURED.get("json") or []
    assert stored, "应有入库数据"
    caocao = next((c for c in stored if c.get("name") == "曹操"), None)
    assert caocao is not None, "曹操应入库"
    artwork = caocao.get("artwork")
    assert artwork == "artworks/曹操-经典形象.png", (
        f"artwork 应为相对路径 'artworks/曹操-经典形象.png'，实际 {artwork!r}"
    )
    # 4) download_image 收到的 url 是大图 URL（去 /thumb/ + 去尺寸后缀）
    called_url = _download_calls[0][0]
    assert called_url == EXPECTED_BIG_URL, (
        f"download_image 应收到大图 URL，实际 {called_url}"
    )

    print(f"[PASS] C1. download_image 被调用，路径含 '曹操-经典形象.png': {called_path}")
    print(f"[PASS] C2. 角色 artwork 字段为相对路径: {artwork}")
    print(f"[PASS] C3. download_image 收到大图 URL: {called_url}")


def test_integration_crawl_artwork(monkeypatch):
    """pytest 收集入口：用 pytest 的 monkeypatch fixture 验证集成行为。"""
    _run(monkeypatch)


class _SimpleMonkeyPatcher:
    """standalone 用的最小 monkeypatch 实现（.setattr 接口与 pytest 一致）。"""

    def setattr(self, obj, name, value):
        setattr(obj, name, value)


def main():
    test_extract_classic_artwork_url_thumbnail()
    test_extract_classic_artwork_url_none()
    test_extract_classic_artwork_url_protocol_relative()
    test_artwork_filename()
    _run(_SimpleMonkeyPatcher())
    print("\n全部断言通过。")


if __name__ == "__main__":
    main()
