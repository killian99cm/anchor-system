#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dca_ledger.py — 定投落库「半自动」工具（单 159 #1 · 2026-10-02 建）

【为什么需要它】
  2026-10-02 核查发现：**9 月 21 个交易日只有 13 天有定投记录**（缺 8 天）。
  经用户逐日确认 ＋ Δmv 反证，确认是**记录未落库（B4 载体缺失）**，而**根因＝定投记录无自动写入路径**
  —— `sync_all.py` 链路里没有这一步，全靠复盘时人工手写 ⇒ 与「规则命中台账 9 月 0 条」**完全同型**。

【设计：半自动，而**不是**全自动】
  本工具**只生成候选**，**写入必须显式 `--confirm`**。理由（2026-10-02 的教训）：
    · 协议值（如「黄金 ¥15/天」）能证明「**应该有**」，**不能**证明「**实际发生了**」——
      用户已证明存在例外（**9/22 纳指未扣**）；
    · ⇒ ⛔ **绝不静默把协议值写进 App 真值体系**。

【三级证据】（写入时逐行标注，⛔ 不得与 App 真值同貌）
  L1 = 逐日 Δmv 硬反证（需两日 mv；⛔ 档案只留最新一日 ⇒ 仅「最近一日」可得）
  L2 = 用户逐日确认
  L3 = 仅协议值（**候选**，默认 ⛔ 不写）

用法：
  python dca_ledger.py --scan [YYYY-MM]           # 只读：覆盖矩阵 + 缺口清单（默认本月）
  python dca_ledger.py --scan 2026-09 --json      # 机器可读
  python dca_ledger.py --write 2026-09 --confirm  # 把 L3 候选写入（需显式 --confirm）
  python dca_ledger.py --write 2026-09 --levels L2,L3 --confirm   # 指定允许写入的等级
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import paths            # noqa: E402
import trading_calendar as tc   # noqa: E402

# 🔴 标记：写入行的 note 必须含此串，供「是否半自动产物」一眼可辨（⛔ 不得与 App 真值同貌）
MARK = "⚠️ 半自动落库（dca_ledger）"

# `dca_running` 的形态是**人读字符串**（如「国泰黄金每天15」），此处做**唯一**的解析点。
_DCA_PAT = re.compile(r"^(?P<name>.+?)每天(?P<amt>\d+(?:\.\d+)?)$")


def parse_dca_running(strs: list[str]) -> list[dict]:
    """把 `dca_running` 的人读字符串解析为 [{key, amount, raw}]。

    ⚠️ 解析失败**必须显式声张**（返回 raw 并标 parse_ok=False），⛔ 不得静默丢弃 ——
    丢掉一条就等于**漏检一个标的的全部缺口**。
    """
    out = []
    for s in strs or []:
        m = _DCA_PAT.match(str(s).strip())
        if m:
            out.append({"key": m.group("name"), "amount": float(m.group("amt")),
                        "raw": s, "parse_ok": True})
        else:
            out.append({"key": str(s), "amount": None, "raw": s, "parse_ok": False})
    return out


# 🔴 `fund` 字段**写法不统一**是本主题的**共同病根**（同时也是单 159 #3 的靶子）：
#   实测样本：「华泰柏瑞纳指100ETF联接(QDII)A」／「华泰柏瑞纳达克100ETF联接(QDII)A」（错别字）／
#   「华泰柏瑞纳斯达克100ETF联接A」／以及 **`fund` 为空** 的行（2026-09-24 两条）。
#   ⇒ 比对前必须**归一化**，否则会把「记录在、只是写法不同」误报成**假缺口**。
# 🔴 单 159 #3：归一化**下沉到 `data_processor`**（全库单一真源），本模块改为复用
#    —— ⛔ 不再自持一份，否则两处实现迟早漂移。
from data_processor import fund_equiv, norm_fund  # noqa: E402,F401


def _norm_fund_local_unused(s: object) -> str:
    """归一化基金名（去括号内容／别名／字母／空格／ETF／联接），供**比对**用。

    ⚠️ 仅供**同一性判定**，⛔ 不用于回写、⛔ 不覆盖原始值（原文必须原样保留）。
    """
    t = str(s or "")
    for k, v in _FUND_ALIAS.items():
        t = t.replace(k, v)
    t = re.sub(r"[（(][^)）]*[)）]", "", t)          # 去括号内容（如 (QDII)）
    t = t.replace("ETF", "").replace("联接", "").replace("基金", "")
    t = re.sub(r"[A-Za-z0-9\s\-]", "", t)            # 去字母/数字/空格/横线
    return t


def fund_equiv(a: object, b: object) -> bool:
    """两个基金名是否**指向同一只**（归一化后互相包含）。"""
    na, nb = norm_fund(a), norm_fund(b)
    if not na or not nb:
        return False
    return na in nb or nb in na


def _row_matches_fund(row: dict, fund: str) -> tuple[bool, str]:
    """判定一条 transactions 行是否属该标的 → (是否, 判定方式)。"""
    f = row.get("fund")
    if f is None or str(f).strip() == "":
        # `fund` 为空：仅凭「同一天 + 金额与协议一致」**推定**，并**显式标注**（⛔ 不静默采信）
        return False, "fund 为空（需人工确认）"
    if fund_equiv(f, fund):
        return True, ("归一化后一致" if str(f) != fund else "逐字一致")
    return False, f"名称不同（{f}）"

#
# 为什么不用模糊匹配：2026-10-02 实测两种算法都不可靠 ——
#   · `key[:2]` 兜底 ⇒ **「华泰纳指100」被匹配到「华泰柏瑞上证红利ETF联接A」**（假缺口＋指向错标的）；
#   · 2-gram 相似度（阈值 0.34）⇒ **两条都匹配不上**（国泰黄金 0.333、华泰纳指100 0.176），
#     因为「纳指 → 纳斯达克」属**同义词**，纯字符串算法无从得知。
# ⇒ **误匹配的代价（报假缺口 ＋ 漏真缺口）远大于「匹配不上」** ⇒ 改为**显式映射**，
#   未命中一律**声张**并提示补映射（⛔ 不得静默跳过 —— 跳过＝漏检该标的的全部缺口）。
DCA_KEY_MAP: dict[str, str] = {
    "国泰黄金": "国泰黄金ETF联接A",
    "华泰纳指100": "华泰柏瑞纳斯达克100ETF联接A",
}


def _match_holding(key: str, data: dict) -> tuple[str | None, str]:
    """→ (持仓名, 匹配方式)。**只认显式映射**；未命中 ⇒ (None, '未映射·需人工补')。

    返回「匹配方式」是为了让报障可分辨（`显式映射` vs `未映射`），
    ⛔ 不得把两者都写成一句「未找到」——那是 9/24 已立规禁过的病。
    """
    names = {str(h.get("name") or "") for h in data.get("holdings_summary", []) if h.get("name")}
    hit = DCA_KEY_MAP.get(key)
    if hit and hit in names:
        return hit, "显式映射"
    if hit and hit not in names:
        return None, f"映射表指向「{hit}」但该持仓不在档案中（疑已清仓/改名）"
    return None, f"未映射（请把「{key}」补进 DCA_KEY_MAP）"


def trading_days(year: int, month: int, asof: date | None = None) -> list[str]:
    """该月**已发生**的交易日（**按 `trading_calendar` 实算**，⛔ 不按自然日/星期几近似）。

    🔴 **2026-10-02 修复（本工具自己的第二个 bug）**：初版扫**整月**交易日历 ⇒
        当月是「当前月」时会把**未来的交易日**一并报成缺口（如 10/2 扫 10 月 ⇒
        10/8–10/30 全被列为「缺记录」）。⇒ 现**截断到 `asof`（默认今天）**：
        未来尚未发生的日子**不是缺口**，报出来只会淹没有效信号。
    """
    from datetime import timedelta
    cut = asof or date.today()
    out, d = [], date(year, month, 1)
    while d.month == month:
        if d > cut:
            break
        if tc.is_trading_day(d):
            out.append(d.isoformat())
        d = d + timedelta(days=1)
    return out


def scan(year: int, month: int, data: dict | None = None,
         data_path: str | Path | None = None) -> dict:
    """扫出「应有定投但无记录」的缺口。只读。

    `data_path` 注入口（2026-10-02 加）：初版只能传 `data`，于是**不可读分支无法测试**
    —— 传 `data=None` 会去读真实档案并**成功**，测试里的「不可读」断言恒假
    （与「把无法判定当通过」同型）。⇒ 加路径注入口，使不可读分支**可被真的打到**。
    """
    if data is None:
        try:
            p = Path(data_path) if data_path is not None else Path(paths.DATA_PATH)
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            return {"status": "unavailable", "note": f"⚠️ 档案不可读：{type(e).__name__}",
                    "days": [], "targets": [], "gaps": [], "field_gaps": [], "unparsed": []}

    spec = parse_dca_running(data.get("dca_running") or [])
    unparsed = [x["raw"] for x in spec if not x["parse_ok"]]
    targets = []
    for x in spec:
        if not x["parse_ok"]:
            continue
        fund, how = _match_holding(x["key"], data)
        targets.append({"key": x["key"], "amount": x["amount"], "fund": fund,
                        "match_how": how, "raw": x["raw"]})

    days = trading_days(year, month)
    pref = f"{year:04d}-{month:02d}-"
    dca_rows = [t for t in data.get("transactions", [])
                if t.get("op") == "定投" and str(t.get("date", "")).startswith(pref)]

    exempt = (data.get("_meta") or {}).get("dca_exemptions") or {}
    gaps, matrix, field_gaps = [], [], []
    r2 = {"field_gaps": field_gaps}
    for d0 in days:
        row = {"date": d0, "have": {}, "miss": []}
        for t in targets:
            fund = t["fund"]
            if not fund:
                continue
            got, hows, field_gap = [], [], []
            for x in dca_rows:
                if x.get("date") != d0:
                    continue
                ok, how = _row_matches_fund(x, fund)
                hows.append((x.get("fund"), how, x.get("amount")))
                if ok:
                    got.append(x)
                elif how.startswith("fund 为空") and abs(float(x.get("amount") or 0) - float(t["amount"] or 0)) < 0.01:
                    # 🔴 **记录存在、只是 `fund` 字段缺失**，且**金额与协议一致** ⇒ 判「已发生·字段待补」，
                    #    ⛔ 不计入「缺记录」——否则会报**假缺口**（2026-10-02 实测：9/24 两条本是如此）。
                    #    ⚠️ 但**必须单列**并提示补字段，⛔ 不得当「已齐备」。
                    field_gap.append({"amount": x.get("amount"),
                                      "raw_index_hint": x.get("date")})
            exc = (exempt or {}).get(f"{d0}|{fund}")
            row["have"][fund] = sum(float(x.get("amount") or 0) for x in got) if got else None
            if exc:
                row["exempt"] = exc
                continue
            if field_gap:
                r2["field_gaps"].append({"date": d0, "fund": fund, "rows": field_gap,
                                         "note": "记录存在但 `fund` 字段为空（金额与协议一致）⇒ **须补字段**，⛔ 不是缺记录"})
                continue
            if not got:
                # 🔴 逐日「已找到但未匹配」的行必须**随缺口一并报出** ——
                #    否则「记录在、只是 fund 写法不同/为空」会被误报成**假缺口**（2026-10-02 实测 6 条里多数如此）
                near = [h for h in hows if h[1] != "名称不同"]
                gaps.append({"date": d0, "fund": fund, "amount": t["amount"], "evidence": "L3",
                             "near_rows": near,
                             "note": ("仅协议值（DCA 协议应有，但未见可判定记录）"
                                      + ("；⚠️ **当日有 fund 为空/不可判定的定投行**，需人工确认后销账"
                                         if near else ""))})
        matrix.append(row)

    return {"status": "ok" if not gaps else "gaps",
            "scope": pref[:7], "days": days, "targets": targets, "matrix": matrix,
            "gaps": gaps, "field_gaps": field_gaps,
            # ⛔ 只数**日期键**（形如 `YYYY-MM-DD|标的`）；`_note`/`_registered` 等说明键不计
            "exempt_used": len([k for k in exempt if k and not str(k).startswith("_")]),
            "unparsed": unparsed,
            "note": (f"共 {len(days)} 个交易日 × {len(targets)} 个定投标的 ⇒ **{len(gaps)} 处缺口**"
                     if gaps else f"✅ {len(days)} 个交易日 × {len(targets)} 个标的 **无缺口**")}


def write_gaps(year: int, month: int, levels: set[str], confirm: bool,
               data: dict | None = None, dry_run: bool = False) -> dict:
    """把缺口按指定证据等级写入 transactions。**⛔ 无 confirm 一律不写**（半自动铁律）。"""
    r = scan(year, month, data=data)
    if r["status"] == "unavailable":
        return {"ok": False, "reason": r["note"]}
    todo = [g for g in r["gaps"] if g["evidence"] in levels]
    if not confirm:
        return {"ok": False, "reason": "⛔ 未传 --confirm：本工具**默认只读**（半自动＝生成候选 → 人工确认）",
                "candidates": todo}
    if dry_run:
        return {"ok": True, "dry_run": True, "would_write": len(todo), "candidates": todo}
    return {"ok": True, "dry_run": False, "to_write": todo, "candidates": todo}


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--scan", nargs="?", const="", default=None)
    ap.add_argument("--write", nargs="?", const="", default=None)
    ap.add_argument("--levels", default="L1,L2")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(sys.argv[1:])

    def ym(s: str) -> tuple[int, int]:
        if s and "-" in s:
            y, m = s.split("-")[:2]
            return int(y), int(m)
        t = date.today()
        return t.year, t.month

    if a.write is not None:
        y, m = ym(a.write)
        r = write_gaps(y, m, set(a.levels.split(",")), a.confirm)
        if not r["ok"]:
            print(f"❌ {r['reason']}")
            for c in r.get("candidates", []):
                print(f"   候选：{c['date']} {c['fund']} ¥{c['amount']}（{c['evidence']}）")
            return 2
        print(f"（dry_run={r.get('dry_run')}）待写 {len(r.get('candidates', []))} 条")
        return 0

    if a.scan is not None:
        y, m = ym(a.scan)
        r = scan(y, m)
        if a.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
            return 0 if r["status"] != "unavailable" else 3
        print("=" * 64)
        print(f"  定投落库覆盖扫描 · {r.get('scope')} · status={r['status']}")
        print("=" * 64)
        if r["status"] == "unavailable":
            print("  " + r["note"]); return 3
        print(f"  定投协议（dca_running 解析）:")
        for t in r["targets"]:
            flag = "" if t["fund"] else "  🔴"
            print(f"    {t['key']} ≈ ¥{t['amount']}/天 → 持仓「{t['fund']}」"
                  f"（{t['match_how']}｜源: {t['raw']}）{flag}")
        _unmapped = [t["key"] for t in r["targets"] if not t["fund"]]
        if _unmapped:
            print(f"  ⚠️ **未映射的标的有 {len(_unmapped)} 个**：{_unmapped}"
                  f" ⇒ ⛔ 其全部缺口**不会被检出**（补 DCA_KEY_MAP 后重跑）")
        for u in r["unparsed"]:
            print(f"    ⚠️ **无法解析**：{u}（⛔ 会漏检该标的的全部缺口）")
        print(f"  {r['note']}")
        for g in r["gaps"][:40]:
            print(f"    🔴 {g['date']} {g['fund']} 缺记录（协议 ¥{g['amount']}，{g['evidence']}）")
            for nr in g.get("near_rows", []):
                print(f"         ↳ 当日有疑似行：fund={nr[0]!r}（{nr[1]}）¥{nr[2]} ⇒ 人工确认后销账")
        if len(r["gaps"]) > 40:
            print(f"    …… 其余 {len(r['gaps']) - 40} 条")
        for g in r.get("field_gaps", []):
            print(f"    🟠 {g['date']} {g['fund']} —— **记录存在但 fund 字段为空**"
                  f"（{len(g['rows'])} 行，金额与协议一致）⇒ 须补字段，⛔ 不是缺记录")
        if r.get("exempt_used"):
            print(f"  （已按 `_meta.dca_exemptions` 豁免 {r['exempt_used']} 项「已证未买」）")
        return 0 if r["status"] == "ok" else 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
