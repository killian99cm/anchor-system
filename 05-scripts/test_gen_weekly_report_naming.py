#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`gen_weekly_report.py` 命名与落盘目录回归测试（2026-09-25 · 单 33）

背景（两处实测缺陷，均已修）：
  ① **周数基准日错**：原实现无论 `--week` 传什么都用 `date.today()` 算文件名 ⇒
     2026-09-24 实测 `--week 09-07`／`09-14`／无参 **三周全部写成 W4**（互相覆盖）。
  ② **落盘目录不符约定**：原 `KB_DIR` ＝ `04-reviews/` 根，而既有周报实际在
     `04-reviews/weekly/`（`weekly_report_202608_*.md`、`weekly_report_202609_W1.md`）。

🔴 **反向断言**：把命名改回「以今天为基准」⇒ 本测试**必须失败**（防回退）。

运行：python test_gen_weekly_report_naming.py
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import paths  # noqa: E402


def _stub_week_days():
    """给 2026-09-07 ~ 09-11 造 5 个交易日的假数据（只为让 build_report 有东西可渲染）。"""
    days = []
    d = date(2026, 9, 7)
    for _ in range(5):
        days.append({"date": d.isoformat(), "day": "周X",
                     "total_assets": 48000.0, "portfolio_day_pnl": -10.0,
                     "shanghai": {"close": 3900.0, "change": "-0.2%"},
                     "kechuang50": {"close": 1600.0, "change": "-0.3%"},
                     "market_note": "夹具", "holdings_note": "夹具"})
        d += timedelta(days=1)
    return days


class TestWeeklyNaming(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="anchor_wkname_")
        os.environ["ANCHOR_REVIEWS_DIR"] = self.tmp           # 若 paths 支持覆盖则生效
        import importlib
        import paths as _p
        importlib.reload(_p)
        import gen_weekly_report as g
        importlib.reload(g)
        self.g = g
        # 强制把输出根指到临时目录（⛔ 不碰生产 04-reviews/）
        self.g.KB_DIR = self.tmp
        self.g.load_data = lambda: {}
        self.g.get_week_days = lambda data, ws: _stub_week_days()
        self.g.build_report = lambda data, wd: "# 夹具周报\n"

    def _run(self, argv):
        """跑一次 main() 并返回**本次产出**的相对路径列表。

        🔴 必须先清空输出根（2026-09-25 修）：否则同一用例内多次调用会**累积文件**，
           `os.walk` 顺序不保证 ⇒ `got[0]` 取到的可能是**上一次**的产物
           （首版即因此误报：09-14 用例读到 09-07 的 W2）。⇒ 这是**测试夹具缺陷**，非被测代码问题。
        """
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.makedirs(self.tmp, exist_ok=True)
        old = sys.argv[:]
        sys.argv = ["gen_weekly_report.py"] + argv
        try:
            self.g.main()
        finally:
            sys.argv = old
        got = []
        for root, _dirs, files in os.walk(self.tmp):
            for f in files:
                got.append(os.path.relpath(os.path.join(root, f), self.tmp))
        return sorted(got)

    def test_week_arg_controls_filename(self):
        """`--week 09-07` ⇒ 文件名必须是 **W2**（9/7 所在周＝月内第 2 周段）。"""
        got = self._run(["--week", "09-07"])
        self.assertTrue(got, "未产出任何文件")
        name = got[0].replace("\\", "/")
        self.assertIn("weekly/", name, f"❌ 未落到 weekly/ 子目录：{name}")
        self.assertRegex(name, r"weekly_report_202609_W2\.md$",
                         f"❌ --week 09-07 应得 W2，实得：{name}")

    def test_week_arg_09_14_is_w3(self):
        got = self._run(["--week", "09-14"])
        self.assertRegex(got[0].replace("\\", "/"), r"weekly_report_202609_W3\.md$",
                         f"❌ --week 09-14 应得 W3，实得：{got[0]}")

    def test_reverse_today_based_naming_would_collide(self):
        """🔴 **反向断言**：若命名改回「以今天为基准」，则 09-07 与 09-14 会**同落一个文件**
        ⇒ 本用例据此判红（防回退）。"""
        a = self._run(["--week", "09-07"])
        b = self._run(["--week", "09-14"])
        self.assertNotEqual(a, b, "❌ 两个不同周产出同名文件 ⇒ 命名仍以「今天」为基准（回退）")

    def test_default_uses_today(self):
        """无参数 ⇒ 以今天为基准（ISO 惯例：按本周周四所属月/段）。"""
        got = self._run([])
        t = date.today()
        anchor = t + timedelta(days=(3 - t.weekday()))      # 本周周四
        w = (anchor.day - 1) // 7 + 1
        self.assertRegex(got[0].replace("\\", "/"),
                         rf"weekly_report_{anchor.year}{anchor.month:02d}_W{w}\.md$",
                         f"❌ 无参应得今天所在周，实得：{got[0]}")

    def test_iso_convention_reproduces_existing_filenames(self):
        """🔴 **契约测试**：ISO 惯例必须**逐一复现仓库现存周报名**（否则「对齐既有规范」是假的）。"""
        cases = {"09-07": "weekly_report_202609_W2.md",
                 "09-14": "weekly_report_202609_W3.md",
                 "09-21": "weekly_report_202609_W4.md"}
        for wk, want in cases.items():
            got = self._run(["--week", wk])
            self.assertTrue(got[0].replace("\\", "/").endswith(want),
                            f"❌ --week {wk} 应为 {want}，实得 {got[0]}")
        # 跨月周：8/31（周一）那周归属 9 月第 1 段 ⇒ 202609_W1（与仓库现存一致）
        got = self._run(["--week", "08-31"])
        self.assertTrue(got[0].replace("\\", "/").endswith("weekly_report_202609_W1.md"),
                        f"❌ --week 08-31 应归 202609_W1（该周周四 9/3），实得 {got[0]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
