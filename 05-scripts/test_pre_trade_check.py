#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anchor 交易前校验测试（test_pre_trade_check.py，C2/C5 新增）
覆盖：阈值读规则契约 / 缺失回退内置 + 来源标记 / 契约覆盖 / 品种匹配 /
      月操作统计复用 data_processor（定投·出入金不计、严格日期匹配）。
运行: python test_pre_trade_check.py
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths
import pre_trade_check as ptc
from data_processor import monthly_ops_summary


class TestBuiltinThresholds(unittest.TestCase):
    def test_builtin_keys_complete(self):
        b = ptc.BUILTIN_THRESHOLDS
        for k in ("e1_sat_single_limit", "e4_sat_monthly_net", "big_amount_batch",
                  "max_monthly_ops", "scorecard_event_exempt", "targets"):
            self.assertIn(k, b)
        self.assertEqual(b["e1_sat_single_limit"], 3000.0)
        self.assertEqual(b["max_monthly_ops"], 4)
        self.assertGreaterEqual(len(b["targets"]), 9)


class TestLoadThresholds(unittest.TestCase):
    def setUp(self):
        self._orig = paths.RULE_CONTRACT_PATH

    def tearDown(self):
        paths.RULE_CONTRACT_PATH = self._orig

    def test_load_from_real_contract(self):
        # 真实契约存在时应来自 contract，且数值/品种齐全
        th = ptc.load_thresholds()
        self.assertEqual(th["_source"], "contract")
        self.assertEqual(th["e1_sat_single_limit"], 3000.0)
        self.assertIn("创新药", th["targets"])

    def test_fallback_when_contract_missing(self):
        # 契约路径不存在 → 回退内置默认并标记 builtin（不抛异常）
        paths.RULE_CONTRACT_PATH = Path(tempfile.gettempdir()) / "__no_such_contract__.json"
        th = ptc.load_thresholds()
        self.assertEqual(th["_source"], "builtin")
        self.assertEqual(th["e1_sat_single_limit"], 3000.0)
        self.assertEqual(th["max_monthly_ops"], 4)
        self.assertIn("创新药", th["targets"])

    def test_contract_overrides_builtin(self):
        # 契约里的数值应覆盖内置；targets 做合并（内置品种保留）
        tmp = Path(tempfile.gettempdir()) / "_ptc_contract.json"
        payload = {"thresholds": {"e1_sat_single_limit": 9999.0,
                                  "targets": {"测试品种": {"target": 1, "layer": "卫星", "reach": "x"}}}}
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            paths.RULE_CONTRACT_PATH = tmp
            th = ptc.load_thresholds()
            self.assertEqual(th["_source"], "contract")
            self.assertEqual(th["e1_sat_single_limit"], 9999.0)
            self.assertIn("测试品种", th["targets"])   # 契约品种并入
            self.assertIn("创新药", th["targets"])      # 内置品种保留
        finally:
            tmp.unlink(missing_ok=True)


class TestFindTarget(unittest.TestCase):
    def setUp(self):
        self.targets = ptc.BUILTIN_THRESHOLDS["targets"]

    def test_keyword_hit(self):
        key, tgt = ptc.find_target(self.targets, {}, "创新药")
        self.assertEqual(key, "创新药")
        self.assertEqual(tgt["layer"], "卫星")

    def test_holding_fuzzy_hit(self):
        holdings = {"易方达恒生港股通创新药ETF联接C": {"mv": 1}}
        key, tgt = ptc.find_target(self.targets, holdings, "港股通创新药")
        self.assertEqual(key, "创新药")

    def test_miss_returns_none(self):
        key, tgt = ptc.find_target(self.targets, {}, "不存在品种xyz")
        self.assertIsNone(key)
        self.assertIsNone(tgt)


class TestMonthlyOpsReuse(unittest.TestCase):
    """pre_trade_check 月操作统计复用 data_processor：定投/出入金/自动扣款不计，严格按月。"""
    def test_excludes_auto_and_cross_month(self):
        data = {"transactions": [
            {"date": "2026-08-01", "op": "定投"},                                   # 不计
            {"date": "2026-08-02", "op": "买入"},                                   # 1
            {"date": "2026-08-03", "op": "加仓"},                                   # 2
            {"date": "2026-08-04", "op": "转入"},                                   # 出入金不计
            {"date": "2026-08-05", "op": "买入",
             "note": "智能定投自动扣款（非手动操作，不计入月限额）"},               # note 自动扣款不计
            {"date": "2026-07-30", "op": "买入"},                                   # 上月不计
        ]}
        used, viol = monthly_ops_summary(data, year=2026, month=8)
        self.assertEqual(used, 2)


if __name__ == "__main__":
    print("=" * 60)
    print("Anchor - Pre-Trade Check Test Suite")
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
