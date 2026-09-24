#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2 判据「mx 口径回落」测试（裁决 #C1-20 · 2026-09-23 · 用户授权）

背景：东财 `push2` 全族被 IP 限流 ⇒ `days`（push2 全量）当日档会缺；此前只能落回
「判不了」（fail-closed）。裁决允许**第三级回落**读 mx 口径，但两口径**不同指标族**
（mx＝成份区间涨跌幅(流通市值加权平均) vs push2 `f3`＝板块指数涨跌幅）⇒ 必须：

  ① **独立命名空间**：mx 值进 `days_mx`，⛔ 不得混进 `days`（`days` 的不变量是「全量」，
     混入 partial 会让日后把「没取到」误读成「该板块不存在」）；
  ② **逐日标源**：`days_mx_meta` 记口径名/源/条数；
  ③ **容忍带**（`MX_TOL_PP`）：符号临界带与分支①阈值临界带内一律**判不了**（fail-closed）。

🔴 本文件含 **反向断言**（本仓惯例「改回旧写法即失败」）：
   · 去掉 mx 回落 ⇒ 必须回到「判不了」（证明该级是承重的）；
   · 去掉 `_mx` 标记 ⇒ 临界带值会给出**结论**（证明带是从标记来的，不是摆设）。

运行: python test_a2_mx_fallback.py   （用 ANCHOR_BOARD_HISTORY 隔离，⛔ 不碰生产缓存）
"""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 🔴 真隔离：换路径，不靠 try/finally（v4.5.1 教训：进程被硬杀时 finally 不执行）
_TMP = tempfile.mkdtemp(prefix="anchor_a2mx_")
os.environ["ANCHOR_BOARD_HISTORY"] = os.path.join(_TMP, "board_pct_history.json")

import fetch_public as fp                  # noqa: E402
import gen_watchlist_status as gws         # noqa: E402

A2_PCT = 2.0
D22, D23 = "2026-09-22", "2026-09-23"
BK_RBOT, BK_SOLID = "BK1184", "BK0968"


def _write_cache(days=None, days_mx=None, meta=None):
    hist = {"schema": 1, "days": days or {}, "updated_at": "2026-09-23 22:00"}
    if days_mx is not None:
        hist["days_mx"] = days_mx
        hist["days_mx_meta"] = meta or {}
    with io.open(fp._board_history_path(), "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False)


def _row(name, chg, bt="概念板块"):
    return {"name": name, "chg_pct": chg, "board_type": bt}


class TestNamespaceIsolation(unittest.TestCase):
    """① mx 写入必须落在 days_mx，且 days 一字不动。"""

    def test_record_mx_does_not_touch_days(self):
        _write_cache(days={D22: {BK_RBOT: _row("人形机器人", 0.06)}},
                     days_mx={}, meta={})
        r = fp.board_history_record_mx(
            {BK_RBOT: _row("人形机器人", -0.26)}, D23,
            metric="成份区间涨跌幅(流通市值加权平均)", source="mx-data")
        self.assertTrue(r.get("recorded"), r)
        # ① days 未污染 —— 这是本裁决最关键的不变量
        self.assertIsNone(fp.board_history_day(D23), "⛔ mx 值混进了 days 命名空间")
        mx = fp.board_history_day_mx(D23)
        self.assertIsNotNone(mx, "days_mx 未写入")
        self.assertAlmostEqual(float(mx[BK_RBOT]["chg_pct"]), -0.26, places=6)
        # ② 逐日标源
        meta = fp.board_history_meta_mx(D23) or {}
        self.assertIn("加权平均", str(meta.get("metric")), "未记录口径名")
        self.assertEqual(meta.get("source"), "mx-data")
        # ③ 前一日（push2 档）不受影响
        self.assertIsNotNone(fp.board_history_day(D22))
        self.assertIsNone(fp.board_history_day_mx(D22))

    def test_mx_shape_marked_partial_and_mx(self):
        _write_cache(days_mx={D23: {BK_RBOT: _row("人形机器人", -0.26)}}, meta={})
        ab = gws._boards_from_mx_cache(fp.board_history_day_mx(D23), D23,
                                       fp.board_history_meta_mx(D23))
        self.assertFalse(ab["complete"], "mx 档必须标 complete=False（非全量）")
        self.assertIn("mx覆盖(非全量)", ab["universes"],
                      "找不到板块时不得被读成「该板块不存在」")
        self.assertTrue(ab["by_name"]["人形机器人"].get("_mx"),
                        "row 缺 _mx 标记 ⇒ 容忍带不会生效（静默退化为裸判定）")


class TestThirdRungAndTolerance(unittest.TestCase):
    """③ 第三级回落可用 ＋ 容忍带生效 ＋ 反向断言。

    🔴 带值 `fp.MX_TOL_PP` 于 2026-09-24 由 **1.0pp** 取代初版 0.15pp（首次对拉实测：
       `|Δpp|` max **0.8451**／mean 0.3813，且出现 **1 条判定翻转**＝人形机器人
       mx −0.2593 判「不成立」而 push2 +0.30 判「命中」）。本类中的临界值**随带宽度
       重新标定**，⛔ 不得写死数字（写死即失去对带值的约束力）。
    """

    def _today_boards(self, chg):
        _write_cache(days={D22: {BK_RBOT: _row("人形机器人", 0.06)}},
                     days_mx={D23: {BK_RBOT: _row("人形机器人", chg)}}, meta={})
        return gws._boards_from_mx_cache(fp.board_history_day_mx(D23), D23,
                                         fp.board_history_meta_mx(D23))

    def test_rung3_makes_it_judgeable(self):
        """days 缺当日、days_mx 有 ⇒ 用 mx 判定（值远离临界带 ⇒ 完全判定）。"""
        far_neg = -(fp.MX_TOL_PP + 0.5)          # 带外负：跌破符号临界带才有资格「完全判定」
        hit, det, note = gws._eval_a2("人形机器人", self._today_boards(far_neg), A2_PCT,
                                      prev_day={BK_RBOT: _row("人形机器人", 0.06)},
                                      prev_date=D22)
        self.assertTrue(det, f"应可完全判定：{note}")
        self.assertFalse(hit)
        self.assertIn("mx 口径", note)

    def test_reverse_without_rung3_it_is_undecidable(self):
        """🔴 反向：拿掉 mx 档（等价旧写法）⇒ 必须回到「判不了」。"""
        hit, det, note = gws._eval_a2("人形机器人", {}, A2_PCT,
                                      prev_day={BK_RBOT: _row("人形机器人", 0.06)},
                                      prev_date=D22)
        self.assertFalse(det, "回落被拿掉后竟仍能判定 ⇒ 该级不是承重的")
        self.assertIsNone(hit)

    def test_sign_band_is_fail_closed(self):
        """符号临界带（|chg| ≤ MX_TOL_PP）⇒ 判不了。"""
        hit, det, note = gws._eval_a2("人形机器人", self._today_boards(-0.05), A2_PCT,
                                      prev_day={BK_RBOT: _row("人形机器人", 0.06)},
                                      prev_date=D22)
        self.assertIsNone(hit)
        self.assertFalse(det)
        self.assertIn("符号临界带", note)

    def test_first_duila_measured_value_must_be_undecidable(self):
        """🔴 **实测值回归**：人形机器人 2026-09-23 mx ＝ **−0.2593** ⇒ 必须「判不了」。

        这是 2026-09-24 对拉实测抓到的**唯一一条判定翻转**：旧带（0.15）下该值判
        「不成立（完全）」，而同日 push2（+0.30%）判「**命中**」⇒ 旧带**放行了本该禁买的**。
        ⛔ 本断言是这条缺陷的守门人：带值若被改小到 ≤0.21（＝|−0.2593| 之下），本测试必红。
        """
        hit, det, note = gws._eval_a2("人形机器人", self._today_boards(-0.2593), A2_PCT,
                                      prev_day={BK_RBOT: _row("人形机器人", 0.06)},
                                      prev_date=D22)
        self.assertIsNone(hit, f"实测翻转值竟给出结论 ⇒ 容忍带又兜不住了：{note}")
        self.assertFalse(det)

    def test_reverse_old_band_would_have_granted_it(self):
        """🔴 反向断言：把带值**改回初版 0.15** ⇒ 同值（−0.2593）必须变回「完全判定不成立」。

        证明「新带是承重的」且「旧带确实会放行」—— 即本类不是摆设。
        """
        old = fp.MX_TOL_PP
        fp.MX_TOL_PP = 0.15
        try:
            hit, det, note = gws._eval_a2("人形机器人", self._today_boards(-0.2593), A2_PCT,
                                          prev_day={BK_RBOT: _row("人形机器人", 0.06)},
                                          prev_date=D22)
        finally:
            fp.MX_TOL_PP = old
        self.assertTrue(det, f"改回 0.15 竟仍判不了 ⇒ 该测试抓不到回归：{note}")
        self.assertFalse(hit)
        self.assertIn("完全判定", note)

    def test_reverse_without_mx_flag_band_disappears(self):
        """🔴 反向：同值但**不带** `_mx` 标记（走 push2 档）⇒ 必须给出结论。

        证明「带」是从 `_mx` 标记来的 —— 若标记丢失，会静默变成裸判定。
        """
        boards = {"rows": [dict(_row("人形机器人", -0.05), code=BK_RBOT)],
                  "by_name": {"人形机器人": dict(_row("人形机器人", -0.05), code=BK_RBOT)},
                  "universes": {}, "complete": True, "ts": "test"}
        hit, det, note = gws._eval_a2("人形机器人", boards, A2_PCT,
                                      prev_day={BK_RBOT: _row("人形机器人", 0.06)},
                                      prev_date=D22)
        self.assertTrue(det, f"非 mx 值不应带容忍带：{note}")
        self.assertFalse(hit)

    def test_branch1_band_is_fail_closed(self):
        """分支①阈值临界带（a2−tol ~ a2+tol）⇒ 判不了；带外高值 ⇒ 命中。"""
        inside = A2_PCT - fp.MX_TOL_PP + 0.1
        hit, det, note = gws._eval_a2("人形机器人", self._today_boards(inside), A2_PCT,
                                      prev_day={BK_RBOT: _row("人形机器人", 0.06)},
                                      prev_date=D22)
        self.assertIsNone(hit)
        self.assertFalse(det)
        self.assertIn("分支①阈值临界带", note)

        outside = A2_PCT + fp.MX_TOL_PP + 0.2
        hit2, det2, _ = gws._eval_a2("人形机器人", self._today_boards(outside), A2_PCT,
                                     prev_day={BK_RBOT: _row("人形机器人", 0.06)},
                                     prev_date=D22)
        self.assertTrue(det2)
        self.assertTrue(hit2, "带外高值应判命中")

    def test_mx_branch2_region_is_empty_by_construction(self):
        """🔴 **带变宽的必然代价（显式钉住，⛔ 别当成 bug）**：当 `MX_TOL_PP ≥ a2_pct/2`
        时，分支②可用区间 `(tol, a2−tol)` **为空** ⇒ **mx 侧永远给不出「连续 2 日飘红」
        的判定**（只能「命中（≥a2+tol）」或「不成立（≤−tol）」或「判不了」）。

        这是**正确的**：带的宽度＝已测得的跨口径偏差，偏差比待判的差还要大时，
        「两日各 +0.5%」与「两日各 −0.5%」本就**不可区分** ⇒ 诚实答案就是判不了（fail-closed）。
        """
        if fp.MX_TOL_PP < A2_PCT / 2:
            self.skipTest(f"带值 {fp.MX_TOL_PP} < a2/2 ⇒ 分支②区间非空，本不变量不适用")
        edge = A2_PCT - fp.MX_TOL_PP + 0.05      # 落在 (tol, a2−tol) 若该区间非空
        self.assertLessEqual(fp.MX_TOL_PP, edge, "构造前提被破坏")
        hit, det, note = gws._eval_a2("人形机器人", self._today_boards(edge), A2_PCT,
                                      prev_day={BK_RBOT: _row("人形机器人", 1.50)},
                                      prev_date=D22)
        self.assertIsNone(hit, note)
        self.assertFalse(det)
        self.assertIn("分支①阈值临界带", note)

    def test_prev_day_from_mx_also_banded(self):
        """前日值取自 mx ⇒ 同样带容忍带；带外则正常判定。

        （当日值此处走 **push2 档**〔不带带〕—— 因为带变宽后 mx 侧的 `(tol, a2−tol)` 区间
        为空，分支②只能在「当日 push2 ＋ 前日 mx」这一组合下被真正走到。）
        """
        today_push2 = {"rows": [dict(_row("固态电池", 0.30), code=BK_SOLID)],
                       "by_name": {"固态电池": dict(_row("固态电池", 0.30), code=BK_SOLID)},
                       "universes": {}, "complete": True, "ts": "test"}
        # 前日 mx +0.40 落在带内 ⇒ 不可判
        _write_cache(days={}, days_mx={D22: {BK_SOLID: _row("固态电池", 0.40)}}, meta={})
        hit, det, note = gws._eval_a2("固态电池", today_push2, A2_PCT, prev_day=None,
                                      prev_date=D22,
                                      prev_day_mx=fp.board_history_day_mx(D22))
        self.assertIsNone(hit)
        self.assertFalse(det)
        self.assertIn("临界带", note)
        # 前日 mx +1.50（带外正）＋当日 +0.30 ⇒ 分支② 命中
        _write_cache(days={}, days_mx={D22: {BK_SOLID: _row("固态电池", 1.50)}}, meta={})
        hit2, det2, note2 = gws._eval_a2("固态电池", today_push2, A2_PCT, prev_day=None,
                                         prev_date=D22,
                                         prev_day_mx=fp.board_history_day_mx(D22))
        self.assertTrue(det2, note2)
        self.assertTrue(hit2, f"前日带外为正、当日为正 ⇒ 应命中：{note2}")

    def test_prev_missing_in_both_namespaces(self):
        """前日在 `days` 与 `days_mx` 都缺 ⇒ 判不了，文案须提到两个命名空间。

        ⚠️ 当日值此处走 **push2 档**：带变宽后 mx 侧的 `(tol, a2−tol)` 区间为空
        ⇒ 「需要前日」这条路径**在 mx 当日值下已不可达**（见
        `test_mx_branch2_region_is_empty_by_construction`）。本用例改测同一保护意图：
        **前日两命名空间皆缺时不得放行**，且文案必须点名两个命名空间。
        """
        boards = {"rows": [dict(_row("人形机器人", 0.30), code=BK_RBOT)],
                  "by_name": {"人形机器人": dict(_row("人形机器人", 0.30), code=BK_RBOT)},
                  "universes": {}, "complete": True, "ts": "push2"}
        hit, det, note = gws._eval_a2("人形机器人", boards, A2_PCT, prev_day=None,
                                      prev_date=D22, prev_day_mx=None)
        self.assertIsNone(hit)
        self.assertFalse(det)
        self.assertIn("days_mx", note)
        self.assertIn("days", note)

    def test_mx_partial_must_not_read_as_board_missing(self):
        """🔴 mx 档找不到该主题时，⛔ 不得写成「该板块不存在」（部分覆盖 ≠ 不存在）。"""
        _write_cache(days_mx={D23: {BK_RBOT: _row("人形机器人", 0.30)}}, meta={})
        ab = gws._boards_from_mx_cache(fp.board_history_day_mx(D23), D23, None)
        hit, det, note = gws._eval_a2("固态电池", ab, A2_PCT, prev_day=None, prev_date=D22)
        self.assertIsNone(hit)
        self.assertFalse(det)
        self.assertIn("不等于「该板块不存在」", note)
        self.assertNotIn("双宇宙板块榜", note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
