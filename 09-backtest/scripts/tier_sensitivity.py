#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tier_sensitivity.py — 止盈档位宽度 × 卖出比例网格扫描（回测明算 · v1.0）
档位组合：密(+5/+10/+15) 现(+8/+15/+25) 疏(+10/+20/+35) 极疏(+15/+30/+50)
卖出比例：15% / 25% / 35%（每档卖原始建仓份额的固定比例，剩余为奔跑仓）
奔跑仓出场：60 日线 或 自高回撤 ≥15%（宽松版，依据 runner_sensitivity 结论）
输出：每标的 × 12 组合的总收益/MDD，与满仓基准（buyhold_summary.json）对比
"""
import json
import math
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import takeprofit_compare_backtest as tp

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
COMMISSION = 0.0003
LOT = 100

TIER_SETS = {
    "密档": [0.05, 0.10, 0.15],
    "现档": [0.08, 0.15, 0.25],
    "疏档": [0.10, 0.20, 0.35],
    "极疏": [0.15, 0.30, 0.50],
}
FRACTIONS = [0.15, 0.25, 0.35]
MA_WINDOW = 60
DD_THRESH = 0.15


def run(df, tiers, frac):
    d = df[(df["date"] >= tp.EVAL_START) & (df["date"] <= tp.EVAL_END)].reset_index(drop=True)
    d["ma"] = d["close"].rolling(MA_WINDOW).mean()
    cash, shares, init_sh, avg, entry = tp.INITIAL_CASH, 0, 0, 0.0, None
    tier_idx, runner, peak = 0, False, 0.0
    bp, sp = False, []
    eq, buy_day = [], 0
    for i, row in d.iterrows():
        o, c = row["open"], row["close"]
        if bp:
            px = o
            shares = math.floor(cash / px / LOT) * LOT
            if shares >= LOT:
                cash -= shares * px * (1 + COMMISSION)
                init_sh, avg, entry, buy_day = shares, px, row["date"].strftime("%Y-%m-%d"), i
            else:
                shares = 0
            bp = False
        for frac2, _ in sp:
            s = min(math.floor(init_sh * frac2 / LOT) * LOT, shares)
            if s > 0:
                cash += s * o * (1 - COMMISSION)
                shares -= s
                if tier_idx >= len(tiers) and shares <= init_sh * (1 - frac * len(tiers)) + LOT:
                    runner, peak = True, c
        sp = []
        if i == 0 and shares == 0 and not bp:
            bp = True
        if shares >= LOT:
            gain = c / avg - 1
            while tier_idx < len(tiers):
                if gain >= tiers[tier_idx]:
                    sp.append((frac, "t"))
                    tier_idx += 1
                else:
                    break
            if runner:
                peak = max(peak, c)
                ma = row["ma"]
                dd = c / peak - 1 if peak else 0
                if (pd.notna(ma) and c < ma) or dd <= -DD_THRESH:
                    sp.append((1.0, "r"))
        eq.append(cash + shares * c)
    if shares >= LOT:
        last = d.iloc[-1]
        cash += shares * last["close"] * (1 - COMMISSION)
        shares = 0
    s = pd.Series(eq)
    return {"total": round((s.iloc[-1] / tp.INITIAL_CASH - 1) * 100, 2),
            "mdd": round((s / s.cummax() - 1).min() * 100, 2)}


def main():
    bh = {b["symbol"]: b for b in json.load(open(os.path.join(OUT, "buyhold_summary.json"), encoding="utf-8"))}
    results = {}
    for sym, name in tp.SYMBOLS.items():
        df = tp.load_kline(sym)
        results[name] = {}
        for tname, tiers in TIER_SETS.items():
            for frac in FRACTIONS:
                key = f"{tname}/{int(frac*100)}%"
                results[name][key] = run(df, tiers, frac)

    # 输出：每标的 × 12 组合（总收益/MDD）
    print(f"{'标的':<16}" + "".join(f"{t}/{int(f*100)}%".rjust(14) for t in TIER_SETS for f in FRACTIONS))
    for name, row in results.items():
        line = f"{name:<16}"
        for t in TIER_SETS:
            for f in FRACTIONS:
                k = f"{t}/{int(f*100)}%"
                line += f"{row[k]['total']:>8.1f}/{row[k]['mdd']:>5.1f}".rjust(14)
        print(line)
        bhv = bh[list(tp.SYMBOLS.keys())[list(tp.SYMBOLS.values()).index(name)]]
        print(f"{'  └ 满仓基准':<18} 总收益 {bhv['total_return_pct']:>7.1f}%  MDD {bhv['max_drawdown_pct']:>7.1f}%")

    # 最优组合汇总（按 总收益/MDD 均衡：收益最高且 MDD ≤ 满仓MDD+5pct）
    print()
    print("=== 各标的最优组合（收益最高且回撤不显著恶化满仓）===")
    for name, row in results.items():
        bhv = bh[list(tp.SYMBOLS.keys())[list(tp.SYMBOLS.values()).index(name)]]
        mdd_lim = bhv["max_drawdown_pct"] + 5
        cands = [(k, v) for k, v in row.items() if v["mdd"] >= mdd_lim]
        if cands:
            best = max(cands, key=lambda x: x[1]["total"])
            print(f"  {name:<16} 最佳 {best[0]:<10} 收益 {best[1]['total']:>7.1f}%  MDD {best[1]['mdd']:>6.1f}%  (满仓 {bhv['total_return_pct']}%/{bhv['max_drawdown_pct']}%)")
        else:
            print(f"  {name:<16} 无满足组合（全部回撤恶化 >5pct）——止盈结构在趋势市无法兼顾收益与回撤")


if __name__ == "__main__":
    main()
