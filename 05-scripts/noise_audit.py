#!/usr/bin/env python3
"""
Anchor 噪声审计脚本 v1.0

读取噪声日志（noise/ddx_daily.json + noise/signal_log.json + noise/near_miss.json），
输出每日噪声快照 + 每周噪声评分卡，供复盘报告引用。

用法: python noise_audit.py           → 打印每日快照
      python noise_audit.py --weekly  → 打印本周评分卡
      python noise_audit.py --log-ddx "2026-08-10" [方向] [值]   → 记录DDX
      python noise_audit.py --log-signal "信号名" [触发/消失/假信号]  → 记录信号
      python noise_audit.py --log-near-miss "描述"                 → 记录虚惊

数据目录: Anchor/06-dashboard/noise/
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NOISE_DIR = Path(__file__).parent.parent / "06-dashboard" / "noise"
NOISE_DIR.mkdir(parents=True, exist_ok=True)

DDX_FILE = NOISE_DIR / "ddx_daily.json"
SIGNAL_FILE = NOISE_DIR / "signal_log.json"
NEAR_MISS_FILE = NOISE_DIR / "near_miss.json"
SWING_FILE = NOISE_DIR / "swing_daily.json"       # 盘中振幅（高/低/收盘涨跌）→ 振幅比
TIMING_FILE = NOISE_DIR / "timing_daily.json"     # 操作时机偏差（补仓后次日涨跌）
RULE_FILE = NOISE_DIR / "rule_hits.json"          # 全规则命中台账（触发/保护/误伤）


def load_json(path: Path) -> list:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_json(path: Path, data: list) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 日志记录 ----------

def log_ddx(date: str, direction: str, value: str) -> None:
    """记录每日DDX状态。direction: positive/negative/neutral"""
    data = load_json(DDX_FILE)
    # 去重同一天
    data = [d for d in data if d.get("date") != date]
    data.append({"date": date, "direction": direction, "value": value})
    data.sort(key=lambda x: x["date"])
    save_json(DDX_FILE, data)
    print(f"[DDX] {date} → {direction} ({value})")


def log_signal(name: str, action: str) -> None:
    """记录信号事件。action: triggered/dismissed/false_alarm"""
    data = load_json(SIGNAL_FILE)
    data.append({
        "name": name,
        "action": action,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
    })
    save_json(SIGNAL_FILE, data)
    print(f"[信号] {name} → {action}")


def log_near_miss(description: str) -> None:
    """记录虚惊事件"""
    data = load_json(NEAR_MISS_FILE)
    data.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "description": description,
    })
    save_json(NEAR_MISS_FILE, data)
    print(f"[虚惊] {description[:60]}")


def _pct(val: str) -> float:
    """解析百分比字符串（支持 '+1.42%' / '-0.5' / '1.29'）"""
    try:
        return float(str(val).rstrip("%").replace("+", ""))
    except (ValueError, TypeError):
        return 0.0


def log_swing(date: str, sector: str, high: str, low: str, close: str) -> None:
    """记录盘中振幅：high/low/close 为涨跌幅百分比（如 +1.5 / -2.1 / +0.3）。
    振幅比 = |high - low| / |close|（框架 2.3：>5x=高噪声，>10x=极高噪声）"""
    h, l, c = _pct(high), _pct(low), _pct(close)
    amp = abs(h - l)
    ratio = amp / abs(c) if c != 0 else 0.0
    data = load_json(SWING_FILE)
    data = [d for d in data if not (d.get("date") == date and d.get("sector") == sector)]
    data.append({
        "date": date, "sector": sector,
        "high": h, "low": l, "close": c,
        "amplitude": round(amp, 2), "ratio": round(ratio, 2),
    })
    data.sort(key=lambda x: x["date"])
    save_json(SWING_FILE, data)
    print(f"[振幅] {date} {sector} high={h}% low={l}% close={c}% → 振幅比 {ratio:.2f}x")


def log_timing(date: str, op: str, next_day_pct: str) -> None:
    """记录操作时机偏差：操作（如补仓）后次日涨跌幅（%）。
    次日大跌 = 时机偏差大 = 噪声；用于框架 2.4 操作时机偏差指标"""
    nxt = _pct(next_day_pct)
    data = load_json(TIMING_FILE)
    data.append({"date": date, "op": op, "next_day_pct": round(nxt, 2)})
    data.sort(key=lambda x: x["date"])
    save_json(TIMING_FILE, data)
    print(f"[时机] {date} {op} → 次日 {nxt:+.2f}%")


def log_rule(rule: str, outcome: str, amount: float = 0, note: str = "") -> None:
    """记录规则命中台账。outcome: protected(保护了钱)/missed(误伤或漏触发)/neutral(无影响)
    amount: 保护金额（正数）或误伤金额（负数），单位 ¥"""
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        amount = 0.0
    data = load_json(RULE_FILE)
    data.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "rule": rule,
        "outcome": outcome,
        "amount": round(amount, 2),
        "note": note[:120],
    })
    save_json(RULE_FILE, data)
    print(f"[规则] {rule} → {outcome}（¥{amount:+,.0f}）{note}")


# ---------- 审计分析 ----------

def audit_daily() -> dict:
    """每日噪声快照"""
    ddx = load_json(DDX_FILE)
    signals = load_json(SIGNAL_FILE)
    near_misses = load_json(NEAR_MISS_FILE)

    today = datetime.now().strftime("%Y-%m-%d")

    # DDX 连续方向
    recent_ddx = [d for d in ddx if d["date"] >= (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")]
    ddx_streak = 0
    last_dir = None
    for d in reversed(recent_ddx):
        if d["direction"] == "positive":
            if last_dir is None or last_dir == "positive":
                ddx_streak += 1
                last_dir = "positive"
            else:
                break
        else:
            break

    # DDX 准确率（8/17 审计：分母含假信号数并钳制到 [0,1]，防 0 触发时算出 -200%）
    # 8/17 补充：只统计近 30 天信号（与 weekly 语义一致，防历史累计失真）
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    ddx_signals = [s for s in signals if "DDX" in s.get("name", "") and s.get("date", "") >= cutoff]
    false_count = sum(1 for s in ddx_signals if s["action"] == "false_alarm")
    trigger_count = sum(1 for s in ddx_signals if s["action"] == "triggered")
    total_ddx = trigger_count + false_count
    ddx_accuracy = (trigger_count - false_count) / total_ddx if total_ddx else 1.0
    ddx_accuracy = max(0.0, min(1.0, ddx_accuracy))

    # 今日虚惊
    today_near_misses = [n for n in near_misses if n["date"] == today]

    # 今日信号事件
    today_signals = [s for s in signals if s["date"] == today]

    return {
        "date": today,
        "ddx": {
            "streak_days": ddx_streak,
            "last_direction": last_dir or "unknown",
            "accuracy": round(ddx_accuracy * 100),
            "total_triggers": trigger_count,
            "false_alarms": false_count,
        },
        "near_misses_today": len(today_near_misses),
        "near_misses_detail": [n["description"] for n in today_near_misses],
        "signal_events_today": len(today_signals),
        "signal_events_detail": [f"{s['name']}→{s['action']}" for s in today_signals],
    }


def audit_weekly() -> dict:
    """每周噪声评分卡（v1.1：振幅比/时机偏差改为真实数据 + 规则命中台账）"""
    ddx = load_json(DDX_FILE)
    signals = load_json(SIGNAL_FILE)
    near_misses = load_json(NEAR_MISS_FILE)
    swings = load_json(SWING_FILE)
    timings = load_json(TIMING_FILE)
    rules = load_json(RULE_FILE)

    now = datetime.now()
    monday = now - timedelta(days=now.weekday())
    week_start = monday.strftime("%Y-%m-%d")

    # 本周交易天数（近似，实际需排除周末）
    trading_days = min(5, (now - monday).days + 1)

    # DDX 准确率
    ddx_signals = [s for s in signals
                   if "DDX" in s.get("name", "") and s["date"] >= week_start]
    false_count = sum(1 for s in ddx_signals if s["action"] == "false_alarm")
    trigger_count = sum(1 for s in ddx_signals if s["action"] == "triggered")
    total_ddx = trigger_count + false_count
    ddx_accuracy = (trigger_count - false_count) / total_ddx if total_ddx else 1.0
    ddx_accuracy = max(0.0, min(1.0, ddx_accuracy))

    # 虚惊指数
    week_near_misses = [n for n in near_misses if n["date"] >= week_start]
    near_miss_index = len(week_near_misses) / max(trading_days, 1)

    # 盘中振幅比（真实数据）：>5x 高噪声，>10x 极高噪声
    week_swings = [s for s in swings if s["date"] >= week_start]
    avg_ratio = (sum(s["ratio"] for s in week_swings) / len(week_swings)) if week_swings else None
    if avg_ratio is None:
        swing_score, swing_val = 10, "无数据"  # 数据缺失给中性分并标注
    elif avg_ratio <= 2:
        swing_score, swing_val = 20, f"{avg_ratio:.1f}x"
    elif avg_ratio <= 5:
        swing_score, swing_val = 12, f"{avg_ratio:.1f}x"
    elif avg_ratio <= 10:
        swing_score, swing_val = 6, f"{avg_ratio:.1f}x"
    else:
        swing_score, swing_val = 0, f"{avg_ratio:.1f}x"

    # 操作时机偏差（真实数据）：只统计次日下跌幅度（买对了不罚，8/17 审计）
    week_timings = [t for t in timings if t["date"] >= week_start]
    bad_timings = [abs(t["next_day_pct"]) for t in week_timings if t["next_day_pct"] < 0]
    avg_timing = (sum(bad_timings) / len(bad_timings)) if bad_timings else (0.0 if week_timings else None)
    if avg_timing is None:
        timing_score, timing_val = 15, "无数据"
    elif avg_timing <= 1:
        timing_score, timing_val = 25, f"{avg_timing:.2f}%"
    elif avg_timing <= 2:
        timing_score, timing_val = 15, f"{avg_timing:.2f}%"
    elif avg_timing <= 3:
        timing_score, timing_val = 8, f"{avg_timing:.2f}%"
    else:
        timing_score, timing_val = 0, f"{avg_timing:.2f}%"

    # 规则命中台账（本周）
    week_rules = [x for x in rules if x["date"] >= week_start]
    rule_summary = {
        "triggered": len(week_rules),
        "protected": sum(1 for x in week_rules if x["outcome"] == "protected"),
        "missed": sum(1 for x in week_rules if x["outcome"] == "missed"),
        "protected_amount": round(sum(x["amount"] for x in week_rules if x["outcome"] == "protected" and x["amount"] > 0), 0),
        "missed_amount": round(sum(-x["amount"] for x in week_rules if x["outcome"] == "missed" and x["amount"] < 0), 0),
    }

    # 噪声综合评分
    accuracy_score = ddx_accuracy * 30
    near_miss_score = max(0, (1 - near_miss_index)) * 25

    total_score = accuracy_score + near_miss_score + swing_score + timing_score

    if total_score >= 80:
        level = "🟢 低噪声"
    elif total_score >= 50:
        level = "🟡 中噪声"
    else:
        level = "🔴 高噪声"

    return {
        "week": week_start,
        "trading_days": trading_days,
        "scores": {
            "ddx_accuracy": {"value": f"{round(ddx_accuracy * 100)}%", "score": round(accuracy_score), "weight": 30},
            "near_miss_index": {"value": f"{near_miss_index:.2f}", "score": round(near_miss_score), "weight": 25},
            "intraday_swing": {"value": swing_val, "score": round(swing_score), "weight": 20},
            "timing_bias": {"value": timing_val, "score": round(timing_score), "weight": 25},
        },
        "total_score": round(total_score),
        "noise_level": level,
        "false_alarms": false_count,
        "near_misses": len(week_near_misses),
        "rule_ledger": rule_summary,
    }


# ---------- 主入口 ----------

def main() -> int:
    if "--log-ddx" in sys.argv:
        idx = sys.argv.index("--log-ddx")
        date = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else datetime.now().strftime("%Y-%m-%d")
        direction = sys.argv[idx + 2] if len(sys.argv) > idx + 2 else "unknown"
        value = sys.argv[idx + 3] if len(sys.argv) > idx + 3 else ""
        log_ddx(date, direction, value)
        return 0

    if "--log-signal" in sys.argv:
        idx = sys.argv.index("--log-signal")
        name = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else "unknown"
        action = sys.argv[idx + 2] if len(sys.argv) > idx + 2 else "triggered"
        log_signal(name, action)
        return 0

    if "--log-near-miss" in sys.argv:
        idx = sys.argv.index("--log-near-miss")
        desc = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else "未描述"
        log_near_miss(desc)
        return 0

    if "--log-swing" in sys.argv:
        idx = sys.argv.index("--log-swing")
        date = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else datetime.now().strftime("%Y-%m-%d")
        sector = sys.argv[idx + 2] if len(sys.argv) > idx + 2 else "半导体"
        high = sys.argv[idx + 3] if len(sys.argv) > idx + 3 else "0"
        low = sys.argv[idx + 4] if len(sys.argv) > idx + 4 else "0"
        close = sys.argv[idx + 5] if len(sys.argv) > idx + 5 else "0"
        log_swing(date, sector, high, low, close)
        return 0

    if "--log-timing" in sys.argv:
        idx = sys.argv.index("--log-timing")
        date = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else datetime.now().strftime("%Y-%m-%d")
        op = sys.argv[idx + 2] if len(sys.argv) > idx + 2 else "操作"
        nxt = sys.argv[idx + 3] if len(sys.argv) > idx + 3 else "0"
        log_timing(date, op, nxt)
        return 0

    if "--log-rule" in sys.argv:
        idx = sys.argv.index("--log-rule")
        rule = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else "未命名规则"
        outcome = sys.argv[idx + 2] if len(sys.argv) > idx + 2 else "neutral"
        amount = sys.argv[idx + 3] if len(sys.argv) > idx + 3 else "0"
        note = sys.argv[idx + 4] if len(sys.argv) > idx + 4 else ""
        log_rule(rule, outcome, amount, note)
        return 0

    if "--weekly" in sys.argv:
        result = audit_weekly()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        result = audit_daily()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
