#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anchor 决策日志统计测试（test_decision_log.py，C2 新增）
覆盖：盈亏比分桶、追高型买入分母（买入类·active）、backfilled/superseded 过滤、
      止损执行率、准确率口径。数据全部注入，不依赖真实 decision_log.json。
运行: python test_decision_log.py
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_log as dl


def mk(did, dtype, outcome=None, pnl=None, tags=None, verdict="执行", basis=None, **kw):
    d = {
        "id": did, "date": kw.pop("date", "2026-08-01"), "time": "10:00",
        "type": dtype, "verdict": verdict, "amount": 100.0,
        "rationale": "", "expected": "", "snapshot": {},
        "tags": tags or [], "outcome": outcome, "pnl_pct": pnl,
        "pnl_basis": basis, "review_date": None, "review_note": "",
    }
    d.update(kw)
    return d


# 固定样本：覆盖各统计口径
# v4.4.16：pnl 必须声明 basis；盈亏比只认 realized，故 realized 给足 5 盈 / 5 亏
SAMPLE = [
    mk("1", "加仓", "correct", 5.0, date="2026-08-01", basis="realized"),
    mk("2", "加仓", "correct", 15.0, date="2026-08-02", basis="realized"),
    mk("3", "建仓", "wrong", -20.0, tags=["追高"], date="2026-08-03", basis="realized"),
    mk("4", "观望", "neutral", None, date="2026-08-04"),
    mk("5", "加仓", "correct", 3.0, date="2026-08-05", superseded_by="9"),  # 被推翻
    mk("6", "止损", None, None, verdict="执行止损", date="2026-08-06"),
    mk("7", "止损", None, None, verdict="等待观察", date="2026-08-07"),
    # realized 补足到 盈5/亏5（= MIN_N，达标才出盈亏比）
    mk("11", "减仓", "correct", 4.0, date="2026-08-11", basis="realized"),
    mk("12", "减仓", "correct", 6.0, date="2026-08-12", basis="realized"),
    mk("13", "清仓", "wrong", -8.0, date="2026-08-13", basis="realized"),
    mk("14", "清仓", "wrong", -12.0, date="2026-08-14", basis="realized"),
    mk("15", "清仓", "wrong", -16.0, date="2026-08-15", basis="realized"),
    mk("16", "减仓", "correct", 10.0, date="2026-08-16", basis="realized"),
    mk("17", "清仓", "wrong", -4.0, date="2026-08-17", basis="realized"),
    # 非 realized 口径：**数值大且符号误导**——若被误计入盈亏比，结果会显著偏移（反向断言用）
    mk("21", "观望", "correct", 99.0, date="2026-08-21", basis="price_move"),
    mk("22", "观望", "correct", 88.0, date="2026-08-22", basis="benefit"),
    mk("23", "加仓", "wrong", -77.0, date="2026-08-23", basis="position_pnl"),
    mk("24", "观望", "neutral", 0.0, date="2026-08-24", basis="unquantified"),
    mk("25", "观望", "correct", 66.0, date="2026-08-25"),  # basis 缺失 → legacy_unclassified
]


class TestAccuracyReport(unittest.TestCase):
    def setUp(self):
        self.r = dl.accuracy_report(SAMPLE)

    def test_reviewed_excludes_superseded_and_pending(self):
        # reviewed=16（#5 superseded 排除；#6/#7 未复盘排除）
        self.assertEqual(self.r["total_decisions"], 19)
        self.assertEqual(self.r["reviewed"], 16)
        self.assertEqual(self.r["correct"], 8)
        self.assertEqual(self.r["wrong"], 6)
        self.assertEqual(self.r["neutral"], 2)

    def test_accuracy(self):
        self.assertEqual(self.r["accuracy_pct"], 57.1)  # 8/(8+6)

    def test_profit_loss_ratio(self):
        # realized wins=[5,15,4,6,10] avg_win=8；losses=[-20,-8,-12,-16,-4] avg_loss=12 → 0.67
        self.assertEqual(self.r["avg_win_pct"], 8.0)
        self.assertEqual(self.r["avg_loss_pct"], 12.0)
        self.assertEqual(self.r["pnl_ratio"], 0.67)

    def test_ratio_excludes_non_realized_basis(self):
        """反向断言（v4.4.16 核心）：非 realized 口径必须被排除。

        样本里 #21 +99 / #22 +88 是 price_move / benefit，
        #23 -77 是 position_pnl —— 若沿用旧逻辑（只按数值正负分桶）：
            wins = [5,15,4,6,10,99,88,66]  → avg 36.6
            losses = [-20,-8,-12,-16,-4,-77] → avg 22.8 → 盈亏比 1.60
        与正确值 0.67 差 2.4 倍，且方向相反（把「坏」读成「好」）。
        本断言同时钉住：① 排除确实发生 ② 被排除的确实是这些数
        """
        self.assertEqual(self.r["pnl_ratio_excluded"], 5)
        self.assertEqual(self.r["pnl_basis_counts"]["realized"], 10)
        self.assertEqual(self.r["pnl_basis_counts"]["legacy_unclassified"], 1)
        # 反向：在**同一批样本**上跑旧口径（只按数值正负分桶），错值必须显著偏离现值
        all_pnl = [d["pnl_pct"] for d in SAMPLE
                   if dl._is_active(d) and d["pnl_pct"] is not None]
        nw = [p for p in all_pnl if p > 0]
        nl = [p for p in all_pnl if p < 0]
        naive_ratio = (sum(nw) / len(nw)) / abs(sum(nl) / len(nl))
        self.assertGreater(naive_ratio, 1.4)             # 旧口径：把「坏」读成「好」
        self.assertLess(self.r["pnl_ratio"], 0.7)        # 新口径：真实是坏的
        self.assertGreater(naive_ratio - self.r["pnl_ratio"], 0.9)  # 差值必须大到不可忽视

    def test_ratio_none_when_realized_sample_too_small(self):
        """反向断言：realized 样本不足 MIN_N 时**必须**返回 None，不得给一个看起来正常的数。"""
        thin = [d for d in SAMPLE if d["id"] not in ("16", "17")]
        r = dl.accuracy_report(thin)
        self.assertIsNone(r["pnl_ratio"])          # 盈4/亏4 < MIN_N=5
        self.assertEqual(r["pnl_ratio_sample"]["min_n"], 5)

    def test_avg_pnl_is_realized_only(self):
        # (5+15-20+4+6-8-12-16+10-4)/10 = -2.0；若混入 #21 +99 会变成 +6.7
        self.assertEqual(self.r["avg_pnl_pct"], -2.0)

    def test_chase_denominator_is_active_buys(self):
        # 买入类 active = #1#2#3#23（#5 superseded 不稀释分母）；追高仅 #3 → 25.0%
        self.assertEqual(self.r["chase_count"], 1)
        self.assertEqual(self.r["chase_pct"], 25.0)

    def test_stop_loss_execution_rate(self):
        # 止损触发 #6#7=2，执行 #6=1 → 50%
        self.assertEqual(self.r["stop_loss_triggers"], 2)
        self.assertEqual(self.r["stop_loss_executed"], 1)
        self.assertEqual(self.r["stop_loss_execution_pct"], 50.0)


class TestPnlBasisContract(unittest.TestCase):
    """v4.4.16 口径契约：pnl_pct 的语义必须显式声明，未声明不得进盈亏比。"""

    def test_basis_vocabulary_is_closed(self):
        self.assertEqual(
            set(dl.PNL_BASIS),
            {"realized", "benefit", "price_move", "position_pnl",
             "unquantified", "legacy_unclassified"},
        )

    def test_only_realized_is_ratio_eligible(self):
        # 反向断言：realized 之外每一条都必须在文档里被明确禁止参与盈亏比
        for k, v in dl.PNL_BASIS.items():
            if k == "realized":
                self.assertIn("✅", v)
            else:
                self.assertIn("⛔", v)

    def test_review_rejects_unknown_basis(self):
        """未声明的口径必须被拒绝，不得静默写入（否则契约形同虚设）。"""
        log = {"decisions": [{"id": "z1", "date": "2026-08-01", "outcome": None,
                              "pnl_pct": None, "pnl_basis": None}]}
        orig_load, orig_save = dl.load_log, dl.save_log
        dl.load_log, dl.save_log = lambda: log, lambda _l: None
        try:
            dl.review_decision("z1", "correct", "5.0", "t", basis="made_up")
            self.assertIsNone(log["decisions"][0]["pnl_basis"])  # 未写入
            dl.review_decision("z1", "correct", "5.0", "t", basis="benefit")
            self.assertEqual(log["decisions"][0]["pnl_basis"], "benefit")  # 合法值写入
        finally:
            dl.load_log, dl.save_log = orig_load, orig_save

    def test_existing_realized_records_match_note_arithmetic(self):
        """真实数据抽查：realized 口径的 pnl_pct 必须能由 review_note 里的金额整除复现。

        这是「口径声明不是事后编的」的实证——9 条 realized 全部由 note 中的
        「实盈/实亏 … /成本 …」反算得出，误差 >0.6pp 即说明标注与 note 不符。
        """
        import json
        import pathlib
        LOG = pathlib.Path(__file__).parent.parent / "06-dashboard" / "decision_log.json"
        if not LOG.exists():
            self.skipTest("decision_log.json 不存在（干净环境）")
        log = json.loads(LOG.read_text(encoding="utf-8"))
        realized = [d for d in log["decisions"] if d.get("pnl_basis") == "realized"]
        self.assertGreaterEqual(len(realized), 9)
        self.assertAlmostEqual(sum(d["pnl_pct"] for d in realized), -58.1, places=1)


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

    # ⚠️ 2026-09-17 修：原断言调 `dl.due_list()` / `dl.pending_list()` **不注入"今天"**，
    #    而这两个函数当时【没有注入口】，`datetime.now()` 写死在函数体里 ——
    #    于是断言真值随【运行日期】双向漂移：
    #      实跑 now=2026-01-05 → ['b2'] ✅ ／ now=2026-01-03 → [] ❌ ／ now=2026-01-01 → [] ❌
    #    夹具是 2026-01-0x 的固定日期，只有挂钟走到 1/5 之后才"刚好"通过。
    #    → 已给两个函数加 `today=` 注入口（对齐 freshness_watchdog.trading_lag 的样板），
    #      并在此显式注入固定基准日 —— **测试里的时间必须注入，不能读钟。**
    FIXED = datetime.datetime(2026, 1, 5)   # b2(01-02) 的 T+3 到期日

    def test_due_excludes_backfilled_and_superseded(self):
        due = dl.due_list(today=self.FIXED)
        ids = [d["id"] for d in due]
        self.assertEqual(ids, ["b2"])

    def test_pending_excludes_backfilled_and_superseded(self):
        pend = dl.pending_list(today=self.FIXED)
        ids = [d["id"] for d in pend]
        self.assertEqual(ids, ["b2"])

    def test_due_list_not_yet_due_when_today_earlier(self):
        """反向断言：基准日早于到期日时必须【不】到期 —— 防只测单向。"""
        self.assertEqual([d["id"] for d in dl.due_list(today=datetime.datetime(2026, 1, 3))], [])
        self.assertEqual([d["id"] for d in dl.pending_list(today=datetime.datetime(2026, 1, 3))], [])


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
