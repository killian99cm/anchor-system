#!/usr/bin/env python3
"""Anchor Daily Report — 完整版，含操作建议"""
import json, os, urllib.request, urllib.parse
from datetime import datetime

now = datetime.now()
bj = now.strftime('%Y-%m-%d %H:%M')
date_str = now.strftime('%Y-%m-%d')

# ===== MX data =====
key = os.environ.get('MX_APIKEY', '')
if not key:
    print("No MX_APIKEY")
    exit(1)

def mx(query):
    url = 'https://mkapi2.dfcfs.com/api/v1/data/search'
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'}
    body = json.dumps({"query": query}).encode('utf-8')
    try:
        req = urllib.request.Request(url, data=body, headers=headers)
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        return None

# Pull indices
idx = mx("上证指数 科创50 最新价 涨跌幅 成交额")
sh_price, sh_chg, kc_price, kc_chg = '--', '--', '--', '--'
if idx:
    for tbl in idx.get('data', {}).get('dataTableDTOList', []):
        n = tbl.get('entityName', '')
        t = tbl.get('table', {})
        if '上证' in n:
            v = t.get('f2', []); c = t.get('f3', [])
            sh_price = f"{v[0]:.0f}" if v else '--'
            sh_chg = f"{c[0]:+.2f}%" if c else '--'
        elif '科创50' in n:
            v = t.get('f2', []); c = t.get('f3', [])
            kc_price = f"{v[0]:.0f}" if v else '--'
            kc_chg = f"{c[0]:+.2f}%" if c else '--'

# Pull sectors
sec = mx("半导体 创新药 证券 黄金 最新涨跌幅 主力资金净流入")
sectors = {}
if sec:
    for tbl in sec.get('data', {}).get('dataTableDTOList', []):
        n = tbl.get('entityName', '')
        t = tbl.get('table', {})
        chg = t.get('f3', [])
        if chg:
            for kw in ['半导体', '创新药', '证券', '黄金']:
                if kw in n:
                    sectors[kw] = f"{chg[0]:+.2f}%"

# ===== Try to read portfolio =====
pf_paths = [
    '06-dashboard/portfolio_data.json',
    'Anchor/06-dashboard/portfolio_data.json',
    'portfolio_data.json'
]
pf = None
for p in pf_paths:
    if os.path.exists(p):
        pf = json.load(open(p, encoding='utf-8'))
        break

pnl_str = ''
if pf:
    total = pf.get('total_assets', 0)
    pnl = pf.get('total_hold_pnl_est', 0)
    pnl_str = f"\n💰 总资产 ¥{total/10000:.2f}万 | 盈亏 {pnl:+.0f}"

# ===== Anchor Rule Engine =====
suggestions = []
alerts = []

if pf:
    H = pf.get('holdings_summary', [])
    for h in H:
        mv = h.get('mv', 0)
        pnl = h.get('pnl', 0) or 0
        dp = h.get('day_pnl', 0) or 0
        n = h.get('name', '')
        g = h.get('group', '')
        if mv < 1 or g == '已清仓' or '余额宝' in n:
            continue

        rate = pnl / (mv - pnl) * 100 if mv != pnl else 0

        # Anchor rules per fund
        if '债券' in n or '红利' in n or g == '全局固收':
            continue  # bedrock, no suggestion needed

        if rate < -8:
            alerts.append(f"🔴 {n[:20]}: {rate:.1f}% 触发-8%止损线！")
        elif rate < 0:
            suggestions.append(f"🟡 {n[:20]}: 浮亏{rate:.1f}%，不加仓")
        elif rate > 0 and rate < 3:
            suggestions.append(f"🟢 {n[:20]}: 盈利{rate:.1f}%，持有")
        else:
            suggestions.append(f"🟢 {n[:20]}: 盈利{rate:.1f}%，可考虑止盈")

sug_text = '\n'.join(suggestions[:6]) if suggestions else '📌 全部持有不动'
alrt_text = '\n'.join(alerts[:3]) if alerts else '✅ 无止损触发'

# ===== Build report =====
report = f"""⚓ Anchor · {date_str} 每日报告
━━━━━━━━━━━━━━━━━━
【大盘】
上证 {sh_price} ({sh_chg})
科创50 {kc_price} ({kc_chg})
━━━━━━━━━━━━━━━━━━
【板块涨跌】
半导体 {sectors.get('半导体','--')}
创新药 {sectors.get('创新药','--')}
证券 {sectors.get('证券','--')}
黄金 {sectors.get('黄金','--')}{pnl_str}
━━━━━━━━━━━━━━━━━━
【Anchor规则判断】
{sug_text}
━━━━━━━━━━━━━━━━━━
【止损警报】
{alrt_text}
━━━━━━━━━━━━━━━━━━
【定投】黄金¥15+纳指¥10+天弘通利周定投
⚠️ 浮亏不加仓 | 卖出冻结72h | 月操作≤4笔
━━━━━━━━━━━━━━━━━━
📱 回复持仓数据，获取完整逐只分析
"""

print(report)

# ===== Server酱 push =====
sk = os.environ.get('SERVER_KEY', '')
if sk:
    try:
        d = urllib.parse.urlencode({
            'title': f'Anchor · {date_str} 完整报告',
            'desp': report
        }).encode('utf-8')
        urllib.request.urlopen(
            urllib.request.Request(f'https://sctapi.ftqq.com/{sk}.send', data=d),
            timeout=10
        )
        print("-> 微信已推送")
    except Exception as e:
        print(f"-> 推送失败: {e}")

os.makedirs('Anchor/04-reviews', exist_ok=True)
os.makedirs('04-reviews', exist_ok=True)
for d in ['Anchor/04-reviews', '04-reviews']:
    try:
        with open(f'{d}/brief_{date_str}.md', 'w', encoding='utf-8') as f:
            f.write(report)
    except:
        pass
