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
        #
        # 🔴 v4.5.17 订正：本夹具原用 **内部键名** `e1_sat_single_limit`。
        #    旧实现为此写了一条**反向查表兜底**（`next((kk for kk,vv in _KEY_MAP.items() if vv==k))`），
        #    于是**同一个阈值在契约里有两个合法键名**（内部名 / 契约名）—— 正是
        #    「两层键名表并存且无绑定」那一族（E4 事故的同一套结构）。
        #    ⇒ 该兜底已随重构删除，契约**只有一套键名**（`extract_rule_contract` 写什么就认什么）。
        #    ⇒ 夹具改用**真契约键名**，并新增断言把夹具键名绑死到注册表上
        #      （否则夹具会再次静默漂移成「测了个不存在的键」—— 那时本测试**依然会绿**，
        #       因为断言值恰好等于内置默认 → 同 J14「弱断言掩盖真实缺口」）。
        tmp = Path(tempfile.gettempdir()) / "_ptc_contract.json"
        _CK = "e1_sat_position_cap"        # 真契约键名（内部名为 e1_sat_single_limit）
        import rule_keys as _rk
        self.assertIn(_CK, _rk.SCALAR_KEYS,
                      f"夹具用的契约键 {_CK!r} 不在注册表内 ⇒ 夹具已漂移，本次断言是空转")
        self.assertNotIn(_CK, _rk.SCALAR_KEYS[_CK].get("internal") or "",
                         "契约键与内部键必须**不同名**（同名则本测试证明不了翻译层在工作）")
        payload = {"thresholds": {_CK: 9999.0,
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

    def test_key_name_drift_is_loud(self):
        """🔴 v4.5.17：契约**非空**却一个数值键都没认出 ⇒ 必须**声张**。

        与 `test_fallback_when_contract_missing` 是**两种不同情形**，必须长得不一样：
          契约不存在 → 回退内置（正常降级，只 print 一句）
          契约存在但键名不匹配 → **键名漂移**（病），须进 `_warns`
        """
        tmp = Path(tempfile.gettempdir()) / "_ptc_drift.json"
        # 键名全部不匹配（模拟契约由旧版本/手工生成）
        tmp.write_text(json.dumps(
            {"rules": {"e1_sat_single_limit": 9999.0, "e4_sat_monthly_net": 8888.0}},
            ensure_ascii=False), encoding="utf-8")
        try:
            paths.RULE_CONTRACT_PATH = tmp
            th = ptc.load_thresholds()
            self.assertTrue(any("键名整体不匹配" in w for w in th["_warns"]),
                            f"漂移未被声张；_warns={th['_warns']}")
            # 🔴 反向：漂移时**全部**取值必须落到 builtin，⛔ 契约坏值一个都不得生效
            self.assertEqual(th["e1_sat_single_limit"], ptc.BUILTIN_THRESHOLDS["e1_sat_single_limit"])
            self.assertEqual(th["e4_sat_monthly_net"], ptc.BUILTIN_THRESHOLDS["e4_sat_monthly_net"])
        finally:
            tmp.unlink(missing_ok=True)

    def test_drift_guard_is_quiet_on_real_contract(self):
        """🔴 **反向断言**：真契约**不得**触发漂移告警
        （否则那是一条**永远亮着**的告警 —— 报告标准 v2.1 判例：会被学会忽略）。"""
        th = ptc.load_thresholds()
        self.assertEqual(th["_source"], "contract")
        self.assertFalse(any("键名整体不匹配" in w for w in th["_warns"]),
                         f"真契约误报漂移：{th['_warns']}")
        self.assertEqual(sum(1 for v in th["_sources"].values()
                             if v.get("tier") == "contract") > 0, True,
                         "真契约必须有键走 tier=contract（否则「未误报」是空集假象）")


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
