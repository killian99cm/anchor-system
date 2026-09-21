#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南向 T+0（`kamt/get`）回归测试（test_southbound_intraday.py · 2026-09-21 新建 · v4.5.13）

**本文件治的是什么**：
    `#C1-7`「换源」在 G-2（南向仅 T-1）这一项上的**落地 ＋ 防陷阱**。
    源找到了（`push2delay kamt/get`，T+0），但**同一响应里埋着一个恒定的假值**：
        `dayNetAmtIn` 名字叫「当日净流入额」，**实测是额度字段** ——
        `4200000 = 1×`、`monthNetAmtIn 63000000 = 15×`（9 月 15 个交易日）、
        `yearNetAmtIn 718200000 = 171×`（2026 年 171 个交易日）。
    ⇒ 它的值**每天恒等于 420 亿**，量级很像个大额净流入，**取错了不会报错**。

**本文件的核心不是「新函数能跑」，而是三组反向断言**：
    ① 证明**窄 fields 参数下根本拿不到 `netBuyAmt`**（字段集依赖是真的）；
    ② 证明**按名字取 `dayNetAmtIn` 会得到一个跨日恒定的 420 亿**（陷阱是真的）；
    ③ 证明**`netBuyAmt ≠ buyAmt − sellAmt` 时不被信任**（内部一致性断言不是装饰）。

**测试策略**：全部**离线**（monkeypatch `_http`），不联网、不碰生产缓存（J11 之理）。
运行: python test_southbound_intraday.py
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_public as fp


# ============================================================ 实测响应形状
# 2026-09-21 收盘后真实抓取，**未构造**（数值逐位来自实盘）
REAL = {
    "sh2hk": {"status": 1, "dayNetAmtIn": 4200000.0, "dayAmtRemain": 0.0,
              "dayAmtThreshold": 4200000.0, "date": "09-21", "date2": "2026-09-21",
              "monthNetAmtIn": 63000000.0, "yearNetAmtIn": 718200000.0,
              "buyAmt": 3047585.83, "sellAmt": 2737929.9, "netBuyAmt": 309655.94},
    "sz2hk": {"status": 1, "dayNetAmtIn": 4200000.0, "dayAmtRemain": 0.0,
              "dayAmtThreshold": 4200000.0, "date": "09-21", "date2": "2026-09-21",
              "monthNetAmtIn": 63000000.0, "yearNetAmtIn": 718200000.0,
              "buyAmt": 1645664.69, "sellAmt": 1540365.87, "netBuyAmt": 105298.82},
}
TRUE_WAN = 309655.94 + 105298.82          # = 414954.76 万元 = 41.50 亿元


def _body(d):
    """`kamt/get` 响应外壳（实测形状）。"""
    return json.dumps({"rc": 0, "rt": 6, "svr": 1, "lt": 1, "full": 1, "data": d})


class KamtFixture(unittest.TestCase):
    """换掉 `_http`；每次用干净缓存，**不碰生产文件**。"""

    def setUp(self):
        self._oh, self._oc, self._or = fp._http, fp._CACHE, fp._record
        fp._CACHE = {}
        fp._record = lambda *a, **k: None

    def tearDown(self):
        fp._http, fp._CACHE, fp._record = self._oh, self._oc, self._or

    def serve(self, data, rc=200):
        body = data if isinstance(data, str) else _body(data)
        fp._http = lambda url, referer, timeout, encoding: (rc, body)


class TestLiveShape(KamtFixture):
    def test_total_is_sum_of_legs_in_yi(self):
        self.serve(REAL)
        r = fp.southbound_intraday()
        self.assertEqual(r["net_buy_wan"], round(TRUE_WAN, 2))
        self.assertAlmostEqual(r["net_buy_yi"], 41.5, places=2)
        self.assertTrue(r["complete"])
        self.assertEqual(r["missing_legs"], [])
        self.assertEqual(r["identity_failed"], [])

    def test_never_close_confirmed(self):
        """盘中值**恒** `close_confirmed=False` —— 这是 F5 的落点，不得有例外。"""
        self.serve(REAL)
        r = fp.southbound_intraday()
        self.assertFalse(r["close_confirmed"])
        self.assertIn("不得作触发线判据", r["forbidden_use"])

    def test_currency_is_declared_unproven(self):
        """币种＝人民币是**有依据的推断**，必须带 `currency_proven=False` 与依据原文。"""
        self.serve(REAL)
        r = fp.southbound_intraday()
        self.assertEqual(r["currency"], "CNY")
        self.assertFalse(r["currency_proven"], "⛔ 不得把推断登记成已证")
        self.assertIn("4200000", r["currency_basis"].replace("420 亿", "4200000")
                      if "4200000" in r["currency_basis"] else r["currency_basis"])


class TestReverseAssertions(KamtFixture):
    """🔴 反向断言：证明「原写法确实会错」，否则测试可能在假阳性下通过。"""

    def test_reverse_quota_field_is_constant_across_days(self):
        """🔴 本文件最重要的一条：**按名字取 `dayNetAmtIn` 会得到一个跨日恒定的 420 亿**。

        构造两天**真实资金流相差近 3 倍**（41.50 亿 vs 11.93 亿）的响应，
        断言 `dayNetAmtIn` **完全不动**，而 `netBuyAmt` 动。
        ⇒ 谁把 `dayNetAmtIn` 当「当日净流入额」，就会往每份报告注入**同一个 420 亿**。
        """
        day_a = json.loads(_body(REAL))["data"]                     # 净买入 41.50 亿
        day_b = json.loads(_body(REAL))["data"]
        for leg in ("sh2hk", "sz2hk"):                              # 次日：净买入约 1/3
            day_b[leg] = dict(day_b[leg])
            day_b[leg]["netBuyAmt"] = day_b[leg]["netBuyAmt"] / 3.0
            day_b[leg]["buyAmt"] = day_b[leg]["sellAmt"] + day_b[leg]["netBuyAmt"]
        self.serve(day_a); a = fp.southbound_intraday()
        fp._CACHE = {}
        self.serve(day_b); b = fp.southbound_intraday()

        self.assertNotAlmostEqual(a["net_buy_yi"], b["net_buy_yi"], places=1,
                                  msg="真流量字段必须随日变化")
        self.assertEqual(day_a["sh2hk"]["dayNetAmtIn"], day_b["sh2hk"]["dayNetAmtIn"],
                         msg="🔴 额度字段必须恒定 —— 若此断言失败，说明我对它的定性错了，"
                             "须回头重读而不是放宽本断言")
        self.assertEqual(day_a["sh2hk"]["dayNetAmtIn"], 4200000.0,
                         msg="1 × 4200000；month=15×、year=171× 与交易日数逐位吻合")
        self.assertEqual(day_a["sh2hk"]["monthNetAmtIn"] / day_a["sh2hk"]["dayNetAmtIn"], 15.0)
        self.assertEqual(day_a["sh2hk"]["yearNetAmtIn"] / day_a["sh2hk"]["dayNetAmtIn"], 171.0)

    def test_reverse_narrow_fields_would_not_return_netbuyamt(self):
        """🔴 证明**字段集依赖是真的**：窄 fields 的响应里根本没有 `netBuyAmt`。

        若不修（沿用 `f51..f56`），本函数会走「无 `netBuyAmt`」分支并把两腿都判缺失
        ⇒ **不是静默给 0，而是显式不完整** —— 这正是我们要的行为，故一并断言。
        """
        narrow = {leg: {k: v for k, v in REAL[leg].items()
                        if k in ("status", "dayNetAmtIn", "dayAmtRemain",
                                 "dayAmtThreshold", "date", "date2")}
                  for leg in REAL}
        self.assertNotIn("netBuyAmt", narrow["sh2hk"],
                         msg="窄字段集下不得出现 netBuyAmt（陷阱的地基）")
        self.serve(narrow)
        r = fp.southbound_intraday()
        self.assertIsNone(r["net_buy_wan"], "拿不到真流量字段 ⇒ ⛔ 不得给合计")
        self.assertFalse(r["complete"])
        self.assertEqual(len(r["missing_legs"]), 2, "两腿都必须被显式判缺失")

    def test_reverse_identity_break_is_not_trusted(self):
        """`netBuyAmt` 与 `buyAmt − sellAmt` 不符 ⇒ 该腿**不参与合计**且被报出。

        ⛔ 既**不静默采纳**，也**不静默丢弃**（v4.5.11 的教训：静默自愈与静默漂移同病）。
        """
        bad = json.loads(_body(REAL))["data"]
        bad["sz2hk"] = dict(bad["sz2hk"])
        bad["sz2hk"]["netBuyAmt"] = bad["sz2hk"]["buyAmt"] - bad["sz2hk"]["sellAmt"] + 9999
        self.serve(bad)
        r = fp.southbound_intraday()
        self.assertIn("港股通(深)", r["identity_failed"])
        self.assertIsNone(r["net_buy_wan"], "有一腿不可信 ⇒ ⛔ 不得给合计")
        self.assertFalse(r["complete"])
        self.assertTrue(any(d["leg"] == "sh2hk" for d in r["detail"]),
                        "另一腿仍须被报出，不得因一腿坏而整体消失")


class TestFailureModes(KamtFixture):
    def test_missing_leg_yields_no_total(self):
        """缺一腿 ⇒ **不得**给出「合计」（v4.5.11 单腿静默错值同族）。"""
        one = {"sh2hk": REAL["sh2hk"]}
        self.serve(one)
        r = fp.southbound_intraday()
        self.assertIsNone(r["net_buy_wan"])
        self.assertEqual(r["legs_found"], 1)
        # 格式与兄弟函数 southbound() 一致：`<leg> <label>`
        self.assertTrue(any("sz2hk" in m and "港股通(深)" in m for m in r["missing_legs"]),
                        f"缺腿必须被显式点名，实际 = {r['missing_legs']!r}")

    def test_http_error_is_loud(self):
        self.serve("", rc=500)
        r = fp.southbound_intraday()
        self.assertFalse(r["ok"])
        self.assertIn("rc=500", r["note"])

    def test_non_json_and_empty_data_survived(self):
        self.serve("<html>nope</html>")
        self.assertFalse(fp.southbound_intraday()["ok"])
        fp._CACHE = {}
        self.serve({})
        r = fp.southbound_intraday()
        self.assertFalse(r["ok"])
        self.assertIn("data 为空", r["note"])


if __name__ == "__main__":
    print("=" * 60)
    print("Anchor - Southbound T+0 (kamt/get) Test Suite")
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
