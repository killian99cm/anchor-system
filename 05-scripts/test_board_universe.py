#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板块双宇宙 + 主力资金回归测试（test_board_universe.py · 2026-09-21 新建 · 登记表 §六 #C1-7 / G-3）

**本文件治的是什么**：
    「概念板块主力资金」被登记为长期缺口（G-3），并被写进多份报告的缺口声明表。
    一次外部探查给出的诊断是「本仓代码把 `fs` 写死成 `m:90+t:2`，**从未请求过概念宇宙**」——
    🔴 **该诊断的前半段对、全局断言错**：`board_movers_all()`（v4.5.1 建）**一直双宇宙取数**，
    但它在最后一跳**只把 f12/f14/f3 搬进结果，`f62`（主力资金）被丢弃**。
    ⇒ 真实病灶是**「取了没人接」**，不是「没有源」。若照那份诊断去改 `sector_flow` 的 `fs`，
    会把行业板块的读数换成概念板块的读数 —— **正是它自己警告的那类张冠李戴**。

**测试策略**：全部**离线**（monkeypatch `_board_page`），不联网、不碰生产缓存。
运行: python test_board_universe.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_public as fp


# 夹具体形状**逐字取自真实端点返回**（2026-09-21 实测）：
#   行业宇宙 «半导体 BK1036 −49.78亿» / «有色金属 BK0478 −22.30亿»
#   概念宇宙 «固态电池 BK0968 +1.34亿» / «半导体概念 BK0917 −54.87亿» / «人形机器人 BK1184 +12.61亿»
FAKE = {
    "m:90+t:2": [
        {"f12": "BK1036", "f14": "半导体", "f3": 0.20, "f62": -4978000000.0},
        {"f12": "BK0478", "f14": "有色金属", "f3": 0.96, "f62": -2230000000.0},
        {"f12": "BK1031", "f14": "光伏设备", "f3": 1.17, "f62": 266000000.0},
    ],
    "m:90+t:3": [
        {"f12": "BK0917", "f14": "半导体概念", "f3": 0.87, "f62": -5487411200.0},
        {"f12": "BK0968", "f14": "固态电池", "f3": 0.75, "f62": 134000000.0},
        {"f12": "BK1184", "f14": "人形机器人", "f3": 1.36, "f62": 1261000000.0},
    ],
}


class BoardFixture(unittest.TestCase):
    """把 `_board_page` 换成离线夹具；**不碰生产缓存文件**（换路径隔离，不靠 try/finally）。"""

    def setUp(self):
        self._orig_page = fp._board_page
        self._orig_cache = fp._CACHE
        fp._CACHE = {}                     # 每次用干净缓存，且**不污染**模块既有条目

        def fake_page(fs, pn, source):
            if pn != 1:
                return [], len(FAKE.get(fs, []))
            rows = FAKE.get(fs, [])
            return rows, len(rows)

        fp._board_page = fake_page

    def tearDown(self):
        fp._board_page = self._orig_page
        fp._CACHE = self._orig_cache


class TestBothUniverses(BoardFixture):
    def test_both_universes_are_requested(self):
        """🔴 双宇宙**都必须被请求** —— 治的是「只查 t:2 ⇒ 概念主题永远匹配不到」。"""
        got = fp.board_movers_all()
        self.assertEqual(set(got["universes"]), {"行业板块", "概念板块"})
        self.assertTrue(got["complete"])
        self.assertEqual(got["total_all"], 6)

    def test_concept_theme_is_findable(self):
        """固态电池／人形机器人只存在于**概念**宇宙 —— 单宇宙写法下它们会「不存在」。"""
        by = fp.board_movers_all()["by_name"]
        self.assertIn("固态电池", by)
        self.assertIn("人形机器人", by)
        self.assertEqual(by["固态电池"]["board_type"], "概念板块")


class TestMainCapitalNotDiscarded(BoardFixture):
    """🔴 本节是本次修复的核心：`f62` 已经下载，**不得在最后一跳丢掉**。"""

    def test_concept_board_carries_main_capital(self):
        by = fp.board_movers_all()["by_name"]
        self.assertEqual(by["固态电池"]["net_yi"], 1.34)
        self.assertEqual(by["人形机器人"]["net_yi"], 12.61)
        self.assertEqual(by["半导体概念"]["net_yi"], -54.87)

    def test_industry_board_also_carries_it(self):
        by = fp.board_movers_all()["by_name"]
        self.assertEqual(by["半导体"]["net_yi"], -49.78)
        self.assertEqual(by["有色金属"]["net_yi"], -22.3)

    def test_reverse_old_shape_would_have_no_net_yi(self):
        """🔴 反向断言：证明**修复前**的行里确实没有 `net_yi`。

        旧写法只搬 f12/f14/f3/board_type/fs —— 本项直接复现那个形状，
        断言 `net_yi` 不在其中。若有人把搬运逻辑改回去，本断言仍通过、
        但**上面三条**会立即失败 ⇒ 两者必须同时存在才有意义。
        """
        d = FAKE["m:90+t:3"][1]                       # 固态电池
        old_row = {"code": d["f12"], "name": d["f14"], "chg_pct": d["f3"],
                   "board_type": "概念板块", "fs": "m:90+t:3"}
        self.assertNotIn("net_yi", old_row)           # 旧形状：主力资金**已到手却不在结果里**
        self.assertEqual(d["f62"], 134000000.0)       # 而源数据里它是存在的 ⇒ 是「丢」不是「无」

    def test_none_is_not_coerced_to_zero(self):
        """🔴 无读数必须保持 `None`，⛔ **不得当 0**。

        「该板块无主力资金读数」与「该板块主力资金恰好为 0」是两件事；
        合并后下游无法区分「缺数据」与「真的没资金」（同 #138「拿到一个价 ≠ 拿到收盘价」）。
        """
        orig = fp._board_page

        def fake(fs, pn, source):
            if fs == "m:90+t:3":
                return [{"f12": "BK9999", "f14": "某概念", "f3": 0.1, "f62": "-"}], 1
            return [], 0

        fp._board_page = fake
        fp._CACHE = {}
        try:
            by = fp.board_movers_all()["by_name"]
            self.assertIn("某概念", by)
            self.assertIsNone(by["某概念"]["net_yi"])
            self.assertIsNot(by["某概念"]["net_yi"], 0)
        finally:
            fp._board_page = orig


class TestUniversesAreNotInterchangeable(BoardFixture):
    """🔴 `t:2` 与 `t:3` **互不覆盖** —— 同名不同物是本项最容易新造的张冠李戴。"""

    def test_same_looking_name_is_two_different_rows(self):
        """「半导体」（行业）与「半导体概念」（概念）是**两个不同的东西**，数值不同。"""
        by = fp.board_movers_all()["by_name"]
        self.assertNotEqual(by["半导体"]["net_yi"], by["半导体概念"]["net_yi"])
        self.assertEqual(by["半导体"]["board_type"], "行业板块")
        self.assertEqual(by["半导体概念"]["board_type"], "概念板块")

    def test_reverse_merging_universes_would_lose_one(self):
        """反向：若把两宇宙**合并成一个 dict 而不带 board_type**，同名项会互相覆盖。

        本项证明 `board_type` / `fs` 两个标签**不是装饰** —— 去掉它们，
        「半导体」与「半导体概念」在 by_name 里无法区分，引用时必然张冠李戴。
        """
        rows = fp.board_movers_all()["rows"]
        merged = {r["name"]: r for r in rows}                     # 故意不带 board_type
        with_type = {(r["board_type"], r["name"]): r for r in rows}
        self.assertEqual(len(merged), len(with_type))             # 本夹具恰好无同名
        # 但只要有一个同名项，无标签版就会少一条 —— 直接证明标签的必要性
        self.assertTrue(all("board_type" in r and "fs" in r for r in rows))


if __name__ == "__main__":
    print("=" * 60)
    print("Anchor - Board Universe & Main Capital Test Suite")
    print("=" * 60)
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print()
    print("=" * 60)
    if result.wasSuccessful():
        print("ALL TESTS PASSED")
    else:
        print(f"FAILURES: {len(result.failures)} | ERRORS: {len(result.errors)}")
    print(f"   Ran {result.testsRun} tests")
    print("=" * 60)
    sys.exit(0 if result.wasSuccessful() else 1)
