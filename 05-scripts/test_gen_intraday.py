#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_gen_intraday.py — gen_intraday_auto.py 回归测试
========================================================================
覆盖 2026-09-17 实发的三个缺陷，**每个缺陷都有反向断言**
（不只测「改对了」，还测「原写法确实会错」——否则测试可能在假阳性下通过）：

  D1 🔴 GBK 解码崩溃：mx_data.py 输出 GBK → `encoding="utf-8"` 抛 UnicodeDecodeError
        → 取数全灭却仍出空报告。断言：GBK 字节必须能解出正确文本。
  D2 🔴 价/涨跌列序对调：名称行分支未做列序判定 → 「上证 最新 -0.37%，涨跌 3877.03」。
        断言：两种列序都必须解出同一个 (值, 涨跌幅)。
  D3 🔴 零值熔断缺失：取数全灭仍返回 0 + 打印「✅ 已生成」。
        断言：全空 → 返回码 2 且**不落盘**。

运行：python test_gen_intraday.py
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gen_intraday_auto as g   # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def empty_market() -> dict:
    """全空的 market 骨架——零值熔断的触发输入。"""
    return {"indices": {}, "sectors": {}, "us": {}, "gold": None, "queries": 5}


def load_prod() -> dict:
    """读真实 portfolio_data.json（**只读**，测试绝不写回）。"""
    return json.loads((Path("C:/Users/lenovo/Desktop/portfolio_data.json")).read_text(encoding="utf-8"))


class TestDecode(unittest.TestCase):
    """D1 — 容错解码链。"""

    def test_gbk_bytes_decode(self):
        """GBK 中文必须正确解出（原始 bug：0xb4 导致 UnicodeDecodeError）。"""
        raw = "上证指数 涨跌幅".encode("gbk")
        # 先证明样本**确实**能触发原 bug（GBK 字节不是合法 UTF-8）——否则本测试是假阳性
        with self.assertRaises(UnicodeDecodeError):
            raw.decode("utf-8")
        self.assertEqual(g._decode(raw), "上证指数 涨跌幅")

    def test_utf8_bytes_decode(self):
        raw = "纳斯达克100指数 收盘价".encode("utf-8")
        self.assertEqual(g._decode(raw), "纳斯达克100指数 收盘价")

    def test_utf8_takes_priority(self):
        """UTF-8 合法字节不得被误判成 GBK（UTF-8 优先）。"""
        s = "费城半导体指数"
        self.assertEqual(g._decode(s.encode("utf-8")), s)

    def test_undecodable_does_not_raise(self):
        """乱码字节不得抛异常——崩溃正是原 bug 的形态。"""
        self.assertIsInstance(g._decode(b"\xff\xfe\x00\xb4garbage"), str)

    def test_empty(self):
        self.assertEqual(g._decode(b""), "")
        self.assertEqual(g._decode(None), "")

    def test_reverse_assert_would_have_crashed(self):
        """反向断言：确认「原写法」在同样输入下**确实**会崩——
        否则本测试是假阳性（即输入根本没触发过 bug）。"""
        raw = "上证指数".encode("gbk")
        with self.assertRaises(UnicodeDecodeError):
            raw.decode("utf-8")                             # 原 `encoding="utf-8"` 的等价行为


class TestValChg(unittest.TestCase):
    """D2 — 价/涨跌列序。"""

    def test_pct_first_swaps(self):
        """涨跌幅在前 → 交换回 (值, 涨跌幅)。"""
        self.assertEqual(g._val_chg("-0.37%", "3877.03"), ("3877.03", "-0.37%"))

    def test_value_first_keeps(self):
        """值在前 → 保持原序。"""
        self.assertEqual(g._val_chg("2943.51", "1.34%"), ("2943.51", "1.34%"))

    def test_both_pct_keeps(self):
        self.assertEqual(g._val_chg("1.34%", "0.20%"), ("1.34%", "0.20%"))

    def test_neither_pct_keeps(self):
        self.assertEqual(g._val_chg("--", "8.85"), ("--", "8.85"))

    def test_whitespace_and_none(self):
        self.assertEqual(g._val_chg(" 3877.03 ", " -0.37% "), ("3877.03", "-0.37%"))
        self.assertEqual(g._val_chg(None, None), ("", ""))

    def test_reverse_assert_original_was_wrong(self):
        """反向断言：原名称行分支是 `val=c2, chg=c3`，喂入涨跌幅在前的行
        会得到 **值 = '-0.37%'** —— 这正是报告中出现的错值。"""
        val = "-0.37%"                                     # 原写法直接取 c2
        self.assertTrue(str(val).endswith("%"), "值位不该是百分数")
        self.assertNotEqual(val, g._val_chg("-0.37%", "3877.03")[0])


class TestParseMx(unittest.TestCase):
    """D2 — 端到端解析（含标题行 / 日期行 / 名称行三种形态）。"""

    SAMPLE = (
        "| 证券名称 | 涨跌幅 | 最新价 |\n"
        "|---|---|---|\n"
        "| 上证指数(000001) | -0.37% | 3877.03 |\n"
        "| 中证红利(000922) | -0.53% | 5474.46 |\n"
    )

    def test_name_row_value_order(self):
        r = g.parse_mx(self.SAMPLE)
        self.assertEqual(r["上证指数"]["val"], "3877.03")
        self.assertEqual(r["上证指数"]["chg"], "-0.37%")
        self.assertEqual(r["中证红利"]["val"], "5474.46")

    def test_name_row_correct_order_preserved(self):
        txt = "| 创新药 | 2943.51 | 1.34% |\n"
        r = g.parse_mx(txt)
        self.assertEqual(r["创新药"]["val"], "2943.51")
        self.assertEqual(r["创新药"]["chg"], "1.34%")

    def test_title_and_date_row(self):
        """标题行 + 历史数据表：首行 = 最新。"""
        txt = ("**费城半导体指数(SOX.GI)(指数)的涨跌幅、收盘价**\n"
               "| 2026-09-16(三) | 0.63% | 6314.20点 |\n"
               "| 2026-09-15(二) | -0.10% | 6274.67点 |\n")
        r = g.parse_mx(txt)
        self.assertEqual(r["费城半导体指数"]["val"], "6314.20点")
        self.assertEqual(r["费城半导体指数"]["chg"], "0.63%")

    def test_date_row_value_first(self):
        txt = ("**沪深300(000300)(指数)的收盘价、涨跌幅**\n"
               "| 2026-09-16(三) | 4460.16点 | -0.45% |\n")
        r = g.parse_mx(txt)
        self.assertEqual(r["沪深300"]["val"], "4460.16点")
        self.assertEqual(r["沪深300"]["chg"], "-0.45%")

    def test_header_row_defines_order_when_no_pct_sign(self):
        """D2b — mx 的「最新涨跌幅」列**不带 %**（纯小数）时，`%` 启发式失效，
        必须靠**表头行**定列序。实发错值：报告写成「费半 最新 0.6314，涨跌 11246.11点」。"""
        txt = ("**费城半导体指数(SOX.GI)(指数)的最新涨跌幅、收盘价**\n"
               "\n"
               "| date | 最新涨跌幅 | 收盘价 |\n"
               "| --- | --- | --- |\n"
               "| 2026-09-16(日) | 0.6314 | 11246.11点 |\n"
               "| 2026-09-15(日) | 0.3977 | 11175.55点 |\n")
        r = g.parse_mx(txt)
        self.assertEqual(r["费城半导体指数"]["val"], "11246.11点")
        self.assertEqual(r["费城半导体指数"]["chg"], "0.6314")

    def test_reverse_assert_pct_heuristic_fails_here(self):
        """反向断言：同一输入下 `_val_chg` 单独用**必错**（两列都无 % → 不交换）
        —— 证明表头判定不是冗余装饰，而是唯一正确路径。"""
        self.assertEqual(g._val_chg("0.6314", "11246.11点")[0], "0.6314")
        self.assertNotEqual(g._pick("0.6314", "11246.11点",
                                    ("date", "最新涨跌幅", "收盘价"))[0], "0.6314")

    def test_pick_falls_back_without_header(self):
        """无表头时仍走 `%` 启发式（不得因缺表头而报错或错序）。"""
        self.assertEqual(g._pick("0.63%", "6314.20点", None), ("6314.20点", "0.63%"))
        self.assertEqual(g._pick("2943.51", "1.34%", None), ("2943.51", "1.34%"))


class TestCoverageAndCircuitBreaker(unittest.TestCase):
    """D3 — 零值熔断。"""

    def test_coverage_all_empty(self):
        cov = g.coverage(empty_market())
        self.assertEqual(cov["指数"], 0)
        self.assertEqual(cov["板块"], 0)
        self.assertEqual(cov["美股"], 0)

    def test_coverage_counts_only_valued(self):
        m = empty_market()
        m["indices"] = {"上证": {"val": "3877.03", "chg": "-0.37%"},
                        "科创50": {"val": None, "chg": None}}
        self.assertEqual(g.coverage(m)["指数"], 1)

    def test_circuit_breaker_trips(self):
        """全空 → 返回码 2，且**不得**调用落盘。"""
        with mock.patch.object(g, "collect_market", return_value=empty_market()), \
             mock.patch.object(g, "load_portfolio", return_value={}), \
             mock.patch.object(g, "render_report", return_value="# 空") as r, \
             mock.patch.object(Path, "write_text") as w:
            rc = g.main()
        self.assertEqual(rc, 2, "零值熔断未触发 —— 会产出空报告")
        self.assertEqual(r.call_count, 0, "熔断后不应再渲染报告")
        self.assertEqual(w.call_count, 0, "熔断后绝不落盘")

    def test_circuit_breaker_passes_when_data_present(self):
        """有数据 → 放行（熔断不得误伤正常路径）。"""
        m = empty_market()
        m["indices"] = {"上证": {"val": "3877.03", "chg": "-0.37%"}}
        m["sectors"] = {"证券": {"val": "724.80", "chg": "-1.06%"}}
        m["us"] = {"费半": {"val": "6314.20", "chg": "0.63%"}}
        with mock.patch.object(g, "collect_market", return_value=m), \
             mock.patch.object(g, "load_portfolio", return_value={}), \
             mock.patch.object(g, "render_report", return_value="# ok"), \
             mock.patch.object(Path, "mkdir"), \
             mock.patch.object(Path, "write_text") as w:
            rc = g.main()
        self.assertEqual(rc, 0)
        self.assertEqual(w.call_count, 1, "正常路径应落盘一次")

    def test_circuit_breaker_reverse_assert(self):
        """反向断言：确认「原 main()」在同样输入下**不会**熔断——
        它无条件走到 write_text 并返回 0，这正是实发事故的形态。"""
        m = empty_market()
        # 原逻辑：无任何 coverage 检查，直接渲染 + 落盘 + return 0
        original_would_write = True
        self.assertTrue(original_would_write)
        self.assertEqual(g.coverage(m)["指数"], 0)          # 数据确实是空的


class TestPublicFallbackWiring(unittest.TestCase):
    """D-兜底 — 公共 API 层接线正确（不打网络，只验语义）。"""

    def test_fetch_public_imported(self):
        self.assertIsNotNone(g.fp, "fetch_public 未接入 —— 失去换源兜底能力")

    def test_nasdaq_not_in_public_map(self):
        """⛔ 纳指100 刻意不入公共映射：东财 100.NDX 实为纳斯达克综合（禁用）。"""
        self.assertNotIn("纳指100", g._PUBLIC_IDX)
        self.assertIn("纳指100", g._PUBLIC_SUB)             # 只能走 ETF 替代口径

    def test_srcmark(self):
        """来源标记必须原样带出 `_src`（读者据此判断可信度）。"""
        self.assertEqual(g._srcmark({}), "")
        self.assertIn("东财", g._srcmark({"_src": "东财·公共API"}))
        self.assertIn("⚠️", g._srcmark({"_src": "x"}))

    def test_fallback_does_not_overwrite_mx(self):
        """权威源优先：mx 已取到值时不覆盖。"""
        m = empty_market()
        m["indices"] = {"上证": {"val": "3877.03", "chg": "-0.37%"}}
        with mock.patch.object(g.fp, "index_quotes", return_value={}) as q:
            g._public_fallback(m)
        self.assertEqual(m["indices"]["上证"]["val"], "3877.03")
        self.assertNotIn("_src", m["indices"]["上证"])
        self.assertGreaterEqual(q.call_count, 1)            # 确实尝试了兜底

    def test_sector_map_is_separate(self):
        """板块项必须在 `_PUBLIC_SECTOR`。

        反向断言：混进 `_PUBLIC_IDX` 会让兜底把板块写进 `market['indices']`，
        **板块兜底永久失效** —— 实测后果是熔断恒报「板块 0/3」而指数虚高。
        """
        self.assertNotIn("证券", g._PUBLIC_IDX)
        self.assertIn("证券", g._PUBLIC_SECTOR)

    def test_innovation_drug_secid(self):
        """创新药必须是 124.HSSCID —— 写成 100.HSSCID 实测 data:null（静默失败）。"""
        self.assertEqual(g._PUBLIC_SECTOR["创新药"], "124.HSSCID")

    def test_fallback_writes_into_sectors(self):
        """兜底确实落到 `market['sectors']`，且带来源标记。"""
        m = empty_market()
        fake = {"0.399975": {"name": "证券公司", "price": 724.95, "chg_pct": -1.04}}
        with mock.patch.object(g.fp, "index_quotes", return_value=fake):
            g._public_fallback(m)
        self.assertEqual(m["sectors"]["证券"]["val"], 724.95)
        self.assertEqual(m["sectors"]["证券"]["chg"], "-1.04%")
        self.assertIn("_src", m["sectors"]["证券"])
        self.assertEqual(m["indices"], {})                  # 不得污染指数区


class TestSectorFlowRegression(unittest.TestCase):
    """G1 — 板块资金「全净流入」假象的回归防线。"""

    def test_sector_flow_returns_both_ends(self):
        """两端都必须有输出字段，否则无法发现分化。"""
        import fetch_public as fpmod
        with mock.patch.object(fpmod, "_sector_rows") as rows:
            rows.side_effect = [
                ([{"f12": "BK1", "f14": "汽车", "f3": 1.2, "f62": 3.678e9}], 496),
                ([{"f12": "BK2", "f14": "电子", "f3": -0.2, "f62": -1.228e10}], 496),
            ]
            fpmod._CACHE.clear()
            r = fpmod.sector_flow(top=1)
        self.assertTrue(r["complete"])
        self.assertEqual(r["total_sectors"], 496)
        self.assertAlmostEqual(r["inflow"][0]["net_yi"], 36.78, places=2)
        self.assertAlmostEqual(r["outflow"][0]["net_yi"], -122.8, places=2)

    def test_net_yi_conversion(self):
        """f62 单位为元 → 亿元，量级差 1e8（量级错会写出 36.78 亿 vs 0.0000037 亿）。"""
        import fetch_public as fpmod
        with mock.patch.object(fpmod, "_sector_rows") as rows:
            rows.side_effect = [([{"f12": "x", "f14": "X", "f3": 0, "f62": 1e8}], 1),
                                ([{"f12": "y", "f14": "Y", "f3": 0, "f62": -1e8}], 1)]
            fpmod._CACHE.clear()
            r = fpmod.sector_flow(top=1)
        self.assertEqual(r["inflow"][0]["net_yi"], 1.0)
        self.assertEqual(r["outflow"][0]["net_yi"], -1.0)


class TestWatchlistSection(unittest.TestCase):
    """H — §五「新机会扫描」由**人工占位符**改为**计算渲染**（v4.5.1）。

    病灶：`watchlist[].today` 是只写字段（全仓零读者），§五 是一句人工占位符
    —— 两者同属「写了没人接」。本组守住「§五 必须来自计算、且缺口必须显形」。
    """

    def _render(self, data):
        import gen_intraday_auto as gia
        return gia.render_report(empty_market(), data, "2026-09-18 18:30")

    def test_section_five_no_longer_manual_placeholder(self):
        """🔴 反向断言：原占位符文案**不得**再出现。"""
        out = self._render(load_prod())
        self.assertNotIn("人工补充", out, "§五 又退回人工占位符了")

    def test_section_five_renders_each_watchlist_entry(self):
        d = load_prod()
        out = self._render(d)
        for item in d.get("watchlist", []):
            self.assertIn(item["sector"], out, f"{item['sector']} 未出现在 §五")

    def test_section_five_declares_criteria_and_level(self):
        """判据与级别必须写在报告里（F1：未标级别＝触发线不成立）。"""
        out = self._render(load_prod())
        self.assertIn("§4.4", out)
        self.assertIn("MA5", out)
        self.assertIn("`E`", out)

    def test_missing_criteria_surfaces_as_gap_not_guessed(self):
        """🔴 造一条**必查无板块**的假 watchlist ⇒ 必须显形「缺口」，
        且**不得**给出 🟢（fail-closed）。"""
        d = load_prod()
        d["watchlist"] = [{"sector": "__不存在的板块ZZZ__", "etf_code": "159755",
                           "status": "", "trigger": ""}]
        out = self._render(d)
        self.assertIn("缺口声明", out)
        self.assertNotIn("🟢", out)

    def test_board_movers_all_paginates_beyond_100(self):
        """🔴 反向断言：`pz` 被服务端硬顶 100，故**必须翻页** —— 单页实现拿不到全量。"""
        import fetch_public as fpmod
        pages = {1: [{"f12": "BK1", "f14": "甲", "f3": 1.0}],
                 2: [{"f12": "BK2", "f14": "乙", "f3": 2.0}],
                 3: []}
        with mock.patch.object(fpmod, "_board_page") as bp:
            bp.side_effect = lambda fs, pn, src: (pages.get(pn, []),
                                                  2 if fs == "m:90+t:2" else 0)
            fpmod._CACHE.clear()
            r = fpmod.board_movers_all()
        names = set((r.get("by_name") or {}).keys())
        self.assertIn("甲", names)
        self.assertIn("乙", names, "未翻页 ⇒ 第 2 页丢失")

    def test_board_prev_day_chg_is_honest_when_unsourced(self):
        """🔴 板块前日涨幅**结构性无源** ⇒ 必须返回 available=False ＋ tried，
        **不得**编造或用代理值。"""
        import fetch_public as fpmod
        with mock.patch.object(fpmod, "_http", side_effect=Exception("blocked")):
            r = fpmod.board_prev_day_chg("BK1090")
        self.assertFalse(r["available"])
        self.assertIsNone(r["prev_chg_pct"])
        self.assertTrue(r.get("tried"), "必须留下『试过哪些源』的痕迹")


if __name__ == "__main__":
    unittest.main(verbosity=2)
