#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交易日历测试（test_trading_calendar.py · 2026-09-21 新建 · 登记表 §六 #C1-8）

覆盖：休市日表、调休上班日≠交易日、fail-loud 边界、`add_trading_days` 方向性、
      表与官方通知的一致性、以及**反向断言**（证明「不用本日历」确实会出错）。
运行: python test_trading_calendar.py
"""
import os
import sys
import unittest
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import trading_calendar as tc


class TestClosedTable(unittest.TestCase):
    def test_weekend_dates_never_listed_in_closed(self):
        """`CLOSED` 只该收**工作日**中的休市日 —— 周末已由星期规则排除。

        防的是「把 9/26(六) 也抄进表里」这类冗余：它不会报错，只会让表越抄越长、
        最后没人能判断哪条是必须的。
        """
        bad = [s for s in tc.CLOSED if date.fromisoformat(s).weekday() >= 5]
        self.assertEqual(bad, [], f"CLOSED 不应包含周末日期：{bad}")

    def test_closed_within_verified_range(self):
        """🔴 表里的每一天都必须落在核定区间内。

        防的是**「加了新年度的休市日，却忘了扩 VERIFIED_THROUGH」** ——
        那种改法**完全无效且无声**：`_check_range` 会先把日期挡在区间外，
        `CLOSED` 里那条永远不被读到。**一个永不生效的条目比没有更危险。**
        """
        out = [s for s in tc.CLOSED
               if not (tc.VERIFIED_FROM <= date.fromisoformat(s) <= tc.VERIFIED_THROUGH)]
        self.assertEqual(out, [], f"CLOSED 有日期落在核定区间外（该条目永不生效）：{out}")


class TestIsTradingDay(unittest.TestCase):
    def test_mid_autumn_friday_is_closed(self):
        """2026-09-25 是**周五**，但中秋休市 —— 这正是「按星期几近似」会答错的那一天。"""
        self.assertEqual(date(2026, 9, 25).weekday(), 4)      # 先钉死它确实是周五
        self.assertFalse(tc.is_trading_day(date(2026, 9, 25)))

    def test_september_week_is_four_trading_days(self):
        """9/21–9/24 四个交易日，9/25 休市，9/28 开市（与 CLAUDE.md 口径一致）。"""
        for iso in ("2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-28"):
            self.assertTrue(tc.is_trading_day(date.fromisoformat(iso)), iso)
        for iso in ("2026-09-25", "2026-09-26", "2026-09-27"):
            self.assertFalse(tc.is_trading_day(date.fromisoformat(iso)), iso)

    def test_makeup_workday_is_not_trading_day(self):
        """🔴 调休上班日 ≠ 交易日 —— 2026-09-20(周日)／10-10(周六) 机关上班，**A 股不开市**。

        这是本模块最容易搞错的一点：日历上看是「工作日」，交易所里是「休市日」。
        """
        self.assertIn("2026-09-20", tc.MAKEUP_WORKDAYS)
        self.assertIn("2026-10-10", tc.MAKEUP_WORKDAYS)
        self.assertEqual(date(2026, 9, 20).weekday(), 6)     # 周日
        self.assertEqual(date(2026, 10, 10).weekday(), 5)    # 周六
        self.assertFalse(tc.is_trading_day(date(2026, 9, 20)))
        self.assertFalse(tc.is_trading_day(date(2026, 10, 10)))

    def test_accepts_datetime_as_well_as_date(self):
        self.assertTrue(tc.is_trading_day(datetime(2026, 9, 21, 14, 30)))
        self.assertFalse(tc.is_trading_day(datetime(2026, 9, 25, 14, 30)))

    def test_reverse_naive_weekday_approx_would_be_wrong(self):
        """🔴 反向断言：证明**假日表是必需的，不是装饰**。

        仅按「周一到周五」的近似（本仓旧 `freshness_watchdog` 口径）会把
        中秋 9/25 **判成交易日** —— 若本日历没有假日表，它给出的答案与近似版完全相同，
        那这 19 行 `CLOSED` 就白写了。断言两者**必须不同**：
        谁把 `CLOSED` 清空（或退回近似），本项立即失败。
        """
        d = date(2026, 9, 25)
        self.assertTrue(tc.naive_weekday_approx(d), "近似版应（错误地）判为交易日")
        self.assertFalse(tc.is_trading_day(d), "本日历必须判为休市")
        self.assertNotEqual(tc.naive_weekday_approx(d), tc.is_trading_day(d))

    def test_naive_approx_differs_on_more_than_one_day(self):
        """不止 9/25 一天 —— 差异面必须覆盖整张表，否则说明表只对了一天。"""
        diffs = [s for s in tc.CLOSED
                 if tc.naive_weekday_approx(date.fromisoformat(s)) != tc.is_trading_day(date.fromisoformat(s))]
        self.assertEqual(len(diffs), len(tc.CLOSED))


class TestFailLoud(unittest.TestCase):
    """⛔ 超出核定区间**必须报错**，不得静默回退「按星期几猜」。"""

    def test_after_horizon_raises(self):
        with self.assertRaises(tc.CalendarUnavailable):
            tc.is_trading_day(date(2027, 1, 15))

    def test_before_horizon_raises(self):
        with self.assertRaises(tc.CalendarUnavailable):
            tc.is_trading_day(date(2025, 10, 10))

    def test_add_trading_days_walking_past_horizon_raises(self):
        """走表走出边界也要报错（不能因为「起点在区间内」就放行）。"""
        with self.assertRaises(tc.CalendarUnavailable):
            tc.add_trading_days(date(2026, 12, 31), 3)

    def test_error_message_names_the_fix(self):
        """报错必须告诉人怎么修 —— 否则线上看到它只会去猜。"""
        try:
            tc.is_trading_day(date(2027, 3, 1))
        except tc.CalendarUnavailable as e:
            self.assertIn("CLOSED", str(e))
            self.assertIn("VERIFIED_THROUGH", str(e))
        else:
            self.fail("应当抛 CalendarUnavailable")


class TestAddTradingDays(unittest.TestCase):
    def test_friday_plus_three_lands_on_wednesday(self):
        """🔴 本模块立项的直接案例：9/18(周五) + 3 交易日 → **9/23(周三)**。

        旧的自然日口径给的是 **9/21(周一)** —— 只隔 **1 个交易日**。
        """
        self.assertEqual(tc.add_trading_days(date(2026, 9, 18), 3), date(2026, 9, 23))

    def test_reverse_natural_days_would_give_a_different_answer(self):
        """反向断言：两个口径在这一天**必须不同** —— 否则本项测不出任何东西。"""
        from datetime import timedelta
        base = date(2026, 9, 18)
        natural = base + timedelta(days=3)
        trading = tc.add_trading_days(base, 3)
        self.assertNotEqual(natural, trading)
        self.assertEqual(natural, date(2026, 9, 21))
        # 且自然日口径只覆盖 1 个交易日 —— 这正是「混样本」的成因
        self.assertEqual(tc.trading_days_between(base, natural), 1)

    def test_start_on_weekend_skips_forward(self):
        """起点本身非交易日时，向**前**数（8/29 周六 → 8/31、9/1、9/2）。"""
        self.assertEqual(tc.add_trading_days(date(2026, 8, 29), 3), date(2026, 9, 2))

    def test_step_over_mid_autumn(self):
        """9/24(周四) + 1 → 跳过 9/25(中秋) 与周末 → **9/28(周一)**。"""
        self.assertEqual(tc.add_trading_days(date(2026, 9, 24), 1), date(2026, 9, 28))

    def test_step_over_national_day_week(self):
        """9/30 + 1 → 跳过 10/1–10/7 长假 → **10/8**。"""
        self.assertEqual(tc.add_trading_days(date(2026, 9, 30), 1), date(2026, 10, 8))

    def test_zero_returns_same_day(self):
        d = date(2026, 9, 25)      # 休市日 +0 仍返回它自己（不做归一化，避免"悄悄改日期"）
        self.assertEqual(tc.add_trading_days(d, 0), d)

    def test_negative_direction(self):
        self.assertEqual(tc.add_trading_days(date(2026, 9, 28), -1), date(2026, 9, 24))


class TestPrevNext(unittest.TestCase):
    def test_prev_is_strictly_before(self):
        """🔴 `prev_trading_day` 必须**严格早于**入参。

        本仓 v4.5.7 的实发缺陷正是「传入当日 → 返回当日自身 ⇒ 拿当日与前一日比」。
        若本函数把交易日原样返回，那条 bug 会换一个地方复活。
        """
        self.assertEqual(tc.prev_trading_day(date(2026, 9, 21)), date(2026, 9, 18))
        self.assertNotEqual(tc.prev_trading_day(date(2026, 9, 21)), date(2026, 9, 21))

    def test_next_is_strictly_after(self):
        self.assertEqual(tc.next_trading_day(date(2026, 9, 24)), date(2026, 9, 28))
        self.assertEqual(tc.next_trading_day(date(2026, 9, 25)), date(2026, 9, 28))

    def test_prev_and_next_skip_holidays_both_ways(self):
        self.assertEqual(tc.prev_trading_day(date(2026, 9, 28)), date(2026, 9, 24))
        self.assertEqual(tc.next_trading_day(date(2026, 9, 18)), date(2026, 9, 21))


class TestTradingDaysBetween(unittest.TestCase):
    def test_half_open_interval(self):
        # [9/18, 9/21) 含 9/18 一天
        self.assertEqual(tc.trading_days_between(date(2026, 9, 18), date(2026, 9, 21)), 1)

    def test_zero_when_reversed_or_equal(self):
        self.assertEqual(tc.trading_days_between(date(2026, 9, 21), date(2026, 9, 21)), 0)
        self.assertEqual(tc.trading_days_between(date(2026, 9, 21), date(2026, 9, 18)), 0)

    def test_week_containing_mid_autumn(self):
        # [9/21, 9/28) → 9/21、9/22、9/23、9/24 = 4 天（9/25 休市，26/27 周末）
        self.assertEqual(tc.trading_days_between(date(2026, 9, 21), date(2026, 9, 28)), 4)


class TestSelfCheckBinding(unittest.TestCase):
    """表 ↔ 官方通知的一致性：`_SELF_CHECK` 把「通知写的星期」钉进运行路径。"""

    def test_self_check_table_is_not_empty(self):
        self.assertGreaterEqual(len(tc._SELF_CHECK), 10)

    def test_self_check_matches_reality(self):
        """若我抄错了区间，这里的星期会对不上（import 时已跑，此处显式再验一次）。"""
        for iso, expect_wd in tc._SELF_CHECK:
            self.assertEqual(date.fromisoformat(iso).weekday(), expect_wd, iso)


if __name__ == "__main__":
    print("=" * 60)
    print("Anchor - Trading Calendar Test Suite")
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
