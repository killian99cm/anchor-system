# -*- coding: utf-8 -*-
"""
Anchor 完整执行链回测（8/31 归因 P1-4 证据）
=============================================
把 Anchor 真实执行链完整建模（替代此前"止盈单维度"实验）：
  - 建仓：334 分批（3:3:4，批间隔 3 交易日，次日开盘执行）
  - 止损：-8% 收盘触发 → 次日开盘清仓（含缓冲语义）
  - 止盈：③疏档 +10%/+20%/+35% 各卖 25%（原始建仓份额）+ 剩余 25% 奔跑仓（破 20 日线或自峰值回撤≥8% 出清）
  - 限额：月操作 ≤4 笔（自然月，超限跳过新买入）
  - 冷却：清仓后 5 交易日不建仓
  - 多区间：full(2021-09~2026-08) / seg1(2021-09~2023-08 跌市) / seg2(2023-09~2026-08 涨市)
信号收盘确认 → 次日开盘执行（无前视）；A股 ETF 100 份手数 + T+1 + 万三双边费。
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
COMMISSION = 0.0003  # ETF 双边万三，免印花税

# ③疏档（8/31 候选）：+10%/+20%/+35% 各卖 25%
TIERS = [(0.10, 0.25), (0.20, 0.25), (0.35, 0.25)]
RUNNER_MA = 20          # 奔跑仓破 20 日线出清
RUNNER_DD = 0.08        # 或自峰值回撤 ≥8%
STOP_LOSS = 0.08        # -8% 止损
BATCH = [0.3, 0.3, 0.4] # 334 分批
BATCH_GAP = 3           # 批间隔交易日
COOLDOWN = 5            # 清仓冷却交易日
MONTH_LIMIT = 4         # 月操作上限

SEGMENTS = {
    "full": ("2021-09-01", "2026-08-26"),
    "seg1": ("2021-09-01", "2023-08-31"),
    "seg2": ("2023-09-01", "2026-08-26"),
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
                rows.append((m.group(1), float(m.group(2)), float(m.group(3)),
                             float(m.group(4)), float(m.group(5))))
    df = pd.DataFrame(rows, columns=["date", "open", "last", "high", "low"])
    df = df.rename(columns={"last": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)  # westock 数据最新在前，需升序
    df["ma20"] = df["close"].rolling(RUNNER_MA).mean()
    return df


def run_strategy(df, symbol, name, eval_start, eval_end):
    """单标的 × 单区间完整执行链。返回 (equity_curve, trade_history)。"""
    cash = INITIAL_CASH
    shares = 0
    avg_cost = 0.0          # 加权持仓成本
    entry_date = None
    entry_day = -1          # 建仓首日索引（T+1 用）
    plan_shares = 0         # 334 分批计划总份额（分批完成前未知，先记录已投入金额）
    batch_cash = 0.0        # 本批次计划金额
    batch_idx = 0           # 下一批索引 0/1/2
    batch_due = -1          # 下一批应执行日索引
    pending_first = False   # 建仓信号（第 1 批）
    state = "idle"          # idle/building/holding/cooldown
    cooldown_until = -1
    ops_month = {}          # 月操作计数 {"2026-08": n}（跨自然月自动清空）
    ops_month_key = ""      # 当前计数月
    sold_tiers = 0          # 已触发的止盈档数
    runner_active = False
    runner_peak = 0.0
    stop_pending = False
    tp_pending = []         # [(frac, label)] 次日卖出队列
    equity = []
    trades = []
    signal_price = 0.0

    def month_key(dt):
        return dt.strftime("%Y-%m")

    def check_month(dt):
        """跨自然月时清空月计数（必须在查询/计数前调用，防上月累计永久拦截）"""
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
        nonlocal sold_tiers, runner_active, avg_cost, runner_peak
        sold_tiers = 0
        runner_active = False
        runner_peak = 0.0
        avg_cost = 0.0

    for i, row in df.iterrows():
        dt = row["date"]
        o, c = row["open"], row["close"]
        date = dt.strftime("%Y-%m-%d")

        # 0) 评估窗口 gating：窗口前只预热指标（ma20 已向量化），窗口后停止（交易/净值均受限于窗口）
        if date < eval_start:
            continue
        if date > eval_end:
            break

        # 1) 先执行昨日挂单（次日开盘）
        if pending_first and state == "idle":
            check_month(dt)
            if sum(ops_month.values()) + 1 > MONTH_LIMIT:
                pending_first = False  # 月限额：本次建仓跳过
            else:
                # 第 1 批：计划用现金的 30%
                budget = cash * BATCH[0]
                size = int(budget / (o * (1 + COMMISSION)) / LOT) * LOT
                if size >= LOT:
                    cost = size * o * (1 + COMMISSION)
                    cash -= cost
                    shares = size
                    avg_cost = o
                    entry_date = date
                    entry_day = i
                    count_op(dt)
                    state = "building"
                    batch_idx = 1
                    batch_due = i + BATCH_GAP
                pending_first = False

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
                    count_op(dt)
                batch_idx += 1
                batch_due = i + BATCH_GAP
                if batch_idx >= len(BATCH):
                    state = "holding"

        for frac, label, tp in tp_pending:
            if shares >= LOT:
                sell_sh = min(int(shares * frac / LOT) * LOT, shares)
                if sell_sh > 0:
                    proceeds = sell_sh * o * (1 - COMMISSION)
                    cash += proceeds
                    pnl = proceeds - sell_sh * avg_cost * (1 + COMMISSION)
                    pnl_pct = (o / avg_cost - 1) * 100
                    trades.append({
                        "entry_date": entry_date, "exit_date": date, "side": "long",
                        "size": sell_sh, "entry_price": round(avg_cost, 4),
                        "exit_price": round(o, 4), "pnl": round(pnl, 2),
                        "pnl_pct": round(pnl_pct, 2), "holding_bars": i - entry_day,
                        "symbol": symbol, "symbol_name": name, "label": label,
                    })
                    shares -= sell_sh
                    count_op(dt)
        tp_pending = []

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
                "symbol": symbol, "symbol_name": name, "label": "止损-8%",
            })
            shares = 0
            count_op(dt)
            reset_cycle()
            state = "cooldown"
            cooldown_until = i + COOLDOWN
        stop_pending = False

        # 2) 生成今日信号（次日执行）
        if state == "idle" and shares == 0 and not pending_first:
            pending_first = True

        if state in ("building", "holding") and shares >= LOT:
            gain = c / avg_cost - 1
            # 止盈档（③疏档）
            while sold_tiers < len(TIERS):
                thr, frac = TIERS[sold_tiers]
                if gain >= thr:
                    tp_pending.append((frac, f"止盈+{int(thr*100)}%卖25%", None))
                    sold_tiers += 1
                else:
                    break
            # 止损（收盘触发，次日执行）
            if gain <= -STOP_LOSS:
                stop_pending = True
            # 奔跑仓
            if sold_tiers >= len(TIERS) and shares > 0:
                runner_active = True
            if runner_active and shares > 0:
                runner_peak = max(runner_peak, c)
                ma = row["ma20"]
                dd = c / runner_peak - 1 if runner_peak else 0.0
                if (not pd.isna(ma) and c < ma) or dd <= -RUNNER_DD:
                    tp_pending.append((1.0, "奔跑仓出清(破20日线或回撤≥8%)", None))

        # 3) 清仓完成态（止盈档卖完奔跑仓出清后 shares==0）
        if state in ("building", "holding") and shares == 0 and sold_tiers >= len(TIERS):
            state = "cooldown"
            cooldown_until = i + COOLDOWN
            runner_active = False
            sold_tiers = 0
            avg_cost = 0.0

        # 冷却结束回 idle
        if state == "cooldown" and i >= cooldown_until:
            state = "idle"

        # 4) 记录净值（并记录窗口最后一天的收盘价，供期末强平使用）
        last_close = c
        last_date = date
        if date <= eval_end:
            equity.append({"date": date, "value": round(cash + shares * c, 2)})

    # 期末强制平仓（用评估窗口最后一天的收盘价，避免 look-ahead 使用窗口外价格）
    if shares >= LOT:
        o = last_close
        proceeds = shares * o * (1 - COMMISSION)
        pnl = proceeds - shares * avg_cost * (1 + COMMISSION)
        pnl_pct = (o / avg_cost - 1) * 100
        trades.append({
            "entry_date": entry_date, "exit_date": last_date,
            "side": "long", "size": shares, "entry_price": round(avg_cost, 4),
            "exit_price": round(o, 4), "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
            "holding_bars": None,
            "symbol": symbol, "symbol_name": name, "label": "期末强制平仓",
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
    all_equity, all_trades, summaries = [], [], []

    for sym, name in SYMBOLS.items():
        df = load_kline(sym)
        for seg, (s0, s1) in SEGMENTS.items():
            eq, tr = run_strategy(df, sym, name, s0, s1)
            m = metrics(eq)
            bh = buyhold_benchmark(df, s0, s1)
            wins = [t for t in tr if t["pnl"] >= 0]
            m.update({
                "symbol": sym, "symbol_name": name, "segment": seg,
                "start": s0, "end": s1,
                "total_trades": len(tr),
                "win_rate_pct": round(len(wins) / len(tr) * 100, 1) if tr else 0,
                "buyhold_return_pct": bh["total_return_pct"] if bh else None,
                "buyhold_mdd_pct": bh["max_drawdown_pct"] if bh else None,
            })
            summaries.append(m)
            for e in eq:
                e.update({"symbol": sym, "symbol_name": name, "segment": seg})
            all_equity.extend(eq)
            for t in tr:
                t["segment"] = seg
            all_trades.extend(tr)
            print(f"  {name:<12} {seg:<5} 收益 {m['total_return_pct']:>7.2f}%  MDD {m['max_drawdown_pct']:>7.2f}%  Sharpe {m['sharpe']:>5.2f}  交易 {len(tr)}  胜率 {m['win_rate_pct']:.0f}%  (满仓 {m['buyhold_return_pct']}%)")

    pd.DataFrame(all_equity).to_csv(os.path.join(OUT_DIR, "full_anchor_equity.csv"), index=False)
    pd.DataFrame(all_trades).to_csv(os.path.join(OUT_DIR, "full_anchor_trades.csv"), index=False)
    json.dump({"meta": {"strategy": "Anchor 完整执行链（334建仓+止损+疏档止盈+月限额）", "initial_cash": INITIAL_CASH, "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}, "summary": summaries},
              open(os.path.join(OUT_DIR, "full_anchor_summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n✅ 三件套已写入 {OUT_DIR}")


if __name__ == "__main__":
    main()
