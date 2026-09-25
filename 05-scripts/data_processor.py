#!/usr/bin/env python3
"""
Anchor v3.3 — 数据处理器
从 portfolio_data.json 提取、分类、计算所有数据
独立于渲染层，可单独测试
"""
import json
import re
from datetime import date, datetime, timedelta


# ===== ANCHOR LAYER MAPPING =====
# 仅用 group / 关键词兜底分类；不在源码里固化具体持仓名称。
ANCHOR_MAP = {}

LAYER_ORDER = ["bedrock", "core", "sat", "cash"]
LAYER_META = {
    "bedrock": {"k": "bed", "icon": "🛡️", "label": "压舱石", "cls": "b0", "target": 45},
    "core": {"k": "core", "icon": "🚀", "label": "核心增长", "cls": "b1", "target": 20},
    "sat": {"k": "sat", "icon": "🔥", "label": "卫星进攻", "cls": "b2", "target": 20},
    "cash": {"k": "csh", "icon": "💰", "label": "现金预备", "cls": "b3", "target": 15},
}
TAG_CLASS_BY_LAYER = {"bedrock": "tag-b", "core": "tag-g", "sat": "tag-a", "cash": "tag-g"}


def fp(v):
    """Format profit/loss with sign"""
    if v is None:
        return "0"
    return f"+{v:,.0f}" if v >= 0 else f"{v:,.0f}"


def fc(v):
    """CSS color class: g=green, r=red"""
    return "g" if v >= 0 else "r"


def rate(pnl, mv):
    """Calculate return rate: pnl / (cost_basis) * 100
    8/17 审计：成本 <= 0（pnl >= mv，如大幅回血后成本为负）时返回 0，
    避免收益率符号反转导致止损线误判（rate(200,100) 原返回 -200% 会误触 -8% 红线）。"""
    if not mv or mv == pnl or mv - pnl == 0:
        return 0
    cost = mv - pnl
    if cost <= 0:
        return 0
    return pnl / cost * 100


def safe_float(val, default=0):
    """Safely convert string/number to float"""
    if val is None:
        return default
    try:
        return float(str(val).replace(',', ''))
    except (ValueError, TypeError):
        return default


def data_reference_date(data, fallback=None):
    """Return the source-data date so rule countdowns do not drift by runtime date."""
    for key in ('update_date', 'update_time'):
        raw = data.get(key)
        if not raw:
            continue
        try:
            return datetime.strptime(str(raw)[:10], '%Y-%m-%d').date()
        except ValueError:
            continue
    return fallback or date.today()


DEFAULT_CASH_FLOOR = 0.10
DEFAULT_MONTHLY_OPS = 4
# v4.5.1（09-18）：月额度**买卖两维**默认值 —— 手册 §1.3 正文「正常月≤4笔（买入≤2+卖出≤2）」。
# `max_monthly_ops` 是**总数上限**，**不等于**任一维上限；三者独立判定。
DEFAULT_MONTHLY_BUYS = 2
DEFAULT_MONTHLY_SELLS = 2
DEFAULT_MONTHLY_CLEANUP = 6

# 创新药时间止损截止日 —— 单一事实源（规则手册 v3.3：8/20，实际日期优先从数据解析）
TIME_STOP_DEADLINE = date(2026, 8, 20)


def _in_time_stop_window(d, ref):
    """日期窗口守卫（8/17 审计）：时间止损截止日只接受 参考日-7天 ~ 参考日+60天 内的日期，
    防止 pending_actions 文本中的任意日期（如 '8/31归因'、历史日期）误当截止日。"""
    return ref - timedelta(days=7) <= d <= ref + timedelta(days=60)


def time_stop_deadline_from_data(data):
    """从 pending_actions 的时间止损条目解析截止日（'8/20' / '2026-08-20'）。
    语义（8/17 审计加固）：时间止损 = 建仓日 + 30 天。
    解析规则：条目内最早日期视为建仓日；文本中的日期若与 建仓日+30 相差 ≤7 天
    且落在参考日窗口内，才作为截止日候选；否则忽略（防 '8/31归因' 等杂项日期劫持）。"""
    ref = data_reference_date(data)
    candidates = [TIME_STOP_DEADLINE]
    for item in data.get('pending_actions', []):
        txt = str(item)
        if '时间止损' not in txt and '创新药' not in txt:
            continue
        dates = []
        for m in re.finditer(r'(\d{4})-(\d{1,2})-(\d{1,2})', txt):
            try:
                dates.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
            except ValueError:
                pass
        for m in re.finditer(r'(\d{1,2})/(\d{1,2})', txt):
            try:
                dates.append(date(ref.year, int(m.group(1)), int(m.group(2))))
            except ValueError:
                pass
        if not dates:
            continue
        entry = min(dates)  # 建仓日（最早日期）
        for d in dates:
            # 与建仓日相差 ~30 天（±7 容差）且落在窗口内 → 截止日候选
            if abs((d - entry).days - 30) <= 7 and _in_time_stop_window(d, ref):
                candidates.append(d)
        # 兜底：建仓日+30 可直接作为候选，但建仓日须合理（参考日前 5~60 天，
        # 太近说明是行情/备注日期而非建仓日，避免 8/14→9/13 这类误判）
        if ref - timedelta(days=60) <= entry <= ref - timedelta(days=5):
            fallback = entry + timedelta(days=30)
            if _in_time_stop_window(fallback, ref):
                candidates.append(fallback)
    return max(candidates)


def time_stop_remaining(data):
    """时间止损剩余天数（按数据参考日），过期后钳制为 0，不显示负数。"""
    return max((time_stop_deadline_from_data(data) - data_reference_date(data)).days, 0)


def get_peak_assets(data):
    """Return the required peak-assets baseline from portfolio data."""
    peak = data.get('_meta', {}).get('peak_assets')
    if peak in (None, '', 0):
        raise ValueError("Missing required _meta.peak_assets")
    peak = safe_float(peak, 0)
    if peak <= 0:
        raise ValueError("Missing required _meta.peak_assets")
    return peak


def liabilities_in_cash(data):
    """Return the loan principal still sitting in cash (余额宝残留).

    净值口径：自有净值 = total_assets - liabilities.in_cash。
    贷款到账后未转出部分混在余额宝，会虚增回撤基准对照的总资产。
    v3.5.5：回撤/安全垫按净值计算，避免贷款残留虚高安全垫。
    """
    return safe_float(data.get('_meta', {}).get('liabilities', {}).get('in_cash', 0), 0)


def net_outflow_total(data):
    """Return cumulative capital withdrawn from the account (累计净转出).

    净值口径补正项，与 liabilities.in_cash 方向相反：
      - in_cash     = 借来的钱仍留在账户里 → 虚增 total_assets，回撤要扣掉
      - net_outflow = 自己的钱离开了账户   → 压低 total_assets，回撤要加回

    v4.4.7：不补回会制造「假回撤」。9/14 用户转出 ¥8,298.67 至银行卡/消费，
    若不补回：净值 40,848.24 → 回撤 -17.5% → 误触发 -15% 线「核心增长减 1/3」，
    而当日实际为盈利 +98.80。回撤梯子量的是市场回撤，不是提现。
    """
    return safe_float(data.get('_meta', {}).get('net_outflow_total', 0), 0)


def drawdown_status(total, peak):
    """Return explicit drawdown status with signed precedence."""
    if peak <= 0:
        raise ValueError("peak_assets must be > 0")
    dd_pct = (total - peak) / peak * 100
    cushion = total - peak * 0.95
    lines = {
        'minus5': round(peak * 0.95, 2),
        'minus10': round(peak * 0.90, 2),
        'minus15': round(peak * 0.85, 2),
    }
    if dd_pct >= 0:
        return {"level": "safe", "line": None, "dd_pct": dd_pct, "action": "new-high", "cushion": cushion, "lines": lines}
    if dd_pct <= -15:
        return {"level": "red", "line": 15, "dd_pct": dd_pct, "action": "核心增长减 1/3", "cushion": total - peak * 0.85, "lines": lines}
    if dd_pct <= -10:
        return {"level": "red", "line": 10, "dd_pct": dd_pct, "action": "卫星全部清仓", "cushion": total - peak * 0.90, "lines": lines}
    if dd_pct <= -5:
        return {"level": "amber", "line": 5, "dd_pct": dd_pct, "action": "卫星仓位减半", "cushion": cushion, "lines": lines}
    return {"level": "safe", "line": None, "dd_pct": dd_pct, "action": None, "cushion": cushion, "lines": lines}


def compute_drawdown_state(data, totals):
    """Return normalized drawdown state using portfolio data.

    v3.5.5 净值口径：回撤/安全垫以自有净值计算
    （total_assets 扣减账户内贷款残留 liabilities.in_cash），
    防止贷款虚增总资产导致安全垫被高估 3 倍以上。
    v4.4.7 净值口径补正：再加回累计净转出 net_outflow_total，
    防止用户提现/消费被算成市场亏损、误触发减仓线。
    total_assets = 账户口径（含贷款残留，四层占比仍用它）；
    net_assets   = 净值口径（回撤/安全垫用它）= total - in_cash + net_outflow。
    """
    peak = get_peak_assets(data)
    peak_note = data.get('_meta', {}).get('peak_note', '')
    total_assets = safe_float(totals['total'], 0)
    liabilities = liabilities_in_cash(data)
    outflow = net_outflow_total(data)
    net_assets = total_assets - liabilities + outflow
    status = drawdown_status(net_assets, peak)
    triggered_line = status['line']
    if status['level'] == 'safe' and status['dd_pct'] >= 0:
        triggered_line = None
    return {
        'peak_assets': peak,
        'peak_note': peak_note,
        'total_assets': round(total_assets, 2),
        'net_assets': round(net_assets, 2),
        'liabilities_in_cash': round(liabilities, 2),
        'net_outflow_total': round(outflow, 2),
        'dd_pct': round(status['dd_pct'], 1),
        'dd_level': status['level'],
        'safe_cushion': round(status['cushion'], 2),
        'lines': status['lines'],
        'triggered_line': triggered_line,
        'action': status['action'],
    }


def derive_take_profit_profile(name, layer):
    """Return a visible take-profit profile for each holding."""
    name = str(name)
    if layer == 'cash':
        return '冻结72h后可用'
    if layer == 'bedrock':
        if '红利' in name or '高股息' in name or '股息' in name:
            return '+30%卖1/3'
        if '黄金' in name:
            return '定投中 / 永不卖'
        return '永不卖'
    if layer == 'core':
        if '纳指' in name or '纳斯达克' in name or 'QDII' in name or '全球高端制造' in name:
            return '定投持有 / 估值阈值'
        return '持有'
    if '创新药' in name:
        # 09-01 同步：止盈档位按 8/31 归因裁决③ 落地 v3.6（+10/+20/+35，手册 2.3 已拍板）；此前 +8/+15/+25 为 v3.4 档
        return '-8%止损 / +10%+20%+35% / 30天'
    if '证券' in name:
        return '-8%止损 / PB1.35·1.6'
    if '半导体' in name or '芯片' in name:
        return 'DDX连2日为正才加仓'
    if '黄金' in name:
        return '定投中'
    return '-8%止损 / 阶梯止盈'


def derive_holding_tag(name, layer, data=None, mkt=None, existing_tag=''):
    """Return a current-state tag; holdings and labels can change with market data."""
    data = data or {}
    name = str(name)
    mkt_note = str((mkt or data.get('market', {}) or {}).get('note', ''))
    text = ' '.join([
        mkt_note,
        str(data.get('pending_actions', '')),
        str(data.get('watchlist', '')),
        str(data.get('dca_running', '')),
    ])
    tc = TAG_CLASS_BY_LAYER.get(layer, 'tag-a')

    if layer == 'cash':
        return existing_tag or '现金预备', tc
    if layer == 'bedrock':
        if '黄金' in name:
            return '定投中' if '黄金' in str(data.get('dca_running', '')) else '永不卖', 'tag-a'
        return existing_tag or derive_take_profit_profile(name, layer), tc
    if layer == 'core':
        if '纳指' in name or '纳斯达克' in name or 'QDII' in name or '全球高端制造' in name:
            if '溢价' in text:
                return '溢价冻结', 'tag-r'
            if any(('纳指' in str(x) or '纳斯达克' in str(x) or 'QDII' in str(x) or '全球高端制造' in str(x)) for x in data.get('dca_running', [])):
                return '定投中', 'tag-g'
            return '估值观察', 'tag-a'
        return existing_tag or derive_take_profit_profile(name, layer), tc
    if layer == 'sat':
        if '创新药' in name:
            remaining = time_stop_remaining(data)
            return f'{remaining}天倒计时', 'tag-a' if remaining > 5 else 'tag-r'
        if '半导体' in name or '芯片' in name:
            if 'DDX转负' in text or 'DDX为负' in text:
                return 'DDX暂停', 'tag-r'
            if 'DDX' in text and ('为正' in text or '转正' in text):
                return 'DDX观察', 'tag-a'
            return 'DDX待确认', 'tag-a'
        if '证券' in name:
            if 'PB' in text:
                return 'PB观察', 'tag-a'
            return '估值观察', 'tag-a'
        return existing_tag or '动态观察', tc
    return existing_tag or '', tc


def derive_portfolio_state(total, cash_mv, dd_pct, mkt_note, ops_count, max_ops, violation_count=0):
    """Derive a conservative portfolio state and freeze flags."""
    cash_ratio = cash_mv / total if total else 0
    note = str(mkt_note or '')
    freeze_reasons = []

    if dd_pct <= -15:
        freeze_reasons.append('-15%回撤')
    elif dd_pct <= -10:
        freeze_reasons.append('-10%回撤')
    if cash_ratio < DEFAULT_CASH_FLOOR:
        freeze_reasons.append(f'现金{cash_ratio*100:.1f}%<10%')
    if ops_count >= max_ops:
        freeze_reasons.append(f'月操作{ops_count}/{max_ops}已满')
    if 'DDX转负' in note:
        freeze_reasons.append('DDX转负')
    if '溢价' in note and ('10-12%' in note or '高溢价' in note):
        freeze_reasons.append('纳指高溢价')
    if violation_count > 0 and (dd_pct <= -10 or cash_ratio < DEFAULT_CASH_FLOOR):
        freeze_reasons.append(f'{violation_count}次违规')

    if dd_pct <= -15 or cash_ratio < DEFAULT_CASH_FLOOR:
        state = '防守'
    elif dd_pct <= -10 or 'DDX转负' in note or ops_count >= max_ops:
        state = '观望'
    elif 'DDX连' in note and ('为正' in note or '转正' in note) and '转负' not in note:
        state = '进攻'
    else:
        state = '常规'

    return {
        'state': state,
        'cash_ratio': cash_ratio,
        'freeze_new_buy': bool(freeze_reasons),
        'freeze_reasons': freeze_reasons,
        'allow_existing_exits': True,
    }


def compute_risk_state(rules, risks, drawdown_state, ops_state, mkt=None):
    """Normalize current risk status from existing outputs."""
    level = 'green'
    reasons = []
    rule_text = ' '.join(str(r.get('t', '')) for r in rules)
    risk_text = ' '.join(str(r.get('n', '')) + ' ' + str(r.get('d', '')) for r in risks)
    mkt_note = str((mkt or {}).get('note', ''))

    if drawdown_state.get('dd_level') == 'red' or ops_state.get('is_over_limit'):
        level = 'red'
    elif drawdown_state.get('dd_level') == 'amber' or ops_state.get('is_at_limit') or any(r.get('lv') == 'rr' for r in rules):
        level = 'amber'

    if 'DDX转负' in rule_text or 'DDX转负' in risk_text or 'DDX转负' in mkt_note:
        reasons.append('DDX转负')
    if drawdown_state.get('dd_level') == 'red':
        reasons.append(f"回撤{drawdown_state.get('dd_pct', 0):.1f}%")
    elif drawdown_state.get('dd_level') == 'amber':
        reasons.append(f"回撤{drawdown_state.get('dd_pct', 0):.1f}%")
    if ops_state.get('is_over_limit'):
        reasons.append(f"月操作{ops_state.get('count', 0)}/{ops_state.get('max', 0)}")
    if '纳指ETF高溢价' in risk_text:
        reasons.append('纳指高溢价')
    if any('时间止损' in s for s in [rule_text, risk_text]):
        reasons.append('时间止损关注')

    label = '安全'
    if level == 'red':
        label = '需要行动'
    elif level == 'amber':
        label = '关注即可'

    return {
        'level': level,
        'label': label,
        'red_count': sum(1 for r in rules if r.get('lv') == 'rr'),
        'amber_count': sum(1 for r in rules if r.get('lv') == 'ra'),
        'green_count': sum(1 for r in rules if r.get('lv') == 'rg'),
        'reasons': reasons,
    }


def compute_freeze_state(data, ops_state, risk_state, mkt=None, totals=None):
    """Return a non-trading freeze summary."""
    mkt_note = str((mkt or {}).get('note', ''))
    reasons = []
    if ops_state.get('is_at_limit'):
        reasons.append(f"月操作{ops_state.get('count', 0)}/{ops_state.get('max', 0)}已满")
    if risk_state.get('level') == 'red':
        reasons.append('风险红灯')
    if risk_state.get('level') == 'amber' and ops_state.get('is_at_limit'):
        reasons.append('风险+操作双重约束')
    if totals:
        total = totals.get('total', 0) or 0
        cash_ratio = (totals.get('cash_mv', 0) or 0) / total if total else 0
        if cash_ratio < DEFAULT_CASH_FLOOR:
            reasons.append(f'现金{cash_ratio*100:.1f}%<10%硬下限')
    if 'DDX转负' in mkt_note or 'DDX转负' in risk_state.get('reasons', []):
        reasons.append('DDX转负')
    if '纳指高溢价' in risk_state.get('reasons', []) or ('溢价' in mkt_note and ('10-12%' in mkt_note or '高溢价' in mkt_note)):
        reasons.append('纳指高溢价')
    if data.get('_meta', {}).get('peak_assets') in (None, '', 0):
        reasons.append('峰值基准缺失')

    frozen = bool(reasons)
    level = 'red' if risk_state.get('level') == 'red' else ('amber' if reasons else 'green')
    return {
        'frozen': frozen,
        'level': level,
        'reasons': reasons,
        'allow_existing_exits': True,
    }


def compute_clock_state(data, today=None):
    """Derive visible holding-age and cooldown clocks from transactions."""
    if today is None:
        today = data_reference_date(data)

    def parse_dt(raw):
        s = str(raw or '').strip()
        for fmt in ('%Y-%m-%d', '%m/%d %H:%M', '%m/%d'):
            try:
                dt = datetime.strptime(s[:10] if fmt == '%Y-%m-%d' else s, fmt).date()
                if fmt != '%Y-%m-%d':
                    dt = dt.replace(year=today.year)
                return dt
            except ValueError:
                continue
        return None

    def key(name):
        name = str(name)
        for kw in ('创新药', '半导体', '芯片', '证券', '纳指', '纳斯达克', 'QDII', '黄金', '红利', '高端制造'):
            if kw in name:
                return kw
        return name[:8]

    buys = {}
    sells = {}
    for t in data.get('transactions', []):
        dt = parse_dt(t.get('date'))
        if not dt:
            continue
        k = key(t.get('name', ''))
        op = str(t.get('op', ''))
        if any(x in op for x in ('买入', '加仓', '定投')):
            buys.setdefault(k, []).append(dt)
        if any(x in op for x in ('卖出', '减仓', '清仓', '止盈')):
            sells.setdefault(k, []).append(dt)

    holding_clocks = []
    for h in data.get('holdings_summary', []):
        if (h.get('mv', 0) or 0) <= 0 or h.get('group') != '进攻组合':
            continue
        k = key(h.get('name', ''))
        dates = sorted(buys.get(k, []))
        entry = dates[0] if dates else None
        last_buy = dates[-1] if dates else None
        holding_clocks.append({
            'name': h.get('name', ''),
            'entry_date': entry.isoformat() if entry else '',
            'last_buy_date': last_buy.isoformat() if last_buy else '',
            'holding_days': (today - entry).days if entry else None,
            'time_stop_days_left': max(30 - (today - entry).days, 0) if entry else None,
        })

    cooldowns = []
    for k, dates in sells.items():
        last = max(dates)
        until = last + timedelta(days=3)
        remaining = max((until - today).days, 0)
        cooldowns.append({
            'name_key': k,
            'last_sell_at': last.isoformat(),
            'cooldown_until': until.isoformat(),
            'cooldown_days_left': remaining,
            'active': remaining > 0,
        })

    return {'holdings': holding_clocks, 'cooldowns': cooldowns}


def compute_factor_clusters(data, totals):
    """Conservative factor proxy map for monthly concentration warnings."""
    active = [h for h in data.get('holdings_summary', []) if (h.get('mv', 0) or 0) > 0]
    stock_items = data.get('stock_holdings', [])
    clusters = {
        'growth_beta': ['纳指', '纳斯达克', '半导体', '芯片', '创新药', '证券'],
        'defensive_income': ['债券', '红利', '现金'],
        'gold': ['黄金'],
    }
    out = {}
    total = totals.get('total', 0) or 0
    for name, kws in clusters.items():
        mv = sum(h.get('mv', 0) or 0 for h in active if any(kw in str(h.get('name', '')) for kw in kws))
        for s in stock_items:
            s_name = str(s.get('name') or s.get('code') or '')
            s_mv = (s.get('mv') if s.get('mv') is not None else (s.get('shares', 0) or 0) * (s.get('price', 0) or 0)) or 0
            if any(kw in s_name for kw in kws):
                mv += s_mv
        out[name] = {'mv': round(mv, 2), 'pct': round(mv / total * 100, 1) if total else 0}
    out['thresholds'] = {'growth_beta_warn_pct': 40, 'growth_beta_block_pct': 50}
    return out


def compute_opportunity_scores(data, ops_state, risk_state, freeze_state, totals):
    """Return advisory opportunity scores without changing trading semantics."""
    out = []
    for item in data.get('watchlist', []):
        sector = str(item.get('sector', ''))
        trigger = str(item.get('trigger', ''))
        status = str(item.get('status', ''))
        reasons = []
        score = 20
        if '回调' in trigger or '低位' in trigger:
            score += 20
            reasons.append('回调观察位')
        if '🟢' in status:
            score += 10
        if freeze_state.get('frozen'):
            reasons.append('冻结中')
            score -= 15
        grade = '观察'
        if score >= 60:
            grade = '扩仓候选'
        elif score >= 45:
            grade = '加仓候选'
        elif score >= 30:
            grade = '试探'
        out.append({
            'name': sector,
            'score': score,
            'grade': grade,
            'blocked_by': freeze_state.get('reasons', []),
            'reasons': reasons,
        })
    for item in data.get('pending_actions', []):
        name = str(item.get('name', ''))
        reasons = []
        score = 25
        if 'DDX' in name or 'PB' in name or '溢价' in name or '时间止损' in name:
            score += 15
            reasons.append('规则驱动')
        if freeze_state.get('frozen'):
            score -= 10
            reasons.append('冻结中')
        grade = '观察'
        if score >= 60:
            grade = '扩仓候选'
        elif score >= 45:
            grade = '加仓候选'
        elif score >= 30:
            grade = '试探'
        out.append({
            'name': name,
            'score': score,
            'grade': grade,
            'blocked_by': freeze_state.get('reasons', []),
            'reasons': reasons,
        })
    return out


def pending_action_priority(item):
    """Return a unified pending-action label for UI and summary blocks."""
    return str(item.get('priority') or item.get('p') or item.get('name') or item.get('action') or '')


def normalize_pending_actions(items):
    """Normalize pending_actions into the compact UI contract used by the dashboard.
    8/17 审计：非 dict 条目（字符串等脏数据）直接跳过，防止 rebuild 崩溃。"""
    normalized = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        normalized.append({
            'p': pending_action_priority(item),
            't': str(item.get('name') or item.get('t') or item.get('action') or ''),
            'd': str(item.get('action') or item.get('d') or ''),
            'u': str(item.get('updated') or item.get('u') or ''),
            'name': str(item.get('name') or item.get('t') or item.get('action') or ''),
            'action': str(item.get('action') or item.get('d') or ''),
            'priority': str(item.get('priority') or item.get('p') or ''),
            'updated': str(item.get('updated') or item.get('u') or ''),
        })
    return normalized


def current_ops_period(data, today=None):
    """Return the current operation period as (year, month, label)."""
    meta = data.get('_meta', {})
    year = meta.get('ops_year')
    month = meta.get('ops_month')
    if year is not None and month is not None:
        try:
            year = int(year)
            month = int(month)
            if 1 <= month <= 12 and 2000 <= year <= 2100:  # 8/17 审计：月份/年份合法性校验
                return year, month, f'{month}月'
        except (ValueError, TypeError):
            pass

    update_date = data.get('update_date') or data.get('update_time')
    if update_date:
        try:
            dt = datetime.strptime(str(update_date)[:10], '%Y-%m-%d').date()
            return dt.year, dt.month, f'{dt.month}月'
        except ValueError:
            pass

    if today is None:
        today = date.today()
    return today.year, today.month, f'{today.month}月'


def compute_ops_state(data, today=None):
    """Return normalized monthly operation state.

    v4.5.1（09-18）：改为**二维**（手册 §1.3 v3.11 口径）——
    `count`/`max`/`remaining` **保留旧语义（总数）**以兼容既有渲染，
    新增 `buys`/`sells` 与两维判定。⚠️ 判定一律读 `is_over_limit`（任一维超限即超限），
    **不得再用 `count >= max` 作唯一判据** —— 一维判据存在**假阴性路径**
    （买入 3 笔 + 卖出 0 笔时 3 < 4 会放行，而买入维已超 2）。"""
    year, month, label = current_ops_period(data, today=today)
    s = monthly_ops_summary(data, year=year, month=month)
    max_total = s.max_total if s.max_total > 0 else DEFAULT_MONTHLY_OPS
    remaining = max(max_total - s.total, 0)
    return {
        'year': year,
        'month': month,
        'label': label,
        # ---- 旧字段（总数口径，兼容既有渲染）----
        'count': s.total,
        'max': max_total,
        'remaining': remaining,
        'is_at_limit': s.total >= max_total,
        'is_over_limit': s.is_over_limit,
        # ---- v4.5.1 新增：买卖两维 ----
        'buys': s.buys,
        'sells': s.sells,
        'max_buys': s.max_buys,
        'max_sells': s.max_sells,
        'is_buy_over': s.is_buy_over,
        'is_sell_over': s.is_sell_over,
        'buy_remaining': max(s.max_buys - s.buys, 0),
        'sell_remaining': max(s.max_sells - s.sells, 0),
        'violations': s.violations,
        'unknown_ops': list(s.unknown_ops),
        'has_unknown': s.has_unknown,
        'suspect_dupes': list(s.suspect_dupes),
        'has_suspect_dupes': s.has_suspect_dupes,
    }


# ══════════════════════════════════════════════════════════════════════════
# 月操作额度 · 口径（手册 §1.3 v3.11「月操作额度·口径定义」· 2026-09-18 立）
# ══════════════════════════════════════════════════════════════════════════
# 🔴 v4.5.1 立此闭集，修三个缺陷（此前实现在同一 KPI 上同时犯三个）：
#   ① **维度丢失** —— 手册正文写「正常月≤4笔（买入≤2+卖出≤2）」，速查表压缩成「正常≤4」，
#      而门禁绑的是 `max_monthly_ops = 4` 一维 ⇒ **绑到了转述表，丢了决定性括号**。
#      后果是**假阴性**：买入 3 笔 + 卖出 0 笔时，一维口径报「3/4 可执行 1 笔」✅ 放行，
#      而正文口径应为「买入已超 2」⛔ 拦截。与 v4.4.13（转述表压缩丢限定词）**同型**。
#   ② **记录 ≠ 事件** —— `赎回`(T日提交) 与 `赎回确认`(T+1确认) 是**同一事件的两条腿**，
#      旧实现按 `op` 黑名单逐条计数 ⇒ 单事件计 2 次（9 月实测虚增为 10，真实事件 8）。
#      与 v4.4.16（`pnl_pct` 混装 5 种语义）**同族**：聚合函数按「记录」算，
#      而 KPI 的语义是「事件」。
#   ③ **分类靠子串巧合** —— `余额宝转出`/`转换转入` 此前**被排除**，并非因其被列出，
#      而是因 `'转出'`/`'转入'` 恰是它们的子串 ⇒ **碰巧对，不是定义对**。
#      新增 op 类型（如 `转换转出`）随时会静默破功。
# ⇒ 故：**黑名单翻转为闭集白名单 ＋ 未知 op fail-loud**（而不是「再往黑名单加一个词」——
#    那只能修到下一个 op 类型出现为止）。
MONTHLY_OPS_BUY_MARKERS = ('买入', '加仓', '建仓', '补仓')
MONTHLY_OPS_SELL_MARKERS = ('卖出', '赎回', '清仓', '减仓')
# 记账腿：**资金／份额的记账动作**，非**决策动作**，一律不计入月额度。
# 🔴 `赎回` 计入、`赎回确认`／`赎回到账` 不计入 —— 三者是同一事件的三条腿，只计提交那一条。
MONTHLY_OPS_LEDGER_LEGS = (
    '定投', '赎回到账', '赎回确认',
    '转入', '转出', '入金', '出金',
    '转换转入', '转换转出', '余额宝转入', '余额宝转出',
)


def classify_txn_op(op):
    """把一个交易记录归到 'buy' / 'sell' / 'leg' / 'unknown'。

    🔴 未识别的 op 返回 **'unknown'** —— 调用方**必须显式处置**（声张），
    不得静默计入、也不得静默排除。口径见手册 §1.3 第 ④ 条。"""
    op = str(op or '').strip()
    if not op:
        return 'unknown'
    # 🔴 记账腿**必须先判** —— `赎回确认` 含子串 `赎回`，若先判 sell 会被误归。
    if any(k in op for k in MONTHLY_OPS_LEDGER_LEGS):
        return 'leg'
    if any(op.startswith(k) for k in MONTHLY_OPS_BUY_MARKERS):
        return 'buy'
    if any(op.startswith(k) for k in MONTHLY_OPS_SELL_MARKERS):
        return 'sell'
    return 'unknown'


def is_superseded_txn(t):
    """交易记录是否已被取代（v4.5.1 新增）。

    与**决策日志的取代机制**（v4.4.2 `superseded`）对齐 —— 交易记录此前**没有**取代机制，
    于是「盘中记错、收盘订正」只能靠**再记一条**，导致同一事件被计两次
    （9/1「贷款第1笔」实录两条：盘中记证券、收盘确认记鹏华）。

    支持两种写法：`superseded: true` 或 `superseded_by: "<取代者说明>"`。"""
    if t.get('superseded') is True:
        return True
    return bool(t.get('superseded_by'))


def txn_exclusion_reason(t):
    """该记录**不计入月额度**的原因；`None` = 计入。

    把「为什么不算」显式化，而不是靠布尔黑箱 —— 便于报文里逐条说明、
    也便于测试直接断言**是哪一条口径**在起作用（而非只断言一个布尔）。

    判定顺序（**先显式声明，再分类**）：
      1. `superseded` / `superseded_by` 字段      → 'superseded'（已被取代）
      2. op ∩ 记账腿闭集                           → 'ledger_leg'（记账腿）
      3. note 含「自动扣款」/「非手动」            → 'note_declared_non_manual'
         ⚠️ 这不是启发式 —— 是**人工写下的显式声明**（如「智能定投自动扣款（非手动操作，
         不计入月限额）」），按「显式声明优先于推断」保留（v4.5.1 修复中曾一度漏掉，被
         `test_pre_trade_check.TestMonthlyOpsReuse` 当场抓出回归）。
      4. 其余                                      → None（计入）
    """
    if is_superseded_txn(t):
        return 'superseded'
    if classify_txn_op(t.get('op')) == 'leg':
        return 'ledger_leg'
    note = str(t.get('note', ''))
    if '自动扣款' in note or '非手动' in note:
        return 'note_declared_non_manual'
    return None


def is_manual_operation(t):
    """【向后兼容保留】是否计入月操作限额。

    🔴 v4.5.1 起**不再作为口径权威** —— 旧实现是「排除词黑名单」，会把 `赎回确认`
    这类**同一事件的记账腿**计入，且对未知 op 静默按「计入」处理。
    新代码请用 `classify_txn_op()` ＋ `monthly_ops_summary()`（二维口径）。
    本函数保留仅为兼容既有调用点，语义等价于「`txn_exclusion_reason` 为 None」。"""
    return txn_exclusion_reason(t) is None


def _txn_date_in_month(d, year, month):
    """交易日期是否属于目标月份（8/17 审计加固）：
    支持 '2026-08-07' / '2026/8/7' / '8/7' / '8/7 14:49'，且必须是日期开头的严格匹配，
    防止 '8/31归因' 这类文本被 startswith('8/') 误计。"""
    d = str(d or '').strip()
    m = re.match(r'^(\d{4})[\-/](\d{1,2})[\-/](\d{1,2})', d)
    if m:
        return int(m.group(1)) == year and int(m.group(2)) == month
    m = re.match(r'^(\d{1,2})/(\d{1,2})', d)
    if m:
        return int(m.group(1)) == month
    return False


class MonthlyOpsSummary:
    """月操作额度汇总（手册 §1.3 v3.11 **二维口径**）。

    向后兼容：仍可 2 元组解包 `(total, violations)`、可 `[0]` 下标 ——
    既有调用点（gen_excel_skill / gen_monthly_attribution / gen_weekly_report）
    无需改动即得正确总数；需要二维判定处请读 `.buys` / `.sells` /
    `.is_buy_over` / `.is_sell_over`。"""

    __slots__ = ('year', 'month', 'buys', 'sells', 'violations', 'unknown_ops',
                 'superseded_records', 'suspect_dupes', 'max_buys', 'max_sells', 'max_total',
                 'buy_items', 'sell_items')

    def __init__(self, year, month, buys, sells, violations=0,
                 unknown_ops=(), superseded_records=0, suspect_dupes=(),
                 max_buys=2, max_sells=2, max_total=4, buy_items=(), sell_items=()):
        self.year = year
        self.month = month
        self.buys = buys
        self.sells = sells
        self.violations = violations
        self.unknown_ops = tuple(unknown_ops)
        self.superseded_records = superseded_records
        self.suspect_dupes = tuple(suspect_dupes)
        self.max_buys = max_buys
        self.max_sells = max_sells
        self.max_total = max_total
        # 🔴 v4.5.34（单 152）：**计入额度的逐笔名单**（原始记录 dict，文件序）。
        #    与 `buys`/`sells` 出自**同一循环** ⇒ **零新口径**；供月度归因的逐笔披露
        #    与「第 N 笔起超限」序号标注（⛔ 调用方不得据此自造计数）。
        self.buy_items = tuple(buy_items)
        self.sell_items = tuple(sell_items)

    @property
    def total(self):
        return self.buys + self.sells

    @property
    def is_buy_over(self):
        return self.buys > self.max_buys

    @property
    def is_sell_over(self):
        return self.sells > self.max_sells

    @property
    def is_total_over(self):
        return self.total > self.max_total

    @property
    def is_over_limit(self):
        """任一维度超限即为超限（买卖两维独立，不可互相占用额度）。"""
        return self.is_buy_over or self.is_sell_over or self.is_total_over

    @property
    def has_unknown(self):
        """存在闭集之外的 op ⇒ 额度结论**不可信**，调用方必须声张。"""
        return bool(self.unknown_ops)

    @property
    def has_suspect_dupes(self):
        """存在疑似同一事件的双记记录 ⇒ 额度**可能虚高**，须人工确认。"""
        return bool(self.suspect_dupes)

    # ---- 向后兼容（旧签名 `(count, violation_count)`）----
    def __iter__(self):
        return iter((self.total, self.violations))

    def __len__(self):
        return 2

    def __getitem__(self, i):
        return (self.total, self.violations)[i]

    def __repr__(self):
        return (f"MonthlyOpsSummary({self.year}-{self.month:02d}: "
                f"买入 {self.buys}/{self.max_buys} · 卖出 {self.sells}/{self.max_sells} · "
                f"合计 {self.total}/{self.max_total}"
                + (f" · ⚠️未知op={list(self.unknown_ops)}" if self.unknown_ops else "")
                + (f" · 已取代 {self.superseded_records}" if self.superseded_records else "")
                + (f" · ⚠️疑似双记 {len(self.suspect_dupes)} 组" if self.suspect_dupes else "")
                + ")")


def monthly_ops_summary(data, year=None, month=None):
    """月操作额度统计（**单一真源** · 手册 §1.3 v3.11 二维口径）。

    Returns: `MonthlyOpsSummary` —— 向后兼容 2 元组解包，另暴露 `.buys` / `.sells`。

    🔴 三条口径（详见文件内 MONTHLY_OPS_* 常量处的说明）：
      ① 计「事件」不计「记录」（记账腿不计入；`superseded` 记录不计入）
      ② 买卖**两维独立**判定（`买入≤2` 与 `卖出≤2` 各自成立，非「总数≤4」一维）
      ③ 未知 op **fail-loud** —— 收进 `.unknown_ops` 并置 `has_unknown`，
         **不静默计入、也不静默排除**

    Handles '2026-08-07' / '2026/8/7' / '8/7' formats（严格日期开头匹配）。"""
    if year is None or month is None:
        year, month, _ = current_ops_period(data)
    txns = data.get('transactions', [])
    month_txns = [t for t in txns if _txn_date_in_month(t.get('date'), year, month)]

    meta = data.get('_meta', {}) or {}
    max_buys = int(safe_float(meta.get('monthly_buys_max'), DEFAULT_MONTHLY_BUYS) or DEFAULT_MONTHLY_BUYS)
    max_sells = int(safe_float(meta.get('monthly_sells_max'), DEFAULT_MONTHLY_SELLS) or DEFAULT_MONTHLY_SELLS)
    max_total = int(safe_float(meta.get('max_monthly_ops'), DEFAULT_MONTHLY_OPS) or DEFAULT_MONTHLY_OPS)

    buys = sells = violations = superseded = 0
    unknown = []
    counted = []
    for t in month_txns:
        reason = txn_exclusion_reason(t)
        if reason == 'superseded':
            superseded += 1
            continue
        if reason is not None:
            # 'ledger_leg' / 'note_declared_non_manual' —— 记账腿与显式声明，均不计入
            continue
        kind = classify_txn_op(t.get('op'))
        if kind == 'unknown':
            # 🔴 fail-loud：收进名单，**不并入买卖任一维** —— 见口径 ③
            unknown.append(str(t.get('op', '')).strip() or '<空 op>')
            continue
        counted.append((t, kind))
        if kind == 'buy':
            buys += 1
        else:
            sells += 1
        if '违规' in str(t.get('note', '')):
            violations += 1

    # 🔴 疑似双记检测（**只声张，不自动折叠**）—— 口径 ① 要求「计事件不计记录」，
    #    但「两条记录 = 一个事件」只能由人判定。系统此前对该情形**零感知**：
    #    9/1「贷款第1笔」实录两条（盘中记证券 / 收盘确认记鹏华），静静被计成 2 笔买入。
    #    故此处**报出**同键多条记录供人工确认，**不替用户判定谁对**。
    #
    # 🔴 v4.5.2 修正分组键：**必须含 `fund`**。
    #    原键为 (日期, op, 金额) —— **不含基金** ⇒ 会把「同日同额但**不同基金**的两笔
    #    正常买入」（如 9/1 证券 ¥2000 ＋ 鹏华 ¥2000）**长期误报**为疑似双记。
    #    误报的代价不是噪声而已：**天天响的告警会被学会忽略**，那时真正的双记
    #    （同基金同额同日 ×2）也就一起被无视了 —— 与 v2.1「一条永远做不到的强制项
    #    会训练出『照抄免责』的习惯」同族。
    #    ⚠️ 真阳性**不受影响**：9/1 那组两条都是「易方达证券ETF联接C ¥2000」，
    #      键相同 ⇒ 仍会被抓出（见 test_monthly_ops 的反向断言）。
    _groups = {}
    for t, _kind in counted:
        k = (str(t.get('date', '')), str(t.get('op', '')),
             str(t.get('fund') or t.get('name') or ''), str(t.get('amount', '')))
        _groups.setdefault(k, []).append(t)
    suspect = [
        {'date': k[0], 'op': k[1], 'fund': k[2], 'amount': k[3],
         'funds': sorted({str(x.get('fund') or x.get('name') or '') for x in v}),
         'count': len(v)}
        for k, v in _groups.items() if len(v) > 1
    ]
    suspect.sort(key=lambda x: (x['date'], x['op']))

    return MonthlyOpsSummary(
        year=year, month=month, buys=buys, sells=sells, violations=violations,
        unknown_ops=sorted(set(unknown)), superseded_records=superseded,
        suspect_dupes=suspect,
        max_buys=max_buys, max_sells=max_sells, max_total=max_total,
        buy_items=[t for t, k in counted if k == 'buy'],
        sell_items=[t for t, k in counted if k == 'sell'],
    )


# group 字段 → 层级（来自 portfolio_data.json，新基金自动归类）
GROUP_TO_LAYER = {
    "全局固收": "bedrock",
    "核心增长": "core",
    "全局QDII": "core",
    "进攻组合": "sat",
    "现金预备": "cash",
}
# 兜底：未知 group 时按关键词判断
KEYWORD_TO_LAYER = [
    ("债券", "bedrock"), ("黄金", "bedrock"), ("红利ETF", "bedrock"), ("红利", "bedrock"),  # 8/17：长词优先
    ("QDII", "core"), ("混合", "core"), ("纳指", "core"), ("纳斯达克", "core"),
    ("半导体", "sat"), ("创新药", "sat"), ("证券", "sat"), ("芯片", "sat"),
    ("现金", "cash"), ("货币", "cash"),
]


def normalize_layer(layer):
    layer = str(layer or '').strip()
    return layer if layer in LAYER_ORDER else ''


def resolve_layer(name, group, item=None):
    """Determine layer from explicit data → ANCHOR_MAP → group → keyword fallback.
    Returns (layer, tag, tc) or None if unresolvable."""
    item = item or {}
    explicit_layer = normalize_layer(item.get('layer') or item.get('anchor_layer'))
    if explicit_layer:
        return (explicit_layer, item.get('tag', ''), item.get('tc') or TAG_CLASS_BY_LAYER[explicit_layer])
    if name in ANCHOR_MAP:
        return ANCHOR_MAP[name]
    if group and group in GROUP_TO_LAYER:
        layer = GROUP_TO_LAYER[group]
        return (layer, item.get('tag', ''), item.get('tc') or TAG_CLASS_BY_LAYER[layer])
    for kw, layer in KEYWORD_TO_LAYER:
        if kw in str(name):
            return (layer, item.get('tag', ''), item.get('tc') or TAG_CLASS_BY_LAYER[layer])
    return None


def process_holdings(raw_holdings, stocks, data=None, mkt=None):
    """Process holdings into four-layer structure.
    P1-1: 智能分类 — 优先 group 字段(JSON)，ANCHOR_MAP 精确覆盖，关键词兜底。"""
    data = data or {}
    bedrock, core, sat, cash = [], [], [], []
    dropped = []

    for h in raw_holdings:
        name = h.get('name', '')
        mv = h.get('mv', 0) or 0
        if mv <= 0:
            continue
        group = h.get('group', '')
        layer_info = resolve_layer(name, group, h)
        if not layer_info:
            dropped.append(name)
            continue
        layer, existing_tag, tc = layer_info
        pnl = safe_float(h.get('pnl', 0))
        dp = safe_float(h.get('day_pnl', 0))
        tag, resolved_tc = derive_holding_tag(name, layer, data=data, mkt=mkt, existing_tag=existing_tag)
        item = {
            "n": name, "mv": round(mv, 2), "pnl": round(pnl, 2),
            "dp": round(dp, 2), "rt": round(rate(pnl, mv), 2),
            "tag": tag, "tc": resolved_tc or tc,
            "profile": derive_take_profit_profile(name, layer),
            "type": "cash" if layer == "cash" else "fund",
            "layer": layer,
            "src": "map" if name in ANCHOR_MAP else ("explicit" if h.get('layer') or h.get('anchor_layer') else ("group" if group else "kw"))
        }
        if layer == 'bedrock':
            bedrock.append(item)
        elif layer == 'core':
            core.append(item)
        elif layer == 'sat':
            sat.append(item)
        elif layer == 'cash':
            cash.append(item)

    # Add stock holdings dynamically by their own layer or group
    for s in stocks:
        price = s.get('price', 0)
        shares = s.get('shares', 0)
        mv = s.get('mv') if s.get('mv') is not None else shares * price
        if mv <= 0:
            continue
        pnl = safe_float(s.get('pnl', 0))
        dp = safe_float(s.get('day_pnl', 0))
        name = s.get('name') or s.get('code') or '未命名股票'
        layer_info = resolve_layer(name, s.get('group', ''), s)
        if not layer_info:
            # 8/17 审计（M6）：与基金口径一致——无法归类则告警跳过，不静默塞入压舱石扭曲占比
            dropped.append(name)
            continue
        layer, existing_tag, tc = layer_info
        tag, resolved_tc = derive_holding_tag(name, layer, data=data, mkt=mkt, existing_tag=existing_tag)
        item = {
            "n": name, "mv": round(mv, 2),
            "pnl": round(pnl, 2), "dp": round(dp, 2), "rt": round(rate(pnl, mv), 2),
            "tag": tag or derive_take_profit_profile(name, layer),
            "tc": resolved_tc or TAG_CLASS_BY_LAYER.get(layer, 'tag-b'),
            "st": 1,
            "profile": derive_take_profit_profile(name, layer),
            "type": "stock",
            "layer": layer,
            "src": "stock"
        }
        if layer == 'bedrock':
            bedrock.append(item)
        elif layer == 'core':
            core.append(item)
        elif layer == 'sat':
            sat.append(item)
        elif layer == 'cash':
            cash.append(item)
        else:
            bedrock.append(item)

    return bedrock, core, sat, cash, dropped


def compute_totals(bedrock, core, sat, cash):
    """Compute layer totals and overall totals."""
    bedrock_mv = sum(i['mv'] for i in bedrock)
    core_mv = sum(i['mv'] for i in core)
    sat_mv = sum(i['mv'] for i in sat)
    cash_mv = sum(i['mv'] for i in cash)
    all_items = bedrock + core + sat + cash
    stock_mv = sum(i['mv'] for i in all_items if i.get('st') or i.get('type') == 'stock')
    fund_mv_total = sum(i['mv'] for i in all_items if i.get('type', 'fund') == 'fund')
    total = bedrock_mv + core_mv + sat_mv + cash_mv
    total_pnl = sum(i['pnl'] for i in bedrock + core + sat + cash)
    return {
        "bedrock_mv": bedrock_mv, "core_mv": core_mv, "sat_mv": sat_mv,
        "cash_mv": cash_mv, "fund_mv_total": fund_mv_total,
        "total": total, "stock_mv": stock_mv, "total_pnl": total_pnl,
    }


def compute_holding_counts(bedrock, core, sat, cash):
    """Compute dynamic holding counts across layers and instrument types."""
    layers = {'bedrock': bedrock, 'core': core, 'sat': sat, 'cash': cash}
    by_layer = {layer: 0 for layer in layers}
    counts = {'active': 0, 'fund': 0, 'stock': 0, 'cash': 0, 'non_cash': 0, 'total': 0}
    for layer, items in layers.items():
        for item in items:
            mv = safe_float(item.get('mv', 0), 0)
            if mv <= 0:
                continue
            by_layer[layer] += 1
            counts['active'] += 1
            counts['total'] += 1
            if layer == 'cash' or item.get('type') == 'cash':
                counts['cash'] += 1
            elif item.get('st') or item.get('type') == 'stock':
                counts['stock'] += 1
            else:
                counts['fund'] += 1
    counts['non_cash'] = counts['active'] - counts['cash']
    for layer in ('bedrock', 'core', 'sat'):
        counts[layer] = by_layer[layer]
    by_type = {'fund': counts['fund'], 'stock': counts['stock'], 'cash': counts['cash']}
    parts = []
    if counts['fund']:
        parts.append(f"{counts['fund']}只基金")
    if counts['stock']:
        parts.append(f"{counts['stock']}只股票")
    if counts['cash']:
        parts.append(f"{counts['cash']}项现金")
    counts['layers'] = by_layer
    counts['by_layer'] = by_layer
    counts['by_type'] = by_type
    counts['active_label'] = ' + '.join(parts) if parts else '暂无持仓'
    return counts


def build_layer_rows(totals, holding_counts=None):
    """Build render-ready layer rows from current totals and dynamic counts."""
    total = totals.get('total', 0) or 0
    mv_by_layer = {
        'bedrock': totals.get('bedrock_mv', 0),
        'core': totals.get('core_mv', 0),
        'sat': totals.get('sat_mv', 0),
        'cash': totals.get('cash_mv', 0),
    }
    holding_counts = holding_counts or {}
    by_layer = holding_counts.get('by_layer', holding_counts.get('layers', {}))
    rows = []
    for layer in LAYER_ORDER:
        meta = LAYER_META[layer]
        mv = mv_by_layer.get(layer, 0) or 0
        rows.append({
            'key': layer,
            'k': meta['k'],
            'icon': meta['icon'],
            'label': meta['label'],
            'cls': meta['cls'],
            'target': meta['target'],
            'mv': round(mv, 2),
            'pct': round(mv / total * 100, 1) if total else 0,
            'count': by_layer.get(layer, 0),
        })
    return rows


def generate_rules(sat_holdings, data, mkt, totals, drawdown_state=None, ops_state=None):
    """Generate rule checks from data (NOT hardcoded)."""
    rules = []
    mkt_note = mkt.get('note', '')
    txns = data.get('transactions', [])
    pa = data.get('pending_actions', [])

    # Count monthly operations (unified helper)
    if ops_state is None:
        ops_state = compute_ops_state(data)

    # Stop-loss checks for satellite
    for item in sat_holdings:
        r = rate(item['pnl'], item['mv'])
        if r <= -8:
            rules.append({"lv": "rr", "t": f"{item['n'][:12]} 浮亏 {r:.1f}% 触发 -8% 止损线！"})

    # DDX rule
    if 'DDX' in mkt_note or '半导体' in mkt_note:
        ddx_negative = 'DDX转负' in mkt_note or 'DDX为负' in mkt_note or ('DDX连续' in mkt_note and '为负' in mkt_note)
        ddx_positive = 'DDX转正' in mkt_note or (('DDX连' in mkt_note or 'DDX连续' in mkt_note) and '为正' in mkt_note)
        if ddx_negative:
            rules.append({"lv": "rr", "t": "半导体 DDX 转负 → 补仓暂停，等待 DDX 连2日为正"})
        elif ddx_positive:
            snippet = mkt_note[mkt_note.find('DDX'):][:40] if 'DDX' in mkt_note else '详见行情'
            rules.append({"lv": "rg", "t": f"半导体 DDX 已确认转正（{snippet}）；仅恢复观察，不覆盖浮亏不加仓"})
        else:
            rules.append({"lv": "ra", "t": "半导体 DDX 状态待确认，关注下个交易日"})
    else:
        rules.append({"lv": "ra", "t": "半导体 DDX 数据待更新"})

    # 纳指溢价（从行情备注推导；无数据时显示待确认，不写死数值）
    if '溢价' in mkt_note:
        if '高溢价' in mkt_note or '10-12' in mkt_note:
            premium_lv, premium_t = "rr", "纳指ETF溢价率偏高 → 不建仓，等待溢价率 <= 3%"
        else:
            premium_lv, premium_t = "rg", "纳指ETF溢价率已回落 → 可评估建仓"
    else:
        premium_lv, premium_t = "ra", "纳指ETF溢价率待确认（≤3% 才建仓）"
    rules.append({"lv": premium_lv, "t": premium_t})

    # 创新药时间止损（截止日从数据解析，剩余天数钳制为 0）
    remaining = time_stop_remaining(data)
    rules.append({"lv": "ra", "t": f"创新药时间止损倒计时：按数据日剩{remaining}天（截止日见规则手册）"})

    # 回撤
    if drawdown_state is None:
        drawdown_state = compute_drawdown_state(data, totals)
    dd_pct = drawdown_state['dd_pct']
    safe_cushion = drawdown_state['safe_cushion']

    if dd_pct <= -15:
        rules.append({"lv": "rr", "t": f"总资产回撤 {dd_pct:.1f}% 触发 -15% 线！核心增长减 1/3"})
    elif dd_pct <= -10:
        rules.append({"lv": "rr", "t": f"总资产回撤 {dd_pct:.1f}% 触发 -10% 线！卫星全部清仓"})
    elif dd_pct <= -5:
        rules.append({"lv": "ra", "t": f"总资产回撤 {dd_pct:.1f}% 触发 -5% 线！卫星仓位减半"})
    else:
        _dd_basis = f"已扣贷款残留 ¥{drawdown_state['liabilities_in_cash']:,.0f}"
        if drawdown_state.get('net_outflow_total'):
            _dd_basis += f"·已补回净转出 ¥{drawdown_state['net_outflow_total']:,.0f}"
        rules.append({"lv": "rg", "t": f"自有净值距 -5% 回撤线 ¥{drawdown_state['lines']['minus5']:,.0f} 还有 ¥{safe_cushion:,.0f} 安全垫（{_dd_basis}）"})

    # 操作计数 (from unified helper)
    violations = ops_state.get('violations', 0)
    if violations:
        discipline = f'{violations}次违规！'
    elif ops_state.get('is_over_limit'):
        discipline = '超出额度 · 禁止新买入'
    elif ops_state.get('is_at_limit'):
        discipline = '额度已满 · 禁止新买入'
    else:
        discipline = '零违规 · 纪律满分'
    ops_lv = "rr" if ops_state.get('is_over_limit') or violations else ("ra" if ops_state.get('is_at_limit') else "rg")
    rules.append({
        "lv": ops_lv,
        "t": f"{ops_state['label']}操作 {ops_state['count']}/{ops_state['max']} 笔 · {discipline}"
    })

    return rules


def generate_risk_matrix(data, mkt_note, totals, ops_state=None):
    """Generate dynamic risk matrix from data."""
    risks = []
    raw = data.get('holdings_summary', [])
    if ops_state is None:
        ops_state = compute_ops_state(data)
    kc = data.get('market', {}).get('kc', {})

    # DDX
    if 'DDX转负' in mkt_note:
        risks.append({"l": "red", "n": "半导体DDX转负", "d": "主力净流出", "c": "r"})
    elif 'DDX' in mkt_note and ('为正' in mkt_note or '转正' in mkt_note):
        risks.append({"l": "green", "n": "半导体DDX为正", "d": "主力净流入确认", "c": "g"})
    else:
        risks.append({"l": "amber", "n": "半导体DDX待确认", "d": "关注下个交易日", "c": "a"})

    # 纳指溢价（从行情备注推导）
    if '溢价' in mkt_note:
        if '高溢价' in mkt_note or '10-12' in mkt_note:
            risks.append({"l": "red", "n": "纳指ETF高溢价", "d": "溢价率偏高，不建仓", "c": "r"})
        else:
            risks.append({"l": "green", "n": "纳指ETF溢价可控", "d": "可评估建仓", "c": "g"})
    else:
        risks.append({"l": "amber", "n": "纳指ETF溢价待确认", "d": "需行情备注更新", "c": "a"})

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
    remaining_days = time_stop_remaining(data)
    if remaining_days <= 5:
        risks.append({"l": "red", "n": "创新药时间紧迫", "d": f"按数据日仅剩{remaining_days}天", "c": "r"})
    else:
        risks.append({"l": "amber", "n": "创新药时间压力", "d": f"按数据日剩{remaining_days}天", "c": "a"})

    # 黄金
    gold_h = next((h for h in raw if '黄金' in str(h.get('name', '')) and h.get('mv', 0) > 0), None)
    if gold_h:
        gold_day_pct = safe_float(gold_h.get('day_pct', 0), 0)  # 8/17 审计：防字符串崩溃
        if gold_day_pct > 0.02:
            risks.append({"l": "amber", "n": "黄金短期过热", "d": f"单日+{gold_day_pct*100:.1f}%", "c": "a"})
        else:
            risks.append({"l": "green", "n": "黄金稳健", "d": f"日涨跌 {gold_day_pct*100:+.2f}%", "c": "g"})

    # 固收
    bond_items = [h for h in raw if '债券' in str(h.get('name', '')) and h.get('mv', 0) > 0]
    if bond_items and all(h.get('day_pnl', 0) >= -1 for h in bond_items):
        risks.append({"l": "green", "n": "固收稳定产出", "d": "债券正收益", "c": "g"})

    # 成交量（解析"万亿"数字与 3 万亿阈值比较；无数据时输出待确认）
    vol_match = None
    vol_str = '--'
    if '万亿' in mkt_note:
        m = re.search(r'(\d+(?:\.\d+)?)\s*万亿', mkt_note)
        if m:
            vol_match = float(m.group(1))
            vol_str = f"{vol_match:g}万亿"
    if vol_match is None:
        risks.append({"l": "amber", "n": "市场成交量", "d": "待确认", "c": "a"})
    else:
        vol_ok = vol_match >= 3
        risks.append({"l": "green" if vol_ok else "amber", "n": "市场成交量",
                      "d": f"{vol_str} · {'放量' if vol_ok else '常态'}", "c": "g" if vol_ok else "a"})

    # 纪律
    if ops_state.get('violations', 0) == 0:
        risks.append({"l": "green", "n": "纪律执行满分", "d": f"{ops_state['label']}{ops_state['count']}笔零违规", "c": "g"})
    else:
        risks.append({"l": "red", "n": "存在违规操作", "d": f"{ops_state.get('violations', 0)}次违规", "c": "r"})

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
            "sh": round(safe_float(c.get('sh', 0), 0)),   # 8/17 审计：防逗号字符串崩溃
            "st": round(safe_float(c.get('star', 0), 0)),
            "pnl": round(safe_float(c.get('pnl', 0), 0))
        })
    return chart_out


def generate_today_conclusion(rules, pa):
    """Generate 今日结论 (P1-2). Returns dict for HTML top strip.
    Data-driven from rules (rr/ra/rg) + pending_actions priorities."""
    rr = [r for r in rules if r.get('lv') == 'rr']
    ra = [r for r in rules if r.get('lv') == 'ra']
    rg = [r for r in rules if r.get('lv') == 'rg']
    pa_core = [p for p in pa if '🔴' in str(p.get('p', ''))]
    pa_all = pa

    if rr:
        return {
            "cls": "rr", "ic": "🔴", "tag": "需要行动",
            "tx": rr, "warn": ra, "pa_core": len(pa_core), "pa_total": len(pa_all)
        }
    if ra:
        return {
            "cls": "ra", "ic": "🟡", "tag": "关注即可",
            "tx": ra, "warn": [], "pa_core": len(pa_core), "pa_total": len(pa_all)
        }
    return {
        "cls": "rg", "ic": "✅", "tag": "无需操作",
        "tx": rg or [{"lv": "rg", "t": "全部绿灯 · 今日没有必须做的事，持有等待"}],
        "warn": [], "pa_core": len(pa_core), "pa_total": len(pa_all)
    }


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


# 星期对照（weekday(): 0=周一 … 6=周日）
_WEEKDAYS_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _fnum(v):
    """把值安全转 float（容忍逗号/亿/% 等字符串），失败返回 None。"""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("%", "").replace("+", "").replace("亿", "").replace("万", ""))
    except (ValueError, TypeError):
        return None


def total_hold_pnl(data: dict) -> float:
    """持有盈亏估计的【单一真源】（定义式，见 `_meta.pnl_total_note`）。

        total_hold_pnl_est = Σ holdings_summary.pnl(mv>0) + Σ stock_holdings.pnl(mv>0)

    🔴 为什么要有这个函数（2026-09-18 v4.5.4）：
      本字段此前**全仓无任何自动写入方**（唯一写入者是 `setup.py` 的一次性初始化，其余全是读），
      却被 **5 处消费**（gen_anchor_pro 公开页 / gen_weekly_report 周报 / sync_all 日快照 /
      ai_bridge_sync 信息桥 / stop_profit_backtest），**且数据更新协议第 77-78 行的入库字段清单
      里没有它** ⇒ 只能靠人工入库时手改。
      实测漂移史：**9/1–9/2 漂 +380.22**（持续 3 个备份快照）、**9/18 漂 -190.39**；
      9/10 / 9/14 / 9/16 / 9/17 均为 0（说明它确实在被人工维护，只是**必然周期性漏**）。
      ⇒ 结论：**它不是「一个待更新的字段」，而是「一个可派生的标量」**。
         改为派生后人工彻底退出该环 —— 这是「缺的是机制不是补丁」在本字段上的落地。
    """
    h = sum((_fnum(x.get("pnl")) or 0.0)
            for x in (data.get("holdings_summary") or [])
            if (_fnum(x.get("mv")) or 0) > 0)
    s = sum((_fnum(x.get("pnl")) or 0.0)
            for x in (data.get("stock_holdings") or [])
            if (_fnum(x.get("mv")) or 0) > 0)
    return round(h + s, 2)


def sync_total_hold_pnl(data: dict) -> dict:
    """按定义式重算 `total_hold_pnl_est` 并写入 `data`（**本函数不落盘**，由调用方决定）。

    返回 `{"old","new","changed","delta"}`。
    🔴 `changed=True` 时调用方**必须声张**（🔧 打印 old→new）——
      **静默自愈与静默漂移是同一个病的两面**：若只在漂移时悄悄改掉，
      就没人知道「它曾漂过、漂了多少」，与 v4.5.2「把静默失效变响」同旨。
    ⛔ 只有当 `mv>0` 的持仓计入（已清仓的零市值条目上残留的 pnl 不参与），与定义式一致。
    """
    old = data.get("total_hold_pnl_est")
    new = total_hold_pnl(data)
    data["total_hold_pnl_est"] = new
    changed = not (isinstance(old, (int, float)) and abs(float(old) - new) < 0.005)
    return {"old": old, "new": new, "changed": changed,
            "delta": (round(new - float(old), 2) if isinstance(old, (int, float)) else None)}


def validate_integrity(data: dict) -> list:
    """结构化入库自检（v4.4.0）。返回问题 list；严重问题以 '🔴' 开头（应阻断），提示以 '🟡' 开头（仅提示）。

    V1-V5 为硬项（data_pipeline --integrity / sync_all 步骤0 命中即 rc=1），
    V6-V7 为软提示。约束前提（口径铁律）：fund_account 已含 yuebao，
    顶层自洽判定为 total_assets == fund_account + stock_account，勿三者相加。
    """
    issues = []

    # ---- V1 🔴 chart_data 无重复日期（MM-DD 唯一）----
    chart = data.get("chart_data") or []
    seen_d = {}
    for c in chart:
        dd = c.get("d", "")
        if not dd:
            continue
        if dd in seen_d:
            issues.append(f"🔴 V1 chart_data 重复日期 {dd}（出现 ≥2 次，脏条目直通页面）")
        else:
            seen_d[dd] = c.get("sh")

    # ---- V2 🔴 时间轴对账：summaries/chart 末条必须等于 update_date ----
    update_date = str(data.get("update_date") or "").strip()
    if update_date:
        if chart:
            last_d = str(chart[-1].get("d", ""))
            if last_d != update_date[-5:]:
                issues.append(f"🔴 V2 chart_data 末条 {last_d} ≠ update_date {update_date}（图落后/超前，曾出现 2 天滞后）")
        else:
            issues.append("🔴 V2 chart_data 为空，无时间轴")
        summaries = data.get("daily_summaries") or []
        if summaries:
            last_s = str(summaries[-1].get("date", ""))[:10]
            if last_s != update_date[:10]:
                issues.append(f"🔴 V2 daily_summaries 末条 {last_s} ≠ update_date {update_date}")
        else:
            issues.append("🔴 V2 daily_summaries 为空")
    else:
        issues.append("🔴 V2 缺 update_date，无法对账 chart/summaries 时间轴")

    # ---- V3 🔴 星期正确性（拦 9/1「周一」误标类）----
    summaries = data.get("daily_summaries") or []
    for s in summaries:
        dt_raw = str(s.get("date", ""))[:10]
        day_txt = str(s.get("day", "")).strip()
        if len(dt_raw) == 10 and "T" not in dt_raw:
            try:
                dt = datetime.strptime(dt_raw, "%Y-%m-%d")
            except ValueError:
                continue
            expect = _WEEKDAYS_CN[dt.weekday()]
            # day 形态不定（"周五"/"2026-09-04 周五"/"周五收盘"…）→ 以「期望 token 是否出现」判定
            if day_txt and expect not in day_txt:
                issues.append(f"🔴 V3 {dt_raw} 星期标错：{day_txt!r}（应为 {expect}）")

    # ---- V4 🔴 顶层自洽（fund_account 已含 yuebao）----
    total = _fnum(data.get("total_assets"))
    fund = _fnum(data.get("fund_account"))
    stock = _fnum(data.get("stock_account"))
    yuebao = _fnum(data.get("yuebao"))
    if total is not None and fund is not None and stock is not None:
        if abs(total - (fund + stock)) > 0.01:
            issues.append(f"🔴 V4 顶层不自治：total_assets {total} ≠ fund_account {fund} + stock_account {stock} = {fund + stock}")
    if fund is not None and yuebao is not None and fund + 0.01 < yuebao:
        issues.append(f"🔴 V4 fund_account {fund} < yuebao {yuebao}（fund_account 已含 yuebao，勿三者相加）")

    # ---- V5 🔴 market.date == update_date（若 market 有 date）----
    mkt_date = str((data.get("market") or {}).get("date", "")).strip()
    if mkt_date and update_date and mkt_date != update_date[:10]:
        issues.append(f"🔴 V5 market.date {mkt_date} ≠ update_date {update_date}（行情日期与持仓日期错配）")

    # ---- V6 🟡 活跃基金持仓市值和 ≈ fund_account（仅提示）----
    if fund is not None:
        active_sum = sum(
            (_fnum(h.get("mv")) or 0)
            for h in (data.get("holdings_summary") or [])
            if _fnum(h.get("mv")) is not None and (_fnum(h.get("mv")) > 0) and h.get("group") != "已清仓"
        )
        if abs(active_sum - fund) > 0.02:
            issues.append(f"🟡 V6 活跃持仓市值和 {active_sum:,.2f} 与 fund_account {fund:,.2f} 偏差 >0.02（核对 holdings_summary 口径）")

    # ---- V7 🟡 data_freshness 由人工入库维护 ----
    meta_fresh = str((((data.get("_meta") or {}).get("data_freshness") or {}).get("holdings")) or "").strip()
    if meta_fresh and meta_fresh[:10] != update_date[:10]:
        issues.append(f"🟡 V7 _meta.data_freshness.holdings 为 {meta_fresh[:10]}，落后 update_date {update_date[:10]}（该字段由人工入库维护，见协议 v1.5）")

    # ---- V8 🔴 total_hold_pnl_est 必须等于定义式（v4.5.4）----
    #   本字段被 5 处消费（公开页/周报/日快照/信息桥/回测脚本）却此前无自动写入方，
    #   只能人工手改 ⇒ 实测漂移 9/1 +380.22、9/18 -190.39。现改为**派生**：
    #   `sync_derived_fields.py` 在 sync_all 中**先于本自检**重算写回。
    #   🔴 本断言是**顺序护栏**：若归一化步骤被跳过 / 被排到自检之后 / 被改名，
    #      此处必须响 —— 「步骤存在」与「步骤在自检之前跑过」是两件事。
    _cur = data.get("total_hold_pnl_est")
    _calc = total_hold_pnl(data)
    if not isinstance(_cur, (int, float)):
        issues.append(f"🔴 V8 total_hold_pnl_est 非数值（{_cur!r}），定义式应得 {_calc}")
    elif abs(float(_cur) - _calc) > 0.01:
        issues.append(f"🔴 V8 total_hold_pnl_est {_cur} ≠ 定义式 Σpnl(mv>0) {_calc}"
                      f"（差 {round(_calc - float(_cur), 2)}）—— 归一化步骤（sync_derived_fields.py）未跑或跑在其后")

    return issues


def process_all(data):
    """Process all portfolio data. Returns dict ready for embedding."""
    # Validate
    warnings = validate_data(data)
    # v4.4.0 结构化入库自检（rebuild 现有 _warnings 循环免费打印；致命闸门在 data_pipeline --integrity / sync_all 步骤0）
    try:
        warnings += validate_integrity(data)
    except Exception as _e:
        warnings.append(f"validate_integrity 异常: {_e}")

    # Holdings (P1-1 智能分类)
    raw = data.get('holdings_summary', [])
    stocks = data.get('stock_holdings', [])
    mkt = data.get('market', {})
    bedrock, core, sat, cash, dropped = process_holdings(raw, stocks, data=data, mkt=mkt)
    for d in dropped:
        warnings.append(f"持仓无法归类，已跳过: {d}")

    # Totals and dynamic holding contract
    totals = compute_totals(bedrock, core, sat, cash)
    holding_counts = compute_holding_counts(bedrock, core, sat, cash)
    layers = build_layer_rows(totals, holding_counts)

    # Shared state
    mkt = data.get('market', {})
    mkt_note = mkt.get('note', '')
    ops_state = compute_ops_state(data)
    drawdown_state = compute_drawdown_state(data, totals)
    rules = generate_rules(sat, data, mkt, totals, drawdown_state=drawdown_state, ops_state=ops_state)
    risks = generate_risk_matrix(data, mkt_note, totals, ops_state)
    risk_state = compute_risk_state(rules, risks, drawdown_state, ops_state, mkt)
    freeze_state = compute_freeze_state(data, ops_state, risk_state, mkt, totals)
    opportunity_scores = compute_opportunity_scores(data, ops_state, risk_state, freeze_state, totals)
    clock_state = compute_clock_state(data)
    factor_clusters = compute_factor_clusters(data, totals)
    portfolio_state = derive_portfolio_state(
        totals['total'], totals['cash_mv'], drawdown_state['dd_pct'], mkt_note,
        ops_state['count'], ops_state['max'], ops_state['violations']
    )

    # DCA list
    dca_list = [str(d) for d in data.get('dca_running', [])]
    pending_actions = normalize_pending_actions(data.get('pending_actions', []))

    # Daily summaries
    ds_out = prepare_daily_summaries(data)

    # Chart data
    chart_out = prepare_chart_data(data)

    # Build result
    today = generate_today_conclusion(rules, pending_actions)
    result = {
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "source_update_date": data.get('update_date') or data.get('update_time', ''),
        "total": round(totals['total'], 2),
        "fundMv": round(totals['fund_mv_total'], 2),
        "cashMv": round(totals['cash_mv'], 2),
        "stockMv": round(totals['stock_mv'], 2),
        "totalPnl": round(totals['total_pnl'], 2),
        "bedrock_mv": round(totals['bedrock_mv']),
        "core_mv": round(totals['core_mv']),
        "sat_mv": round(totals['sat_mv']),
        "cash_mv": round(totals['cash_mv']),
        "peak_assets": drawdown_state['peak_assets'],
        "peak_note": drawdown_state['peak_note'],
        "dd_pct": drawdown_state['dd_pct'],
        "aug_ops": ops_state['count'],
        "aug_ops_max": ops_state['max'],
        "violations": ops_state['violations'],
        "mkt": mkt,
        "dca": dca_list,
        "bedrock": bedrock,
        "core": core,
        "sat": sat,
        "cash": cash,
        "holding_counts": holding_counts,
        "layers": layers,
        "layer_order": LAYER_ORDER,
        "layer_meta": LAYER_META,
        "rules": rules,
        "wl": data.get('watchlist', []),
        "pa": pending_actions,
        "risks": risks,
        "today": today,
        "ds": ds_out,
        "chart": chart_out,
        "drawdown_state": drawdown_state,
        "ops_state": ops_state,
        "risk_state": risk_state,
        "freeze_state": freeze_state,
        "opportunity_scores": opportunity_scores,
        "clock_state": clock_state,
        "factor_clusters": factor_clusters,
        "portfolio_state": portfolio_state,
        "state": {
            "ops": ops_state,
            "drawdown": drawdown_state,
            "risk": risk_state,
            "freeze": freeze_state,
            "opportunities": opportunity_scores,
            "clocks": clock_state,
            "factor_clusters": factor_clusters,
            "portfolio": portfolio_state,
            "holding_counts": holding_counts,
            "layers": layers,
        },
        "_warnings": warnings,
    }
    return result


def build_snapshot(embed):
    """Build snapshot JSON from the processed embed."""
    state = embed.get('state', {})
    snapshot = {
        "update_time": embed.get('time', ''),
        "source_update_date": embed.get('source_update_date', ''),
        "total_assets": embed.get('total', 0),
        "fund_mv": embed.get('fundMv', 0),
        "stock_mv": embed.get('stockMv', 0),
        "cash_mv": embed.get('cashMv', 0),
        "total_pnl": embed.get('totalPnl', 0),
        "holding_counts": embed.get('holding_counts', {}),
        "layers": embed.get('layers', []),
        "layer_order": embed.get('layer_order', []),
        "layer_meta": embed.get('layer_meta', {}),
        "peak_assets": embed.get('peak_assets', 0),
        "dd_pct": embed.get('dd_pct', 0),
        "layer_summary": {
            "bedrock": {"mv": embed.get('bedrock_mv', 0), "pct": round(embed.get('bedrock_mv', 0) / embed.get('total', 1) * 100, 1) if embed.get('total', 0) > 0 else 0},
            "core": {"mv": embed.get('core_mv', 0), "pct": round(embed.get('core_mv', 0) / embed.get('total', 1) * 100, 1) if embed.get('total', 0) > 0 else 0},
            "sat": {"mv": embed.get('sat_mv', 0), "pct": round(embed.get('sat_mv', 0) / embed.get('total', 1) * 100, 1) if embed.get('total', 0) > 0 else 0},
            "cash": {"mv": embed.get('cash_mv', 0), "pct": round(embed.get('cash_mv', 0) / embed.get('total', 1) * 100, 1) if embed.get('total', 0) > 0 else 0},
        },
        "dca_running": embed.get('dca', []),
        "watchlist": embed.get('wl', []),
        "pending_actions": embed.get('pa', []),
        "rule_checks": embed.get('rules', []),
        "risk_matrix": embed.get('risks', []),
        "today_conclusion": embed.get('today', {}),
        "drawdown_state": embed.get('drawdown_state', {}),
        "ops_state": embed.get('ops_state', {}),
        "risk_state": embed.get('risk_state', {}),
        "freeze_state": embed.get('freeze_state', {}),
        "opportunity_scores": embed.get('opportunity_scores', []),
        "clock_state": embed.get('clock_state', {}),
        "factor_clusters": embed.get('factor_clusters', {}),
        "chart_data": embed.get('chart', []),
        "state": state,
        "aug_ops": embed.get('aug_ops', 0),
        "aug_ops_max": embed.get('aug_ops_max', 0),
        "violations": embed.get('violations', 0),
        "portfolio_state": embed.get('portfolio_state', {}),
    }
    return snapshot
