#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ledger_audit.py — 账本不变量审计器（Anchor v4.5）

【为什么存在】
2026-10-31 一天之内连挖出四处账本错误：在途记了申报额、台账 15 行累计字段为空、
周末流水被精确匹配漏掉、三口径被混用。这些错误的共同点是：
    **每一处都是事后才发现的，没有一处是写入时被拦下的。**
把口径写进手册 = 没有，因为不会有任何东西因此报错。
本脚本把口径条款变成可执行断言，让「不一致」在写入那一刻就失败。

【覆盖的规则】
  #C1-38 / #C1-52  三口径分离（L1 总财富 / L2 场内本金 / L3 投资净值）
  #C1-44           备用金下限
  #C1-53           在途资金计入净值
  #C1-54           累计量按「≤ 日期」推进（周末流水不得漏计）
  #C1-55           检索缺失不得单模式定论（由 evidence_index.py 配合）
  #C1-56           申报额 ≠ 到账额
  F8①             只许加严：不确定的流出不得加回净值
  血教训           JSON 停更 >3 交易日 ⇒ 引擎输出不可信

【用法】
    python ledger_audit.py                # 全量审计，PASS/FAIL 清单
    python ledger_audit.py --json         # 机器可读（供门禁/CI）
    python ledger_audit.py --quiet        # 只出 FAIL 与汇总
    python ledger_audit.py --group G3     # 只跑某一组
    python ledger_audit.py --fix-hints    # FAIL 时附带修复建议

退出码：0 全部通过 / 1 存在 FAIL / 2 数据文件读不出

变更管理：新增口径条款时必须同步在此登记断言，否则该条款视为未生效。
"""
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import paths

# ============ 容差（金额元 / 百分比 pp） ============
TOL_AMT = 0.05
TOL_PCT = 0.005
TOL_DAY = 0.5


@dataclass
class Check:
    gid: str
    cid: str
    title: str
    status: str = "SKIP"          # PASS / FAIL / WARN / SKIP
    detail: str = ""
    fix: str = ""
    rule: str = ""

    @property
    def ok(self):
        return self.status in ("PASS", "SKIP")


@dataclass
class Audit:
    checks: list = field(default_factory=list)

    def add(self, gid, cid, title, status, detail="", fix="", rule=""):
        self.checks.append(Check(gid, cid, title, status, detail, fix, rule))

    def guard(self, gid, cid, title, fn, rule=""):
        """跑一个返回 (ok, detail, fix) 的断言函数，异常记为 FAIL 而非崩溃。"""
        try:
            ok, detail, fix = fn()
        except Exception as e:
            ok, detail, fix = False, f"断言自身异常：{type(e).__name__}: {e}", "检查数据结构是否变更"
        self.add(gid, cid, title, "PASS" if ok else "FAIL", detail, fix, rule)

    def counts(self):
        c = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}
        for x in self.checks:
            c[x.status] = c.get(x.status, 0) + 1
        return c

    @property
    def failed(self):
        return [c for c in self.checks if c.status == "FAIL"]


def approx(a, b, tol=TOL_AMT):
    return abs(float(a) - float(b)) <= tol


def f2(x):
    try:
        return f"{float(x):,.2f}"
    except (TypeError, ValueError):
        return str(x)


# ============================================================
# 取数与派生
# ============================================================
class Ledger:
    def __init__(self, data):
        self.d = data
        self.m = data.get("_meta", {}) or {}
        self.liab = self.m.get("liabilities", {}) or {}
        self.in_cash = float(self.liab.get("in_cash", 0) or 0)
        self.debt_total = float(self.liab.get("total", 0) or 0)
        self.peak = float(self.m.get("peak_assets", 0) or 0)
        self.net_outflow = float(self.m.get("net_outflow_total", 0) or 0)
        self.total = float(data.get("total_assets", 0) or 0)

    # --- 三口径 ---
    @property
    def L2(self):
        return self.total - self.in_cash

    @property
    def L3(self):
        return self.L2 + self.net_outflow

    def card_cash(self):
        bc = self.m.get("bank_card_20261031", {}) or {}
        return float(bc.get("balance", 0) or 0)

    def offbook_block(self):
        """返回账外资产块的键名与内容；没有则 (None, None)。
        区分「没有登记」与「登记为 0」—— 前者是漏记，后者是事实。"""
        for k, v in self.m.items():
            if k.startswith("offbook_assets") and isinstance(v, dict):
                return k, v
        return None, None

    def offbook(self):
        _k, ob = self.offbook_block()
        if not ob:
            return 0.0
        for key in ("total", "amount", "mv", "value"):
            if key in ob:
                try:
                    return float(ob[key])
                except (TypeError, ValueError):
                    pass
        # 兼容「按子项列示」的写法：把子项金额加起来
        s = 0.0
        for v in ob.values():
            if isinstance(v, dict) and any(x in v for x in ("amount", "mv", "value")):
                for x in ("amount", "mv", "value"):
                    if x in v:
                        try:
                            s += float(v[x])
                        except (TypeError, ValueError):
                            pass
                        break
        return s

    @property
    def L1(self):
        return self.total - self.debt_total + self.card_cash() + self.offbook()

    def dd_pct(self):
        if not self.peak:
            return None
        return (self.L3 - self.peak) / self.peak * 100

    # --- 台账 ---
    def ledger(self):
        for key in ("drawdown_ledger_daily_2026_10", "drawdown_ledger_daily_2026_11"):
            blk = self.m.get(key)
            if blk and blk.get("daily"):
                return key, blk
        return None, None

    def flows(self):
        """从 10 月外部流水表构造 [(date, 净流出额, label)]，正=流出。"""
        for mk in ("drawdown_ledger_20261031", "drawdown_ledger_20261030"):
            blk = self.m.get(mk)
            if not blk:
                continue
            mo = blk.get("monthly_oct") or {}
            ef = mo.get("external_flows_2026_10")
            if ef:
                break
        else:
            return [], None
        rows = []
        for k, v in (ef.get("out") or {}).items():
            if k == "合计":
                continue
            md = k.split(" ")[0]
            try:
                mo_, dy_ = md.split("/")
                rows.append((date(2026, int(mo_), int(dy_)), float(v), k))
            except (ValueError, IndexError):
                continue
        for k, v in (ef.get("in") or {}).items():
            if k == "合计":
                continue
            md = k.split(" ")[0]
            try:
                mo_, dy_ = md.split("/")
                rows.append((date(2026, int(mo_), int(dy_)), -float(v), k))
            except (ValueError, IndexError):
                continue
        rows.sort()
        return rows, ef


# ============================================================
# G0 · 结构自洽
# ============================================================
def build(aud: Audit, L: Ledger):
    d = L.d

    aud.guard("G0", "A0.1", "total_assets = 基金账户 + 股票账户", lambda: (
        approx(d.get("fund_account", 0) + d.get("stock_account", 0), L.total),
        f"{f2(d.get('fund_account', 0))} + {f2(d.get('stock_account', 0))} = "
        f"{f2(d.get('fund_account', 0) + d.get('stock_account', 0))} vs total {f2(L.total)}",
        "两个子账户之和必须等于 total_assets，差额说明有一边漏记或多记"), "三口径")

    def _fund_sum():
        hs = d.get("holdings_summary", []) or []
        if not hs:
            return False, "holdings_summary 为空", "补持仓明细"
        s = sum(float(x.get("mv", 0) or 0) for x in hs)
        return (approx(s, d.get("fund_account", 0)),
                f"Σmv {f2(s)}（{len(hs)} 条）vs fund_account {f2(d.get('fund_account', 0))}",
                "持仓市值之和必须等于基金账户总额；不等说明有持仓未登记或 mv 过期")
    aud.guard("G0", "A0.2", "fund_account = Σ holdings_summary.mv", _fund_sum, "资产全集盘点")

    def _stock_sum():
        sh = d.get("stock_holdings", []) or []
        if not sh:
            return True, "无股票持仓（跳过）", ""
        s = sum(float(x.get("mv", 0) or 0) for x in sh)
        return (approx(s, d.get("stock_account", 0)),
                f"Σmv {f2(s)}（{len(sh)} 条）vs stock_account {f2(d.get('stock_account', 0))}",
                "股票持仓市值之和必须等于股票账户总额")
    aud.guard("G0", "A0.3", "stock_account = Σ stock_holdings.mv", _stock_sum, "资产全集盘点")

    def _cd_dates():
        """兼容 chart_data 的 d（MM-DD）/date（YYYY-MM-DD）两种写法，
        并强制「有条目就必须有日期」—— 全空日期曾被误判为 PASS（沉默通过）。"""
        cd = d.get("chart_data", []) or []
        if not cd:
            return False, "chart_data 为空", "至少要有历史序列，否则趋势/回撤图无法呈现"
        got, bad = [], 0
        for x in cd:
            v = x.get("date") or x.get("d")
            if v:
                got.append(str(v))
            else:
                bad += 1
        if bad:
            return False, f"{len(cd)} 条中有 {bad} 条无日期字段（d/date 均空）", \
                "日期是时间轴的唯一锚点，缺日期等于该点无法定位；⛔ 不得用空日期蒙混通过"
        return True, f"{len(cd)} 条全部有日期", ""
    aud.guard("G0", "A0.4", "chart_data 每条都有日期", _cd_dates)

    def _dup_dates():
        cd = d.get("chart_data", []) or []
        ds = [str(x.get("date") or x.get("d")) for x in cd if (x.get("date") or x.get("d"))]
        dup = {x for x in ds if ds.count(x) > 1}
        if dup:
            return False, f"chart_data 重复日期：{sorted(dup)}", "删除重复行，否则图表时间轴错位"
        return True, f"{len(ds)} 条，无重复", ""
    aud.guard("G0", "A0.5", "chart_data 日期无重复", _dup_dates)

    def _sorted_dates():
        cd = d.get("chart_data", []) or []
        ds = [str(x.get("date") or x.get("d")) for x in cd if (x.get("date") or x.get("d"))]
        if not ds:
            return False, "无有效日期可排", "先修 A0.4"
        if ds != sorted(ds):
            return False, "chart_data 非升序", "按日期升序排列，否则折线会回勾"
        return True, "升序正确", ""
    aud.guard("G0", "A0.6", "chart_data 日期升序", _sorted_dates)

    def _chart_covers_ledger():
        """台账是逐日真相，chart_data 是它的可视化派生视图。
        台账有读数的日子，chart_data 必须有对应点 —— 否则仪表盘曲线是断的，
        而断掉的曲线会让「本月到底怎么走的」重新变成不可见（这就是 10 月缺 10 天的成因）。"""
        key, blk = L.ledger()
        if not blk:
            return True, "无台账可比", ""
        led = {r["date"] for r in blk.get("daily", []) if r.get("total_assets")}
        cd = d.get("chart_data", []) or []
        have = set()
        for x in cd:
            v = str(x.get("date") or x.get("d") or "")
            if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                have.add(v)
            elif re.match(r"^\d{2}-\d{2}$", v):
                have.add(f"{L.d.get('update_date', '')[:4]}-{v}")
        miss = sorted(led - have)
        if miss:
            return (False, f"台账 {len(led)} 天有读数，chart_data 缺 {len(miss)} 天：{', '.join(miss)}",
                    "跑 gen_daily_hub 或 rebuild_derived 重新派生 chart_data；"
                    "⛔ 不得让台账与图表长期不一致 —— 那是「数据在里面但看不见」")
        return True, f"台账 {len(led)} 天全部有图表点", ""
    aud.guard("G0", "A0.7", "chart_data 覆盖台账全部有读数日", _chart_covers_ledger, "多副本同步")

    def _chart_vs_market():
        """chart_data 末条必须与 market 块逐项一致。
        这条针对「同一事实存多份、改一份忘另一份」——
        10/30 的 star 曾写成创业板指 2413.63（科创50 实为 1160.84），
        而 note 里早就写了「kechuang50 字段实际存创业板指」，说明**发现了却没改数据**。"""
        mk = d.get("market", {}) or {}
        cd = d.get("chart_data", []) or []
        if not mk or not cd:
            return True, "无 market 块可比", ""
        last = cd[-1]
        mdate = mk.get("date")
        ldate = str(last.get("date") or last.get("d") or "")
        bad = []
        if mdate and ldate:
            short = mdate[5:] if re.match(r"^\d{4}-", mdate) else mdate
            if ldate not in (mdate, short):
                bad.append(f"末条日期 {ldate} ≠ market.date {mdate}")
        pairs = [("sh", "sh"), ("star", "kc"), ("pnl", None)]
        for ck, mkk in pairs:
            if ck not in last:
                continue
            if mkk and mkk in mk and mk[mkk].get("close") is not None:
                if not approx(last[ck], mk[mkk]["close"], 0.02):
                    bad.append(f"末条 {ck}={f2(last[ck])} vs market.{mkk}.close={f2(mk[mkk]['close'])}")
        if bad:
            return False, "；".join(bad), \
                "chart_data 必须由 market 块派生，⛔ 不得各自维护；字段语义变更须同时改数据而非只写 note"
        return True, "末条与 market 块一致（sh / star↔kc）", ""
    aud.guard("G0", "A0.8", "chart_data 末条 = market 块", _chart_vs_market, "多副本同步")

    def _star_gap():
        """近期 star 跳变检测。两条约束避免误报：
        ① 只看最近 12 个点（远期数据中间隔长假，跳变大属正常）；
        ② 只在相邻两点日期间隔 ≤5 个自然日时判定 —— 隔了缺口就不是单日跳。
        近期数据本应逐日连续，出现 ±15% 以上的跳变基本可断定字段被换成了另一个指数
        （10-09 的 1457 → 10-28 的 2634 即此，实为创业板指）。"""
        cd = [x for x in (d.get("chart_data", []) or []) if x.get("star") is not None]
        if len(cd) < 3:
            return True, "样本不足", ""

        def _dt(x):
            v = str(x.get("date") or x.get("d") or "")
            try:
                if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                    return date.fromisoformat(v)
                if re.match(r"^\d{2}-\d{2}$", v):
                    return date(2026, int(v[:2]), int(v[3:]))
            except ValueError:
                return None
            return None

        rec = cd[-12:]
        bad = []
        for i in range(1, len(rec)):
            a, b = rec[i - 1], rec[i]
            da, db = _dt(a), _dt(b)
            if not da or not db:
                continue
            if (db - da).days > 5:
                continue
            try:
                pa, pb = float(a["star"]), float(b["star"])
            except (TypeError, ValueError):
                continue
            if pa <= 0:
                continue
            chg = (pb - pa) / pa * 100
            if abs(chg) > 15:
                bad.append(f"{a.get('d') or a.get('date')} {f2(pa)} → "
                           f"{b.get('d') or b.get('date')} {f2(pb)}（{chg:+.1f}%，相隔 {(db - da).days} 天）")
        if bad:
            return (False, "近期 " + "；".join(bad[:4]),
                    "科创50 不可能在几个交易日内这样跳，该段 star 存的是别的指数（多半是创业板指）；"
                    "须回查原始报告改正，⛔ 不得按比例推算补值（F5）")
        return True, f"最近 {len(rec)} 个点，相邻且近距的跳变均 ≤15%", ""
    aud.guard("G0", "A0.9", "chart_data.star 近期连续（语义 = 科创50）", _star_gap, "字段口径")


# ============================================================
# G1 · 三口径（#C1-38 / #C1-52 / F10）
# ============================================================
def build_g1(aud: Audit, L: Ledger):
    aud.guard("G1", "A1.1", "L2 场内本金 = total − in_cash", lambda: (
        True, f"L2 = {f2(L.L2)}（total {f2(L.total)} − in_cash {f2(L.in_cash)}）", ""),
        "#C1-38")

    aud.guard("G1", "A1.2", "L3 投资净值 = L2 + 净转出", lambda: (
        True, f"L3 = {f2(L.L3)}（L2 {f2(L.L2)} + 净转出 {f2(L.net_outflow)}）", ""),
        "#C1-38")

    def _l1():
        if L.debt_total <= 0:
            return False, "liabilities.total 为空或 0，L1 无法成立", "必须记录未偿还负债余额"
        if L.card_cash() <= 0:
            return False, "卡内现金未登记，L1 会漏算", "补 bank_card 块"
        k, _ob = L.offbook_block()
        if k is None:
            return (False,
                    f"未发现任何 offbook_assets_* 块 ⇒ L1 按 0 计算，账外资产会被整段漏掉。"
                    f"当前 L1 = {f2(L.total - L.debt_total + L.card_cash())}（未含账外）",
                    "⛔ 账外资产必须显式登记，**没有也要写 0** —— 靠缺省等于把「漏记」设计成默认行为"
                    "（当年 33,840.81 就是这样消失了一个月）")
        calc = L.total - L.debt_total + L.card_cash() + L.offbook()
        return (True,
                f"L1 = {f2(calc)} = 账上 {f2(L.total)} − 负债 {f2(L.debt_total)} "
                f"+ 卡内 {f2(L.card_cash())} + 账外 {f2(L.offbook())}（来源块 {k}）", "")
    aud.guard("G1", "A1.3", "L1 总财富 = 账上 − 未还负债 + 卡内 + 账外", _l1, "#C1-52 / #C1-49")

    def _debt_consistency():
        pr = L.liab.get("principal")
        rp = L.liab.get("repaid")
        if pr is None or rp is None:
            return True, f"未拆分本金/已还，仅用 total={f2(L.debt_total)}（兼容旧数据）", ""
        calc = float(pr) - float(rp)
        return (approx(calc, L.debt_total),
                f"本金 {f2(pr)} − 已还 {f2(rp)} = {f2(calc)} vs total {f2(L.debt_total)}",
                "#C1-52：total 必须是未还余额，不得按到账额或本金记")
    aud.guard("G1", "A1.4", "负债自洽：total = 本金 − 已还", _debt_consistency, "#C1-52")

    def _l1_vs_l3():
        """L1 与 L3 的差必须能被公式完全解释，否则说明某一口径用错了基数。
        L1 = total − 负债 + 卡内 + 账外
        L3 = total − in_cash + 净转出
        相减 ⇒ L1 − L3 = 卡内 + 账外 − (负债 − in_cash) − 净转出
        """
        gap = L.L1 - L.L3
        explain = L.card_cash() + L.offbook() - (L.debt_total - L.in_cash) - L.net_outflow
        if not approx(gap, explain, 1.0):
            return (False,
                    f"L1 − L3 = {f2(gap)}，但按「卡内 + 账外 − (负债 − in_cash) − 净转出」应为 "
                    f"{f2(explain)}，差 {f2(gap - explain)}",
                    "三口径之间必须能互相推导；对不上说明某一口径用错了基数（#C1-52 最易错）")
        return (True, f"L1 − L3 = {f2(gap)}，与公式解 {f2(explain)} 相符（可解释，非混用）", "")
    aud.guard("G1", "A1.5", "L1 与 L3 的差额可被公式完全解释", _l1_vs_l3, "#C1-38 / F10")

    def _caliber_block():
        blk = L.m.get("capital_three_calibers_20261031")
        if not blk:
            return True, "未建三口径块（跳过）", ""
        pairs = [("on_acct_own", L.L2, "L2"), ("invest_net_worth", L.L3, "L3")]
        bad = []
        for k, expect, label in pairs:
            if k in blk and not approx(blk[k], expect, 1.0):
                bad.append(f"{label} 块内 {f2(blk[k])} vs 实算 {f2(expect)}")
        if bad:
            return False, "；".join(bad), "派生块算完未回填，或回填后源数据又变了 —— 须重算"
        return True, "三口径派生块与实时计算一致", ""
    aud.guard("G1", "A1.6", "三口径派生块与实时计算一致", _caliber_block, "#C1-38")


# ============================================================
# G2 · 回撤
# ============================================================
def build_g2(aud: Audit, L: Ledger):
    def _peak():
        if L.peak <= 0:
            return False, "peak_assets 缺失", "必须设定峰值基准"
        note = str(L.m.get("peak_note", ""))
        if "2026" not in note:
            return False, f"peak_note 无日期出处：{note[:60]}", "峰值必须写明取自哪一天哪个口径"
        return True, f"peak = {f2(L.peak)}，note 有出处", ""
    aud.guard("G2", "A2.1", "峰值有出处（日期 + 口径）", _peak, "回撤基准")

    def _dd():
        calc = L.dd_pct()
        if calc is None:
            return False, "无法计算回撤", "补 peak"
        return True, f"回撤 = ({f2(L.L3)} − {f2(L.peak)}) / {f2(L.peak)} = {calc:.3f}%", ""
    aud.guard("G2", "A2.2", "回撤 = (L3 − peak) / peak", _dd, "#C1-38")

    def _lines():
        want = {"-5%": L.peak * 0.95, "-10%": L.peak * 0.90, "-15%": L.peak * 0.85}
        note = str(L.m.get("peak_note", ""))
        bad = []
        for label, v in want.items():
            if f"{v:,.2f}" not in note and f"{v:,.0f}" not in note:
                bad.append(f"{label} 应 ≈ {f2(v)}")
        if bad:
            return False, "；".join(bad) + "（peak_note 未同步）", "峰值变动后三线必须同步重算并写回 note"
        return True, "三线与 peak 自洽且已写入 note", ""
    aud.guard("G2", "A2.3", "三条警戒线与 peak 自洽", _lines, "§4.1")

    def _cushion():
        line5 = L.peak * 0.95
        return True, f"距 −5% 线安全垫 = {f2(L.L3 - line5)}", ""
    aud.guard("G2", "A2.4", "安全垫计算", _cushion, "§4.1")


# ============================================================
# G3 · 台账逐日可复算（#C1-53）
# ============================================================
def build_g3(aud: Audit, L: Ledger):
    key, blk = L.ledger()
    if not blk:
        aud.add("G3", "A3.0", "日台账存在", "SKIP", "未找到 drawdown_ledger_daily_*", "若当月已建仓应建台账")
        return

    rows = blk.get("daily", [])

    def _missing():
        bad = []
        for r in rows:
            gap = r.get("total_assets") in (None, 0)
            if gap:
                continue
            for k in ("date", "total_assets", "net_worth", "drawdown_pct", "cum_net_outflow_total"):
                if r.get(k) is None:
                    bad.append(f"{r.get('date')} 缺 {k}")
        if bad:
            return False, "；".join(bad[:6]) + (f" 等 {len(bad)} 处" if len(bad) > 6 else ""), \
                "台账每行必须可独立复算：缺字段等于该日无法验证"
        return True, f"{len(rows)} 行字段完整", ""
    aud.guard("G3", "A3.1", "台账字段完整（非 GAP 行）", _missing, "#C1-53")

    def _recalc_nw():
        bad = []
        for r in rows:
            if r.get("total_assets") in (None, 0):
                continue
            calc = r["total_assets"] + (r.get("in_transit") or 0) - L.in_cash + r["cum_net_outflow_total"]
            if not approx(calc, r["net_worth"]):
                bad.append(f"{r['date']} 实算 {f2(calc)} vs 档案 {f2(r['net_worth'])}")
        if bad:
            return False, "；".join(bad[:5]) + (f" 等 {len(bad)} 天" if len(bad) > 5 else ""), \
                "净值 = total + 在途 − in_cash + 累计净转出；对不上说明某一项写错或漏记"
        return True, f"{sum(1 for r in rows if r.get('total_assets'))} 天全部吻合", ""
    aud.guard("G3", "A3.2", "净值逐日可复算", _recalc_nw, "#C1-53 / #C1-54")

    def _recalc_dd():
        bad = []
        for r in rows:
            if r.get("net_worth") is None or r.get("drawdown_pct") is None:
                continue
            calc = (r["net_worth"] - L.peak) / L.peak * 100
            if abs(calc - r["drawdown_pct"]) > TOL_PCT:
                bad.append(f"{r['date']} 实算 {calc:.3f}% vs 档案 {r['drawdown_pct']:.3f}%")
        if bad:
            return False, "；".join(bad[:5]), "回撤必须由净值直接得出，不得单独填写"
        return True, "全部一致（≤0.005pp）", ""
    aud.guard("G3", "A3.3", "回撤逐日可复算", _recalc_dd, "#C1-38")

    def _gap_no_interp():
        line5 = L.peak * 0.95
        bad = []
        for r in rows:
            if r.get("total_assets") in (None, 0) and r.get("net_worth") is not None:
                bad.append(f"{r['date']} 无读数却有净值")
            if r.get("net_worth") is not None and r.get("dist_to_minus5") is not None:
                calc = r["net_worth"] - line5
                if not approx(calc, r["dist_to_minus5"], 0.02):
                    bad.append(f"{r['date']} 安全垫实算 {f2(calc)} vs 档案 {f2(r['dist_to_minus5'])}")
        if bad:
            return False, "；".join(bad[:5]), "GAP 日必须留空（F5 禁止插值）；安全垫由净值导出"
        return True, "GAP 无插值，安全垫全部一致", ""
    aud.guard("G3", "A3.4", "GAP 日不插值 + 安全垫可复算", _gap_no_interp, "F5")

    def _last_matches():
        if not rows:
            return True, "空台账", ""
        last = [r for r in rows if r.get("net_worth") is not None]
        if not last:
            return False, "台账全为 GAP", "至少需要一天实测"
        if not approx(last[-1]["net_worth"], L.L3, 1.0):
            return (False,
                    f"末日台账净值 {f2(last[-1]['net_worth'])} vs 当前实算 L3 {f2(L.L3)}，差 {f2(last[-1]['net_worth'] - L.L3)}",
                    "台账末行必须与当前净值一致；不一致说明台账未更新或净转出变了")
        return True, f"末日 {last[-1]['date']} 净值 {f2(last[-1]['net_worth'])} = 当前 L3", ""
    aud.guard("G3", "A3.5", "台账末日 = 当前净值", _last_matches, "#C1-53")


# ============================================================
# G4 · 日程连续性（抓「在途金额写错」这类错）
# ============================================================
def build_g4(aud: Audit, L: Ledger):
    key, blk = L.ledger()
    if not blk:
        return
    rows = [r for r in blk.get("daily", []) if r.get("net_worth") is not None]
    if len(rows) < 2:
        return

    def _daily_bridge():
        """相邻日：Δ净值 必须 = Δ总资产 + Δ在途 + 当日净外部流出。
        这条能抓出「在途金额与实际到账不符」——因为实际到账体现在 total 里，
        而在途只影响净值一侧，两边必须对上。"""
        bad = []
        fl, _ = L.flows()
        flow_by_day = {}
        for fd, amt, _lbl in fl:
            flow_by_day[fd] = flow_by_day.get(fd, 0.0) + amt
        for i in range(1, len(rows)):
            a, b = rows[i - 1], rows[i]
            try:
                da = date.fromisoformat(a["date"])
                db = date.fromisoformat(b["date"])
            except (KeyError, ValueError):
                continue

            d_nw = b["net_worth"] - a["net_worth"]
            d_ta = b["total_assets"] - a["total_assets"]
            d_it = (b.get("in_transit") or 0) - (a.get("in_transit") or 0)
            flow = sum(v for k, v in flow_by_day.items() if da < k <= db)
            calc = d_ta + d_it + flow
            if not approx(calc, d_nw, TOL_DAY):
                bad.append(
                    f"{a['date']}→{b['date']} 净值变 {f2(d_nw)}，但 Δ总资产 {f2(d_ta)} "
                    f"+ Δ在途 {f2(d_it)} + 外部流 {f2(flow)} = {f2(calc)}（差 {f2(d_nw - calc)}）")
        if bad:
            return False, "；".join(bad[:4]) + (f" 等 {len(bad)} 处" if len(bad) > 4 else ""), \
                "净值桥断说明在途金额、外部流水或总资产读数三者中有一个错（#C1-53/#C1-56）"
        return True, f"{len(rows) - 1} 个交易日区间全部闭合（≤{TOL_DAY} 元）", ""
    aud.guard("G4", "A4.1", "相邻日净值桥闭合", _daily_bridge, "#C1-53 / #C1-56")


# ============================================================
# G5 · 流水独立累加 vs 台账（#C1-54）
# ============================================================
def build_g5(aud: Audit, L: Ledger):
    fl, ef = L.flows()
    if not fl:
        aud.add("G5", "A5.0", "外部流水表存在", "SKIP", "未找到 external_flows 块", "无流水则无法核销")
        return

    def _sum_match():
        s = sum(a for _d, a, _l in fl)
        declared = float(ef.get("net_outflow", 0) or 0)
        if not approx(s, declared, 0.01):
            return False, f"逐笔累加 {f2(s)} vs 声明净流出 {f2(declared)}", \
                "流水表自身不一致，先修表再谈台账"
        return True, f"逐笔累加 = 声明值 {f2(declared)}", ""
    aud.guard("G5", "A5.1", "流水表自洽（Σout − Σin = 声明净额）", _sum_match, "#C1-54")

    def _weekend_present():
        we = [(d, a, l) for d, a, l in fl if d.weekday() >= 5]
        if not we:
            return True, "本月无周末流水", ""
        names = "；".join(f"{d.isoformat()}({d.strftime('%a')}) {f2(a)}" for d, a, _l in we)
        return True, f"{len(we)} 笔发生在非交易日：{names}", \
            "这些流水必须被「≤ 日期」口径计入，不得按交易日精确匹配（#C1-54）"
    aud.guard("G5", "A5.2", "非交易日流水已识别", _weekend_present, "#C1-54")

    key, blk = L.ledger()
    if not blk:
        return
    rows = blk.get("daily", [])

    def _replay():
        """按 #C1-54 指针法独立累加，与台账 cum 逐日比对。"""
        base = float(L.m.get("net_outflow_total", 0) or 0) - sum(a for _d, a, _l in fl)
        run, ptr, bad = base, 0, []
        for r in rows:
            try:
                ds = date.fromisoformat(r["date"])
            except (KeyError, ValueError):
                continue
            while ptr < len(fl) and fl[ptr][0] <= ds:
                run += fl[ptr][1]
                ptr += 1
            if r.get("total_assets") in (None, 0):
                continue
            if r.get("cum_net_outflow_total") is None:
                bad.append(f"{r['date']} cum 为空")
                continue
            if not approx(run, r["cum_net_outflow_total"], 0.02):
                bad.append(f"{r['date']} 流水累加 {f2(run)} vs 台账 {f2(r['cum_net_outflow_total'])}")
        if bad:
            return False, "；".join(bad[:5]) + (f" 等 {len(bad)} 天" if len(bad) > 5 else ""), \
                "台账累计净转出必须能从流水独立累加得出；不等说明漏记了某笔（常见于周末）"
        return True, "按「≤ 日期」推进，逐日与台账一致", ""
    aud.guard("G5", "A5.3", "流水独立累加 = 台账累计（防周末漏计）", _replay, "#C1-54")

    def _tail():
        if not rows:
            return True, "", ""
        if not approx(L.net_outflow, float(ef.get("net_outflow", 0)) +
                      (L.net_outflow - sum(a for _d, a, _l in fl)), 0.01):
            return True, "期末净转出由 base + 当月流水构成", ""
        return True, f"net_outflow_total {f2(L.net_outflow)} 与流水口径一致", ""
    aud.guard("G5", "A5.4", "期末累计 = 基期 + 本月流水", _tail, "#C1-54")


# ============================================================
# G6 · 跨字段金额一致（#C1-56 申报额 ≠ 到账额）
# ============================================================
def build_g6(aud: Audit, L: Ledger):
    d = L.d
    txs = d.get("transactions", []) or []

    def _declared_fixes():
        """已加 amount_actual_received_* 的交易：差额必须等于声明值。"""
        bad, n = [], 0
        for t in txs:
            k_actual = [k for k in t if k.startswith("amount_actual_received")]
            if not k_actual:
                continue
            n += 1
            actual = float(t[k_actual[0]])
            amt = float(t.get("amount", 0) or 0)
            gap = actual - amt
            if "amount_discrepancy" in t:
                if not approx(gap, float(t["amount_discrepancy"]), 0.02):
                    bad.append(f"{t.get('date')} {t.get('name')} 声明差额 {f2(t['amount_discrepancy'])} "
                               f"vs 实算 {f2(gap)}")
            elif abs(gap) > max(1.0, abs(amt) * 0.01):
                bad.append(f"{t.get('date')} {t.get('name')} 差额 {f2(gap)} 未声明")
        if bad:
            return False, "；".join(bad), \
                "#C1-56：申报额与到账额不一致时必须显式声明差额，⛔ 不得默认「差不多」"
        return True, f"{n} 笔已声明到账额，差额自洽", ""
    aud.guard("G6", "A6.1", "交易记录申报额与到账额差额已声明", _declared_fixes, "#C1-56")

    def _transit_vs_actual():
        """台账在途金额必须等于对应交易的实际到账额（若有登记）。"""
        key, blk = L.ledger()
        if not blk:
            return True, "无台账", ""
        actuals = {}
        for t in txs:
            ks = [k for k in t if k.startswith("amount_actual_received")]
            if ks:
                actuals[t.get("date")] = float(t[ks[0]])
        bad = []
        for r in blk.get("daily", []):
            it = r.get("in_transit")
            if not it:
                continue
            dv = r.get("date")
            if dv in actuals and not approx(it, actuals[dv], 0.5):
                bad.append(f"{dv} 台账在途 {f2(it)} vs 交易实到 {f2(actuals[dv])}")
        if bad:
            return False, "；".join(bad), \
                "#C1-53 要求在途按实际到账额记，⛔ 不得用申报额（这条就是 2,658 vs 2,774.78 的护栏）"
        return True, "在途金额与已登记的实际到账额一致", ""
    aud.guard("G6", "A6.2", "台账在途 = 交易实际到账额", _transit_vs_actual, "#C1-53 / #C1-56")

    def _chain_residuals():
        """余额链每段的残差必须已解释（有 verdict），未解释的大额残差即 FAIL。"""
        blk = L.m.get("alipay_reconciliation_20261031", {}) or {}
        chain = blk.get("balance_chain_verification", []) or []
        if not chain:
            return True, "无余额链（跳过）", ""
        bad = []
        for seg in chain:
            res = seg.get("residual")
            if res is None:
                continue
            if abs(float(res)) <= 0.5:
                continue
            if not seg.get("verdict"):
                bad.append(f"{seg.get('segment')} 残差 {f2(res)} 无结论")
        if bad:
            return False, "；".join(bad), \
                "余额链残差 >0.5 元必须有明确结论（内部划转须附证据），⛔ 不得留白"
        return True, f"{len(chain)} 段，全部已解释或残差 ≤0.5", ""
    aud.guard("G6", "A6.3", "余额链残差全部有结论", _chain_residuals, "#C1-46")


# ============================================================
# G7 · 时效性（血教训：停更 13 天引擎仍报绿）
# ============================================================
def build_g7(aud: Audit, L: Ledger):
    def _staleness():
        ud = L.d.get("update_date")
        if not ud:
            return False, "update_date 缺失", "必须记录数据截止日"
        try:
            dud = date.fromisoformat(ud)
        except ValueError:
            return False, f"update_date 格式非法：{ud}", "统一用 YYYY-MM-DD"
        today = date.today()
        gap = (today - dud).days
        if gap > 7:
            return (False,
                    f"update_date {ud} 距今 {gap} 天（约 {gap * 5 // 7} 个交易日）⇒ **数据滞后，引擎输出不可信**",
                    "先更新数据再谈任何结论；其余审计项的 PASS 也不代表现状")
        if gap > 3:
            return (True, f"update_date {ud} 距今 {gap} 天（周末/节假日可正常）⇒ 注意确认是否已更新", "")
        return True, f"update_date {ud}，距今 {gap} 天", ""
    aud.guard("G7", "A7.1", "数据时效性（>3 交易日即失效）", _staleness, "血教训")

    def _no_unknown_stale():
        blk = L.m.get("stale_closed_20261031", {}) or {}
        items = blk.get("items", []) or []
        bad = [x.get("item", "")[:40] for x in items
               if "待证伪" in str(x.get("falsification_test", ""))
               and "已执行" not in str(x.get("falsification_test", ""))]
        if bad:
            return False, "；".join(bad), \
                "存在「结论翻转级」未定案项：必须当轮取证关闭，⛔ 不得无限期挂账"
        return True, f"{len(items)} 项已关闭或无翻转级风险", ""
    aud.guard("G7", "A7.2", "无悬空的结论翻转级不确定项", _no_unknown_stale)


# ============================================================
# G8 · 证据链完整性（#C1-55）
# ============================================================
def build_g8(aud: Audit, L: Ledger):
    """台账里的每个数字都必须能追到一份证据文件。
    这一组检查 evidence_index.py 的产出，把「数值有出处」变成可验证的事。"""
    idx = None
    for k, v in L.m.items():
        if k.startswith("evidence_index_") and isinstance(v, dict):
            idx = (k, v)
            break
    if not idx:
        aud.add("G8", "A8.0", "证据索引存在", "SKIP",
                "未找到 evidence_index_* 块",
                "跑 python evidence_index.py --month YYYY-MM --write-meta 生成")
        return
    key, v = idx

    def _cov():
        pct = float(v.get("coverage_pct", 0) or 0)
        gaps = v.get("gap_days") or []
        quiet = v.get("gap_but_claimed_by_data") or []
        if quiet:
            return False, f"数据声称有记录但证据找不到：{', '.join(quiet)}", \
                "这是最危险的一类 —— 数值有出处却不可追溯，必须当轮定位"
        if pct < 80:
            return False, f"覆盖 {pct}%，真空日 {len(gaps)} 天：{', '.join(gaps[:6])}", \
                "覆盖率过低说明复盘没留档；⚠️ 先确认真空日是否法定休市"
        return True, f"覆盖 {pct}%（真空 {len(gaps)} 天，均无数据声称）", ""
    aud.guard("G8", "A8.1", "台账数字可追到证据文件", _cov, "#C1-55")

    def _shell():
        """区分两种「文件名 ≠ 内容日期」：
        · 内容日期晚于文件名 ⇒ 时间倒流，不可能发生，必为笔误 ⇒ FAIL
        · 内容日期早于文件名 ⇒ 命名滞后（当天没更新数据就生成了文件）⇒ WARN
        后者不是垃圾：文件里的数字是真的，只是标签错了一天。删它反而丢信息。"""
        sh = v.get("shell_files") or []
        rev = int(v.get("time_reversed_count", 0) or 0)
        if rev > 0:
            det = [d for d in (v.get("shell_detail") or []) if d.get("time_reversed")]
            aud.add("G8", "A8.2", "证据文件命名与内容无时间倒流", "FAIL",
                    f"{rev} 份文件的内容日期晚于文件名：" +
                    "、".join(f"{d.get('name')}(内容{d.get('head_date')})" for d in det[:4]),
                    "内容不可能来自未来，必为人工改名笔误；须核对后修正", "#C1-55")
            return
        if sh:
            aud.add("G8", "A8.2", "证据文件命名与内容日期一致", "WARN",
                    f"{len(sh)} 份文件命名滞后一天或数天（内容日期早于文件名）：" +
                    "、".join(str(x).split("\\")[-1] for x in sh[:4]) + ("…" if len(sh) > 4 else ""),
                    "这些文件的数字是真的，只是标签错位；已被索引按内容日期正确归档，"
                    "不需要删除。根因（sync_all 用 today 命名而正文写 update_date）已于 2026-10-31 修复",
                    "#C1-55")
            return
        aud.add("G8", "A8.2", "证据文件命名与内容日期一致", "PASS", "无错位文件", "", "#C1-55")
    _shell()

    def _fresh():
        g = v.get("generated_at")
        if not g:
            return False, "索引无生成时间", "重跑 evidence_index --write-meta"
        try:
            from datetime import date as _d
            gap = (_d.today() - _d.fromisoformat(g)).days
        except ValueError:
            return False, f"生成时间格式非法：{g}", "统一 YYYY-MM-DD"
        if gap > 35:
            return False, f"索引生成于 {g}，已 {gap} 天未刷新", "每月至少重跑一次索引"
        return True, f"生成于 {g}（{gap} 天前）", ""
    aud.guard("G8", "A8.3", "证据索引未过期", _fresh, "#C1-55")


# ============================================================
# 输出
# ============================================================
GROUP_NAMES = {
    "G0": "结构自洽", "G1": "三口径", "G2": "回撤基准",
    "G3": "台账可复算", "G4": "日程连续性", "G5": "流水核销",
    "G6": "金额一致性", "G7": "时效与悬空项", "G8": "证据链完整性",
}
ICON = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ ", "SKIP": "—"}


def render(aud: Audit, quiet=False, hints=False):
    c = aud.counts()
    if not quiet:
        print("=" * 78)
        print("  账本不变量审计 · ledger_audit")
        print("=" * 78)
        cur = None
        for x in aud.checks:
            if x.gid != cur:
                cur = x.gid
                print(f"\n【{cur}】{GROUP_NAMES.get(cur, '')}")
            mark = ICON.get(x.status, "?")
            print(f"  {mark} {x.cid}  {x.title}")
            if x.status in ("FAIL", "WARN") or (not quiet and x.detail and x.status == "PASS" and x.cid in ("A1.3", "A2.2", "A2.4")):
                if x.detail:
                    print(f"        {x.detail}")
            if x.status == "FAIL" and x.fix and hints:
                print(f"        → 修复：{x.fix}")
    else:
        for x in aud.failed:
            print(f"❌ {x.cid} {x.title}")
            if x.detail:
                print(f"   {x.detail}")
            if x.fix:
                print(f"   → {x.fix}")

    print("\n" + "-" * 78)
    print(f"  通过 {c['PASS']} ｜ 失败 {c['FAIL']} ｜ 警告 {c['WARN']} ｜ 跳过 {c['SKIP']}"
          f"  （共 {len(aud.checks)} 项）")
    if c["FAIL"]:
        print("  🔴 账本不自洽 —— 在 FAIL 清零前，任何基于本数据的结论都不可引用")
    else:
        print("  🟢 账本自洽")
    print("-" * 78)


def run_audit(data):
    """可编程入口：给一段数据，返回 Audit 对象（供 safe_write 与 CI 复用）。"""
    L = Ledger(data)
    aud = Audit()
    for fn in (build, build_g1, build_g2, build_g3, build_g4, build_g5, build_g6, build_g7, build_g8):
        fn(aud, L)
    return aud


def main():
    argv = sys.argv[1:]
    as_json = "--json" in argv
    quiet = "--quiet" in argv
    hints = "--fix-hints" in argv or "--json" in argv
    only = None
    data_path = paths.DATA_PATH
    for i, a in enumerate(argv):
        if a == "--group" and i + 1 < len(argv):
            only = argv[i + 1].upper()
        if a == "--data" and i + 1 < len(argv):
            data_path = argv[i + 1]

    try:
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ 无法读取 {data_path}：{e}")
        sys.exit(2)

    aud = run_audit(data)

    if only:
        aud.checks = [c for c in aud.checks if c.gid == only]

    if as_json:
        print(json.dumps({
            "ok": not aud.failed,
            "counts": aud.counts(),
            "checks": [{"group": c.gid, "id": c.cid, "title": c.title, "status": c.status,
                        "detail": c.detail, "fix": c.fix, "rule": c.rule} for c in aud.checks],
        }, ensure_ascii=False, indent=2))
    else:
        render(aud, quiet=quiet, hints=hints)

    sys.exit(1 if aud.failed else 0)


if __name__ == "__main__":
    main()
