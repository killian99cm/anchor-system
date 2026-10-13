#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2 判据「push2 部分抢救档（days_push2_partial）」读取侧接线测试（2026-10-13）

背景：东财限流导致 `days`（全量）在 10/8、10/9、10/12 缺档；10/13 以 push2his
板块日K抢救关键板块落盘 `days_push2_partial`（口径与 f3 族逐位吻合，10 个重叠板块
|Δ|=0.00pp）。但 A2 读取侧此前只读 `days → days_mx` ⇒ 抢救档读不到（fail-closed）。
本次接线：

  当日链：live → days → **days_push2_partial** → days_mx
  前日链：days → **days_push2_partial** → days_mx

🔴 与 mx 档的本质区别：本档与 `days` **同口径族**（push2 f3）⇒ **不施容忍带**；
   仅**覆盖窄**（非全量）⇒ 找不到 ≠ 不存在（universes 键已明示）。

🔴 反向断言（承重，本仓惯例「改回旧写法即失败」）：
   · 拿掉 partial 档 ⇒ 同一夹具必须回到「判不了」（证明该级承重）；
   · 同一值放 mx 档 ⇒ 带内判不了；放 partial 档 ⇒ 正常判定（证明带只对 mx 生效）；
   · days 档有该板块时 ⇒ 必须用 days（优先级，防抢救档覆盖全量档）。

运行: python test_a2_partial_fallback.py（用 ANCHOR_BOARD_HISTORY 隔离，⛔ 不碰生产缓存）
"""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 🔴 真隔离：换路径，不靠 try/finally（v4.5.1 教训：进程被硬杀时 finally 不执行）
_TMP = tempfile.mkdtemp(prefix="anchor_a2partial_")
os.environ["ANCHOR_BOARD_HISTORY"] = os.path.join(_TMP, "board_pct_history.json")

import fetch_public as fp                  # noqa: E402
import gen_watchlist_status as gws         # noqa: E402

A2_PCT = 2.0
D11, D12 = "2026-10-09", "2026-10-12"
BK_SOLID = "BK0968"


def _write_cache(partial=None, partial_meta=None, days=None, days_mx=None, meta=None):
    hist = {"schema": 1, "days": days or {}, "updated_at": "2026-10-13 14:00"}
    if partial is not None:
        hist["days_push2_partial"] = partial
        hist["days_push2_partial_meta"] = partial_meta or {}
    if days_mx is not None:
        hist["days_mx"] = days_mx
        hist["days_mx_meta"] = meta or {}
    with io.open(fp._board_history_path(), "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False)


def _row(name, chg, bt="概念板块"):
    return {"name": name, "chg_pct": chg, "board_type": bt}


def _push2_today(chg):
    r = dict(_row("固态电池", chg))
    r["code"] = BK_SOLID
    return {"rows": [r], "by_name": {"固态电池": r}, "universes": {},
            "complete": True, "ts": "test"}


class TestPartialShape(unittest.TestCase):
    """读取函数与新形状（非全量可辨识、⛔ 不打 _mx 标记）。"""

    def test_partial_reader_and_shape(self):
        _write_cache(partial={D12: {BK_SOLID: _row("固态电池", -2.51)}})
        day = fp.board_history_day_partial(D12)
        self.assertIsNotNone(day)
        self.assertIsNone(fp.board_history_day_partial("1970-01-01"),
                          "不存在的日期必须返 None（⛔ 不得回退到最近一条）")
        ab = gws._boards_from_partial_cache(day, D12)
        self.assertFalse(ab["complete"], "部分抢救档必须标 complete=False（非全量）")
        self.assertIn("push2部分覆盖(非全量)", ab["universes"],
                      "找不到板块时不得被读成「该板块不存在」")
        self.assertNotIn("_mx", ab["by_name"]["固态电池"],
                         "partial 与 days 同口径族 ⇒ ⛔ 不得带 _mx 标记（否则误施容忍带）")
        self.assertTrue(str(ab["ts"]).startswith("partial:"))

    def test_partial_miss_not_read_as_board_missing(self):
        """🔴 partial 档找不到该板块时，⛔ 不得写成「该板块不存在」（部分覆盖 ≠ 不存在）。"""
        _write_cache(partial={D12: {BK_SOLID: _row("固态电池", -2.51)}})
        ab = gws._boards_from_partial_cache(fp.board_history_day_partial(D12), D12)
        hit, det, note = gws._eval_a2("人形机器人", ab, A2_PCT, prev_day=None, prev_date=D11)
        self.assertIsNone(hit)
        self.assertFalse(det)
        self.assertIn("不等于", note)
        self.assertIn("部分抢救档", note)
        self.assertNotIn("双宇宙板块榜", note)


class TestPrevChain(unittest.TestCase):
    """前日三档链：days → days_push2_partial（无带）→ days_mx（带）。"""

    def test_prev_from_partial_makes_branch2_judgeable(self):
        """当日 +0.5（需前日）＋ 前日仅在 partial（+0.4，>0）⇒ 分支②命中、完全判定。"""
        _write_cache(partial={D12: {BK_SOLID: _row("固态电池", 0.40)}})
        hit, det, note = gws._eval_a2("固态电池", _push2_today(0.50), A2_PCT,
                                      prev_day=None, prev_date=D12,
                                      prev_day_partial=fp.board_history_day_partial(D12))
        self.assertTrue(det, note)
        self.assertTrue(hit, f"前日为正且当日为正 ⇒ 应命中分支②：{note}")
        self.assertIn("days_push2_partial", note,
                      "来源可见（R4）：回退路径必须显式标出实际来源，⛔ 不得静默")

    def test_prev_from_partial_negative_no_hit(self):
        _write_cache(partial={D12: {BK_SOLID: _row("固态电池", -2.51)}})
        hit, det, note = gws._eval_a2("固态电池", _push2_today(0.50), A2_PCT,
                                      prev_day=None, prev_date=D12,
                                      prev_day_partial=fp.board_history_day_partial(D12))
        self.assertTrue(det, note)
        self.assertFalse(hit)
        self.assertIn("≤ 0", note)

    def test_reverse_without_partial_undecidable(self):
        """🔴 反向（本单最重要）：拿掉 partial 档（等价接线前写法）⇒ 同一夹具必须「判不了」。"""
        _write_cache(partial={D12: {BK_SOLID: _row("固态电池", 0.40)}})
        hit, det, note = gws._eval_a2("固态电池", _push2_today(0.50), A2_PCT,
                                      prev_day=None, prev_date=D12)
        self.assertIsNone(hit, f"未接线竟仍可判定 ⇒ 接线不承重：{note}")
        self.assertFalse(det)

    def test_no_band_on_partial_reverse_mx_banded(self):
        """🔴 带只对 mx 生效：同一 +0.40 值，partial ⇒ 命中；mx ⇒ 带内判不了。"""
        _write_cache(partial={D12: {BK_SOLID: _row("固态电池", 0.40)}},
                     days_mx={D12: {BK_SOLID: _row("固态电池", 0.40)}})
        hit_p, det_p, note_p = gws._eval_a2("固态电池", _push2_today(0.50), A2_PCT,
                                            prev_day=None, prev_date=D12,
                                            prev_day_partial=fp.board_history_day_partial(D12))
        self.assertTrue(hit_p, f"partial 档（同口径族）不应施带：{note_p}")
        hit_m, det_m, note_m = gws._eval_a2("固态电池", _push2_today(0.50), A2_PCT,
                                            prev_day=None, prev_date=D12,
                                            prev_day_mx=fp.board_history_day_mx(D12))
        self.assertIsNone(hit_m, f"mx 档带内竟给结论（容忍带失效）：{note_m}")
        self.assertFalse(det_m)

    def test_full_day_wins_over_partial(self):
        """🔴 优先级：前日 days（全量）有该板块时 ⛔ 不得读 partial（防抢救档覆盖全量档）。"""
        _write_cache(days={D12: {BK_SOLID: _row("固态电池", 0.40)}},
                     partial={D12: {BK_SOLID: _row("固态电池", -0.90)}})
        hit, det, note = gws._eval_a2("固态电池", _push2_today(0.50), A2_PCT,
                                      prev_day=fp.board_history_day(D12), prev_date=D12,
                                      prev_day_partial=fp.board_history_day_partial(D12))
        self.assertTrue(hit, f"应取 days 档（+0.40 ⇒ 命中）；若误取 partial（−0.90）则不命中：{note}")
        self.assertNotIn("days_push2_partial", note, "用了 partial 档却不动声色 ⇒ 优先级错误")

    def test_missing_in_all_three_mentions_all(self):
        """三档皆缺 ⇒ 判不了，且文案须点名三个命名空间（读者须知道查过哪些地方）。"""
        _write_cache(partial={D12: {BK_SOLID: _row("固态电池", 0.40)}})
        hit, det, note = gws._eval_a2("固态电池", _push2_today(0.50), A2_PCT,
                                      prev_day=None, prev_date=D11,
                                      prev_day_partial=None, prev_day_mx=None)
        self.assertIsNone(hit)
        self.assertFalse(det)
        for ns in ("days", "days_push2_partial", "days_mx"):
            self.assertIn(ns, note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
