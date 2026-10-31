#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_ledger_audit.py — 故障注入测试（Anchor v4.5）

【为什么存在】
一个「看起来通过」的校验器毫无价值。必须证明：
    **把 2026-10-31 真实发生过的每一类错误重新放进去，它都会亮红。**
本测试不做合成数据空跑（那是 test_calculations 的职责），
而是拿**真实的 portfolio_data.json 做基线**，逐个注入已知错误，
断言「对应的那条断言被触发」。

基线必须先全绿化 —— 否则测的就是一个本来就坏的东西。

用法：
    python test_ledger_audit.py            # 全部
    python test_ledger_audit.py -v         # 逐条明细
退出码：0 全部通过 / 1 有失败
"""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import paths
from ledger_audit import run_audit, scan_direct_writers


def load_base():
    with open(paths.DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


BASE = load_base()


def fails_of(data):
    return {c.cid for c in run_audit(data).failed}


class TestBaseline(unittest.TestCase):
    """基线必须干净，否则后续注入测试不可信。"""

    def test_baseline_is_clean(self):
        aud = run_audit(BASE)
        f = [f"{c.cid} {c.title}｜{c.detail[:80]}" for c in aud.failed]
        self.assertEqual(f, [], "基线数据本身未通过审计，先修数据再谈回归")

    def test_all_groups_present(self):
        aud = run_audit(BASE)
        groups = {c.gid for c in aud.checks}
        self.assertEqual(groups, {"G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"})


class FaultInjection(unittest.TestCase):
    """每一例都对应 2026-10-31 真实踩过的坑。"""

    def _m(self):
        return copy.deepcopy(BASE)

    # ---- ① 在途记成「申报额」而不是「到账额」（#C1-56，今天最贵的一个错）----
    def test_transit_uses_declared_not_actual(self):
        d = self._m()
        rows = d["_meta"]["drawdown_ledger_daily_2026_10"]["daily"]
        hit = [r for r in rows if r.get("in_transit")]
        self.assertTrue(hit, "基线里应存在带在途的行，否则本测试无意义")
        for r in hit:
            r["in_transit"] = round(r["in_transit"] * 0.9581, 2)   # 退回申报额 2,658
        self.assertIn("A6.2", fails_of(d))

    # ---- ② 台账累计字段留空（曾经 15 行全空，等于不可复算）----
    def test_ledger_cum_missing(self):
        d = self._m()
        rows = d["_meta"]["drawdown_ledger_daily_2026_10"]["daily"]
        n = 0
        for r in rows:
            if r.get("total_assets") and r.get("cum_net_outflow_total") is not None:
                r["cum_net_outflow_total"] = None
                n += 1
        self.assertGreater(n, 0)
        f = fails_of(d)
        self.assertIn("A3.1", f)
        self.assertIn("A3.2", f)

    # ---- ③ 周末流水漏计（#C1-54，曾算出 −42% 假回撤）----
    def test_weekend_flow_dropped(self):
        d = self._m()
        ef = d["_meta"]["drawdown_ledger_20261031"]["monthly_oct"]["external_flows_2026_10"]
        # 删掉 10/17（周六）的腿，模拟「按交易日精确匹配」的漏计
        drop = [k for k in ef["out"] if k.startswith("10/17")]
        self.assertTrue(drop, "基线应有 10/17 流水")
        for k in drop:
            del ef["out"][k]
        ef["out"]["合计"] = round(ef["out"]["合计"] - 30000, 2)
        f = fails_of(d)
        self.assertTrue({"A5.1", "A5.3"} & f, f"A5 组应报警，实际 {f}")

    # ---- ④ 三口径混用：L1 用 in_cash 而不是负债全额（#C1-52，L1 一天改五次）----
    def test_l1_uses_in_cash(self):
        d = self._m()
        d["_meta"]["liabilities"]["total"] = 7023.77        # 错记成 in_cash
        f = fails_of(d)
        self.assertTrue({"A1.4", "A1.5"} & f, f"负债自洽类断言应报警，实际 {f}")

    # ---- ⑤ 账外资产漏记（曾漏 33,840.81，L1 少算一个月）----
    def test_offbook_missing(self):
        d = self._m()
        for k in list(d["_meta"].keys()):
            if k.startswith("offbook"):
                d["_meta"].pop(k)
        f = fails_of(d)
        self.assertTrue({"A1.3", "A1.5"} & f, f"L1 类断言应报警，实际 {f}")

    # ---- ⑥ 子账户加不回总资产 ----
    def test_total_mismatch(self):
        d = self._m()
        d["total_assets"] = round(float(d["total_assets"]) + 100, 2)
        self.assertIn("A0.1", fails_of(d))

    # ---- ⑦ chart_data 日期字段全空（曾沉默通过）----
    def test_chart_dates_blank(self):
        d = self._m()
        for x in d["chart_data"]:
            x.pop("d", None)
            x.pop("date", None)
        self.assertIn("A0.4", fails_of(d))

    # ---- ⑧ chart_data 缺日（曾缺 10 天，曲线悄悄断）----
    def test_chart_missing_days(self):
        d = self._m()
        d["chart_data"] = [x for x in d["chart_data"] if not str(x.get("d", "")).startswith("10-1")]
        self.assertIn("A0.7", fails_of(d))

    # ---- ⑨ star 存成创业板指（曾 12 条污染，note 写了却没改）----
    def test_star_is_cyb(self):
        d = self._m()
        kc = (d.get("market") or {}).get("kc", {}).get("close")
        cyb = (d.get("market") or {}).get("zq", {}).get("close")
        if not kc or not cyb:
            self.skipTest("market 块无 kc/zq")
        d["chart_data"][-1]["star"] = cyb
        self.assertIn("A0.8", fails_of(d))

    # ---- ⑩ 日台账净值算错（改一个数看能不能被抓）----
    def test_ledger_networth_off(self):
        d = self._m()
        rows = [r for r in d["_meta"]["drawdown_ledger_daily_2026_10"]["daily"] if r.get("net_worth")]
        rows[len(rows) // 2]["net_worth"] = round(rows[len(rows) // 2]["net_worth"] + 500, 2)
        f = fails_of(d)
        self.assertTrue({"A3.2", "A4.1"} & f, f"应报净值复算或桥接失败，实际 {f}")

    # ---- ⑪ 数据停更（血教训：JSON 停更 13 天引擎仍报绿）----
    def test_stale_data(self):
        d = self._m()
        d["update_date"] = "2026-09-01"
        self.assertIn("A7.1", fails_of(d))

    # ---- ⑫ 余额链残差留白（曾挂 2,297.45 一整天不结案）----
    def test_chain_residual_unexplained(self):
        d = self._m()
        chain = d["_meta"]["alipay_reconciliation_20261031"]["balance_chain_verification"]
        for seg in chain:
            if seg.get("residual") and abs(float(seg["residual"])) > 0.5:
                seg.pop("verdict", None)
        self.assertIn("A6.3", fails_of(d))


class SafeWriteGate(unittest.TestCase):
    """证明门禁真的会拦下写入，且原文件一个字节都没变。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="anchor_gate_"))
        self.target = self.tmpdir / "portfolio_data.json"
        shutil.copy2(paths.DATA_PATH, self.target)
        self.before = self.target.read_bytes()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_rejects_broken_write(self):
        from safe_write import commit, AuditRejected

        def bad(data):
            data["total_assets"] = float(data["total_assets"]) + 999

        with self.assertRaises(AuditRejected):
            commit(bad, reason="注入错误，应被拒绝", data_path=self.target, verbose=False)
        self.assertEqual(self.target.read_bytes(), self.before,
                         "被拒绝的写入不得改动原文件")

    def test_accepts_clean_write(self):
        from safe_write import commit

        def ok(data):
            data["_meta"]["gate_probe"] = "ok"

        aud = commit(ok, reason="写入门禁自测：无副作用变更",
                     data_path=self.target, verbose=False)
        self.assertEqual([c.cid for c in aud.failed], [])
        after = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(after["_meta"]["gate_probe"], "ok")
        self.assertTrue(any(e.get("reason", "").startswith("写入门禁自测")
                            for e in after["_meta"].get("write_log", [])))

    def test_requires_reason(self):
        from safe_write import commit

        with self.assertRaises(ValueError):
            commit(lambda x: None, reason="   ", data_path=self.target, verbose=False)


class GateBypass(unittest.TestCase):
    """门禁真正的软肋不是「拒绝坏数据」，而是「可以被完全绕过」。
    这一组证明：绕过之后是**可检测**的 —— 哪怕只改了 1 元。
    没有这一组，safe_write 就只是「一条建议」。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="anchor_bypass_"))
        self.target = self.tmpdir / "portfolio_data.json"
        shutil.copy2(paths.DATA_PATH, self.target)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_direct_json_dump_is_detected(self):
        from safe_write import commit
        commit(lambda d: None, reason="建立基线", data_path=self.target, verbose=False)

        with open(self.target, encoding="utf-8") as f:
            d = json.load(f)
        d["total_assets"] = float(d["total_assets"]) + 1     # 只改 1 元
        with open(self.target, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

        with open(self.target, encoding="utf-8") as f:
            aud = run_audit(json.load(f))
        ids = {c.cid for c in aud.failed}
        self.assertIn("A9.2", ids, "绕过门禁的写入必须被内容指纹检出，否则门禁形同虚设")

    def test_gated_write_keeps_fingerprint_valid(self):
        from safe_write import commit
        commit(lambda d: d["_meta"].__setitem__("probe_a", 1),
               reason="第一次变更", data_path=self.target, verbose=False)
        commit(lambda d: d["_meta"].__setitem__("probe_b", 2),
               reason="第二次变更", data_path=self.target, verbose=False)
        with open(self.target, encoding="utf-8") as f:
            aud = run_audit(json.load(f))
        self.assertEqual([c.cid for c in aud.failed], [],
                         "连续两次走门禁的写入之后，指纹应仍然有效")


class GateIsTheOnlyDoor(unittest.TestCase):
    """A9.2 只能事后说「有人绕过了」，说不了「还有几条旁路在」。

    只要还有脚本自己 json.dump，每天正常同步一次就把 A9.2 推红一次；
    常在红的断言必然被关掉 —— 门禁就是在这一步死掉的。
    A9.4 把「旁路存在」本身变成 FAIL。
    """

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="anchor_sidechannel_"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, body):
        (self.tmpdir / name).write_text(body, encoding="utf-8")

    def test_direct_open_write_is_flagged(self):
        self._write("bad_direct.py",
                    "import json\n"
                    "from paths import DATA_PATH\n"
                    "with open(DATA_PATH, 'w', encoding='utf-8') as f:\n"
                    "    json.dump({}, f)\n")
        self.assertEqual(scan_direct_writers(self.tmpdir), ["bad_direct.py"],
                         "open(DATA_PATH,'w') 这种最直白的旁路必须被抓到")

    def test_alias_and_atomic_replace_are_flagged(self):
        # 真实案例：sync_derived_fields 当年是「写 tmp + os.replace(tmp, p)」，没有 open(p,'w')
        self._write("bad_alias.py",
                    "import json, os\n"
                    "import paths\n"
                    "p = paths.DATA_PATH\n"
                    "tmp = str(p) + '.tmp'\n"
                    "with open(tmp, 'w', encoding='utf-8') as f:\n"
                    "    json.dump({}, f)\n"
                    "os.replace(tmp, p)\n")
        self.assertEqual(scan_direct_writers(self.tmpdir), ["bad_alias.py"],
                         "别名 + os.replace 的原子写法不能被漏掉（这正是当初漏的那种）")

    def test_reading_and_side_files_are_not_flagged(self):
        self._write("good_reader.py",
                    "import json\n"
                    "import paths\n"
                    "with open(paths.DATA_PATH, encoding='utf-8') as f:\n"
                    "    d = json.load(f)\n"
                    "with open('candidates.json', 'w', encoding='utf-8') as f:\n"
                    "    json.dump(d, f)\n")
        self.assertEqual(scan_direct_writers(self.tmpdir), [],
                         "只读 + 写别的文件，不算旁路；否则这条断言会因为误报被关掉")

    def test_production_scripts_have_no_side_channel(self):
        self.assertEqual(scan_direct_writers(), [],
                         "05-scripts 下除 safe_write.py 外不得有脚本直接写 portfolio_data.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
