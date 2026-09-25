#!/usr/bin/env python3
"""
Anchor 月度归因辅助器 (P2-2)
自动完成月度归因的步骤 1/3/5/6（从 portfolio_data.json + mx-data 可得），
步骤 2（真实盈亏）需用户提供，脚本生成待填模板。

用法:
    python gen_monthly_attribution.py                 # 本月
    python gen_monthly_attribution.py --month 2026-07 # 指定月
输出:
    04-reviews/月度归因_YYYY年M月.md (骨架，AI/用户补叙事)
"""
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import paths
from data_processor import monthly_ops_summary, safe_float
from decision_log import QUOTA_TAG, QUOTA_TAG_SINCE, LOG_FILE as DECISION_LOG_FILE

DATA_PATH = paths.DATA_PATH
KB_DIR = paths.REVIEWS_DIR
RULE_LEDGER = Path(__file__).parent.parent / "06-dashboard" / "noise" / "rule_hits.json"


def load_rule_ledger(month_prefix: str) -> list:
    """加载规则命中台账（noise/rule_hits.json）并按月过滤，供归因自动汇总"""
    if not RULE_LEDGER.exists():
        return []
    try:
        data = json.loads(RULE_LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [x for x in data if str(x.get("date", "")).startswith(month_prefix)]


def load_data():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def month_txns(data, year, month):
    """本月的所有交易记录（与 data_processor.monthly_ops_summary 口径一致，支持 '8/' 与 '08/'）。"""
    prefixes = [f"{year}-{month:02d}", f"{month}/", f"{month:02d}/"]
    out = []
    for t in data.get('transactions', []):
        d = str(t.get('date', ''))
        if any(d.startswith(p) for p in prefixes):
            out.append(t)
    return out


def classify_txn(t):
    """分类交易: 买入/卖出/清仓/定投/转换/出入金。"""
    op = t.get('op', '')
    if '清仓' in op:
        return '清仓'
    if '减仓' in op or '卖出' in op or '止盈' in op:
        return '卖出'
    if '定投' in op:
        return '定投'
    if '转入' in op or '转出' in op or '入金' in op or '出金' in op:
        return '出入金'
    if '加仓' in op or '买入' in op or '试探' in op:
        return '买入'
    return op or '其他'


# ══════════════════════════════════════════════════════════════════
# 月操作额度 · **超限披露**（单 152 · 裁决 #C1-21 方案 A-3 · 2026-09-24）
#   病灶：买入维 12 个月超限 11 个月、9 月超限 5 笔，而留痕 0 笔 ⇒ 「超了也没事」。
#   本段让**超限与「超限未留痕」的差额**每月可见（留痕载体见 decision_log 的自动打标）。
# ══════════════════════════════════════════════════════════════════
def _month_day(date_s):
    """'2026-09-07' / '9/7' → (9, 7)；不可解析 → None（⛔ 不猜）。"""
    s = str(date_s or '').strip()
    m = re.match(r'^(\d{4})[\-/](\d{1,2})[\-/](\d{1,2})', s) or re.match(r'^(\d{1,2})/(\d{1,2})', s)
    if not m:
        return None
    g = m.groups()
    return (int(g[-2]), int(g[-1]))


def _txn_sort_key(t):
    """逐笔披露的**时序**排序键（日期格式混用 '2026-09-07' / '9/7' 实测存在）。
    不可解析者排到末尾（⛔ 不丢弃、也不猜其日期）。"""
    md = _month_day(t.get('date'))
    return (0, md) if md else (1, (0, 0))


def _tagged_decisions(year, month) -> list:
    """本月 `decision_log` 中带 `违规·月额度` tag 的记录（「留痕」列的判据）。"""
    p = DECISION_LOG_FILE
    if not p.exists():
        return []
    try:
        ds = json.loads(p.read_text(encoding="utf-8")).get("decisions", [])
    except Exception:                                         # noqa: BLE001
        return []
    return [d for d in ds
            if str(d.get("date", "")).startswith(f"{year}-{month:02d}")
            and QUOTA_TAG in (d.get("tags") or [])]


def quota_disclosure(data, year, month) -> str:
    """月操作额度·超限披露段（Markdown）。

    🔴 计数**单一真源** ＝ `data_processor.monthly_ops_summary()`（⛔ 本函数只做排序与序号
       标注，**不加任何计数口径** —— 单 152 验收 6）。
    口径「**含本笔**」⇒ 第 `max_buys + 1` 笔起为超限（与手册 §1.3「买入 ≤2」一致）。
    ⛔ 无超限时**显式**写「本月无超限」—— 不得静默省略整段（验收 3）。"""
    s = monthly_ops_summary(data, year, month)
    over = max(s.buys - s.max_buys, 0)
    tagged = _tagged_decisions(year, month)
    rows = []
    for i, t in enumerate(sorted(s.buy_items, key=_txn_sort_key), 1):
        md = _month_day(t.get('date'))
        amt = safe_float(t.get('amount'))
        hit = next((d for d in tagged
                    if _month_day(d.get('date')) == md
                    and abs(safe_float(d.get('amount')) - amt) < 0.01), None)
        mark = f"✅ #{hit['id']}" if hit else ('⛔ 无' if i > s.max_buys else '—')
        rows.append(
            f"| {i} | {t.get('date', '')} | {t.get('name') or t.get('fund') or ''} | "
            f"{t.get('op', '')} | ¥{amt:,.0f} | "
            f"{'🔴 **超限**' if i > s.max_buys else '额度内'} | {mark} |")
    table = ("| # | 日期 | 标的 | 操作 | 金额 | 额度 | 留痕 |\n"
             "|---|---|---|---|---|---|---|\n"
             + ("\n".join(rows) if rows else "| — | — | — | — | — | — | — |"))
    head = (f"**本月买入维超限 {over} 笔（上限 {s.max_buys}）**"
            if over else f"**本月无超限**（买入维 {s.buys}/{s.max_buys}）")
    tail = "\n".join([
        f"- 买入事件 **{s.buys}** 笔 / 上限 {s.max_buys}｜卖出事件 {s.sells} 笔 / 上限 {s.max_sells}"
        f"（口径见手册 §1.3；「含本笔」⇒ 第 {s.max_buys + 1} 笔起为超限）",
        f"- 留痕：本月 `decision_log` 带 `{QUOTA_TAG}` tag 的记录 **{len(tagged)}** 条"
        f"（{('、'.join('#' + str(d.get('id')) for d in tagged)) if tagged else '无'}）"
        f"｜**留痕 {len(tagged)} vs 超限 {over}** —— 差额即「超限未留痕」（本段存在的理由）",
        "- 🔴 **#C1-21 判例 4**：「**半导体回补继续被锁**」是本件（方案 A）的**已知代价，"
        "不是遗漏** —— 额度数字未动 ⇒ 超限部分不得据此补仓（**不动作 ≠ 不报告**）。",
        f"- ℹ️ 超限**自动打标**自 **{QUOTA_TAG_SINCE}** 生效（A-3「**不溯及既往**」）"
        "⇒ 本表在**该日之前月份**的「⛔ 无留痕」描述的是**当时无此机制**，"
        "⛔ **不得**据以**追溯认定历史违规**。",
    ])
    return f"{head}\n\n{table}\n\n{tail}"


def build_report(data, year, month):
    today = date.today()
    txns = month_txns(data, year, month)

    # 步骤1: 交易统计
    by_type = {}
    for t in txns:
        c = classify_txn(t)
        by_type[c] = by_type.get(c, 0) + 1
    txn_rows = "\n".join(
        f"| {t.get('date','')} | {t.get('name','')} | {t.get('op','')} | {t.get('amount','')} | {t.get('note','')} |"
        for t in txns
    ) or "| -- | -- | -- | -- | -- |"

    # 步骤5: 卫星胜率（从 ops 判断）
    sat_ops = [t for t in txns if any(k in str(t.get('name','')) for k in ['半导体','创新药','证券','芯片','光伏','TMT','高端制造','示例小盘基金','衡瑞','诺安'])]
    sat_win = sum(1 for t in sat_ops if '清仓' in t.get('op','') and '累计' in str(t.get('note','')) and '+' in str(t.get('note','')))
    sat_note = "（胜率需人工确认实际盈亏）"

    # 步骤6: 违规检查候选（关键词）
    violations = [t for t in txns if '违规' in str(t.get('note',''))]
    viol_note = f"{len(violations)} 条疑似违规" if violations else "未检测到违规关键词（需人工确认）"

    # 单 152：月操作额度·超限披露（#C1-21 方案 A-3 要求「每月显式报出」）
    quota_md = quota_disclosure(data, year, month)

    # 步骤7-辅助: 规则命中台账（noise/rule_hits.json 自动汇总）
    ledger = load_rule_ledger(f"{year}-{month:02d}")
    rule_stats = {}
    for x in ledger:
        r = str(x.get("rule", "?"))
        s = rule_stats.setdefault(r, {"triggered": 0, "protected": 0, "missed": 0, "amount": 0.0})
        s["triggered"] += 1
        if x.get("outcome") == "protected":
            s["protected"] += 1
            s["amount"] += float(x.get("amount", 0) or 0)
        elif x.get("outcome") == "missed":
            s["missed"] += 1
    rule_rows = "\n".join(
        f"| {r} | {s['triggered']} 触发 / {s['protected']} 保护 / {s['missed']} 误伤 | 保护约 ¥{s['amount']:,.0f} |"
        for r, s in sorted(rule_stats.items())
    ) or "| （本月台账暂无记录，用 noise_audit.py --log-rule 记录） | -- | -- |"

    report = f"""# ⚓ Anchor 月度归因报告 — {year}年{month}月

**报告日期**：{today.isoformat()}
**数据来源**：portfolio_data.json + mx-data · 真实盈亏以用户提供为准

---

## 一、月度总账（用户提供为准）

> ⚠️ **铁律：真实盈亏 = 用户提供为准**（勿用 mx-data 推算覆盖）。7月曾因此出错（+2,053 → 修正 -2,343）。

| 指标 | 数值 |
|------|------|
| 月初总资产 | 【用户填】 |
| 月末总资产 | 【用户填】 |
| 真实盈亏（剔除资金转入） | 【用户填】 |
| 日均盈亏 | 【用户填】 |
| 资金转入/转出 | 【用户填】 |

## 二、月度交易统计（自动）

共 **{len(txns)}** 笔：{', '.join(f'{k} {v}笔' for k,v in by_type.items()) or '无'}

| 日期 | 标的 | 操作 | 金额 | 备注 |
|------|------|------|------|------|
{txn_rows}

## 三、基准对比（mx-data 补）

| 基准 | 月度涨跌 | 组合超额 |
|------|------|------|
| 上证 | 【mx-data】 | 【计算】 |
| 科创50 | 【mx-data】 | 【计算】 |
| 沪深300 | 【mx-data】 | 【计算】 |

## 四、亏损拆解（复盘补）

- 最大亏损日 Top5：【复盘补】
- 最大盈利日 Top3：【复盘补】
- 盈亏比：【计算】

## 五、卫星胜率

本月卫星操作 **{len(sat_ops)}** 笔{sat_note}。
操作清单：【待补】

## 六、规则执行检查

| 检查项 | 结果 |
|------|------|
| 浮亏加仓 | 【确认】 |
| 72h 冻结 | 【确认】 |
| 月操作 ≤4 | {monthly_ops_summary(data, year, month)[0]}/4 笔（手动操作，定投/出入金不计） |
| DDX 负补仓 | 【确认】 |
| 溢价>3% 建仓 | 【确认】 |
| 自动扫描 | {viol_note} |

## 六·A 月操作额度 · 超限披露（自动 · 单 152 ／ #C1-21 方案 A-3）

{quota_md}

## 七、规则命中台账（自动，来自 noise/rule_hits.json）

| 规则 | 本月命中 | 保护金额 |
|------|------|------|
{rule_rows}

## 八、规则评分（1-10）

| 规则 | 评分 | 备注 |
|------|:--:|------|
| 浮亏不加仓 | | 10/10 🏆 基准 |
| -8% 止损 | | |
| 阶梯止盈 | | |
| 时间止损30天 | | |
| DDX过滤器 | | |
| 卖出冻结72h | | |

## 九、规则修正提案（三问评审）

每条新规则回答：
1. 能阻止哪段历史亏损？
2. 与现有规则冲突吗？
3. 一个月能验证吗？
→ 三过吸收 / 两过搁置 / 一过拒绝

- 【待填提案】

## 十、版本与归档

- [ ] 更新规则手册版本号 + CHANGELOG
- [ ] 更新体系总览 anchor-pro.html
- [ ] 记忆文件双向同步
- [ ] 归档旧版规则

---

*数据：mx-data · 以用户提供为准 · 投资有风险*
"""
    return report


def main():
    today = date.today()
    year, month = today.year, today.month
    if '--month' in sys.argv:
        idx = sys.argv.index('--month')
        if idx + 1 < len(sys.argv):
            parts = sys.argv[idx + 1].split('-')
            year, month = int(parts[0]), int(parts[1])

    data = load_data()
    report = build_report(data, year, month)

    # 文件归类规则: 月度归因 → 04-reviews/monthly/
    out_dir = os.path.join(KB_DIR, "monthly")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"月度归因_{year}年{month}月.md")
    if os.path.exists(out_path):
        out_path = os.path.join(out_dir, f"月度归因_{year}年{month}月_draft.md")
        print(f"[WARN] 目标归因已存在，生成草稿: {out_path}")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"[OK] 月度归因骨架已生成: {out_path}")
    print(f"     已自动统计 {len(month_txns(data, year, month))} 笔交易")
    print(f"     需用户提供: 月度总账(真实盈亏) | 需mx-data: 基准涨跌 | 需复盘: 亏损拆解")


if __name__ == '__main__':
    main()
