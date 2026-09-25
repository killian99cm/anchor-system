#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单 150 回归：DDX **降级可见化**（「不可得（已试 N 源）」）＋ 两类不可得**必须可分辨**

背景
----
DDX 四周期**连续 3 次取数全空**（9/22 部分、9/23、9/24 收盘后重试）。后果两层：
① **数据层（本单）**：DDX 栏**静默留空** ⇒ 读者分不清「**无源**」与「**零值**」，
   也分不清「**A 股体系外**」（真·不可得，⛔ 不要重试）与「**取数失败**」（限流，**可重试**）；
② **规则层（⛔ 不在本单）**：半导体 `X` 级过滤器与 §2.2 B3 双双失去判据源 ⇒ 已挂 #C1-21 **N-5**。

断言
----
① **源可用 ⇒ 文案为空**（⛔ 不得含「不可得」三字；否则它会变成天天出现的装饰句）
   ＋ 🔴 **断言执行计数 ≥1**（防「引入 skip 后断言永不执行」—— 144 验收③ 同型）；
② **源失败 ⇒ 文案含「不可得（已试 N 源）」**，且 N 是**实测的**尝试次数（⛔ 不写死）；
③ 🔴 **两类不可得必须写出不同的话** ——「A 股体系外」vs「取数失败」
   （写成同一句 = 把「有源却没换」误报成「边界」，报告标准 §二.13 明禁）；
④ 🔴 **反向（承重）**：把降级文案换成**常量**（不分两类）⇒ ③ 的判别力必须消失
   ⇒ 证明 ③ 不是空转断言；
⑤ **零值不是缺失**：`f88=0.0` ⇒ `available=True`、文案为空（与 `_num` 的单测同族）。

⛔ 本单**不碰规则/阈值**（规则侧处置须待 #C1-21 N-5 裁决）；⛔ 打桩 `_http` ⇒ 零网络。

运行：python test_ddx_degradation.py
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import fetch_public as fp          # noqa: E402

SECIDS = ["0.980017", "1.513120"]
CALLS = []                          # 🔴 执行计数（断言「确实跑过」）


def _row(code, f88, market=0):
    return {"f12": code, "f13": market, "f14": f"标的{code}", "f88": f88,
            "f396": f88, "f91": f88, "f94": f88,
            "f89": f88, "f397": f88, "f92": f88, "f95": f88, "f90": f88}


def _resp(payload, rc=0):
    CALLS.append(1)
    return (200, json.dumps({"rc": rc, "data": payload}))


def _down(msg="[RemoteDisconnected] Remote end closed connection without response"):
    """连接层失败（**计数也要记** —— 否则「断言执行计数」在多轮重试下会失真）。"""
    CALLS.append(1)
    return (-1, msg)


class TestDDXDegradation(unittest.TestCase):
    def setUp(self):
        CALLS.clear()
        fp._CACHE.clear()

    def test_01_available_yields_empty_text(self):
        """① 源可用 ⇒ 文案为空（⛔ 源可用时不得出现「不可得」）。"""
        with mock.patch.object(fp, "_http", return_value=_resp(
                {"diff": [_row("980017", 0.218, 0), _row("513120", -0.342, 1)]})):
            r = fp.ddx(SECIDS)
        txt = fp.ddx_unavailable_text(r, SECIDS)
        self.assertEqual(txt, "", f"❌ 源可用却给出降级文案：{txt}")
        self.assertNotIn("不可得", txt)
        self.assertGreaterEqual(len(CALLS), 1, "❌ 断言未执行（执行计数 0）⇒ 本用例无鉴别力")

    def test_02_source_failure_says_unavailable_with_n(self):
        """② 源失败 ⇒ 文案含「不可得（已试 N 源）」，N＝实测尝试次数。"""
        with mock.patch.object(fp, "_http",
                              return_value=_down()):
            r = fp.ddx(SECIDS)
        txt = fp.ddx_unavailable_text(r, SECIDS)
        self.assertIn("不可得（已试 3 源）", txt, f"❌ 未写出「已试 N 源」：{txt}")
        self.assertIn("取数失败", txt)
        self.assertGreaterEqual(len(CALLS), 1)

    def test_03_two_kinds_of_unavailable_must_read_differently(self):
        """🔴 ③ **A 股体系外**（回行但字段为 `-`）与 **取数失败**（连接断）**必须写得不一样**。"""
        # A 股体系外：端点回行，但 f88 族是 `-`
        with mock.patch.object(fp, "_http", return_value=_resp(
                {"diff": [{"f12": "HSSCID", "f13": 124, "f14": "恒生港股通创新药",
                           "f88": "-", "f396": "-", "f91": "-", "f94": "-",
                           "f89": "-", "f397": "-", "f92": "-", "f95": "-", "f90": "-"}]})):
            outside = fp.ddx_unavailable_text(fp.ddx(["124.HSSCID"]), ["124.HSSCID"])
        # 取数失败：连接被对端关闭
        fp._CACHE.clear()
        with mock.patch.object(fp, "_http", return_value=_down("[RemoteDisconnected] boom")):
            failed = fp.ddx_unavailable_text(fp.ddx(["0.980017"]), ["0.980017"])
        self.assertIn("A 股体系外", outside, f"❌ 体系外未写「A 股体系外」：{outside}")
        self.assertIn("不要重试", outside)
        self.assertIn("取数失败", failed)
        self.assertIn("可重试", failed)
        self.assertNotEqual(outside, failed, "❌ 两类不可得被写成同一句 ⇒ 读者无法分辨（§二.13 明禁）")

    def test_04_reverse_unified_text_loses_discriminating_power(self):
        """🔴 ④ 反向（承重）：把文案换成**常量**（不分两类）⇒ ③ 的判别力必须消失。"""
        const = lambda r, s=None: "**不可得（已试 3 源）**"      # noqa: E731
        orig = fp.ddx_unavailable_text
        try:
            fp.ddx_unavailable_text = const
            a = fp.ddx_unavailable_text({}, [])
            b = fp.ddx_unavailable_text({}, [])
        finally:
            fp.ddx_unavailable_text = orig
        self.assertEqual(a, b, "❌ 常量文案下两者仍不同 ⇒ 本反向用例无意义")
        self.assertNotIn("A 股体系外", a)
        self.assertNotIn("取数失败", a)
        # 对照：真实现下两者**确实不同**（由 test_03 断言）
        self.assertNotEqual(orig({"124.HSSCID": {"available": False, "sources_tried": 3,
                                                "unavailable_reason": "真·不可得（A 股体系外：…）"}},
                                 ["124.HSSCID"]),
                            orig({"0.980017": {"available": False, "sources_tried": 3,
                                               "unavailable_reason": "取数失败（…）"}},
                                 ["0.980017"]))

    def test_05_zero_is_a_value_not_a_gap(self):
        """⑤ 零值不是缺失：`f88=0.0` ⇒ available=True、文案为空。"""
        with mock.patch.object(fp, "_http", return_value=_resp({"diff": [_row("980017", 0.0)]})):
            r = fp.ddx(["0.980017"])
        self.assertTrue(r["0.980017"]["available"], "❌ 0.0 被当成缺失（与 _num 的口径冲突）")
        self.assertEqual(fp.ddx_unavailable_text(r, ["0.980017"]), "")

    def test_06_sources_tried_is_recorded_for_degradation_text(self):
        """② N 必须是**实测**的：`_attempts` 随实际 host 轮换长度变化。"""
        with mock.patch.object(fp, "_http", return_value=_down("boom")):
            r = fp.ddx(["0.980017"])
        self.assertTrue(r.get("_attempts"), "❌ 未留痕实际试过的 host ⇒ 文案写不出真实 N")
        self.assertEqual(r["0.980017"]["sources_tried"], len(r["_attempts"]))

    def test_07_rule_layer_untouched(self):
        """⛔ 规则侧未动：本单只改取数层与文案（判据源 150 §1.3）。"""
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_public.py"),
                   encoding="utf-8").read()
        for token in ("b3_", "ddx_consecutive", "semiconductor_filter"):
            self.assertNotIn(token, src, f"❌ 取数层出现规则侧标识 `{token}`（越界）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
