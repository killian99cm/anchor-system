#!/usr/bin/env python3
"""
Anchor v3.3 Premium 投资看板生成器
从 portfolio_data.json 生成 premium 级 portfolio_analysis.html + portfolio_snapshot.json
"""
import json, os
from datetime import datetime, date

# ===== PATHS =====
DESKTOP = r"C:\Users\lenovo\Desktop"
ANCHOR_DATA = r"C:\Users\lenovo\Desktop\Anchor\06-看板数据"
DATA_PATH = os.path.join(DESKTOP, "portfolio_data.json")
HTML_PATH = os.path.join(DESKTOP, "portfolio_analysis.html")
HTML_PATH2 = os.path.join(ANCHOR_DATA, "portfolio_analysis.html")
SNAPSHOT_PATH = os.path.join(DESKTOP, "portfolio_snapshot.json")
SNAPSHOT_PATH2 = os.path.join(ANCHOR_DATA, "portfolio_snapshot.json")

with open(DATA_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)

now = datetime.now()
update_time = now.strftime('%Y-%m-%d %H:%M:%S')

# ===== ANCHOR LAYER MAPPING =====
ANCHOR_MAP = {
    "鹏华畅享债券C": ("bedrock", "永远不卖", "tag-b"),
    "中银稳健增利债券A": ("bedrock", "永远不卖", "tag-b"),
    "国泰黄金ETF联接A": ("bedrock", "定投中", "tag-a"),
    "华泰柏瑞纳斯达克100ETF联接A": ("core", "定投 10/天", "tag-g"),
    "天弘纳斯达克100指数(QDII)C": ("core", "QDII", "tag-g"),
    "天弘通利混合A": ("core", "偏压舱石", "tag-b"),
    "易方达恒生港股通创新药ETF联接C": ("sat", "13天倒计时", "tag-a"),
    "易方达证券ETF联接C": ("sat", "PB1.32", "tag-a"),
    "华夏国证半导体芯片ETF联接C": ("sat", "DDX暂停", "tag-r"),
    "余额宝": ("cash", "现金预备", "tag-g"),
}

def fp(v): return f"+{v:,.0f}" if v >= 0 else f"{v:,.0f}"
def fc(v): return "g" if v >= 0 else "r"

# ===== Process holdings =====
raw = data.get('holdings_summary', [])
stocks = data.get('stock_holdings', [])

bedrock, core, sat, cash = [], [], [], []

for h in raw:
    name = h.get('name', '')
    mv = h.get('mv', 0) or 0
    if mv <= 0: continue
    layer_info = ANCHOR_MAP.get(name)
    if not layer_info: continue
    layer, tag, tc = layer_info
    pnl = float(str(h.get('pnl', 0)).replace(',', ''))
    dp = float(str(h.get('day_pnl', 0) or 0).replace(',', ''))
    item = {"n": name, "mv": round(mv, 2), "pnl": round(pnl, 2),
            "dp": round(dp, 2), "tag": tag, "tc": tc}
    if layer == 'bedrock': bedrock.append(item)
    elif layer == 'core': core.append(item)
    elif layer == 'sat': sat.append(item)
    elif layer == 'cash': cash.append(item)

# Add stock
for s in stocks:
    price = s.get('price', 0); shares = s.get('shares', 0)
    mv = shares * price
    pnl = float(str(s.get('pnl', 0)).replace(',', ''))
    dp = float(str(s.get('day_pnl', 0) or 0).replace(',', ''))
    bedrock.append({"n": s.get('name', '515180'), "mv": round(mv, 2),
                    "pnl": round(pnl, 2), "dp": round(dp, 2),
                    "tag": "永远不卖", "tc": "tag-b", "st": 1})

# ===== Compute totals =====
bedrock_mv = sum(i['mv'] for i in bedrock)
core_mv = sum(i['mv'] for i in core)
sat_mv = sum(i['mv'] for i in sat)
cash_mv = sum(i['mv'] for i in cash)
fund_mv_total = bedrock_mv + core_mv + sat_mv
total = bedrock_mv + core_mv + sat_mv + cash_mv
stock_mv = sum(i['mv'] for i in bedrock if i.get('st'))
total_pnl = sum(i['pnl'] for i in bedrock + core + sat + cash)

# ===== Market =====
mkt = data.get('market', {})
sh = mkt.get('sh', {})
kc = mkt.get('kc', {})
dca_list = [str(d) for d in data.get('dca_running', [])]

# ===== Watchlist & Pending =====
wl = data.get('watchlist', [])
pa = data.get('pending_actions', [])

# ===== Rule checks =====
rules = []
sat_total = sum(i['mv'] for i in sat)
for item in sat:
    r = item['pnl'] / (item['mv'] - item['pnl']) * 100 if item['mv'] != item['pnl'] else 0
    if r <= -8:
        rules.append({"lv": "rr", "t": f"{item['n'][:12]} 浮亏 {r:.1f}% 触发 -8% 止损线！"})

rules.append({"lv": "rr", "t": "半导体 DDX = -0.016（8/6转负）-> 补仓暂停，等待 DDX 连2日为正"})
rules.append({"lv": "rr", "t": "纳指ETF溢价率 ~10-12% -> 不建仓，等待溢价率 <= 3%"})
rules.append({"lv": "ra", "t": "创新药时间止损倒计时：8月20日截止（剩13天），当前浮亏 -4.0%"})
dd_pct = (total - 37535) / 37535 * 100  # old peak reference
if dd_pct <= -15:
    rules.append({"lv": "rr", "t": f"总资产回撤 {dd_pct:.1f}% 触发 -15% 线！核心增长减 1/3"})
elif dd_pct <= -10:
    rules.append({"lv": "rr", "t": f"总资产回撤 {dd_pct:.1f}% 触发 -10% 线！卫星全部清仓"})
elif dd_pct <= -5:
    rules.append({"lv": "ra", "t": f"总资产回撤 {dd_pct:.1f}% 触发 -5% 线！卫星仓位减半"})
else:
    rules.append({"lv": "rg", "t": f"总资产距 -5% 回撤线 31,313 还有 {total - 31313:,.0f} 安全垫"})
rules.append({"lv": "rg", "t": "8月操作 0/4 笔 · 零违规 · 纪律满分"})

# ===== Risk matrix =====
risks = [
    {"l": "red", "n": "半导体DDX转负", "d": "主力-20.73亿净流出", "c": "r"},
    {"l": "red", "n": "纳指ETF高溢价", "d": "溢价率~10-12%", "c": "r"},
    {"l": "red", "n": "科创50主力流出", "d": "DDX=-0.089，连续3日", "c": "r"},
    {"l": "amber", "n": "创新药时间压力", "d": "距8/20剩13天", "c": "a"},
    {"l": "amber", "n": "成交量萎缩", "d": "2.66->1.17万亿", "c": "a"},
    {"l": "amber", "n": "黄金短期过热", "d": "两日+4.5%", "c": "a"},
    {"l": "green", "n": "固收稳定产出", "d": "债券+黄金正收益", "c": "g"},
    {"l": "green", "n": "纪律执行满分", "d": "8月零操作零违规", "c": "g"},
]

# ===== Daily summaries (compact) =====
ds_out = []
for d in data.get('daily_summaries', [])[:13]:
    ops = " · ".join([o.get('op', '') for o in d.get('operations', [])]) or "无"
    sh_d = d.get('shanghai', {})
    kc_d = d.get('kechuang50', {})
    ds_out.append({
        "dt": d.get('date', '')[:10],
        "dy": d.get('day', ''),
        "sh": str(sh_d.get('close', '--')),
        "sc": str(sh_d.get('change', '--')),
        "kc": str(kc_d.get('close', '--')),
        "kcc": str(kc_d.get('change', '--')),
        "pnl": str(d.get('portfolio_day_pnl_est', '--')),
        "note": d.get('market_note', '')[:200],
        "ops": ops
    })

# ===== Chart data =====
chart_out = []
for c in data.get('chart_data', []):
    chart_out.append({
        "d": c.get('d', ''),
        "sh": round(c.get('sh', 0)),
        "st": round(c.get('star', 0)),
        "pnl": round(float(str(c.get('pnl', 0)).replace(',', '')), 0)
    })

# ===== Build embedded JSON =====
embed = {
    "time": update_time,
    "total": round(total, 2),
    "fundMv": round(fund_mv_total, 2),
    "cashMv": round(cash_mv, 2),
    "stockMv": round(stock_mv, 2),
    "totalPnl": round(total_pnl, 2),
    "mkt": mkt,
    "dca": dca_list,
    "bedrock": bedrock,
    "core": core,
    "sat": sat,
    "cash": cash,
    "rules": rules,
    "wl": wl,
    "pa": pa,
    "risks": risks,
    "ds": ds_out,
    "chart": chart_out
}

embed_json = json.dumps(embed, ensure_ascii=False)

# ===== PREMIUM HTML =====
html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Anchor v3.3 · 投资看板</title>
<style>
:root{{
  --bg:#02070f; --bg2:#060d1a; --bg3:#0a1226; --bg4:#0d1630;
  --border:#111d38; --border2:#162544; --border3:#1b2d52;
  --text:#cdd6e8; --text2:#738099; --text3:#3d4b66;
  --accent:#4d8af0; --accent2:#3570d8; --accentg:rgba(77,138,240,0.12);
  --green:#00d69e; --green2:#00b888; --greeng:rgba(0,214,158,0.10);
  --amber:#f0a830; --amber2:#d49520; --amberg:rgba(240,168,48,0.10);
  --red:#f04668; --red2:#d03050; --redg:rgba(240,70,104,0.10);
  --purple:#9b7cf0; --purpleg:rgba(155,124,240,0.10);
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  background:var(--bg); color:var(--text);
  font-family:"Inter","Segoe UI",system-ui,-apple-system,sans-serif;
  font-size:13px; line-height:1.5; min-height:100vh;
  -webkit-font-smoothing:antialiased;
}}
body::before{{
  content:''; position:fixed; inset:0; z-index:0; pointer-events:none;
  background:
    radial-gradient(ellipse at 15% 0%,rgba(77,138,240,0.05)0%,transparent 55%),
    radial-gradient(ellipse at 85% 100%,rgba(0,214,158,0.03)0%,transparent 55%),
    radial-gradient(ellipse at 50% 50%,rgba(240,168,48,0.02)0%,transparent 70%);
}}
.app{{max-width:1600px;margin:0 auto;padding:20px 28px 50px;position:relative;z-index:1}}

.header{{
  display:flex;align-items:center;gap:14px;margin-bottom:18px;
  padding:14px 20px;background:var(--bg2);border:1px solid var(--border);
  border-radius:10px;
}}
.header .logo{{font-size:20px;font-weight:800;color:#fff;letter-spacing:-0.5px;display:flex;align-items:center;gap:7px}}
.header .logo .icon{{font-size:24px}}
.header .logo em{{font-style:normal;color:var(--accent)}}
.header .ver{{font-size:9px;background:var(--accentg);color:var(--accent);padding:2px 9px;border-radius:8px;letter-spacing:1px;font-weight:600;border:1px solid rgba(77,138,240,0.18)}}
.header .mkt-status{{font-size:9px;padding:3px 10px;border-radius:6px;letter-spacing:1px;font-weight:600}}
.header .mkt-status.closed{{background:rgba(240,70,104,0.08);color:var(--red);border:1px solid rgba(240,70,104,0.15)}}
.header .spacer{{flex:1}}
.header .top-stat{{font-size:10px;color:var(--text2);text-align:right;line-height:1.4}}
.header .top-stat b{{color:#fff;font-family:"JetBrains Mono","Cascadia Code",Consolas,monospace;font-size:12px}}
.header .clock{{font-family:"JetBrains Mono","Cascadia Code",Consolas,monospace;font-size:11px;color:var(--amber);background:var(--amberg);padding:5px 14px;border-radius:6px;border:1px solid rgba(240,168,48,0.12);white-space:nowrap}}

.kpi-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px}}
.kpi{{
  background:var(--bg2);border:1px solid var(--border);border-radius:9px;
  padding:15px 18px;position:relative;overflow:hidden;transition:all .2s;cursor:default
}}
.kpi:hover{{transform:translateY(-2px);border-color:var(--border2);box-shadow:0 4px 20px rgba(0,0,0,0.3)}}
.kpi::after{{content:'';position:absolute;top:0;left:0;width:100%;height:2px}}
.kpi:nth-child(1)::after{{background:linear-gradient(90deg,var(--accent),transparent)}}
.kpi:nth-child(2)::after{{background:linear-gradient(90deg,var(--green),transparent)}}
.kpi:nth-child(3)::after{{background:linear-gradient(90deg,var(--amber),transparent)}}
.kpi:nth-child(4)::after{{background:linear-gradient(90deg,var(--accent),transparent);opacity:0.5}}
.kpi:nth-child(5)::after{{background:linear-gradient(90deg,var(--purple),transparent)}}
.kpi .kl{{font-size:8px;color:var(--text3);letter-spacing:2.2px;margin-bottom:5px;text-transform:uppercase}}
.kpi .kv{{font-family:"JetBrains Mono","Cascadia Code",Consolas,monospace;font-size:22px;font-weight:800;color:#fff;line-height:1.1}}
.kpi .kv .ku{{font-size:11px;font-weight:400;opacity:0.4;margin-left:1px}}
.kpi .ks{{font-size:10px;color:var(--text2);margin-top:5px;line-height:1.4}}

.pyr-row{{display:grid;grid-template-columns:230px 1fr;gap:10px;margin-bottom:16px}}
.pyr-viz{{
  background:var(--bg2);border:1px solid var(--border);border-radius:9px;
  padding:18px 14px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px
}}
.pyr-viz h3{{font-size:9px;color:var(--text3);letter-spacing:2.5px;margin-bottom:12px;text-transform:uppercase}}
.pyr-layer{{
  width:100%;text-align:center;padding:9px 6px;border-radius:5px;
  font-size:9px;font-weight:600;transition:all .25s;cursor:default;position:relative
}}
.pyr-layer:hover{{transform:translateX(4px);filter:brightness(1.3)}}
.pyr-layer .pv{{font-size:16px;font-weight:800}}
.pyr-layer .pl{{font-size:7px;opacity:0.55;letter-spacing:1px;margin-top:2px}}
.pyr-layer .pb{{font-size:8px;opacity:0.45;margin-top:2px}}
.pyr-layer.bed{{background:rgba(77,138,240,0.09);color:var(--accent);width:100%;border:1px solid rgba(77,138,240,0.12)}}
.pyr-layer.core{{background:rgba(0,214,158,0.06);color:var(--green);width:72%;border:1px solid rgba(0,214,158,0.10)}}
.pyr-layer.sat{{background:rgba(240,168,48,0.06);color:var(--amber);width:48%;border:1px solid rgba(240,168,48,0.10)}}
.pyr-layer.csh{{background:rgba(115,128,153,0.04);color:var(--text2);width:32%;border:1px solid rgba(115,128,153,0.08)}}

.hp{{background:var(--bg2);border:1px solid var(--border);border-radius:9px;overflow:hidden}}
.hp-head{{padding:7px 16px;font-size:8px;font-weight:600;letter-spacing:1.2px;display:flex;justify-content:space-between;align-items:center;cursor:default}}
.hp-head.b0{{background:rgba(77,138,240,0.05);color:var(--accent)}}
.hp-head.b1{{background:rgba(0,214,158,0.03);color:var(--green)}}
.hp-head.b2{{background:rgba(240,168,48,0.03);color:var(--amber)}}
.hp-head.b3{{background:rgba(115,128,153,0.02);color:var(--text2)}}
.hp-head .hs{{font-family:"JetBrains Mono",monospace;font-size:10px;font-weight:400;opacity:0.7}}
.hp-th{{display:flex;align-items:center;padding:5px 16px 7px;font-size:8px;color:var(--text3);letter-spacing:1.2px;border-bottom:1px solid var(--border);font-weight:600}}
.hp-th span{{cursor:pointer;user-select:none;transition:color .2s}}
.hp-th span:hover{{color:var(--text)}}
.hp-th .c1{{flex:1;min-width:70px}}.hp-th .c2{{width:68px;text-align:right;flex-shrink:0}}.hp-th .c3{{width:55px;text-align:right;flex-shrink:0}}.hp-th .c4{{width:58px;text-align:right;flex-shrink:0}}.hp-th .c5{{width:52px;text-align:right;flex-shrink:0}}
.hr{{display:flex;align-items:center;padding:4px 16px;font-size:10.5px;border-bottom:1px solid rgba(255,255,255,0.004);transition:background .15s}}
.hr:last-child{{border:none}}
.hr:hover{{background:rgba(255,255,255,0.004)}}
.hr .c1{{flex:1;min-width:70px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:center;gap:6px}}
.hr .c2{{width:68px;text-align:right;font-family:"JetBrains Mono",monospace;font-size:10px;color:var(--text2);flex-shrink:0}}
.hr .c3{{width:55px;text-align:right;font-family:"JetBrains Mono",monospace;font-size:10px;font-weight:600;flex-shrink:0}}
.hr .c4{{width:58px;text-align:right;font-family:"JetBrains Mono",monospace;font-size:10px;font-weight:600;flex-shrink:0}}
.hr .c5{{width:52px;text-align:right;font-family:"JetBrains Mono",monospace;font-size:10px;font-weight:600;flex-shrink:0}}
.hr .tag{{font-size:7px;padding:1px 5px;border-radius:3px;letter-spacing:0.3px;font-weight:600;flex-shrink:0}}
.tag-b{{background:rgba(77,138,240,0.10);color:var(--accent)}}
.tag-g{{background:rgba(0,214,158,0.08);color:var(--green)}}
.tag-a{{background:rgba(240,168,48,0.08);color:var(--amber)}}
.tag-r{{background:rgba(240,70,104,0.08);color:var(--red)}}

.grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}}
.card{{background:var(--bg2);border:1px solid var(--border);border-radius:9px;overflow:hidden}}
.card-h{{
  padding:9px 16px;border-bottom:1px solid var(--border);
  font-size:8px;font-weight:600;letter-spacing:1.8px;color:var(--text3);
  background:var(--bg3);display:flex;justify-content:space-between;align-items:center;text-transform:uppercase
}}
.card-b{{padding:10px 16px;max-height:320px;overflow-y:auto}}

.rule-i{{padding:8px 12px;border-radius:5px;margin-bottom:5px;font-size:10.5px;line-height:1.5;display:flex;align-items:flex-start;gap:8px}}
.rule-i .dot{{width:7px;height:7px;border-radius:50%;margin-top:3px;flex-shrink:0}}
.rule-i.rr{{background:var(--redg);border:1px solid rgba(240,70,104,0.15)}}.rule-i.rr .dot{{background:var(--red);box-shadow:0 0 8px var(--red);animation:pulse 2s infinite}}
.rule-i.ra{{background:var(--amberg);border:1px solid rgba(240,168,48,0.12)}}.rule-i.ra .dot{{background:var(--amber);box-shadow:0 0 6px var(--amber)}}
.rule-i.rg{{background:var(--greeng);border:1px solid rgba(0,214,158,0.10)}}.rule-i.rg .dot{{background:var(--green)}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.4}}}}

.wr{{display:flex;align-items:center;padding:5px 0;font-size:10.5px;border-bottom:1px solid rgba(255,255,255,0.006);gap:6px}}
.wr .wn{{width:18px;font-size:11px;font-weight:700;text-align:center;flex-shrink:0;color:var(--text3)}}
.wr .ws{{flex:1;min-width:55px}}
.wr .wc{{font-family:"JetBrains Mono",monospace;font-size:8.5px;color:var(--accent);width:75px;flex-shrink:0}}
.wr .wt{{font-size:9px;color:var(--amber);width:80px;flex-shrink:0;text-align:right}}
.wr .wst{{font-size:9px;width:75px;flex-shrink:0;text-align:right}}

.pi{{padding:6px 0;font-size:10.5px;border-bottom:1px solid rgba(255,255,255,0.006)}}
.pi .pp{{font-size:8.5px;color:var(--amber);margin-bottom:2px;letter-spacing:0.5px}}
.pi .pt{{color:var(--text)}}
.pi .pu{{font-size:8.5px;color:var(--text3);margin-top:1px}}

.rr-row{{display:flex;align-items:center;padding:4px 0;font-size:10.5px;gap:8px}}
.rr-row .rlvl{{width:22px;text-align:center;flex-shrink:0;font-size:11px}}
.rr-row .rn{{flex:1;min-width:70px}}
.rr-row .rd{{font-size:9.5px;color:var(--text2);text-align:right}}

.ds{{padding:7px 0;border-bottom:1px solid rgba(255,255,255,0.007);font-size:10.5px;line-height:1.55;color:var(--text2)}}
.ds:last-child{{border:none}}
.ds b{{color:#fff}}
.ds .op{{color:var(--amber);font-size:9.5px}}

.chart-wrap{{position:relative}}
.chart-legend{{display:flex;gap:16px;margin-bottom:6px;font-size:9px;color:var(--text3)}}
.chart-legend span{{display:flex;align-items:center;gap:5px}}
.chart-legend .ldot{{width:9px;height:9px;border-radius:2px}}

.g{{color:var(--green);font-weight:600}}.r{{color:var(--red);font-weight:600}}.a{{color:var(--amber)}}.pu{{color:var(--purple)}}
.meta{{font-size:9.5px;color:var(--text3);text-align:center;margin-top:20px;line-height:1.8}}
::-webkit-scrollbar{{width:3px}}::-webkit-scrollbar-thumb{{background:var(--border2);border-radius:2px}}

@media(max-width:1150px){{
  .pyr-row{{grid-template-columns:1fr}}
  .pyr-viz{{flex-direction:row;gap:2px;padding:10px}}
  .pyr-layer{{margin:0 1px;font-size:7px}}
  .pyr-layer .pv{{font-size:12px}}
  .kpi-row{{grid-template-columns:repeat(3,1fr)}}
  .grid2,.grid3{{grid-template-columns:1fr}}
}}
@media(max-width:680px){{
  .kpi-row{{grid-template-columns:repeat(2,1fr)}}
  .header{{flex-wrap:wrap}}
  .app{{padding:10px 8px 30px}}
}}
</style>
</head>
<body>
<div class="app">
<div class="header">
  <div class="logo"><span class="icon">⚓</span> <em>Anchor</em></div>
  <span class="ver">v3.3</span>
  <span class="mkt-status closed">A股已收盘</span>
  <span class="spacer"></span>
  <div class="top-stat">数据源 <b>mx-data</b></div>
  <div class="top-stat" style="margin-left:14px">更新 <b id="hd-update">--</b></div>
  <div class="clock" id="clock">--</div>
</div>
<div class="kpi-row" id="kpi"></div>
<div class="pyr-row">
  <div class="pyr-viz" id="pyramid"></div>
  <div class="hp">
    <div class="hp-th"><span class="c1">持仓名称</span><span class="c2">市值</span><span class="c3">盈亏</span><span class="c4">收益率</span><span class="c5">日涨跌</span></div>
    <div id="holdings"></div>
  </div>
</div>
<div class="grid3">
  <div class="card">
    <div class="card-h">Rule Check · 规则检查<span style="color:var(--amber);font-weight:400;letter-spacing:0">每日自动</span></div>
    <div class="card-b" id="rules"></div>
  </div>
  <div class="card">
    <div class="card-h">Watchlist · 关注清单<span id="wlc" style="color:var(--accent);font-weight:400;letter-spacing:0"></span></div>
    <div class="card-b" id="wlbody"></div>
  </div>
  <div class="card">
    <div class="card-h">Actions · 待办事项<span id="pac" style="color:var(--amber);font-weight:400;letter-spacing:0"></span></div>
    <div class="card-b" id="pabody"></div>
  </div>
</div>
<div class="grid2">
  <div class="card">
    <div class="card-h">Risk Matrix · 风险矩阵</div>
    <div class="card-b" id="risks"></div>
  </div>
  <div class="card">
    <div class="card-h">Trend · 走势<span style="font-weight:400;letter-spacing:0;color:var(--text3)">上证 · 科创50 · 日盈亏</span></div>
    <div class="card-b chart-wrap">
      <div class="chart-legend">
        <span><span class="ldot" style="background:var(--amber)"></span>上证</span>
        <span><span class="ldot" style="background:var(--accent)"></span>科创50</span>
        <span><span class="ldot" style="background:var(--green)"></span>日盈亏（右轴）</span>
      </div>
      <canvas id="chart" style="width:100%;height:230px"></canvas>
    </div>
  </div>
</div>
<div class="card" style="margin-bottom:24px">
  <div class="card-h">History · 每日总结 <span id="dsc" style="font-weight:400;letter-spacing:0;color:var(--text3)"></span></div>
  <div class="card-b" id="dailys" style="max-height:400px"></div>
</div>
<div class="meta">
  ⚓ Anchor v3.3 · 压舱石 45% | 核心增长 20% | 卫星进攻 20% | 现金预备 15%<br>
  回撤控制线：-5% ¥31,313 | -10% ¥29,665 | -15% ¥28,017 · 数据：东方财富 mx-data API<br>
  <a href="Anchor/08-可视化网站/anchor-pro.html" style="color:var(--accent);text-decoration:none">📖 体系总览</a> ·
  <a href="Anchor/05-脚本工具/anchor_calculator.html" style="color:var(--accent);text-decoration:none">🔢 仓位计算器</a> ·
  🤖 Generated with Claude Code · 投资有风险，决策需谨慎
</div>
</div>

<script>
var D = {embed_json};

function fp(v){{return v>=0?"+"+v.toFixed(0):v.toFixed(0)}}
function fc(v){{return v>=0?"g":"r"}}
function fm(v){{return v.toLocaleString("en-US")}}
function rate(pnl,mv){{if(!mv||mv===pnl)return 0;return pnl/(mv-pnl)*100}}

(function(){{
  var c=document.getElementById("clock"),u=document.getElementById("hd-update");
  u.textContent=D.time;
  function t(){{
    var n=new Date();
    c.textContent=n.toLocaleDateString("zh-CN",{{year:"numeric",month:"2-digit",day:"2-digit"}})+" "+n.toLocaleTimeString("zh-CN",{{hour12:false}})+" · 周"+["日","一","二","三","四","五","六"][n.getDay()];
  }}
  t();setInterval(t,1000);
}})();

(function(){{
  var h="";
  h+='<div class="kpi"><div class="kl">Total Assets</div><div class="kv" style="color:var(--accent)">'+(D.total/10000).toFixed(2)+'<span class="ku">万</span></div><div class="ks">基金 '+(D.fundMv/10000).toFixed(1)+'万 · 股票 '+(D.stockMv/10000).toFixed(1)+'万 · 现金 '+(D.cashMv/10000).toFixed(2)+'万</div></div>';
  h+='<div class="kpi"><div class="kl">Hold PnL</div><div class="kv '+fc(D.totalPnl)+'">'+(D.totalPnl>=0?"+":"")+fm(Math.round(D.totalPnl))+'</div><div class="ks">10只活跃持仓 · 持仓盈亏</div></div>';
  h+='<div class="kpi"><div class="kl">SSE · 上证</div><div class="kv" style="color:var(--amber)">'+D.mkt.sh.close+'</div><div class="ks '+fc(String(D.mkt.sh.change).indexOf("+")===0)+'">'+D.mkt.sh.change+' · '+D.mkt.date+' '+D.mkt.day+'</div></div>';
  h+='<div class="kpi"><div class="kl">STAR 50</div><div class="kv '+fc(String(D.mkt.kc.change).indexOf("+")===0)+'">'+D.mkt.kc.close+'</div><div class="ks">'+D.mkt.kc.change+' · 定投: '+(D.dca||[]).join(" · ")+'</div></div>';
  h+='<div class="kpi"><div class="kl">August Ops</div><div class="kv" style="color:var(--green)">0<span class="ku">/4</span></div><div class="ks">零操作 · 零违规 · 满分</div></div>';
  document.getElementById("kpi").innerHTML=h;
}})();

(function(){{
  var lyrs=[
    {{k:"bed",icon:"🛡️",label:"压舱石",mv:{round(bedrock_mv)},tgt:45}},
    {{k:"core",icon:"🚀",label:"核心增长",mv:{round(core_mv)},tgt:20}},
    {{k:"sat",icon:"🔥",label:"卫星进攻",mv:{round(sat_mv)},tgt:20}},
    {{k:"csh",icon:"💰",label:"现金预备",mv:{round(cash_mv)},tgt:15}}
  ];
  var h='<h3>四层金字塔</h3>';
  lyrs.forEach(function(l){{
    var pct=D.total>0?(l.mv/D.total*100).toFixed(0):0;
    h+='<div class="pyr-layer '+l.k+'"><div class="pv">'+l.icon+' '+pct+'%</div><div class="pl">'+l.label+'</div><div class="pb">目标 '+l.tgt+'% · ¥'+(l.mv/10000).toFixed(2)+'万</div></div>';
  }});
  document.getElementById("pyramid").innerHTML=h;
}})();

(function(){{
  var layers=[
    {{items:D.bedrock,cls:"b0",label:"🛡️ 压舱石层"}},
    {{items:D.core,cls:"b1",label:"🚀 核心增长层"}},
    {{items:D.sat,cls:"b2",label:"🔥 卫星进攻层"}},
    {{items:D.cash,cls:"b3",label:"💰 现金预备层"}}
  ];
  var h="";
  layers.forEach(function(lyr){{
    var items=lyr.items||[];
    var mv=items.reduce(function(s,i){{return s+(i.mv||0);}},0);
    h+='<div style="border-bottom:1px solid rgba(255,255,255,0.01)"><div class="hp-head '+lyr.cls+'">'+lyr.label+'<span class="hs">¥'+fm(mv)+' · '+(D.total>0?(mv/D.total*100).toFixed(0):0)+'%</span></div>';
    items.forEach(function(i){{
      var r=rate(i.pnl,i.mv);
      h+='<div class="hr"><span class="c1">'+(i.n||"?")+(i.tag?' <span class="tag '+i.tc+'">'+i.tag+'</span>':'')+'</span><span class="c2">'+(i.mv/10000).toFixed(2)+'万</span><span class="c3 '+fc(i.pnl)+'">'+fp(i.pnl)+'</span><span class="c4 '+fc(r)+'">'+(r>=0?"+":"")+r.toFixed(1)+'%</span><span class="c5 '+fc(i.dp)+'">'+fp(i.dp)+'</span></div>';
    }});
    h+='</div>';
  }});
  document.getElementById("holdings").innerHTML=h;
}})();

(function(){{
  var h="";
  (D.rules||[]).forEach(function(r){{
    h+='<div class="rule-i '+r.lv+'"><span class="dot"></span><span>'+r.t+'</span></div>';
  }});
  h+='<div style="margin-top:10px;font-size:9.5px;color:var(--text3);line-height:2">📏 回撤控制线（基于 ¥32,961）：<br><span class="a">-5% → ¥31,313（卫星减半）</span><br><span class="r">-10% → ¥29,665（卫星全清）</span><br><span class="r">-15% → ¥28,017（核心减1/3）</span></div>';
  document.getElementById("rules").innerHTML=h;
}})();

(function(){{
  var wl=D.wl||[];
  document.getElementById("wlc").textContent=wl.length+"只";
  var h="";
  wl.forEach(function(w){{
    h+='<div class="wr"><span class="wn">'+(w.r||w.rank||"")+'</span><span class="ws">'+(w.s||w.sector||"")+'</span><span class="wc">'+(w.c||w.etf_code||"")+'</span><span class="wt">触发: '+(w.t||w.trigger||"")+'</span><span class="wst">'+(w.st||w.status||"")+'</span></div>';
  }});
  document.getElementById("wlbody").innerHTML=h||'<div style="color:var(--text3);font-size:10px">暂无</div>';
}})();

(function(){{
  var pa=D.pa||[];
  document.getElementById("pac").textContent=pa.length+"项";
  var h="";
  pa.forEach(function(p){{
    h+='<div class="pi"><div class="pp">'+p.p+'</div><div class="pt">'+p.t+(p.d?" · "+p.d:"")+'</div>'+(p.u?'<div class="pu">📅 '+p.u+'</div>':'')+'</div>';
  }});
  document.getElementById("pabody").innerHTML=h||'<div style="color:var(--text3);font-size:10px">暂无</div>';
}})();

(function(){{
  var h="";
  (D.risks||[]).forEach(function(r){{
    h+='<div class="rr-row"><span class="rlvl">'+(r.l=="red"?"🔴":r.l=="amber"?"🟡":r.l=="green"?"🟢":r.l)+'</span><span class="rn '+r.c+'">'+r.n+'</span><span class="rd">'+r.d+'</span></div>';
  }});
  document.getElementById("risks").innerHTML=h;
}})();

(function(){{
  var ds=D.ds||[];
  document.getElementById("dsc").textContent="共"+ds.length+"条";
  var h="";
  ds.forEach(function(d){{
    h+='<div class="ds"><b>'+d.dt+' '+d.dy+'</b> | 上证 '+d.sh+'('+d.sc+') | 科创 '+d.kc+'('+d.kcc+') | PnL <b class="'+fc(parseFloat(d.pnl))+'">'+d.pnl+'</b><br>'+d.note.substring(0,180)+'<br><span class="op">操作: '+d.ops+'</span></div>';
  }});
  document.getElementById("dailys").innerHTML=h||'<div style="color:var(--text3);font-size:10px">暂无</div>';
}})();

setTimeout(function(){{
  var cd=D.chart||[],cv=document.getElementById("chart");
  if(!cv||cd.length<2)return;
  var rect=cv.parentElement.getBoundingClientRect();
  var W=rect.width-8,H=230;
  cv.width=W*2;cv.height=H*2;cv.style.width=W+"px";cv.style.height=H+"px";
  var ctx=cv.getContext("2d");ctx.scale(2,2);
  var pad={{t:14,r:50,b:26,l:42}},w=W-pad.l-pad.r,h=H-pad.t-pad.b;
  var sh=cd.map(function(d){{return d.sh;}}),st=cd.map(function(d){{return d.st;}}),pn=cd.map(function(d){{return d.pnl;}});
  var shMin=Math.min.apply(null,sh)-30,shMax=Math.max.apply(null,sh)+30;
  var pnMin=Math.min.apply(null,pn)-100,pnMax=Math.max.apply(null,pn)+100;
  var shRng=shMax-shMin||1,pnRng=pnMax-pnMin||1;
  function xi(i){{return pad.l+i/Math.max(1,cd.length-1)*w}}
  function ySH(v){{return pad.t+(shMax-v)/shRng*h}}
  function yPN(v){{return pad.t+(pnMax-v)/pnRng*h}}
  ctx.strokeStyle="rgba(255,255,255,0.018)";ctx.lineWidth=1;
  for(var i=0;i<6;i++){{var gy=pad.t+i*h/5;ctx.beginPath();ctx.moveTo(pad.l,gy);ctx.lineTo(pad.l+w,gy);ctx.stroke()}}
  if(pnMin<0&&pnMax>0){{var zy=yPN(0);ctx.strokeStyle="rgba(255,255,255,0.03)";ctx.setLineDash([4,5]);ctx.beginPath();ctx.moveTo(pad.l,zy);ctx.lineTo(pad.l+w,zy);ctx.stroke();ctx.setLineDash([])}}
  function area(key,color,yFn){{
    var grad=ctx.createLinearGradient(0,pad.t,0,pad.t+h);
    grad.addColorStop(0,color.replace(")","")+",0.15)");grad.addColorStop(1,color.replace(")","")+",0.00)");
    ctx.fillStyle=grad;ctx.beginPath();
    cd.forEach(function(d,i){{var px=xi(i),py=yFn(d[key]);i===0?ctx.moveTo(px,py):ctx.lineTo(px,py)}});
    ctx.lineTo(xi(cd.length-1),pad.t+h);ctx.lineTo(pad.l,pad.t+h);ctx.closePath();ctx.fill();
  }}
  area("sh","rgba(240,168,48",ySH);area("st","rgba(77,138,240",ySH);area("pnl","rgba(0,214,158",yPN);
  function line(key,color,lw,yFn){{
    ctx.strokeStyle=color;ctx.lineWidth=lw;ctx.lineJoin="round";ctx.beginPath();
    cd.forEach(function(d,i){{var px=xi(i),py=yFn(d[key]);i===0?ctx.moveTo(px,py):ctx.lineTo(px,py)}});ctx.stroke();
    cd.forEach(function(d,i){{ctx.fillStyle=color;ctx.beginPath();ctx.arc(xi(i),yFn(d[key]),2.5,0,Math.PI*2);ctx.fill()}});
  }}
  line("sh","#f0a830",2.2,ySH);line("st","#4d8af0",2.2,ySH);line("pnl","#00d69e",1.6,yPN);
  ctx.fillStyle="#738099";ctx.font='8px "Segoe UI",sans-serif';ctx.textAlign="center";
  cd.forEach(function(d,i){{if(i%Math.max(1,Math.floor(cd.length/7))===0||i===cd.length-1)ctx.fillText(d.d,xi(i),H-pad.b+12)}});
  ctx.fillStyle="#738099";ctx.font='8px "JetBrains Mono",monospace';ctx.textAlign="left";
  [0,0.25,0.5,0.75,1].forEach(function(f){{var val=pnMax-f*pnRng,ly=yPN(val);ctx.fillText((val>=0?"+":"")+Math.round(val),pad.l+w+4,ly+3)}});
}},150);
</script>
</body>
</html>'''

# ===== WRITE =====
os.makedirs(ANCHOR_DATA, exist_ok=True)

# 同步数据源 JSON 到看板目录
import shutil
data_json_dest = os.path.join(ANCHOR_DATA, "portfolio_data.json")
if os.path.abspath(DATA_PATH) != os.path.abspath(data_json_dest):
    shutil.copy2(DATA_PATH, data_json_dest)

for p in [HTML_PATH, HTML_PATH2]:
    with open(p, 'w', encoding='utf-8') as f:
        f.write(html)

# ===== SNAPSHOT =====
snapshot = {
    "update_time": update_time,
    "total_assets": round(total, 2),
    "fund_mv": round(fund_mv_total, 2),
    "stock_mv": round(stock_mv, 2),
    "cash_mv": round(cash_mv, 2),
    "total_pnl": round(total_pnl, 2),
    "layer_summary": {
        "bedrock": {"mv": round(bedrock_mv, 2), "pct": round(bedrock_mv/total*100, 1) if total > 0 else 0},
        "core": {"mv": round(core_mv, 2), "pct": round(core_mv/total*100, 1) if total > 0 else 0},
        "sat": {"mv": round(sat_mv, 2), "pct": round(sat_mv/total*100, 1) if total > 0 else 0},
        "cash": {"mv": round(cash_mv, 2), "pct": round(cash_mv/total*100, 1) if total > 0 else 0},
    },
    "dca_running": dca_list,
    "watchlist": wl,
    "pending_actions": pa,
    "rule_checks": rules,
    "chart_data": chart_out,
}
for sp in [SNAPSHOT_PATH, SNAPSHOT_PATH2]:
    with open(sp, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

print(f"[OK] Data JSON  -> {data_json_dest}")
print(f"[OK] Premium HTML -> {HTML_PATH} ({len(html):,} bytes)")
print(f"[OK] Premium HTML -> {HTML_PATH2} ({len(html):,} bytes)")
print(f"[OK] Snapshot    -> {SNAPSHOT_PATH}")
print(f"[OK] Snapshot    -> {SNAPSHOT_PATH2}")
print(f"     Total: CNY {total:,.0f} | Bedrock: {bedrock_mv/total*100:.0f}% | Core: {core_mv/total*100:.0f}% | Sat: {sat_mv/total*100:.0f}% | Cash: {cash_mv/total*100:.0f}%")
print(f"     PnL: {fp(total_pnl)} | Holdings: {len(bedrock)+len(core)+len(sat)+len(cash)} active")

# Data freshness check
today = date.today()
mkt_date_str = mkt.get('date', '')
try:
    mkt_date = datetime.strptime(mkt_date_str, '%Y-%m-%d').date()
    mkt_age = (today - mkt_date).days
except:
    mkt_age = 999

print(f"\n----- Data Freshness -----")
print(f"  Market data: {mkt_date_str} ({mkt_age}d ago) {'[STALE]' if mkt_age > 1 else '[OK]'}")
print(f"  Holdings: {len(bedrock)+len(core)+len(sat)+len(cash)} active, {len([h for h in raw if h.get('mv',0)==0 and '已清仓' in str(h.get('group',''))])} cleared")
print(f"  Watchlist: {len(wl)} items | Pending: {len(pa)} items")

# Rule alerts summary
alerts = [r for r in rules if r.get('lv') == 'rr']
warns = [r for r in rules if r.get('lv') == 'ra']
print(f"  Rule Alerts: {len(alerts)} RED, {len(warns)} AMBER")

# Remind about time-sensitive items
for pa_item in pa:
    pa_text = str(pa_item).lower()
    if '8/20' in pa_text or '8月20' in pa_text:
        remaining = (date(2026, 8, 20) - today).days
        print(f"  [TIMER] 创新药时间止损: {remaining}天剩余")

print("Done.")
