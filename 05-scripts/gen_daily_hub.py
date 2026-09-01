#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_daily_hub.py — Anchor 当日指挥中心入口页生成器（v4.1.0）

把"当天需要看的文件"聚合到单一页面：
  - 顶部今日快照（总资产/当日盈亏/四层/上证/决策日志）—— 数据内联自 portfolio_data.json
  - 今日信号区（红绿灯）—— 半导体/创新药/时机A/月操作/回撤，数据驱动
  - 实时仪表盘直达（私有看板/决策胜率/公开页/图集）—— 点击即开
  - 事件日历（未来 7 事件 + 关联文件）
  - 报告中心 / 数据文件 / 系统工具 / 快捷口令 —— 分类链接直达

技术要点：
  - 数据全部内联（file:// 下 fetch 本地 JSON 会被 CORS 拦截，故生成时注入）
  - 模板用 __PLACEHOLDER__ 占位替换（避免 f-string 与 HTML/JS 花括号冲突）
  - 相对链接（页面位于 06-dashboard/，用 ../ 上跳）
  - GSAP 增强（CDN 加载失败 → .no-gsap 纯静态，内容完整可见；reduced-motion 静态）
  - 复用 portfolio_analysis.html 同款主题色，视觉协调

用法: python gen_daily_hub.py      （sync_all.py 已自动调用；也可单独运行）
"""
import json, os, sys, glob, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
from decision_log import accuracy_report
from data_processor import process_all  # 复用权威派生数据（四层/风险/回撤/操作），口径与主看板一致
from freshness_watchdog import banner_html  # B3：数据陈旧页顶横幅

# ============ 工具函数 ============
def money(v, digits=0):
    """金额格式化，千分位"""
    try:
        n = float(v)
        return f"{n:,.{digits}f}"
    except (TypeError, ValueError):
        return "--"

def signed(v, digits=0, with_pct=False):
    """带符号数字（A股习惯：红盈绿亏由 CSS class 控制，这里只输出 +/- 数值）"""
    try:
        n = float(v)
        s = f"{n:+,.{digits}f}"
        return s + ("%" if with_pct else "")
    except (TypeError, ValueError):
        return "--"

def is_positive(v):
    """判断数值正负（防御字符串/None）"""
    try:
        return float(v) >= 0
    except (TypeError, ValueError):
        return True  # 未知按中性处理

def pct_str(v, digits=1):
    try:
        return f"{float(v):.{digits}f}%"
    except (TypeError, ValueError):
        return "--"

def esc(s):
    """HTML 转义"""
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ============ 数据加载 ============
DATA_PATH = paths.DATA_PATH  # 桌面 portfolio_data.json（权威源）
ANCHOR = paths.ANCHOR

def load_data():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)

def latest_report(kind, keyword=""):
    """找 04-reviews/<kind>/ 下最新含 keyword 的报告文件（相对 ANCHOR 的 Path）"""
    d = ANCHOR / "04-reviews" / kind
    if not d.is_dir():
        return None
    files = [p for p in d.glob("*.md") if (keyword in p.name or not keyword)]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)

# ============ 数据片段构建 ============
def build_kpis(processed, data, rep):
    """今日快照 KPI 行（数据全部来自 process_all 权威派生）"""
    mkt = processed.get("mkt", {}) or {}
    sh = mkt.get("sh", {}) or {}
    kc = mkt.get("kc", {}) or {}
    ds = processed.get("ds", [])
    today = ds[0] if ds else {}
    pnl = today.get("pnl")  # process_all 缩写键：pnl = portfolio_day_pnl_est
    total = processed.get("total", 0)
    hold_pnl = processed.get("totalPnl", 0)
    # 基金账户按用户 App 口径（含现金层余额宝），股票账户为持仓市值
    fund = data.get("fund_account", 0)
    stock = data.get("stock_account", 0)
    cash_mv = processed.get("cashMv", 0)

    kpis = [
        ("Total assets", f"¥{money(total)}", f"基金账户 ¥{money(fund)} · 股票 ¥{money(stock)}", "var(--blue)"),
        ("今日盈亏", signed(pnl), "基金+现金 + 股票 515180", "var(--red)" if is_positive(pnl) else "var(--green)"),
        ("持有盈亏", signed(hold_pnl), "基金 + 股票 全部未实现", "var(--red)" if is_positive(hold_pnl) else "var(--green)"),
        ("上证指数", f"{sh.get('close', '--')} {sh.get('change', '')}", "科创50 " + str(kc.get("close", "--")) + " " + str(kc.get("change", "")), "var(--amber)"),
        ("决策日志", f"{rep.get('total_decisions', 0)} 条", f"准确率 {rep.get('accuracy_pct') or '--'}% · 盈亏比 {rep.get('pnl_ratio') or '--'}:1", "var(--purple)"),
        ("现金缓冲", pct_str((cash_mv / total * 100) if total else 0), "目标 15% · 超配留进攻层", "var(--green)"),
    ]
    return "".join(
        f'<article class="kpi reveal" style="--tone:{c}"><div class="kpi-label">{l}</div>'
        f'<div class="kpi-value">{v}</div><div class="kpi-sub">{s}</div></article>'
        for l, v, s, c in kpis
    )

def build_strips(processed):
    """四层配比条带（条宽∝配比，左对齐；点击跳主看板）"""
    layers = processed.get("layers", [])
    if not layers:
        return '<div class="empty">四层占比待 rebuild 注入（先跑 sync_all 或 rebuild.py）</div>'

    tone = {"bedrock": "var(--blue)", "core": "var(--green)", "sat": "var(--amber)", "cash": "var(--purple)"}
    icons = {"bedrock": "🛡️", "core": "🚀", "sat": "🔥", "cash": "💰"}
    max_pct = max((float(l.get("pct", 0)) for l in layers), default=1) or 1
    rows = []
    for l in layers:
        p = float(l.get("pct", 0))
        w = max(4.0, p / max_pct * 100)  # 最长条铺满轨道
        key = l.get("key", "")
        rows.append(
            f'<a class="strip-row" href="portfolio_analysis.html" title="打开私有看板查看四层明细">'
            f'<span class="strip-icon">{icons.get(key, "◈")}</span>'
            f'<span class="strip-label">{esc(l.get("label", ""))}</span>'
            f'<span class="strip-track"><span class="strip-fill" data-w="{w:.1f}" style="--tone:{tone.get(key, "var(--blue)")}"></span></span>'
            f'<span class="strip-val">{p:.1f}%<em>/ 目标 {l.get("target", "--")}%</em></span></a>'
        )
    return "".join(rows)

def build_signals(processed, data, rep):
    """今日信号区（红绿灯）"""
    slw = (data.get("stop_loss_watch") or {}).get("华夏半导体芯片ETF联接C", {})
    cards = []

    def card(status, title, desc, link, link_txt, tone):
        icon = {"🟢": "safe", "🟡": "watch", "🔴": "action", "⚪": "neutral"}.get(status, "watch")
        cls = {"safe": "safe", "watch": "watch", "action": "action", "neutral": "neutral"}[icon]
        return (f'<div class="signal {cls} reveal"><div class="signal-top"><span class="signal-status">{status}</span>'
                f'<span class="signal-title">{esc(title)}</span><span class="spacer"></span><span class="signal-tag">{cls}</span></div>'
                f'<div class="signal-desc">{esc(desc)}</div>'
                f'<a class="signal-link" href="{link}">→ {esc(link_txt)}</a></div>')

    # 半导体
    if slw:
        cur = slw.get("cur_pct", 0)
        # 观察仓市值从持仓明细取（避免把 cur_pct 百分比误当金额）
        semi_mv = next((h.get("mv") for h in data.get("holdings_summary", []) if "半导体" in (h.get("name") or "")), None)
        mv_txt = f"¥{money(semi_mv, 0)}" if semi_mv is not None else "--"
        semi_desc = (f"止损执行闭环完成：赎回款 ¥491.60 已到账；剩余观察仓约 {mv_txt}（浮亏 {pct_str(cur)}）。"
                     f"8/25 超大单 +9.73亿首日转正=止跌观察，但主力 -17.56亿 —— DDX 连正≥2日前不动")
        cards.append(card("🟡", "半导体观察仓", semi_desc, "portfolio_analysis.html", "打开主看板 · 8/27 复盘 #22", "watch"))
    else:
        cards.append(card("🟢", "半导体", "无在途止损项", "portfolio_analysis.html", "打开主看板", "safe"))

    # 创新药
    inno = "持有收益转正 +33.73（+1.34%），整仓累计 -271.55 待回补；建仓 +3000 暂缓（南向未连入，等双确认）；9/7 港股通纳入 14 家医药 = 窗口"
    cards.append(card("🟡", "创新药 +3000 暂缓", inno, "portfolio_analysis.html", "打开主看板 · 8/27 复盘 #23", "watch"))

    # 时机A
    sh_close = ((processed.get("mkt", {}) or {}).get("sh", {}) or {}).get("close")
    if sh_close is not None and float(sh_close) >= 3900:
        cards.append(card("🟢", "时机A", "上证站稳 3900 连 2 天 → 新子弹可用", "portfolio_analysis.html", "打开主看板", "safe"))
    else:
        cards.append(card("⚪", "时机A 待确认", "上证需「再站上 3900 连 2 天」才重新触发；当前未收复 3900", "portfolio_analysis.html", "打开主看板", "neutral"))

    # 月操作 / 冻结
    ops = processed.get("ops_state", {}) or {}
    ops_txt = f"8月操作 {ops.get('count', '--')}/{ops.get('max', '--')} 笔" + (" · 额度已满 · 禁止新买入" if ops.get("is_at_limit") else " · 可操作")
    cards.append(card("🟡", "月操作额度", ops_txt, "portfolio_analysis.html", "打开主看板", "watch"))

    # 回撤
    dd = processed.get("drawdown_state", {}) or {}
    dd_txt = f"回撤 {pct_str(dd.get('dd_pct'))}（安全区）· 距 -5% 线还余 ¥{money(dd.get('safe_cushion'))}"
    cards.append(card("🟢", "回撤安全", dd_txt, "portfolio_analysis.html", "打开主看板", "safe"))

    # 决策日志
    ratio = rep.get("pnl_ratio")
    ratio_ok = ratio is not None and float(ratio) >= 1.5
    status_icon = "🟢" if ratio_ok else "🟡"
    dec_txt = (f"{rep.get('total_decisions', 0)} 条 · 准确率 {rep.get('accuracy_pct')}% · 盈亏比 {ratio or '--'}:1"
               f"（目标 ≥1.5:1{' ✅' if ratio_ok else '，8/27 复盘后整改'}）· 待复盘 #22/#23（8/27）")
    cards.append(card(status_icon, "决策日志", dec_txt, "decision_dashboard.html", "打开决策胜率仪表盘", "safe" if ratio_ok else "watch"))

    return "".join(cards)

def build_dashes():
    """实时仪表盘直达（4 张大卡）"""
    dashes = [
        ("📊", "私有主看板", "portfolio_analysis.html", "四层占比 / 持仓控制台 / 规则检查 / 风险矩阵 / 每日复盘 · 实时数据内联", "HTML · 实时"),
        ("🎯", "决策胜率仪表盘", "decision_dashboard.html", "26 条决策 · 准确率 / 盈亏比 / 追高占比 / T+3 复盘提醒", "HTML · 实时"),
        ("🌐", "公开体系页", "../08-website/anchor-pro.html", "Anchor v4.0 体系介绍 · 四层金字塔 / 进化叙事 · GSAP 动效", "HTML · 动态"),
        ("🗺️", "体系图集", "../08-website/diagrams/", "pyramid-4layer / data-pipeline / decision-loop / architecture · 4 张体系图（内嵌 SVG）", "HTML · 静态"),
    ]
    return "".join(
        f'<a class="dash-card reveal" href="{href}" style="--tone:var(--blue)"><span class="dash-icon">{icon}</span>'
        f'<span class="dash-body"><strong>{esc(title)}</strong><span>{esc(sub)}</span></span>'
        f'<span class="dash-type">{typ}</span></a>'
        for icon, title, href, sub, typ in dashes
    )

# 事件日历：固定序列，gen 时按日期过滤（过去自动消失，未来自动显示）
EVENTS = [
    {"d": "2026-08-26", "t": "英伟达财报（凌晨）+ 核心 PCE", "e": "半导体 / 纳指 / 黄金三方方向观测窗：财报定企稳质量、PCE 定金价方向", "files": [("黄金专题", "04-reviews/special/2026-08-24-黄金走势深度分析.md"), ("盘中研究 8/25", "04-reviews/research/2026-08-25-盘中研究报告.md")]},
    {"d": "2026-08-27", "t": "决策日志 T+3 复盘 #22 + #23", "e": "#22 半导体止损执行效果 + #23 创新药观望双确认 + 登海种业中报验证", "files": [("深度复盘 8/25", "04-reviews/daily/2026-08-25-深度复盘.md"), ("决策仪表盘", "06-dashboard/decision_dashboard.html")]},
    {"d": "2026-08-28", "t": "杰克逊霍尔（沃什首秀）", "e": "本周最大变量：决定美债利率与降息路径，联动黄金/纳指", "files": [("黄金专题", "04-reviews/special/2026-08-24-黄金走势深度分析.md")]},
    {"d": "2026-08-31", "t": "月度归因（里程碑）", "e": "三目标验证：平均收益率 ≥+3% / 盈亏比 ≥1.5:1 / 加仓准确率 ≥70%（当前 -5.02% / 0.60:1 / 57%）", "files": [("归因清单", "00-system/月度归因八步清单.md"), ("8月归因", "04-reviews/monthly/月度归因_2026年8月.md")]},
    {"d": "2026-09-07", "t": "港股通调整纳入 14 家医药", "e": "创新药最大增量窗口（8/28-9/7 或现提前反弹窗口）", "files": [("深度复盘 8/25", "04-reviews/daily/2026-08-25-深度复盘.md")]},
    {"d": "2026-09-15", "t": "FOMC 议息（9/15-16）", "e": "加息概率 ~40%：美债长端利率路径关键节点", "files": [("黄金专题", "04-reviews/special/2026-08-24-黄金走势深度分析.md")]},
]

def build_events():
    """未来 7 事件（含今日之后），每卡带关联文件"""
    today = datetime.date.today().isoformat()
    future = [e for e in EVENTS if e["d"] >= today][:7]
    if not future:
        return '<div class="empty">近期无已登记事件</div>'
    out = []
    for e in future:
        when = e["d"]
        files = "".join(
            f'<a href="../{href}" class="chip">{esc(name)}</a>'
            for name, href in e["files"]
        )
        out.append(
            f'<div class="event-card reveal"><div class="event-date">{when}</div>'
            f'<div class="event-body"><strong>{esc(e["t"])}</strong><span class="event-desc">{esc(e["e"])}</span>'
            f'<span class="event-files">{files}</span></div></div>'
        )
    return "".join(out)

def build_report_links():
    """报告中心：今日报告 + 周期报告（自动找最新文件）"""
    daily = latest_report("daily", "深度复盘")
    research = latest_report("research")
    gold = latest_report("special", "黄金走势深度分析")
    weekly = latest_report("weekly")
    monthly = latest_report("monthly", "8月")

    def link(label, path, typ):
        if not path:
            return f'<a class="file-card off"><span class="file-name">{esc(label)}</span><span class="file-type">暂无</span></a>'
        rel_p = path.relative_to(ANCHOR).as_posix()
        return (f'<a class="file-card reveal" href="../{rel_p}"><span class="file-name">{esc(label)}</span>'
                f'<span class="file-sub">{esc(rel_p)}</span><span class="file-type">{typ}</span></a>')

    today_section = (
        '<div class="file-group"><h3>今日报告</h3>'
        + link("深度复盘（今日）", daily, "MD")
        + link("盘中研究报告（最新）", research, "MD")
        + link("黄金走势专题", gold, "MD")
        + "</div>"
    )
    cycle_section = (
        '<div class="file-group"><h3>周期报告</h3>'
        + link("周报（最新）", weekly, "MD")
        + link("月度归因（8月）", monthly, "MD")
        + "</div>"
    )
    return today_section + cycle_section

def build_datafiles():
    """数据文件链接"""
    files = [
        ("portfolio_data.json（权威源）", "portfolio_data.json", "JSON · 数据"),
        ("portfolio_snapshot.json（快照）", "portfolio_snapshot.json", "JSON · 快照"),
        ("portfolio_holdings.xlsx（Excel 10表）", "portfolio_holdings.xlsx", "XLSX · 表格"),
        ("decision_log.json（决策日志）", "decision_log.json", "JSON · 隐私"),
    ]
    return "".join(
        f'<a class="file-card reveal" href="{href}"><span class="file-name">{esc(label)}</span>'
        f'<span class="file-sub">{esc(href)}</span><span class="file-type">{typ}</span></a>'
        for label, href, typ in files
    )

def build_tools():
    """系统与工具链接"""
    tools = [
        ("会话检查点", "00-system/会话检查点.md", "每次对话开始先读", "MD"),
        ("数据更新协议", "00-system/数据更新协议.md", "所有更新频率与步骤", "MD"),
        ("投资规则手册 v3.4", "01-rules/投资规则手册_v3.4_正式版.md", "买点/止损/止盈/换仓/仓位", "MD"),
        ("股票交易规则 v1.0", "01-rules/股票交易规则_v1.0.md", "股票 515180 专属规则", "MD"),
        ("月度归因八步清单", "00-system/月度归因八步清单.md", "8/31 归因流程", "MD"),
        ("噪声审计框架", "00-system/噪声审计框架.md", "信号质量审计", "MD"),
        ("公开页", "08-website/anchor-pro.html", "体系介绍 / 展示页", "HTML"),
        ("体系图集", "08-website/diagrams/", "4 张品牌 SVG 图", "HTML"),
    ]
    return "".join(
        f'<a class="file-card reveal" href="../{href}"><span class="file-name">{esc(label)}</span>'
        f'<span class="file-sub">{esc(href)}</span><span class="file-type">{typ}</span></a>'
        for label, href, sub, typ in tools
    )

def build_commands():
    """快捷口令（一句话触发）"""
    cmds = [
        ("更新今日数据", "mx-data 收盘 → 更新 JSON → rebuild → 全量同步", "📥"),
        ("出报告", "14:30→操作建议 / 21:30→收盘复盘", "📝"),
        ("复盘报告", "21:30 收盘复盘（含噪声审计快照）", "📊"),
        ("仓位点检", "四层占比检查 + 红灯扫描", "🔍"),
        ("止损倒计时", "半导体硬Deadline 剩余天数", "⏱️"),
        ("月度归因", "完整月度收益拆解", "📈"),
    ]
    return "".join(
        f'<div class="cmd-card reveal"><span class="cmd-icon">{icon}</span><strong>{esc(label)}</strong>'
        f'<span class="cmd-desc">{esc(desc)}</span><code>说「{esc(label)}」</code></div>'
        for label, desc, icon in cmds
    )

# ============ HTML 模板（__占位符__ 注入，避免 f-string 与 JS 花括号冲突） ============
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Anchor 当日指挥中心 · __UPDATE__ __DAY__</title>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.13.0/dist/gsap.min.js"></script>
<style>
:root{--bg:#02070f;--surface:#071120;--surface-2:#0b1729;--surface-3:#0f1e34;--line:#18304d;--line-soft:rgba(154,188,225,.14);--text:#edf4ff;--muted:#91a4bd;--dim:#6b84a6;--blue:#3987e5;--blue-soft:rgba(57,135,229,.14);--green:#36d39c;--amber:#fab219;--red:#e66767;--purple:#9085e9;--mono:"JetBrains Mono","Cascadia Code",Consolas,monospace;--shadow:0 18px 55px rgba(0,0,0,.25)}
*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}body{background:var(--bg);color:var(--text);font:13px/1.55 Inter,"Segoe UI",system-ui,sans-serif;min-height:100vh;overflow-x:hidden}body:before{content:"";position:fixed;inset:0;z-index:-2;background:radial-gradient(circle at 12% -8%,rgba(57,135,229,.16),transparent 32%),radial-gradient(circle at 92% 86%,rgba(54,211,156,.07),transparent 30%),linear-gradient(180deg,#02070f,#04101c 48%,#02070f)}body:after{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.22;background-image:linear-gradient(rgba(130,170,215,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(130,170,215,.06) 1px,transparent 1px);background-size:48px 48px;mask-image:linear-gradient(#000,transparent 78%)}
a{color:inherit;text-decoration:none}.app{max-width:1240px;margin:0 auto;padding:18px 24px 56px}
.topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:12px;padding:12px 18px;margin-bottom:14px;border:1px solid var(--line-soft);border-radius:13px;background:rgba(4,13,25,.9);backdrop-filter:blur(18px);box-shadow:0 8px 28px rgba(0,0,0,.18)}.brand{display:flex;align-items:center;gap:8px;color:#fff;font-size:18px;font-weight:800;letter-spacing:-.5px}.brand-mark{display:grid;place-items:center;width:27px;height:27px;border:1px solid rgba(57,135,229,.45);border-radius:8px;color:var(--blue)}.brand em{font-style:normal;color:var(--blue)}.badge{font:600 10px var(--mono);color:var(--blue);border:1px solid rgba(57,135,229,.3);padding:3px 8px;border-radius:999px}.status{font:600 10px var(--mono);padding:4px 10px;border-radius:999px}.status.safe{color:var(--green);background:rgba(54,211,156,.09);border:1px solid rgba(54,211,156,.25)}.status.watch{color:var(--amber);background:rgba(250,178,25,.09);border:1px solid rgba(250,178,25,.25)}.status.action{color:var(--red);background:rgba(230,103,103,.09);border:1px solid rgba(230,103,103,.25)}.spacer{flex:1}.topstat{font-size:10px;color:var(--dim);text-align:right}.topstat b{display:block;color:#fff;font:11px var(--mono)}.clock{font:11px var(--mono);color:var(--amber);padding:5px 10px;border:1px solid rgba(250,178,25,.22);border-radius:7px;background:rgba(250,178,25,.06);white-space:nowrap}
.quicknav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}.quicknav a{font:10px var(--mono);color:var(--muted);padding:5px 11px;border:1px solid var(--line);border-radius:999px;transition:.15s}.quicknav a:hover{color:#fff;border-color:var(--blue);background:var(--blue-soft)}
.kpi-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:14px}.kpi{position:relative;min-height:118px;padding:15px;border:1px solid var(--line-soft);border-radius:12px;background:rgba(7,17,32,.78);overflow:hidden;transition:.2s}.kpi:hover{transform:translateY(-3px);border-color:rgba(57,135,229,.5)}.kpi:after{content:"";position:absolute;left:0;top:0;width:64px;height:2px;background:var(--tone,var(--blue))}.kpi-label{color:var(--dim);font:9px var(--mono);letter-spacing:1px;text-transform:uppercase}.kpi-value{margin-top:9px;color:#fff;font:700 22px var(--mono);letter-spacing:-1px}.kpi-sub{margin-top:6px;color:var(--muted);font-size:10px;line-height:1.45}
.panel{border:1px solid var(--line-soft);border-radius:13px;background:rgba(7,17,32,.78);overflow:hidden;margin-bottom:14px}.panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;border-bottom:1px solid var(--line-soft);background:rgba(255,255,255,.025)}.panel-head h2{font-size:11px;letter-spacing:1.1px;text-transform:uppercase}.panel-head span{font:10px var(--mono);color:var(--dim)}.panel-body{padding:15px 16px}
.strips{display:flex;flex-direction:column;gap:10px}.strip-row{display:grid;grid-template-columns:26px 70px 1fr 108px;gap:11px;align-items:center;padding:8px 10px;border-radius:9px;transition:.18s}.strip-row:hover{background:rgba(57,135,229,.07);transform:translateX(3px)}.strip-icon{font-size:15px;text-align:center}.strip-label{color:var(--muted);font-size:11px}.strip-track{height:12px;overflow:hidden;border-radius:99px;background:#14263c}.strip-fill{display:block;height:100%;border-radius:99px;background:var(--tone);transform-origin:left}.strip-val{color:#fff;font:11px var(--mono);text-align:right;white-space:nowrap}.strip-val em{display:block;color:var(--dim);font-size:9px;font-style:normal}
.signals{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:10px}.signal{position:relative;padding:13px 15px;border:1px solid var(--line-soft);border-left:4px solid var(--dim);border-radius:11px;background:rgba(9,18,33,.7);transition:.18s}.signal:hover{transform:translateY(-2px);border-color:rgba(57,135,229,.45)}.signal.safe{border-left-color:var(--green)}.signal.watch{border-left-color:var(--amber)}.signal.action{border-left-color:var(--red)}.signal.neutral{border-left-color:var(--dim)}.signal-top{display:flex;align-items:center;gap:8px}.signal-status{font-size:14px}.signal-title{color:#fff;font-weight:700;font-size:11.5px}.signal-tag{margin-left:auto;font:9px var(--mono);text-transform:uppercase;letter-spacing:.6px;padding:2px 7px;border-radius:5px;background:rgba(145,164,189,.12);color:var(--muted)}.signal.safe .signal-tag{color:var(--green);background:rgba(54,211,156,.1)}.signal.watch .signal-tag{color:var(--amber);background:rgba(250,178,25,.1)}.signal.action .signal-tag{color:var(--red);background:rgba(230,103,103,.1)}.signal.neutral .signal-tag{color:var(--dim);background:rgba(145,164,189,.08)}.signal-desc{margin-top:7px;color:var(--muted);font-size:10.5px;line-height:1.6}.signal-link{display:inline-block;margin-top:8px;font:10px var(--mono);color:var(--blue)}.signal-link:hover{text-decoration:underline}
.dash-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}.dash-card{display:flex;align-items:center;gap:11px;padding:16px;border:1px solid var(--line-soft);border-radius:13px;background:rgba(7,17,32,.78);transition:.2s;position:relative;overflow:hidden}.dash-card:after{content:"";position:absolute;left:0;top:0;width:100%;height:2px;background:var(--tone,var(--blue));opacity:.8}.dash-card:hover{transform:translateY(-4px);border-color:rgba(57,135,229,.5);box-shadow:var(--shadow)}.dash-icon{font-size:26px;flex:0 0 auto}.dash-body{display:flex;flex-direction:column;gap:3px;min-width:0}.dash-body strong{color:#fff;font-size:13px}.dash-body span:last-child{color:var(--muted);font-size:9.5px;line-height:1.45}.dash-type{position:absolute;top:9px;right:9px;font:8.5px var(--mono);color:var(--dim);border:1px solid var(--line);padding:2px 6px;border-radius:5px}
.events{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:10px}.event-card{display:flex;gap:12px;padding:12px 14px;border:1px solid var(--line-soft);border-radius:11px;background:rgba(9,18,33,.7);transition:.18s}.event-card:hover{border-color:rgba(57,135,229,.45)}.event-date{flex:0 0 64px;color:var(--amber);font:600 11px var(--mono);padding-top:2px}.event-body{display:flex;flex-direction:column;gap:5px;min-width:0}.event-body strong{color:#fff;font-size:11.5px}.event-desc{color:var(--muted);font-size:10px;line-height:1.55}.event-files{display:flex;gap:6px;flex-wrap:wrap}.chip{font:9.5px var(--mono);color:var(--blue);border:1px solid rgba(57,135,229,.3);padding:2px 8px;border-radius:999px;transition:.15s}.chip:hover{background:var(--blue-soft);color:#fff}
.file-group{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px;margin-bottom:12px}.file-group h3{grid-column:1/-1;color:var(--dim);font:9px var(--mono);letter-spacing:1.2px;text-transform:uppercase;margin-bottom:2px}.file-card{display:flex;flex-direction:column;gap:4px;padding:12px 14px;border:1px solid var(--line-soft);border-radius:11px;background:rgba(9,18,33,.7);transition:.18s;position:relative}.file-card:hover{transform:translateY(-3px);border-color:rgba(57,135,229,.5);box-shadow:var(--shadow)}.file-card.off{opacity:.5;pointer-events:none}.file-name{color:#fff;font-weight:700;font-size:11.5px}.file-sub{color:var(--dim);font:9px var(--mono);word-break:break-all}.file-type{position:absolute;top:10px;right:11px;font:8.5px var(--mono);color:var(--blue);border:1px solid rgba(57,135,229,.3);padding:2px 6px;border-radius:5px}
.cmd-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}.cmd-card{display:flex;flex-direction:column;gap:5px;padding:13px 14px;border:1px solid var(--line-soft);border-radius:11px;background:rgba(9,18,33,.7)}.cmd-icon{font-size:17px}.cmd-card strong{color:#fff;font-size:11.5px}.cmd-desc{color:var(--muted);font-size:9.5px}.cmd-card code{font:10px var(--mono);color:var(--amber);background:rgba(250,178,25,.07);border:1px dashed rgba(250,178,25,.25);padding:4px 8px;border-radius:6px;margin-top:2px}
.footer{margin-top:6px;padding:16px 0;color:var(--dim);font:9.5px var(--mono);text-align:center;line-height:2}.footer a{color:var(--blue)}
.empty{padding:14px 0;color:var(--dim);font-size:10px}
/* GSAP 初始态：仅 .js.gsap 生效；no-gsap / reduced-motion 静态可见 */
.js.gsap .reveal{opacity:0;transform:translateY(26px)}
.js.gsap .strip-fill{transform:scaleX(0)}
@media(max-width:1100px){.kpi-grid{grid-template-columns:repeat(3,1fr)}.dash-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:720px){.app{padding:10px 10px 35px}.topbar{flex-wrap:wrap}.kpi-grid{grid-template-columns:repeat(2,1fr)}.dash-grid{grid-template-columns:1fr}.strip-row{grid-template-columns:24px 60px 1fr}.strip-val em{display:none}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important;scroll-behavior:auto!important}.js.gsap .reveal{opacity:1!important;transform:none!important}.js.gsap .strip-fill{transform:none!important}}
</style>
</head>
<body>
<div class="app">
<header class="topbar"><div class="brand"><span class="brand-mark">⚓</span><span><em>Anchor</em> Daily Hub</span></div><span class="badge">v4.1</span><span class="status __STATUS_CLS__">__STATUS_LABEL__</span><span class="spacer"></span><div class="topstat">数据截止<b>__UPDATE__ __DAY__</b></div><div class="clock" id="clock">--</div></header>
<nav class="quicknav">
<a href="#snapshot">今日快照</a><a href="#signals">今日信号</a><a href="#dashboards">实时仪表盘</a><a href="#events">事件日历</a><a href="#reports">报告中心</a><a href="#data">数据文件</a><a href="#tools">系统工具</a><a href="#commands">快捷口令</a>
</nav>
__FRESH_BANNER__

<section class="kpi-grid" id="snapshot">__KPIS__</section>

<section class="panel"><div class="panel-head"><h2>Allocation · 四层配比</h2><span>条宽∝配比 · 点击行跳主看板</span></div><div class="panel-body"><div class="strips">__STRIPS__</div></div></section>

<section class="panel" id="signals"><div class="panel-head"><h2>今日信号 · 红绿灯</h2><span>数据驱动 · 6 项</span></div><div class="panel-body"><div class="signals">__SIGNALS__</div></div></section>

<section id="dashboards"><div class="dash-grid">__DASHES__</div></section>

<section class="panel" id="events"><div class="panel-head"><h2>事件日历 · 今日必读</h2><span>未来事件 + 关联文件</span></div><div class="panel-body"><div class="events">__EVENTS__</div></div></section>

<section class="panel" id="reports"><div class="panel-head"><h2>报告中心</h2><span>自动定位最新文件</span></div><div class="panel-body">__REPORTS__</div></section>

<section class="panel" id="data"><div class="panel-head"><h2>数据文件</h2><span>双击直接打开</span></div><div class="panel-body"><div class="file-group">__DATAFILES__</div></div></section>

<section class="panel" id="tools"><div class="panel-head"><h2>系统与工具</h2><span>规则 · 协议 · 检查点</span></div><div class="panel-body"><div class="file-group">__TOOLS__</div></div></section>

<section class="panel" id="commands"><div class="panel-head"><h2>快捷口令</h2><span>说一句即触发</span></div><div class="panel-body"><div class="cmd-grid">__COMMANDS__</div></div></section>

<div class="footer">Anchor v4.1.0 · 当日指挥中心 · 数据内联自 <a href="portfolio_data.json">portfolio_data.json</a> · 生成 __NOW__ · 打开主看板 / 决策仪表盘可看全量细节</div>
</div>
<script>
(function(){var days=["日","一","二","三","四","五","六"],n=new Date();document.getElementById("clock").textContent=n.toLocaleDateString("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit"})+" "+n.toLocaleTimeString("zh-CN",{hour12:false})+" · 周"+days[n.getDay()]})();
document.documentElement.className+=" js";
var gsapOk=window.gsap;
document.documentElement.className+=gsapOk?" gsap":" no-gsap";
var ioOk=typeof IntersectionObserver==="function";
if(gsapOk && ioOk){
  var io=new IntersectionObserver(function(entries){
    entries.forEach(function(en){if(en.isIntersecting){
      io.unobserve(en.target);
      var el=en.target;
      if(el.classList.contains("strip-fill")){gsap.to(el,{scaleX:1,duration:.7,ease:"power2.out"})}
      else{gsap.to(el,{opacity:1,y:0,duration:.55,ease:"power2.out"})}
    }});
  },{threshold:.12});
  document.querySelectorAll(".reveal").forEach(function(el){io.observe(el)});
  document.querySelectorAll(".strip-fill").forEach(function(el){io.observe(el)});
}else{
  /* 无 GSAP 或无 IO：静态兜底，内容永不消失 */
  document.querySelectorAll(".reveal").forEach(function(el){el.style.opacity=1;el.style.transform="none"});
  document.querySelectorAll(".strip-fill").forEach(function(el){el.style.transform="scaleX(1)"});
}
</script>
</body>
</html>"""

# ============ 主流程 ============
def render_html(data, rep):
    """组装：process_all 权威派生 → 构建各片段 → 模板占位符替换"""
    processed = process_all(data)
    fragments = {
        "__FRESH_BANNER__": banner_html(data),  # B3：fresh 时为空串
        "__KPIS__": build_kpis(processed, data, rep),
        "__STRIPS__": build_strips(processed),
        "__SIGNALS__": build_signals(processed, data, rep),
        "__DASHES__": build_dashes(),
        "__EVENTS__": build_events(),
        "__REPORTS__": build_report_links(),
        "__DATAFILES__": build_datafiles(),
        "__TOOLS__": build_tools(),
        "__COMMANDS__": build_commands(),
    }

    frag = {
        "__UPDATE__": str(data.get("update_date", "")),
        "__DAY__": str(((processed.get("mkt", {}) or {}).get("day")) or ""),
        "__STATUS_CLS__": "safe",
        "__STATUS_LABEL__": "安全",
        "__NOW__": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    risk = processed.get("risk_state", {}) or {}
    lvl = risk.get("level", "green")
    frag["__STATUS_CLS__"] = {"red": "action", "amber": "watch", "green": "safe"}.get(lvl, "safe")
    frag["__STATUS_LABEL__"] = str(risk.get("label", "安全"))

    html = HTML_TEMPLATE
    for k, v in fragments.items():
        html = html.replace(k, v)
    for k, v in frag.items():
        html = html.replace(k, v)
    return html

def main():
    if not DATA_PATH.exists():
        print(f"[gen_daily_hub] 错误：找不到 {DATA_PATH}")
        return 1
    data = load_data()
    rep = accuracy_report()  # 复用 decision_log.py 同口径统计
    html = render_html(data, rep)
    out = paths.DASHBOARD_DIR / "daily_hub.html"
    out.write_text(html, encoding="utf-8")
    print(f"[gen_daily_hub] OK -> {out}")
    print(f"[gen_daily_hub] 数据截止 {data.get('update_date')} · 总资产 ¥{money(data.get('total_assets'))} · 决策 {rep.get('total_decisions')} 条")
    return 0

if __name__ == "__main__":
    sys.exit(main())
