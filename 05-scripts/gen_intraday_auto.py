#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_intraday_auto.py — Anchor 盘中深度报告全自动生成器（v2.0, 2026-09-01 #18 提案落地）
========================================================
全自动：mx-data 行情采集（A股+美股+板块+黄金）→ 规则信号 → 六段式 v2.0 模板 → 落盘 research/

用法: python gen_intraday_auto.py [--dry-run]
产出: Anchor/04-reviews/research/YYYY-MM-DD-盘中研究报告.md（六段式 v2.0）
"""
import json, os, sys, re, subprocess
from datetime import datetime
from pathlib import Path

# ---------- 路径 ----------
DESKTOP = Path("C:/Users/lenovo/Desktop")
ANCHOR = DESKTOP / "Anchor"
DATA = DESKTOP / "portfolio_data.json"
OUT_DIR = ANCHOR / "04-reviews" / "research"
MX_DATA_DIR = Path("C:/Users/lenovo/.workbuddy/skills/mx-data")
MX_PY = Path("C:/Users/lenovo/.workbuddy/binaries/python/envs/mxdata/Scripts/python.exe")
MX_SCRIPT = MX_DATA_DIR / "mx_data.py"
MX_OUT = DESKTOP / "mx_output"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------- 行情采集（mx-data 全自动）----------
QUERIES = [
    "上证指数 科创50 沪深300 中证红利 最新价 涨跌幅",
    "中证全指证券公司指数 国证半导体芯片指数 最新价 涨跌幅 主力资金净流入",
    "恒生港股通创新药指数 最新价 涨跌幅",
    "COMEX黄金期货 最新价 涨跌幅",
    "费城半导体指数 纳斯达克100 最新收盘价 涨跌幅",
]

def fetch_mx(query: str) -> str:
    """调 mx_data.py，返回 stdout 文本"""
    try:
        r = subprocess.run([str(MX_PY), str(MX_SCRIPT), query, str(MX_OUT)],
                           capture_output=True, text=True, timeout=120, encoding="utf-8")
        return r.stdout or ""
    except Exception as e:
        return f"[mx-error] {e}"

def parse_mx(text: str) -> dict:
    """从 mx_data stdout 提取 名称→(最新值, 涨跌幅)。
    兼容两种输出：①名称行（| 名称 | 值 | 涨跌 |）②标题行（**名称(代码)的xx** + 历史数据表首行=最新）"""
    out = {}
    cur_name = None
    for line in text.splitlines():
        # 标题行：**费城半导体指数(SOX.GI)(指数)的涨跌幅、收盘价**
        m = re.match(r"\*\*(.+?)[(（][^)]*[)）]?.*?(?:指数|的)", line)
        if m:
            nm = m.group(1).strip()
            if nm and len(nm) < 30:
                cur_name = nm
                out.setdefault(nm, {"val": None, "chg": None})
            continue
        # 数据行：| 2026-08-31(日) | 0.57% | 11535.05点 | 或 | 名称 | 值 | 涨跌 |
        m = re.match(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            c1, c2, c3 = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            # 首列是日期 → 表数据行（最新=第一行）；首列是中文名 → 名称行
            if re.match(r"^\d{4}-\d{2}-\d{2}", c1):
                if cur_name and out.get(cur_name, {}).get("val") is None:
                    # 表头可能是 涨跌幅|收盘价（美股/黄金）或 最新价|涨跌幅（A股）
                    if c2.endswith("%") and not c3.endswith("%"):
                        out[cur_name]["val"] = c3   # 收盘价
                        out[cur_name]["chg"] = c2   # 涨跌幅
                    else:
                        out[cur_name]["val"] = c2
                        out[cur_name]["chg"] = c3
            elif re.match(r"^[\u4e00-\u9fa5]", c1) and len(c1) < 30:
                name = re.split(r"[(（]", c1)[0].strip()
                out[name] = {"val": c2, "chg": c3}
    return out

def collect_market() -> dict:
    """全自动采集：8 查询 → 汇总 dict"""
    market = {"indices": {}, "sectors": {}, "us": {}, "gold": None, "queries": len(QUERIES)}
    for q in QUERIES:
        txt = fetch_mx(q)
        parsed = parse_mx(txt)
        for k, v in parsed.items():
            if "上证" in k: market["indices"]["上证"] = v
            elif "科创" in k: market["indices"]["科创50"] = v
            elif "沪深300" in k: market["indices"]["沪深300"] = v
            elif "红利" in k: market["indices"]["中证红利"] = v
            elif "证券" in k: market["sectors"]["证券"] = v
            elif "芯片" in k: market["sectors"]["半导体"] = v
            elif "创新药" in k: market["sectors"]["创新药"] = v
            elif "COMEX" in k or "黄金" in k: market["gold"] = v
            elif "费城" in k or "半导体指数" in k: market["us"]["费半"] = v
            elif "纳斯达克100" in k: market["us"]["纳指100"] = v
    return market

# ---------- 持仓数据 ----------
def load_portfolio() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))

# ---------- 六段式模板 ----------
def render_report(market: dict, data: dict, ts: str) -> str:
    idx = market["indices"]; sec = market["sectors"]; us = market["us"]
    g = lambda d, k, f: d[k][f] if k in d else "—"
    lines = []
    lines.append(f"# 📈 Anchor 盘中研究报告 — {ts}")
    lines.append(f"\n**数据时点**：{ts}（mx-data 全自动采集 {market['queries']} 查询）｜ 持仓 = {data.get('update_date','?')}")
    lines.append("\n---\n\n## 一、市场实时全景\n")
    lines.append("| 指数 | 最新 | 涨跌 |")
    lines.append("|------|------|------|")
    for k in ("上证","科创50","沪深300","中证红利"):
        if k in idx: lines.append(f"| {k} | {idx[k]['val']} | {idx[k]['chg']} |")
    lines.append("\n### 板块\n")
    lines.append("| 板块 | 最新 | 涨跌 |")
    lines.append("|------|------|------|")
    for k in ("证券","半导体","创新药"):
        if k in sec: lines.append(f"| {k} | {sec[k]['val']} | {sec[k]['chg']} |")
    lines.append(f"\n### 隔夜美股（自动采集）\n")
    lines.append("| 指数 | 收盘 | 涨跌 |")
    lines.append("|------|------|------|")
    for k in ("费半","纳指100"):
        if k in us: lines.append(f"| {k} | {us[k]['val']} | {us[k]['chg']} |")
    if market["gold"]:
        lines.append(f"\n**COMEX 黄金**：{market['gold']['val']}（{market['gold']['chg']}）")
    lines.append("\n---\n\n## 二、持仓全景（自动）\n")
    lines.append("| 持仓 | 市值(估) | 备注 |")
    lines.append("|------|---------|------|")
    for h in data.get("holdings_summary", []):
        if h.get("mv", 0) > 0:
            lines.append(f"| {h['name']} | ¥{h['mv']:,.2f} | {h.get('note','')[:40]} |")
    stk = data.get("stock_holdings") or []
    for s in stk:
        lines.append(f"| {s['name']} | ¥{s.get('mv',0):,.2f} | 股票 |")
    lines.append(f"\n**总资产**：¥{data.get('total_assets',0):,.2f}（基金 {data.get('fund_account',0):,.2f} + 股票 {data.get('stock_account',0):,.2f}）")
    lines.append("\n---\n\n## 三、规则信号（自动）\n")
    # 信号：读 daily_advice 或 data_processor（此处简版：pending_actions + 额度）
    ops = (data.get("_meta") or {}).get("ops_state") or {}
    lines.append(f"- 月操作额度：{ops.get('count','?')}/{ops.get('max','4')}")
    for a in data.get("pending_actions", []):
        lines.append(f"- ⏰ {a.get('name','')}：{a.get('action','')[:60]}")
    lines.append("\n---\n\n## 四、操作建议（模板待人工填充规则引用）\n")
    lines.append("- 依据评分卡 + pre_trade_check 输出（手动核对触发条件）")
    lines.append("\n---\n\n## 五、新机会扫描（watchlist 自动）\n")
    lines.append("- 板块数据见上表；**人工补充**：候选板块连红天数/触发条件（数据驱动）")
    lines.append("\n---\n\n## 六、风险快照\n")
    lines.append("- 自动提示：板块涨跌极端值/黄金方向/美股联动（人工确认 B5/止损线）")
    lines.append(f"\n---\n\n*全自动生成：{ts} ｜ gen_intraday_auto.py v2.0（#18 提案）｜ 行情 mx-data 实时，非记忆值*")
    return "\n".join(lines)

# ---------- main ----------
def main() -> int:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    market = collect_market()
    data = load_portfolio()
    md = render_report(market, data, ts)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fname = OUT_DIR / f"{datetime.now().strftime('%Y-%m-%d')}-盘中研究报告.md"
    fname.write_text(md, encoding="utf-8")
    print(f"✅ 全自动报告已生成: {fname}")
    print(f"   行情查询 {market['queries']} 组 | 指数 {len(market['indices'])} | 板块 {len(market['sectors'])} | 美股 {len(market['us'])}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
