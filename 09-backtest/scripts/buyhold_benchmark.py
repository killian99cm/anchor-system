#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
buyhold_benchmark.py — buy & hold 基准（回测明算 · v1.1 修正版）
修正 v1.0 错误：净值 = 初始现金 - 买入成本 + 份额×收盘（v1.0 漏扣成本导致收益虚高、回撤被稀释）
输出：09-backtest/output/buyhold_summary.json（满仓总收益/年化/MDD/Sharpe，与主脚本同口径）
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


def main():
    results = []
    for sym, name in tp.SYMBOLS.items():
        d = tp.load_kline(sym)
        d = d[(d["date"] >= tp.EVAL_START) & (d["date"] <= tp.EVAL_END)].reset_index(drop=True)
        buy_px = d.iloc[0]["open"]
        shares = (tp.INITIAL_CASH // buy_px // 100) * 100
        cash0 = tp.INITIAL_CASH - shares * buy_px  # 买入成本已扣（v1.1 修正）
        eq = pd.Series([cash0 + shares * r.close for r in d.itertuples()])
        total = (eq.iloc[-1] / tp.INITIAL_CASH - 1) * 100
        mdd = (eq / eq.cummax() - 1).min() * 100
        ann = ((eq.iloc[-1] / tp.INITIAL_CASH) ** (252 / max(len(eq), 1)) - 1) * 100
        ret = eq.pct_change()
        sharpe = ret.mean() / ret.std() * math.sqrt(252) if ret.std() and not pd.isna(ret.std()) else 0
        results.append({
            "symbol": sym, "symbol_name": name, "strategy": "buy&hold",
            "total_return_pct": round(total, 2), "annual_return_pct": round(ann, 2),
            "max_drawdown_pct": round(mdd, 2), "sharpe": round(sharpe, 2),
            "initial_cash": tp.INITIAL_CASH, "start": tp.EVAL_START, "end": tp.EVAL_END,
        })
        print(f"{name:<16} 满仓 {total:>7.2f}%  年化 {ann:>6.2f}%  MDD {mdd:>7.2f}%  Sharpe {sharpe:.2f}")
    with open(os.path.join(OUT, "buyhold_summary.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("✅ 已写入 output/buyhold_summary.json")


if __name__ == "__main__":
    main()
