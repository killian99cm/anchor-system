#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_dashboard.py — 渲染止盈档位对比回测的 HTML 仪表盘（回测明算 · 契约要求）"""
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"C:\Users\lenovo\.workbuddy\plugins\marketplaces\experts\plugins\strategy-backtest-expert\skills\quant-backtest-lab\reference")
from render_dashboard import render_dashboard  # noqa: E402

TEMPLATE = r"C:\Users\lenovo\.workbuddy\plugins\marketplaces\experts\plugins\strategy-backtest-expert\skills\quant-backtest-lab\reference\dashboard_template.html"

SYMBOLS = {
    "sz159995": "芯片ETF华夏(半导体)",
    "sh512880": "证券ETF",
    "sh515180": "红利ETF易方达",
    "sh518880": "黄金ETF",
    "sh513100": "纳指ETF",
}
INITIAL = 100000.0

eq = pd.read_csv(os.path.join(OUT, "takeprofit_equity.csv"))
tr = pd.read_csv(os.path.join(OUT, "takeprofit_trades.csv"))
sm = json.load(open(os.path.join(OUT, "takeprofit_summary.json"), encoding="utf-8"))
summaries = {s["symbol"] + "_" + ("A" if "旧档" in s["strategy"] else "B"): s for s in sm["summary"]}

# ---- 主 tab「对比」：line_chart（10 条净值线，转收益率 %）----
series = []
colors = {"A": "#f23645", "B": "#0891b2"}  # A 红、B 蓝
for sym, name in SYMBOLS.items():
    for v, vlabel in [("A", "旧档v3.3"), ("B", "新档v3.4")]:
        col = f"{sym}_{v}"
        pts = [{"date": r["date"], "value": round((r[col] / INITIAL - 1) * 100, 2)}
               for _, r in eq.iterrows()]
        series.append({"name": f"{name}·{vlabel}", "points": pts, "stroke": colors[v]})

# ---- metric_table：每标的 A/B 对比 ----
rows = []
for sym, name in SYMBOLS.items():
    a = summaries[f"{sym}_A"]
    b = summaries[f"{sym}_B"]
    rows.append({"metric": f"{name}", "values": [{"main": f"{a['total_return_pct']}%"},
                                                 {"main": f"{b['total_return_pct']}%"}]})
metric_rows = [
    {"metric": "总收益", "values": [{"main": "旧档 v3.3"}, {"main": "新档 v3.4"}]},
] + rows
mdd_rows = []
for sym, name in SYMBOLS.items():
    a = summaries[f"{sym}_A"]
    b = summaries[f"{sym}_B"]
    mdd_rows.append({"metric": f"{name}", "values": [{"main": f"{a['max_drawdown_pct']}%"},
                                                     {"main": f"{b['max_drawdown_pct']}%"}]})

# ---- 每标的一个 tab：overview_chart（A/B 净值 overlay）+ trades_table ----
modules = []
tabs = [{"id": "compare", "label": "对比总览"}]

# 主 tab
modules.append({
    "type": "line_chart", "tab": "compare", "title": "净值对比（5 标的 × 2 档位，收益率 %）",
    "subtitle": "区间 2021-09 ~ 2026-08 · 初始 ¥100,000 · 前复权日线",
    "series": series,
})
modules.append({
    "type": "metric_table", "tab": "compare", "title": "总收益对比",
    "columns": ["标的", "旧档 v3.3", "新档 v3.4"], "rows": metric_rows,
})
modules.append({
    "type": "metric_table", "tab": "compare", "title": "最大回撤对比",
    "columns": ["标的", "旧档 v3.3", "新档 v3.4"], "rows": mdd_rows,
})
modules.append({
    "type": "text", "tab": "compare", "title": "核心结论",
    "text": (
        "1. **新档在震荡/下跌段更优**：证券新档 +3.81% vs 旧档 +1.99%（更早止盈保住利润）；黄金新档 MDD -14.93% 优于旧档 -17.99%。\n"
        "2. **新档在趋势市踏空**：纳指新档 2024-03 奔跑仓破 20 日线出清（+26.9%）后踏空主升浪，最终 +18.7% vs 旧档 +48.5%。\n"
        "3. **奔跑仓 20 日线出场过敏感**：趋势中的正常回调即触发清仓，25% 奔跑仓吃到的主升段有限。\n"
        "4. 旧档「卖 1/3 后死拿」在单边上涨中占优，但无风控、回撤暴露大。"
    ),
})
modules.append({
    "type": "text", "tab": "compare", "title": "关键假设与局限",
    "text": (
        "- 买入：区间首日开盘全额买入；止盈：收盘确认档位、次日开盘卖出（无前视偏差）\n"
        "- 每档按**原始建仓份额**的固定比例卖出（旧档 1/3，新档 25%）；A 股 ETF 100 份手数、T+1\n"
        "- 费用：佣金万三双边（ETF 免印花税）；期末剩余持仓按收盘价强制平仓\n"
        "- 局限：日线无法还原日内先后顺序；回测区间 2021-2026 前跌后涨，对「更早止盈」策略不利，存在区间依赖；5 个标的均为 ETF，未覆盖个股。"
    ),
})

# 每标的 detail tab
for sym, name in SYMBOLS.items():
    tid = sym
    tabs.append({"id": tid, "label": name})
    # overview_chart：A/B overlay
    pts_a = [{"date": r["date"], "equity": r[f"{sym}_A"], "drawdown_abs": 0.0, "pnl": 0.0}
             for _, r in eq.iterrows()]
    pts_b = [{"date": r["date"], "equity": r[f"{sym}_B"], "drawdown_abs": 0.0, "pnl": 0.0}
             for _, r in eq.iterrows()]
    modules.append({
        "type": "overview_chart", "tab": tid, "title": f"{name} · 两档位净值对比",
        "stats": [
            {"label": "旧档总收益", "value": f"{summaries[f'{sym}_A']['total_return_pct']}%",
             "raw": summaries[f"{sym}_A"]["total_return_pct"]},
            {"label": "新档总收益", "value": f"{summaries[f'{sym}_B']['total_return_pct']}%",
             "raw": summaries[f"{sym}_B"]["total_return_pct"]},
            {"label": "交易笔数", "value": f"{summaries[f'{sym}_A']['total_trades']} / {summaries[f'{sym}_B']['total_trades']}"},
        ],
        "points": pts_b,
        "series_key": "equity",
        "overlay_series": [{"name": f"{name}·旧档v3.3", "points": pts_a, "stroke": "#f23645"}],
        "toggles": [{"id": "equity", "label": "净值", "checked": True}],
        "modes": [{"id": "absolute", "label": "绝对", "active": True}],
    })
    sym_trades = tr[tr["symbol"] == sym].copy()
    sym_trades["label"] = sym_trades["strategy"] + "·" + sym_trades["label"]
    modules.append({
        "type": "trades_table", "tab": tid, "title": f"{name} · 交易明细",
        "rows": sym_trades.to_dict(orient="records"),
        "columns": [
            {"key": "exit_date", "label": "卖出日", "format": "text"},
            {"key": "label", "label": "动作", "format": "pill"},
            {"key": "size", "label": "份额", "format": "number"},
            {"key": "entry_price", "label": "成本", "format": "number"},
            {"key": "exit_price", "label": "卖价", "format": "number"},
            {"key": "pnl_pct", "label": "收益率", "format": "pct"},
            {"key": "holding_bars", "label": "持有(交易日)", "format": "number"},
        ],
    })

report_data = {
    "ui": {
        "subtitle": "Anchor 止盈档位 v3.3 vs v3.4 · 5 标的 · 2021-09 ~ 2026-08",
        "active_tab": "compare",
        "tabs": tabs,
        "language": "zh",
        "color_scheme": "eastern",
    },
    "modules": modules,
    "disclaimer": "⚠️ 以上内容基于公开信息整理生成，仅供参考，不构成任何投资建议或个股推荐。投资有风险，决策需谨慎。",
}

render_dashboard(report_data, output_path=os.path.join(OUT, "index.html"), template_path=TEMPLATE)
print(f"✅ 仪表盘已生成: {os.path.join(OUT, 'index.html')}")
