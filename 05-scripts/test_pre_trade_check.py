#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anchor 交易前校验测试（test_pre_trade_check.py，C2/C5 新增）
覆盖：阈值读规则契约 / 缺失回退内置 + 来源标记 / 契约覆盖 / 品种匹配 /
      月操作统计复用 data_processor（定投·出入金不计、严格日期匹配）。
运行: python test_pre_trade_check.py
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths
import pre_trade_check as ptc
from data_processor import monthly_ops_summary


class TestBuiltinThresholds(unittest.TestCase):
    def test_builtin_keys_complete(self):
        b = ptc.BUILTIN_THRESHOLDS
        for k in ("e1_sat_single_limit", "e4_sat_monthly_net", "big_amount_batch",
                  "max_monthly_ops", "scorecard_event_exempt", "targets"):
            self.assertIn(k, b)
        self.assertEqual(b["e1_sat_single_limit"], 3000.0)
        self.assertEqual(b["max_monthly_ops"], 4)
        self.assertGreaterEqual(len(b["targets"]), 9)


class TestLoadThresholds(unittest.TestCase):
    def setUp(self):
        self._orig = paths.RULE_CONTRACT_PATH

    def tearDown(self):
        paths.RULE_CONTRACT_PATH = self._orig

    def test_load_from_real_contract(self):
        # 真实契约存在时应来自 contract，且数值/品种齐全
        th = ptc.load_thresholds()
        self.assertEqual(th["_source"], "contract")
        self.assertEqual(th["e1_sat_single_limit"], 3000.0)
        self.assertIn("创新药", th["targets"])

    def test_fallback_when_contract_missing(self):
        # 契约路径不存在 → 回退内置默认并标记 builtin（不抛异常）
        paths.RULE_CONTRACT_PATH = Path(tempfile.gettempdir()) / "__no_such_contract__.json"
        th = ptc.load_thresholds()
        self.assertEqual(th["_source"], "builtin")
        self.assertEqual(th["e1_sat_single_limit"], 3000.0)
        self.assertEqual(th["max_monthly_ops"], 4)
        self.assertIn("创新药", th["targets"])

    def test_contract_overrides_builtin(self):
        # 契约里的数值应覆盖内置；targets 做合并（内置品种保留）
        #
        # 🔴 v4.5.17 订正：本夹具原用 **内部键名** `e1_sat_single_limit`。
        #    旧实现为此写了一条**反向查表兜底**（`next((kk for kk,vv in _KEY_MAP.items() if vv==k))`），
        #    于是**同一个阈值在契约里有两个合法键名**（内部名 / 契约名）—— 正是
        #    「两层键名表并存且无绑定」那一族（E4 事故的同一套结构）。
        #    ⇒ 该兜底已随重构删除，契约**只有一套键名**（`extract_rule_contract` 写什么就认什么）。
        #    ⇒ 夹具改用**真契约键名**，并新增断言把夹具键名绑死到注册表上
        #      （否则夹具会再次静默漂移成「测了个不存在的键」—— 那时本测试**依然会绿**，
        #       因为断言值恰好等于内置默认 → 同 J14「弱断言掩盖真实缺口」）。
        tmp = Path(tempfile.gettempdir()) / "_ptc_contract.json"
        _CK = "e1_sat_position_cap"        # 真契约键名（内部名为 e1_sat_single_limit）
        import rule_keys as _rk
        self.assertIn(_CK, _rk.SCALAR_KEYS,
                      f"夹具用的契约键 {_CK!r} 不在注册表内 ⇒ 夹具已漂移，本次断言是空转")
        self.assertNotIn(_CK, _rk.SCALAR_KEYS[_CK].get("internal") or "",
                         "契约键与内部键必须**不同名**（同名则本测试证明不了翻译层在工作）")
        payload = {"thresholds": {_CK: 9999.0,
                                  "targets": {"测试品种": {"target": 1, "layer": "卫星", "reach": "x"}}}}
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            paths.RULE_CONTRACT_PATH = tmp
            th = ptc.load_thresholds()
            self.assertEqual(th["_source"], "contract")
            self.assertEqual(th["e1_sat_single_limit"], 9999.0)
            self.assertIn("测试品种", th["targets"])   # 契约品种并入
            self.assertIn("创新药", th["targets"])      # 内置品种保留
        finally:
            tmp.unlink(missing_ok=True)

    def test_key_name_drift_is_loud(self):
        """🔴 v4.5.17：契约**非空**却一个数值键都没认出 ⇒ 必须**声张**。

        与 `test_fallback_when_contract_missing` 是**两种不同情形**，必须长得不一样：
          契约不存在 → 回退内置（正常降级，只 print 一句）
          契约存在但键名不匹配 → **键名漂移**（病），须进 `_warns`
        """
        tmp = Path(tempfile.gettempdir()) / "_ptc_drift.json"
        # 键名全部不匹配（模拟契约由旧版本/手工生成）
        tmp.write_text(json.dumps(
            {"rules": {"e1_sat_single_limit": 9999.0, "e4_sat_monthly_net": 8888.0}},
            ensure_ascii=False), encoding="utf-8")
        try:
            paths.RULE_CONTRACT_PATH = tmp
            th = ptc.load_thresholds()
            self.assertTrue(any("键名整体不匹配" in w for w in th["_warns"]),
                            f"漂移未被声张；_warns={th['_warns']}")
            # 🔴 反向：漂移时**全部**取值必须落到 builtin，⛔ 契约坏值一个都不得生效
            self.assertEqual(th["e1_sat_single_limit"], ptc.BUILTIN_THRESHOLDS["e1_sat_single_limit"])
            self.assertEqual(th["e4_sat_monthly_net"], ptc.BUILTIN_THRESHOLDS["e4_sat_monthly_net"])
        finally:
            tmp.unlink(missing_ok=True)

    def test_drift_guard_is_quiet_on_real_contract(self):
        """🔴 **反向断言**：真契约**不得**触发漂移告警
        （否则那是一条**永远亮着**的告警 —— 报告标准 v2.1 判例：会被学会忽略）。"""
        th = ptc.load_thresholds()
        self.assertEqual(th["_source"], "contract")
        self.assertFalse(any("键名整体不匹配" in w for w in th["_warns"]),
                         f"真契约误报漂移：{th['_warns']}")
        self.assertEqual(sum(1 for v in th["_sources"].values()
                             if v.get("tier") == "contract") > 0, True,
                         "真契约必须有键走 tier=contract（否则「未误报」是空集假象）")


class TestFindTarget(unittest.TestCase):
    def setUp(self):
        self.targets = ptc.BUILTIN_THRESHOLDS["targets"]

    def test_keyword_hit(self):
        key, tgt = ptc.find_target(self.targets, {}, "创新药")
        self.assertEqual(key, "创新药")
        self.assertEqual(tgt["layer"], "卫星")

    def test_holding_fuzzy_hit(self):
        holdings = {"易方达恒生港股通创新药ETF联接C": {"mv": 1}}
        key, tgt = ptc.find_target(self.targets, holdings, "港股通创新药")
        self.assertEqual(key, "创新药")

    def test_miss_returns_none(self):
        key, tgt = ptc.find_target(self.targets, {}, "不存在品种xyz")
        self.assertIsNone(key)
        self.assertIsNone(tgt)


class TestMonthlyOpsReuse(unittest.TestCase):
    """pre_trade_check 月操作统计复用 data_processor：定投/出入金/自动扣款不计，严格按月。"""
    def test_excludes_auto_and_cross_month(self):
        data = {"transactions": [
            {"date": "2026-08-01", "op": "定投"},                                   # 不计
            {"date": "2026-08-02", "op": "买入"},                                   # 1
            {"date": "2026-08-03", "op": "加仓"},                                   # 2
            {"date": "2026-08-04", "op": "转入"},                                   # 出入金不计
            {"date": "2026-08-05", "op": "买入",
             "note": "智能定投自动扣款（非手动操作，不计入月限额）"},               # note 自动扣款不计
            {"date": "2026-07-30", "op": "买入"},                                   # 上月不计
        ]}
        used, viol = monthly_ops_summary(data, year=2026, month=8)
        self.assertEqual(used, 2)


class TestHolidayGate(unittest.TestCase):
    """§4.5 节前闸门（v3.14 新增 / v4.5.20 进契约与门禁）。

    🔴 本类**只调用纯函数** `ptc.holiday_closure()` 与离线日历，**不读写任何生产文件**
    （J11 教训：隔离靠换路径、不靠 `try/finally` —— `finally` 在进程被硬杀时不执行，
    而那正是假条目 `__TEST_FAIL__` 曾永久留在生产注册表里的原因）。
    """

    D = staticmethod(date.fromisoformat)

    def _g(self, s, days=5):
        return ptc.holiday_closure(self.D(s), days)

    # ── 正面断言：判据本身 ─────────────────────────────────────────────────
    def test_gate_days_comes_from_contract(self):
        """阈值须来自契约，且注册表里真的声明了它（否则取了 builtin 也算过）。"""
        import rule_keys as _rk
        self.assertIn("holiday_gate_min_closure", ptc.BUILTIN_THRESHOLDS)
        self.assertEqual(ptc.BUILTIN_THRESHOLDS["holiday_gate_min_closure"], 5)
        th = ptc.load_thresholds()
        self.assertEqual(th["holiday_gate_min_closure"], 5)
        self.assertEqual(th["_sources"]["holiday_gate_min_closure"]["tier"], "contract",
                         f"节前闸门阈值未走契约 ⇒ {th['_sources']['holiday_gate_min_closure']}")
        self.assertIn("holiday_gate_min_closure", _rk.SCALAR_KEYS)

    def test_national_day_eve_is_gated(self):
        """国庆前最后交易日 2026-09-30（连休 10/1–10/7 ＝ 7 天）⇒ 命中。"""
        g = self._g("2026-09-30")
        self.assertTrue(g["trading"])
        self.assertEqual(g["next_td"], self.D("2026-10-08"))
        self.assertEqual(g["closure_days"], 7)
        self.assertTrue(g["hit"])

    def test_spring_festival_eve_is_gated(self):
        """春节前最后交易日 2026-02-13（连休 10 天）⇒ 命中（最长的一条）。"""
        g = self._g("2026-02-13")
        self.assertEqual(g["closure_days"], 10)
        self.assertTrue(g["hit"])

    def test_labour_day_eve_is_gated(self):
        """劳动节前最后交易日 2026-04-30（连休 5/1–5/5 ＝ 5 天）⇒ 命中（**恰好等于阈值**）。

        边界值必须落在「命中」侧：§4.5 写的是「**≥5** 个自然日」。
        """
        g = self._g("2026-04-30")
        self.assertEqual(g["closure_days"], 5)
        self.assertTrue(g["hit"], "≥ 的等号侧必须命中；若改 > 则本条失败")

    def test_midautumn_eve_is_NOT_gated(self):
        """🔴 中秋前最后交易日 2026-09-24（连休 9/25–9/27 ＝ 3 天）⇒ **不得命中**。

        本条是 §4.5 里那句 📌 自检留痕的**执行侧钉子**：闸门初拟适用于**一切**节前，
        落笔时按附录E · F7（状态信号须自带例外出口）**下调**为「≥5 个自然日」。
        谁把阈值改回 3，本条必失败 —— 这是故意的。
        """
        g = self._g("2026-09-24")
        self.assertTrue(g["trading"])
        self.assertEqual(g["closure_days"], 3)
        self.assertFalse(g["hit"])

    def test_norm_weekdays_are_not_gated(self):
        """普通交易日一律不命中（含周五 —— 跨周末只有 2 天）。"""
        for s in ("2026-09-17", "2026-09-18", "2026-09-23", "2026-09-21"):
            self.assertFalse(self._g(s)["hit"], f"{s} 被误判为长假前最后交易日")

    def test_non_trading_day_is_not_applicable(self):
        """非交易日 ⇒ 「不适用」（➖），**且不得**输出任何 closure 数字。"""
        for s in ("2026-09-25", "2026-05-01", "2026-10-01"):
            g = self._g(s)
            self.assertFalse(g["trading"])
            self.assertIsNone(g["closure_days"])
            self.assertFalse(g["hit"])

    # ── 反向断言 1：那个 `−1` 是承重的 ────────────────────────────────────
    def test_reverse_the_minus_one_is_load_bearing(self):
        """🔴 **反向断言**：少减 1 的写法在**普通周五**上会与正确值分歧 ⇒ 证明 `−1` 不是装饰。

        普通周五 9/18：正确 closure ＝ **2**（周六、周日），少减 1 的写法得 **3**。
        取 min_days ＝ 3（若有人把阈值改成 3）时，两者给出**相反结论** ——
        `hit` 的差别**恰好只由那个 `−1` 决定**。⛔ 不要把这条删掉换成「断言 closure==2」：
        那样测的是「我算对了」，而这条测的是「**算错了会被发现**」。
        """
        g = self._g("2026-09-18", days=3)
        self.assertEqual(g["closure_days"], 2)
        self.assertEqual(g["naive_days"], 3)
        self.assertFalse(g["hit"])
        self.assertTrue(g["naive_days"] >= 3,
                        "少减 1 的写法在本日必须达到阈值 ⇒ 否则本反向断言是空转")

    # ── 反向断言 2：日历是承重的，不是装饰 ────────────────────────────────
    def test_reverse_naive_weekday_approx_would_misjudge(self):
        """🔴 **反向断言**：按星期几近似的写法会**把中秋当成交易日**。

        2026-09-25 是**周五** ⇒ `naive_weekday_approx` 判「是交易日」，而真值**休市**。
        因此任何「周五就查一查」的实现都会在这一天问出**错误的下一交易日**。
        """
        import trading_calendar as tc
        d = self.D("2026-09-25")
        self.assertTrue(tc.naive_weekday_approx(d),
                        "前提不成立：naive 近似若本就说它是休市，本断言证明不了什么")
        self.assertFalse(tc.is_trading_day(d))
        self.assertFalse(self._g("2026-09-25")["trading"],
                         "9/25 中秋必须落「不适用」，⛔ 不得落入正常交易日分支")

    # ── 反向断言 3：阈值 5 有区分力（不是「永不生效」的值）────────────────
    def test_reverse_threshold_has_discriminating_power(self):
        """🔴 **反向断言**：threshold ＝ 5 必须**既不漏也不滥**。

        中秋（3 天）与国庆（7 天）之间必须有分界 —— 若阈值取 3，
        中秋前最后交易日会**一起被禁**（＝把「长假」扩大到「一切连休」，
        正是 §4.5 自检留痕里被否掉的那个版本）。
        """
        mid, nat = self._g("2026-09-24"), self._g("2026-09-30")
        self.assertFalse(mid["hit"] and not nat["hit"])
        self.assertFalse(self._g("2026-09-24", days=3)["hit"] is False,
                         "阈值 3 下中秋必须命中 ⇒ 否则「阈值下调会扩大打击面」这条没被真正证明")
        self.assertTrue(self._g("2026-09-30", days=3)["hit"])

    # ── 反向断言 4：日历不可用 ⇒ 抛错，⛔ 不是静默「不命中」──────────────
    def test_reverse_out_of_range_raises_not_silently_passes(self):
        """🔴 **反向断言**：核定区间外必须 **fail-loud**。

        若这里返回 `hit=False`（而不是抛错），闸门会在 2027 年的每一天
        静默放行，且**报告上看不出任何异常** —— 即「**拿到一个结果 ≠ 结果是对的**」
        （#138 同族）。⛔ 不得改成「回退按星期几猜」。
        """
        import trading_calendar as tc
        with self.assertRaises(tc.CalendarUnavailable):
            ptc.holiday_closure(self.D("2027-01-05"), 5)

    # ── 反向断言 5：纯函数 —— 判据必须可被断言，不得偷读时钟 ──────────────
    def test_reverse_purity_no_clock_no_file(self):
        """🔴 **反向断言**：`holiday_closure` 必须是 `asof` 的纯函数。

        它若「顺手」默认取 `date.today()`，则：① 测试将只在某些日子通过
        （**间歇性假绿**）；② 回溯核对永远得不到旧日结论。

        🔴 **本条自身已修正过一次**（2026-09-23，变异测试当场抓到）：
        初版写的是 `assertNotIn("date.today()", src)` —— **逐字匹配**，
        把 `from datetime import date as _d` 后写 `_d.today()` 就能绕过。
        ⇒ 现改为**正则匹配「任何形如 `X.today(` / `X.now(` 的调用」**，
        ⛔ 不再依赖某个具体拼写（**「验证探针本身未经校验」本主题第 N 次，
        这次病灶在探针里**）。
        """
        import inspect
        import re
        src = inspect.getsource(ptc.holiday_closure)
        for pat, why in ((r"\.today\s*\(", "读今天"), (r"\.now\s*\(", "读此刻"),
                         (r"time\.time\s*\(", "读时间戳")):
            m = re.search(pat, src)
            self.assertIsNone(m, f"纯函数里出现 {why} 的调用 {m.group(0) if m else ''!r} "
                                 f"⇒ 已不是纯函数（换个 import 别名也绕不过本断言）")
        self.assertIn("asof", inspect.signature(ptc.holiday_closure).parameters)
        # 同参必同果（确定性）
        a = ptc.holiday_closure(self.D("2026-09-30"), 5)
        b = ptc.holiday_closure(self.D("2026-09-30"), 5)
        self.assertEqual(a, b)


class TestHolidayGateEndToEnd(unittest.TestCase):
    """端到端：跑真 `main()`，证明**分支真的接上了**（不只是纯函数对）。"""

    def _run(self, argv):
        import contextlib
        import io as _io
        old = sys.argv
        sys.argv = ["pre_trade_check.py"] + argv
        buf = _io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = ptc.main()
        finally:
            sys.argv = old
        return rc, buf.getvalue()

    def _gate_line(self, out):
        for ln in out.splitlines():
            if "节前闸门" in ln:
                return ln.strip()
        return ""

    def test_national_day_eve_blocks_satellite(self):
        rc, out = self._run(["创新药", "300", "--asof", "2026-09-30"])
        self.assertEqual(rc, 1, f"长假前最后交易日必须拦截；输出：\n{out}")
        self.assertIn("⛔ 节前闸门:", out)

    def test_output_prints_both_clocks(self):
        """🔴 提交时刻与数据日期**必须同时可见** —— 二者语义相反、长相一样，混装即静默错。"""
        _, out = self._run(["创新药", "300", "--asof", "2026-09-30"])
        ln = self._gate_line(out)
        self.assertIn("提交时刻 2026-09-30", ln)
        self.assertIn("--asof 覆盖", ln, "回溯运行时必须标明是覆盖值，⛔ 不得伪装成今天")
        self.assertIn("数据日期", ln)

    def test_dataroom_layer_not_gated(self):
        """压舱石层 ⇒ 「本层不适用」（§4.5 只禁卫星层）。"""
        rc, out = self._run(["鹏华畅享债券", "300", "--asof", "2026-09-30"])
        self.assertIn("节前闸门·本层不适用", out)
        self.assertNotIn("⛔ 节前闸门:", out)

    def test_offtable_target_fails_closed(self):
        """表外标的 ⇒ **层别未知 ⇒ 拦截**（⛔ 不等于「已通过」）。"""
        _, out = self._run(["某不存在品种xyz", "300", "--asof", "2026-09-30"])
        self.assertIn("⛔ 节前闸门·层别未知", out)

    def test_midautumn_is_not_gated_end_to_end(self):
        """🔴 中秋前（9/24）不得出现任何 ⛔ 节前闸门行。"""
        _, out = self._run(["创新药", "300", "--asof", "2026-09-24"])
        self.assertNotIn("⛔ 节前闸门", out)
        self.assertIn("✅ 节前闸门", out)

    def test_reverse_gate_reads_submission_clock_not_data_date(self):
        """🔴 **反向断言**：闸门必须读**提交时刻**，⛔ 不得读**数据日期**。

        本仓 `gen_watchlist_status` / `board_history_record` 的教训是**相反方向**的
        （那里该用**数据自身交易日**，用 `now` 是 bug）。两个方向**语义相反、长相一样**
        ⇒ 必须有一条断言把「这里用的是哪一个」钉死，否则后人按上一处教训来改**必错**。

        构造：数据日期 ＝ `portfolio_data.json` **现值**（本用例不固定它，见下行注）。
          · 提交时刻 ＝ 2026-09-30（长假前）⇒ **⛔ 拦**
          · 提交时刻 ＝ 2026-09-22（普通交易日）⇒ **不拦**
        两者结论必须不同 —— 相同则说明闸门读的是数据日期（实现方向反了）。

        🔴 2026-09-23 修复（假红）：原实现把「数据日期 2026-09-22」**硬编码**进断言，
            ⇒ 每次收盘入库（update_date 前进一天）本用例必红，**长相与代码回归完全一样**
            （同族：单 144「活源失败与代码回归不可区分」）。现改为**从数据源读取**。
        """
        rc_eve, out_eve = self._run(["创新药", "300", "--asof", "2026-09-30"])
        rc_day, out_day = self._run(["创新药", "300", "--asof", "2026-09-22"])
        self.assertIn("⛔ 节前闸门:", out_eve)
        self.assertNotIn("⛔ 节前闸门:", out_day)
        self.assertEqual(rc_eve, 1)
        # 同一个数据日期必须被打印出来（否则「读了哪一个」在报告上无从分辨）
        # ⛔ 不得硬编码日期；每次都从真源读（读不到即用例失败，不静默放过）
        with open(paths.DATA_PATH, encoding="utf-8") as f:
            live_date = json.load(f).get("update_date")
        self.assertTrue(live_date, f"portfolio_data.json 缺 update_date：{paths.DATA_PATH}")
        self.assertIn(f"数据日期 {live_date}", out_eve)


if __name__ == "__main__":
    print("=" * 60)
    print("Anchor - Pre-Trade Check Test Suite")
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
