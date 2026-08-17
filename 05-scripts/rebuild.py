#!/usr/bin/env python3
"""
Anchor v3.3 私有投资看板生成器。
数据层由 data_processor.process_all() 统一计算，渲染层只负责展示。
"""
import json
import logging
import os
import shutil
from datetime import date, datetime

import paths

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "rebuild.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("rebuild")

DESKTOP = paths.DESKTOP
ANCHOR_DATA = paths.DASHBOARD_DIR
DATA_PATH = paths.DATA_PATH
HTML_PATH = paths.HTML_PATH
HTML_PATH2 = paths.DASHBOARD_DIR / "portfolio_analysis.html"
SNAPSHOT_PATH = paths.SNAPSHOT_PATH
SNAPSHOT_PATH2 = paths.DASHBOARD_DIR / "portfolio_snapshot.json"

from data_processor import build_snapshot, fp, process_all

try:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
except FileNotFoundError:
    log.error("portfolio_data.json not found at %s", DATA_PATH)
    raise SystemExit(1)
except json.JSONDecodeError as exc:
    log.error("Invalid JSON: %s", exc)
    raise SystemExit(1)

embed = process_all(data)
for warning in embed.get("_warnings", []):
    log.warning(warning)
snapshot = build_snapshot(embed)

html = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Anchor v3.5 · 私有投资驾驶舱</title>
<style>
:root{--bg:#02070f;--surface:#071120;--surface-2:#0b1729;--surface-3:#0f1e34;--line:#18304d;--line-soft:rgba(154,188,225,.14);--text:#edf4ff;--muted:#91a4bd;--dim:#536a85;--blue:#3987e5;--blue-soft:rgba(57,135,229,.14);--green:#36d39c;--amber:#fab219;--red:#e66767;--purple:#9085e9;--mono:"JetBrains Mono","Cascadia Code",Consolas,monospace;--shadow:0 18px 55px rgba(0,0,0,.25)}
*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}body{background:var(--bg);color:var(--text);font:13px/1.55 Inter,"Segoe UI",system-ui,sans-serif;min-height:100vh;overflow-x:hidden}body:before{content:"";position:fixed;inset:0;z-index:-2;background:radial-gradient(circle at 12% -8%,rgba(57,135,229,.16),transparent 32%),radial-gradient(circle at 92% 86%,rgba(54,211,156,.07),transparent 30%),linear-gradient(180deg,#02070f,#04101c 48%,#02070f)}body:after{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.22;background-image:linear-gradient(rgba(130,170,215,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(130,170,215,.06) 1px,transparent 1px);background-size:48px 48px;mask-image:linear-gradient(#000,transparent 78%)}
button{font:inherit;cursor:pointer}.app{max-width:1600px;margin:0 auto;padding:18px 28px 56px}.topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:13px;padding:12px 18px;margin-bottom:15px;border:1px solid var(--line-soft);border-radius:13px;background:rgba(4,13,25,.9);backdrop-filter:blur(18px);box-shadow:0 8px 28px rgba(0,0,0,.18)}.brand{display:flex;align-items:center;gap:8px;color:#fff;font-size:19px;font-weight:800;letter-spacing:-.5px}.brand-mark{display:grid;place-items:center;width:27px;height:27px;border:1px solid rgba(57,135,229,.45);border-radius:8px;color:var(--blue)}.brand em{font-style:normal;color:var(--blue)}.badge{font:600 10px var(--mono);color:var(--blue);border:1px solid rgba(57,135,229,.3);padding:3px 8px;border-radius:999px}.status{font:600 10px var(--mono);padding:4px 10px;border-radius:999px}.status.safe{color:var(--green);background:rgba(54,211,156,.09);border:1px solid rgba(54,211,156,.25)}.status.watch{color:var(--amber);background:rgba(250,178,25,.09);border:1px solid rgba(250,178,25,.25)}.status.action{color:var(--red);background:rgba(230,103,103,.09);border:1px solid rgba(230,103,103,.25)}.spacer{flex:1}.topstat{font-size:10px;color:var(--dim);text-align:right}.topstat b{display:block;color:#fff;font:11px var(--mono)}.clock{font:11px var(--mono);color:var(--amber);padding:5px 10px;border:1px solid rgba(250,178,25,.22);border-radius:7px;background:rgba(250,178,25,.06);white-space:nowrap}
.decision{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:14px;padding:17px 20px;margin-bottom:15px;border:1px solid var(--line-soft);border-left:4px solid var(--green);border-radius:13px;background:rgba(7,17,32,.83);box-shadow:var(--shadow)}.decision.watch{border-left-color:var(--amber);background:rgba(250,178,25,.06)}.decision.action{border-left-color:var(--red);background:rgba(230,103,103,.07)}.decision-icon{font-size:22px}.decision-copy strong{display:block;color:#fff;font-size:14px}.decision-copy span{display:block;color:var(--muted);font-size:11px;margin-top:3px}.decision-tag{font-size:10px;font-weight:800;letter-spacing:.8px;padding:5px 9px;border-radius:7px;background:var(--green);color:#03140e}.decision.watch .decision-tag{background:var(--amber);color:#251a03}.decision.action .decision-tag{background:var(--red);color:#fff}
.kpi-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:15px}.kpi{position:relative;min-height:126px;padding:16px;border:1px solid var(--line-soft);border-radius:12px;background:rgba(7,17,32,.78);overflow:hidden;transition:.2s}.kpi:hover{transform:translateY(-3px);border-color:rgba(57,135,229,.5)}.kpi:after{content:"";position:absolute;left:0;top:0;width:64px;height:2px;background:var(--tone,var(--blue))}.kpi-label{color:var(--dim);font:9px var(--mono);letter-spacing:1px;text-transform:uppercase}.kpi-value{margin-top:10px;color:#fff;font:700 23px var(--mono);letter-spacing:-1px}.kpi-value small{font-size:11px;color:var(--dim);letter-spacing:0}.kpi-sub{margin-top:7px;color:var(--muted);font-size:10px;line-height:1.45}
.panel{border:1px solid var(--line-soft);border-radius:13px;background:rgba(7,17,32,.78);overflow:hidden}.panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;border-bottom:1px solid var(--line-soft);background:rgba(255,255,255,.025)}.panel-head h2{font-size:11px;letter-spacing:1.1px;text-transform:uppercase}.panel-head span{font:10px var(--mono);color:var(--dim)}.panel-body{padding:16px}.control-grid{display:grid;grid-template-columns:300px 1fr;gap:12px;margin-bottom:15px}.allocation{display:flex;flex-direction:column;gap:13px}.allocation-row{display:grid;grid-template-columns:74px 1fr 86px;gap:10px;align-items:center}.allocation-label{color:var(--muted);font-size:10px}.meter{height:9px;overflow:hidden;border-radius:99px;background:#14263c}.meter-fill{height:100%;min-width:2px;border-radius:99px;background:var(--tone)}.allocation-value{text-align:right;color:#fff;font:10px var(--mono)}.allocation-note{margin-top:15px;padding:10px;border:1px solid rgba(250,178,25,.22);border-radius:9px;background:rgba(250,178,25,.06);color:var(--muted);font-size:10px;line-height:1.6}
.filter-row{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:10px}.filter-btn{padding:6px 10px;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--muted);font-size:10px}.filter-btn:hover,.filter-btn.active{color:#fff;border-color:var(--blue);background:var(--blue-soft)}.sort-select{padding:6px 9px;border:1px solid var(--line);border-radius:7px;background:var(--surface-3);color:var(--muted);font-size:10px}.filter-count{margin-left:auto;color:var(--dim);font:10px var(--mono)}.holdings{max-height:430px;overflow:auto}.holdings-head,.holding-row{display:grid;grid-template-columns:minmax(150px,1fr) 80px 76px 76px 76px 74px;gap:8px;align-items:center}.holdings-head{padding:7px 16px;color:var(--dim);font:9px var(--mono);border-bottom:1px solid var(--line-soft)}.holding-row{padding:8px 16px;border-bottom:1px solid rgba(154,188,225,.07);font-size:10px;transition:.15s}.holding-row:hover{background:rgba(57,135,229,.05)}.holding-row:last-child{border:0}.holding-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#dce8f7}.holding-tag{display:inline-block;margin-left:5px;padding:2px 5px;border-radius:4px;font-size:8px}.tag-b{color:var(--blue);background:rgba(57,135,229,.12)}.tag-g{color:var(--green);background:rgba(54,211,156,.1)}.tag-a{color:var(--amber);background:rgba(250,178,25,.1)}.tag-r{color:var(--red);background:rgba(230,103,103,.1)}.num{text-align:right;color:var(--muted);font:10px var(--mono)}.positive{color:var(--red)}.negative{color:var(--green)} /* 红盈绿亏（A股习惯） */
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:15px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:15px}.list{max-height:330px;overflow:auto}.rule-row,.risk-row,.watch-row,.action-row{padding:9px 0;border-bottom:1px solid rgba(154,188,225,.07);font-size:10.5px}.rule-row:last-child,.risk-row:last-child,.watch-row:last-child,.action-row:last-child{border-bottom:0}.rule-row{display:flex;gap:8px;align-items:flex-start}.dot{width:8px;height:8px;margin-top:4px;flex:0 0 auto;border-radius:50%;background:var(--green)}.dot.watch{background:var(--amber);box-shadow:0 0 7px rgba(250,178,25,.45)}.dot.action{background:var(--red);box-shadow:0 0 9px rgba(230,103,103,.52)}.muted{color:var(--muted)}.risk-row,.watch-row{display:grid;grid-template-columns:25px 1fr auto;gap:8px;align-items:center}.risk-level{font-size:13px}.risk-detail,.watch-trigger{color:var(--dim);font-size:9px;text-align:right}.action-row strong{display:block;color:#fff;font-size:10px}.action-row span{display:block;color:var(--muted);margin-top:2px}.action-row small{display:block;color:var(--dim);font-size:9px;margin-top:3px}.empty{padding:16px 0;color:var(--dim);font-size:10px}
.trend-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.trend-card{padding:14px;border:1px solid var(--line-soft);border-radius:12px;background:rgba(7,17,32,.78)}.trend-title{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}.trend-title strong{font-size:11px}.trend-title span{font:10px var(--mono);color:var(--muted)}.trend-svg{width:100%;height:168px;display:block}.trend-gridline{stroke:rgba(145,164,189,.12);stroke-width:1}.trend-axis{fill:var(--dim);font:9px var(--mono)}.trend-line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}.trend-dot{stroke:var(--surface);stroke-width:2;cursor:pointer}.chart-table{margin-top:12px}.chart-table summary{color:var(--muted);font-size:10px;cursor:pointer}.chart-table table{margin-top:8px;width:100%;border-collapse:collapse}.chart-table td{padding:4px;color:var(--muted);font:9px var(--mono);border-bottom:1px solid rgba(154,188,225,.07)}
.daily{max-height:420px;overflow:auto}.daily-row{display:grid;grid-template-columns:84px 120px 1fr;gap:13px;padding:11px 0;border-bottom:1px solid rgba(154,188,225,.07);font-size:10.5px}.daily-row:last-child{border-bottom:0}.daily-date{color:#fff;font:10px var(--mono)}.daily-market{color:var(--muted)}.daily-note{color:var(--muted)}.daily-note b{color:var(--amber);font-weight:600}.meta{padding:18px 0 0;color:var(--dim);font:10px var(--mono);text-align:center;line-height:1.9}.meta a{color:var(--blue);text-decoration:none}.footer{margin-top:18px;padding-top:20px;border-top:1px solid var(--line-soft);color:var(--dim);font:10px var(--mono);text-align:center;line-height:2}
@media(max-width:1200px){.kpi-grid{grid-template-columns:repeat(3,1fr)}.control-grid{grid-template-columns:1fr}.grid3,.grid2{grid-template-columns:1fr 1fr}.topstat{display:none}}@media(max-width:760px){.app{padding:10px 8px 35px}.topbar{flex-wrap:wrap;padding:10px 12px}.spacer{display:none}.status{margin-left:auto}.kpi-grid{grid-template-columns:repeat(2,1fr)}.grid3,.grid2,.trend-grid{grid-template-columns:1fr}.holdings-head,.holding-row{grid-template-columns:minmax(130px,1fr) 66px 62px 62px}.holdings-head span:nth-child(5),.holdings-head span:nth-child(6),.holding-row .optional{display:none}.daily-row{grid-template-columns:1fr;gap:4px}.daily-market{font-size:9px}}@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
</style>
</head>
<body>
<div class="app">
<header class="topbar"><div class="brand"><span class="brand-mark">⚓</span><span><em>Anchor</em> Terminal</span></div><span class="badge">v3.5 PRIVATE</span><span class="status safe" id="headerStatus">状态计算中</span><span class="spacer"></span><div class="topstat">数据源<b>本地 portfolio_data.json</b></div><div class="topstat">更新<b id="updateLabel">--</b></div><div class="clock" id="clock">--</div></header>
<section class="decision safe" id="decision"><div class="decision-icon" id="decisionIcon">◉</div><div class="decision-copy"><strong id="decisionTitle">今日结论计算中</strong><span id="decisionText">等待统一状态合同。</span></div><div class="decision-tag" id="decisionTag">--</div></section>
<section class="kpi-grid" id="kpi"></section>
<section class="control-grid"><div class="panel"><div class="panel-head"><h2>Allocation · 四层配置</h2><span>目标 / 当前</span></div><div class="panel-body"><div class="allocation" id="allocation"></div><div class="allocation-note" id="allocationNote"></div></div></div><div class="panel"><div class="panel-head"><h2>Portfolio control center · 持仓控制台</h2><span id="holdingSummary">--</span></div><div class="panel-body"><div class="filter-row" id="holdingFilters"><button class="filter-btn active" data-layer="all">全部</button><button class="filter-btn" data-layer="bedrock">压舱石</button><button class="filter-btn" data-layer="core">核心</button><button class="filter-btn" data-layer="sat">卫星</button><button class="filter-btn" data-layer="cash">现金</button><select class="sort-select" id="holdingSort" aria-label="持仓排序"><option value="mv">按市值</option><option value="pnl">按盈亏</option><option value="rate">按收益率</option><option value="name">按名称</option></select><span class="filter-count" id="holdingCount"></span></div><div class="holdings"><div class="holdings-head"><span>名称 / 状态</span><span>层级</span><span>市值</span><span>盈亏</span><span>收益率</span><span>日涨跌</span></div><div id="holdings"></div></div></div></div></section>
<section class="grid3"><div class="panel"><div class="panel-head"><h2>Rule check · 规则检查</h2><span>自动</span></div><div class="panel-body list" id="rules"></div></div><div class="panel"><div class="panel-head"><h2>Watchlist · 关注清单</h2><span id="watchCount">--</span></div><div class="panel-body list" id="watchlist"></div></div><div class="panel"><div class="panel-head"><h2>Action queue · 待办队列</h2><span id="actionCount">--</span></div><div class="panel-body list" id="actions"></div></div></section>
<section class="grid2"><div class="panel"><div class="panel-head"><h2>Risk board · 风险矩阵</h2><span id="riskSummary">--</span></div><div class="panel-body list" id="risks"></div></div><div class="panel"><div class="panel-head"><h2>Drawdown & freeze · 回撤与冻结</h2><span id="freezeStatus">--</span></div><div class="panel-body" id="drawdown"></div></div></section>
<section class="panel" style="margin-bottom:15px"><div class="panel-head"><h2>Market & PnL trend · 分量趋势</h2><span>单一量纲 · 独立小图</span></div><div class="panel-body"><div class="trend-grid" id="trendGrid"></div><details class="chart-table"><summary>打开趋势数据表</summary><div id="trendTable"></div></details></div></section>
<section class="panel"><div class="panel-head"><h2>Daily review feed · 每日复盘</h2><span id="dailyCount">--</span></div><div class="panel-body daily" id="dailyFeed"></div></section>
<div class="meta">Anchor v3.5 · 四层占比由统一数据合同生成 · 真实数据只存本地<br>回撤基准、风险状态、冻结状态、操作计数均来自 data_processor.process_all()</div>
<footer class="footer"><a href="Anchor/08-website/anchor-pro.html" data-anchor-link="08-website/anchor-pro.html">📖 体系总览</a> · <a href="Anchor/05-scripts/anchor_calculator.html" data-anchor-link="05-scripts/anchor_calculator.html">🔢 仓位计算器</a><br>投资有风险，决策需谨慎</footer>
</div>
<script>
var D=__DATA__;
function node(tag,cls,text){var n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n}
function add(parent,tag,cls,text){var n=node(tag,cls,text);parent.appendChild(n);return n}
function svgNode(tag,attrs){var n=document.createElementNS("http://www.w3.org/2000/svg",tag);Object.keys(attrs||{}).forEach(function(k){n.setAttribute(k,attrs[k])});return n}
function money(v){return Number(v||0).toLocaleString("en-US",{maximumFractionDigits:0})}
function signed(v){var n=Number(v||0);return (n>=0?"+":"")+money(n)}
function tone(layer){return {bedrock:"var(--blue)",core:"var(--green)",sat:"var(--amber)",cash:"var(--dim)"}[layer]||"var(--blue)"}
function levelClass(level){return level==="red"?"action":level==="amber"?"watch":"safe"}
function levelIcon(level){return level==="red"?"🔴":level==="amber"?"🟡":"🟢"}
function updateClock(){var now=new Date(),days=["日","一","二","三","四","五","六"];document.getElementById("clock").textContent=now.toLocaleDateString("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit"})+" "+now.toLocaleTimeString("zh-CN",{hour12:false})+" · 周"+days[now.getDay()]}
updateClock();setInterval(updateClock,1000);document.getElementById("updateLabel").textContent=D.time||D.source_update_date||"--";

(function(){var state=D.risk_state||{},today=D.today||{},freeze=D.freeze_state||{},level=state.level||"green",decision=document.getElementById("decision");decision.className="decision "+levelClass(level);document.getElementById("headerStatus").className="status "+levelClass(level);document.getElementById("headerStatus").textContent=state.label||"安全";document.getElementById("decisionIcon").textContent=today.ic||levelIcon(level);document.getElementById("decisionTag").textContent=today.tag||state.label||"安全";document.getElementById("decisionTitle").textContent=level==="red"?"今天先处理红灯，再考虑新动作":level==="amber"?"今天以观察和等待为主":"今天没有必须执行的交易";var reasons=(state.reasons||[]).concat(freeze.reasons||[]);document.getElementById("decisionText").textContent=(today.tx||[]).map(function(x){return x.t||""}).filter(Boolean).join(" · ")||reasons.join(" · ")||"全部规则通过，保持当前计划。"+(freeze.frozen?" 当前存在冻结条件。":"")})();

(function(){var root=document.getElementById("kpi"),ops=D.ops_state||{},dd=D.drawdown_state||{},hc=D.holding_counts||{},cashRatio=Number(D.portfolio_state?D.portfolio_state.cash_ratio:0)*100,items=[
  ["Total assets","¥"+money(D.total),"基金 ¥"+money(D.fundMv)+" · 股票 ¥"+money(D.stockMv),"var(--blue)"],
  ["Hold PnL",signed(D.totalPnl),hc.active_label||"持仓动态计算",Number(D.totalPnl||0)>=0?"var(--red)":"var(--green)"], /* 红盈绿亏 */
  ["Drawdown",(Number(dd.dd_pct||D.dd_pct||0)>=0?"+":"")+Number(dd.dd_pct||D.dd_pct||0).toFixed(1)+"%","高点 ¥"+money(dd.peak_assets||D.peak_assets),levelClass(dd.dd_level)==="safe"?"var(--green)":"var(--amber)"],
  [ops.label||"Ops",String(ops.count||D.aug_ops||0)+" / "+String(ops.max||D.aug_ops_max||0),ops.violations?String(ops.violations)+" 次违规":"零违规",ops.is_over_limit?"var(--red)":ops.is_at_limit?"var(--amber)":"var(--green)"],
  ["Cash buffer",cashRatio.toFixed(1)+"%","硬下限 10%",cashRatio<10?"var(--red)":"var(--cyan)"],
  ["Active holdings",hc.active_label||String(hc.active||0)+" 项","层级动态生成","var(--purple)"]
];items.forEach(function(item){var card=node("article","kpi");card.style.setProperty("--tone",item[3]);add(card,"div","kpi-label",item[0]);add(card,"div","kpi-value",item[1]);add(card,"div","kpi-sub",item[2]);root.appendChild(card)})})();

(function(){var box=document.getElementById("allocation"),rows=D.layers||[];rows.forEach(function(l){var row=node("div","allocation-row"),m=add(row,"div","allocation-label",l.label),track=add(row,"div","meter"),fill=add(track,"div","meter-fill");fill.style.setProperty("--tone",tone(l.key));fill.style.width=Math.min(Number(l.pct||0),100)+"%";add(row,"div","allocation-value",Number(l.pct||0).toFixed(1)+"% / "+l.target+"%");box.appendChild(row)});var state=D.portfolio_state||{},freeze=D.freeze_state||{};document.getElementById("allocationNote").textContent="现金安全垫 "+(Number(state.cash_ratio||0)*100).toFixed(1)+"% · "+(freeze.frozen?"当前冻结："+(freeze.reasons||[]).join("、"):"当前未触发全局冻结")})();

(function(){var current="all",sort="mv",root=document.getElementById("holdings"),layers=D.layers||[],items=[];layers.forEach(function(l){(D[l.key]||[]).forEach(function(item){items.push(Object.assign({},item,{layer:l.key,layerLabel:l.label}))})});function render(){root.textContent="";var visible=items.filter(function(i){return current==="all"||i.layer===current});visible.sort(function(a,b){if(sort==="name")return String(a.n).localeCompare(String(b.n),"zh");if(sort==="pnl")return Number(b.pnl||0)-Number(a.pnl||0);if(sort==="rate")return Number(b.rt||0)-Number(a.rt||0);return Number(b.mv||0)-Number(a.mv||0)});visible.forEach(function(i){var row=node("div","holding-row"),name=add(row,"span","holding-name",i.n||"未命名");if(i.tag)add(name,"span","holding-tag "+(i.tc||"tag-a"),i.tag);add(row,"span","num",i.layerLabel);add(row,"span","num","¥"+money(i.mv));add(row,"span","num "+(Number(i.pnl||0)>=0?"positive":"negative"),signed(i.pnl));add(row,"span","num "+(Number(i.rt||0)>=0?"positive":"negative"),(Number(i.rt||0)>=0?"+":"")+Number(i.rt||0).toFixed(1)+"%");add(row,"span","num optional "+(Number(i.dp||0)>=0?"positive":"negative"),signed(i.dp));root.appendChild(row)});document.getElementById("holdingCount").textContent=visible.length+" 项"}document.querySelectorAll("#holdingFilters [data-layer]").forEach(function(btn){btn.addEventListener("click",function(){current=btn.dataset.layer;document.querySelectorAll("#holdingFilters [data-layer]").forEach(function(b){b.classList.toggle("active",b===btn)});render()})});document.getElementById("holdingSort").addEventListener("change",function(){sort=this.value;render()});document.getElementById("holdingSummary").textContent=(D.holding_counts||{}).active_label||"动态持仓";render()})();

(function(){var root=document.getElementById("rules"),rules=D.rules||[],dd=D.drawdown_state||{};rules.forEach(function(r){var row=node("div","rule-row"),dot=add(row,"span","dot "+levelClass(r.lv==="rr"?"red":r.lv==="ra"?"amber":"green"));add(row,"span","muted",r.t||"");row.insertBefore(dot,row.firstChild);root.appendChild(row)});var extra=add(root,"div","rule-row");add(extra,"span","dot watch");add(extra,"span","muted","回撤线 · -5% "+money(dd.lines&&dd.lines.minus5)+" / -10% "+money(dd.lines&&dd.lines.minus10)+" / -15% "+money(dd.lines&&dd.lines.minus15))})();

(function(){var root=document.getElementById("watchlist"),wl=D.wl||[];document.getElementById("watchCount").textContent=wl.length+" 项";if(!wl.length){add(root,"div","empty","暂无关注项");return}wl.forEach(function(w){var row=node("div","watch-row");add(row,"span","risk-level",w.status&&w.status.indexOf("🔴")>=0?"🔴":"🟡");var main=add(row,"span",null,w.sector||w.s||"未命名板块");add(main,"small","muted",(w.etf_code||w.c||"")+" · "+(w.status||w.st||""));add(row,"span","watch-trigger","触发："+(w.trigger||w.t||"观察"));root.appendChild(row)})})();

(function(){var root=document.getElementById("actions"),pa=D.pa||[];document.getElementById("actionCount").textContent=pa.length+" 项";if(!pa.length){add(root,"div","empty","暂无待办");return}pa.forEach(function(p){var row=node("div","action-row");add(row,"strong",null,p.p||p.priority||"待办");add(row,"span",null,p.t||p.name||p.action||"");add(row,"small",null,(p.d||p.action||"")+(p.u?" · 更新 "+p.u:""));root.appendChild(row)})})();

(function(){var root=document.getElementById("risks"),risks=D.risks||[];var red=risks.filter(function(r){return r.l==="red"}).length,amber=risks.filter(function(r){return r.l==="amber"}).length;document.getElementById("riskSummary").textContent=red+" 红 / "+amber+" 黄";if(!risks.length){add(root,"div","empty","暂无风险项");return}risks.forEach(function(r){var row=node("div","risk-row");add(row,"span","risk-level",levelIcon(r.l));var main=add(row,"span",null,r.n||"风险项");add(main,"small","muted",r.c==="r"?"需要处理":r.c==="a"?"持续观察":"当前稳定");add(row,"span","risk-detail",r.d||"");root.appendChild(row)})})();

(function(){var root=document.getElementById("drawdown"),dd=D.drawdown_state||{},freeze=D.freeze_state||{},state=D.risk_state||{};function line(label,value,cls){var row=node("div","summary-stat");add(row,"span",null,label);add(row,"strong",cls,value);root.appendChild(row)}line("当前回撤",(Number(dd.dd_pct||0)>=0?"+":"")+Number(dd.dd_pct||0).toFixed(1)+"%",levelClass(dd.dd_level)==="safe"?"positive":"negative");line("触发线",dd.triggered_line?"-"+dd.triggered_line+"%":"未触发",dd.triggered_line?"negative":"positive");line("冻结状态",freeze.frozen?"已冻结":"未冻结",freeze.frozen?"negative":"positive");var note=add(root,"div","allocation-note",freeze.frozen?(freeze.reasons||[]).join(" · "):"允许现有仓位退出；新增买入仍需通过规则检查");note.style.marginTop="12px";document.getElementById("freezeStatus").textContent=freeze.frozen?"冻结中":"可观察"})();

function renderTrendCard(root,data,key,label,color,formatter){var card=node("article","trend-card"),title=node("div","trend-title");add(title,"strong",null,label);var last=data.length?data[data.length-1][key]:0;add(title,"span",null,formatter(last));card.appendChild(title);var svg=svgNode("svg",{viewBox:"0 0 600 180",role:"img","aria-label":label+"趋势图"}),values=data.map(function(d){return Number(d[key]||0)}),min=Math.min.apply(null,values.concat([0])),max=Math.max.apply(null,values.concat([0]));if(min===max){min-=1;max+=1}var left=42,right=14,top=14,bottom=28,w=600-left-right,h=180-top-bottom;[0,.5,1].forEach(function(step){var y=top+step*h;svg.appendChild(svgNode("line",{x1:left,y1:y,x2:left+w,y2:y,class:"trend-gridline"}));var val=max-step*(max-min),text=svgNode("text",{x:4,y:y+3,class:"trend-axis"});text.textContent=formatter(val);svg.appendChild(text)});var points=data.map(function(d,i){var x=left+(data.length<2?0:i/(data.length-1)*w),y=top+(max-Number(d[key]||0))/(max-min)*h;return [x,y]});if(points.length){svg.appendChild(svgNode("polyline",{points:points.map(function(p){return p[0]+","+p[1]}).join(" "),class:"trend-line",stroke:color}));points.forEach(function(p,i){var circle=svgNode("circle",{cx:p[0],cy:p[1],r:5,class:"trend-dot",fill:color,tabindex:"0"}),titleNode=svgNode("title",{});titleNode.textContent=(data[i].d||"")+" · "+formatter(data[i][key]);circle.appendChild(titleNode);svg.appendChild(circle)})}card.appendChild(svg);var table=node("details","chart-table");var summary=node("summary",null,"数据表");table.appendChild(summary);var tableEl=node("table");data.forEach(function(d){var tr=node("tr");add(tr,"td",null,d.d||"");add(tr,"td",null,formatter(d[key]));tableEl.appendChild(tr)});table.appendChild(tableEl);card.appendChild(table);root.appendChild(card)}
(function(){var root=document.getElementById("trendGrid"),data=D.chart||[];renderTrendCard(root,data,"sh","上证指数","#fab219",function(v){return Number(v||0).toFixed(0)});renderTrendCard(root,data,"st","科创50","#3987e5",function(v){return Number(v||0).toFixed(0)});renderTrendCard(root,data,"pnl","日盈亏","#e66767",function(v){return (Number(v||0)>=0?"+":"")+Number(v||0).toFixed(0)})})(); /* 红盈绿亏 */

(function(){var root=document.getElementById("dailyFeed"),ds=D.ds||[];document.getElementById("dailyCount").textContent=ds.length+" 条";if(!ds.length){add(root,"div","empty","暂无每日总结");return}ds.forEach(function(d){var row=node("div","daily-row");add(row,"div","daily-date",(d.dt||"")+" "+(d.dy||""));add(row,"div","daily-market","上证 "+(d.sh||"--")+" ("+(d.sc||"--")+") · 科创 "+(d.kc||"--")+" ("+(d.kcc||"--")+") · PnL "+(d.pnl||"--"));var note=add(row,"div","daily-note",d.note||"");if(d.ops){add(note,"b",null,"操作："+d.ops)}root.appendChild(row)})})();

(function(){
  // 页脚链接路径修正：看板同时存在于 桌面 与 Anchor/06-dashboard/ 两个位置
  // 06-dashboard 副本 → 用 ../ 上跳一级；桌面副本 → 用 Anchor/ 子目录
  function anchorBase(){
    var h=(window.location.href||"").replace(/\\/g,"/");
    return h.indexOf("/06-dashboard/")>=0?"../":"Anchor/";
  }
  document.querySelectorAll("[data-anchor-link]").forEach(function(a){
    a.href=anchorBase()+a.getAttribute("data-anchor-link");
  });
})();
</script>
</body>
</html>'''

# 转义 `</` 防止 JSON 内容逃逸出 <script> 上下文（数据可能来自外部源）
html = html.replace("__DATA__", json.dumps(embed, ensure_ascii=False).replace("</", "<\\/"))
os.makedirs(ANCHOR_DATA, exist_ok=True)
data_json_dest = os.path.join(ANCHOR_DATA, "portfolio_data.json")
if os.path.abspath(DATA_PATH) != os.path.abspath(data_json_dest):
    shutil.copy2(DATA_PATH, data_json_dest)
    log.info("Data JSON -> %s", data_json_dest)
for path in (HTML_PATH, HTML_PATH2):
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    log.info("Private HTML -> %s (%s bytes)", path, f"{len(html):,}")
for path in (SNAPSHOT_PATH, SNAPSHOT_PATH2):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    log.info("Snapshot -> %s", path)

def ratio(key):
    total = embed.get("total", 0) or 0
    return embed.get(key, 0) / total * 100 if total else 0

log.info(
    "Total: CNY %s | Bedrock %.1f%% | Core %.1f%% | Sat %.1f%% | Cash %.1f%%",
    f"{embed['total']:,.0f}", ratio("bedrock_mv"), ratio("core_mv"), ratio("sat_mv"), ratio("cash_mv"),
)
log.info("PnL: %s | Holdings: %s", fp(embed["totalPnl"]), embed.get("holding_counts", {}).get("active_label", "暂无持仓"))

today = date.today()
mkt_date_str = embed.get("mkt", {}).get("date", "")
try:
    mkt_age = (today - datetime.strptime(mkt_date_str, "%Y-%m-%d").date()).days
except (TypeError, ValueError):
    mkt_age = 999
log.info("Market data: %s (%sd ago) %s", mkt_date_str, mkt_age, "[STALE]" if mkt_age > 1 else "[OK]")
alerts = [r for r in embed["rules"] if r.get("lv") == "rr"]
warns = [r for r in embed["rules"] if r.get("lv") == "ra"]
log.info("Rule alerts: %s RED, %s AMBER", len(alerts), len(warns))
for item in embed["pa"]:
    if "8/20" in str(item).lower() or "8月20" in str(item):
        log.info("[TIMER] 创新药时间止损提醒")
log.info("Done.")
