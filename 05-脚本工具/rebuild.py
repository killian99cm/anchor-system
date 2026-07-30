#!/usr/bin/env python3
"""
Rebuild portfolio_analysis.html from portfolio_data.json
- Fund holdings: daily PnL, cumulative, total MV, yield %, monthly return
- Asset allocation: SVG donut chart
- Trend chart: daily total return from daily_summaries
- All daily summaries displayed
"""
import json, os
from datetime import datetime

DESKTOP = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(DESKTOP, 'portfolio_data.json')

with open(DATA_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)

now = datetime.now()
update_time = now.strftime('%Y-%m-%d %H:%M')

total = data.get('total_assets', 0)
fund_acct = data.get('fund_account', 0)
stock_acct = data.get('stock_account', 0)
yuebao = data.get('yuebao', 0)

# ===== BUILD HOLDINGS =====
holdings = []
for h in data.get('holdings_summary', []):
    mv = h.get('mv', 0)
    if mv <= 0: continue
    pnl = h.get('pnl', 0)
    try: pnl = float(str(pnl).replace(',', ''))
    except: pnl = 0
    cumul = h.get('cumul', 0)
    try: cumul = float(str(cumul).replace(',', ''))
    except: cumul = 0
    day_pnl = h.get('day_pnl', 0) or 0
    try: day_pnl = float(str(day_pnl).replace(',', ''))
    except: day_pnl = 0
    day_pct = h.get('day_pct', 0) or 0
    try: day_pct = float(str(day_pct))
    except: day_pct = 0
    note = h.get('note', '')
    holdings.append({
        'name': h.get('name', '?'), 'mv': mv, 'pnl': pnl, 'cumul': cumul,
        'day_pnl': day_pnl, 'day_pct': day_pct, 'group': h.get('group', ''), 'note': note
    })

stocks = []
for s in data.get('stock_holdings', []):
    price = s.get('price', 0)
    shares = s.get('shares', 0)
    pnl = s.get('pnl', 0)
    try: pnl = float(str(pnl).replace(',', ''))
    except: pnl = 0
    stocks.append({'name': s.get('name',''), 'shares': shares, 'cost': s.get('cost',0),
                   'price': price, 'pnl': pnl, 'mv': shares*price})

total_pnl_hold = sum(h['pnl'] for h in holdings) + sum(s['pnl'] for s in stocks)

# ===== GROUPS =====
groups = {}
for h in holdings:
    g = h['group']
    if '固收' in g: g = '固收'
    elif 'QDII' in g: g = '海外 QDII'
    elif '进攻' in g: g = '进攻'
    elif '防御' in g: g = '防御'
    elif '已清仓' in g: continue
    else: g = '其他'
    groups.setdefault(g, []).append(h)

# ===== ALLOCATION =====
alloc = {}
for g, items in groups.items():
    alloc[g] = sum(h['mv'] for h in items)
for s in stocks:
    alloc['股票'] = alloc.get('股票', 0) + s['mv']
total_alloc = sum(alloc.values())
alloc_sorted = sorted(alloc.items(), key=lambda x: x[1], reverse=True)

# ===== DAILY SUMMARIES =====
ds_list = data.get('daily_summaries', [])

# Latest market
mkt = data.get('market', {})
if not mkt:
    mkt = {}
sh = mkt.get('sh', {})
kc = mkt.get('kc', {})

# ===== WATCHLIST & PENDING =====
wl = data.get('watchlist', [])
pa = data.get('pending_actions', [])
dca = data.get('dca_running', [])

# ===== BUILD HTML =====
def fpnl(v): return f'+{v:,.0f}' if v >= 0 else f'{v:,.0f}'
def fc(v): return 'green' if v >= 0 else 'red'
def fps(v): return f'+{v:.1f}%' if v >= 0 else f'{v:.1f}%'

# Holdings HTML
holdings_html = ''
for gname, items in groups.items():
    for h in items:
        yield_pct = h['pnl'] / (h['mv'] - h['pnl']) * 100 if h['mv'] != h['pnl'] else 0
        day_str = fps(h['day_pct'] * 100) if h['day_pct'] else '--'
        day_pnl_str = fpnl(h['day_pnl'])
        holdings_html += f'<div class="row" data-mv="{h["mv"]:.0f}" data-cumul="{h["cumul"]:.0f}" data-pnl="{h["pnl"]:.0f}" data-yield="{yield_pct:.1f}" data-daypct="{h["day_pct"]*100 if h["day_pct"] else 0:.1f}" data-daypnl="{h["day_pnl"]:.0f}"><span class="n" title="{h["note"]}">{h["name"]}</span><span class="v">{h["mv"]:,.0f}</span><span class="p {fc(h["cumul"])}">{fpnl(h["cumul"])}</span><span class="p {fc(h["pnl"])}">{fpnl(h["pnl"])}</span><span class="p {fc(yield_pct)}">{fps(yield_pct)}</span><span class="p {fc(h["day_pnl"])}">{day_pnl_str}</span><span class="p {fc(h["day_pct"]*100 if h["day_pct"] else 0)}">{day_str}</span></div>\n'
    holdings_html += '\n'

# Alloc HTML with bar + SVG donut
colors_donut = {'固收': '#5b8def', '海外 QDII': '#f0b030', '进攻': '#00d4a0', '防御': '#ff4d6a', '其他': '#8b8fa3', '股票': '#c084fc'}
alloc_html = ''
# Donut
cx, cy, r, lw = 120, 120, 90, 22
paths = ''
cum = 0
for gname, v in alloc_sorted:
    pct = v / total_alloc
    sa = cum * 2 * 3.14159 - 3.14159 / 2
    ea = (cum + pct) * 2 * 3.14159 - 3.14159 / 2
    x1, y1 = cx + r * __import__('math').cos(sa), cy + r * __import__('math').sin(sa)
    x2, y2 = cx + r * __import__('math').cos(ea), cy + r * __import__('math').sin(ea)
    paths += f'<path d="M{cx} {cy} L{x1:.1f} {y1:.1f} A{r} {r} 0 {1 if pct > 0.5 else 0} 1 {x2:.1f} {y2:.1f} Z" fill="{colors_donut.get(gname, "#8b8fa3")}" opacity="0.85"/>'
    cum += pct
    alloc_html += f'<div class="row"><span class="n">{gname}</span><span class="v">{pct*100:.1f}%</span><span class="v">{v:,.0f}</span></div>\n'

donut_svg = f'''<svg width="240" height="240" viewBox="0 0 240 240" style="flex-shrink:0">
  <circle cx="120" cy="120" r="90" fill="none" stroke="var(--border)" stroke-width="{lw}"/>
  {paths}
  <circle cx="120" cy="120" r="{r-lw/2-1}" fill="var(--surface)"/>
  <text x="120" y="116" text-anchor="middle" fill="#fff" font-size="22" font-weight="700" font-family="monospace">{total_alloc:,.0f}</text>
  <text x="120" y="138" text-anchor="middle" fill="var(--text3)" font-size="10" letter-spacing="1">总资产</text>
</svg>'''

# Watchlist
wl_html = ''
for w in wl:
    wl_html += f'<div class="row"><span class="n amber">{w.get("rank","")}. {w.get("sector","")}</span><span class="v">{w.get("etf","")}</span><span class="p amber">触发: {w.get("trigger","")}</span></div>\n'

# Pending
pa_html = ''
for p in pa:
    if isinstance(p, dict):
        pa_html += f'<div class="row"><span class="n">{p.get("action","")} - {p.get("name","")}</span><span class="v">{p.get("priority","")}</span></div>\n'
    else:
        pa_html += f'<div class="row"><span class="name">{p}</span></div>\n'

# Daily summaries
summary_html = ''
for d in ds_list:
    ops = ', '.join([o.get('op', '') for o in d.get('operations', [])]) or '无'
    pnl_est = d.get('portfolio_day_pnl_est', '--')
    summary_html += f'''<div class="summary-item">
<b>{d["date"]} {d.get("day","")}</b> | 上证 {d["shanghai"]["close"]}({d["shanghai"]["change"]}) | 科创50 {d["kechuang50"]["close"]}({d["kechuang50"]["change"]}) | 预估盈亏 {pnl_est}
<br>{d.get("market_note","")[:250]}
<br><span class="amber">操作: {ops}</span>
</div>\n'''

# DCA text
dca_text = ' · '.join([str(a) for a in dca]) if dca else '无'

# Chart data for JS
chart_data = data.get('chart_data', [])
if not chart_data:
    for d in ds_list:
        chart_data.append({
            'd': d.get('date', '')[5:],
            'sh': d['shanghai']['close'],
            'star': d['kechuang50']['close'],
            'pnl': float(str(d.get('portfolio_day_pnl_est', '0')).replace('+', '').replace(',', '')) if d.get('portfolio_day_pnl_est') else 0
        })

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>投资看板 · {update_time}</title>
<style>
:root{{--bg:#08090d;--surface:#0f1118;--surface2:#141820;--border:#1e2235;--text:#d4d6dc;--text2:#8b8fa3;--text3:#5c6078;--green:#00d4a0;--red:#ff4d6a;--amber:#f0b030;--accent:#5b8def}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',-apple-system,sans-serif;font-size:14px;line-height:1.5;min-height:100vh}}
body::before{{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(255,255,255,0.002)2px,rgba(255,255,255,0.002)4px),radial-gradient(ellipse at 10% 5%,rgba(91,141,239,0.06)0%,transparent 50%),radial-gradient(ellipse at 85% 90%,rgba(0,212,160,0.04)0%,transparent 50%);pointer-events:none;z-index:0}}
.app{{max-width:1520px;margin:0 auto;padding:28px 36px 60px;position:relative;z-index:1}}

.header{{display:flex;align-items:flex-end;gap:24px;margin-bottom:28px;padding-bottom:18px;border-bottom:2px solid var(--border)}}
.header h1{{font-size:24px;font-weight:700;color:#fff;letter-spacing:-0.5px}}
.header h1 span{{color:var(--amber);font-weight:400;font-size:13px;margin-left:12px;letter-spacing:0}}
.header .clock{{font-family:monospace;font-size:13px;color:var(--amber);margin-left:auto;background:rgba(240,176,48,0.06);padding:6px 16px;border-radius:4px;border:1px solid rgba(240,176,48,0.15)}}

.kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
.kpi-card{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:20px 24px;position:relative;overflow:hidden}}
.kpi-card::before{{content:'';position:absolute;top:0;left:0;width:3px;height:100%}}
.kpi-card:nth-child(1)::before{{background:var(--accent);opacity:0.6}}
.kpi-card:nth-child(2)::before{{background:var(--amber);opacity:0.6}}
.kpi-card:nth-child(3)::before{{background:var(--green);opacity:0.6}}
.kpi-card:nth-child(4)::before{{background:var(--accent);opacity:0.6}}
.kpi-label{{font-size:11px;color:var(--text3);letter-spacing:1.8px;margin-bottom:8px;text-transform:uppercase}}
.kpi-value{{font-family:monospace;font-size:28px;font-weight:700;color:#fff;line-height:1.1}}
.kpi-sub{{font-size:12px;color:var(--text2);margin-top:6px}}

.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:6px;overflow:hidden}}
.card-h{{padding:12px 20px;border-bottom:1px solid var(--border);font-size:11px;font-weight:600;letter-spacing:1.5px;color:var(--text3);text-transform:uppercase;background:var(--surface2)}}
.card-b{{padding:14px 20px;max-height:480px;overflow-y:auto}}

.row{{display:flex;align-items:center;padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.01);font-size:13px}}
.row:hover{{background:rgba(255,255,255,0.006)}}
.row .n{{flex:1;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:100px}}
.row .v{{width:95px;text-align:right;font-family:monospace;font-size:13px;color:var(--text2);flex-shrink:0}}
.row .p{{width:85px;text-align:right;font-family:monospace;font-size:13px;font-weight:600;flex-shrink:0}}
.gtitle{{font-size:11px;font-weight:600;letter-spacing:2px;color:var(--accent);padding:8px 0 2px;border-bottom:1px solid var(--border);margin-bottom:1px;text-transform:uppercase}}
.th-row{{display:flex;align-items:center;padding:4px 0 8px;border-bottom:2px solid var(--border);margin-bottom:6px;font-size:10px;color:var(--text3);letter-spacing:1.5px;font-weight:600}}
.th-row .n{{flex:1;min-width:100px}}.th-row .v{{width:95px;text-align:right;flex-shrink:0}}.th-row .p{{width:85px;text-align:right;flex-shrink:0}}
.sort-btn{{cursor:pointer;user-select:none;transition:color .2s}}.sort-btn:hover{{color:#fff}}
.gtitle{{font-size:10px;font-weight:600;letter-spacing:2px;color:var(--accent);padding:10px 0 3px;border-bottom:1px solid var(--border);margin-bottom:2px;text-transform:uppercase}}

.summary-item{{padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.02);font-size:12px;line-height:1.6;color:var(--text2)}}
.summary-item b{{color:#fff}}

.green{{color:var(--green);font-weight:600}}.red{{color:var(--red);font-weight:600}}.amber{{color:var(--amber)}}
::-webkit-scrollbar{{width:4px}}::-webkit-scrollbar-thumb{{background:var(--border);border-radius:2px}}
@media(max-width:960px){{.kpi-row{{grid-template-columns:repeat(2,1fr)}}.grid2{{grid-template-columns:1fr}}}}
.chart-wrap{{display:flex;gap:20px;align-items:center}}
</style>
</head>
<body>
<div class="app">
<div class="header"><h1>PORTFOLIO<span>投资组合看板</span></h1><div class="clock" id="clock">--</div></div>

<div class="kpi-row">
<div class="kpi-card"><div class="kpi-label">Total Assets · 总资产</div><div class="kpi-value" style="color:var(--accent)">{total:,.0f}</div><div class="kpi-sub">基金 {fund_acct:,.0f} · 股票 {stock_acct:,.0f} · 余额宝 {yuebao:,.0f}</div></div>
<div class="kpi-card"><div class="kpi-label">PnL · 持仓盈亏</div><div class="kpi-value {fc(total_pnl_hold)}">{fpnl(total_pnl_hold)}</div><div class="kpi-sub">{len(holdings)} 只基金 · {len(stocks)} 只股票 · 持有盈亏</div></div>
<div class="kpi-card"><div class="kpi-label">SSE · 上证指数</div><div class="kpi-value">{sh.get('close','--')}</div><div class="kpi-sub"><span class="{fc(1) if not str(sh.get('change','')).startswith('-') else 'red'}">{sh.get('change','--')}</span> · {mkt.get('vol','--')}</div></div>
<div class="kpi-card"><div class="kpi-label">STAR 50 · 科创50</div><div class="kpi-value">{kc.get('close','--')}</div><div class="kpi-sub">定投 {dca_text}</div></div>
</div>

<div class="card" style="margin-bottom:24px"><div class="card-h">Holdings · 持仓明细</div><div class="card-b"><div class="th-row"><span class="n sort-btn" onclick="sortTable('n')">名称 ▾</span><span class="v sort-btn" onclick="sortTable('mv')">市值 ▾</span><span class="p sort-btn" onclick="sortTable('cumul')">累计盈亏 ▾</span><span class="p sort-btn" onclick="sortTable('pnl')">持有盈亏 ▾</span><span class="p sort-btn" onclick="sortTable('yield')">收益率 ▾</span><span class="p sort-btn" onclick="sortTable('daypnl')">当日盈亏 ▾</span><span class="p sort-btn" onclick="sortTable('daypct')">日涨跌 ▾</span></div><div id="holdings-body">{holdings_html}</div></div></div>

<div class="grid2">
<div class="card"><div class="card-h">Allocation · 资产配置</div><div class="card-b"><div class="chart-wrap">{donut_svg}<div style="flex:1">{alloc_html}</div></div></div></div>
<div class="card"><div class="card-h">Trend · 走势图</div><div class="card-b"><canvas id="trendChart" style="width:100%;height:220px"></canvas><div style="text-align:center;color:var(--text3);font-size:10px;margin-top:6px">上证(金色) vs 科创50(蓝色) · 每日收盘后更新</div></div></div>
</div>
</div>

<div class="grid2">
<div class="card"><div class="card-h">Watchlist · 关注清单</div><div class="card-b">{wl_html or '暂无'}</div></div>
<div class="card"><div class="card-h">Actions · 待办</div><div class="card-b">{pa_html or '暂无'}</div></div>
</div>

<div class="card" style="margin-bottom:28px"><div class="card-h">History · 每日总结 ({len(ds_list)}条)</div><div class="card-b">{summary_html or '暂无记录'}</div></div>
</div>
</div>

<script>
var CHART_DATA = {json.dumps(chart_data, ensure_ascii=False)};

(function(){{
  var c=document.getElementById('clock');
  function t(){{c.textContent=new Date().toLocaleDateString('zh-CN',{{year:'numeric',month:'2-digit',day:'2-digit'}})+'  '+new Date().toLocaleTimeString('zh-CN',{{hour12:false}});}}
  t();setInterval(t,1000);

  var cv=document.getElementById('trendChart');
  if(!cv||CHART_DATA.length<2){{if(cv){{var cx=cv.getContext('2d');cv.width=600;cv.height=200;cx.font='13px "Segoe UI",sans-serif';cx.fillStyle='#5c6078';cx.textAlign='center';cx.fillText('走势图将在积累 2 个以上交易日数据后自动绘制',300,100);cx.fillText('每日收盘后运行 rebuild.py 更新数据',300,125);}}}}else{{
    var cx=cv.getContext('2d'),W=cv.parentElement.clientWidth-40,H=220;
    cv.width=W*2;cv.height=H*2;cv.style.width=W+'px';cv.style.height=H+'px';cx.scale(2,2);
    var pad={{top:20,r:10,b:30,l:45}},w=W-pad.l-pad.r,h=H-pad.top-pad.b;
    var shVals=CHART_DATA.map(function(d){{return d.sh;}}),starVals=CHART_DATA.map(function(d){{return d.star;}});
    var allVals=shVals.concat(starVals),minY=Math.min.apply(null,allVals)-30,maxY=Math.max.apply(null,allVals)+30;
    function y(v){{return pad.top+(maxY-v)/(maxY-minY)*h;}}
    function x(i){{return pad.l+i/(CHART_DATA.length-1)*w;}}

    cx.strokeStyle='rgba(255,255,255,0.03)';cx.lineWidth=1;
    for(var i=0;i<5;i++){{var gy=pad.top+i*h/4;cx.beginPath();cx.moveTo(pad.l,gy);cx.lineTo(pad.l+w,gy);cx.stroke();}}

    function line(key,color){{
      cx.strokeStyle=color;cx.lineWidth=2;cx.beginPath();
      CHART_DATA.forEach(function(d,i){{var px=x(i),py=y(d[key]);i===0?cx.moveTo(px,py):cx.lineTo(px,py);}});
      cx.stroke();
    }}
    line('sh','#f0b030');line('star','#5b8def');
    cx.fillStyle='#8b8fa3';cx.font='9px "Segoe UI",sans-serif';cx.textAlign='center';
    CHART_DATA.forEach(function(d,i){{cx.fillText(d.d,x(i),H-pad.b+14);}});
    cx.fillStyle='#f0b030';cx.fillRect(W-170,6,10,10);cx.fillStyle='#fff';cx.font='10px "Segoe UI",sans-serif';cx.textAlign='left';cx.fillText('上证',W-156,15);
    cx.fillStyle='#5b8def';cx.fillRect(W-110,6,10,10);cx.fillText('科创50',W-96,15);
  }}
}}());
</script>
</body>
</html>'''

html_path = os.path.join(DESKTOP, 'portfolio_analysis.html')
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

snapshot = {
    "update_time": update_time,
    "total_assets": total, "fund_account": fund_acct, "stock_account": stock_acct, "yuebao": yuebao,
    "total_hold_pnl_est": total_pnl_hold,
    "market": mkt,
    "holdings_summary": holdings, "stock_holdings": stocks,
    "dca_running": [str(a) for a in dca],
    "watchlist": wl, "pending_actions": pa, "daily_summaries": ds_list,
    "chart_data": chart_data
}
with open(os.path.join(DESKTOP, 'portfolio_snapshot.json'), 'w', encoding='utf-8') as f:
    json.dump(snapshot, f, ensure_ascii=False, indent=2)

print(f'OK - {len(html):,}B - Assets:{total:,.0f} - PnL:{total_pnl_hold:,.0f} - Funds:{len(holdings)}')