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

    # DDX 准确率
    ddx_signals = [s for s in signals if "DDX" in s.get("name", "")]
    false_count = sum(1 for s in ddx_signals if s["action"] == "false_alarm")
    trigger_count = sum(1 for s in ddx_signals if s["action"] == "triggered")
    ddx_accuracy = (trigger_count - false_count) / max(trigger_count, 1)

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
    """每周噪声评分卡"""
    ddx = load_json(DDX_FILE)
    signals = load_json(SIGNAL_FILE)
    near_misses = load_json(NEAR_MISS_FILE)

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
    ddx_accuracy = (trigger_count - false_count) / max(trigger_count, 1)

    # 虚惊指数
    week_near_misses = [n for n in near_misses if n["date"] >= week_start]
    near_miss_index = len(week_near_misses) / max(trading_days, 1)

    # 噪声综合评分
    accuracy_score = ddx_accuracy * 30
    near_miss_score = max(0, (1 - near_miss_index)) * 25
    # 默认给满分，实际需要盘中振幅数据（从MX API获取较复杂，暂用默认值）
    swing_score = 15  # 默认中等
    timing_score = 20  # 默认中等

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
            "intraday_swing": {"value": "待采集", "score": swing_score, "weight": 20},
            "timing_bias": {"value": "待评估", "score": timing_score, "weight": 25},
        },
        "total_score": round(total_score),
        "noise_level": level,
        "false_alarms": false_count,
        "near_misses": len(week_near_misses),
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

    if "--weekly" in sys.argv:
        result = audit_weekly()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        result = audit_daily()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
