#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Anchor 数据新鲜度看门狗（freshness_watchdog.py，B3）

目的：防止在陈旧数据上生成建议/看板——"宁可提示数据旧，也不把旧数据当今天讲"。

口径（工作日近似，不依赖交易所日历，法定节假日需人工判断）：
  - 以 portfolio_data.json 的 update_date 为数据日期，计算到今天的「交易日滞后」
  - lag<=1 → fresh（T 日收盘数据，T 晚 / T+1 白天看都正常）
  - lag==2 → warn（缺 1 个交易日）
  - lag>=3 → stale（缺 ≥2 个交易日，不得据此推建议）
  - 日期缺失/无法解析 → unknown（按异常处理）

用法：
  python freshness_watchdog.py                 # 检查桌面权威 JSON，打印报告（stale/unknown → rc=1）
  python freshness_watchdog.py --json <path>   # 指定 JSON
被其它脚本复用：
  from freshness_watchdog import check_freshness, trading_lag
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

WARN_LAG = 2     # lag==2 警告
STALE_LAG = 3    # lag>=3 陈旧


def parse_date(s):
    """宽容解析 YYYY-MM-DD / YYYY/MM/D（取前 10 位），失败返回 None。"""
    if not s:
        return None
    s = str(s).strip().replace("/", "-")[:10]
    for fmt in ("%Y-%m-%d",):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # 兼容 2026-8-3 这类不补零
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def trading_lag(update_str, today=None):
    """数据日期到 today 的交易日滞后（工作日近似，不含起点当天，含今天）。无法解析返回 None。"""
    ud = parse_date(update_str)
    td = today or date.today()
    if not ud:
        return None
    if ud >= td:
        return 0
    lag = 0
    cur = ud + timedelta(days=1)
    while cur <= td:
        if cur.weekday() < 5:  # 周一=0 … 周五=4
            lag += 1
        cur += timedelta(days=1)
    return lag


def level_of(lag):
    if lag is None:
        return "unknown"
    if lag >= STALE_LAG:
        return "stale"
    if lag >= WARN_LAG:
        return "warn"
    return "fresh"


def check_freshness(data=None, today=None):
    """返回 dict：{level, update_date, today, lag, calendar_days, message}。
    data 可传入已加载的 portfolio_data dict；不传则读桌面权威 JSON。"""
    own_load = data is None
    if own_load:
        try:
            data = json.loads(paths.DATA_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            return {"level": "unknown", "update_date": None, "today": str(today or date.today()),
                    "lag": None, "calendar_days": None, "message": f"无法读取/解析 {paths.DATA_PATH.name}: {e}"}
    upd = data.get("update_date") or data.get("update_time")
    ud = parse_date(upd)
    td = today or date.today()
    lag = trading_lag(upd, td)
    cal_days = (td - ud).days if ud else None
    level = level_of(lag)

    if level == "fresh":
        msg = f"数据新鲜（截至 {upd}，滞后 {lag} 个交易日）"
    elif level == "warn":
        msg = f"数据滞后 {lag} 个交易日（截至 {upd}）——请尽快更新 App 明细并跑 sync_all"
    elif level == "stale":
        msg = (f"数据已陈旧：截至 {upd}，滞后 {lag} 个交易日 / 自然日 {cal_days} 天——"
               f"不得据此生成当日建议，请先更新数据")
    else:
        msg = "无法判定数据日期（update_date 缺失或格式异常），请检查 portfolio_data.json"
    return {"level": level, "update_date": str(upd) if upd else None,
            "today": str(td), "lag": lag, "calendar_days": cal_days, "message": msg}


def banner_html(data=None):
    """供 gen_daily_hub 嵌入的页顶陈旧横幅 HTML；fresh/unknown 返回空串。"""
    r = check_freshness(data)
    if r["level"] in ("fresh", "unknown"):
        return ""
    color = "#b45309" if r["level"] == "warn" else "#b91c1c"
    bg = "#fef3c7" if r["level"] == "warn" else "#fee2e2"
    return (
        '<div style="background:{bg};color:{c};border:1px solid {c};border-radius:8px;'
        'padding:10px 14px;margin:10px 0;font-size:14px;font-weight:600;">'
        '⚠️ 数据新鲜度：{msg}（今日 {today}）</div>'
    ).format(bg=bg, c=color, msg=r["message"], today=r["today"])


def main():
    ap = argparse.ArgumentParser(description="Anchor 数据新鲜度看门狗")
    ap.add_argument("--json", default=None, help="指定 portfolio_data.json 路径")
    args = ap.parse_args()
    if args.json:
        with open(args.json, encoding="utf-8") as f:
            data = json.load(f)
        r = check_freshness(data)
    else:
        r = check_freshness()
    icon = {"fresh": "✅", "warn": "🟡", "stale": "🔴", "unknown": "❓"}.get(r["level"], "")
    print(f"{icon} [{r['level']}] {r['message']}")
    # stale / unknown → 非 0，便于 sync_all / 计划任务感知
    return 1 if r["level"] in ("stale", "unknown") else 0


if __name__ == "__main__":
    sys.exit(main())
