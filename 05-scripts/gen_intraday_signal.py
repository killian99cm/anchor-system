#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_intraday_signal.py — Anchor 盘中规则信号导出器（v1.0, 2026-08-26）

用途：供 WorkBuddy「工作日 14:30 盘中信号」自动化读取。
行为：读桌面 portfolio_data.json -> data_processor.process_all() -> 打印精简信号 JSON。
特性：不依赖任何外部行情 API；失败时退出码非 0 并打印错误信息。

用法: python gen_intraday_signal.py [--pretty]
"""
import json
import sys
import os
from datetime import datetime

# Windows 控制台默认 GBK，强制 stdout 走 UTF-8，避免 ¥ 等字符 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import paths
    from data_processor import process_all
except ImportError as exc:
    print(json.dumps({"error": f"模块导入失败: {exc}", "hint": "请确认在 05-scripts 目录下运行"}, ensure_ascii=False))
    sys.exit(1)

try:
    with open(paths.DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
except FileNotFoundError:
    print(json.dumps({"error": f"数据文件不存在: {paths.DATA_PATH}"}, ensure_ascii=False))
    sys.exit(1)
except json.JSONDecodeError as exc:
    print(json.dumps({"error": f"数据文件 JSON 解析失败: {exc}"}, ensure_ascii=False))
    sys.exit(1)

try:
    embed = process_all(data)
except Exception as exc:
    print(json.dumps({"error": f"规则引擎处理失败: {exc}"}, ensure_ascii=False))
    sys.exit(1)

# ---- 信号分级映射（沿用看板口径：rr=红 / ra=黄 / rg=绿）----
LV_MAP = {"rr": "red", "ra": "amber", "rg": "green"}


def pick_signals(rules):
    """rules 列表 -> 信号清单（含等级与文案）"""
    out = []
    for r in rules or []:
        out.append({"level": LV_MAP.get(r.get("lv", ""), "amber"), "text": r.get("t", "")})
    return out


signal = {
    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "data_update_date": embed.get("source_update_date") or data.get("update_date") or data.get("update_time", ""),
    "total_assets": embed.get("total"),
    "total_pnl": embed.get("totalPnl"),
    "layers": [
        {"label": l.get("label"), "pct": l.get("pct"), "target": l.get("target"), "mv": l.get("mv"), "count": l.get("count")}
        for l in (embed.get("layers") or [])
    ],
    "month_ops": embed.get("ops_state"),
    "drawdown": embed.get("drawdown_state"),
    "freeze": embed.get("freeze_state"),
    "portfolio_state": embed.get("portfolio_state"),
    "risk_state": embed.get("risk_state"),
    "signals": pick_signals(embed.get("rules")),
    "risks": embed.get("risks"),
    "today": embed.get("today"),
    "pending_actions_total": (embed.get("today") or {}).get("pa_total"),
    "opportunity_scores": embed.get("opportunity_scores"),
    "clock_state": embed.get("clock_state"),
    "warnings": embed.get("_warnings", []),
}

if "--pretty" in sys.argv:
    print(json.dumps(signal, ensure_ascii=False, indent=2))
else:
    print(json.dumps(signal, ensure_ascii=False))
sys.exit(0)
