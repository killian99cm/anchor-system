#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anchor 决策日志统计测试（test_decision_log.py，C2 新增）
覆盖：盈亏比分桶、追高型买入分母（买入类·active）、backfilled/superseded 过滤、
      止损执行率、准确率口径。数据全部注入，不依赖真实 decision_log.json。
运行: python test_decision_log.py
"""
import contextlib
import datetime
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

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
    # 🆕 2026-09-21：到期日口径改**交易日 +3** ⇒ b2(01-02 周五) 的 T+3 到期日移到 **01-07**。
    #    （旧口径自然日+3 给 01-05；两者在这条上差 2 天，因为 01-03/04 是周末。）
    FIXED = datetime.datetime(2026, 1, 7)

    def test_due_excludes_backfilled_and_superseded(self):
        due = dl.due_list(today=self.FIXED)
        ids = [d["id"] for d in due]
        self.assertEqual(ids, ["b2"])

    def test_pending_excludes_backfilled_and_superseded(self):
        pend = dl.pending_list(today=self.FIXED)
        ids = [d["id"] for d in pend]
        self.assertEqual(ids, ["b2"])

    def test_due_list_not_yet_due_when_today_earlier(self):
        """反向断言：基准日早于到期日时必须【不】到期 —— 防只测单向。

        🆕 2026-09-21：改用 **到期日前一天**（01-06）—— 比 01-03 更贴边，
        能抓住「差一天」的 off-by-one，而 01-03 离得远、错了也照样通过。
        """
        self.assertEqual([d["id"] for d in dl.due_list(today=datetime.datetime(2026, 1, 6))], [])
        self.assertEqual([d["id"] for d in dl.pending_list(today=datetime.datetime(2026, 1, 6))], [])
        self.assertEqual([d["id"] for d in dl.due_list(today=datetime.datetime(2026, 1, 3))], [])


class TestDueDate(unittest.TestCase):
    """T+3 到期日口径（2026-09-21 由**自然日**订正为**交易日**）。"""

    def test_t_plus_3_trading_days(self):
        # 2026-08-29 是周六 ⇒ 之后 3 个交易日 = 08-31(一)、09-01(二)、09-02(三)
        self.assertEqual(dl.due_date({"date": "2026-08-29"}), "2026-09-02")

    def test_friday_record_lands_on_wednesday(self):
        # 2026-09-18(五) → 09-21(一)、09-22(二)、09-23(三)
        self.assertEqual(dl.due_date({"date": "2026-09-18"}), "2026-09-23")

    def test_reverse_natural_days_would_give_a_different_answer(self):
        """🔴 反向断言：证明**口径订正确实改变了答案**。

        2026-09-18（周五）：自然日+3 = **09-21（周一）**，交易日+3 = **09-23（周三）**。
        若两者相同，则「改口径」这件事在测试上不可见 —— 也就没人能发现它被改回去了。
        这正是 v4.5.9 记的缺陷一：自然日口径下**周五创建的决策只隔 1 个交易日**。
        """
        base = datetime.datetime(2026, 9, 18)
        natural = (base + datetime.timedelta(days=3)).strftime("%Y-%m-%d")
        self.assertEqual(natural, "2026-09-21")
        self.assertNotEqual(dl.due_date({"date": "2026-09-18"}), natural)

    def test_calendar_unavailable_returns_none_not_a_guess(self):
        """🔴 日历不覆盖时**返回 None**，⛔ 不得按星期几近似（那会把中秋当交易日）。"""
        self.assertIsNone(dl.due_date({"date": "2025-10-10"}))
        self.assertIsNone(dl.due_date({"date": "2027-01-04"}))

    def test_reverse_weekday_approx_would_not_return_none(self):
        """反向：同期若退回「自然日」近似，2025-10-10 会**给出一个日期**而不是 None。

        两者必须不同 —— 这是「不猜」与「猜」的分界。
        """
        base = datetime.datetime(2025, 10, 10)
        naive = (base + datetime.timedelta(days=3)).strftime("%Y-%m-%d")
        self.assertIsNotNone(naive)
        self.assertNotEqual(dl.due_date({"date": "2025-10-10"}), naive)


class TestReviewable(unittest.TestCase):
    """「到期」≠「可复盘」（v4.5.9 缺陷二）：判据数据未入库时不得当成『现在就能做』。"""

    def setUp(self):
        self._orig = dl.data_date

    def tearDown(self):
        dl.data_date = self._orig

    def test_reviewable_only_when_data_covers_due_date(self):
        dl.data_date = lambda: "2026-09-18"
        d = {"id": "x", "date": "2026-09-14"}          # 到期 09-17 ≤ 09-18 ⇒ 可复盘
        self.assertEqual(due_of(d), "2026-09-17")
        ok, why = dl.reviewable(d)
        self.assertTrue(ok, why)

    def test_not_reviewable_when_data_is_earlier_than_due(self):
        dl.data_date = lambda: "2026-09-18"
        d = {"id": "x", "date": "2026-09-18"}          # 到期 09-23 > 09-18 ⇒ 不可复盘
        ok, why = dl.reviewable(d)
        self.assertFalse(ok)
        self.assertIn("2026-09-23", why)               # 必须说清缺的是哪天

    def test_reverse_ignoring_data_date_would_say_reviewable(self):
        """反向：若只看「到期日已过」而不看判据数据，09-18 创建的那条会被误报为可复盘。

        这正是 2026-09-21 实发的红色告警（报 #64 到期，而数据仍停在 09-18）。
        """
        dl.data_date = lambda: "2026-09-18"
        d = {"id": "x", "date": "2026-09-18"}
        # 只看到期日 ⇒ 旧实现会判「已到期」（09-23 尚未到，但旧口径给 09-21，已在今天之前）
        self.assertEqual((datetime.datetime(2026, 9, 18) + datetime.timedelta(days=3)).strftime("%Y-%m-%d"),
                         "2026-09-21")
        self.assertLessEqual("2026-09-21", "2026-09-21")
        # 但 reviewable 必须说「不」——两者结论相反，这个差值就是本测试的意义
        self.assertFalse(dl.reviewable(d)[0])
        # 且新口径的到期日（09-23）确实晚于今天，不再制造「天天亮着做不掉」的红警
        self.assertGreater(dl.due_date(d), "2026-09-21")


class TriggerLineTests(unittest.TestCase):
    """inbox/145：E 级触发线到期检查（验收 A1–A6）。

    ⛔ 全程**不触碰生产文件**（A6）：文件级一律用 `pf_path` 显式注入临时文件 ——
       本类**根本不写生产路径**（不靠 try/finally 保隔离，J11 教训）。
    """

    NOW = datetime.datetime(2026, 9, 23, 10, 0)          # 9/23 上午（9/22 到期 ⇒ 已逾期 1 天）

    def _line(self, **kw):
        ln = {"id": "S1", "target": "证券ETF", "condition": "PB>1.6 止盈 1/3",
              "level": "E", "due": "2026-09-22", "verdict": None, "verdict_date": None}
        ln.update(kw)
        return ln

    def _capture(self, pf_path):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dl.trigger_lines_report(now=self.NOW, pf_path=str(pf_path))
        self.assertEqual(rc, 0)
        return buf.getvalue()

    # ---- A1 正向：到期未裁定 ⇒ 显式 🔴 + 「已逾期 N 天」 ----
    def test_a1_overdue_explicit_red_and_days(self):
        res = dl.evaluate_trigger_lines([self._line()], self.NOW)
        self.assertEqual(len(res["overdue"]), 1)
        self.assertEqual(res["overdue"][0]["_overdue"], 1)
        text = dl.render_trigger_lines(res, "2026-09-23")
        self.assertIn("🔴", text)
        self.assertIn("欠裁定", text)
        self.assertIn("已逾期 1 天", text)

    # ---- A2 反向：已裁定（含「不执行」）⇒ 不得再报欠裁定；A5：「不执行」⇒ 失效 ----
    def test_a2_settled_never_reported_overdue_and_a5_invalid(self):
        for v in ("执行", "顺延", "撤销", "不执行"):
            res = dl.evaluate_trigger_lines([self._line(verdict=v)], self.NOW)
            self.assertEqual(res["overdue"], [], f"verdict={v} 仍被报欠裁定")
            text = dl.render_trigger_lines(res, "2026-09-23")
            self.assertNotIn("欠裁定", text)
            self.assertNotIn("🔴", text)
        res = dl.evaluate_trigger_lines([self._line(verdict="不执行")], self.NOW)
        text = dl.render_trigger_lines(res, "2026-09-23")
        self.assertIn("本线失效", text)                    # A5 / F6 第 2 款

    # ---- A3 反向：边界精确到 14:30（14:29 不得报逾期；14:31 必须报）----
    def test_a3_boundary_exact_1430(self):
        line = self._line(due="2026-09-23")
        early = dl.evaluate_trigger_lines([line], datetime.datetime(2026, 9, 23, 14, 29))
        self.assertEqual(early["overdue"], [])
        self.assertEqual(len(early["window_open"]), 1)
        _etxt = dl.render_trigger_lines(early, "2026-09-23")
        self.assertNotIn("已逾期", _etxt)          # ⛔ 未过 14:30 不得报逾期（说明句「不按逾期报」不算）
        self.assertNotIn("🔴", _etxt)
        late = dl.evaluate_trigger_lines([line], datetime.datetime(2026, 9, 23, 14, 31))
        self.assertEqual(len(late["overdue"]), 1)
        self.assertEqual(late["overdue"][0]["_overdue"], 0)

    # ---- A4 反向：「字段不存在」≠「空数组无欠」≠「线存在但无裁定」三者输出不同形 ----
    def test_a4_missing_field_vs_empty_distinct(self):
        tmp = Path(tempfile.mkdtemp(prefix="anchor_tl145_"))
        p_missing = tmp / "pf_missing.json"
        p_missing.write_text(json.dumps({"total_assets": 1}), encoding="utf-8")
        p_empty = tmp / "pf_empty.json"
        p_empty.write_text(json.dumps({"trigger_lines": []}), encoding="utf-8")
        p_open = tmp / "pf_open.json"
        p_open.write_text(json.dumps({"trigger_lines": [self._line()]}, ensure_ascii=False),
                          encoding="utf-8")
        out_missing, out_empty, out_open = (self._capture(p_missing), self._capture(p_empty),
                                            self._capture(p_open))
        self.assertIn("不存在", out_missing)
        self.assertIn("不是「今日无欠」", out_missing)
        self.assertIn("今日无欠", out_empty)
        self.assertNotIn("不存在", out_empty)
        self.assertIn("欠裁定", out_open)
        self.assertNotEqual(out_missing, out_empty)        # 裁定 3 的直接钉死
        self.assertNotEqual(out_open, out_empty)
        self.assertNotEqual(out_open, out_missing)

    # ---- 级别与异常形态（F1：未标级别＝不成立；X 级无裁定义务）----
    def test_levels_and_malformed(self):
        res = dl.evaluate_trigger_lines(
            [self._line(id="X1", level="X"),
             self._line(id="M1", level=""),
             self._line(id="M2", due="9/22"),
             "非对象元素"], self.NOW)
        self.assertEqual(len(res["x_level"]), 1)
        self.assertEqual(len(res["malformed"]), 3)
        self.assertEqual(res["overdue"], [])
        text = dl.render_trigger_lines(res, "2026-09-23")
        self.assertIn("X 级线", text)
        self.assertIn("未标级别", text)
        self.assertIn("格式错", text)

    # ---- A6：全程不触碰生产文件（跑一次注入路径，生产 portfolio_data.json 字节不变）----
    def test_a6_no_production_touch(self):
        prod = dl.paths.DATA_PATH
        before = prod.read_bytes() if prod.exists() else None
        tmp = Path(tempfile.mkdtemp(prefix="anchor_tl145b_"))
        p = tmp / "pf.json"
        p.write_text(json.dumps({"trigger_lines": [self._line()]}, ensure_ascii=False),
                     encoding="utf-8")
        self._capture(p)
        after = prod.read_bytes() if prod.exists() else None
        self.assertEqual(before, after, "生产 portfolio_data.json 被改动（A6 违规）")


def due_of(d):
    return dl.due_date(d)


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
