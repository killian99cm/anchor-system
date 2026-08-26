#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
takeprofit_compare_backtest.py — Anchor 止盈档位新旧对比回测（回测明算 · v1.0）

对比策略：
  A 旧档（v3.3）：+10% 卖 1/3 → +20% 再卖 1/3 → 剩余 1/3 持有到期
  B 新档（v3.4）：+8% 卖 25% → +15% 卖 25% → +25% 卖 25% → 剩余 25% 奔跑仓
                  （收盘破 20 日线 或 自高回撤 ≥8% → 次日开盘清仓）

规则约定：
  - 数据：westock-data K 线（前复权 qfq），2021-08 ~ 2026-08
  - 买入：区间首日开盘价全额买入（100 份手数）
  - 止盈：收盘价确认档位（浮盈率=close/avg_cost-1），次日开盘卖出对应份额（防 look-ahead）
  - T+1：买入当日不可卖出，最早次日
  - 费用：佣金 0.03% 双边（ETF 免印花税）
  - 期末：剩余持仓按期末收盘价强制清算
  - 每档止盈仅触发一次（reached 标记）
"""
import csv
import json
import math
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
COMMISSION = 0.0003  # 万三
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
LOT = 100  # ETF 场内 100 份/手


def load_kline(symbol: str) -> pd.DataFrame:
    """解析 westock-data 的 markdown K 线输出为 DataFrame（原始数据位于 ../data/）"""
    path = os.path.join(OUT_DIR, "..", "data", f"_kline_{symbol}.md")
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or "date" in line or line.startswith("| ---"):
                continue
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) < 6:
                continue
            try:
                rows.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                })
            except (ValueError, IndexError):
                continue
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def run_strategy(df: pd.DataFrame, variant: str) -> tuple:
    """
    运行单一标的的止盈策略。
    返回 (equity_curve, trade_history, final_value, stats)
    variant: "A"(旧档) / "B"(新档)
    """
    df = df[(df["date"] >= EVAL_START) & (df["date"] <= EVAL_END)].reset_index(drop=True)
    df["ma20"] = df["close"].rolling(20).mean()

    cash = INITIAL_CASH
    shares = 0
    init_shares = 0        # 原始建仓份额（止盈按原始份额的固定比例卖）
    avg_cost = 0.0
    entry_date = None

    # 档位定义：[(threshold, fraction_of_initial, label)]
    if variant == "A":
        TIERS = [(0.10, 1 / 3, "+10%卖1/3"), (0.20, 1 / 3, "+20%再卖1/3")]
    else:
        TIERS = [(0.08, 0.25, "+8%卖25%"), (0.15, 0.25, "+15%卖25%"), (0.25, 0.25, "+25%卖25%")]

    tier_idx = 0
    runner_active = False      # 奔跑仓模式（B 档卖满 3 档后，剩余恰为原始 25%）
    runner_peak_close = 0.0    # 奔跑仓启动后的最高收盘价
    buy_pending = False
    # 次日卖出队列：每项 (fraction_of_initial, label)
    sell_pending = []
    equity_curve = []
    trade_history = []

    buy_day = 0  # 买入日索引（T+1 计算持有时长）

    for i, row in df.iterrows():
        date = row["date"].strftime("%Y-%m-%d")
        o, c = row["open"], row["close"]

        # 1) 先执行昨日挂单（次日开盘成交）
        if buy_pending:
            px = o  # 执行日开盘价（不是信号日价格）
            shares = math.floor(cash / px / LOT) * LOT
            shares = max(shares, 0)
            if shares >= LOT:
                cost = shares * px
                fee = cost * COMMISSION
                cash -= (cost + fee)
                init_shares = shares
                avg_cost = px
                entry_date = date
                buy_day = i
            else:
                shares = 0
            buy_pending = False

        for frac, tp_label in sell_pending:
            # 按原始建仓份额的固定比例卖出（A：1/3 原始；B：25% 原始）
            sell_sh = math.floor(init_shares * frac / LOT) * LOT
            sell_sh = min(sell_sh, shares)
            if sell_sh > 0:
                proceeds = sell_sh * o
                fee = proceeds * COMMISSION
                cash += (proceeds - fee)
                pnl = (o - avg_cost) * sell_sh - fee
                pnl_pct = (o / avg_cost - 1) * 100 if avg_cost else 0.0
                trade_history.append({
                    "entry_date": entry_date, "exit_date": date, "side": "long",
                    "size": sell_sh, "entry_price": round(avg_cost, 4),
                    "exit_price": round(o, 4), "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "holding_bars": i - buy_day,
                    "symbol": None, "label": tp_label,
                })
                shares -= sell_sh
                if variant == "B" and tier_idx >= len(TIERS) and shares <= init_shares * 0.25 + LOT:
                    runner_active = True
                    runner_peak_close = c
        sell_pending = []

        # 2) 生成今日信号（明日执行）
        if i == 0 and shares == 0 and not buy_pending:
            buy_pending = True

        if shares >= LOT:
            gain = c / avg_cost - 1
            # 止盈档位（A/B 共同逻辑，每档仅触发一次）
            while tier_idx < len(TIERS):
                thr, frac, lbl = TIERS[tier_idx]
                if gain >= thr:
                    sell_pending.append((frac, lbl))
                    tier_idx += 1
                else:
                    break
            # 奔跑仓跟踪（B 档独有）
            if variant == "B" and runner_active:
                runner_peak_close = max(runner_peak_close, c)
                ma = row["ma20"]
                dd = c / runner_peak_close - 1 if runner_peak_close else 0.0
                if (not pd.isna(ma) and c < ma) or dd <= -0.08:
                    sell_pending.append((1.0, "奔跑仓出清(破20日线或回撤≥8%)"))

        # 3) 记录净值
        equity_curve.append({"date": date, "value": round(cash + shares * c, 2)})

    # 期末强平
    if shares >= LOT:
        last = df.iloc[-1]
        date = last["date"].strftime("%Y-%m-%d")
        proceeds = shares * last["close"]
        fee = proceeds * COMMISSION
        cash += (proceeds - fee)
        pnl = (last["close"] - avg_cost) * shares - fee  # 买入费已在建仓时扣过，不重复扣
        trade_history.append({
            "entry_date": entry_date, "exit_date": date, "side": "long",
            "size": shares, "entry_price": round(avg_cost, 4),
            "exit_price": round(last["close"], 4), "pnl": round(pnl, 2),
            "pnl_pct": round((last["close"] / avg_cost - 1) * 100, 2),
            "holding_bars": len(df) - 1 - buy_day,
            "symbol": None, "label": "期末强制平仓",
        })
        shares = 0

    final_value = cash
    return equity_curve, trade_history, final_value


def compute_stats(equity_curve, trades, initial_cash, variant_label):
    if not equity_curve:
        return {}
    eq = pd.DataFrame(equity_curve)
    eq["ret"] = eq["value"].pct_change()
    total = (eq["value"].iloc[-1] / initial_cash - 1) * 100
    n = len(eq)
    ann = ((eq["value"].iloc[-1] / initial_cash) ** (252 / max(n, 1)) - 1) * 100 if eq["value"].iloc[-1] > 0 else -100
    dd = (eq["value"] / eq["value"].cummax() - 1).min() * 100
    sharpe = eq["ret"].mean() / eq["ret"].std() * math.sqrt(252) if eq["ret"].std() and not pd.isna(eq["ret"].std()) else 0
    wins = [t for t in trades if t["pnl"] > 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    return {
        "strategy": variant_label,
        "total_return_pct": round(total, 2),
        "annual_return_pct": round(ann, 2),
        "max_drawdown_pct": round(dd, 2),
        "sharpe": round(sharpe, 2),
        "win_rate_pct": round(win_rate, 1),
        "total_trades": len(trades),
        "final_value": round(eq["value"].iloc[-1], 2),
    }


def main():
    all_equity = {}
    all_trades = []
    summaries = []
    meta_list = []

    for sym, name in SYMBOLS.items():
        df = load_kline(sym)
        for variant, vlabel in [("A", "旧档v3.3"), ("B", "新档v3.4")]:
            eq, tr, fv = run_strategy(df, variant)
            col = f"{sym}_{variant}"
            eqdf = pd.DataFrame(eq)
            all_equity[col] = eqdf.set_index("date")["value"]
            for t in tr:
                t["symbol"] = sym
                t["symbol_name"] = name
                t["strategy"] = vlabel
            all_trades.extend(tr)
            stats = compute_stats(eq, tr, INITIAL_CASH, vlabel)
            stats["symbol"] = sym
            stats["symbol_name"] = name
            summaries.append(stats)
            meta_list.append({
                "strategy_name": f"止盈档位{vlabel}", "symbol": sym,
                "start": EVAL_START, "end": EVAL_END,
                "initial_cash": INITIAL_CASH, "market": "china_a",
            })

    # 1) equity.csv（宽表）
    eq_wide = pd.DataFrame(all_equity).reset_index()
    eq_wide.to_csv(os.path.join(OUT_DIR, "takeprofit_equity.csv"), index=False)

    # 2) trades.csv
    with open(os.path.join(OUT_DIR, "takeprofit_trades.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "symbol_name", "strategy", "entry_date", "exit_date",
                                          "side", "size", "entry_price", "exit_price", "pnl", "pnl_pct",
                                          "holding_bars", "label"])
        w.writeheader()
        for t in all_trades:
            w.writerow(t)

    # 3) summary.json
    with open(os.path.join(OUT_DIR, "takeprofit_summary.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta_list, "summary": summaries}, f, ensure_ascii=False, indent=2)

    print(f"完成：5 标的 × 2 策略，交易笔数 {len(all_trades)}")
    for s in summaries:
        print(f"  {s['symbol_name']:<16} {s['strategy']:<8} 总收益 {s['total_return_pct']:>8.2f}%  "
              f"年化 {s['annual_return_pct']:>7.2f}%  MDD {s['max_drawdown_pct']:>7.2f}%  "
              f"Sharpe {s['sharpe']:>5.2f}  胜率 {s['win_rate_pct']:>5.1f}%  交易 {s['total_trades']}")


if __name__ == "__main__":
    main()
