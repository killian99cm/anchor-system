#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner_sensitivity.py — 奔跑仓出场参数敏感性扫描（回测明算 · v1.0）
对「新档 v3.4 + 奔跑仓」的出场参数做 3×3 网格：
  均线窗口：20 / 40 / 60 日（收盘破线出清）
  自高回撤：8% / 12% / 15%
输出：每标的 × 每组合的总收益 / 最大回撤矩阵，用于评估「改奔跑仓出场线」建议是否成立。
"""
import json
import math
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

OUT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(OUT, "..", "data")
COMMISSION = 0.0003
SYMBOLS = {
    "sz159995": "芯片ETF华夏(半导体)",
    "sh512880": "证券ETF",
    "sh515180": "红利ETF易方达",
    "sh518880": "黄金ETF",
    "sh513100": "纳指ETF",
}
EVAL_START = "2021-09-01"
EVAL_END = "2026-08-26"
INITIAL_CASH = 100000.0
LOT = 100
TIERS_B = [(0.08, 0.25), (0.15, 0.25), (0.25, 0.25)]


def load_kline(symbol):
    rows = []
    with open(os.path.join(DATA, f"_kline_{symbol}.md"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or "date" in line or line.startswith("| ---"):
                continue
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) < 6:
                continue
            try:
                rows.append({"date": parts[0], "open": float(parts[1]),
                             "close": float(parts[2]), "high": float(parts[3]),
                             "low": float(parts[4])})
            except (ValueError, IndexError):
                continue
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def run(df, ma_window, dd_thresh):
    df = df[(df["date"] >= EVAL_START) & (df["date"] <= EVAL_END)].reset_index(drop=True)
    df["ma"] = df["close"].rolling(ma_window).mean()
    cash, shares, init_shares, avg_cost, entry_date = INITIAL_CASH, 0, 0, 0.0, None
    tier_idx, runner_active, runner_peak = 0, False, 0.0
    buy_pending, sell_pending = False, []
    equity, buy_day = [], 0

    for i, row in df.iterrows():
        date = row["date"].strftime("%Y-%m-%d")
        o, c = row["open"], row["close"]
        if buy_pending:
            px = o
            shares = math.floor(cash / px / LOT) * LOT
            if shares >= LOT:
                cash -= shares * px * (1 + COMMISSION)
                init_shares, avg_cost, entry_date, buy_day = shares, px, date, i
            else:
                shares = 0
            buy_pending = False
        for frac, tp in sell_pending:
            sell_sh = min(math.floor(init_shares * frac / LOT) * LOT, shares)
            if sell_sh > 0:
                proceeds = sell_sh * o
                cash += proceeds * (1 - COMMISSION)
                shares -= sell_sh
                if tier_idx >= len(TIERS_B) and shares <= init_shares * 0.25 + LOT:
                    runner_active, runner_peak = True, c
        sell_pending = []
        if i == 0 and shares == 0 and not buy_pending:
            buy_pending = True
        if shares >= LOT:
            gain = c / avg_cost - 1
            while tier_idx < len(TIERS_B):
                if gain >= TIERS_B[tier_idx][0]:
                    sell_pending.append((TIERS_B[tier_idx][1], "tier"))  # (fraction, label) 防错位
                    tier_idx += 1
                else:
                    break
            if runner_active:
                runner_peak = max(runner_peak, c)
                ma = row["ma"]
                dd = c / runner_peak - 1 if runner_peak else 0.0
                if (not pd.isna(ma) and c < ma) or dd <= -dd_thresh:
                    sell_pending.append((1.0, "runner_exit"))
        equity.append(cash + shares * c)

    # 期末强平
    if shares >= LOT:
        last = df.iloc[-1]
        cash += shares * last["close"] * (1 - COMMISSION)
        shares = 0
    eq = pd.Series(equity)
    total = (eq.iloc[-1] / INITIAL_CASH - 1) * 100
    mdd = (eq / eq.cummax() - 1).min() * 100
    ann = ((eq.iloc[-1] / INITIAL_CASH) ** (252 / max(len(eq), 1)) - 1) * 100
    ret = eq.pct_change()
    sharpe = ret.mean() / ret.std() * math.sqrt(252) if ret.std() and not pd.isna(ret.std()) else 0
    return {"total": round(total, 2), "mdd": round(mdd, 2), "ann": round(ann, 2), "sharpe": round(sharpe, 2)}


def main():
    grids = [(w, d) for w in (20, 40, 60) for d in (0.08, 0.12, 0.15)]
    results = {}
    for sym, name in SYMBOLS.items():
        df = load_kline(sym)
        row = {}
        for w, d in grids:
            r = run(df, w, d)
            row[f"MA{w}/DD{int(d*100)}"] = r
        results[name] = row

    print(f"{'标的':<14} " + " ".join(f"{k:>14}" for k, _ in grids))
    print("总收益% (MDD%)")
    for name, row in results.items():
        cells = []
        for w, d in grids:
            k = f"MA{w}/DD{int(d*100)}"
            cells.append(f"{row[k]['total']:>7.1f}({row[k]['mdd']:>5.1f})")
        print(f"{name:<14} " + " ".join(f"{c:>14}" for c in cells))

    # 纳指突出展示
    print()
    print("=== 纳指ETF 重点：原版(MA20/DD8) 对比各组合 ===")
    base = results["纳指ETF"]["MA20/DD8"]
    print(f"原版新档 v3.4: 总收益 {base['total']}% (旧档 48.5%)")
    for w, d in grids:
        k = f"MA{w}/DD{int(d*100)}"
        r = results["纳指ETF"][k]
        print(f"  {k:<12} 总收益 {r['total']:>7.2f}%  MDD {r['mdd']:>6.2f}%  Sharpe {r['sharpe']:.2f}")


if __name__ == "__main__":
    main()
