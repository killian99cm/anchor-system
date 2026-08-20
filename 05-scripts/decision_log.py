#!/usr/bin/env python3
"""
Anchor 决策日志 + 胜率统计 v1.0（8/20 确立）

核心目标（用户）：「在一次一次操作中吸取经验，提高胜率、收益率、准确率」。
机制：每次给操作建议 → 留痕（数据快照 + 判断 + 预期）→ 事后复盘（实际结果）
      → 统计准确率/胜率 → 校准规则。与 noise_audit（审计规则信号质量）互补，
      decision_log 记录的是「我的决策」本身。

用法:
  python decision_log.py --add <类型> <标的> <判定> [金额] [依据] [预期方向]
      # 例: python decision_log.py --add 建仓 创新药 暂缓不买 3000 "单日+5.36%追高+资金获利了结" 跌
  python decision_log.py --review <id> <结果> [收益率%] [复盘备注]
      # 例: python decision_log.py --review 1 correct +3.2 "3日后创新药回落，不买正确"
      # 结果: correct(判断对)/wrong(判断错)/neutral(中性无法判定)
  python decision_log.py --report        → 胜率/准确率统计
  python decision_log.py --list          → 列出全部决策（含待复盘）
  python decision_log.py --pending       → 列出待复盘项（T+3 后回填）

数据: Anchor/06-dashboard/decision_log.json（私有，.gitignore）
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LOG_FILE = Path(__file__).parent.parent / "06-dashboard" / "decision_log.json"


def load_log() -> dict:
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"decisions": []}


def save_log(log: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def log_decision(dtype: str, fund: str, verdict: str, amount: float = 0,
                 rationale: str = "", expected: str = "", snapshot: dict = None) -> str:
    """记录一次决策。verdict: 执行买入/执行卖出/等待未触发/观望不买/持有。
    expected: 预期方向（涨/跌/中性）。snapshot: 数据快照 dict（如 fund_flow_snapshot 输出）。"""
    log = load_log()
    now = datetime.now()
    did = str(len(log["decisions"]) + 1)
    entry = {
        "id": did,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "type": dtype,            # 建仓/加仓/止损/评估/观望
        "fund": fund,             # 标的（建议用 data_pipeline 的 key）
        "verdict": verdict,       # 三档：执行买入/执行卖出/等待未触发/观望不买/持有
        "amount": amount,
        "rationale": rationale,   # 判断依据（引用数据管道，防张冠李戴）
        "expected": expected,     # 预期方向
        "snapshot": snapshot or {},
        "outcome": None,          # correct/wrong/neutral
        "pnl_pct": None,          # 事后收益率 %
        "review_date": None,
        "review_note": "",
    }
    log["decisions"].append(entry)
    save_json = save_log(log)
    print(f"✅ 已记录决策 #{did} [{dtype}] {fund} → {verdict}（¥{amount:,.0f}）")
    print(f"   预期: {expected or '未填'} | 依据: {rationale[:60]}")
    print(f"   复盘指令: python decision_log.py --review {did} <correct/wrong/neutral> <收益率%> <备注>")
    return did


def review_decision(did: str, outcome: str, pnl_pct: str = "", note: str = "") -> None:
    """事后复盘回填。outcome: correct/wrong/neutral"""
    log = load_log()
    for d in log["decisions"]:
        if d["id"] == did:
            d["outcome"] = outcome
            d["review_date"] = datetime.now().strftime("%Y-%m-%d")
            d["pnl_pct"] = float(pnl_pct) if pnl_pct not in ("", "0") else 0.0
            d["review_note"] = note
            save_log(log)
            print(f"✅ #{did} 已复盘：{outcome}（pnl {d['pnl_pct']:+.2f}%）{note}")
            return
    print(f"❌ 未找到决策 #{did}")


def pending_list(days: int = 3) -> list:
    """待复盘项：已过 T+days 但仍未回填的决策"""
    log = load_log()
    now = datetime.now()
    pend = []
    for d in log["decisions"]:
        if d["outcome"] is None:
            d_date = datetime.strptime(d["date"], "%Y-%m-%d")
            if (now - d_date).days >= days:
                pend.append(d)
    return pend


def accuracy_report() -> dict:
    """胜率/准确率统计：按类型 + 总览"""
    log = load_log()
    decisions = log["decisions"]
    reviewed = [d for d in decisions if d["outcome"]]
    total = len(decisions)

    # 总览
    correct = sum(1 for d in reviewed if d["outcome"] == "correct")
    wrong = sum(1 for d in reviewed if d["outcome"] == "wrong")
    neutral = sum(1 for d in reviewed if d["outcome"] == "neutral")
    accuracy = correct / (correct + wrong) * 100 if (correct + wrong) else None

    # 按类型
    by_type = {}
    for d in reviewed:
        t = d["type"]
        bucket = by_type.setdefault(t, {"total": 0, "correct": 0, "wrong": 0, "neutral": 0})
        bucket["total"] += 1
        bucket[d["outcome"]] = bucket.get(d["outcome"], 0) + 1

    # 收益率（有 pnl 的）
    pnl_values = [d["pnl_pct"] for d in reviewed if d["pnl_pct"] is not None]
    avg_pnl = sum(pnl_values) / len(pnl_values) if pnl_values else None

    return {
        "total_decisions": total,
        "reviewed": len(reviewed),
        "pending_review": len(decisions) - len(reviewed),
        "correct": correct,
        "wrong": wrong,
        "neutral": neutral,
        "accuracy_pct": round(accuracy, 1) if accuracy is not None else None,
        "avg_pnl_pct": round(avg_pnl, 2) if avg_pnl is not None else None,
        "by_type": by_type,
    }


def main() -> int:
    if "--add" in sys.argv:
        idx = sys.argv.index("--add")
        args = sys.argv[idx + 1:]
        # 位置: 类型 标的 判定 [金额] [依据] [预期]
        if len(args) < 3:
            print("用法: --add <类型> <标的> <判定> [金额] [依据] [预期]")
            return 1
        dtype, fund, verdict = args[0], args[1], args[2]
        amount = float(args[3]) if len(args) > 3 and args[3].replace(".", "").replace("-", "").isdigit() else 0
        rationale = args[4] if len(args) > 4 else ""
        expected = args[5] if len(args) > 5 else ""
        log_decision(dtype, fund, verdict, amount, rationale, expected)
        return 0

    if "--review" in sys.argv:
        idx = sys.argv.index("--review")
        args = sys.argv[idx + 1:]
        if len(args) < 2:
            print("用法: --review <id> <correct/wrong/neutral> [收益率%] [备注]")
            return 1
        review_decision(args[0], args[1], args[2] if len(args) > 2 else "", args[3] if len(args) > 3 else "")
        return 0

    if "--report" in sys.argv:
        rep = accuracy_report()
        print(f"📊 决策统计（决策日志 v1.0）")
        print(f"   总决策: {rep['total_decisions']} | 已复盘: {rep['reviewed']} | 待复盘: {rep['pending_review']}")
        if rep["accuracy_pct"] is not None:
            print(f"   准确率: {rep['accuracy_pct']}%（correct {rep['correct']} / wrong {rep['wrong']} / neutral {rep['neutral']}）")
        else:
            print("   准确率: 无已复盘数据（需 --review 回填）")
        if rep["avg_pnl_pct"] is not None:
            print(f"   平均收益率: {rep['avg_pnl_pct']:+.2f}%")
        if rep["by_type"]:
            print("   按类型:")
            for t, b in rep["by_type"].items():
                acc = b["correct"] / (b["correct"] + b["wrong"]) * 100 if (b["correct"] + b["wrong"]) else None
                acc_s = f"{acc:.0f}%" if acc is not None else "-"
                print(f"     {t}: {b['total']}次 正确{b['correct']}/错{b['wrong']}/中性{b['neutral']} 准确率{acc_s}")
        return 0

    if "--pending" in sys.argv:
        pend = pending_list()
        if not pend:
            print("✅ 无待复盘项")
            return 0
        for d in pend:
            print(f"  #{d['id']} {d['date']} [{d['type']}] {d['fund']} → {d['verdict']}")
            print(f"     复盘: python decision_log.py --review {d['id']} <correct/wrong/neutral> <收益率%> <备注>")
        return 0

    if "--list" in sys.argv:
        log = load_log()
        for d in log["decisions"]:
            mark = d["outcome"] or "⏳待复盘"
            print(f"#{d['id']} {d['date']} [{d['type']}] {d['fund']} → {d['verdict']} ¥{d['amount']:,.0f} | {mark}")
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
