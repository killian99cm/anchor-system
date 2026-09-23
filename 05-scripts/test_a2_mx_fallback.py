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
    """③ 第三级回落可用 ＋ 容忍带生效 ＋ 反向断言。"""

    def _today_boards(self, chg):
        _write_cache(days={D22: {BK_RBOT: _row("人形机器人", 0.06)}},
                     days_mx={D23: {BK_RBOT: _row("人形机器人", chg)}}, meta={})
        return gws._boards_from_mx_cache(fp.board_history_day_mx(D23), D23,
                                         fp.board_history_meta_mx(D23))

    def test_rung3_makes_it_judgeable(self):
        """days 缺当日、days_mx 有 ⇒ 用 mx 判定（值远离临界带 ⇒ 完全判定）。"""
        hit, det, note = gws._eval_a2("人形机器人", self._today_boards(-0.26), A2_PCT,
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
        """符号临界带（|chg| ≤ 0.15pp）⇒ 判不了。"""
        hit, det, note = gws._eval_a2("人形机器人", self._today_boards(-0.05), A2_PCT,
                                      prev_day={BK_RBOT: _row("人形机器人", 0.06)},
                                      prev_date=D22)
        self.assertIsNone(hit)
        self.assertFalse(det)
        self.assertIn("符号临界带", note)

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
        """分支①阈值临界带（1.85~2.15）⇒ 判不了；2.20 ⇒ 命中。"""
        hit, det, note = gws._eval_a2("人形机器人", self._today_boards(1.95), A2_PCT,
                                      prev_day={BK_RBOT: _row("人形机器人", 0.06)},
                                      prev_date=D22)
        self.assertIsNone(hit)
        self.assertFalse(det)
        self.assertIn("分支①阈值临界带", note)

        hit2, det2, _ = gws._eval_a2("人形机器人", self._today_boards(2.20), A2_PCT,
                                     prev_day={BK_RBOT: _row("人形机器人", 0.06)},
                                     prev_date=D22)
        self.assertTrue(det2)
        self.assertTrue(hit2, "≥ 2.15 应判命中（带外）")

    def test_prev_day_from_mx_also_banded(self):
        """前日值取自 mx ⇒ 同样带容忍带；带外则正常判定。"""
        _write_cache(days={},  # 前一日 push2 档缺失
                     days_mx={D22: {BK_SOLID: _row("固态电池", 0.05)},
                              D23: {BK_SOLID: _row("固态电池", 0.30)}}, meta={})
        today_mx = fp.board_history_day_mx(D23)
        prev_mx = fp.board_history_day_mx(D22)
        ab = gws._boards_from_mx_cache(today_mx, D23, None)
        # 前日 +0.05 落在带内 ⇒ 不可判
        hit, det, note = gws._eval_a2("固态电池", ab, A2_PCT, prev_day=None,
                                      prev_date=D22, prev_day_mx=prev_mx)
        self.assertIsNone(hit)
        self.assertFalse(det)
        self.assertIn("临界带", note)
        # 前日 +0.40（带外正）＋当日 +0.30（带外正）⇒ 分支② 命中
        _write_cache(days={}, days_mx={D22: {BK_SOLID: _row("固态电池", 0.40)},
                                       D23: {BK_SOLID: _row("固态电池", 0.30)}}, meta={})
        ab2 = gws._boards_from_mx_cache(fp.board_history_day_mx(D23), D23, None)
        hit2, det2, note2 = gws._eval_a2("固态电池", ab2, A2_PCT, prev_day=None,
                                         prev_date=D22,
                                         prev_day_mx=fp.board_history_day_mx(D22))
        self.assertTrue(det2, note2)
        self.assertTrue(hit2, f"连续两日带外为正 ⇒ 应命中：{note2}")

    def test_prev_missing_in_both_namespaces(self):
        """当日 mx 有值、但前日在 days 与 days_mx 都缺 ⇒ 判不了，文案须提到两个命名空间。"""
        _write_cache(days={}, days_mx={D23: {BK_RBOT: _row("人形机器人", 0.30)}}, meta={})
        ab = gws._boards_from_mx_cache(fp.board_history_day_mx(D23), D23, None)
        hit, det, note = gws._eval_a2("人形机器人", ab, A2_PCT, prev_day=None,
                                      prev_date=D22, prev_day_mx=None)
        self.assertIsNone(hit)
        self.assertFalse(det)
        self.assertIn("days_mx", note)

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
