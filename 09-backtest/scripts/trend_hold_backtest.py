# -*- coding: utf-8 -*-
"""
方案1 回测：趋势跟踪版（取消阶梯止盈，改移动止损）vs 现有 Anchor 规则
================================================================
改动点（相对 full_anchor_backtest.py）：
  - 删除 TIERS 阶梯止盈（+10/+20/+35 各卖 25%）
  - 退出机制改为「移动止损」：收盘破 20 日线 或 自持有峰值回撤 >= 8% 或 相对成本 -8% → 次日开盘清仓
  - 其余不变：334 建仓、月限额 <=4、冷却 5 交易日、无前视、A股 ETF 手数 + T+1 + 万三双边费
目的：干净分离「止盈」这一个变量，量化「让利润奔跑」在趋势资产上的收益提升与回撤代价。
"""
import io
import json
import math
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "..", "data")
OUT_DIR = os.path.join(BASE, "..", "output")

SYMBOLS = {
    "sz159995": "芯片ETF",
    "sh512880": "证券ETF",
    "sh515180": "红利ETF",
    "sh518880": "黄金ETF",
    "sh513100": "纳指ETF",
}
INITIAL_CASH = 100000.0
LOT = 100
COMMISSION = 0.0003

BATCH = [0.3, 0.3, 0.4]
BATCH_GAP = 3
COOLDOWN = 5
MONTH_LIMIT = 4
STOP_LOSS = 0.08      # -8% 相对成本硬止损
TREND_MA = 20         # 移动止损：破 20 日线
TREND_DD = 0.08       # 移动止损：自峰值回撤 8%

SEGMENTS = {
    "full": ("2021-09-01", "2026-09-24"),
    "seg1": ("2021-09-01", "2023-08-31"),
    "seg2": ("2023-09-01", "2026-09-24"),
}


def load_kline(symbol: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, f"_kline_{symbol}.md")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    rows = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|", line)
            if m:
                rows.append((m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4)), float(m.group(5))))
    df = pd.DataFrame(rows, columns=["date", "open", "last", "high", "low"])
    df = df.rename(columns={"last": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["ma20"] = df["close"].rolling(TREND_MA).mean()
    return df


def run_trend_strategy(df, symbol, name, eval_start, eval_end):
    cash = INITIAL_CASH
    shares = 0
    avg_cost = 0.0
    entry_date = None
    entry_day = -1
    batch_idx = 0
    batch_due = -1
    pending_first = False
    state = "idle"
    cooldown_until = -1
    ops_month = {}
    ops_month_key = ""
    peak = 0.0
    stop_pending = False
    equity = []
    trades = []

    def month_key(dt):
        return dt.strftime("%Y-%m")

    def check_month(dt):
        nonlocal ops_month_key
        k = month_key(dt)
        if k != ops_month_key:
            ops_month_key = k
            ops_month.clear()

    def count_op(dt):
        check_month(dt)
        k = month_key(dt)
        ops_month[k] = ops_month.get(k, 0) + 1

    def reset_cycle():
        nonlocal avg_cost, peak
        avg_cost = 0.0
        peak = 0.0

    for i, row in df.iterrows():
        dt = row["date"]
        o, c = row["open"], row["close"]
        date = dt.strftime("%Y-%m-%d")

        if date < eval_start:
            continue
        if date > eval_end:
            break

        # 1) 昨日挂单：334 第一批
        if pending_first and state == "idle":
            check_month(dt)
            if sum(ops_month.values()) + 1 > MONTH_LIMIT:
                pending_first = False
            else:
                budget = cash * BATCH[0]
                size = int(budget / (o * (1 + COMMISSION)) / LOT) * LOT
                if size >= LOT:
                    cost = size * o * (1 + COMMISSION)
                    cash -= cost
                    shares = size
                    avg_cost = o
                    peak = o
                    entry_date = date
                    entry_day = i
                    count_op(dt)
                    state = "building"
                    batch_idx = 1
                    batch_due = i + BATCH_GAP
                pending_first = False

        # 2) 昨日挂单：334 后续批
        if state == "building" and shares >= LOT and batch_idx < len(BATCH):
            if i >= batch_due:
                budget = cash * BATCH[batch_idx]
                size = int(budget / (o * (1 + COMMISSION)) / LOT) * LOT
                if size >= LOT:
                    cost = size * o * (1 + COMMISSION)
                    cash -= cost
                    new_avg = (shares * avg_cost + size * o) / (shares + size)
                    shares += size
                    avg_cost = new_avg
                    peak = max(peak, o)
                    count_op(dt)
                batch_idx += 1
                batch_due = i + BATCH_GAP
                if batch_idx >= len(BATCH):
                    state = "holding"

        # 3) 昨日挂单：移动止损 / 硬止损 清仓
        if stop_pending and shares >= LOT:
            sell_sh = shares
            proceeds = sell_sh * o * (1 - COMMISSION)
            cash += proceeds
            pnl = proceeds - sell_sh * avg_cost * (1 + COMMISSION)
            pnl_pct = (o / avg_cost - 1) * 100
            trades.append({
                "entry_date": entry_date, "exit_date": date, "side": "long",
                "size": sell_sh, "entry_price": round(avg_cost, 4),
                "exit_price": round(o, 4), "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2), "holding_bars": i - entry_day,
                "symbol": symbol, "symbol_name": name, "label": "趋势退出/止损",
            })
            shares = 0
            count_op(dt)
            reset_cycle()
            state = "cooldown"
            cooldown_until = i + COOLDOWN
        stop_pending = False

        # 4) 建仓信号：idle 即准备建仓（与现有一致，无条件回场）
        if state == "idle" and shares == 0 and not pending_first:
            pending_first = True

        # 5) 生成今日信号（次日执行）
        if state in ("building", "holding") and shares >= LOT:
            gain = c / avg_cost - 1
            # 硬止损：相对成本 -8%
            if gain <= -STOP_LOSS:
                stop_pending = True
            else:
                # 移动止损：自峰值回撤 8% 或 破 20 日线
                peak = max(peak, c)
                dd = c / peak - 1 if peak else 0.0
                ma = row["ma20"]
                if dd <= -TREND_DD or (not pd.isna(ma) and c < ma):
                    stop_pending = True

        # 6) 冷却结束回 idle
        if state == "cooldown" and i >= cooldown_until:
            state = "idle"

        last_close = c
        last_date = date
        if date <= eval_end:
            equity.append({"date": date, "value": round(cash + shares * c, 2)})

    # 期末强平
    if shares >= LOT:
        o = last_close
        proceeds = shares * o * (1 - COMMISSION)
        pnl = proceeds - shares * avg_cost * (1 + COMMISSION)
        pnl_pct = (o / avg_cost - 1) * 100
        trades.append({
            "entry_date": entry_date, "exit_date": last_date, "side": "long",
            "size": shares, "entry_price": round(avg_cost, 4),
            "exit_price": round(o, 4), "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2), "holding_bars": None,
            "symbol": symbol, "symbol_name": name, "label": "期末强平",
        })
        cash += proceeds
        shares = 0
        if equity:
            equity[-1]["value"] = round(cash, 2)

    return equity, trades


def buyhold_benchmark(df, eval_start, eval_end):
    d = df[(df["date"] >= eval_start) & (df["date"] <= eval_end)].reset_index(drop=True)
    if d.empty:
        return None
    buy_px = d.iloc[0]["open"]
    shares = int(INITIAL_CASH / (buy_px * (1 + COMMISSION)) / LOT) * LOT
    cost = shares * buy_px * (1 + COMMISSION)
    cash0 = INITIAL_CASH - cost
    eq = pd.Series([cash0 + shares * r.close for r in d.itertuples()])
    return {
        "total_return_pct": round((eq.iloc[-1] / INITIAL_CASH - 1) * 100, 2),
        "max_drawdown_pct": round((eq / eq.cummax() - 1).min() * 100, 2),
    }


def metrics(equity):
    if not equity:
        return {}
    s = pd.Series([e["value"] for e in equity])
    total = (s.iloc[-1] / INITIAL_CASH - 1) * 100
    n = len(s)
    years = n / 244
    annual = ((s.iloc[-1] / INITIAL_CASH) ** (1 / years) - 1) * 100 if years > 0 else 0
    mdd = (s / s.cummax() - 1).min() * 100
    ret = s.pct_change().dropna()
    sharpe = (ret.mean() / ret.std() * math.sqrt(244)) if ret.std() > 0 and len(ret) > 1 else 0
    return {
        "total_return_pct": round(total, 2),
        "annual_return_pct": round(annual, 2),
        "max_drawdown_pct": round(mdd, 2),
        "sharpe": round(float(sharpe), 2),
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    # 读现有 Anchor 结果（full_anchor_summary.json 的 full segment）
    existing = {}
    p = os.path.join(OUT_DIR, "full_anchor_summary.json")
    if os.path.exists(p):
        for row in json.load(open(p, encoding="utf-8"))["summary"]:
            if row.get("segment") == "full":
                existing[row["symbol"]] = row

    results = []
    print(f"{'标的':<10} {'策略':<12} {'总收益':>8} {'年化':>7} {'MDD':>8} {'Sharpe':>7} {'交易':>5} {'胜率':>6}")
    print("-" * 80)
    for sym, name in SYMBOLS.items():
        df = load_kline(sym)
        s0, s1 = SEGMENTS["full"]
        eq, tr = run_trend_strategy(df, sym, name, s0, s1)
        m = metrics(eq)
        bh = buyhold_benchmark(df, s0, s1)
        wins = [t for t in tr if t["pnl"] >= 0]
        wr = round(len(wins) / len(tr) * 100, 1) if tr else 0
        m.update({
            "symbol": sym, "symbol_name": name, "strategy": "趋势跟踪(无止盈)",
            "total_trades": len(tr), "win_rate_pct": wr,
            "buyhold_return_pct": bh["total_return_pct"] if bh else None,
            "buyhold_mdd_pct": bh["max_drawdown_pct"] if bh else None,
        })
        results.append(m)

        ex = existing.get(sym, {})
        ex_ret = ex.get("total_return_pct")
        ex_mdd = ex.get("max_drawdown_pct")
        ex_ann = ex.get("annual_return_pct")
        ex_sh = ex.get("sharpe")

        print(f"{name:<10} {'趋势跟踪':<12} {m['total_return_pct']:>7.2f}% {m['annual_return_pct']:>6.2f}% {m['max_drawdown_pct']:>7.2f}% {m['sharpe']:>7.2f} {len(tr):>5} {wr:>5.1f}%")
        if ex_ret is not None:
            d_ret = m['total_return_pct'] - ex_ret
            d_mdd = m['max_drawdown_pct'] - ex_mdd
            print(f"{'':<10} {'现有Anchor':<12} {ex_ret:>7.2f}% {ex_ann:>6.2f}% {ex_mdd:>7.2f}% {ex_sh:>7.2f}  {'':>5}")
            print(f"{'':<10} {'→差值':<12} {d_ret:>+7.2f}pp {'':>6} {d_mdd:>+7.2f}pp")
        if m['buyhold_return_pct'] is not None:
            print(f"{'':<10} {'买入持有':<12} {m['buyhold_return_pct']:>7.2f}% {'':>6} {m['buyhold_mdd_pct']:>7.2f}%")
        print()

    json.dump({"meta": {"strategy": "趋势跟踪版（取消阶梯止盈，改移动止损）", "initial_cash": INITIAL_CASH},
               "summary": results},
              open(os.path.join(OUT_DIR, "trend_hold_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n✅ 已写入 {OUT_DIR}/trend_hold_summary.json")


if __name__ == "__main__":
    main()
