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


# ============================================================================
# 🔴 台账派生重建 —— 修复「9 月 0 条」（2026-09-30）
# ============================================================================
# 病灶（2026-09-30 排查）：本台账**唯一的写入路径是手工命令** `--log-rule`
#   （以及 `--log-ddx/--log-signal/--log-swing/--log-timing`），
#   而 `noise_audit.py` **不在 `sync_all.py` 链路中、也未被任何脚本调用**
#   ⇒ 记录**全靠人记得跑**。事实：台账最后一条停在 **2026-08-17**，
#   9 月整月 **0 条** —— 而 9 月实际发生了月额度超限（买入 6/2、卖出 3/2）、
#   A3 摊平命中 2 次、A2 追红日等多次规则命中。
#
# 修法（**不加重手工负担，改为从既有真源派生**）：
#   系统里这些命中的**检测逻辑早就存在且已在跑**，只是结果散落在各处 ——
#     · 月额度违规 → `decision_log.json` 的 `tags` 含 `违规·月额度`（单 152 自动打标）
#     · 止损执行   → `decision_log.json` 中 `type=止损` 且 `verdict` 含「执行」
#     · A2 追红日  → `portfolio_data.json` watchlist 条目的 `today_meta.a2_hit`
#   ⇒ 本模块**只做归集**，⛔ 不新造判定、⛔ 不臆造条目。
#
# 🔴 幂等键 ＝ **(date, rule, note 前 40 字)**：
#   只按 `rule` 去重 ⇒ 跨日同类命中会被吞（如 9/14 与 9/28 两笔通利加仓）；
#   只按 `date` 去重 ⇒ 同日多条不同规则会被吞。故须三键合一（见测试 T3）。

def _paths():
    """惰性取真源路径（⛔ 不在模块顶部硬编码，便于测试注入）。"""
    import paths
    return paths.DATA_PATH, paths.ANCHOR / "06-dashboard" / "decision_log.json"


def _quota_tag() -> str:
    """月额度违规 tag 的**单一真源** ＝ `decision_log.QUOTA_TAG`（⛔ 本模块不得自写字面量）。"""
    import decision_log
    return decision_log.QUOTA_TAG


# 🔴 tag → 规则名的映射（**按系统实际在用的 tag 词表**，2026-09-30 实测归纳）。
#    ⛔ 只用 `违规·月额度` 会漏掉 9 月全部命中 —— 因为该 tag 自 2026-09-24 才生效
#   且**不溯及既往**，而 9/14、9/28 两笔额度违规是**补录**（补录不打标）。
#    ⇒ 单 152 的自动打标**不能回溯修复 9 月**，故本表按**真实存在的 tag** 归纳。
TAG_TO_RULE: dict[str, tuple[str, str]] = {
    "违规·月额度": ("月额度·买入维超限", "missed"),
    "月额度满": ("月额度（已达上限·据此不买）", "protected"),
    "超E1上限": ("E1 单只卫星上限超限", "missed"),
    "超压舱石上限": ("压舱石单只上限超限", "missed"),
    "超限": ("超限（E1／压舱石等）", "missed"),
    "执行违规": ("执行违规（纪）", "missed"),
    "红日": ("A2 追红日（禁买）", "protected"),
    "B5": ("B5 观察仓破位", "protected"),
    "破位": ("破位（技术）", "protected"),
    "清仓": ("清仓", "protected"),
    "节前": ("§4.5 节前闸门", "protected"),
    "压舱石闸门": ("§4.2.1 压舱石闸门", "protected"),
    "止损观察": ("止损观察（未触发）", "neutral"),
}


def derive_rule_hits(year: int, month: int, data: dict | None = None,
                     log: list | None = None) -> list[dict]:
    """从既有真源**派生**该月的规则命中（只读，⛔ 不写盘）。

    返回与 `log_rule` 同构的记录列表；`note` 均带 `[派生]` 前缀以区别于手工条目。
    数据不可读时**返回一条显式声张记录**，⛔ 不得静默当「本月无命中」。
    """
    import json as _json
    dpath, lpath = _paths()
    pref = f"{year:04d}-{month:02d}-"
    out: list[dict] = []

    if data is None:
        try:
            data = _json.loads(Path(dpath).read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            return [{"date": pref + "01", "rule": "⚠️派生失败", "outcome": "neutral", "amount": 0,
                     "note": f"[派生] 档案不可读：{type(e).__name__}"}]
    if log is None:
        try:
            log = _json.loads(Path(lpath).read_text(encoding="utf-8")).get("decisions", [])
        except Exception:  # noqa: BLE001
            log = []

    for r in log:
        if not str(r.get("date", "")).startswith(pref):
            continue
        tags = list(r.get("tags") or [])
        # ① 按 tag 映射（同一 tag 只记一条；同日多 tag ⇒ 多行，⛔ 不合并）
        for tg in tags:
            if tg in TAG_TO_RULE:
                rule, outcome = TAG_TO_RULE[tg]
                out.append({
                    "date": r["date"], "rule": rule, "outcome": outcome,
                    "amount": -float(r.get("amount") or 0) if outcome == "missed" else 0.0,
                    "note": f"[派生·tag:{tg}] #{r.get('id')} {r.get('type')} {r.get('fund')}｜{str(r.get('verdict'))[:30]}",
                })
        # ② 止损执行（type 维，非 tag）：即便无 tag 也必须记
        if str(r.get("type", "")) == "止损" and "执行" in str(r.get("verdict", "")):
            out.append({
                "date": r["date"], "rule": f"止损执行（{r.get('fund')}）", "outcome": "protected",
                "amount": 0.0,
                "note": f"[派生·type] #{r.get('id')} {r.get('verdict')}｜{str(r.get('rationale'))[:50]}",
            })

    # ③ A2 追红日（watchlist 条目的 today_meta.a2_hit；⚠️ 该字段只保留最新一天 ⇒ 历史不可回溯）
    for w in (data.get("watchlist") or []):
        if not isinstance(w, dict):
            continue
        tm = w.get("today_meta") or {}
        if tm.get("a2_hit") is True:
            d0 = str(tm.get("computed_at") or "")[:10]
            if d0.startswith(pref):
                out.append({"date": d0, "rule": "A2 追红日（watchlist）", "outcome": "protected",
                            "amount": 0.0,
                            "note": f"[派生·watchlist] {w.get('sector') or w.get('name')}：{str(tm.get('a2_detail'))[:50]}"})
    return out


def rebuild_rule_hits(year: int, month: int, dry_run: bool = False) -> dict:
    """把派生结果**幂等合并**进台账（⛔ 不删既有手工条目）。"""
    existing = load_json(RULE_FILE)

    def key(x):
        return (str(x.get("date", "")), str(x.get("rule", "")), str(x.get("note", ""))[:40])

    seen = {key(x) for x in existing}
    added = [r for r in derive_rule_hits(year, month) if key(r) not in seen]
    if added and not dry_run:
        existing.extend(added)
        existing.sort(key=lambda x: str(x.get("date", "")))
        save_json(RULE_FILE, existing)
    return {"month": f"{year:04d}-{month:02d}", "existing": len(seen), "added": len(added),
            "total": len(existing) + (len(added) if dry_run else 0), "records": added}


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

    if "--rebuild-hits" in sys.argv:
        idx = sys.argv.index("--rebuild-hits")
        arg = sys.argv[idx + 1] if len(sys.argv) > idx + 1 and "-" in sys.argv[idx + 1] else ""
        if arg:
            yy, mm = arg.split("-")[:2]
            y, m = int(yy), int(mm)
        else:
            now = datetime.now()
            y, m = now.year, now.month
        dry = "--dry-run" in sys.argv
        r = rebuild_rule_hits(y, m, dry_run=dry)
        print(f"规则命中台账派生重建 · {r['month']}{'（dry-run）' if dry else ''}")
        print(f"  既有条目 {r['existing']} ｜ 新增 {r['added']} ｜ 合计 {r['total']}")
        for x in r["records"]:
            print(f"    + {x['date']} {x['rule']} → {x['outcome']}｜{x['note'][:70]}")
        if not r["records"]:
            print("    （无新增；⛔ 若本月确有命中却为 0，请检查真源是否含对应标记）")
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
