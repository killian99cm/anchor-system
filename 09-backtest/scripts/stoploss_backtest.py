#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stoploss_backtest.py — 止损端完整回测（回测明算 · v1.0）
对比三种止损策略（配合现档止盈 +8/+15/+25% 卖25% + 奔跑仓 60日线/回撤15%）：
  A 不止损：仅止盈档位
  B 即时止损：浮亏 ≤-8% 收盘触发 → 次日开盘清仓
  C 硬Deadline：浮亏 ≤-8% 触发 → 缓冲 3 交易日后第 4 个交易日开盘无条件清仓
输出：每标的 × 3 止损变体的总收益/MDD/盈亏比（均盈/均亏）
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
TIERS = [(0.08, 0.25), (0.15, 0.25), (0.25, 0.25)]
MA_WINDOW = 60
DD_THRESH = 0.15
SL = -0.08
DEADLINE_DAYS = 4  # 触发后第 4 个交易日无条件


def run(df, sl_mode):
    d = df[(df["date"] >= tp.EVAL_START) & (df["date"] <= tp.EVAL_END)].reset_index(drop=True)
    d["ma"] = d["close"].rolling(MA_WINDOW).mean()
    cash, shares, init_sh, avg, entry = tp.INITIAL_CASH, 0, 0, 0.0, None
    tier_idx, runner, peak = 0, False, 0.0
    bp, sp = False, []
    eq, trades, buy_day = [], [], 0
    sl_triggered, sl_countdown, sl_low_after = False, 0, 0.0
    sl_entry_px = 0.0

    for i, row in d.iterrows():
        o, c = row["open"], row["close"]
        date = row["date"].strftime("%Y-%m-%d")
        # 1) 执行挂单
        if bp:
            px = o
            shares = math.floor(cash / px / LOT) * LOT
            if shares >= LOT:
                cash -= shares * px * (1 + COMMISSION)
                init_sh, avg, entry, buy_day = shares, px, date, i
            else:
                shares = 0
            bp = False
        for frac2, lbl in sp:
            s = min(math.floor(init_sh * frac2 / LOT) * LOT, shares)
            if s > 0:
                cash += s * o * (1 - COMMISSION)
                shares -= s
                trades.append({"exit_date": date, "label": lbl, "pnl_pct": (o / avg - 1) * 100,
                               "pnl": (o - avg) * s - s * o * COMMISSION})
                if tier_idx >= len(TIERS) and shares <= init_sh * 0.25 + LOT:
                    runner, peak = True, c
        sp = []
        # 2) 止损状态机
        if shares >= LOT and sl_mode != "none" and not sl_triggered:
            if c / avg - 1 <= SL:
                sl_triggered = True
                sl_countdown = 0
                sl_entry_px = avg
        if sl_triggered and shares >= LOT:
            if sl_mode == "immediate":
                sp.append((1.0, "止损-8%次日清仓"))
                sl_triggered = False
            else:  # deadline
                sl_countdown += 1
                if sl_countdown >= DEADLINE_DAYS:
                    sp.append((1.0, "硬Deadline第4天清仓"))
                    sl_triggered = False
        # 3) 信号生成
        if i == 0 and shares == 0 and not bp:
            bp = True
        if shares >= LOT:
            gain = c / avg - 1
            while tier_idx < len(TIERS):
                if gain >= TIERS[tier_idx][0]:
                    sp.append((TIERS[tier_idx][1], "止盈" + str(int(TIERS[tier_idx][0] * 100)) + "%"))
                    tier_idx += 1
                else:
                    break
            if runner:
                peak = max(peak, c)
                ma = row["ma"]
                dd = c / peak - 1 if peak else 0
                if (pd.notna(ma) and c < ma) or dd <= -DD_THRESH:
                    sp.append((1.0, "奔跑仓出清"))
        eq.append(cash + shares * c)
    # 期末
    if shares >= LOT:
        last = d.iloc[-1]
        cash += shares * last["close"] * (1 - COMMISSION)
        shares = 0
        trades.append({"exit_date": "end", "label": "期末平仓", "pnl_pct": (last["close"] / avg - 1) * 100, "pnl": 0})
    s = pd.Series(eq)
    wins = [t for t in trades if t["pnl"] > 0]
    avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
    losses = [t for t in trades if t["pnl"] < 0]
    avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
    plr = abs(avg_win / avg_loss) if avg_loss else float("inf")
    return {"total": round((s.iloc[-1] / tp.INITIAL_CASH - 1) * 100, 2),
            "mdd": round((s / s.cummax() - 1).min() * 100, 2),
            "trades": len(trades), "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
            "plr": round(plr, 2) if plr != float("inf") else None}


def main():
    modes = [("none", "不止损"), ("immediate", "即时止损-8%"), ("deadline", "硬Deadline(第4天)")]
    bh = {b["symbol"]: b for b in json.load(open(os.path.join(OUT, "buyhold_summary.json"), encoding="utf-8"))}
    print(f"{'标的':<16}" + "".join(f"{m[1]:>24}" for m in modes))
    print(f"{'':16}" + "".join(f"{'总收益/MDD/盈亏比':>24}" for m in modes))
    for sym, name in tp.SYMBOLS.items():
        df = tp.load_kline(sym)
        line = f"{name:<16}"
        for _, mname in modes:
            r = run(df, _)
            line += f"{r['total']:>7.1f}/{r['mdd']:>6.1f}/{str(r['plr']):>5}".rjust(24)
        print(line)
        bhv = bh[sym]
        print(f"  └ 满仓基准: 收益 {bhv['total_return_pct']}%  MDD {bhv['max_drawdown_pct']}%")


if __name__ == "__main__":
    main()
