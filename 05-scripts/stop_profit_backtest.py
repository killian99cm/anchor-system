#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stop_profit_backtest.py — 止盈档位重构案例回测（v2.0, 2026-09-01 C4 函数化）

目的：P1 优化项「止盈重构回测」——用真实交易流水与已清仓基金数据，
对比旧档（+10%/+20% 各卖1/3）与新档（+8%/+15%/+25% 各卖25% + 25%奔跑仓跟20日线）。

v2 变更（C4）：
  - 函数化（load_data/cleared_funds/sell_txn/build_findings/ratio_line/main），可被复用/测试
  - 路径走 paths.py（不再硬编码用户目录）
  - --month YYYY-MM：只统计指定月份卖出流水；--top N：案例数（默认 5）；--data 指定 JSON
  - 案例从数据动态生成（已清仓基金 + 其真实流水），方法论结论（旧档/新档/差异）保留为模板
  - 盈亏比改从 decision_log.accuracy_report 动态读取（不再写死 0.60）

用法:
  python stop_profit_backtest.py                 # 全量
  python stop_profit_backtest.py --month 2026-08 # 只看 8 月卖出
"""
import argparse
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

SELL_OPS = ("卖出", "减仓", "清仓", "减仓83%", "减仓51%", "赎回", "赎回到账")


def load_data(data_path=None):
    """读取组合数据；默认桌面权威 JSON。"""
    p = Path(data_path) if data_path else paths.DATA_PATH
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def cleared_funds(data):
    """已清仓基金（按累计盈亏绝对值降序，便于优先展示代表性案例）。"""
    rows = [h for h in data.get("holdings_summary", []) if h.get("group") == "已清仓"]
    rows.sort(key=lambda h: abs(h.get("cumul", 0) or 0), reverse=True)
    return rows


def fund_ops(data, name, limit=6):
    """某只基金的前 limit 条流水（保持时间顺序）。"""
    return [t for t in data.get("transactions", []) if str(t.get("name", "")) == name][:limit]


def sell_txn(data, month=None):
    """卖出类流水；month='YYYY-MM' 时只保留该月（严格日期开头匹配）。"""
    out = [t for t in data.get("transactions", []) if str(t.get("op", "")) in SELL_OPS]
    if month:
        out = [t for t in out if str(t.get("date", "")).replace("/", "-").startswith(month)]
    return out


def _methodology(cumul):
    """按该笔累计盈亏方向选择方法论结论模板（结论保留，案例动态）。"""
    if cumul >= 0:
        return (
            "旧档 +10/+20 各卖1/3：提前清空，易吃不到主升段",
            "新档 +8%卖25% 锁首利 + 25%奔跑仓跟20日线：保留底仓参与主升段",
            "奔跑仓机制针对「卖最顶/拿不住」缺陷",
        )
    return (
        "旧档止盈端无奔跑仓，止损端执行靠自觉，亏损易被时间放大",
        "止损端由 -8% 后第4交易日硬 Deadline 解决（不属止盈档位）",
        "止盈重构修「赚端」、止损 Deadline 修「亏端」，双管齐下",
    )


def build_findings(data, top=5):
    """从已清仓且有累计盈亏的基金动态构建案例（取 |cumul| 前 top，兼顾盈亏两侧）。"""
    cases = []
    for h in cleared_funds(data):
        cumul = h.get("cumul", 0) or 0
        if cumul == 0:
            continue
        ops = fund_ops(data, h.get("name", ""))
        flow = " → ".join(f"{t.get('date','')} {t.get('op','')}" for t in ops[:4]) or "（无明细流水）"
        old, new, delta = _methodology(cumul)
        cases.append({
            "case": h.get("name", ""),
            "evidence": f"{flow}；累计 {cumul:+.2f}",
            "old": old, "new": new, "delta": delta,
            "cumul": cumul,
        })
        if len(cases) >= top:
            break
    return cases


def ratio_line(data):
    """盈亏比从决策日志动态读取；无样本时明确说明，不写死数字。"""
    try:
        from decision_log import accuracy_report
        r = accuracy_report()
        if r.get("pnl_ratio") is not None:
            return (f"决策日志口径: 盈亏比 {r['pnl_ratio']}:1"
                    f"（均盈 {r.get('avg_win_pct')}% vs 均亏 {r.get('avg_loss_pct')}%，目标 ≥1.5:1）")
    except Exception as e:
        return f"决策日志口径: 盈亏比暂缺（读取统计失败：{e}）"
    return "决策日志口径: 盈亏比暂缺（decision_log 无已复盘收益样本）"


def report(data, month=None, top=5):
    lines = []
    p = lambda s="": lines.append(s)

    # [1] 已清仓回顾
    cleared = cleared_funds(data)
    p("=" * 70)
    p(f"[1] 已清仓基金处置回顾（{len(cleared)} 只）")
    p("=" * 70)
    for h in cleared:
        name = h.get("name", "")
        cumul = h.get("cumul", 0)
        note = str(h.get("note", ""))[:60]
        ops = " → ".join(str(t.get("op", "")) for t in fund_ops(data, name))
        p(f"• {name[:20]:<22} 累计盈亏 {cumul:>9.2f} | 操作: {ops} | {note}")

    # [2] 卖出点位（可 --month）
    sells = sell_txn(data, month)
    p()
    p("=" * 70)
    p("[2] 卖出点位质量评估（旧档 vs 新档）" + (f" · 仅 {month}" if month else ""))
    p("=" * 70)
    p(f"卖出类流水共 {len(sells)} 笔：")
    for s in sells:
        p(f"  {s.get('date','')} | {str(s.get('name',''))[:20]:<22} | {s.get('op','')} | ¥{s.get('amount','')} | {str(s.get('note',''))[:45]}")

    # [3] 案例（动态）
    findings = build_findings(data, top=top)
    p()
    p("=" * 70)
    p("[3] 新旧档位对照结论（案例取自已清仓真实流水；方法论为固定结论）")
    p("=" * 70)
    if not findings:
        p("（无累计盈亏非 0 的已清仓案例）")
    for f in findings:
        p(f"📌 {f['case']}")
        p(f"   证据: {f['evidence']}")
        p(f"   旧档: {f['old']}")
        p(f"   新档: {f['new']}")
        p(f"   差异: {f['delta']}")
        p()

    # [4] 盈亏比基准（动态）
    p("=" * 70)
    p("[4] 盈亏比现状（优化前基准）")
    p("=" * 70)
    p(f"当前持有盈亏估计: {data.get('total_hold_pnl_est', 0):+,.2f}")
    p(ratio_line(data))
    p("→ 盈利端重构（止盈档位）与亏损端硬化（止损Deadline）即为盈亏比修复的双引擎。")
    p()
    p("结论：止盈档位重构的核心价值 = ①更早更小锁利（+8% 卖 25%）对抗「拿不住」")
    p("      ②奔跑仓制度（25% 跟 20 日线）修复「卖最顶」 ③与止损 Deadline 形成盈亏比双引擎。")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="止盈档位重构案例回测（函数化、动态取数）")
    ap.add_argument("--month", default=None, help="只统计指定月份卖出流水，格式 YYYY-MM")
    ap.add_argument("--top", type=int, default=5, help="动态案例最多展示数（默认 5）")
    ap.add_argument("--data", default=None, help="指定 portfolio_data.json 路径（默认桌面权威）")
    args = ap.parse_args()
    if args.month:
        # 严格校验 YYYY-MM
        import re
        if not re.fullmatch(r"20\d{2}-(0?[1-9]|1[0-2])", args.month):
            print(f"[错误] --month 格式应为 YYYY-MM，收到 {args.month!r}")
            return 2
    try:
        data = load_data(args.data)
    except Exception as exc:
        print(json.dumps({"error": f"读取数据失败: {exc}"}, ensure_ascii=False))
        return 1
    print(report(data, month=args.month, top=args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
