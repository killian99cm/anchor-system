#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stop_profit_backtest.py — 止盈档位回测 / 案例检视（v3.0, 2026-09-23 口径契约化 · inbox/141）

目的：用真实交易流水与已清仓基金数据，检视**现行**止盈档位下的卖出质量；
      可选地对一个**显式传入**的替代档位做对照。

🔴 v3.0 口径契约化（inbox/141 裁定 R1–R5）：
  - **现行档位唯一源 = `rule_contract.json` 的 `take_profit`**（经 paths.RULE_CONTRACT_PATH），
    脚本内**禁止任何档位数字字面量**；卖出比例与奔跑仓余量**由档位数派生**。
  - 「现行 / 替代」的语义角色**由数据决定**：替代档位只能经 `--alt-tiers` 显式传入，
    ⛔ 不虚构「新档」，⛔ 无参数时**不做档位对比**。
  - 护栏：契约缺失/不可读、档位数 ≠ 3、非严格递增 → **报错退出（非零码）**，⛔ 不回退硬编码。

v2 变更（C4）：函数化（load_data/cleared_funds/sell_txn/build_findings/ratio_line/main），
  路径走 paths.py；--month/--top/--data；盈亏比改从 decision_log.accuracy_report 动态读取。

用法:
  python stop_profit_backtest.py                       # 全量（按契约现行档位检视）
  python stop_profit_backtest.py --month 2026-08       # 只看 8 月卖出
  python stop_profit_backtest.py --alt-tiers 12,18,30   # 与显式替代档位对照（参数即来源）
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


def load_contract():
    """读现行止盈档位（唯一源 = rule_contract.json）。

    🔴 inbox/141 裁定 R1/R5：契约缺失 / 不可读 / 档位数 ≠3 / 非严格递增 / 非数值
    ⇒ 返回 (None, 原因)，调用方**报错退出**；⛔ **绝不回退到任何硬编码档位**。
    返回 (tiers, source_label)；source_label 形如 `rule_contract.json @ 2026-09-22 22:30 …`。
    """
    p = (Path(os.environ["ANCHOR_RULE_CONTRACT"]) if os.environ.get("ANCHOR_RULE_CONTRACT")
         else paths.RULE_CONTRACT_PATH)      # env 覆盖仅供测试隔离（同 ANCHOR_BOARD_HISTORY 约定）
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"契约缺失：{p}（R1：⛔ 不得回退硬编码档位）"
    except Exception as e:                                        # noqa: BLE001
        return None, f"契约不可读：{type(e).__name__} {e}"
    tiers = (doc.get("rules") or {}).get("take_profit")
    if not isinstance(tiers, list) or len(tiers) != 3:
        return None, f"take_profit 档位数异常：应为严格递增三档，实得 {tiers!r}（R5）"
    try:
        tiers = [float(t) for t in tiers]
    except (TypeError, ValueError):
        return None, f"take_profit 存在非数值元素：{tiers!r}（R5）"
    if not (tiers[0] < tiers[1] < tiers[2]):
        return None, f"take_profit 非严格递增：{tiers!r}（R5）"
    updated = doc.get("updated") or doc.get("data_date") or "unknown"
    return tiers, f"rule_contract.json @ {updated}"


def tiers_label(tiers):
    """档位标签（唯一渲染入口，防文案里散落字面量）。"""
    return "/".join(f"+{t:g}" for t in tiers)


def runner_part_pct(n_tiers):
    """每档卖出比例与奔跑仓余量 = 100/(档位数+1)（3 档 ⇒ 各卖一份、余一份奔跑仓）。"""
    part = 100.0 / (n_tiers + 1)
    return int(part) if float(part).is_integer() else part


def guard_current_label(tiers, claimed):
    """🛡️ R3 强制护栏：被标为「现行」的那一组**必须 == 契约值**，否则报错（非静默渲染）。"""
    if claimed != tiers_label(tiers):
        raise ValueError(f"护栏触发：被标为「现行」的档位 {claimed!r} ≠ 契约值 "
                         f"{tiers_label(tiers)!r}（R3：语义角色由数据决定）")
    return claimed


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


def methodology_blocks(cumul, tiers, src, alt_tiers=None):
    """按累计盈亏方向生成检视块（**全部档位文本由契约值/显式参数派生**，R2/R3/R4）。

    - 「现行」栏 = 契约值（经 `guard_current_label` 护栏，结构性保证）；
    - 有 `alt_tiers`（**显式参数**）才做对照；无参数 ⇒ 明确写「不做档位对照」；
    - ⛔ 不出现「旧档/新档」措辞，⛔ 不推荐任何非契约档位。
    """
    cur = guard_current_label(tiers, tiers_label(tiers))
    part = runner_part_pct(len(tiers))
    if cumul >= 0:
        out = [f"现行档位（{src}）：{cur} 各卖 {part}%，剩余 {part}% 奔跑仓（破线或自高回撤出清）"]
        if alt_tiers:
            out.append(f"替代档位（--alt-tiers 显式传入，来源=命令参数）：{tiers_label(alt_tiers)}")
            out.append("对照口径：差异以本工具案例数据为准；⛔ 不对非契约档位作推荐性结论")
        else:
            out.append("（未传入 --alt-tiers ⇒ **不做档位对照**；R3：替代档位须显式传入）")
        return out
    return [f"现行档位（{src}）：{cur}；止盈端按契约档执行，"
            f"止损端由 §2.2 B1 硬 Deadline 解决（不属止盈档位）"]


def build_findings(data, top=5, tiers=None, src="", alt_tiers=None):
    """从已清仓且有累计盈亏的基金动态构建案例（取 |cumul| 前 top，兼顾盈亏两侧）。"""
    cases = []
    for h in cleared_funds(data):
        cumul = h.get("cumul", 0) or 0
        if cumul == 0:
            continue
        ops = fund_ops(data, h.get("name", ""))
        flow = " → ".join(f"{t.get('date','')} {t.get('op','')}" for t in ops[:4]) or "（无明细流水）"
        cases.append({
            "case": h.get("name", ""),
            "evidence": f"{flow}；累计 {cumul:+.2f}",
            "blocks": methodology_blocks(cumul, tiers, src, alt_tiers),
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


def report(data, month=None, top=5, tiers=None, src="", alt_tiers=None):
    lines = []
    p = lambda s="": lines.append(s)
    cur_label = guard_current_label(tiers, tiers_label(tiers))       # R3 护栏（打印前再验一次）
    part = runner_part_pct(len(tiers))

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
    p(f"[2] 卖出点位清单（现行档位 {cur_label} ｜ {src}）"
      + (f" · 仅 {month}" if month else "")
      + ("　🧪 含替代档位对照" if alt_tiers else ""))
    p("=" * 70)
    p(f"卖出类流水共 {len(sells)} 笔：")
    for s in sells:
        p(f"  {s.get('date','')} | {str(s.get('name',''))[:20]:<22} | {s.get('op','')} | ¥{s.get('amount','')} | {str(s.get('note',''))[:45]}")

    # [3] 案例（动态）
    findings = build_findings(data, top=top, tiers=tiers, src=src, alt_tiers=alt_tiers)
    p()
    p("=" * 70)
    p("[3] 现行档位检视（案例取自已清仓真实流水）"
      + ("＋ 替代档位对照（--alt-tiers 显式传入）" if alt_tiers else "；⛔ 未传入替代档位 ⇒ 不做档位对照"))
    p("=" * 70)
    if not findings:
        p("（无累计盈亏非 0 的已清仓案例）")
    for f in findings:
        p(f"📌 {f['case']}")
        p(f"   证据: {f['evidence']}")
        for b in f["blocks"]:
            p(f"   {b}")
        p()

    # [4] 盈亏比基准（动态）
    p("=" * 70)
    p("[4] 盈亏比现状（优化前基准）")
    p("=" * 70)
    p(f"当前持有盈亏估计: {data.get('total_hold_pnl_est', 0):+,.2f}")
    p(ratio_line(data))
    p("→ 盈利端重构（止盈档位）与亏损端硬化（止损Deadline）即为盈亏比修复的双引擎。")
    p()
    p(f"结论：现行止盈档位 = {cur_label}（来源：{src}）")
    p(f"      各档卖出 {part}% ＋ 剩余 {part}% 奔跑仓；与止损 Deadline 端共同服务盈亏比修复。")
    if alt_tiers:
        p(f"      替代档位 {tiers_label(alt_tiers)} 为命令参数传入的对照项，⛔ 不构成推荐。")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="止盈档位检视（现行档位经契约读取；对照档位须显式传入）")
    ap.add_argument("--month", default=None, help="只统计指定月份卖出流水，格式 YYYY-MM")
    ap.add_argument("--top", type=int, default=5, help="动态案例最多展示数（默认 5）")
    ap.add_argument("--data", default=None, help="指定 portfolio_data.json 路径（默认桌面权威）")
    ap.add_argument("--alt-tiers", default=None,
                    help="显式传入的替代档位（逗号分隔三档，如 12,18,30），用于对照；"
                         "⛔ 不传则不做档位对照（R3）")
    args = ap.parse_args()
    if args.month:
        # 严格校验 YYYY-MM
        import re
        if not re.fullmatch(r"20\d{2}-(0?[1-9]|1[0-2])", args.month):
            print(f"[错误] --month 格式应为 YYYY-MM，收到 {args.month!r}")
            return 2
    # 🔴 R1/R5：现行档位唯一源 = rule_contract.json；不可判定 ⇒ 非零退出、零档位结论
    tiers, src = load_contract()
    if tiers is None:
        print(f"[错误] 止盈档位不可判定：{src}")
        print("       ⛔ R1/R5：契约缺失或异常时不得回退任何硬编码档位"
              "（先跑 extract_rule_contract.py / sync_all 重建契约）")
        return 1
    alt = None
    if args.alt_tiers:
        try:
            alt = [float(x) for x in str(args.alt_tiers).split(",")]
        except ValueError:
            print(f"[错误] --alt-tiers 解析失败：{args.alt_tiers!r}")
            return 2
        if len(alt) != 3 or not (alt[0] < alt[1] < alt[2]):
            print(f"[错误] --alt-tiers 应为严格递增三档：{args.alt_tiers!r}")
            return 2
    try:
        data = load_data(args.data)
    except Exception as exc:
        print(json.dumps({"error": f"读取数据失败: {exc}"}, ensure_ascii=False))
        return 1
    print(report(data, month=args.month, top=args.top, tiers=tiers, src=src, alt_tiers=alt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
