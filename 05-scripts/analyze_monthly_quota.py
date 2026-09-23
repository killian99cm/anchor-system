# -*- coding: utf-8 -*-
"""月操作额度 · 实证分析（一次性研究脚本，不改任何规则/数据）

回答用户问句：「每月的交易额度需不需要增加？Anchor 会不会因此错过上涨行情？或者改成动态的？」

口径：**复用** data_processor.monthly_ops_summary（单一真源，手册 §1.3 v3.11 二维口径），
⛔ 不自造 op 白名单。

产出四组事实：
  A. 逐月 buys/sells vs 上限（哪些月份真的顶格／超限）
  B. 「额度耗尽日」分布 —— 第 2 笔买入发生在当月第几个交易日 ⇒ 额度到底 bind 多少天
  C. 买入维明细（每笔日期/标的/金额/op）—— 看清额度被什么吃掉
  D. 决策日志里引用「月额度」的决策条数与其 outcome
"""
import io
import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths
from data_processor import monthly_ops_summary, classify_txn_op, txn_exclusion_reason

DATA = json.load(open(paths.DATA_PATH, encoding="utf-8"))
TX = DATA.get("transactions", [])


def ym(t):
    d = str(t.get("date", ""))
    if len(d) >= 7 and d[4] == "-":
        return d[:7]
    return None


def main():
    months = sorted({ym(t) for t in TX if ym(t)})
    print("=" * 78)
    print("A. 逐月二维额度实算（口径＝data_processor.monthly_ops_summary 单一真源）")
    print("=" * 78)
    print(f"{'月份':<9}{'买入':>5}{'/2':>4}{'卖出':>5}{'/2':>4}  {'状态':<22}{'未知op':<14}{'疑似双记'}")
    rows = []
    for m in months:
        y, mo = int(m[:4]), int(m[5:7])
        s = monthly_ops_summary(DATA, y, mo)
        if s.buys == 0 and s.sells == 0:
            continue
        if s.buys > s.max_buys and s.sells > s.max_sells:
            st = "🔴 两维均超"
        elif s.buys > s.max_buys:
            st = "🔴 买入维超"
        elif s.sells > s.max_sells:
            st = "🟠 卖出维超"
        elif s.buys == s.max_buys and s.sells == s.max_sells:
            st = "🟡 两维顶格"
        elif s.buys == s.max_buys or s.sells == s.max_sells:
            st = "🟡 一维顶格"
        else:
            st = "🟢 未顶格"
        uk = ",".join(s.unknown_ops) if s.unknown_ops else "-"
        rows.append((m, s, st))
        print(f"{m:<9}{s.buys:>5}{('/'+str(s.max_buys)):>4}{s.sells:>5}{('/'+str(s.max_sells)):>4}"
              f"  {st:<22}{uk:<14}{len(s.suspect_dupes)}")

    print()
    print("=" * 78)
    print("B. 「额度耗尽日」—— 第 2 笔买入（＝买入维顶格）发生在当月第几天")
    print("   ⇒ 该日之后的全部交易日，买入维一律拦（X 级除外，#C1-15 只给了卖出侧出口）")
    print("=" * 78)
    print(f"{'月份':<9}{'第1笔':<12}{'第2笔':<12}{'第3笔+':<28}{'耗尽后剩余自然日'}")
    import calendar
    for m, s, st in rows:
        y, mo = int(m[:4]), int(m[5:7])
        buys = sorted(
            [t for t in TX if ym(t) == m
             and txn_exclusion_reason(t) is None
             and classify_txn_op(t.get("op")) == "buy"],
            key=lambda t: str(t.get("date")))
        if not buys:
            continue
        d = [str(t.get("date"))[:10] for t in buys]
        ndays = calendar.monthrange(y, mo)[1]
        rest = ""
        if len(d) >= 2:
            rest = f"{ndays - int(d[1][8:10])} 天（至月末）"
        print(f"{m:<9}{d[0]:<12}{(d[1] if len(d)>1 else '—'):<12}"
              f"{(','.join(d[2:]) or '—'):<28}{rest}")

    print()
    print("=" * 78)
    print("C. 买入维逐笔明细（近 6 个月）—— 额度被什么吃掉")
    print("=" * 78)
    for m, s, st in rows[-6:]:
        buys = sorted([t for t in TX if ym(t) == m
                       and txn_exclusion_reason(t) is None
                       and classify_txn_op(t.get("op")) == "buy"],
                      key=lambda t: str(t.get("date")))
        if not buys:
            continue
        print(f"\n--- {m}（买入 {s.buys}/{s.max_buys}）---")
        for t in buys:
            print(f"  {str(t.get('date'))[:10]}  {str(t.get('op')):<6}"
                  f"¥{float(t.get('amount') or 0):>8,.0f}  "
                  f"{str(t.get('fund') or t.get('name') or '')[:26]:<28}"
                  f"{str(t.get('note') or '')[:52]}")

    print()
    print("=" * 78)
    print("D. 决策日志中引用「月额度」的决策 —— 它作为拦截依据的实际出场记录")
    print("=" * 78)
    dj = json.load(open(paths.DECISION_LOG_PATH, encoding="utf-8"))
    ds = dj["decisions"] if isinstance(dj, dict) else dj
    hit = [d for d in ds
           if "月额度" in str(d.get("rationale", "")) or "月额度" in " ".join(map(str, d.get("tags") or []))
           or "额度" in str(d.get("rationale", ""))]
    print(f"决策总数 {len(ds)}；引用额度 {len(hit)} 条")
    oc = defaultdict(int)
    for d in hit:
        oc[str(d.get("outcome"))] += 1
        print(f"  #{d.get('id'):>3} {str(d.get('date'))[:10]} {str(d.get('type')):<5}"
              f"{str(d.get('verdict'))[:16]:<18}outcome={str(d.get('outcome')):<8}"
              f"pnl={d.get('pnl_pct')}")
    print("  outcome 分布:", dict(oc))

    print()
    print("=" * 78)
    print("E. 全期买卖两维合计（回答「哪一维才是真瓶颈」）")
    print("=" * 78)
    tb = sum(s.buys for _, s, _ in rows)
    ts = sum(s.sells for _, s, _ in rows)
    n = len(rows)
    print(f"有操作月份数 {n}；买入事件合计 {tb}（月均 {tb/n:.2f}）；卖出事件合计 {ts}（月均 {ts/n:.2f}）")
    over_b = sum(1 for _, s, _ in rows if s.buys > s.max_buys)
    over_s = sum(1 for _, s, _ in rows if s.sells > s.max_sells)
    print(f"买入维超限月份 {over_b}/{n}；卖出维超限月份 {over_s}/{n}")


if __name__ == "__main__":
    main()
