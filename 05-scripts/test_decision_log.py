#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anchor 决策日志统计测试（test_decision_log.py，C2 新增）
覆盖：盈亏比分桶、追高型买入分母（买入类·active）、backfilled/superseded 过滤、
      止损执行率、准确率口径。数据全部注入，不依赖真实 decision_log.json。
运行: python test_decision_log.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_log as dl


def mk(did, dtype, outcome=None, pnl=None, tags=None, verdict="执行", **kw):
    d = {
        "id": did, "date": kw.pop("date", "2026-08-01"), "time": "10:00",
        "type": dtype, "verdict": verdict, "amount": 100.0,
        "rationale": "", "expected": "", "snapshot": {},
        "tags": tags or [], "outcome": outcome, "pnl_pct": pnl,
        "review_date": None, "review_note": "",
    }
    d.update(kw)
    return d


# 固定样本：覆盖各统计口径
SAMPLE = [
    mk("1", "加仓", "correct", 5.0, date="2026-08-01"),
    mk("2", "加仓", "correct", 15.0, date="2026-08-02"),
    mk("3", "建仓", "wrong", -20.0, tags=["追高"], date="2026-08-03"),
    mk("4", "观望", "neutral", None, date="2026-08-04"),
    mk("5", "加仓", "correct", 3.0, date="2026-08-05", superseded_by="9"),  # 被推翻
    mk("6", "止损", None, None, verdict="执行止损", date="2026-08-06"),
    mk("7", "止损", None, None, verdict="等待观察", date="2026-08-07"),
]


class TestAccuracyReport(unittest.TestCase):
    def setUp(self):
        self.r = dl.accuracy_report(SAMPLE)

    def test_reviewed_excludes_superseded_and_pending(self):
        # reviewed = #1-#4（#5 superseded 排除；#6/#7 未复盘排除）
        self.assertEqual(self.r["total_decisions"], 7)
        self.assertEqual(self.r["reviewed"], 4)
        self.assertEqual(self.r["correct"], 2)
        self.assertEqual(self.r["wrong"], 1)
        self.assertEqual(self.r["neutral"], 1)

    def test_accuracy(self):
        self.assertEqual(self.r["accuracy_pct"], 66.7)  # 2/(2+1)

    def test_profit_loss_ratio(self):
        # wins=[5,15] avg_win=10；losses=[-20] avg_loss=20 → 盈亏比 0.5
        self.assertEqual(self.r["avg_win_pct"], 10.0)
        self.assertEqual(self.r["avg_loss_pct"], 20.0)
        self.assertEqual(self.r["pnl_ratio"], 0.5)

    def test_chase_denominator_is_active_buys(self):
        # 买入类 active = #1#2#3（#5 superseded 不稀释分母）；追高仅 #3 → 33.3%
        self.assertEqual(self.r["chase_count"], 1)
        self.assertEqual(self.r["chase_pct"], 33.3)

    def test_stop_loss_execution_rate(self):
        # 止损触发 #6#7=2，执行 #6=1 → 50%
        self.assertEqual(self.r["stop_loss_triggers"], 2)
        self.assertEqual(self.r["stop_loss_executed"], 1)
        self.assertEqual(self.r["stop_loss_execution_pct"], 50.0)


class TestDueFiltering(unittest.TestCase):
    """due_list / pending_list 必须排除 backfilled 流水补录与 superseded。"""
    OLD = [
        mk("b1", "加仓", None, date="2026-01-01", backfilled=True),   # 补录噪声，排除
        mk("b2", "加仓", None, date="2026-01-02"),                    # 正常未复盘，保留
        mk("b3", "加仓", None, date="2026-01-03", superseded_by="x"), # 被推翻，排除
    ]

    def setUp(self):
        self._orig = dl.load_log
        dl.load_log = lambda: {"decisions": self.OLD}

    def tearDown(self):
        dl.load_log = self._orig

    def test_due_excludes_backfilled_and_superseded(self):
        due = dl.due_list()
        ids = [d["id"] for d in due]
        self.assertEqual(ids, ["b2"])

    def test_pending_excludes_backfilled_and_superseded(self):
        pend = dl.pending_list()
        ids = [d["id"] for d in pend]
        self.assertEqual(ids, ["b2"])


class TestDueDate(unittest.TestCase):
    def test_t_plus_3_natural_days(self):
        self.assertEqual(dl.due_date({"date": "2026-08-29"}), "2026-09-01")


if __name__ == "__main__":
    print("=" * 60)
    print("Anchor - Decision Log Statistics Test Suite")
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
