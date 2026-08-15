#!/usr/bin/env python3
"""
Anchor v3.3 核心计算测试
覆盖: 四层占比、收益率、回撤线、盈亏计算
运行: python test_calculations.py
"""
import copy
import json
import os
import re
import sys
import unittest
from datetime import date

# ===== 被测逻辑：从 data_processor import 权威实现（单一事实源） =====
# data_processor.py 是本文件所在目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
from data_processor import fp, rate, safe_float, monthly_ops_summary, is_manual_operation, get_peak_assets, drawdown_status, process_all, build_snapshot

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

def check_drawdown_level(current_total, peak):
    """Return drawdown level using the shared drawdown contract."""
    status = drawdown_status(current_total, peak)
    dd_pct = status["dd_pct"]
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
        """Simulate actual portfolio (8/14): bed=18809, core=6120, sat=5790, cash=4838"""
        ratios = calc_layer_ratios(18809, 6120, 5790, 4838)
        total = ratios["total"]
        self.assertGreater(total, 35000)
        self.assertLess(total, 36000)
        # Bedrock should be largest (~53%)
        self.assertGreater(ratios["bedrock"], 50)


class TestDrawdownCheck(unittest.TestCase):
    # 回撤基准（8/15 上移后）：¥35,655（8/10 本周最高点）
    PEAK = 35655

    def test_above_peak(self):
        level, pct = check_drawdown_level(36000, self.PEAK)
        self.assertEqual(level, "safe")
        self.assertGreaterEqual(pct, 0)

    def test_warn(self):
        level, pct = check_drawdown_level(33500, self.PEAK)
        self.assertEqual(level, "warn")
        self.assertLessEqual(pct, -5)
        self.assertGreater(pct, -10)

    def test_critical_10(self):
        level, pct = check_drawdown_level(32000, self.PEAK)
        self.assertEqual(level, "critical-10")
        self.assertLessEqual(pct, -10)
        self.assertGreater(pct, -15)

    def test_critical_15(self):
        level, pct = check_drawdown_level(29000, self.PEAK)
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

    def test_dca_not_counted(self):
        """定投/出入金不计入月操作限额（与交易备注口径一致）"""
        data = {"transactions": [
            {"date": "2026-08-07", "op": "加仓", "amount": 300},
            {"date": "2026-08-10", "op": "定投", "amount": 135,
             "note": "智能定投自动扣款（非手动操作，不计入月限额）"},
            {"date": "2026-08-12", "op": "余额宝转出", "amount": 500},
            {"date": "2026-08-13", "op": "赎回到账", "amount": 1000},
        ]}
        count, viol = monthly_ops_summary(data, year=2026, month=8)
        self.assertEqual(count, 1)
        self.assertEqual(viol, 0)

    def test_real_data_consistency(self):
        """真实数据：monthly_ops_summary 与数据参考月手动操作数口径一致（不耦合具体月份）"""
        data_path = paths.DATA_PATH
        if not os.path.exists(data_path):
            self.skipTest("portfolio_data.json not found")
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        m = re.search(r'(\d{4})-(\d{1,2})', str(data.get('update_date') or data.get('update_time') or ''))
        if not m:
            self.skipTest("update_date 缺失，无法确定参考月")
        year, month = int(m.group(1)), int(m.group(2))
        count, viol = monthly_ops_summary(data, year=year, month=month)
        prefixes = (f"{year}-{month:02d}", f"{month}/", f"{month:02d}/")
        manual = sum(1 for t in data.get('transactions', [])
                     if str(t.get('date', '')).startswith(prefixes) and is_manual_operation(t))
        self.assertEqual(count, manual,
                         f"{year}-{month:02d} monthly_ops_summary={count} 但手动交易实际 {manual} 笔")
        self.assertEqual(viol, sum(1 for t in data.get('transactions', [])
                                   if '违规' in str(t.get('note', '')) and str(t.get('date', '')).startswith(prefixes)))


class TestRealPortfolioData(unittest.TestCase):
    """Integration test: validate actual portfolio_data.json"""

    @classmethod
    def setUpClass(cls):
        data_path = paths.DATA_PATH
        if not os.path.exists(data_path):
            raise unittest.SkipTest("portfolio_data.json not found")
        with open(data_path, 'r', encoding='utf-8') as f:
            cls.data = json.load(f)

    def test_required_fields(self):
        required = ['holdings_summary', 'total_assets', 'market', 'update_date', '_meta']
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

    def test_peak_assets_required(self):
        """peak_assets 缺失时应直接失败，而不是静默回退"""
        with self.assertRaises(ValueError):
            get_peak_assets({'_meta': {}})

    def test_drawdown_check(self):
        """检查当前回撤级别 — 使用 _meta.peak_assets 作为唯一基准"""
        current = self.data.get('total_assets', 0)
        peak = get_peak_assets(self.data)
        level, pct = check_drawdown_level(current, peak)
        expected = drawdown_status(current, peak)
        print(f"\n  [INFO] Current: {current:,.0f}, Peak: {peak:,.0f}, DD: {pct:.1f}%, Level: {level}")
        self.assertEqual(expected['dd_pct'], pct)
        if level != "safe":
            print(f"  [WARN] Portfolio in {level} zone! Check drawdown_state in process_all output.")
        self.assertIsNotNone(level)

    def test_process_all_state_contract(self):
        """process_all 应输出统一 state 合同"""
        embed = process_all(self.data)
        self.assertIn('state', embed)
        self.assertIn('drawdown_state', embed)
        self.assertIn('ops_state', embed)
        self.assertIn('risk_state', embed)
        self.assertIn('freeze_state', embed)
        self.assertIn('factor_clusters', embed)
        self.assertIn('holding_counts', embed)
        self.assertIn('layers', embed)
        self.assertIn('layer_order', embed)
        self.assertIn('layer_meta', embed)
        self.assertEqual(embed['state'].get('drawdown', {}).get('peak_assets'), get_peak_assets(self.data))
        self.assertEqual(embed['state'].get('ops', {}).get('count'), embed.get('aug_ops'))
        self.assertEqual(embed['layer_order'], ['bedrock', 'core', 'sat', 'cash'])
        self.assertEqual([row.get('key') for row in embed.get('layers', [])], embed['layer_order'])
        self.assertEqual(set(embed['holding_counts'].get('by_layer', {}).keys()), set(embed['layer_order']))

    def test_process_all_dynamic_holding_contract(self):
        """process_all 应随新增持仓动态扩展合同"""
        base = process_all(self.data)
        data = copy.deepcopy(self.data)
        data.setdefault('holdings_summary', []).append({
            'name': '示例新基金',
            'mv': 1234,
            'pnl': 12,
            'day_pnl': 1,
            'group': '核心增长',
            'layer': 'core',
        })
        data.setdefault('stock_holdings', []).append({
            'name': '示例新股票',
            'mv': 4321,
            'pnl': -5,
            'day_pnl': -1,
            'group': '进攻组合',
            'layer': 'sat',
        })
        embed = process_all(data)
        self.assertEqual(embed['holding_counts']['active'], base['holding_counts']['active'] + 2)
        self.assertEqual(embed['holding_counts']['fund'], base['holding_counts']['fund'] + 1)
        self.assertEqual(embed['holding_counts']['stock'], base['holding_counts']['stock'] + 1)
        self.assertEqual(embed['holding_counts']['by_layer']['core'], base['holding_counts']['by_layer']['core'] + 1)
        self.assertEqual(embed['holding_counts']['by_layer']['sat'], base['holding_counts']['by_layer']['sat'] + 1)
        self.assertIn('示例新基金', [i.get('n') for i in embed['core']])
        self.assertIn('示例新股票', [i.get('n') for i in embed['sat']])

    def test_process_all_stock_shares_price_contract(self):
        """股票缺少 mv 时，应由 shares*price 计入市值、层级和快照合同"""
        data = copy.deepcopy(self.data)
        data.setdefault('stock_holdings', []).append({
            'name': '示例按股数股票',
            'shares': 10,
            'price': 123.4,
            'pnl': 4,
            'day_pnl': 1,
            'layer': 'core',
        })
        base = process_all(self.data)
        embed = process_all(data)
        self.assertEqual(embed['stockMv'], base['stockMv'] + 1234)
        self.assertEqual(embed['holding_counts']['stock'], base['holding_counts']['stock'] + 1)
        self.assertEqual(embed['holding_counts']['by_layer']['core'], base['holding_counts']['by_layer']['core'] + 1)
        self.assertEqual(embed['layers'][1]['mv'], base['layers'][1]['mv'] + 1234)
        self.assertIn('示例按股数股票', [i.get('n') for i in embed['core']])

    def test_build_snapshot_state_contract(self):
        """build_snapshot 应保留统一 state 与关键风险字段"""
        embed = process_all(self.data)
        snapshot = build_snapshot(embed)
        self.assertIn('state', snapshot)
        self.assertIn('drawdown_state', snapshot)
        self.assertIn('ops_state', snapshot)
        self.assertIn('freeze_state', snapshot)
        self.assertIn('holding_counts', snapshot)
        self.assertIn('layers', snapshot)
        self.assertIn('layer_order', snapshot)
        self.assertIn('layer_meta', snapshot)
        self.assertEqual(snapshot['peak_assets'], embed['peak_assets'])
        self.assertEqual(snapshot['dd_pct'], embed['dd_pct'])
        self.assertEqual(snapshot['layer_order'], embed['layer_order'])
        self.assertEqual(snapshot['holding_counts'], embed['holding_counts'])
        self.assertEqual(snapshot['layers'], embed['layers'])
        self.assertEqual(snapshot['layer_meta'], embed['layer_meta'])

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
