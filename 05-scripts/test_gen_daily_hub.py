#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""当日指挥中心文案测试（test_gen_daily_hub.py，inbox/143-B）

覆盖（此组断言修复后**永久保留**，防「硬编码陈旧文案」回退）：
  ① 非新低场景 ⇒ 输出不得含「新低」（值说反的修复钉死）
  ② 不得含「破位」与写死日期「9/7」（不被字段支撑的旁白 / 过期事件窗口）
  ③ 「严禁加仓」的理由必须随数据（月额度满 ⇒ 数据驱动理由；否则「见当日报告」，
     ⛔ 不编造理由）
运行: python test_gen_daily_hub.py
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gen_daily_hub as gdh


def _data(cumul):
    return {"holdings_summary": [{"name": "创新药C", "cumul": cumul, "mv": 2421}],
            "stop_loss_watch": {}}


def _inno_card(html):
    """截取「创新药 严禁加仓」卡片的 desc 段（避免误伤其它卡片的措辞）。"""
    m = re.search(r"创新药 严禁加仓</span>.*?signal-desc\">(.*?)</div>", html, re.S)
    if not m:
        m = re.search(r"signal-desc\">([^<]*创新药[^<]*)</div>", html, re.S)
    return m.group(1) if m else ""


class InnoCardTests(unittest.TestCase):
    def _html(self, cumul, ops=None):
        return gdh.build_signals({"ops_state": ops or {}}, _data(cumul), {})

    def test_143B1_非新低场景不得出现新低(self):
        card = _inno_card(self._html(-233.57))                    # 9/18 −368.63 → 9/21 −233.57（改善）
        self.assertIn("整仓累计", card, "累计值须如实出现（渲染口径为整数）")
        self.assertNotIn("新低", card)

    def test_143B2_不得出现破位与写死日期(self):
        card = _inno_card(self._html(-233.57))
        self.assertNotIn("破位", card)
        self.assertNotIn("9/7", card)

    def test_143B3_理由随数据_不编造(self):
        card_open = _inno_card(self._html(-233.57, {"is_at_limit": False, "label": "9月"}))
        self.assertIn("原因见当日报告", card_open)
        self.assertNotIn("额度已满", card_open)
        card_full = _inno_card(self._html(-233.57, {"is_at_limit": True, "label": "9月"}))
        self.assertIn("9月额度已满", card_full)

    def test_源文件不得残留写死日期(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "gen_daily_hub.py"), encoding="utf-8").read()
        self.assertIsNone(re.search(r"9/7|09-07", src), "源文件仍含写死日期")


if __name__ == "__main__":
    print("=" * 60)
    print("Anchor - Daily Hub Copy Test Suite")
    print("=" * 60)
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("=" * 60)
    print("ALL TESTS PASSED" if result.wasSuccessful()
          else f"FAILURES: {len(result.failures)} | ERRORS: {len(result.errors)}")
    print(f"   Ran {result.testsRun} tests")
    print("=" * 60)
    sys.exit(0 if result.wasSuccessful() else 1)
