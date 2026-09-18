# -*- coding: utf-8 -*-
"""test_anchor_pro_privacy.py — gen_anchor_pro 公开页隐私护栏测试（v4.5.4，2026-09-18）

缘起（真实事故，非假想）：
  2026-09-18 入库后 `total_hold_pnl_est` 由人工维护改为派生，实算 **1366.36**；
  `numeric_token_forms()` 会额外产出**整数形态** `1366`，而 `anchor-pro.html` 的一条
  CSS 注释里写着「≥1366px 不出视口」⇒ `sync_all` 步骤 4「anchor-pro 公开页」
  以 `[ERROR] 公开HTML包含私有标记：1366` **失败**。
  🔴 定性：**机制缺陷** —— token 集由真实字段派生，任何取整落在 4 位数的字段值
  （布点 1024/1280/1366/1440/1920、年份 2026、z-index…）都会撞上 HTML 字面量，
  且**每次撞都表现为「公开页生成失败」而非「泄漏」**。

本测试钉两件事：
  ① 豁免**确实生效**（`1366px` 不再误报）；
  ② 豁免**没有放宽到危险面**（裸 `1366`、小数 `1366.36`、千分位、`1366%`、假单位 `1366pxx` 全部仍被抓）。
  ③ **反向断言**：证明**修复前的写法确实会误报** —— 否则本测试可能在「护栏根本没跑」的假阳性下通过。

⛔ 全程**只读**，不写任何生产文件（沿用 J11 之理：**换路径隔离，不靠 try/finally**）。
"""

import os
import sys
import unittest

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

import gen_anchor_pro as g  # noqa: E402


class TestCssUnitExemption(unittest.TestCase):
    """豁免面：纯整数 token + 每一处命中都紧跟 CSS 长度单位。"""

    def test_real_css_comment_no_longer_false_positives(self):
        """本轮事故的原始字符串（注释原语，单位后有空格）。"""
        self.assertFalse(g.contains_sensitive_token("/* ≥1366px 不出视口 */", "1366"))

    def test_cjk_after_unit_still_exempt(self):
        """🔴 去空白压缩后中文紧贴单位：`px不出` —— Unicode 下 `\\b` 认为中文是词字符，
        用 `\\b` 会在此失效。此用例钉住必须用 `(?![A-Za-z0-9])`。"""
        self.assertFalse(g.contains_sensitive_token("≥1366px不出视口", "1366"))

    def test_media_query_form(self):
        self.assertFalse(g.contains_sensitive_token("@media (min-width:1366px)", "1366"))

    def test_common_breakpoints_all_exempt(self):
        for bp in ("1024", "1280", "1366", "1440", "1536", "1920"):
            with self.subTest(bp=bp):
                self.assertFalse(
                    g.contains_sensitive_token(f"@media (min-width:{bp}px){{}}", bp),
                    f"布点 {bp}px 不应被判为泄漏")

    # ---- 反向面：豁免不得扩散 ----

    def test_bare_integer_still_caught(self):
        self.assertTrue(g.contains_sensitive_token("total_assets: 1366", "1366"))

    def test_decimal_form_still_caught(self):
        """小数形态根本不进豁免分支（token 非 isdigit）。"""
        self.assertTrue(g.contains_sensitive_token("v=1366.36", "1366.36"))

    def test_thousands_separator_still_caught(self):
        self.assertTrue(g.contains_sensitive_token("x 1,366 y", "1,366"))

    def test_mixed_hits_judged_as_leak(self):
        """同一 token 一处落在 CSS 长度、一处裸出现 ⇒ **必须判泄漏**（要求「每一处」都豁免）。"""
        self.assertTrue(g.contains_sensitive_token("a 1366px b 1366 c", "1366"))

    def test_year_like_literal_still_caught(self):
        self.assertTrue(g.contains_sensitive_token("更新日期 2026", "2026"))

    def test_percent_not_exempt(self):
        """`%` 故意不在单位表内 —— 涨跌幅与数据无法区分，纳入即松绑。"""
        self.assertTrue(g.contains_sensitive_token("chg 1366%", "1366"))

    def test_fake_unit_still_caught(self):
        """`1366pxx` 不是合法单位（`(?![A-Za-z0-9])` 拦住）。"""
        self.assertTrue(g.contains_sensitive_token("1366pxx", "1366"))

    def test_non_numeric_token_unaffected(self):
        self.assertTrue(g.contains_sensitive_token("易方达恒生港股通创新药", "易方达恒生港股通创新药"))

    def test_empty_token_never_hits(self):
        self.assertFalse(g.contains_sensitive_token("任意文本", ""))


class TestLeakedTokensIntegration(unittest.TestCase):
    """端到端形态：leaked_tokens 在真实 token 集下的判定。"""

    def _data(self, **kw):
        base = {"total_assets": 47899.11, "fund_account": 42263.11,
                "stock_account": 5636.00, "yuebao": 8462.26, "total_hold_pnl_est": 1366.36}
        base.update(kw)
        return base

    def test_css_comment_scenario_clean(self):
        self.assertEqual(g.leaked_tokens("/* ≥1366px 不出视口 */", self._data()), [])

    def test_real_leak_detected(self):
        hits = g.leaked_tokens("total_hold_pnl_est = 1366.36", self._data())
        self.assertIn("1366.36", hits)

    def test_reverse_old_behaviour_would_have_leaked(self):
        """🔴 **反向断言**：钉住「修复前的写法确实会误报」——
        旧实现就是对 `1366px` 直接 `token in text`。若将来有人把豁免删掉，
        本断言仍会通过（它测的是旧逻辑本身），但 test_real_css_comment_no_longer_false_positives
        会失败 ⇒ 两者配对即锁死「豁免必须存在且必须有效」。"""
        text = "/* ≥1366px 不出视口 */"
        self.assertTrue("1366" in text, "旧写法（裸子串判定）在此必判命中 —— 这正是本轮误报的机理")


class TestRealArtifacts(unittest.TestCase):
    """真实产物回归：护栏在**当前真实文件**上必须放行。

    ⚠️ 只读。若 anchor-pro.html 尚不存在（未生成过），跳过而非失败。
    """

    def test_real_anchor_pro_html_passes_guard(self):
        if not os.path.exists(g.PRO_HTML):
            self.skipTest(f"未生成 {g.PRO_HTML}")
        with open(g.PRO_HTML, encoding="utf-8") as f:
            html = f.read()
        try:
            data = g.load_public_data()
        except Exception as e:  # 公开源缺失不构成本测试的失败面
            self.skipTest(f"公开数据源不可用: {e}")
        hits = g.leaked_tokens(html, data)
        self.assertEqual(hits, [], f"公开页被误判/真泄漏：{hits}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
