#!/usr/bin/env python3
"""Anchor Market Fetcher — A股(东方财富) + 美股(Sina) 双源实时"""
import urllib.request, json
from datetime import datetime, timezone, timedelta

now = datetime.now()
bj = now.strftime('%Y-%m-%d %H:%M')
print(f"=== Anchor Market · {bj} ===\n")

def fetch(url, parser, label):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=10)
        return parser(resp)
    except Exception as e:
        print(f"  [{label}] 连接失败")
        return None

# ===== A-Share (East Money) =====
print("【A股指数】")
em = fetch(
    "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&fields=f2,f3,f4,f12,f14&secids=1.000001,1.000688,0.399001,0.399006",
    lambda r: json.loads(r.read()),
    "A股"
)
if em and em.get('data') and em['data'].get('diff'):
    for item in em['data']['diff']:
        print(f"  {item['f14']}: {item['f2']:.2f}  {item['f3']:+.2f}%")

# A-Share sectors
print("\n【A股板块】")
em2 = fetch(
    "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&fields=f2,f3,f14&secids=90.BK1036,90.BK1106,90.BK1030,90.BK1148,90.BK1050,90.BK1025,90.BK1090",
    lambda r: json.loads(r.read()),
    "板块"
)
if em2 and em2.get('data') and em2['data'].get('diff'):
    for item in em2['data']['diff']:
        print(f"  {item['f14']}: {item['f3']:+.2f}%")

# ===== US Market (Sina) =====
print("\n【美股实时】")
us_codes = {
    'gb_ixic': '纳斯达克', 'gb_dji': '道琼斯', 'gb_inx': '标普500',
    'gb_sox': '费城半导体'
}
url = 'https://hq.sinajs.cn/list=' + ','.join(us_codes.keys())
sina = fetch(url, lambda r: r.read().decode('gbk'), "美股")
if sina:
    for line in sina.strip().split('\n'):
        parts = line.split('"')[1].split(',')
        if len(parts) > 2:
            name = us_codes.get(line.split('=')[0].split('_')[1], parts[0])
            price = float(parts[1])
            chg = float(parts[2])
            print(f"  {name}: {price:,.2f}  {chg:+.2f}%")

# ===== Key holdings indicators =====
print(f"\n=== Done · {datetime.now().strftime('%H:%M:%S')} ===")
