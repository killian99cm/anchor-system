# -*- coding: utf-8 -*-
"""月操作额度 · 反事实回测（一次性研究脚本，不改任何规则/数据）

回答：「若把额度当**真闸门**执行（现在 147 校验器与日报已经在这么写了），
      从『买入维耗尽日』到月末这段被锁死的窗口里，Anchor 到底错过了什么？」

口径与自限：
  · 耗尽日 ＝ 当月第 2 笔**买入事件**日（复用 data_processor 单一真源分类）
  · 前向收益 ＝ 腾讯前复权日K 收盘价，**耗尽日收盘 → 月末最后交易日收盘**
  · 标的宇宙 ＝ 卫星层可及的 4 个宽基/行业 ETF（创新药/半导体/证券/科创50）
    ⛔ 不含表外 watchlist 四主题（无对应可得的连续日K，见报告缺口声明）
  · 🔴 **这不是「建议买」的回测**：它只测「被锁窗口里标的涨了多少」，
    **不含 A2/E1/E4/评分卡/节前闸门** —— 即它是**额度的孤立效应上界**
    （真实可捕获量必然更小，因为其余闸门仍会拦）⇒ 结论若为「不值得」则**更稳**
  · 样本量 n 逐表披露（附录E · F8 ④：无 n 的断言最高只能评 C 级）
"""
import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths
import fetch_public as fp
from data_processor import classify_txn_op, txn_exclusion_reason

DATA = json.load(open(paths.DATA_PATH, encoding="utf-8"))
TX = DATA.get("transactions", [])

UNIVERSE = {
    "sh513120": "创新药ETF",
    "sh512480": "半导体ETF",
    "sh512880": "证券ETF",
    "sh000688": "科创50",
}
BUY_TICKET = 300.0   # 手册 watchlist 单笔下限 ¥300


def ym(t):
    d = str(t.get("date", ""))
    return d[:7] if len(d) >= 7 and d[4] == "-" else None


def exhaustion_days():
    """每月「买入维耗尽日」＝**第 2 笔买入记录**所在日期。返回 {ym: date_str}。

    🔴 口径订正（本脚本首版曾错）：**必须按记录序取第 2 条，⛔ 不得先对日期去重**。
       首版用 `sorted(set(dates))[1]` ⇒ 同日多笔被折叠，2026-01 算成 01-26（真值 01-08）、
       2026-09 算成 09-07（真值 09-01）。**错的方向是缩短被锁窗口 ⇒ 低估额度的影响**，
       即对「额度该放宽」这一主张**偏有利**，故必须订正后重跑（否则结论不可用）。
    """
    by = defaultdict(list)
    for t in TX:
        m = ym(t)
        if not m or txn_exclusion_reason(t) is not None:
            continue
        if classify_txn_op(t.get("op")) == "buy":
            by[m].append(str(t.get("date"))[:10])
    out = {}
    for m, ds in by.items():
        ds = sorted(ds)          # ⛔ 不 set()：同日多笔各自是一笔
        if len(ds) >= 2:
            out[m] = ds[1]
    return out


def main():
    ex = exhaustion_days()
    print("=" * 92)
    print("反事实回测 · 「买入维耗尽日 → 月末」被锁窗口的前向收益")
    print("=" * 92)
    print(f"标的宇宙: {UNIVERSE}   单笔假设 ¥{BUY_TICKET:.0f}")
    print(f"耗尽日取自 data_processor 单一真源分类；共 {len(ex)} 个月存在耗尽日")
    print()

    kl = {}
    for c in UNIVERSE:
        rows = fp.daily_kline(c, 300) or []
        kl[c] = {r["date"]: r["close"] for r in rows if r.get("date")}
        print(f"  {c:<10}{UNIVERSE[c]:<12} bars={len(rows):>4}  "
              f"{(rows[0]['date'] if rows else '-')} → {(rows[-1]['date'] if rows else '-')}")
    print()

    hdr = f"{'月份':<9}{'耗尽日':<12}{'月末':<12}"
    for c in UNIVERSE:
        hdr += f"{UNIVERSE[c]:>12}"
    hdr += f"{'均值%':>9}{'4标的合计盈亏¥':>16}"
    print(hdr)
    print("-" * len(hdr))

    all_ret = []
    tot_pnl = 0.0
    months_used = 0
    for m in sorted(ex):
        d0 = ex[m]
        series = {}
        month_end = None
        for c in UNIVERSE:
            days = sorted(kl[c].keys())
            after = [d for d in days if d >= d0 and d[:7] == m]
            if len(after) < 2:
                series[c] = None
                continue
            a, b = kl[c][after[0]], kl[c][after[-1]]
            series[c] = (b / a - 1) * 100 if a else None
            month_end = after[-1] if month_end is None or after[-1] > month_end else month_end
        vals = [v for v in series.values() if v is not None]
        if not vals or not month_end:
            print(f"{m:<9}{d0:<12}{'—':<12}" + "".join(f"{'—':>12}" for _ in UNIVERSE)
                  + f"{'—':>9}{'—':>16}  ⚠️ 日K 未覆盖该月（样本外，不计入 n）")
            continue
        months_used += 1
        line = f"{m:<9}{d0:<12}{month_end:<12}"
        for c in UNIVERSE:
            v = series[c]
            line += f"{v:>11.2f}%" if v is not None else f"{'—':>12}"
        mean = sum(vals) / len(vals)
        pnl = sum((v / 100) * BUY_TICKET for v in vals)
        all_ret.extend(vals)
        tot_pnl += pnl
        line += f"{mean:>8.2f}%{pnl:>15,.2f}"
        print(line)

    print("-" * len(hdr))
    n = len(all_ret)
    if n:
        pos = sum(1 for v in all_ret if v > 0)
        neg = sum(1 for v in all_ret if v < 0)
        srt = sorted(all_ret)
        print(f"合计 {months_used} 个月 × 最多 {len(UNIVERSE)} 标的 = **n={n}** 个「月内被锁窗口收益」样本")
        print(f"  正收益 {pos}（{pos/n*100:.1f}%）｜负收益 {neg}（{neg/n*100:.1f}%）")
        print(f"  均值 {sum(all_ret)/n:+.2f}%｜中位 {srt[n//2]:+.2f}%｜"
              f"最好 {srt[-1]:+.2f}%｜最差 {srt[0]:+.2f}%")
        print(f"  若每标的每月按 ¥{BUY_TICKET:.0f} 买入 ⇒ 12 个月累计盈亏 **¥{tot_pnl:+,.2f}**"
              f"（占当前总资产 {tot_pnl/DATA.get('total_assets',1)*100:+.2f}%）")
        # 证伪条件自检
        print()
        print("🔴 证伪条件（F8 ②）：若『均值 > 0 且 正收益占比 > 60% 且 n ≥ 20』成立，")
        print("   才可主张「额度确实系统性错过上涨行情」；否则该主张不成立。")
        verdict = (sum(all_ret)/n > 0) and (pos/n > 0.60) and (n >= 20)
        print(f"   实算：均值 {sum(all_ret)/n:+.2f}% ｜正占比 {pos/n*100:.1f}% ｜n={n} ⇒ "
              f"{'✅ 主张成立' if verdict else '⛔ 主张不成立'}")


if __name__ == "__main__":
    main()
