#!/usr/bin/env python3
"""Anchor Portfolio Analyzer — 一键检查组合健康度"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path

DATA = Path(r"C:\Users\lenovo\Desktop\Anchor\06-看板数据\portfolio_data.json")
if not DATA.exists():
    DATA = Path(r"C:\Users\lenovo\Desktop\portfolio_data.json")

with open(DATA, encoding='utf-8') as f:
    D = json.load(f)

H = D.get('holdings_summary', [])
S = D.get('stock_holdings', [])
total = D.get('total_assets', 0)
pnl = D.get('total_hold_pnl_est', 0)

print(f"⚓ Anchor 组合分析 · {D.get('update_date', '?')}")
print(f"总资产: ¥{total:,.0f} | 盈亏: {pnl:+,.0f}\n")

# 1. Layer classification
bedrock, core, sat, cash, pending = [], [], [], [], []
for h in H:
    mv, n, g = h.get('mv', 0), h.get('name', ''), h.get('group', '')
    if mv < 1: continue
    if g == '待结算': pending.append(h); continue
    if '余额宝' in n: cash.append(h); continue
    if g == '全局固收' or '黄金' in n or '债券' in n: bedrock.append(h)
    elif '纳斯达克' in n or '纳指' in n or '天弘通利' in n: core.append(h)
    else: sat.append(h)

for s in S:
    bedrock.append({'name': s.get('name', '红利ETF'), 'mv': s.get('mv', 0),
                    'pnl': s.get('pnl', 0), 'day_pnl': s.get('day_pnl', 0)})

bMv = sum(f.get('mv', 0) for f in bedrock)
cMv = sum(f.get('mv', 0) for f in core)
sMv = sum(f.get('mv', 0) for f in sat)
caMv = sum(f.get('mv', 0) for f in cash + pending)
tot = bMv + cMv + sMv + caMv

print("【四层金字塔】")
for name, mv, target in [("压舱石", bMv, 0.45), ("核心增长", cMv, 0.20), ("卫星进攻", sMv, 0.15), ("现金预备", caMv, 0.15)]:
    actual = mv / tot * 100 if tot else 0
    bar = '█' * int(actual / 2) + '░' * (22 - int(actual / 2))
    flag = '✅' if abs(actual/100 - target) < 0.08 else '⚠️'
    print(f"  {flag} {name}: {actual:5.1f}% (目标{target*100:.0f}%) {bar}")

# 2. Satellite risk check
print("\n【卫星层风险】")
for f in sat:
    mv, pnl = f.get('mv', 0), f.get('pnl', 0) or 0
    rate = pnl / (mv - pnl) * 100 if mv != pnl else 0
    flag = '🟢' if rate > 0 else ('🟡' if rate > -8 else '🔴 -8%止损线!')
    print(f"  {flag} {f['name'][:25]:<25} ¥{mv:>6,.0f}  {rate:+.1f}%")

# 3. Risk alerts
print("\n【风控警报】")
alerts = 0
for f in sat:
    pnl = f.get('pnl', 0) or 0
    mv = f.get('mv', 0)
    rate = pnl / (mv - pnl) * 100 if mv != pnl else 0
    if rate < -8:
        print(f"  🔴 {f['name'][:25]}: 亏损{rate:.1f}% 触发-8%止损!")
        alerts += 1

if bMv / tot < 0.40:
    print(f"  🟡 压舱石占比{bMv/tot*100:.1f}% < 40%，防御不足")
    alerts += 1
if caMv < 3000:
    print(f"  🟡 现金{caMv:.0f} < ¥3,000，低于底线")
    alerts += 1
if len(sat) > 4:
    print(f"  🟡 卫星层{len(sat)}只 > 4只上限")
    alerts += 1

if alerts == 0:
    print("  ✅ 无警报")
else:
    print(f"\n  {alerts} 个问题需要处理")

# 4. PnL summary
print(f"\n【盈亏分布】")
pos = [f for f in H if f.get('pnl', 0) > 0 and f.get('mv', 0) > 1]
neg = [f for f in H if f.get('pnl', 0) < 0 and f.get('mv', 0) > 1]
print(f"  盈利: {len(pos)}只  亏损: {len(neg)}只")
best = max(pos, key=lambda x: x.get('pnl', 0)) if pos else None
worst = min(neg, key=lambda x: x.get('pnl', 0)) if neg else None
if best: print(f"  最佳: {best['name'][:25]} +{best['pnl']:,.0f}")
if worst: print(f"  最差: {worst['name'][:25]} {worst['pnl']:,.0f}")

print("\nDone.")
