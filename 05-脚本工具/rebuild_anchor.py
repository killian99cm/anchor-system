#!/usr/bin/env python3
"""Rebuild Anchor-themed portfolio_analysis.html from portfolio_data.json"""
import json, os

DESKTOP = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(DESKTOP, 'portfolio_data.json')

with open(DATA_PATH, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Inject data as JSON
data_json = json.dumps(data, ensure_ascii=False)

html = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Anchor · 投资看板</title>
<style>
:root{
  --bg:#06080d;--surface:#0b0e16;--surface2:#10141f;--border:#181c2a;
  --text:#c8ccd4;--text2:#6b7094;--text3:#3d4160;
  --green:#00d4a0;--red:#ff4d6a;--amber:#f0b030;--accent:#5b8def;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',-apple-system,sans-serif;font-size:13px;line-height:1.5;min-height:100vh}
body::before{content:'';position:fixed;inset:0;background:radial-gradient(ellipse at 20% 5%,rgba(91,141,239,0.04)0%,transparent 50%),radial-gradient(ellipse at 80% 90%,rgba(0,212,160,0.03)0%,transparent 50%);pointer-events:none;z-index:0}
.app{max-width:1480px;margin:0 auto;padding:24px 32px 60px;position:relative;z-index:1}
.header{display:flex;align-items:center;gap:12px;margin-bottom:22px;padding-bottom:14px;border-bottom:1px solid var(--border)}
.header .logo{font-size:22px;font-weight:700;color:#fff;letter-spacing:-0.5px}
.header .logo span{color:var(--accent)}
.header .subtitle{font-size:10px;color:var(--text3);letter-spacing:2px}
.header .clock{font-family:monospace;font-size:11px;color:var(--amber);margin-left:auto;background:rgba(240,176,48,0.05);padding:5px 12px;border-radius:4px;border:1px solid rgba(240,176,48,0.10)}
.kpi-row{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:18px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px 18px;position:relative;overflow:hidden}
.kpi::before{content:'';position:absolute;top:0;left:0;width:3px;height:100%}
.kpi:nth-child(1)::before{background:var(--accent)}
.kpi:nth-child(2)::before{background:var(--green)}
.kpi:nth-child(3)::before{background:var(--amber)}
.kpi:nth-child(4)::before{background:var(--red)}
.kpi:nth-child(5)::before{background:var(--accent);opacity:0.5}
.kpi .lbl{font-size:9px;color:var(--text3);letter-spacing:1.8px;margin-bottom:5px;text-transform:uppercase}
.kpi .val{font-family:monospace;font-size:22px;font-weight:700;color:#fff;line-height:1.1}
.kpi .val span{font-size:13px;font-weight:400}
.kpi .sub{font-size:10px;color:var(--text2);margin-top:3px}
.pyramid-row{display:grid;grid-template-columns:220px 1fr;gap:14px;margin-bottom:18px}
.pyramid-viz{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:18px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.pyramid-viz h3{font-size:10px;color:var(--text3);letter-spacing:1.5px;margin-bottom:12px;text-transform:uppercase}
.layer{width:100%;text-align:center;padding:9px 6px;border-radius:4px;margin-bottom:3px;font-size:10px;font-weight:600}
.layer .pct{font-size:15px;font-weight:700}
.layer .lbl{font-size:9px;opacity:0.7;letter-spacing:1px}
.layer.bedrock{background:rgba(91,141,239,0.10);color:var(--accent);width:100%}
.layer.core{background:rgba(0,212,160,0.08);color:var(--green);width:72%}
.layer.sat{background:rgba(240,176,48,0.08);color:var(--amber);width:48%}
.layer.cash{background:rgba(107,112,148,0.07);color:var(--text2);width:32%}
.holdings-panel{background:var(--surface);border:1px solid var(--border);border-radius:6px;overflow:hidden}
.lblock .lhead{padding:8px 14px;font-size:9px;font-weight:600;letter-spacing:1.5px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between}
.lblock .lhead.b{background:rgba(91,141,239,0.05);color:var(--accent)}
.lblock .lhead.c{background:rgba(0,212,160,0.04);color:var(--green)}
.lblock .lhead.s{background:rgba(240,176,48,0.04);color:var(--amber)}
.lblock .lhead.ca{background:rgba(107,112,148,0.03);color:var(--text2)}
.lblock .lbody{padding:2px 0}
.hrow{display:flex;align-items:center;padding:5px 14px;font-size:11px;border-bottom:1px solid rgba(255,255,255,0.008)}
.hrow:hover{background:rgba(255,255,255,0.003)}
.hrow .n{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:70px}
.hrow .v{width:72px;text-align:right;font-family:monospace;font-size:11px;color:var(--text2);flex-shrink:0}
.hrow .p{width:62px;text-align:right;font-family:monospace;font-size:11px;font-weight:600;flex-shrink:0}
.hrow .d{width:56px;text-align:right;font-family:monospace;font-size:10px;font-weight:600;flex-shrink:0}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:6px;overflow:hidden}
.card-h{padding:8px 14px;border-bottom:1px solid var(--border);font-size:9px;font-weight:600;letter-spacing:1.5px;color:var(--text3);text-transform:uppercase;background:var(--surface2)}
.card-b{padding:10px 14px;max-height:340px;overflow-y:auto}
.summary-item{padding:7px 0;border-bottom:1px solid rgba(255,255,255,0.015);font-size:11px;line-height:1.55;color:var(--text2)}
.summary-item b{color:#fff}
.summary-item .op{color:var(--amber);font-size:10px}
.pending-row{display:flex;align-items:center;padding:4px 0;font-size:11px;border-bottom:1px solid rgba(255,255,255,0.008)}
.pending-row .n{flex:1}
.pending-row .v{width:70px;text-align:right;font-family:monospace;color:var(--amber);flex-shrink:0}
.green{color:var(--green)}.red{color:var(--red)}.amber{color:var(--amber)}
::-webkit-scrollbar{width:3px}::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
@media(max-width:1024px){.pyramid-row{grid-template-columns:1fr}.pyramid-viz{flex-direction:row;gap:6px;padding:10px}.layer{margin-bottom:0;margin-right:2px;font-size:8px}.kpi-row{grid-template-columns:repeat(3,1fr)}.grid2{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="app">
<div class="header"><div class="logo">&#9875; <span>Anchor</span></div><div class="subtitle">INVESTMENT SYSTEM</div><div class="clock" id="clock"></div></div>
<div class="kpi-row" id="kpi-row"></div>
<div class="pyramid-row"><div class="pyramid-viz"><h3>四层金字塔</h3><div class="layer bedrock"><div class="pct" id="bpct"></div><div class="lbl">压舱石</div></div><div class="layer core"><div class="pct" id="cpct"></div><div class="lbl">核心增长</div></div><div class="layer sat"><div class="pct" id="spct"></div><div class="lbl">卫星进攻</div></div><div class="layer cash"><div class="pct" id="ypct"></div><div class="lbl">现金预备</div></div></div><div class="holdings-panel" id="hp"></div></div>
<div class="grid2"><div class="card"><div class="card-h">Pending · 待结算</div><div class="card-b" id="ps"></div></div><div class="card"><div class="card-h">Chart · 走势</div><div class="card-b"><canvas id="tc" style="width:100%;height:200px"></canvas></div></div></div>
<div class="card"><div class="card-h">History · 每日总结</div><div class="card-b" id="ss" style="max-height:420px"></div></div>
</div>
<script>
var D=''' + data_json + r''';
D=JSON.parse(D);
(function(){
var c=document.getElementById('clock'),now=new Date();
c.textContent=now.toLocaleDateString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'})+'  '+now.toLocaleTimeString('zh-CN',{hour12:false});
setInterval(function(){var n=new Date();c.textContent=n.toLocaleDateString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'})+'  '+n.toLocaleTimeString('zh-CN',{hour12:false});},1000);
var H=D.holdings_summary||[],S=D.stock_holdings||[],yb=D.yuebao||0,pc=D.pending_clearance_total||0,mkt=D.market||{},sums=D.daily_summaries||[],cd=D.chart_data||[];
var bMv=0,cMv=0,sMv=0,caMv=yb,bF=[],cF=[],sF=[];
H.forEach(function(h){var mv=h.mv||0,n=h.name||'',g=h.group||'';if(mv<1||g==='已清仓'||g==='待结算')return;if(n.indexOf('余额宝')!==-1){caMv=mv;return;}if(g==='全局固收'||n.indexOf('黄金')!==-1||n.indexOf('债券')!==-1){bMv+=mv;bF.push(h);}else if(n.indexOf('纳斯达克')!==-1||n.indexOf('纳指')!==-1||n.indexOf('示例指数基金通利')!==-1){cMv+=mv;cF.push(h);}else{sMv+=mv;sF.push(h);}});
S.forEach(function(s){bMv+=s.mv||0;bF.push({name:s.name||'红利ETF',mv:s.mv||0,pnl:s.pnl||0,day_pnl:s.day_pnl||0});});
var tot=bMv+cMv+sMv+caMv,fundEx=0;H.forEach(function(h){if(h.name.indexOf('余额宝')===-1)fundEx+=h.mv||0;});
var tp=D.total_hold_pnl_est||0;
document.getElementById('kpi-row').innerHTML='<div class="kpi"><div class="lbl">Total Assets</div><div class="val" style="color:var(--accent)">'+(tot/10000).toFixed(2)+'<span> 万</span></div><div class="sub">基金 '+(fundEx/10000).toFixed(1)+'万 · 现金 '+(yb/10000).toFixed(1)+'万</div></div><div class="kpi"><div class="lbl">Hold PnL</div><div class="val '+(tp>=0?'green':'red')+'">'+(tp>=0?'+':'')+tp.toFixed(0)+'</div><div class="sub">持有盈亏</div></div><div class="kpi"><div class="lbl">SSE · 上证</div><div class="val" style="color:var(--amber)">'+(mkt.sh?mkt.sh.close:'--')+'</div><div class="sub">'+(mkt.sh?mkt.sh.change:'--')+' · '+(mkt.date||'')+'</div></div><div class="kpi"><div class="lbl">STAR 50</div><div class="val '+(mkt.kc&&String(mkt.kc.change).indexOf('+')===0?'green':'red')+'">'+(mkt.kc?mkt.kc.close:'--')+'</div><div class="sub">'+(mkt.kc?mkt.kc.change:'--')+'</div></div><div class="kpi"><div class="lbl">Pending</div><div class="val" style="color:var(--amber)">'+((pc||0)/10000).toFixed(2)+'<span> 万</span></div><div class="sub">待结算 · 冻结72h</div></div>';
document.getElementById('bpct').textContent=(bMv/tot*100).toFixed(0)+'%';
document.getElementById('cpct').textContent=(cMv/tot*100).toFixed(0)+'%';
document.getElementById('spct').textContent=(sMv/tot*100).toFixed(0)+'%';
document.getElementById('ypct').textContent=(caMv/tot*100).toFixed(0)+'%';
function fp(v){return v>=0?'+'+v.toFixed(0):v.toFixed(0);}
function rl(label,cls,funds,mv){var h='<div class="lblock"><div class="lhead '+cls+'">'+label+'<span>'+mv.toFixed(0)+' · '+(mv/tot*100).toFixed(0)+'%</span></div><div class="lbody">';funds.forEach(function(f){var m=f.mv||0,pn=f.pnl||0,dp=f.day_pnl||0;h+='<div class="hrow"><span class="n">'+(f.name||'?').substring(0,28)+'</span><span class="v">'+(m/10000).toFixed(2)+'万</span><span class="p '+(pn>=0?'green':'red')+'">'+fp(pn)+'</span><span class="d '+(dp>=0?'green':'red')+'">'+(dp>=0?'+':'')+dp.toFixed(0)+'</span></div>';});h+='</div></div>';return h;}
document.getElementById('hp').innerHTML=rl('&#128161; 压舱石层','b',bF,bMv)+rl('&#128640; 核心增长层','c',cF,cMv)+rl('&#128293; 卫星进攻层','s',sF,sMv)+'<div class="lblock"><div class="lhead ca">&#128176; 现金预备层<span>'+caMv.toFixed(0)+' · '+(caMv/tot*100).toFixed(0)+'%</span></div></div>';
var ph='',pf=[];H.forEach(function(h){if((h.group||'')==='待结算'&&(h.mv||0)>0)pf.push(h);});
if(pf.length>0){pf.forEach(function(f){ph+='<div class="pending-row"><span class="n">'+f.name.substring(0,30)+'</span><span class="v">'+((f.mv||0)/10000).toFixed(2)+'万</span></div>';});ph+='<div class="pending-row" style="margin-top:4px"><span class="n" style="color:var(--amber)">合计到账</span><span class="v" style="color:var(--amber)">'+((pc||0)/10000).toFixed(2)+'万</span></div>';var sc=D.clearance_schedule||{};ph+='<div style="font-size:10px;color:var(--text3);margin-top:4px">';for(var k in sc)ph+=k+': '+sc[k].toFixed(0)+' · ';ph+='冻结至7/25</div>';}else{ph='<div style="color:var(--text3);font-size:11px">无待结算资金</div>';}
document.getElementById('ps').innerHTML=ph;
var sh='';sums.slice(0,14).forEach(function(d){var ops=(d.operations||[]).map(function(o){return o.op;}).join(' · ')||'无';sh+='<div class="summary-item"><b>'+d.date+' '+d.day+'</b> | 上证'+d.shanghai.close+'('+d.shanghai.change+') | 科创'+d.kechuang50.close+'('+d.kechuang50.change+') | PnL '+d.portfolio_day_pnl_est+'<br>'+d.market_note.substring(0,180)+'<br><span class="op">操作: '+ops+'</span></div>';});
document.getElementById('ss').innerHTML=sh||'暂无';
setTimeout(function(){var cv=document.getElementById('tc');if(!cv||cd.length<2)return;var W=cv.parentElement.clientWidth-28,H=200;cv.width=W*2;cv.height=H*2;cv.style.width=W+'px';cv.style.height=H+'px';var cx=cv.getContext('2d');cx.scale(2,2);var pad={top:8,r:6,b:22,l:40},w=W-pad.l-pad.r,h=H-pad.top-pad.b;var shV=cd.map(function(d){return d.sh;}),stV=cd.map(function(d){return d.star;});var all=shV.concat(stV),minY=Math.min.apply(null,all)-25,maxY=Math.max.apply(null,all)+25;function x(i){return pad.l+i/(cd.length-1)*w;}function y(v){return pad.top+(maxY-v)/(maxY-minY)*h;}cx.strokeStyle='rgba(255,255,255,0.02)';cx.lineWidth=1;for(var i=0;i<4;i++){var gy=pad.top+i*h/3;cx.beginPath();cx.moveTo(pad.l,gy);cx.lineTo(pad.l+w,gy);cx.stroke();}function line(key,color,dash){cx.strokeStyle=color;cx.lineWidth=2;if(dash)cx.setLineDash([4,3]);else cx.setLineDash([]);cx.beginPath();cd.forEach(function(d,i){var px=x(i),py=y(d[key]);i===0?cx.moveTo(px,py):cx.lineTo(px,py);});cx.stroke();cx.setLineDash([]);}line('star','#5b8def');line('sh','#f0b030');cx.fillStyle='#6b7094';cx.font='8px monospace';cx.textAlign='center';cd.forEach(function(d,i){if(i%2===0||i===cd.length-1)cx.fillText(d.d,x(i),H-pad.b+11);});cx.fillStyle='#f0b030';cx.fillRect(W-155,6,10,10);cx.fillStyle='#fff';cx.font='10px sans-serif';cx.textAlign='left';cx.fillText('上证',W-141,15);cx.fillStyle='#5b8def';cx.fillRect(W-95,6,10,10);cx.fillText('科创50',W-81,15);},200);
})();
</script>
</body>
</html>'''

html_path = os.path.join(DESKTOP, 'portfolio_analysis.html')
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

total = data.get('total_assets', 0)
pnl = data.get('total_hold_pnl_est', 0)
print(f'Anchor HTML rebuilt - Assets:{total:,.0f} - PnL:{pnl:,.0f}')
