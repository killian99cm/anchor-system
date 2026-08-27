# -*- coding: utf-8 -*-
"""
极端场景压力测试：2022 熊市区间（stress_test_2022.py）
- 区间：2022-01-01 ~ 2022-12-31（A股/全球权益典型熊市年）
- 对比：满仓 buy&hold vs -8% 止损策略（收盘触发→次日开盘清仓）
- 数据：09-backtest/data/_kline_*.md（5 标的，前复权）
"""
import os
import re
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SYMBOLS = {"sz159995": "芯片ETF", "sh512880": "证券ETF", "sh515180": "红利ETF",
           "sh518880": "黄金ETF", "sh513100": "纳指ETF"}
START, END = "2022-01-01", "2022-12-31"


def load(symbol: str) -> pd.DataFrame:
    rows = []
    with open(os.path.join(DATA_DIR, f"_kline_{symbol}.md"), encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|", line)
            if m:
                rows.append([m.group(1), float(m.group(2)), float(m.group(3))])
    df = pd.DataFrame(rows, columns=["date", "open", "close"])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def run(symbol: str, name: str):
    df = load(symbol)
    d = df[(df["date"] >= START) & (df["date"] <= END)].reset_index(drop=True)
    if len(d) < 20:
        return None
    # 满仓 buy&hold
    init = 100000.0
    sh = int(init // d.iloc[0]["open"] // 100) * 100
    cash = init - sh * d.iloc[0]["open"]
    eq = [cash + sh * c for c in d["close"]]
    s = pd.Series(eq)
    bh_ret = (eq[-1] / init - 1) * 100
    bh_mdd = (s / s.cummax() - 1).min() * 100

    # -8% 止损策略（收盘触发→次日开盘清仓；清仓后不再入场）
    cash2, shares2, avg = init, 0, 0.0
    stopped = False
    eq2, stop_px = [], None
    for i, row in d.iterrows():
        if i == 0:
            shares2 = int(cash2 // row["open"] // 100) * 100
            cash2 -= shares2 * row["open"]
            avg = row["open"]
        # 昨日止损信号 → 今日开盘清仓
        if stop_px is not None:
            cash2 += shares2 * row["open"]
            shares2, stopped, stop_px = 0, True, None
        # 收盘触发 -8%
        if shares2 and row["close"] / avg - 1 <= -0.08 and not stopped:
            stop_px = row["close"]
        eq2.append(cash2 + shares2 * row["close"])
    s2 = pd.Series(eq2)
    sl_ret = (eq2[-1] / init - 1) * 100
    sl_mdd = (s2 / s2.cummax() - 1).min() * 100
    return {"name": name, "bh_ret": bh_ret, "bh_mdd": bh_mdd,
            "sl_ret": sl_ret, "sl_mdd": sl_mdd, "stopped": stopped}


def main():
    print("=" * 78)
    print("2022 熊市压力测试（2022-01-01 ~ 2022-12-31）：满仓 vs -8% 止损")
    print("=" * 78)
    print(f"{'标的':<8} {'满仓收益':>8} {'满仓MDD':>8} {'止损收益':>8} {'止损MDD':>8} {'止损价值':<12}")
    for sym, name in SYMBOLS.items():
        r = run(sym, name)
        if not r:
            continue
        dd_save = r["bh_mdd"] - r["sl_mdd"]
        ret_impact = r["sl_ret"] - r["bh_ret"]
        print(f"{name:<8} {r['bh_ret']:>7.1f}% {r['bh_mdd']:>7.1f}% "
              f"{r['sl_ret']:>7.1f}% {r['sl_mdd']:>7.1f}% "
              f"回撤改善 {dd_save:>5.1f}pct / 收益 {ret_impact:+.1f}pct")
    print("\n结论：-8% 止损在 2022 熊市的量化价值 = 回撤保护（MDD 改善）；收益端看止损后是否踏空反弹（区间特性）")


if __name__ == "__main__":
    main()
