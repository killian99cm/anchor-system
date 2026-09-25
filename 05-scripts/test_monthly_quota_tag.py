#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单 152 回归：月额度超限**自动打标** ＋ 月度归因**显式披露**（裁决 #C1-21 方案 A-3）

背景
----
`买入 ≤2` 这条额度 **12 个月里超限 11 个月**、9 月买入事件 5 笔，而 `decision_log` 的违规
留痕 **0 笔** —— 病灶不是「上限太小」，是「**超了也没事**」：买入维满额状态下发生的买入，
系统**不留任何标记**，月度归因也不体现。命中报告标准 v2.1 判例：
「**一条永远做不到的强制项会训练出『照抄免责』的习惯**」。

本测试的断言（与 `outbox/152` 交付件 §口径一一对应）
--------------------------------------------------
① **正向打标**：买入维**已满**（2/2）＋又一笔买入 ⇒ tags 含 `违规·月额度`，**且记录照写**
   （留痕 ≠ 拦截）。
② 🔴 **反向（防误标）**：买入维**未满** ⇒ 不含该 tag；`暂缓不买`／`执行卖出`／`持有`
   等**非买入** ⇒ 一律不含。
③ ⛔ **不溯及既往**：生效日（2026-09-24）**之前**的日期 ⇒ 不打标；**补录**（backfilled）
   ⇒ 不打标。并对**真实** `decision_log.json` 做**只读**扫描：生效日之前的记录带该 tag
   必须 **0 条**（防追溯污染历史准确率读数）。
④ **数据不可读** ⇒ `evaluated=False`、**不打标**，且输出**显式声张**
   （⛔ 不得静默当作「未超限」）。
⑤ **单一真源**：计数一律经 `data_processor.monthly_ops_summary`（spy 证明，⛔ 无自造计数）。
⑥ **月度归因**：有超限 ⇒ 「本月买入维超限 N 笔（上限 2）」＋逐笔（日期/标的/金额/留痕）；
   **无超限 ⇒ 显式写「本月无超限」**（⛔ 不得静默省略整段）。
⑦ 🔴 **反向（承重）**：把打标那两行删掉（＝改回旧写法）跑 ⇒ 记录不含 tag ⇒ ① 必红。

隔离（⛔ 不碰生产数据）
--------------------
`log_decision` 经 `pf_path` 注入夹具 ⇒ 不碰真实 `portfolio_data.json`；
`LOG_FILE` 指向临时目录 ⇒ 不碰真实 `decision_log.json`；
时钟经 `dl.datetime` 冻结 ⇒ **不做定时炸弹测试**（同仓 117 个硬编码日期测试的教训）；
反向探针写在本脚本**同目录**（兄弟模块可导入），运行后**显式删除**并断言零残留。

运行：python test_monthly_quota_tag.py
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import data_processor as dp          # noqa: E402
import decision_log as dl            # noqa: E402
import gen_monthly_attribution as g   # noqa: E402

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
DECISION_LOG_PY = os.path.join(SCRIPTS, "decision_log.py")
PROBE = os.path.join(SCRIPTS, "_152_reverse_probe.py")

FROZEN = datetime(2026, 9, 25, 10, 0)     # 冻结时钟：属 2026-09（夹具同月），且 ≥ 生效日
REAL_LOG_DEFAULT = Path(SCRIPTS).parent / "06-dashboard" / "decision_log.json"


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 25, 10, 0, 0)


def pf(n_buys, ym="2026-09", n_sells=0):
    """造一份最小 `portfolio_data.json` 夹具（借生产结构：transactions + _meta 上限键）。"""
    txns = [{"date": f"{ym}-{i + 1:02d}", "op": "买入", "name": f"夹具买入{i + 1}",
             "amount": 300.0} for i in range(n_buys)]
    txns += [{"date": f"{ym}-{i + 1:02d}", "op": "减仓", "name": f"夹具卖出{i + 1}",
              "amount": 200.0} for i in range(n_sells)]
    return {"transactions": txns,
            "_meta": {"monthly_buys_max": 2, "monthly_sells_max": 2, "max_monthly_ops": 4}}


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="anchor_152_")
        self._log_backup = dl.LOG_FILE
        dl.LOG_FILE = Path(self.tmp) / "decision_log.json"
        self._dt_backup = dl.datetime
        dl.datetime = _FrozenDatetime
        self._glog_backup = g.DECISION_LOG_FILE
        g.DECISION_LOG_FILE = Path(self.tmp) / "decision_log.json"

    def tearDown(self):
        dl.LOG_FILE = self._log_backup
        dl.datetime = self._dt_backup
        g.DECISION_LOG_FILE = self._glog_backup

    # ---- 夹具 ----
    def pf_file(self, n_buys, **kw) -> str:
        p = Path(self.tmp) / "portfolio_data.json"
        p.write_text(json.dumps(pf(n_buys, **kw), ensure_ascii=False), encoding="utf-8")
        return str(p)

    def add(self, n_buys=None, dtype="加仓", verdict="执行买入", pf_path=None, **kw):
        """E2E：走 `log_decision` 真实写盘路径，返回 (记录 dict, 控制台输出)。"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            did = dl.log_decision(dtype, "夹具基金", verdict, 300, "夹具依据", "涨",
                                  pf_path=self.pf_file(n_buys) if pf_path is None else pf_path, **kw)
        recs = json.loads(dl.LOG_FILE.read_text(encoding="utf-8"))["decisions"]
        return next(d for d in recs if d["id"] == did), buf.getvalue()

    def write_tagged_log(self, entries):
        (Path(self.tmp) / "decision_log.json").write_text(
            json.dumps({"decisions": entries}, ensure_ascii=False), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
class TestAutoTag(_Base):
    def test_01_over_quota_auto_tags(self):
        """① 正向：买入维已满（2/2）＋又一笔买入 ⇒ 打标，且**记录照写**（留痕≠拦截）。"""
        for n in (2, 5):
            rec, out = self.add(n)
            self.assertIn(dl.QUOTA_TAG, rec["tags"], f"❌ 买入维已满（{n}笔）未打标")
            self.assertIn("已满", out, "❌ 输出未声张「已满」")
            self.assertEqual(rec["verdict"], "执行买入", "❌ 记录被改动（打标不得改判定）")
            self.assertTrue(dl.LOG_FILE.exists(), "❌ 打标把记录写没了（留痕≠拦截）")

    def test_02_not_over_quota_no_tag(self):
        """🔴 ② 反向：买入维**未满** ⇒ 不含该 tag（防误标）。"""
        for n in (0, 1):
            rec, out = self.add(n)
            self.assertNotIn(dl.QUOTA_TAG, rec["tags"], f"❌ 未满额（{n}笔）被误标")
            self.assertIn("未满", out, "❌ 未满额时未声张读数")

    def test_03_non_buy_decisions_never_tagged(self):
        """🔴 ② 反向：非买入决策（含**显式「不买」**）⇒ 一律不打标（即便额度已满）。"""
        cases = [("观望", "暂缓不买"), ("观望", "持有"), ("观望", "零主动操作"),
                 ("减仓", "执行卖出"), ("止损", "执行止损"), ("清仓", "执行清仓")]
        for dtype, verdict in cases:
            rec, _ = self.add(5, dtype=dtype, verdict=verdict)
            self.assertNotIn(dl.QUOTA_TAG, rec["tags"], f"❌ {dtype}/{verdict} 被误标")

    def test_04_type_outside_closed_set_but_executed_buy(self):
        """① 边界：type 落在闭集外但判定列表明「执行买入」（实测 #54 `type='证券'`）⇒ 打标。"""
        rec, _ = self.add(2, dtype="证券", verdict="执行买入")
        self.assertIn(dl.QUOTA_TAG, rec["tags"], "❌ 闭集外 type + 执行买入 被漏标")


class TestNotRetroactive(_Base):
    def test_05_before_effective_date_no_tag(self):
        """③ 不溯及既往：生效日**之前**的日期 ⇒ 不打标（隔离测日期判据本身）。"""
        r = dl.quota_tag_decision("加仓", "执行买入", "2026-09-23", backfilled=False,
                                  data=pf(5))
        self.assertIsNone(r["tag"], "❌ 生效日之前的日期被打标")
        self.assertIn("不溯及既往", r["note"])
        self.assertFalse(r["evaluated"], "❌ 生效日之前不应触发额度评估")

    def test_06_backfilled_no_tag(self):
        """③ 补录（backfilled）⇒ 不打标（对应交易已在账本中 ⇒「含本笔」口径不成立）。"""
        r = dl.quota_tag_decision("加仓", "执行买入", "2026-09-25", backfilled=True, data=pf(5))
        self.assertIsNone(r["tag"], "❌ 补录记录被打标")
        self.assertIn("补录", r["note"])
        # E2E：--backfill 路径（entry_date 非空 ⇒ backfilled=True）
        rec, _ = self.add(5, entry_date="2026-09-25")
        self.assertTrue(rec["backfilled"])
        self.assertNotIn(dl.QUOTA_TAG, rec["tags"], "❌ E2E 补录路径被打标")

    def test_07_real_log_not_polluted(self):
        """③ 🔴 **只读**扫描真实 decision_log：生效日之前的记录带该 tag 必须 0 条。"""
        if not REAL_LOG_DEFAULT.exists():
            self.skipTest(f"真实决策日志不存在（{REAL_LOG_DEFAULT}）⇒ 无法判定，不计通过")
        ds = json.loads(REAL_LOG_DEFAULT.read_text(encoding="utf-8"))["decisions"]
        bad = [d["id"] for d in ds
               if str(d.get("date", "")) < str(dl.QUOTA_TAG_SINCE)
               and dl.QUOTA_TAG in (d.get("tags") or [])]
        self.assertEqual(bad, [], f"❌ 历史记录被追溯污染（A-3 禁止）：{bad}")


class TestFailLoud(_Base):
    def test_08_unreadable_portfolio_not_silently_pass(self):
        """④ 数据不可读 ⇒ 不打标 ＋ **显式声张**（⛔ 不得静默当作「未超限」）。"""
        rec, out = self.add(pf_path=os.path.join(self.tmp, "不存在.json"))
        self.assertNotIn(dl.QUOTA_TAG, rec["tags"])
        self.assertIn("不可读", out, "❌ 数据不可读却无声张（静默通过）")
        self.assertIn("未评估", out)

    def test_09_single_source_of_truth(self):
        """⑤ 单一真源：计数一律经 `data_processor.monthly_ops_summary`（spy 证明）。"""
        calls = []
        orig = dp.monthly_ops_summary

        def spy(data, year=None, month=None):
            calls.append((year, month))
            return dp.MonthlyOpsSummary(year=year, month=month, buys=9, sells=0,
                                        max_buys=2, max_sells=2, max_total=4)

        dp.monthly_ops_summary = spy
        try:
            # 夹具 0 笔买入 ⇒ 若存在任何自造计数，结果必为「未满」；只有经真源才得 9/2
            rec, _ = self.add(0)
        finally:
            dp.monthly_ops_summary = orig
        self.assertEqual(calls, [(2026, 9)], f"❌ 未按「记录日所在月」调用真源：{calls}")
        self.assertIn(dl.QUOTA_TAG, rec["tags"], "❌ 计数未取自单一真源（自造口径）")


class TestAttributionDisclosure(_Base):
    def test_10_over_quota_disclosed(self):
        """⑥ 有超限 ⇒ 段落含「本月买入维超限 N 笔（上限 2）」＋逐笔。"""
        rep = g.build_report(pf(5), 2026, 9)
        self.assertIn("本月买入维超限 3 笔（上限 2）", rep)
        self.assertIn("六·A 月操作额度 · 超限披露", rep)
        self.assertIn("夹具买入3", rep, "❌ 逐笔明细缺失")
        self.assertIn("🔴 **超限**", rep)
        self.assertIn("记录 **0** 条", rep)
        self.assertIn("留痕 0 vs 超限 3", rep)
        self.assertIn("⛔ 无", rep, "❌ 超限未留痕未被披露（本段存在的理由）")

    def test_11_no_over_quota_explicitly_stated(self):
        """🔴 ⑥ 无超限 ⇒ **显式**写「本月无超限」（⛔ 不得静默省略整段）。"""
        for n in (0, 2):
            rep = g.build_report(pf(n), 2026, 9)
            self.assertIn("本月无超限", rep, f"❌ n_buys={n} 未显式声明无超限")
            self.assertNotIn("本月买入维超限", rep, f"❌ n_buys={n} 误报超限")

    def test_12_tagged_decision_shows_in_ledger_column(self):
        """⑥ 留痕列：本月带该 tag 的决策 ⇒ 对应逐笔行显示 `✅ #id`（差额＝超限未留痕）。"""
        self.write_tagged_log([{"id": "7", "date": "2026-09-03", "amount": 300.0,
                                "tags": [dl.QUOTA_TAG], "fund": "夹具买入3"}])
        rep = g.build_report(pf(5), 2026, 9)
        self.assertIn("记录 **1** 条（#7）", rep)
        self.assertIn("留痕 1 vs 超限 3", rep)
        row = next(ln for ln in rep.splitlines() if "夹具买入3" in ln and ln.startswith("| 3 "))
        self.assertIn("✅ #7", row, f"❌ 超限逐笔行未关联留痕：{row}")


# ══════════════════════════════════════════════════════════════════
PROBE_DRIVER = r'''
import contextlib, importlib.util, io, json, sys, tempfile
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location("probe_152", r"{probe}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class F(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 25, 10, 0, 0)


tmp = tempfile.mkdtemp(prefix="anchor_152_probe_")
mod.datetime = F
mod.LOG_FILE = Path(tmp) / "decision_log.json"
pf = Path(tmp) / "portfolio_data.json"
pf.write_text(json.dumps({{"transactions": [
    {{"date": "2026-09-0%d" % i, "op": "买入", "name": "夹具", "amount": 300.0}}
    for i in (1, 2)], "_meta": {{"monthly_buys_max": 2, "monthly_sells_max": 2,
                                 "max_monthly_ops": 4}}}}, ensure_ascii=False), encoding="utf-8")
with contextlib.redirect_stdout(io.StringIO()):
    did = mod.log_decision("加仓", "夹具基金", "执行买入", 300, "夹具", "涨", pf_path=str(pf))
rec = next(d for d in json.loads(mod.LOG_FILE.read_text(encoding="utf-8"))["decisions"]
           if d["id"] == did)
print("TAGS=" + json.dumps(rec["tags"], ensure_ascii=False))
'''


class TestReverseAssertion(_Base):
    def _run_probe_src(self, src_text, probe_path) -> str:
        """把源码文本写成**同目录**探针模块，子进程跑一遍，返回输出（含 `TAGS=[...]`）。

        ⚠️ 探针必须写在 `SCRIPTS` 同目录（脚本靠 `sys.path[0]` 导入兄弟模块 `paths`/`data_processor`）
        —— 放别处会以 `ImportError` 失败，而那种失败会被误读成「反向断言通过」。"""
        with io.open(probe_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(src_text)
        driver = PROBE_DRIVER.format(probe=probe_path.replace("\\", "\\\\"))
        r = subprocess.run([PY, "-c", driver], capture_output=True, cwd=SCRIPTS)
        return (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")

    def test_13_reverse_removing_tag_write_makes_positive_fail(self):
        """🔴 ⑦ 反向（承重）：删掉打标两行（＝改回旧写法）⇒ tags 不含该 tag ⇒ ① 必红。"""
        probe2 = PROBE + ".broken.py"
        try:
            with io.open(DECISION_LOG_PY, encoding="utf-8") as f:
                real_src = f.read()
            # 先证**探针工装本身有效**：真源码跑 ⇒ 必须打出 tag（否则反向断言无鉴别力）
            good = self._run_probe_src(real_src, PROBE)
            self.assertIn(dl.QUOTA_TAG, good,
                          f"❌ 工装无效：真源码未打出 tag ⇒ 反向断言无意义\n{good[-400:]}")
            # 再删掉打标块（＝改回旧写法）
            m = re.search(r'\n\s*if _q\["tag"\]:\n\s*entry\["tags"\]\.append\(_q\["tag"\]\)\n', real_src)
            self.assertIsNotNone(m, "❌ 反向夹具无法定位打标块（源码结构已变 ⇒ 请更新本测试）")
            broken = real_src[:m.start()] + "\n" + real_src[m.end():]
            out = self._run_probe_src(broken, probe2)
            self.assertNotIn(dl.QUOTA_TAG, out,
                             f"❌ 删掉打标行后仍打出 tag ⇒ 该打标不是承重的（本测试无鉴别力）\n{out[-400:]}")
        finally:
            for p in (PROBE, probe2):
                if os.path.exists(p):
                    os.remove(p)
        for p in (PROBE, probe2):
            self.assertFalse(os.path.exists(p), f"❌ 反向探针未清理（零残留断言）：{p}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
