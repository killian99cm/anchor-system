#!/usr/bin/env python3
"""
Anchor 月度归因辅助器 (P2-2)
自动完成月度归因的步骤 1/3/5/6（从 portfolio_data.json + mx-data 可得），
步骤 2（真实盈亏）需用户提供，脚本生成待填模板。

用法:
    python gen_monthly_attribution.py                 # 本月
    python gen_monthly_attribution.py --month 2026-07 # 指定月
输出:
    04-每日复盘/月度归因_YYYY年M月.md (骨架，AI/用户补叙事)
"""
import json
import os
import sys
from datetime import date

DESKTOP = r"C:\Users\lenovo\Desktop"
DATA_PATH = os.path.join(DESKTOP, "portfolio_data.json")
KB_DIR = os.path.join(DESKTOP, "Anchor", "04-每日复盘")


def load_data():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def month_txns(data, year, month):
    """本月的所有交易记录。"""
    prefixes = [f"{year}-{month:02d}", f"{month}/"]
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
    sat_ops = [t for t in txns if any(k in str(t.get('name','')) for k in ['半导体','创新药','证券','芯片','光伏','TMT','高端制造','中证2000','衡瑞','诺安'])]
    sat_win = sum(1 for t in sat_ops if '清仓' in t.get('op','') and '累计' in str(t.get('note','')) and '+' in str(t.get('note','')))
    sat_note = "（胜率需人工确认实际盈亏）"

    # 步骤6: 违规检查候选（关键词）
    violations = [t for t in txns if '违规' in str(t.get('note',''))]
    viol_note = f"{len(violations)} 条疑似违规" if violations else "未检测到违规关键词（需人工确认）"

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
| 月操作 ≤4 | {len(txns)}/4 笔 |
| DDX 负补仓 | 【确认】 |
| 溢价>3% 建仓 | 【确认】 |
| 自动扫描 | {viol_note} |

## 七、规则评分（1-10）

| 规则 | 评分 | 备注 |
|------|:--:|------|
| 浮亏不加仓 | | 10/10 🏆 基准 |
| -8% 止损 | | |
| 阶梯止盈 | | |
| 时间止损30天 | | |
| DDX过滤器 | | |
| 卖出冻结72h | | |

## 八、规则修正提案（三问评审）

每条新规则回答：
1. 能阻止哪段历史亏损？
2. 与现有规则冲突吗？
3. 一个月能验证吗？
→ 三过吸收 / 两过搁置 / 一过拒绝

- 【待填提案】

## 九、版本与归档

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

    os.makedirs(KB_DIR, exist_ok=True)
    out_path = os.path.join(KB_DIR, f"月度归因_{year}年{month}月.md")
    if os.path.exists(out_path):
        out_path = os.path.join(KB_DIR, f"月度归因_{year}年{month}月_draft.md")
        print(f"[WARN] 目标归因已存在，生成草稿: {out_path}")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"[OK] 月度归因骨架已生成: {out_path}")
    print(f"     已自动统计 {len(month_txns(data, year, month))} 笔交易")
    print(f"     需用户提供: 月度总账(真实盈亏) | 需mx-data: 基准涨跌 | 需复盘: 亏损拆解")


if __name__ == '__main__':
    main()
