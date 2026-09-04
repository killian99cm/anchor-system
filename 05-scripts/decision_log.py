#!/usr/bin/env python3
"""
Anchor 决策日志 + 胜率统计 v3.4（8/21 升级：T+3 到期提醒 + HTML 胜率仪表盘 + 盈亏比分桶 + 止损倒计时）

核心目标（用户）：「在一次一次操作中吸取经验，提高胜率、收益率、准确率」。
机制：每次给操作建议 → 留痕（数据快照 + 判断 + 预期）→ 事后复盘（实际结果）
      → 统计准确率/胜率 → 校准规则。与 noise_audit（审计规则信号质量）互补，
      decision_log 记录的是「我的决策」本身。

T+3 复盘规则（8/21 确立）：记录日 + 3 个自然日后到期回填，如 8/20 记录 → 8/23 到期。
到期日算法 = 记录日 + 3 天，禁止估算。

用法:
  python decision_log.py --add <类型> <标的> <判定> [金额] [依据] [预期方向] [标签]
      # 例: python decision_log.py --add 建仓 创新药 暂缓不买 3000 "单日+5.36%追高+资金获利了结" 跌
      # 标签（v3.4）: 逗号分隔，如 "追高,红日" —— --report 统计追高型买入占比
  python decision_log.py --backfill "日期|类型|标的|判定|金额|依据|预期" [...多行]
      # 例: python decision_log.py --backfill "2026-08-07|加仓|半导体|执行买入|300|DDX连3日为正|涨"
      # 补录历史操作（8/20 决策日志建立前的手动操作），标记 backfilled=true
  python decision_log.py --review <id> <结果> [收益率%] [复盘备注]
      # 例: python decision_log.py --review 1 correct +3.2 "3日后创新药回落，不买正确"
      # 结果: correct(判断对)/wrong(判断错)/neutral(中性无法判定)
  python decision_log.py --report        → 胜率/准确率/盈亏比/追高占比统计
  python decision_log.py --due           → 今日到期/已超期的复盘项（T+3 精确计算）
  python decision_log.py --stopwatch     → 止损倒计时（读取 portfolio_data.json stop_loss_watch，硬Deadline 三态）
  python decision_log.py --dashboard     → 生成胜率仪表盘 HTML（06-dashboard/decision_dashboard.html）
  python decision_log.py --list          → 列出全部决策（含待复盘）
  python decision_log.py --pending       → 列出待复盘项（T+3 后回填）

数据: Anchor/06-dashboard/decision_log.json（私有，.gitignore）
      Anchor/06-dashboard/decision_dashboard.html（生成的仪表盘，私有）
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # C1：统一路径真源

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
                 rationale: str = "", expected: str = "", snapshot: dict = None,
                 entry_date: str = None, tags: list = None) -> str:
    """记录一次决策。verdict: 执行买入/执行卖出/等待未触发/观望不买/持有。
    expected: 预期方向（涨/跌/中性）。snapshot: 数据快照 dict（如 fund_flow_snapshot 输出）。
    entry_date: 补录历史决策时指定 YYYY-MM-DD（默认当天，保证 T+3 复盘精确）。
    tags: 标签列表（v3.4，如 ["追高"]，--report 统计追高型买入占比）。"""
    log = load_log()
    now = datetime.now()
    did = str(len(log["decisions"]) + 1)
    # 补录历史：用 entry_date；否则当天。时间统一标补录操作发生时间
    if entry_date:
        try:
            entry_dt = datetime.strptime(entry_date, "%Y-%m-%d")
            date_str, time_str = entry_dt.strftime("%Y-%m-%d"), "00:00"
        except ValueError:
            date_str, time_str = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    else:
        date_str, time_str = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    entry = {
        "id": did,
        "date": date_str,
        "time": time_str,
        "backfilled": bool(entry_date),   # 标记补录历史，区别于实时记录
        "type": dtype,            # 建仓/加仓/止损/评估/观望
        "fund": fund,             # 标的（建议用 data_pipeline 的 key）
        "verdict": verdict,       # 三档：执行买入/执行卖出/等待未触发/观望不买/持有
        "amount": amount,
        "rationale": rationale,   # 判断依据（引用数据管道，防张冠李戴）
        "expected": expected,     # 预期方向
        "snapshot": snapshot or {},
        "tags": tags or [],       # v3.4: 追高等标签，--report 分桶统计
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
    """事后复盘回填。outcome: correct/wrong/neutral。superseded 决策禁止复盘（前提已推翻）。"""
    log = load_log()
    for d in log["decisions"]:
        if d["id"] == did:
            if not _is_active(d):
                print(f"❌ #{did} 已被 superseded（→#{d.get('superseded_by')}），前提已推翻，禁止复盘（避免污染统计）；复盘请作用于最终有效决策 #{d.get('superseded_by')}")
                return
            d["outcome"] = outcome
            d["review_date"] = datetime.now().strftime("%Y-%m-%d")
            d["pnl_pct"] = float(pnl_pct) if pnl_pct not in ("", "0") else 0.0
            d["review_note"] = note
            save_log(log)
            print(f"✅ #{did} 已复盘：{outcome}（pnl {d['pnl_pct']:+.2f}%）{note}")
            return
    print(f"❌ 未找到决策 #{did}")


def pending_list(days: int = 3) -> list:
    """待复盘项：已过 T+days 但仍未回填的决策（8/31 审计：排除 backfilled 历史补录噪声）"""
    log = load_log()
    now = datetime.now()
    pend = []
    for d in log["decisions"]:
        if d["outcome"] is None and _is_active(d) and not d.get("backfilled"):
            d_date = datetime.strptime(d["date"], "%Y-%m-%d")
            if (now - d_date).days >= days:
                pend.append(d)
    return pend


def _is_active(d: dict) -> bool:
    """有效决策判定：排除已被 superseded（前提被推翻/未执行）的记录，防止污染胜率/盈亏比统计"""
    return not (d.get("superseded_by") or "superseded" in (d.get("tags") or []))


def accuracy_report(decisions=None) -> dict:
    """胜率/准确率统计：按类型 + 总览（superseded 记录不计入）。
    decisions 可注入（测试用）；默认从决策日志文件读取。"""
    if decisions is None:
        decisions = load_log()["decisions"]
    reviewed = [d for d in decisions if d["outcome"] and _is_active(d)]
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

    # 盈亏比分桶（v3.4）：avg_win / avg_loss / 盈亏比（赚得抠亏得大方 → 目标 ≥1.5:1）
    wins = [d["pnl_pct"] for d in reviewed if d["pnl_pct"] is not None and d["pnl_pct"] > 0]
    losses = [d["pnl_pct"] for d in reviewed if d["pnl_pct"] is not None and d["pnl_pct"] < 0]
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = abs(sum(losses) / len(losses)) if losses else None
    pnl_ratio = (avg_win / avg_loss) if (avg_win is not None and avg_loss) else None

    # 追高型买入占比（v3.4，A1 标签）：目标 ≤20%
    # 8/31 审计修正：分母=买入类决策（建仓/加仓/买入 + _is_active），原分母=全部决策稀释 ~2.3 倍
    buy_types = {"建仓", "加仓", "买入"}
    buy_decisions = [d for d in decisions if d.get("type") in buy_types and _is_active(d)]
    chase_buys = [d for d in buy_decisions if "追高" in (d.get("tags") or [])]
    chase_pct = (len(chase_buys) / len(buy_decisions) * 100) if buy_decisions else None

    # 止损执行率（8/31 审计：主指标三件套缺一，口径=verdict 含「执行」/ 全部止损触发）
    stop_triggers = [d for d in decisions if "止损" in (d.get("type") or "")]
    stop_executed = [d for d in stop_triggers if "执行" in (d.get("verdict") or "")]
    stop_execution_pct = (len(stop_executed) / len(stop_triggers) * 100) if stop_triggers else None

    # v4.4.2：待复盘只计有效决策——superseded 前提已推翻永不复盘、backfilled 历史补录为噪声，
    #        原 len(decisions)-len(reviewed) 把 3 条已取代记录算进待复盘（曾虚报 26，实为 23）
    active_total = sum(1 for d in decisions if _is_active(d))
    return {
        "total_decisions": total,  # 57 历史累计（含已取代 3，KPI 标注）
        "active_total": active_total,  # 54 有效决策
        "reviewed": len(reviewed),
        "pending_review": active_total - len(reviewed),
        "correct": correct,
        "wrong": wrong,
        "neutral": neutral,
        "accuracy_pct": round(accuracy, 1) if accuracy is not None else None,
        "avg_pnl_pct": round(avg_pnl, 2) if avg_pnl is not None else None,
        "avg_win_pct": round(avg_win, 2) if avg_win is not None else None,
        "avg_loss_pct": round(avg_loss, 2) if avg_loss is not None else None,
        "pnl_ratio": round(pnl_ratio, 2) if pnl_ratio is not None else None,
        "chase_count": len(chase_buys),
        "chase_pct": round(chase_pct, 1) if chase_pct is not None else None,
        "stop_loss_triggers": len(stop_triggers),
        "stop_loss_executed": len(stop_executed),
        "stop_loss_execution_pct": round(stop_execution_pct, 1) if stop_execution_pct is not None else None,
        "by_type": by_type,
    }


def due_date(d: dict) -> str:
    """T+3 到期日 = 记录日 + 3 个自然日（精确计算，禁止估算）"""
    return (datetime.strptime(d["date"], "%Y-%m-%d") + timedelta(days=3)).strftime("%Y-%m-%d")


def due_list() -> list:
    """今日已到期/超期的复盘项（outcome 为空 且 今天 >= 到期日；superseded/backfilled 跳过——8/31 审计：backfilled 历史补录为噪声）"""
    log = load_log()
    now = datetime.now().strftime("%Y-%m-%d")
    due = []
    for d in log["decisions"]:
        if d["outcome"] is None and _is_active(d) and not d.get("backfilled") and due_date(d) <= now:
            d["due"] = due_date(d)
            due.append(d)
    return due


def next_due() -> dict:
    """下一次到期信息：{date: 最近到期日, items: [决策]}，无待复盘则 date=None"""
    log = load_log()
    nxt = None
    items = []
    for d in log["decisions"]:
        # 09-01 修复：排除 backfilled 历史补录（与 pending_list/due_list 口径一致），
        # 否则过期的历史记录恒占"下次复盘日"位（此前 #42 2025-10-13 陈旧日期）
        if d["outcome"] is None and _is_active(d) and not d.get("backfilled"):
            dd = due_date(d)
            if nxt is None or dd < nxt:
                nxt = dd
                items = [d]
            elif dd == nxt:
                items.append(d)
    return {"date": nxt, "items": items}


def stopwatch() -> int:
    """止损倒计时（v3.4 B4 状态机）：读取 portfolio_data.json stop_loss_watch，按硬Deadline推送三态。
    结构: stop_loss_watch = { "半导体": {"triggered":"2026-08-19","cur_pct":-12.38,
                                        "buffers_used":2,"deadline":"2026-08-22","status":"观察中"} }"""
    desktop_pf = paths.DATA_PATH
    if not desktop_pf.exists():
        desktop_pf = LOG_FILE.parent / "portfolio_data.json"  # 06-dashboard 只读副本
    if not desktop_pf.exists():
        print("❌ 未找到 portfolio_data.json（桌面/06-dashboard）——无法读取 stop_loss_watch")
        return 1
    try:
        data = json.loads(desktop_pf.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ portfolio_data.json 解析失败: {e}")
        return 1
    watch = data.get("stop_loss_watch") or {}
    if not watch:
        print("✅ 无进行中止损监控（stop_loss_watch 为空）")
        return 0
    today = datetime.now()
    print(f"⏱️ 止损倒计时（今日 {today.strftime('%Y-%m-%d')}）· 硬Deadline = 触发后第4交易日 14:30")
    for name, w in watch.items():
        triggered = w.get("triggered") or ""
        deadline = w.get("deadline") or ""
        buffers = w.get("buffers_used", 0)
        pct = w.get("cur_pct")
        status = w.get("status", "观察中")
        pct_s = f"{pct:+.2f}%" if pct is not None else "—"
        if status == "已执行":
            state = "✅ 已执行"
        elif deadline:
            dd = datetime.strptime(deadline, "%Y-%m-%d")
            if dd.date() <= today.date():
                state = "🔴 硬Deadline已到 —— 今日14:30无条件执行（不看红绿）"
            else:
                days = (dd.date() - today.date()).days
                state = f"🟡 距硬Deadline {deadline} 剩 {days} 天"
        else:
            state = "🟡 观察中（无deadline，待设置）"
        print(f"  {name}: 浮亏 {pct_s} | 缓冲/延期已用 {buffers} 次 | 触发 {triggered or '—'} | {state}")
    print("  提示: 止损用 decision_log.py --add 止损 <标的> <执行止损/等待> 留痕，T+3 后 --review 复盘")
    return 0


def dashboard_html() -> str:
    """生成胜率仪表盘 HTML（Anchor 品牌深色金融终端风格）"""
    rep = accuracy_report()
    log = load_log()
    # v4.4.1：全部决策表按时间「新上旧下」——date 降序、同日 id 降序（原升序把最新决策埋在表底）
    decisions = sorted(log["decisions"], key=lambda x: (x.get("date", ""), int(x.get("id", 0) or 0)), reverse=True)
    due = due_list()
    nd = next_due()
    # v4.4.0：footer 注入真实时刻——数据源(decision_log.json)更新时间 + 本页生成时间
    gen_ts = datetime.fromtimestamp(LOG_FILE.stat().st_mtime).strftime('%Y-%m-%d %H:%M') if LOG_FILE.exists() else "--"
    now_ts = datetime.now().strftime('%Y-%m-%d %H:%M')

    def badge(outcome: str) -> str:
        if outcome == "correct":
            return '<span style="color:#36d39c;font-family:Cascadia Mono,monospace">● 正确</span>'
        if outcome == "wrong":
            return '<span style="color:#e66767;font-family:Cascadia Mono,monospace">● 错误</span>'
        if outcome == "neutral":
            return '<span style="color:#91a4bd;font-family:Cascadia Mono,monospace">● 中性</span>'
        return '<span style="color:#fab219;font-family:Cascadia Mono,monospace">◌ 待复盘</span>'

    rows = []
    for d in decisions:
        # v4.4.2：superseded（已被取代/前提推翻）决策整行置灰 + 结果列标「已取代」，
        #        不再显示「⏳待复盘」黄标（防止与真实待复盘混淆，如 27/52/53）
        is_sup = not _is_active(d)
        due_txt = due_date(d)
        if is_sup:
            status = f'<span style="color:#536a85;font-size:11px">已取代' + (f' → #{d["superseded_by"]}' if d.get("superseded_by") else '') + ' · 前提推翻</span>'
        else:
            status = f'<span style="color:#fab219;font-size:11px">⏳ 待复盘（到期 {due_txt}）</span>' if d["outcome"] is None else f'复盘于 {d["review_date"]}'
        row_style = 'style="opacity:0.5;background:rgba(83,106,133,0.04)"' if is_sup else ''
        result_badge = '<span style="color:#536a85;font-family:Cascadia Mono,monospace">已取代</span>' if is_sup else badge(d['outcome'])
        rows.append(f"""
      <tr {row_style}>
        <td style="padding:10px 14px;color:#536a85;font-family:Cascadia Mono,monospace">#{d['id']}</td>
        <td style="padding:10px 14px;color:#91a4bd;font-family:Cascadia Mono,monospace">{d['date']}</td>
        <td style="padding:10px 14px;color:#9085e9;font-family:Cascadia Mono,monospace">{d['type']}</td>
        <td style="padding:10px 14px;color:#e8f1ff">{d['fund']}</td>
        <td style="padding:10px 14px;color:#3987e5">{d['verdict']}</td>
        <td style="padding:10px 14px;color:#e8f1ff;font-family:Cascadia Mono,monospace">{"¥{:,.0f}".format(d['amount']) if d['amount'] else "—"}</td>
        <td style="padding:10px 14px;color:#91a4bd">{d['expected'] or "—"}</td>
        <td style="padding:10px 14px;color:#91a4bd;font-size:11px">{d['rationale'][:34] or "—"}</td>
        <td style="padding:10px 14px">{result_badge}</td>
        <td style="padding:10px 14px;color:#536a85;font-size:11px">{status}</td>
      </tr>""")
    rows_html = "\n".join(rows)

    # KPI 卡片
    acc = rep["accuracy_pct"]
    acc_txt = f"{acc}%" if acc is not None else "—"
    avg = rep["avg_pnl_pct"]
    avg_txt = f"{avg:+.2f}%" if avg is not None else "—"
    pr = rep["pnl_ratio"]
    pr_txt = f"{pr:.2f}:1" if pr is not None else "—"
    chase = rep["chase_pct"]
    chase_txt = f"{chase:.1f}%" if chase is not None else "—"

    # 到期提醒区
    if due:
        due_items = "、".join(f"#{d['id']} {d['fund']}" for d in due)
        due_html = f'<div style="background:rgba(230,103,103,0.10);border:1px solid #e66767;border-radius:8px;padding:14px 18px;margin-bottom:22px"><span style="color:#e66767;font-weight:600">🔴 {len(due)} 项已到复盘期</span> <span style="color:#91a4bd;font-size:12px">— {due_items}</span><br><span style="color:#536a85;font-size:11px;font-family:Cascadia Mono,monospace">运行: python decision_log.py --review &lt;id&gt; correct/wrong/neutral &lt;收益率%&gt; &lt;备注&gt;</span></div>'
    elif nd["date"]:
        nxt_items = "、".join(f"#{d['id']} {d['fund']}" for d in nd["items"])
        due_html = f'<div style="background:rgba(250,178,25,0.08);border:1px solid rgba(250,178,25,0.4);border-radius:8px;padding:14px 18px;margin-bottom:22px"><span style="color:#fab219;font-weight:600">📅 下次复盘日 {nd["date"]}</span> <span style="color:#91a4bd;font-size:12px">— {nxt_items}</span></div>'
    else:
        due_html = '<div style="background:rgba(54,211,156,0.08);border:1px solid rgba(54,211,156,0.4);border-radius:8px;padding:14px 18px;margin-bottom:22px"><span style="color:#36d39c;font-weight:600">✅ 无待复盘项</span></div>'

    by_type_html = ""
    if rep["by_type"]:
        trows = []
        for t, b in rep["by_type"].items():
            tacc = b["correct"] / (b["correct"] + b["wrong"]) * 100 if (b["correct"] + b["wrong"]) else None
            tacc_s = f"{tacc:.0f}%" if tacc is not None else "—"
            trows.append(f'<div style="background:rgba(144,133,233,0.08);border:1px solid rgba(144,133,233,0.3);border-radius:8px;padding:12px 16px"><div style="color:#e8f1ff;font-size:12px">{t} <span style="color:#536a85">×{b["total"]}</span></div><div style="color:#36d39c;font-size:11px;margin-top:4px">正确 {b["correct"]} · <span style="color:#e66767">错 {b["wrong"]}</span> · <span style="color:#91a4bd">中性 {b["neutral"]}</span></div><div style="color:#fab219;font-size:16px;font-family:Cascadia Mono,monospace;margin-top:4px">{tacc_s}</div></div>')
        by_type_html = f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:22px">{"".join(trows)}</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Anchor 决策日志 · 胜率仪表盘</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', 'Microsoft YaHei', system-ui, sans-serif; background: #02070f; color: #e8f1ff; padding: 2.5rem; min-height: 100vh; }}
  .eyebrow {{ font-family: 'Cascadia Mono', Consolas, monospace; font-size: 0.66rem; font-weight: 500; letter-spacing: 0.18em; text-transform: uppercase; color: #536a85; margin-bottom: 0.5rem; }}
  h1 {{ font-size: clamp(1.4rem, 2.2vw + 0.7rem, 1.9rem); font-weight: 600; letter-spacing: -0.02em; margin-bottom: 1.5rem; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 22px; }}
  .kpi {{ background: rgba(57,135,229,0.07); border: 1px solid rgba(57,135,229,0.25); border-radius: 10px; padding: 16px 18px; }}
  .kpi .label {{ color: #536a85; font-size: 10px; font-family: 'Cascadia Mono', monospace; letter-spacing: 0.12em; text-transform: uppercase; }}
  .kpi .value {{ color: #e8f1ff; font-size: 26px; font-weight: 600; font-family: 'Cascadia Mono', monospace; margin-top: 6px; }}
  .kpi .sub {{ color: #91a4bd; font-size: 11px; margin-top: 3px; }}
  h2 {{ color: #3987e5; font-size: 13px; font-family: 'Cascadia Mono', monospace; letter-spacing: 0.12em; margin: 22px 0 10px; }}
  table {{ width: 100%; border-collapse: collapse; background: rgba(232,241,255,0.02); border-radius: 10px; overflow: hidden; }}
  th {{ text-align: left; padding: 10px 14px; color: #536a85; font-size: 10px; font-family: 'Cascadia Mono', monospace; letter-spacing: 0.1em; border-bottom: 1px solid rgba(232,241,255,0.1); text-transform: uppercase; }}
  td {{ border-bottom: 1px solid rgba(232,241,255,0.05); }}
  tr:last-child td {{ border-bottom: none; }}
  .foot {{ color: #536a85; font-size: 11px; margin-top: 22px; text-align: center; font-family: 'Cascadia Mono', monospace; }}
</style>
</head>
<body>
  <p class="eyebrow">Anchor Decision Log · Win-Rate Dashboard</p>
  <h1>决策日志 · 胜率仪表盘</h1>
  {due_html}
  <div class="kpis">
    <div class="kpi"><div class="label">总决策</div><div class="value">{rep['total_decisions']}</div><div class="sub">历史累计 · 有效 {rep['active_total']}（已取代 {rep['total_decisions'] - rep['active_total']}）</div></div>
    <div class="kpi"><div class="label">已复盘</div><div class="value">{rep['reviewed']}</div><div class="sub">T+3 回填</div></div>
    <div class="kpi"><div class="label">待复盘</div><div class="value">{rep['pending_review']}</div><div class="sub">仅有效决策 · 不含已取代</div></div>
    <div class="kpi"><div class="label">准确率</div><div class="value" style="color:#36d39c">{acc_txt}</div><div class="sub">correct / (correct+wrong)</div></div>
    <div class="kpi"><div class="label">平均收益率</div><div class="value" style="color:#3987e5">{avg_txt}</div><div class="sub">已复盘 pnl</div></div>
    <div class="kpi"><div class="label">盈亏比</div><div class="value" style="color:{'#36d39c' if pr and pr >= 1.5 else '#fab219'}">{pr_txt}</div><div class="sub">均盈/均亏 · 目标 ≥1.5:1</div></div>
    <div class="kpi"><div class="label">追高占比</div><div class="value" style="color:{'#36d39c' if chase is not None and chase <= 20 else '#fab219'}">{chase_txt}</div><div class="sub">目标 ≤20%</div></div>
  </div>
  <h2>按类型统计</h2>
  {by_type_html or '<p style="color:#536a85;font-size:12px">暂无已复盘数据</p>'}
  <h2>全部决策</h2>
  <table>
    <thead><tr><th>ID</th><th>日期</th><th>类型</th><th>标的</th><th>判定</th><th>金额</th><th>预期</th><th>依据</th><th>结果</th><th>复盘</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <p class="foot">决策日志 v3.4 · T+3 到期日 = 记录日 + 3 自然日 · 盈亏比目标 ≥1.5:1 · 数据源更新 {gen_ts} · 本页生成 {now_ts}</p>
</body>
</html>"""


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
        tags = [t.strip() for t in args[6].split(",") if t.strip()] if len(args) > 6 else []
        log_decision(dtype, fund, verdict, amount, rationale, expected, tags=tags)
        return 0

    if "--backfill" in sys.argv:
        # 补录历史决策，每条: 日期|类型|标的|判定|金额|依据|预期
        # 例: python decision_log.py --backfill "2026-08-07|加仓|半导体|执行买入|300|DDX连3日为正|涨" ...
        idx = sys.argv.index("--backfill")
        entries = sys.argv[idx + 1:]
        if not entries:
            print("用法: --backfill \"日期|类型|标的|判定|金额|依据|预期\" [...多行]")
            return 1
        n = 0
        for raw in entries:
            parts = [p.strip() for p in raw.split("|")]
            if len(parts) < 4:
                print(f"⚠️ 跳过格式错误: {raw}")
                continue
            date_s, dtype, fund, verdict = parts[0], parts[1], parts[2], parts[3]
            amount = float(parts[4]) if len(parts) > 4 and parts[4].replace(".", "").replace("-", "").isdigit() else 0
            rationale = parts[5] if len(parts) > 5 else ""
            expected = parts[6] if len(parts) > 6 else ""
            tags = [t.strip() for t in parts[7].split(",") if t.strip()] if len(parts) > 7 else []
            log_decision(dtype, fund, verdict, amount, rationale, expected, entry_date=date_s, tags=tags)
            n += 1
        print(f"✅ 补录完成：{n} 条历史决策（标记 backfilled=true）")
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
        print(f"📊 决策统计（决策日志 v3.4）")
        print(f"   总决策: {rep['total_decisions']} | 已复盘: {rep['reviewed']} | 待复盘: {rep['pending_review']}")
        if rep["accuracy_pct"] is not None:
            print(f"   准确率: {rep['accuracy_pct']}%（correct {rep['correct']} / wrong {rep['wrong']} / neutral {rep['neutral']}）")
        else:
            print("   准确率: 无已复盘数据（需 --review 回填）")
        if rep["avg_pnl_pct"] is not None:
            print(f"   平均收益率: {rep['avg_pnl_pct']:+.2f}%")
        # 盈亏比分桶（v3.4 新增）
        if rep["pnl_ratio"] is not None:
            print(f"   盈亏比: {rep['pnl_ratio']:.2f}:1（均盈 {rep['avg_win_pct']:+.2f}% vs 均亏 {rep['avg_loss_pct']:+.2f}%｜目标 ≥1.5:1）")
        if rep["chase_pct"] is not None:
            print(f"   追高型买入: {rep['chase_count']} 条（{rep['chase_pct']:.1f}%｜目标 ≤20%）")
        if rep["stop_loss_execution_pct"] is not None:
            print(f"   止损执行率: {rep['stop_loss_executed']}/{rep['stop_loss_triggers']}（{rep['stop_loss_execution_pct']:.1f}%｜目标 100%）")
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

    if "--stopwatch" in sys.argv:
        return stopwatch()

    if "--due" in sys.argv:
        due = due_list()
        if not due:
            nd = next_due()
            if nd["date"]:
                items = "、".join(f"#{d['id']} {d['fund']}" for d in nd["items"])
                print(f"📅 今日无到期项。最近一次复盘日：{nd['date']}（{items}）")
            else:
                print("✅ 无待复盘项")
            return 0
        print(f"🔴 {len(due)} 项已到 T+3 复盘期（今日 {datetime.now().strftime('%Y-%m-%d')}）:")
        for d in due:
            print(f"  #{d['id']} {d['date']} [{d['type']}] {d['fund']} → {d['verdict']}（到期 {d['due']}）")
            print(f"     复盘: python decision_log.py --review {d['id']} <correct/wrong/neutral> <收益率%> <备注>")
        return 0

    if "--dashboard" in sys.argv:
        html = dashboard_html()
        out = LOG_FILE.parent / "decision_dashboard.html"
        out.write_text(html, encoding="utf-8")
        print(f"✅ 胜率仪表盘已生成: {out}")
        print("   打开方式: 双击 decision_dashboard.html 或用浏览器打开")
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
