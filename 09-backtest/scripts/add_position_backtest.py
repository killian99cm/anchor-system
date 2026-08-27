# -*- coding: utf-8 -*-
"""
加仓专项回测：追高 vs 回调买入（add_position_backtest.py）
- 目的：量化「打分卡 ②回调日」维度的证据——红日追高 vs 回调日买入，后续收益差异
- 信号定义：
  追高（红日）= 当日收盘涨幅 >= 2%
  回调 = 当日跌幅 >= 1% 或 自5日高回撤 >= 2%
- 执行：信号次日开盘买入，持 T+5 / T+20 卖出（T+1 规则，无前视）
- 数据：09-backtest/data/_kline_*.md（5 标的，2021-09~2026-08）
"""
import os
import re
import sys
from datetime import datetime

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

SYMBOLS = {
    "sz159995": "芯片ETF",
    "sh512880": "证券ETF",
    "sh515180": "红利ETF",
    "sh518880": "黄金ETF",
    "sh513100": "纳指ETF",
}


def load_kline(symbol: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, f"_kline_{symbol}.md")
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|", line)
            if m:
                rows.append([m.group(1), float(m.group(2)), float(m.group(3)),
                             float(m.group(4)), float(m.group(5)), float(m.group(6))])
    df = pd.DataFrame(rows, columns=["date", "open", "last", "high", "low", "volume"])
    df = df.rename(columns={"last": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["pct"] = df["close"].pct_change() * 100
    df["hi5"] = df["close"].rolling(5).max().shift(1)  # 昨日视角的5日高
    df["dd5"] = (df["close"] / df["hi5"] - 1) * 100  # 自5日高回撤
    return df


def backtest(symbol: str, hold: int) -> dict:
    df = load_kline(symbol)
    n = len(df)
    chase, pull = [], []  # (signal_date, buy_price, sell_price, ret)
    for i in range(1, n - hold):
        row = df.iloc[i]
        pct = row["pct"]
        dd5 = row["dd5"]
        buy_px = df.iloc[i + 1]["open"]  # 次日开盘执行
        sell_px = df.iloc[i + 1 + hold]["close"] if i + 1 + hold < n else None
        if sell_px is None or pd.isna(buy_px):
            continue
        ret = (sell_px / buy_px - 1) * 100
        if pct >= 2.0:  # 追高：红日
            chase.append((row["date"], ret))
        if pct <= -1.0 or dd5 <= -2.0:  # 回调日
            pull.append((row["date"], ret))
    return {"chase": chase, "pull": pull}


def stat(name: str, rows: list) -> dict:
    if not rows:
        return {"n": 0}
    rets = [r[1] for r in rows]
    s = pd.Series(rets)
    return {
        "n": len(rows),
        "avg": round(s.mean(), 2),
        "median": round(s.median(), 2),
        "win": round((s > 0).mean() * 100, 1),
        "max": round(s.max(), 2),
        "min": round(s.min(), 2),
    }


def main():
    print("=" * 72)
    print("加仓专项回测：追高（红日≥2%）vs 回调日买入 · 次日开盘执行 · T+1")
    print("=" * 72)
    rows_all = []
    for hold in (5, 20):
        print(f"\n--- 持有 T+{hold} 交易日 ---")
        print(f"{'标的':<8} {'追高 n/均收益/胜率':<22} {'回调 n/均收益/胜率':<22} {'差额(回调-追高)':<14}")
        for sym, name in SYMBOLS.items():
            r = backtest(sym, hold)
            cs, ps = stat("chase", r["chase"]), stat("pull", r["pull"])
            diff = (ps.get("avg", 0) - cs.get("avg", 0)) if cs.get("n") and ps.get("n") else None
            d = f"{diff:+.2f}pp" if diff is not None else "—"
            print(f"{name:<8} {cs.get('n',0):>4} / {cs.get('avg','—'):>6} / {cs.get('win','—'):>5}%  "
                  f"{ps.get('n',0):>4} / {ps.get('avg','—'):>6} / {ps.get('win','—'):>5}%  {d}")
            if cs.get("n") and ps.get("n"):
                rows_all.append({"hold": hold, "symbol": name, "chase_avg": cs["avg"],
                                 "pull_avg": ps["avg"], "diff": round(diff, 2)})

    print("\n--- 汇总（5 标的全样本）---")
    for hold in (5, 20):
        sub = [r for r in rows_all if r["hold"] == hold]
        avg_diff = sum(r["diff"] for r in sub) / len(sub) if sub else 0
        win_count = sum(1 for r in sub if r["diff"] > 0)
        print(f"  T+{hold}: 回调优于追高的标的比例 {win_count}/{len(sub)} ｜ 平均差额 {avg_diff:+.2f}pp")

    print("\n结论（供打分卡②回调日证据）:")
    print("  若回调日买入平均收益显著高于红日追高 → 支持「回调日 1 分」的量化依据")
    print("  若差额不显著 → 说明回调日维度在样本内证据弱，需结合 ④资金确认 共同判定")


if __name__ == "__main__":
    main()
