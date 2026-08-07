#!/usr/bin/env python3
"""
Anchor v3.3 — 数据处理器
从 portfolio_data.json 提取、分类、计算所有数据
独立于渲染层，可单独测试
"""
import json
from datetime import date, datetime


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


def fp(v):
    """Format profit/loss with sign"""
    if v is None:
        return "0"
    return f"+{v:,.0f}" if v >= 0 else f"{v:,.0f}"


def fc(v):
    """CSS color class: g=green, r=red"""
    return "g" if v >= 0 else "r"


def rate(pnl, mv):
    """Calculate return rate: pnl / (cost_basis) * 100"""
    if not mv or mv == pnl or mv - pnl == 0:
        return 0
    return pnl / (mv - pnl) * 100


def safe_float(val, default=0):
    """Safely convert string/number to float"""
    if val is None:
        return default
    try:
        return float(str(val).replace(',', ''))
    except (ValueError, TypeError):
        return default


def process_holdings(raw_holdings, stocks):
    """Process holdings into four-layer structure."""
    bedrock, core, sat, cash = [], [], [], []

    for h in raw_holdings:
        name = h.get('name', '')
        mv = h.get('mv', 0) or 0
        if mv <= 0:
            continue
        layer_info = ANCHOR_MAP.get(name)
        if not layer_info:
            continue
        layer, tag, tc = layer_info
        pnl = safe_float(h.get('pnl', 0))
        dp = safe_float(h.get('day_pnl', 0))
        item = {
            "n": name, "mv": round(mv, 2), "pnl": round(pnl, 2),
            "dp": round(dp, 2), "tag": tag, "tc": tc
        }
        if layer == 'bedrock':
            bedrock.append(item)
        elif layer == 'core':
            core.append(item)
        elif layer == 'sat':
            sat.append(item)
        elif layer == 'cash':
            cash.append(item)

    # Add stock holdings to bedrock
    for s in stocks:
        price = s.get('price', 0)
        shares = s.get('shares', 0)
        mv = shares * price
        pnl = safe_float(s.get('pnl', 0))
        dp = safe_float(s.get('day_pnl', 0))
        bedrock.append({
            "n": s.get('name', '515180'), "mv": round(mv, 2),
            "pnl": round(pnl, 2), "dp": round(dp, 2),
            "tag": "永远不卖", "tc": "tag-b", "st": 1
        })

    return bedrock, core, sat, cash


def compute_totals(bedrock, core, sat, cash):
    """Compute layer totals and overall totals."""
    bedrock_mv = sum(i['mv'] for i in bedrock)
    core_mv = sum(i['mv'] for i in core)
    sat_mv = sum(i['mv'] for i in sat)
    cash_mv = sum(i['mv'] for i in cash)
    fund_mv_total = bedrock_mv + core_mv + sat_mv
    total = bedrock_mv + core_mv + sat_mv + cash_mv
    stock_mv = sum(i['mv'] for i in bedrock if i.get('st'))
    total_pnl = sum(i['pnl'] for i in bedrock + core + sat + cash)
    return {
        "bedrock_mv": bedrock_mv, "core_mv": core_mv, "sat_mv": sat_mv,
        "cash_mv": cash_mv, "fund_mv_total": fund_mv_total,
        "total": total, "stock_mv": stock_mv, "total_pnl": total_pnl,
    }


def generate_rules(sat_holdings, data, mkt, totals):
    """Generate rule checks from data (NOT hardcoded)."""
    rules = []
    mkt_note = mkt.get('note', '')
    txns = data.get('transactions', [])
    pa = data.get('pending_actions', [])

    # Count August operations
    aug_txns = [t for t in txns if '2026-08' in str(t.get('date', ''))
                or ('/8/' not in str(t.get('date', ''))
                    and '/8' == str(t.get('date', ''))[:2])]
    aug_ops_count = len(aug_txns)

    # Stop-loss checks for satellite
    for item in sat_holdings:
        r = rate(item['pnl'], item['mv'])
        if r <= -8:
            rules.append({"lv": "rr", "t": f"{item['n'][:12]} 浮亏 {r:.1f}% 触发 -8% 止损线！"})

    # DDX rule
    if 'DDX' in mkt_note or '半导体' in mkt_note:
        if 'DDX连3日为正' in mkt_note or 'DDX转正' in mkt_note or 'DDX连' in mkt_note:
            snippet = mkt_note[mkt_note.find('DDX'):][:40] if 'DDX' in mkt_note else '详见行情'
            rules.append({"lv": "rg", "t": f"半导体 DDX 已确认转正（{snippet}）"})
        elif 'DDX转负' in mkt_note:
            rules.append({"lv": "rr", "t": "半导体 DDX 转负 → 补仓暂停，等待 DDX 连2日为正"})
        else:
            rules.append({"lv": "ra", "t": "半导体 DDX 状态待确认，关注8/10周一"})
    else:
        rules.append({"lv": "ra", "t": "半导体 DDX 数据待更新"})

    # 纳指溢价
    rules.append({"lv": "rr", "t": "纳指ETF溢价率 ~10-12% → 不建仓，等待溢价率 <= 3%"})

    # 创新药时间止损
    for pa_item in pa:
        if '创新药' in str(pa_item) and '8/20' in str(pa_item):
            remaining = (date(2026, 8, 20) - date.today()).days
            rules.append({"lv": "ra", "t": f"创新药时间止损倒计时：8月20日截止（剩{remaining}天）"})
            break
    else:
        rules.append({"lv": "ra", "t": "创新药时间止损倒计时：8月20日截止"})

    # 回撤
    peak_ref = safe_float(data.get('_meta', {}).get('peak_assets', 37535), 37535)
    dd_pct = (totals['total'] - peak_ref) / peak_ref * 100
    safe_cushion = totals['total'] - 31313

    if dd_pct <= -15:
        rules.append({"lv": "rr", "t": f"总资产回撤 {dd_pct:.1f}% 触发 -15% 线！核心增长减 1/3"})
    elif dd_pct <= -10:
        rules.append({"lv": "rr", "t": f"总资产回撤 {dd_pct:.1f}% 触发 -10% 线！卫星全部清仓"})
    elif dd_pct <= -5:
        rules.append({"lv": "ra", "t": f"总资产回撤 {dd_pct:.1f}% 触发 -5% 线！卫星仓位减半"})
    else:
        rules.append({"lv": "rg", "t": f"总资产距 -5% 回撤线 ¥31,313 还有 ¥{safe_cushion:,.0f} 安全垫"})

    # 操作计数
    max_ops = data.get('_meta', {}).get('max_monthly_ops', 4)
    violation_count = sum(1 for t in aug_txns if '违规' in str(t.get('note', '')))
    rules.append({
        "lv": "rg" if violation_count == 0 else "rr",
        "t": f"8月操作 {aug_ops_count}/{max_ops} 笔 · {'零违规 · 纪律满分' if violation_count == 0 else f'{violation_count}次违规！'}"
    })

    return rules


def generate_risk_matrix(data, mkt_note, totals):
    """Generate dynamic risk matrix from data."""
    risks = []
    raw = data.get('holdings_summary', [])
    txns = data.get('transactions', [])
    aug_txns = [t for t in txns if '2026-08' in str(t.get('date', ''))]
    aug_ops_count = len(aug_txns)
    violation_count = sum(1 for t in aug_txns if '违规' in str(t.get('note', '')))
    kc = data.get('market', {}).get('kc', {})

    # DDX
    if 'DDX转负' in mkt_note:
        risks.append({"l": "red", "n": "半导体DDX转负", "d": "主力净流出", "c": "r"})
    elif 'DDX' in mkt_note and ('为正' in mkt_note or '转正' in mkt_note):
        risks.append({"l": "green", "n": "半导体DDX为正", "d": "主力净流入确认", "c": "g"})
    else:
        risks.append({"l": "amber", "n": "半导体DDX待确认", "d": "关注8/10周一", "c": "a"})

    # 纳指溢价
    risks.append({"l": "red", "n": "纳指ETF高溢价", "d": "溢价率~10-12%", "c": "r"})

    # 科创50
    kc_change_str = str(kc.get('change', '0'))
    try:
        kc_change = float(kc_change_str.replace('%', '').replace('+', ''))
    except (ValueError, TypeError):
        kc_change = 0
    if kc_change < 0:
        risks.append({"l": "amber", "n": "科创50回调", "d": f"科创50 {kc_change_str}", "c": "a"})
    else:
        risks.append({"l": "green", "n": "科创50上涨", "d": f"科创50 {kc_change_str}", "c": "g"})

    # 创新药
    remaining_days = (date(2026, 8, 20) - date.today()).days
    if remaining_days <= 5:
        risks.append({"l": "red", "n": "创新药时间紧迫", "d": f"距8/20仅{remaining_days}天", "c": "r"})
    else:
        risks.append({"l": "amber", "n": "创新药时间压力", "d": f"距8/20剩{remaining_days}天", "c": "a"})

    # 黄金
    gold_h = next((h for h in raw if '黄金' in str(h.get('name', '')) and h.get('mv', 0) > 0), None)
    if gold_h:
        gold_day_pct = gold_h.get('day_pct', 0) or 0
        if gold_day_pct > 0.02:
            risks.append({"l": "amber", "n": "黄金短期过热", "d": f"单日+{gold_day_pct*100:.1f}%", "c": "a"})
        else:
            risks.append({"l": "green", "n": "黄金稳健", "d": f"日涨跌 {gold_day_pct*100:+.2f}%", "c": "g"})

    # 固收
    bond_items = [h for h in raw if '债券' in str(h.get('name', '')) and h.get('mv', 0) > 0]
    if bond_items and all(h.get('day_pnl', 0) >= -1 for h in bond_items):
        risks.append({"l": "green", "n": "固收稳定产出", "d": "债券正收益", "c": "g"})

    # 成交量
    vol_str = '--'
    if '万亿' in mkt_note:
        idx = mkt_note.find('万亿')
        vol_str = mkt_note[max(0, idx-5):idx+2]
    risks.append({"l": "green" if '3' in vol_str else "amber",
                  "n": "市场成交量", "d": vol_str, "c": "g" if '3' in vol_str else "a"})

    # 纪律
    if violation_count == 0:
        risks.append({"l": "green", "n": "纪律执行满分", "d": f"8月{aug_ops_count}笔零违规", "c": "g"})
    else:
        risks.append({"l": "red", "n": "存在违规操作", "d": f"{violation_count}次违规", "c": "r"})

    return risks


def prepare_daily_summaries(data):
    """Prepare compact daily summary records."""
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
    return ds_out


def prepare_chart_data(data):
    """Prepare chart data points."""
    chart_out = []
    for c in data.get('chart_data', []):
        chart_out.append({
            "d": c.get('d', ''),
            "sh": round(c.get('sh', 0)),
            "st": round(c.get('star', 0)),
            "pnl": round(safe_float(c.get('pnl', 0)), 0)
        })
    return chart_out


def validate_data(data):
    """Validate portfolio_data.json. Returns list of warnings."""
    warnings = []
    if 'holdings_summary' not in data:
        raise ValueError("Missing required field: holdings_summary")
    if 'market' not in data:
        warnings.append("Missing market data")
    for i, h in enumerate(data.get('holdings_summary', [])):
        if 'name' not in h:
            warnings.append(f"Holding #{i} missing 'name'")
        if 'mv' not in h:
            warnings.append(f"Holding #{i} ('{h.get('name', '?')}') missing 'mv'")
    return warnings


def process_all(data):
    """Process all portfolio data. Returns dict ready for embedding."""
    # Validate
    warnings = validate_data(data)

    # Holdings
    raw = data.get('holdings_summary', [])
    stocks = data.get('stock_holdings', [])
    bedrock, core, sat, cash = process_holdings(raw, stocks)

    # Totals
    totals = compute_totals(bedrock, core, sat, cash)

    # Market
    mkt = data.get('market', {})
    kc = mkt.get('kc', {})

    # Rules
    rules = generate_rules(sat, data, mkt, totals)

    # Risk matrix
    mkt_note = mkt.get('note', '')
    risks = generate_risk_matrix(data, mkt_note, totals)

    # DCA list
    dca_list = [str(d) for d in data.get('dca_running', [])]

    # Daily summaries
    ds_out = prepare_daily_summaries(data)

    # Chart data
    chart_out = prepare_chart_data(data)

    # Build result
    result = {
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total": round(totals['total'], 2),
        "fundMv": round(totals['fund_mv_total'], 2),
        "cashMv": round(totals['cash_mv'], 2),
        "stockMv": round(totals['stock_mv'], 2),
        "totalPnl": round(totals['total_pnl'], 2),
        "bedrock_mv": round(totals['bedrock_mv']),
        "core_mv": round(totals['core_mv']),
        "sat_mv": round(totals['sat_mv']),
        "cash_mv": round(totals['cash_mv']),
        "mkt": mkt,
        "dca": dca_list,
        "bedrock": bedrock,
        "core": core,
        "sat": sat,
        "cash": cash,
        "rules": rules,
        "wl": data.get('watchlist', []),
        "pa": data.get('pending_actions', []),
        "risks": risks,
        "ds": ds_out,
        "chart": chart_out,
        "_warnings": warnings,
    }
    return result
