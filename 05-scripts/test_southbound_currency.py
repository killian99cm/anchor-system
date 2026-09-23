#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南向 T+0 币种口径测试（test_southbound_currency.py，inbox/143-A）

覆盖（修复后**永久保留**，防回退到 CNY/人民币误标）：
  ① `southbound_intraday()` 的 `currency` 必须 ≠ CNY（＝HKD）
  ② `unit` 必须＝万港元；note 不得再写「万元人民币」
  ③ `currency_basis` 必须写明原 `dayAmtThreshold` 推理**已证伪/不成立**，且提到 `dayNetAmtIn`
  ④ `forbidden_use` 必须归因到「单位不同」而非「币种不同」
⛔ 本组为**源码级静态断言**（southbound_intraday 需联网取数，离线不调用真实接口）。
运行: python test_southbound_currency.py
"""
import inspect
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_public as fp

SRC = inspect.getsource(fp.southbound_intraday)


class SouthboundCurrencyTests(unittest.TestCase):
    def test_143A_currency_not_cny(self):
        m = re.search(r'"currency":\s*"([A-Z]+)"', SRC)
        self.assertIsNotNone(m, "未找到 currency 字段")
        self.assertNotEqual(m.group(1), "CNY", "⛔ 币种不得回退为 CNY")
        self.assertEqual(m.group(1), "HKD")

    def test_143A_unit_and_note(self):
        self.assertIn('"unit": "万港元"', SRC)
        self.assertNotIn("万元人民币", SRC)

    def test_143A_basis_falsified_and_names_daynetamtin(self):
        self.assertTrue(("不成立" in SRC) or ("已证伪" in SRC),
                        "currency_basis 必须写明原推理被证伪（R2）")
        self.assertIn("dayNetAmtIn", SRC, "必须点名被证伪所涉的 dayNetAmtIn 族（防空话）")

    def test_143A_forbidden_use_attributes_unit_not_currency(self):
        self.assertIn("单位不同", SRC)
        self.assertNotIn("对拉（币种不同）", SRC)          # 旧「币种不同」断言形已订正
        self.assertIn("误写为「币种不同」", SRC)            # 纠错留痕（引用旧措辞，非新断言）

    def test_143A_not_touch_southbound(self):
        """⛔ 本单不动 southbound()（T-1 百万港元，本已正确）。"""
        s = inspect.getsource(fp.southbound)
        self.assertIn('"unit": "百万港元"', s)
        self.assertNotIn('"currency": "CNY"', s)


if __name__ == "__main__":
    print("=" * 60)
    print("Anchor - Southbound Currency Test Suite")
    print("=" * 60)
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("=" * 60)
    print("ALL TESTS PASSED" if result.wasSuccessful()
          else f"FAILURES: {len(result.failures)} | ERRORS: {len(result.errors)}")
    print(f"   Ran {result.testsRun} tests")
    print("=" * 60)
    sys.exit(0 if result.wasSuccessful() else 1)
