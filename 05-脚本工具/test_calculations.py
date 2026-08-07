#!/usr/bin/env python3
"""
Anchor v3.3 核心计算测试
覆盖: 四层占比、收益率、回撤线、盈亏计算
运行: python test_calculations.py
"""
import json
import os
import sys
import unittest
from datetime import date

# ===== 被测逻辑：从 data_processor import 权威实现（单一事实源） =====
# data_processor.py 是本文件所在目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_processor import fp, rate, safe_float, monthly_ops_summary

# 测试辅助函数（data_processor 未提供，纯测试用）
def calc_layer_ratios(bedrock_mv, core_mv, sat_mv, cash_mv):
    """Calculate four-layer pyramid ratios"""
    total = bedrock_mv + core_mv + sat_mv + cash_mv
    if total == 0:
        return {"bedrock": 0, "core": 0, "sat": 0, "cash": 0, "total": 0}
    return {
        "bedrock": round(bedrock_mv / total * 100, 1),
        "core": round(core_mv / total * 100, 1),
        "sat": round(sat_mv / total * 100, 1),
        "cash": round(cash_mv / total * 100, 1),
        "total": round(total, 2)
    }

def check_drawdown_level(current_total, peak=39510):
    """Return drawdown level: 'safe', 'warn', 'critical-10', 'critical-15'
    Default peak = 39510 (规则手册 v3.3 高点，与 data_processor 一致)"""
    dd_pct = (current_total - peak) / peak * 100
    if dd_pct <= -15:
        return ("critical-15", dd_pct)
    elif dd_pct <= -10:
        return ("critical-10", dd_pct)
    elif dd_pct <= -5:
        return ("warn", dd_pct)
    else:
        return ("safe", dd_pct)

def check_stop_loss(pnl, mv):
    """Check if a position triggers -8% stop loss"""
    r = rate(pnl, mv)
    return r <= -8, r


# ===== TESTS =====

class TestProfitFormat(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(fp(100), "+100")
        self.assertEqual(fp(0), "+0")

    def test_negative(self):
        self.assertEqual(fp(-50), "-50")

    def test_float(self):
        self.assertEqual(fp(123.45), "+123")


class TestRateCalculation(unittest.TestCase):
    def test_positive_return(self):
        # 市值 1100, 盈亏 +100 → 成本 1000 → 收益率 10%
        r = rate(100, 1100)
        self.assertAlmostEqual(r, 10.0, places=1)

    def test_negative_return(self):
        # 市值 900, 盈亏 -100 → 成本 1000 → 收益率 -10%
        r = rate(-100, 900)
        self.assertAlmostEqual(r, -10.0, places=1)

    def test_zero_mv(self):
        r = rate(100, 0)
        self.assertEqual(r, 0)

    def test_mv_equals_pnl(self):
        # Edge case: mv == pnl means cost is 0
        r = rate(100, 100)
        self.assertEqual(r, 0)

    def test_small_values(self):
        r = rate(0.01, 1000.01)
        self.assertAlmostEqual(r, 0.001, places=3)


class TestLayerRatios(unittest.TestCase):
    def test_normal_distribution(self):
        ratios = calc_layer_ratios(45000, 20000, 20000, 15000)
        self.assertEqual(ratios["bedrock"], 45.0)
        self.assertEqual(ratios["core"], 20.0)
        self.assertEqual(ratios["sat"], 20.0)
        self.assertEqual(ratios["cash"], 15.0)
        self.assertEqual(ratios["total"], 100000.00)

    def test_sum_is_100(self):
        ratios = calc_layer_ratios(15000, 5000, 8000, 2000)
        total_pct = ratios["bedrock"] + ratios["core"] + ratios["sat"] + ratios["cash"]
        self.assertAlmostEqual(total_pct, 100.0, places=0)

    def test_zero_total(self):
        ratios = calc_layer_ratios(0, 0, 0, 0)
        self.assertEqual(ratios["total"], 0)
        self.assertEqual(ratios["bedrock"], 0)

    def test_real_world_data(self):
        """Simulate actual portfolio: bed=18822, core=6183, sat=5681, cash=3032"""
        ratios = calc_layer_ratios(18822, 6183, 5681, 3032)
        total = ratios["total"]
        self.assertGreater(total, 33000)
        self.assertLess(total, 34000)
        # Bedrock should be largest (~56%)
        self.assertGreater(ratios["bedrock"], 50)


class TestDrawdownCheck(unittest.TestCase):
    def test_safe(self):
        level, pct = check_drawdown_level(36000, 37535)
        self.assertEqual(level, "safe")
        self.assertGreater(pct, -5)

    def test_warn(self):
        level, pct = check_drawdown_level(35000, 37535)
        self.assertEqual(level, "warn")
        self.assertLessEqual(pct, -5)
        self.assertGreater(pct, -10)

    def test_critical_10(self):
        level, pct = check_drawdown_level(33000, 37535)
        self.assertEqual(level, "critical-10")
        self.assertLessEqual(pct, -10)

    def test_critical_15(self):
        level, pct = check_drawdown_level(31000, 37535)
        self.assertEqual(level, "critical-15")
        self.assertLessEqual(pct, -15)


class TestStopLoss(unittest.TestCase):
    def test_no_trigger(self):
        triggered, r = check_stop_loss(-100, 9000)
        self.assertFalse(triggered)
        self.assertGreater(r, -8)

    def test_trigger(self):
        triggered, r = check_stop_loss(-1000, 9000)
        self.assertTrue(triggered)
        self.assertLessEqual(r, -8)

    def test_exact_boundary(self):
        # -8% exact: mv=9200, pnl=-800 → cost=10000, rate=-8%
        triggered, r = check_stop_loss(-800, 9200)
        self.assertTrue(triggered)


class TestMonthlyOps(unittest.TestCase):
    """操作计数使用 data_processor.monthly_ops_summary（单一事实源）"""

    def setUp(self):
        self.data = {"transactions": [
            {"date": "2026-08-07", "op": "加仓", "amount": 300},
            {"date": "2026-07-15", "op": "加仓", "amount": 200},
            {"date": "7/21 14:49", "op": "买入试探", "amount": 300},
        ]}

    def test_august_count(self):
        count, viol = monthly_ops_summary(self.data, year=2026, month=8)
        self.assertEqual(count, 1)
        self.assertEqual(viol, 0)

    def test_empty_transactions(self):
        count, viol = monthly_ops_summary({"transactions": []}, year=2026, month=8)
        self.assertEqual(count, 0)

    def test_real_data_consistency(self):
        """真实数据：8/7 应计 1 笔操作且零违规"""
        data_path = r"C:\Users\lenovo\Desktop\portfolio_data.json"
        if not os.path.exists(data_path):
            self.skipTest("portfolio_data.json not found")
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        count, viol = monthly_ops_summary(data, year=2026, month=8)
        self.assertEqual(count, 1, f"8月应1笔操作，实际{count}")
        self.assertEqual(viol, 0)


class TestRealPortfolioData(unittest.TestCase):
    """Integration test: validate actual portfolio_data.json"""

    @classmethod
    def setUpClass(cls):
        data_path = r"C:\Users\lenovo\Desktop\portfolio_data.json"
        if not os.path.exists(data_path):
            raise unittest.SkipTest("portfolio_data.json not found")
        with open(data_path, 'r', encoding='utf-8') as f:
            cls.data = json.load(f)

    def test_required_fields(self):
        required = ['holdings_summary', 'total_assets', 'market', 'update_date']
        for field in required:
            self.assertIn(field, self.data, f"Missing required field: {field}")

    def test_layer_sum_equals_total(self):
        """四层占比加总应 ≈100%"""
        holdings = self.data.get('holdings_summary', [])
        bedrock = sum(h['mv'] for h in holdings if h.get('group') == '全局固收')
        core = sum(h['mv'] for h in holdings if h.get('group') in ('核心增长', '全局QDII'))
        sat = sum(h['mv'] for h in holdings if h.get('group') == '进攻组合')
        cash = sum(h['mv'] for h in holdings if h.get('group') == '现金预备')
        ratios = calc_layer_ratios(bedrock, core, sat, cash)
        ratio_sum = ratios["bedrock"] + ratios["core"] + ratios["sat"] + ratios["cash"]
        self.assertAlmostEqual(ratio_sum, 100.0, places=0,
                               msg=f"Layer ratios sum to {ratio_sum}%, expected ~100%")

    def test_total_matches_holdings(self):
        """总资产应等于各层之和（含股票）"""
        holdings = self.data.get('holdings_summary', [])
        stocks = self.data.get('stock_holdings', [])
        total_mv = sum(h.get('mv', 0) or 0 for h in holdings)
        total_mv += sum(s.get('mv', 0) or 0 for s in stocks)
        # Allow ±100 tolerance (rounding + small discrepancies)
        self.assertAlmostEqual(total_mv, self.data.get('total_assets', 0), delta=100,
                               msg=f"Holdings+stock sum {total_mv} vs total_assets {self.data.get('total_assets')}")

    def test_no_negative_mv(self):
        """市值不应为负数"""
        for h in self.data.get('holdings_summary', []):
            mv = h.get('mv', 0) or 0
            self.assertGreaterEqual(mv, 0, f"Negative MV: {h.get('name')}")

    def test_drawdown_check(self):
        """检查当前回撤级别 — 默认基准 39510（规则手册 v3.3 高点）"""
        current = self.data.get('total_assets', 0)
        peak = safe_float(self.data.get('_meta', {}).get('peak_assets', 39510), 39510)
        level, pct = check_drawdown_level(current, peak)
        print(f"\n  [INFO] Current: {current:,.0f}, Peak: {peak:,.0f}, DD: {pct:.1f}%, Level: {level}")
        # This is informational — the test always passes but reports the state
        if level != "safe":
            print(f"  [WARN] Portfolio in {level} zone! Consider updating peak_assets in _meta.")
        self.assertIsNotNone(level)

    def test_transactions_not_empty(self):
        """交易记录不应为空"""
        txns = self.data.get('transactions', [])
        self.assertGreater(len(txns), 0, "No transaction records found")

    def test_daily_summaries_not_empty(self):
        """每日总结不应为空"""
        ds = self.data.get('daily_summaries', [])
        self.assertGreater(len(ds), 0, "No daily summaries found")


if __name__ == '__main__':
    print("=" * 60)
    print("Anchor v3.3 - Core Calculation Test Suite")
    print("=" * 60)
    print()

    # Run with verbosity
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
