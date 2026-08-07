#!/usr/bin/env python3
"""Anchor Portfolio Analyzer v2 — 完整组合健康检查 + 规则检查 + 时间止损"""
import json, sys, io, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path

DATA = Path(r"C:\Users\lenovo\Desktop\portfolio_data.json")
if not DATA.exists():
    DATA = Path(r"C:\Users\lenovo\Desktop\Anchor\06-dashboard\portfolio_data.json")

with open(DATA, encoding="utf-8") as f:
    D = json.load(f)

H = D.get('holdings_summary', [])
S = D.get('stock_holdings', [])
total = D.get('total_assets', 0)
pnl = D.get('total_hold_pnl_est', 0)
today = datetime.date.today()

print(f"⚓ Anchor 组合分析 · {D.get('update_date','?')} · 今天 {today}")
print(f"总资产 ¥{total:,.0f} | 盈亏 {pnl:+,.0f}\n")

# 1. Layer classification
bedrock, core, sat, cash = [], [], [], []
for h in H:
    mv, n, g = h.get('mv', 0), h.get('name', ''), h.get('group', '')
    if mv < 1 or g in ('已清仓', '待结算'): continue
    if '余额宝' in n: cash.append(h); continue
    if g == '全局固收' or '黄金' in n or '债券' in n: bedrock.append(h)
    elif '纳斯达克' in n or '纳指' in n or '天弘通利' in n: core.append(h)
    else: sat.append(h)
for s in S:
    bedrock.append({'name': s.get('name','红利ETF'), 'mv': s.get('mv',0), 'pnl': s.get('pnl',0), 'day_pnl': s.get('day_pnl',0)})

bMv = sum(f.get('mv',0) for f in bedrock)
cMv = sum(f.get('mv',0) for f in core)
sMv = sum(f.get('mv',0) for f in sat)
caMv = sum(f.get('mv',0) for f in cash)
tot = bMv + cMv + sMv + caMv

print("【四层金字塔】")
for name, mv, target in [("压舱石", bMv, 0.45), ("核心增长", cMv, 0.20), ("卫星进攻", sMv, 0.20), ("现金预备", caMv, 0.15)]:
    actual = mv / tot * 100 if tot else 0
    bar = '█' * int(actual/2) + '░' * (22 - int(actual/2))
    flag = '✅' if abs(actual/100 - target) < 0.08 else '⚠️'
    print(f"  {flag} {name}: {actual:5.1f}% (目标{target*100:.0f}%) {bar}")

# 2. Satellite rule check
print("\n【卫星层规则检查】")
alerts = 0
for f in sat:
    mv, pv = f.get('mv',0), f.get('pnl',0) or 0
    rate = pv / (mv - pv) * 100 if mv != pv else 0
    if rate < -8: flag = "🔴 -8%止损线!"; alerts += 1
    elif rate < 0: flag = "🟡 浮亏不加仓"
    elif rate >= 10: flag = "🟢 可阶梯止盈"
    else: flag = "🟢 健康"
    print(f"  {flag} {f['name'][:25]:<25} ¥{mv:>6,.0f}  {rate:+6.1f}%")

# 3. Time stop-loss check (v3.3)
print("\n【时间止损检查 (30天)】")
tx_by_fund = {}
for tx in D.get('transactions', []):
    name = tx.get('name','')
    tx_by_fund.setdefault(name, []).append(tx.get('date',''))

for f in sat:
    name = f.get('name','')
    # Fuzzy match: find buy tx by keyword match
    buys = []
    for txname, dates in tx_by_fund.items():
        if txname[:6] in name or name[:6] in txname:
            for d in dates:
                if d and len(str(d)) >= 10:
                    buys.append(str(d))
    if buys:
        buys.sort()
        last_buy = buys[-1][:10]
        try:
            buy_date = datetime.datetime.strptime(last_buy, "%Y-%m-%d").date()
            days = (today - buy_date).days
            mv, pv = f.get('mv',0), f.get('pnl',0) or 0
            rate = pv / (mv - pv) * 100 if mv != pv else 0
            if days >= 30 and rate < 0:
                print(f"  🔴 {name[:25]}: 持有{days}天 亏损{rate:.1f}% → 触发时间止损!")
                alerts += 1
            elif days >= 20:
                print(f"  🟡 {name[:25]}: 持有{days}天 接近30天线")
            else:
                print(f"  🟢 {name[:25]}: 持有{days}天 正常")
        except:
            print(f"  🟡 {name[:25]}: 日期解析失败")
    else:
        print(f"  ⚪ {name[:25]}: 无买入记录")

# 4. Month operation count
print("\n【操作频率】")
cur_month = today.strftime("%Y-%m")
month_ops = 0
for tx in D.get('transactions', []):
    if str(tx.get('date','')).startswith(cur_month):
        month_ops += 1
flag = "✅" if month_ops <= 4 else "🔴"
print(f"  {flag} 本月操作 {month_ops} 笔 / 上限4笔")

# 5. Cash reserve check
print("\n【现金与风控】")
print(f"  余额宝 ¥{caMv:,.0f} {'✅' if caMv>=3000 else '🔴 低于¥3,000底线'}")
print(f"  组合最大回撤: 待月度归因计算")

# 6. Summary
print("\n【汇总】")
if alerts == 0:
    print("  ✅ 无规则警报")
else:
    print(f"  🔴 {alerts} 个警报需处理")
print("  ✅ 运行完成")
