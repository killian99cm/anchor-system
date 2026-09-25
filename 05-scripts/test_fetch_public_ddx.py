#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_fetch_public_ddx.py — DDX 取数回归测试
================================================================================
存在理由（2026-09-18）：系统此前把「DDX」登记为**结构性无源**，并据此
  ① 删掉了 B2' 触发线里的 DDX 条件（登记表 :351「重设已被证明是正确的」）
  ② 在多份报告里用**板块级主力资金**作替代口径
实测推翻：DDX 一直可得，且**两条独立路径逐位一致**（mx-data 与东财公网）。

**真正的病根**：`stock/get`（单标的端点）**不供** f88 字段族 → 被读成「DDX 无源」。
⇒ 本文件的核心不是「DDX 能不能取」，而是钉死 **「端点选错 ⇒ 必然得出无源结论」**这一
   致错路径，使将来任何人重犯时**有一条测试会红**。

纪律（沿用 v4.4.16 / v4.5.0 的「反向断言」传统）：
  ⛔ **不只测「改对了」，还测「原写法确实会错」** —— 否则测试可能在**假阳性**下通过。
  ⛔ 不碰生产数据文件；全部用 mock，**不发真实网络请求**。
================================================================================
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fetch_public as fp  # noqa: E402


def _resp(diff: list[dict], rc: int = 0) -> tuple[int, str]:
    """构造东财 ulist.np 的成功响应体。"""
    return 200, json.dumps({"rc": rc, "data": {"diff": diff}})


def _row(f13: int, f12: str, f14: str, **kw) -> dict:
    d = {"f13": f13, "f12": f12, "f14": f14}
    d.update(kw)
    return d


class TestDDXEndpoints(unittest.TestCase):
    """端点选择 —— 本次修正的核心。"""

    def setUp(self):
        fp._CACHE.clear()
        fp.PROBE_LOG.clear()

    def test_ddx_uses_list_endpoint(self):
        """正向：DDX 必须走**列表类端点** `ulist.np/get`。"""
        seen = []

        def fake(url, referer, timeout, enc):
            seen.append(url)
            return _resp([_row(0, "980017", "国证芯片", f88=0.218)])

        with mock.patch.object(fp, "_http", side_effect=fake):
            fp.ddx(["0.980017"])
        self.assertEqual(len(seen), 1)
        self.assertIn("/api/qt/ulist.np/get", seen[0])

    def test_reverse_stock_get_yields_no_ddx(self):
        """🔴 **反向断言** —— 证明「修前那条路确实拿不到」。

        故意用 `stock/get` 的真实响应形状（**只有 f57/f58，没有 f88 族**）——
        这正是 2026-09-17 判「DDX 无源」时看到的东西。
        若此用例改为 available=True，说明端点差异已不存在，应重新评估；
        **在它改变之前，「端点 ≠ 无源」这条纪律必须保留**。
        """
        stock_get_shape = _row(1, "513120", "港股创新药ETF广发")  # 没有 f88 等
        with mock.patch.object(fp, "_http", return_value=_resp([stock_get_shape])):
            r = fp.ddx(["1.513120"])
        self.assertFalse(r["1.513120"]["available"],
                         "本用例模拟的是旧行为；若可用则说明端点差异已消失")
        self.assertIsNone(r["1.513120"]["ddx"]["d1"])
        self.assertIsNone(r["1.513120"]["ddx"]["d10"])

    def test_board_code_supported(self):
        """板块码 `90.BK1036` 走同一端点（报告需要板块级 DDX）。"""
        with mock.patch.object(fp, "_http",
                               return_value=_resp([_row(90, "BK1036", "半导体", f88=0.346)])):
            r = fp.ddx(["90.BK1036"])
        self.assertIn("90.BK1036", r)
        self.assertAlmostEqual(r["90.BK1036"]["ddx"]["d1"], 0.346)


class TestDDXParsing(unittest.TestCase):
    """字段解析 —— 含「无此字段」的长相。"""

    def setUp(self):
        fp._CACHE.clear()
        fp.PROBE_LOG.clear()

    def test_four_periods_mapped(self):
        """四周期必须分别落到 d1/d3/d5/d10，且不串位。"""
        with mock.patch.object(fp, "_http", return_value=_resp([
                _row(0, "980017", "国证芯片",
                     f88=0.218, f396=0.293, f91=0.21, f94=-0.111)])):
            d = fp.ddx(["0.980017"])["0.980017"]["ddx"]
        self.assertEqual(d, {"d1": 0.218, "d3": 0.293, "d5": 0.21, "d10": -0.111})

    def test_dash_becomes_none_not_crash(self):
        """东财「无此字段」的长相是字符串 `'-'`（→ 港股/美股/外盘的真实返回）。"""
        self.assertIsNone(fp._num("-"))
        self.assertIsNone(fp._num(""))
        self.assertIsNone(fp._num(None))
        self.assertEqual(fp._num("-0.342"), -0.342)
        self.assertEqual(fp._num(0.0), 0.0, "0.0 不得被误判为缺失")

    def test_hk_us_unavailable_but_a_share_available(self):
        """同一批里区分**真·不可得**（A 股体系外）与**取数失败**。

        A 股/板块 `available=True` ⇒ 说明请求是通的 ⇒ 那时港股/美股的
        `available=False` 属「**真不可得**」，**不是重试就能好的失败**。
        """
        with mock.patch.object(fp, "_http", return_value=_resp([
                _row(0, "980017", "国证芯片", f88=0.218, f396=0.293, f91=0.21, f94=-0.111),
                _row(124, "HSSCID", "恒生港股通创新药指数",
                     f88="-", f396="-", f91="-", f94="-"),
                _row(100, "NDX100", "纳斯达克100",
                     f88="-", f396="-", f91="-", f94="-")])):
            r = fp.ddx(["0.980017", "124.HSSCID", "100.NDX100"])
        self.assertTrue(r["0.980017"]["available"])
        self.assertFalse(r["124.HSSCID"]["available"])
        self.assertFalse(r["100.NDX100"]["available"])
        # 关键：这不是异常，是「该体系不供此指标」——调用方须走替代口径而非重试
        self.assertIsNone(r["124.HSSCID"]["ddx"]["d1"])

    def test_ddz_only_has_d1(self):
        """DDZ 只有当日一档（没有 3/5/10 日）⇒ 结构上就不得假装有。"""
        with mock.patch.object(fp, "_http",
                               return_value=_resp([_row(0, "980017", "国证芯片", f90=11.58)])):
            item = fp.ddx(["0.980017"])["0.980017"]
        self.assertEqual(set(item["ddz"]), {"d1"})
        self.assertAlmostEqual(item["ddz"]["d1"], 11.58)

    def test_close_confirmed_always_false(self):
        """盘中 DDX 不得作触发线判据（附录E · F5）——字段必须恒为 False。"""
        with mock.patch.object(fp, "_http",
                               return_value=_resp([_row(0, "980017", "国证芯片", f88=0.218)])):
            item = fp.ddx(["0.980017"])["0.980017"]
        self.assertIs(item["close_confirmed"], False)


class TestDDXHonesty(unittest.TestCase):
    """缺失必须**可见** —— 静默跳过正是本次要治的病。"""

    def setUp(self):
        fp._CACHE.clear()
        fp.PROBE_LOG.clear()

    def test_missing_secid_is_recorded(self):
        """端点未返回某 secid ⇒ 必须留痕，**不得静默**。"""
        with mock.patch.object(fp, "_http",
                               return_value=_resp([_row(0, "980017", "国证芯片", f88=0.218)])):
            fp.ddx(["0.980017", "0.399975"])
        notes = [r for r in fp.PROBE_LOG if not r["ok"]]
        self.assertTrue(notes, "缺失 secid 必须产生一条失败留痕")
        self.assertIn("0.399975", notes[0]["url"])

    def test_no_missing_records_nothing_failed(self):
        """反向：全都拿到时**不得**留下失败留痕（否则日志会天天假响）。"""
        with mock.patch.object(fp, "_http", return_value=_resp([
                _row(0, "980017", "国证芯片", f88=0.218),
                _row(0, "399975", "证券公司", f88=0.044)])):
            fp.ddx(["0.980017", "0.399975"])
        self.assertFalse([r for r in fp.PROBE_LOG if not r["ok"]],
                         "全部命中时不得留下失败留痕（假告警会被学会忽略）")

    def test_data_null_returns_empty_not_crash(self):
        """`data:null`（如 rc=100 无此证券）⇒ **不抛**，且该 secid **必须显式标不可得**。

        🔴 2026-09-25 契约升级（单 150）：原断言 `r == {}`（＝**静默留空**）已**不再成立**——
        「静默留空」正是 150 要治的形态（读者分不清「无源」与「零值」）。新契约**更强**：
        该 secid **仍在**返回里，但 `available=False` ＋ 带 `unavailable_reason`。
        """
        with mock.patch.object(fp, "_http",
                               return_value=(200, json.dumps({"rc": 100, "data": None}))):
            r = fp.ddx(["9.999999"])
        self.assertEqual(set(r) - {"_attempts"}, {"9.999999"}, "❌ 不可得 secid 被静默丢弃")
        self.assertFalse(r["9.999999"]["available"])
        self.assertIn("取数失败", r["9.999999"]["unavailable_reason"])

    def test_network_failure_returns_empty_not_crash(self):
        """网络层失败 ⇒ **不抛**（会崩的取数层比没有更糟），且必须显式标不可得（同上）。"""
        with mock.patch.object(fp, "_http", return_value=(-1, "[URLError] boom")):
            r = fp.ddx(["0.980017"])
        self.assertEqual(set(r) - {"_attempts"}, {"0.980017"})
        self.assertFalse(r["0.980017"]["available"])
        self.assertGreaterEqual(r["0.980017"]["sources_tried"], 1,
                                "❌ 未记录「已试 N 源」⇒ 降级文案写不出真实的 N")


class TestDDXContract(unittest.TestCase):
    """接口契约 —— 防后人「顺手改签名」改跑调用方。"""

    def test_exported(self):
        self.assertIn("ddx", fp.__all__)

    def test_accepts_bare_string(self):
        """允许传单个 secid 字符串（与 index_quotes 同形）。"""
        fp._CACHE.clear()
        with mock.patch.object(fp, "_http",
                               return_value=_resp([_row(0, "980017", "国证芯片", f88=0.218)])):
            r = fp.ddx("0.980017")
        self.assertIn("0.980017", r)

    def test_fields_include_whole_ddx_family(self):
        """请求字段必须覆盖全族 —— 少一个就少一档，而**报告不会知道**。"""
        for f in ("f88", "f396", "f91", "f94",      # DDX 四周期
                  "f89", "f397", "f92", "f95",      # DDY 四周期
                  "f90"):                            # DDZ
            self.assertIn(f, fp._DDX_FIELDS)
        self.assertNotIn("f57", fp._DDX_FIELDS, "f57 是 stock/get 的字段，非本族")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    unittest.main(verbosity=2)
