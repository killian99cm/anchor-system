#!/usr/bin/env python3
"""
Anchor 周报自动生成器 (P2-1)
从 portfolio_data.json 的 daily_summaries + transactions 自动汇总周数据，
填入周报模板骨架。AI/用户再补充市场叙事与下周计划。

用法:
    python gen_weekly_report.py                 # 本周（自动识别最近5个交易日）
    python gen_weekly_report.py --week 08-03    # 指定周起始日期
输出:
    04-reviews/weekly_report_2026_W{周数}.md
"""
import json
import os
import sys
from datetime import datetime, date, timedelta

DESKTOP = r"C:\Users\lenovo\Desktop"
DATA_PATH = os.path.join(DESKTOP, "portfolio_data.json")
KB_DIR = os.path.join(DESKTOP, "Anchor", "04-reviews")

# 周几中文
WEEK_CN = ["一", "二", "三", "四", "五", "六", "日"]


def load_data():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_week_days(data, week_start_str=None):
    """Get list of trading days for the week. Returns list of daily_summary dicts (oldest first)."""
    days = data.get('daily_summaries', [])
    if week_start_str:
        # 指定周起始，取该日期起 7 天内的记录
        try:
            ws = datetime.strptime(week_start_str, '%Y-%m-%d').date()
        except ValueError:
            ws = datetime.strptime(week_start_str, '%m-%d').date().replace(year=2026)
        we = ws + timedelta(days=6)
        filtered = []
        for d in days:
            try:
                dd = datetime.strptime(str(d.get('date', ''))[:10], '%Y-%m-%d').date()
            except ValueError:
                continue
            if ws <= dd <= we:
                filtered.append(d)
        return sorted(filtered, key=lambda x: x.get('date', ''))
    # 默认：取本周（周一到今天）的记录，并用 chart_data 补全缺失交易日
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    filtered = []
    for d in days:
        try:
            dd = datetime.strptime(str(d.get('date', ''))[:10], '%Y-%m-%d').date()
        except ValueError:
            continue
        if monday <= dd <= today:
            filtered.append(d)
    # 用 chart_data 补全本周缺失交易日（8/3、8/4... 无 daily_summaries 时）
    chart_map = {}
    prev_sh = prev_kc = None
    for c in sorted(data.get('chart_data', []), key=lambda x: x.get('d', '')):
        dd_str = c.get('d', '')
        if dd_str.startswith('08-'):
            chart_map[dd_str] = c
    for c in chart_map.values():
        dstr = f"2026-{c.get('d','')}"
        try:
            dd = datetime.strptime(dstr, '%Y-%m-%d').date()
        except ValueError:
            continue
        if not (monday <= dd <= today):
            continue
        if any(str(f.get('date',''))[:10] == dstr for f in filtered):
            continue
        # 计算涨跌幅（前一交易日收盘）
        sh_close, kc_close = c.get('sh'), c.get('star')
        if prev_sh and sh_close:
            sh_chg = f"{(sh_close/prev_sh-1)*100:+.2f}%"
        else:
            sh_chg = '--'
        if prev_kc and kc_close:
            kc_chg = f"{(kc_close/prev_kc-1)*100:+.2f}%"
        else:
            kc_chg = '--'
        filtered.append({
            "date": dstr,
            "day": WEEK_CN[dd.weekday()],
            "shanghai": {"close": sh_close, "change": sh_chg},
            "kechuang50": {"close": kc_close, "change": kc_chg},
            "volume": "--",
            "market_note": "（来自chart_data，叙事待AI补充）",
            "portfolio_day_pnl_est": c.get('pnl', 0),
            "_src": "chart"
        })
        if sh_close:
            prev_sh = sh_close
        if kc_close:
            prev_kc = kc_close
    return sorted(filtered, key=lambda x: x.get('date', ''))


def format_change(v):
    """Normalize change string like '+1.02%' or 0.0037 to display form."""
    if v is None:
        return '--'
    s = str(v)
    if s.endswith('%'):
        return s
    try:
        fv = float(s)
        return f"{fv*100:+.2f}%" if abs(fv) < 1 else f"{fv:+.2f}%"
    except ValueError:
        return s


def build_report(data, week_days):
    """Assemble report body with filled numbers."""
    today = date.today()
    # 周数 (ISO)
    iso_year, iso_week, _ = today.isocalendar()
    # 本周交易日起止
    if week_days:
        start_d = str(week_days[0].get('date', ''))[:10]
        end_d = str(week_days[-1].get('date', ''))[:10]
    else:
        start_d, end_d = '--', '--'

    # 一、市场表格
    market_rows = []
    for d in week_days:
        sh = d.get('shanghai', {})
        kc = d.get('kechuang50', {})
        date_cn = str(d.get('date', ''))[:10]
        weekday = d.get('day', '')
        note = str(d.get('market_note', ''))[:40]
        market_rows.append(
            f"| {date_cn}（{weekday}） | {sh.get('close','--')} | {format_change(sh.get('change'))} "
            f"| {kc.get('close','--')} | {format_change(kc.get('change'))} | {d.get('volume','--')} | {note} |"
        )

    # 本周累计
    if week_days:
        sh_first = week_days[0].get('shanghai', {}).get('close')
        sh_last = week_days[-1].get('shanghai', {}).get('close')
        kc_first = week_days[0].get('kechuang50', {}).get('close')
        kc_last = week_days[-1].get('kechuang50', {}).get('close')
        try:
            sh_cum = (float(sh_last) / float(sh_first) - 1) * 100
            kc_cum = (float(kc_last) / float(kc_first) - 1) * 100
            sh_cum_s, kc_cum_s = f"{sh_cum:+.1f}%", f"{kc_cum:+.1f}%"
        except (TypeError, ValueError, ZeroDivisionError):
            sh_cum_s, kc_cum_s = '--', '--'
    else:
        sh_cum_s, kc_cum_s = '--', '--'

    # 二、组合表现
    total = data.get('total_assets', 0)
    total_pnl = data.get('total_hold_pnl_est', 0)
    # 周盈亏 = 最近 day_pnl 之和（粗略）
    week_pnl = sum(_parse_pnl(d.get('portfolio_day_pnl_est')) for d in week_days)
    # 本周操作
    week_txns = [t for t in data.get('transactions', []) if _txn_in_week(t.get('date', ''), week_days)]
    week_ops = [t.get('op', '') for t in week_txns]
    week_ops_desc = "、".join(week_ops) if week_ops else "无"
    aug_ops = sum(1 for t in data.get('transactions', []) if str(t.get('date','')).startswith('2026-08') or str(t.get('date','')).startswith('8/'))
    violations = sum(1 for t in data.get('transactions', []) if '违规' in str(t.get('note','')))

    # 四层占比
    holdings = data.get('holdings_summary', [])
    mv = lambda g: sum(h.get('mv',0) or 0 for h in holdings if h.get('group')==g)
    bed, core, sat, cash = mv('全局固收'), mv('核心增长')+mv('全局QDII'), mv('进攻组合'), mv('现金预备')
    tot = bed + core + sat + cash
    pct = lambda v: round(v/tot*100) if tot else 0

    # 三、逐持仓
    holding_rows = []
    name_map = {
        "鹏华畅享债券C": "鹏华债券C", "中银稳健增利债券A": "中银债券A",
        "华泰柏瑞上证红利ETF联接A": "515180红利", "国泰黄金ETF联接A": "黄金ETF A",
        "天弘纳斯达克100指数(QDII)C": "纳指C", "华泰柏瑞纳斯达克100ETF联接A": "纳指A",
        "天弘通利混合A": "天弘通利A", "易方达恒生港股通创新药ETF联接C": "创新药C",
        "易方达证券ETF联接C": "证券ETF C", "华夏国证半导体芯片ETF联接C": "半导体C",
        "余额宝": "余额宝",
    }
    for h in holdings:
        if h.get('mv',0) <= 0:
            continue
        nm = name_map.get(h['name'], h['name'][:8])
        dp = h.get('day_pnl', 0)
        note = ""
        if "创新药" in h['name']:
            note = "⏳ 8/20时间止损"
        elif "证券" in h['name']:
            note = "PB 观察"
        elif "半导体" in h['name']:
            note = "DDX 观察"
        holding_rows.append(
            f"| {nm} | {h['mv']:,.0f} | {dp:+,.0f} | {h.get('pnl',0):+,.0f} | {note} |"
        )
    stock_mv = sum(s.get('mv',0) or 0 for s in data.get('stock_holdings',[]))
    if stock_mv:
        holding_rows.append(f"| 515180红利 | {stock_mv:,.0f} | -- | -- | |")

    # 创新药倒计时
    try:
        remaining = (date(2026, 8, 20) - today).days
    except Exception:
        remaining = '--'

    # 组装
    market_table = "\n".join(market_rows) if market_rows else "| -- | -- | -- | -- | -- | -- | -- |"
    report = f"""# 📊 Anchor 周报 — 第{iso_week}周（{start_d} 至 {end_d}）

**报告日期**：{today.isoformat()}
**覆盖交易日**：{start_d}（{WEEK_CN[date.fromisoformat(start_d).weekday()] if start_d!='--' else '-'}）至 {end_d}（{WEEK_CN[date.fromisoformat(end_d).weekday()] if end_d!='--' else '-'}）
**系统版本**：v3.3
**下次周报**：{today + timedelta(days=7)}

---

## 一、📈 市场全景

### A股本周走势

| 日期 | 上证 | 涨跌 | 科创50 | 涨跌 | 成交额 | 关键事件 |
|------|------|------|------|------|------|------|
{market_table}

**本周累计**：上证 {sh_cum_s}，科创50 {kc_cum_s}

### 核心叙事

> **【补充一句话概括本周主线】**：3-5 句展开 —— 反弹/下跌驱动、主力资金动向、量能变化、板块轮动

### 美股（影响传导）

| 指标 | 本周表现 | 影响 |
|------|------|------|
| 纳斯达克100 | 【待查】 | 🟡 影响纳指QDII净值 |
| COMEX黄金 | 【待查】 | 影响黄金ETF |
| 美元指数 | 【待查】 | 影响QDII/黄金 |

---

## 二、💼 组合表现

### 总体

| 指标 | 数值 | 对比上周 |
|------|------|------|
| 总资产 | ¥{total:,.0f} | 【对比】 |
| 本周盈亏 | ¥{week_pnl:+,.0f} |  |
| 持有盈亏 | {total_pnl:+,.0f} |  |
| 四层占比 | 压舱石 {pct(bed)}% / 核心 {pct(core)}% / 卫星 {pct(sat)}% / 现金 {pct(cash)}% | 目标 45/20/20/15 |
| 本周操作 | {len(week_txns)}笔（{week_ops_desc}） | 月限 4 笔 |
| 违规次数 | {violations}次 |  |

### 逐持仓周度表现

| 持仓 | 市值 | 周涨跌 | 浮盈亏 | 备注 |
|------|------|------|------|------|
{chr(10).join(holding_rows)}

### 周度归因（跑赢/跑输）

> **组合本周 {week_pnl:+,.0f}（【X%】）** vs 上证 / 科创50。【补充跑赢或跑输原因】

---

## 三、🛡️ 纪律检查

| 检查项 | 结果 |
|------|------|
| 月操作数 | {aug_ops} / 4 笔 |
| 违规操作 | {violations} 次（明细：） |
| 浮亏加仓 | 【待确认】 |
| 72h 冻结 | 【待确认】 |
| 定投执行 | 黄金15/天 ✅ · 纳指10/天 ✅ |

---

## 四、📋 待办与规则警报

| 优先级 | 事项 | 状态 |
|:--:|------|------|
| 🔴 | 半导体 DDX 连2日为正 → 补仓 | 观察 |
| 🔴 | 纳指ETF溢价率 ≤3% → 建仓 | 当前 ~10-12%，冻结 |
| 🔴 | 创新药 8/20 时间止损评估 | 倒计时 {remaining} 天 |
| 🟡 | 证券ETF PB<1.35 → +500 | 观察 |
| 🟡 | 固态电池/机器人回调到位 → ¥300试探 | 观察 |
| 📅 | 9月贷款注入方案细化 | 9月中 |

---

## 五、💡 下周计划

- [ ] 【事项1】
- [ ] 【事项2】
- [ ] 【事项3】

---

*数据：mx-data · 以用户提供为准 · 投资有风险*
"""
    return report


def _parse_pnl(v):
    if v is None:
        return 0
    s = str(v).replace('+', '').replace(',', '').replace('¥', '').strip()
    try:
        return float(s)
    except ValueError:
        return 0


def _txn_in_week(date_str, week_days):
    """Check if a transaction date falls within the week's trading days."""
    if not week_days:
        return False
    dates = [str(d.get('date', ''))[:10] for d in week_days]
    # 交易日期格式 '2026-08-07' 或 '8/7'
    for dd in dates:
        try:
            iso = dd
        except Exception:
            continue
        # 简式 '8/7' → '2026-08-07'
        if date_str[:2] == '8/' and iso.startswith('2026-08-0'):
            day_num = int(date_str.split('/')[1].split()[0])
            iso_day = int(iso[-2:])
            if day_num == iso_day:
                return True
        if date_str.startswith(iso):
            return True
    return False


def main():
    week_start = None
    if '--week' in sys.argv:
        idx = sys.argv.index('--week')
        if idx + 1 < len(sys.argv):
            week_start = sys.argv[idx + 1]

    data = load_data()
    week_days = get_week_days(data, week_start)

    if not week_days:
        print("[WARN] 未找到该周交易数据")
        # 仍生成骨架
    report = build_report(data, week_days)

    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    os.makedirs(KB_DIR, exist_ok=True)
    # 命名对齐既有规范：weekly_report_YYYYMM_W{月内周数}.md（如 202608_W1）
    # 月内周数 = 本周一所在日期在本月的第几个"周段"（按7天分）
    monday = today - timedelta(days=today.weekday())
    week_of_month = (monday.day - 1) // 7 + 1
    out_path = os.path.join(KB_DIR, f"weekly_report_{iso_year}{today.month:02d}_W{week_of_month}.md")
    # 防覆盖：若目标文件已存在（如已有人工周报），生成 _draft 待审版
    if os.path.exists(out_path):
        out_path = os.path.join(
            KB_DIR,
            f"weekly_report_{iso_year}{today.month:02d}_W{week_of_month}_draft.md"
        )
        print(f"[WARN] 目标周报已存在，生成草稿: {out_path}")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"[OK] 周报已生成: {out_path}")
    print(f"     覆盖 {len(week_days)} 个交易日")
    print(f"     请补充: 核心叙事、美股、归因、下周计划")


if __name__ == '__main__':
    main()
