# -*- coding: utf-8 -*-
"""完整执行链回测 → 仪表盘 + 图表（8/31 归因 P1-4 证据展示）"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
REF = r"C:/Users/lenovo/.workbuddy/plugins/marketplaces/experts/plugins/strategy-backtest-expert/skills/quant-backtest-lab/reference"
sys.path.insert(0, REF)
OUT = os.path.normpath(os.path.join(BASE, "..", "output"))

from render_dashboard import build_dashboard_data, render_dashboard  # noqa: E402

SYMBOLS = {"sz159995": "芯片ETF", "sh512880": "证券ETF", "sh515180": "红利ETF", "sh518880": "黄金ETF", "sh513100": "纳指ETF"}

eq = pd.read_csv(os.path.join(OUT, "full_anchor_equity.csv"))
tr = pd.read_csv(os.path.join(OUT, "full_anchor_trades.csv"))
sm = {f"{s['symbol']}_{s['segment']}": s for s in json.load(open(os.path.join(OUT, "full_anchor_summary.json"), encoding="utf-8"))["summary"]}

def norm_curve(symbol, seg):
    d = eq[(eq.symbol == symbol) & (eq.segment == seg)].sort_values("date")
    start = d["value"].iloc[0]
    return [{"date": r.date, "value": r.value / start} for r in d.itertuples()]

def trade_rows(symbol, seg):
    d = tr[(tr.symbol == symbol) & (tr.segment == seg)].copy()
    return d.to_dict("records")

modules = []
tabs = [{"id": "compare", "label": "对比总览"}]
for sym, name in SYMBOLS.items():
    tabs.append({"id": sym, "label": name})

# ---- Tab1 对比总览 ----
modules.append({
    "type": "text", "tab": "compare",
    "content": (
        "**完整执行链回测**（334 分批建仓 + -8% 止损 + ③疏档止盈 + 奔跑仓 + 月操作≤4笔），2021-09 ~ 2026-08 三区间切片。"
        "核心结论：策略普遍以收益换回撤控制——黄金/纳指/红利回撤显著低于满仓；趋势市（seg2）止盈结构仍拖累收益，与止盈单维回测一致。"
    ),
})

mrows = []
for sym, name in SYMBOLS.items():
    s = sm[f"{sym}_full"]
    mrows.append({
        "metric": name,
        "values": [
            {"main": f"{s['total_return_pct']}%"},
            {"main": f"{s['max_drawdown_pct']}%"},
            {"main": f"{s['sharpe']}"},
            {"main": f"{s['win_rate_pct']}%"},
            {"main": str(s["total_trades"])},
            {"main": f"{s['buyhold_return_pct']}%"},
        ],
    })
modules.append({
    "type": "metric_table", "tab": "compare", "title": "完整执行链 vs 满仓（full 区间）",
    "columns": ["标的", "策略收益", "策略回撤", "Sharpe", "胜率", "交易数", "满仓收益"],
    "rows": mrows,
})

modules.append({
    "type": "line_chart", "tab": "compare", "title": "策略净值对比（归一化 · full 区间）",
    "subtitle": "完整执行链 · 5 标的",
    "series": [{"name": name, "points": norm_curve(sym, "full")} for sym, name in SYMBOLS.items()],
})

modules.append({
    "type": "text", "tab": "compare",
    "content": "> ⚠️ 以上内容由 AI 基于公开信息整理生成，仅供参考，不构成任何投资建议或个股推荐。投资有风险，决策需谨慎。",
})

# ---- Tab2-6 每标的分页 ----
for sym, name in SYMBOLS.items():
    s = sm[f"{sym}_full"]
    points = [{"date": p["date"], "equity": p["value"] / 100000.0,
               "drawdown_abs": 0.0, "pnl": (p["value"] - 100000.0)} for p in
              eq[(eq.symbol == sym) & (eq.segment == "full")].sort_values("date").to_dict("records")]
    markers = []
    for r in tr[(tr.symbol == sym) & (tr.segment == "full")].to_dict("records"):
        markers.append({
            "date": r["exit_date"], "action": "sell", "price": r["exit_price"],
            "size": r["size"], "pnl": r["pnl"], "pnl_pct": r["pnl_pct"],
            "label": f"{r['label']} {r['pnl_pct']:+.1f}%",
        })
    modules.append({
        "type": "overview_chart", "tab": sym,
        "stats": [
            {"label": "总收益", "value": f"{s['total_return_pct']}%", "raw": s["total_return_pct"]},
            {"label": "最大回撤", "value": f"{s['max_drawdown_pct']}%", "raw": s["max_drawdown_pct"]},
            {"label": "Sharpe", "value": f"{s['sharpe']}"},
            {"label": "交易数", "value": str(s["total_trades"])},
            {"label": "胜率", "value": f"{s['win_rate_pct']}%"},
        ],
        "points": points, "markers": markers,
        "series_key": "equity", "stroke": "#3987e5", "area_fill": "rgba(57,135,229,0.15)",
        "bars_key": "drawdown_abs", "bars_fill": "rgba(144,133,233,0.25)",
        "toggles": [
            {"id": "equity", "label": "净值曲线", "checked": True},
            {"id": "drawdown", "label": "回撤", "checked": False},
            {"id": "trades", "label": "卖出标记", "checked": True},
        ],
        "modes": [{"id": "absolute", "label": "净值", "active": True},
                  {"id": "percentage", "label": "收益率", "active": False}],
        "overlay_series": [{"name": "满仓", "stroke": "#9e9e9e", "points": norm_curve(sym, "full")}],
    })
    modules.append({
        "type": "trades_table", "tab": sym, "title": f"{name} · 全部交易（full）",
        "rows": trade_rows(sym, "full"),
        "columns": [
            {"key": "entry_date", "label": "入场", "format": "text"},
            {"key": "exit_date", "label": "出场", "format": "text"},
            {"key": "label", "label": "动作", "format": "text"},
            {"key": "size", "label": "份额", "format": "number"},
            {"key": "entry_price", "label": "成本", "format": "number"},
            {"key": "exit_price", "label": "出场价", "format": "number"},
            {"key": "pnl", "label": "盈亏", "format": "number"},
            {"key": "pnl_pct", "label": "收益率", "format": "pct"},
        ],
    })

report = {
    "meta": {
        "strategy_name": "Anchor 完整执行链（334建仓+止损+疏档止盈+月限额）",
        "market": "china_a", "language": "zh",
        "initial_cash": 100000.0, "window_start_value": 100000.0,
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    },
    "summary": {},
    "modules": modules,
    "ui": {"tabs": tabs, "active_tab": "compare", "language": "zh"},
}
render_dashboard(report, os.path.join(OUT, "index.html"))
print("✅ index.html 已渲染")

# ---- matplotlib：完整执行链 vs 满仓（收益/回撤）----
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

names = list(SYMBOLS.values())
syms = list(SYMBOLS.keys())
strat = [sm[f"{x}_full"]["total_return_pct"] for x in syms]
bh = [sm[f"{x}_full"]["buyhold_return_pct"] for x in syms]
strat_dd = [sm[f"{x}_full"]["max_drawdown_pct"] for x in syms]
bh_dd = [sm[f"{x}_full"]["buyhold_mdd_pct"] for x in syms]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.6))
x = range(len(names))
ax1.bar([i - 0.18 for i in x], strat, 0.36, label="完整执行链", color="#3987e5")
ax1.bar([i + 0.18 for i in x], bh, 0.36, label="满仓持有", color="#9e9e9e")
for i, (a, b) in enumerate(zip(strat, bh)):
    ax1.text(i - 0.18, a + 1, f"{a:.0f}", ha="center", fontsize=8)
    ax1.text(i + 0.18, b + 1, f"{b:.0f}", ha="center", fontsize=8)
ax1.axhline(0, color="gray", lw=0.8); ax1.set_xticks(list(x)); ax1.set_xticklabels(names)
ax1.set_ylabel("总收益率 (%)"); ax1.set_title("完整执行链 vs 满仓 · 收益")
ax1.legend(); ax1.grid(axis="y", alpha=0.3)

ax2.bar([i - 0.18 for i in x], strat_dd, 0.36, label="完整执行链", color="#3987e5")
ax2.bar([i + 0.18 for i in x], bh_dd, 0.36, label="满仓持有", color="#9e9e9e")
for i, (a, b) in enumerate(zip(strat_dd, bh_dd)):
    ax2.text(i - 0.18, a - 2, f"{a:.0f}", ha="center", fontsize=8)
    ax2.text(i + 0.18, b - 2, f"{b:.0f}", ha="center", fontsize=8)
ax2.axhline(0, color="gray", lw=0.8); ax2.set_xticks(list(x)); ax2.set_xticklabels(names)
ax2.set_ylabel("最大回撤 (%)"); ax2.set_title("完整执行链 vs 满仓 · 回撤")
ax2.legend(); ax2.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.show(); plt.savefig(os.path.join(OUT, "full_anchor_vs_benchmark.png"), dpi=130)
print("✅ full_anchor_vs_benchmark.png 已生成")
