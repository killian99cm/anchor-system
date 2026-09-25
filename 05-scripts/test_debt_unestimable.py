#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单 149 回归：债基「**不可估（结构性无源）**」口径（报告标准 v2.5 · §二.13）

背景（**为什么这条口径不是文字游戏**）
------------------------------------
两只债基（鹏华畅享C ＋ 中银稳健增利A）**合计占组合约 45%**，而：
  ① **盘中估值无源**（天天基金 `fundgz` 全代码失效、东财移动端 `GSZ:null`）；
  ② 🔴 **利率债 ETF 代理「方向全错」**（2026-09-24 **首次逐笔对账**实证：国债ETF **+0.026%**、
     政金债ETF **+0.019%**，而两只债基实际 **−0.153% / −0.097%** ⇒ **符号相反**，
     当日误差 **−17.76 / −12.55 元**，是全部持仓里**最大的两项偏差**）；
  ③ 报告标准要求「持仓项须含 MA5/10/20」⇒ 对债基**只能留空或给错数**（前者不合规、后者更糟）。

断言
----
① **口径真源**：`fetch_registry.json` 的债券条目 **`intraday_estimable=false`** ＋ 非空
   `unestimable_reason`（且原因里**写明 9/24 实证的偏差方向**，供日后复核）；
② 🔴 **不产出数值候选**：走 `data_auto_fill.main()` ⇒ 该条目候选 **`grade=unestimable`**、
   **无 `pct` 键**、**不调用 `mx_query`**（⛔ 不空跑、⛔ 不填 0、⛔ 不填代理值）；
③ **对照组**：同一次运行里**正常条目照常取数** ⇒ 证明不是「整段没跑」（防空转通过）；
④ 🔴 **反向（承重）**：夹具给不可估条目**挂上代理字段**（如 `index_secid`）⇒
   `validate_unestimable` **必须报问题**、`main()` **必须 rc=3 判红**；
⑤ **不误伤**：黄金/纳指 的 **ETF 代理**（已被证明更准）**不受影响** —— 本单只治债基。

隔离：`ANCHOR_FETCH_REGISTRY` / `ANCHOR_FILL_OUT_DIR` 双注入点 ⇒ ⛔ 不碰生产
`fetch_registry.json`，⛔ 不覆盖生产 `04-reviews/daily/*-数据回填候选.json`；`mx_query` 打桩 ⇒ 零网络。

运行：python test_debt_unestimable.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import data_auto_fill as daf          # noqa: E402
import paths                          # noqa: E402

SCRIPTS = os.path.dirname(os.path.abspath(__file__))


def _entry(key, **kw):
    e = {"key": key, "label": key, "pipeline_key": "债券", "holdings_match": ["鹏华畅享"],
         "target_kind": "nav", "close_class": "cn_fund_nav", "fetch": "always",
         "queries": [{"q": "鹏华畅享债券C", "match": ["鹏华畅享"]}]}
    e.update(kw)
    return e


def _write_registry(tmp, entries):
    p = os.path.join(tmp, "registry.json")
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"_meta": {}, "default_suffixes": [" 最新净值 日涨跌幅"],
                   "entries": entries}, f, ensure_ascii=False)
    return p


class TestUnestimableValidator(unittest.TestCase):
    def test_01_declared_entry_passes(self):
        """① 正当声明（有原因、无代理字段、rate_query 已标注用途）⇒ 校验通过。"""
        ok = _entry("债券", intraday_estimable=False,
                    unestimable_reason="fundgz 失效；ETC 代理方向全错（9/24 实证 +0.026% vs −0.153%）",
                    rate_query="中国10年期国债收益率 最新",
                    note="rate_query 仅供宏观锚，不得用于估值反推（非估值用途）")
        self.assertEqual(daf.validate_unestimable([ok]), [])

    def test_02_reverse_proxy_field_goes_red(self):
        """🔴 ④ 反向：不可估条目挂上代理字段 ⇒ **必须报问题**（口径不是装饰）。"""
        bad = _entry("债券", intraday_estimable=False, unestimable_reason="有原因",
                     index_secid="1.511010")            # ← 国债ETF 代理，正是 9/24 方向全错那个
        probs = daf.validate_unestimable([bad])
        self.assertTrue(probs, "❌ 不可估条目带 index_secid 却未报问题 ⇒ 校验是装饰")
        self.assertTrue(any("index_secid" in p for p in probs), probs)

    def test_03_reverse_reason_missing_goes_red(self):
        """🔴 反向：声明不可估却不写原因 ⇒ 必须报问题（⛔ 口径必须写明原因）。"""
        probs = daf.validate_unestimable([_entry("债券", intraday_estimable=False)])
        self.assertTrue(any("unestimable_reason" in p for p in probs), probs)

    def test_04_reverse_rate_query_unlabeled_goes_red(self):
        """🔴 反向：不可估条目仍带 `rate_query` 而 note 未标用途 ⇒ 必须报问题。"""
        probs = daf.validate_unestimable([_entry(
            "债券", intraday_estimable=False, unestimable_reason="有原因",
            rate_query="中国10年期国债收益率 最新", note="利率敏感度看它")])
        self.assertTrue(any("rate_query" in p for p in probs), probs)

    def test_05_no_false_alarm_on_estimable_entries(self):
        """⑤ 不误伤：**可估**条目（黄金/纳指/联接基金）带代理字段 ⇒ 一律不报。"""
        others = [_entry("黄金A", index_secid="1.518880", rate_query=None, note=""),
                  _entry("纳指A", index_secid="100.NDX100", note=""),
                  _entry("证券C", index_secid="0.399975", note="")]
        for e in others:
            e.pop("rate_query", None)
        self.assertEqual(daf.validate_unestimable(others), [],
                         "❌ 误伤了可估条目（黄金/纳指的 ETF 代理已证明更准，本单只治债基）")

    def test_06_real_registry_declares_bond_unestimable(self):
        """① 真源检查：生产 `fetch_registry.json` 的债券条目已声明不可估 ＋ 写明 9/24 实证。"""
        with io.open(os.path.join(SCRIPTS, "fetch_registry.json"), encoding="utf-8") as f:
            d = json.load(f)
        e = [x for x in d["entries"] if x["key"] == "债券"][0]
        self.assertIs(e.get("intraday_estimable"), False, "❌ 债券条目未声明 intraday_estimable=false")
        r = e.get("unestimable_reason") or ""
        for token in ("fundgz", "511010", "0.026", "−0.153", "相反"):
            self.assertIn(token, r, f"❌ unestimable_reason 缺「{token}」—— 须写明 9/24 实证的偏差方向")
        self.assertEqual(daf.validate_unestimable(d["entries"]), [],
                         "❌ 生产注册表本身未通过不可估口径校验")


class TestFillBehaviour(unittest.TestCase):
    """走 `data_auto_fill.main()`：验证「不产出数值候选」＋「正常条目照常取数」。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="anchor_149_")
        self._env = dict(os.environ)
        os.environ["ANCHOR_FILL_OUT_DIR"] = self.tmp
        self.calls = []
        self._mx = daf.mx_query

        def fake_mx(q, timeout=40):
            self.calls.append(q)
            return [{"date": "2026-09-25", "涨跌幅": "1.23%", "name": "鹏华畅享债券C"}]

        daf.mx_query = fake_mx

    def tearDown(self):
        daf.mx_query = self._mx
        os.environ.clear()
        os.environ.update(self._env)

    def _run(self, entries):
        os.environ["ANCHOR_FETCH_REGISTRY"] = _write_registry(self.tmp, entries)
        import importlib
        importlib.reload(daf)                      # 让 REGISTRY_PATH / OUT_DIR 重新读 env
        daf.mx_query = self._mx_stub
        buf = io.StringIO()
        # 🔴 健康矩阵隔离（2026-09-25 修）：`data_auto_fill.main()` 会把 attempt/finalize 写进
        #    `data_source_health.json`，而**该文件当时没有 env 覆盖点** ⇒ 夹具标签
        #    （`债券` / `黄金A`）**落进了生产产物**（本次实测发现并已清理）。
        #    ⇒ 测试层改为**整个矩阵打桩**：既不写生产、也不复用生产里的历史读数
        #    （复用会让第二次运行**不再发起取数** ⇒ 「不调用 mx_query」断言恒真，静默失去鉴别力）。
        import data_source_health as dsh
        from unittest import mock

        class _NullMatrix:
            @staticmethod
            def load():
                return _NullMatrix()

            def attempt(self, *a, **k):
                pass

            def reading(self, *a, **k):
                pass

            def finalize(self, *a, **k):
                pass

            def latest_reading(self, label):
                return None

            def write(self):
                return "(测试隔离：⛔ 不写生产 data_source_health.json)"

        with mock.patch.object(dsh, "HealthMatrix", _NullMatrix):
            with contextlib.redirect_stdout(buf):
                rc = daf.main()
        outs = [f for f in os.listdir(self.tmp) if f.endswith("数据回填候选.json")]
        data = {}
        if outs:
            with io.open(os.path.join(self.tmp, outs[0]), encoding="utf-8") as f:
                data = json.load(f)
        return rc, buf.getvalue(), data

    def setUp_stub(self):
        """打桩 `mx_query`：零网络，且返回**满足四重绑定**的行（列名 ＋ 实体 ＋ 日期）。

        ⚠️ 行必须能被 `_pick_row` 认下（列名 ∈ `PCT_FIELDS_NAV`（nav 类口径）＋ 实体含注册表关键词
        ＋ 无钟点日期）；否则会以「正常条目未取到值」失败，而那与「不可估条目被取数」是**两件不同的事**。"""
        calls = self.calls

        def stub(q, timeout=40):
            calls.append(q)
            return [{"entity": "鹏华畅享债券C", "name": "复权单位净值增长率",
                     "value": "1.23%", "date": "2026-09-25"}]
        return stub

    def test_07_unestimable_entry_yields_no_numeric_candidate(self):
        """② 不可估条目 ⇒ 无 `pct`、grade=unestimable、**不调用 mx_query**；③ 正常条目照常取数。"""
        self._mx_stub = self.setUp_stub()
        rc, out, data = self._run([
            _entry("债券", intraday_estimable=False, unestimable_reason="结构性无源（9/24 实证）",
                   rate_query=None, note=""),
            _entry("黄金A", index_secid="1.518880"),
        ])
        self.assertNotEqual(rc, 3, f"❌ 正当声明被判红：\n{out[-600:]}")
        cands = {c["key"]: c for c in data.get("candidates", [])}
        self.assertEqual(cands["债券"]["grade"], "unestimable")
        self.assertNotIn("pct", cands["债券"], "❌ 不可估条目带上了 pct ⇒ 会被读成「有值」")
        self.assertTrue(cands["债券"]["unestimable_reason"])
        self.assertEqual(self.calls, ["鹏华畅享债券C 最新净值 日涨跌幅"],
                         f"❌ 不可估条目被发起了取数（或正常条目没取）⇒ 实际调用 {self.calls}")
        self.assertIn("pct", cands["黄金A"], "❌ 正常条目未取到值 ⇒ 对照组失效")

    def test_08_reverse_main_red_on_proxy(self):
        """🔴 ④ 反向（承重）：夹具给不可估条目挂 `index_secid` ⇒ `main()` **必须 rc=3 判红**。"""
        self._mx_stub = self.setUp_stub()
        rc, out, data = self._run([
            _entry("债券", intraday_estimable=False, unestimable_reason="有原因",
                   index_secid="1.511010"),
        ])
        self.assertEqual(rc, 3, f"❌ 代理字段未使 main() 判红：\n{out[-800:]}")
        self.assertIn("「不可估」口径被违反", out)
        self.assertTrue(data.get("unestimable_problems"), "❌ 候选文件未留痕问题清单")


if __name__ == "__main__":
    unittest.main(verbosity=2)
