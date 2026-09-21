#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南向资金「合计可信性」回归测试（test_southbound.py · 2026-09-21 新建 · v4.5.11）

**本文件治的是什么**：
    `southbound()` 原写法把沪(002)/深(004)两腿收进 `per_type`，失败时 `continue`，
    **只在「两腿全挂」时才失败**。单腿挂时：
        `dates` 只剩一个集合 ⇒ `set.intersection(*dates)` **恒成功**
        ⇒ `date` 取该腿自身日期、`total` 只剩该腿，**却照旧返回 `ok: True`**。
    实测影响（2026-09-18 真值：沪 17.01 ＋ 深 1176.26 ＝ **1193.27** 百万港元）：
        **深腿若挂即报 17.01（0.17 亿）而非 11.93 亿 —— 偏低 98.6%**，
        且 `ok=True`、探针日志干净、量级看起来仍正常。

**修法（本文件所测的）**：
    该报表每日实为 **6 行**：`002/004/006` 南向族、`001/003/005` 北向族，
    其中 **`006` 是官方合计行**（四项指标与 002+004 逐位相等，已实测）。
    ⇒ 改为**一次请求取回全部类型**，`total` **直取 `006`**，⛔ 不再自己相加。

**测试策略**：全部**离线**（monkeypatch `_http`），不联网、不碰生产缓存。
运行: python test_southbound.py
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_public as fp


def _r(mt, net, buy=None, sell=None, num=None, idx=24750.78):
    return {"MUTUAL_TYPE": mt, "TRADE_DATE": "2026-09-18 00:00:00",
            "NET_DEAL_AMT": net, "BUY_AMT": buy, "SELL_AMT": sell,
            "DEAL_NUM": num, "INDEX_CLOSE_PRICE": idx}


# 2026-09-18 真实读数（百万港元）：沪 17.01 / 深 1176.26 / 合计 1193.27
ROW_SH = _r("002", 17.01, 30350.58, 30333.57, 1264272)
ROW_SZ = _r("004", 1176.26, 21844.56, 20668.30, 839980)
ROW_TOTAL = _r("006", 1193.27, 52195.14, 51001.87, 2104252)
# 北向族：财务字段全 None，INDEX 是 A 股指数（用它证明「分桶」不是靠猜）
ROW_NORTH = _r("005", None, None, None, 14221084, idx=3911.87)
TRUE_TOTAL = 1193.27


def _resp(rows, north=True):
    data = list(rows) + ([ROW_NORTH] if north else [])
    return json.dumps({"result": {"data": data}})


class SbFixture(unittest.TestCase):
    """把 `_http` 换成离线夹具；每次用干净缓存，**不碰生产文件**（J11 之理）。"""

    def setUp(self):
        self._orig_http = fp._http
        self._orig_cache = fp._CACHE
        self._orig_record = fp._record
        fp._CACHE = {}
        fp._record = lambda *a, **k: None

    def tearDown(self):
        fp._http = self._orig_http
        fp._CACHE = self._orig_cache
        fp._record = self._orig_record

    def serve(self, body, rc=200):
        fp._http = lambda url, referer, timeout, encoding: (rc, body)


class TestComplete(SbFixture):
    def test_total_row_is_used_and_cross_check_passes(self):
        self.serve(_resp([ROW_SH, ROW_SZ, ROW_TOTAL]))
        r = fp.southbound()
        self.assertTrue(r["ok"])
        self.assertTrue(r["complete"])
        self.assertTrue(r["legs_complete"])
        self.assertTrue(r["has_total_row"])
        self.assertIn("006", r["total_basis"])
        self.assertAlmostEqual(r["total_mhkd"], TRUE_TOTAL, places=2)
        self.assertEqual(r["date"], "2026-09-18")
        self.assertTrue(r["cross_check"]["match"])
        self.assertEqual(len(r["detail"]), 2, "detail 只保留分腿，不含合计行（否则与合计行重复渲染）")

    def test_northbound_rows_are_ignored(self):
        """北向族（005）必须被分桶丢弃，不得混进南向合计 —— 这是「张冠李戴」防线。"""
        self.serve(_resp([ROW_SH, ROW_SZ, ROW_TOTAL]))
        r = fp.southbound()
        self.assertEqual(r["legs_found"], 2)
        self.assertNotIn("005", [d["type"] for d in r["detail"]])


class TestLegMissing(SbFixture):
    """🔴 本节是本次修复的核心：**缺腿时合计仍可信**（因为直取 006，不靠相加）。"""

    def test_missing_leg_keeps_total_correct(self):
        self.serve(_resp([ROW_SH, ROW_TOTAL]))                    # 深腿挂，合计行在
        r = fp.southbound()
        self.assertTrue(r["complete"], "有合计行 ⇒ 合计可信")
        self.assertFalse(r["legs_complete"], "但分腿不齐必须标出")
        self.assertEqual(r["missing_legs"], ["004 港股通(深)"])
        self.assertAlmostEqual(r["total_mhkd"], TRUE_TOTAL, places=2,
                               msg="缺腿时合计仍须等于真值 —— 这正是改取 006 的意义")

    def test_missing_leg_without_total_row_is_not_claimed_complete(self):
        self.serve(_resp([ROW_SH]))                               # 只有沪腿，也无合计行
        r = fp.southbound()
        self.assertFalse(r["complete"], "凑不出可信合计时必须为 False")
        self.assertIsNone(r["total_mhkd"], "⛔ 不得把单腿值当合计报出")
        self.assertIsNone(r["total_basis"])

    def test_missing_total_row_falls_back_to_leg_sum_with_disclosed_basis(self):
        self.serve(_resp([ROW_SH, ROW_SZ]))                       # 有腿无合计行
        r = fp.southbound()
        self.assertTrue(r["complete"])
        self.assertFalse(r["has_total_row"])
        self.assertIn("求和", r["total_basis"], "降级必须**显式记下依据**，不得静默")
        self.assertAlmostEqual(r["total_mhkd"], TRUE_TOTAL, places=2)
        self.assertIsNone(r["cross_check"], "无合计行时无从交叉校验 ⇒ 须为 None，不得伪造 True")


class TestReverseAssertions(SbFixture):
    """🔴 反向断言：证明**修复前的写法确实会错**，否则测试可能在假阳性下通过。"""

    def test_reverse_old_logic_would_report_a_98pct_low_total(self):
        """复现**修复前**的判定：单腿在场时旧护栏放行，total 只剩该腿。"""
        per_type = {"002": {"label": "港股通(沪)", "rows": [ROW_SH]}}
        old_guard_blocks = (not per_type)                  # 旧护栏：只拦「两腿全挂」
        self.assertFalse(old_guard_blocks, "单腿在场时旧护栏不拦 ⇒ 旧代码会返回 ok=True")

        dates = [{x["TRADE_DATE"][:10] for x in v["rows"]} for v in per_type.values()]
        common = sorted(set.intersection(*dates), reverse=True) if dates else []
        self.assertEqual(common, ["2026-09-18"],
                         "对单个集合求交恒成功 —— 这正是旧写法产生「合法」日期的机制")

        old_total = sum(x["NET_DEAL_AMT"] for v in per_type.values()
                        for x in v["rows"] if x["TRADE_DATE"][:10] == common[0])
        self.assertAlmostEqual(old_total, 17.01, places=2)
        err = abs(old_total - TRUE_TOTAL) / TRUE_TOTAL
        self.assertGreater(err, 0.98, "旧写法在深腿挂时报出的数必须与真值差 >98%")

    def test_reverse_wrong_total_row_is_caught_not_trusted(self):
        """反向断言：即使 006 在场，**它和分腿对不上时也必须报错**而非照抄。

        这条同时是「东财若改动 `006` 编号含义」的探测器 —— 那时算术恒等式会破。
        """
        bad = _r("006", 999.99, 52195.14, 51001.87, 2104252)
        self.serve(_resp([ROW_SH, ROW_SZ, bad]))
        r = fp.southbound()
        self.assertFalse(r["cross_check"]["match"], "合计行与分腿不符必须标为不匹配")
        self.assertAlmostEqual(r["cross_check"]["legs_sum"], TRUE_TOTAL, places=2)
        self.assertAlmostEqual(r["total_mhkd"], 999.99, places=2,
                               msg="仍以官方合计行为准，但 cross_check 已标红供人复核")


class TestFailureModes(SbFixture):
    def test_http_error_is_loud(self):
        self.serve("boom", rc=500)
        r = fp.southbound()
        self.assertFalse(r["ok"])
        self.assertIn("rc=500", r["note"])

    def test_zero_rows_is_loud(self):
        self.serve(_resp([], north=False))
        r = fp.southbound()
        self.assertFalse(r["ok"])
        self.assertIn("0 行", r["note"])

    def test_non_json_is_loud(self):
        self.serve("<html>not json</html>")
        r = fp.southbound()
        self.assertFalse(r["ok"])
        self.assertIn("非 JSON", r["note"])


if __name__ == "__main__":
    print("=" * 60)
    print("Anchor - Southbound Completeness Test Suite")
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
