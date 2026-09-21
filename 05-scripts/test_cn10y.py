#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中国10Y「换源」回归测试（test_cn10y.py · 2026-09-21 新建 · v4.5.12）

**本文件治的是什么**：
    `cn10y()` 的旧 docstring 断言「**东财公开 API 不提供任何国债收益率**」，
    并据此**预期返回 `value=None`**、每份报告照走替代口径。**该断言已被实测证伪**：
    东财 `datacenter-web` 的 `RPTA_WEB_TREASURYYIELD` **一直可用**。
    旧写法之所以「4 源全失败」，是因为它**只试了 `push2` 那一套服务的 `stock/get`**
    —— **收益率在另一套服务里**（试的是 A 服务，结论下在 B 服务上）。

**修法（本文件所测的）**：
    ① 主源改走 `datacenter-web` 报表端点（`reportName=RPTA_WEB_TREASURYYIELD`，
       字段 `EMM00166466`）；② 旧 secid 循环降为**末位兜底**（保留防报表下线）。

**测试策略**：全部**离线**（monkeypatch `_http` / `_em_json`），不联网、不碰生产缓存。
运行: python test_cn10y.py
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_public as fp


def _dc_body(rows):
    """datacenter 报表响应形状（实测形状，非构造）。"""
    return json.dumps({"result": {"data": rows}, "success": True,
                       "message": "ok", "code": 0})


# 实测值（2026-09-14~09-20 连续，末条 9/20 = 调休上班日，债市照常发布）
DC_ROWS = [
    {"SOLAR_DATE": "2026-09-20 00:00:00", "EMM00166466": 1.6818},
    {"SOLAR_DATE": "2026-09-18 00:00:00", "EMM00166466": 1.682},
    {"SOLAR_DATE": "2026-09-17 00:00:00", "EMM00166466": 1.6862},
]
TRUE_0918 = 1.682


class Cn10yFixture(unittest.TestCase):
    """换掉 `_http`/`_em_json`；每次用干净缓存，**不碰生产文件**（J11 之理）。"""

    def setUp(self):
        self._oh, self._oc, self._oe, self._or = fp._http, fp._CACHE, fp._em_json, fp._record
        fp._CACHE = {}
        fp._record = lambda *a, **k: None

    def tearDown(self):
        fp._http, fp._CACHE, fp._em_json, fp._record = self._oh, self._oc, self._oe, self._or

    def serve_dc(self, body, rc=200):
        fp._http = lambda url, referer, timeout, encoding: (rc, body)

    def serve_legacy(self, value):
        fp._em_json = lambda path, params, label: {"f43": value}


class TestPrimarySource(Cn10yFixture):
    def test_datacenter_is_primary_and_value_is_returned(self):
        self.serve_dc(_dc_body(DC_ROWS))
        r = fp.cn10y()
        self.assertAlmostEqual(r["value"], 1.6818, places=4,
                               msg="主源必须命中 —— 这正是「无源」被证伪的落点")
        self.assertIn("datacenter", r["source"])
        self.assertIn("RPTA_WEB_TREASURYYIELD", r["source"])

    def test_data_date_is_exposed_separately_from_fetch_time(self):
        """🔴 `date`（数据自身日期）与 `ts`（取数时刻）必须是两个字段。

        旧写法值恒为 None，这个区别看不见；换源成功后若只暴露 `ts`，
        报告会把「我今天取的」写成「今天的数据」。
        """
        self.serve_dc(_dc_body(DC_ROWS))
        r = fp.cn10y()
        self.assertEqual(r["date"], "2026-09-20", "date 必须是数据自身日期")
        self.assertNotEqual(r["date"], r["ts"][:10], "date 不得等于取数日（否则两者被混为一谈）")
        self.assertRegex(r["ts"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    def test_legacy_secids_are_not_tried_when_primary_hits(self):
        """主源命中后**不得**再烧 secid 循环 —— 那也是配额/时间成本。"""
        calls = {"n": 0}

        def _boom(path, params, label):
            calls["n"] += 1
            return {"f43": None}

        self.serve_dc(_dc_body(DC_ROWS))
        fp._em_json = _boom
        r = fp.cn10y()
        self.assertAlmostEqual(r["value"], 1.6818, places=4)
        self.assertEqual(calls["n"], 0, "主源命中时旧路径一次都不该被调用")
        self.assertEqual(r["n_sources_tried"], 1)


class TestFallback(Cn10yFixture):
    def test_falls_back_to_legacy_when_report_is_empty(self):
        self.serve_dc(_dc_body([]))
        self.serve_legacy(1.7)
        r = fp.cn10y()
        self.assertAlmostEqual(r["value"], 1.7, places=4)
        self.assertIn("stock/get", r["source"], "兜底路径必须自我披露")

    def test_out_of_range_value_is_rejected_not_reported(self):
        """收益率合理区间守卫：300 这种值不得被当成中国10Y报出。"""
        self.serve_dc(_dc_body([{"SOLAR_DATE": "2026-09-20 00:00:00", "EMM00166466": 300}]))
        self.serve_legacy(None)
        r = fp.cn10y()
        self.assertIsNone(r["value"], "超区间值必须被拒绝")


class TestReverseAssertions(Cn10yFixture):
    """🔴 反向断言：证明**修复前的写法确实拿不到**，否则测试可能在假阳性下通过。"""

    def test_reverse_legacy_path_alone_would_yield_none(self):
        """只用旧路径（主源不可用）⇒ 必须 None —— 这正是修复前的生产状态。"""
        self.serve_dc("boom", rc=500)
        self.serve_legacy(None)
        r = fp.cn10y()
        self.assertIsNone(r["value"])
        self.assertGreaterEqual(r["n_sources_tried"], 4,
                                "旧路径 4 个 secid 必须都被试过（计数器不得少报）")

    def test_reverse_assertion_that_datacenter_is_a_different_service(self):
        """同行内断言：`stock/get` 与 `RPTA_WEB_TREASURYYIELD` 是**两套服务**。

        若将来有人把主源改回 `stock/get`，本测试的 URL 断言必失败。
        """
        urls = []

        def _spy(url, referer, timeout, encoding):
            urls.append(url)
            return 200, _dc_body(DC_ROWS)

        fp._http = _spy
        fp.cn10y()
        self.assertTrue(urls, "必须真的发起过请求")
        self.assertIn("datacenter-web.eastmoney.com", urls[0],
                      "主源必须走 datacenter 服务，不是 push2")
        self.assertIn("reportName=", urls[0])


class TestFailureModes(Cn10yFixture):
    def test_http_error_then_everything_fails_is_loud(self):
        self.serve_dc("", rc=500)
        self.serve_legacy(None)
        r = fp.cn10y()
        self.assertIsNone(r["value"])
        self.assertIn("全部失败", r["note"])
        self.assertIsNone(r["date"], "无值时 date 必须为 None，不得伪造日期")

    def test_non_json_is_survived(self):
        self.serve_dc("<html>not json</html>")
        self.serve_legacy(1.65)
        r = fp.cn10y()
        self.assertAlmostEqual(r["value"], 1.65, places=4, msg="非 JSON 必须被吞掉并降级，不得抛穿")


if __name__ == "__main__":
    print("=" * 60)
    print("Anchor - China 10Y Source-Switch Test Suite")
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
