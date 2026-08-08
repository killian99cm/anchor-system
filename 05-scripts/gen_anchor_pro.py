#!/usr/bin/env python3
"""
Anchor 体系总览页 (anchor-pro.html) 公共数据生成器

公开网页只能使用脱敏示例数据。这个脚本固定读取
06-dashboard/portfolio_data_example.json，替换 anchor-pro.html 内嵌的 var D={...} 数据块。

用法: python gen_anchor_pro.py
输出: 08-website/anchor-pro.html（公开 / 示例数据）
"""
import json
import re
import sys
from pathlib import Path

DESKTOP = Path(r"C:\Users\lenovo\Desktop")
ANCHOR = DESKTOP / "Anchor"
PUBLIC_DATA_PATH = ANCHOR / "06-dashboard" / "portfolio_data_example.json"
PRO_HTML = ANCHOR / "08-website" / "anchor-pro.html"

LAYER_ORDER = ["bedrock", "core", "sat", "cash"]
LAYER_META = {
    "bedrock": {"icon": "🛡️", "label": "压舱石", "cls": "bed", "target": 45, "fallback": "示例债券基金 + 示例红利ETF"},
    "core": {"icon": "🚀", "label": "核心增长", "cls": "core", "target": 20, "fallback": "示例宽基指数基金"},
    "sat": {"icon": "🔥", "label": "卫星进攻", "cls": "sat", "target": 20, "fallback": "示例行业ETF"},
    "cash": {"icon": "💰", "label": "现金预备", "cls": "cash", "target": 15, "fallback": "现金预备"},
}
GROUP_TO_LAYER = {
    "全局固收": "bedrock",
    "核心增长": "core",
    "全局QDII": "core",
    "进攻组合": "sat",
    "现金预备": "cash",
}
KEYWORD_TO_LAYER = [
    ("债券", "bedrock"), ("黄金", "bedrock"), ("红利", "bedrock"),
    ("QDII", "core"), ("纳指", "core"), ("纳斯达克", "core"), ("混合", "core"),
    ("半导体", "sat"), ("芯片", "sat"), ("创新药", "sat"), ("证券", "sat"),
    ("现金", "cash"), ("货币", "cash"),
]
PRIVATE_TOKENS = [
    "示例黄金基金",
    "示例联接基金恒生港股通创新药ETF联接C",
    "示例行业基金半导体芯片ETF联接C",
    "示例联接基金证券ETF联接C",
    "示例指数基金通利混合A",
    "示例债券基金",
    "示例债券基金B",
    "示例指数基金纳斯达克100指数",
    "示例宽基基金纳斯达克100",
    "100红利",
    "余额宝",
    "515180",
    "35485.73",
    "32961",
    "10只基金 + 1只股票 + 余额宝",
    "10只活跃持仓",
    "12个活跃项",
    "109笔实盘交易",
    "109笔交易",
    "28只清仓基金",
    "13个月数据",
    "13个月盈亏走势",
    "13个月合计",
    "¥2,343",
    "日均亏损从 -¥86 降到 -¥66",
    "真实亏损案例",
    "实盘持仓",
]

EXAMPLE_NAME_BY_LAYER = {
    "bedrock": "示例压舱基金",
    "core": "示例核心基金",
    "sat": "示例行业ETF",
    "cash": "现金预备",
}


def load_public_data():
    """Load sanitized public example data only."""
    if "--private" in sys.argv:
        raise SystemExit("[ERROR] anchor-pro.html 是公开页面，禁止使用私有 portfolio_data.json 生成。")
    with open(PUBLIC_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("_example"):
        raise SystemExit(f"[ERROR] {PUBLIC_DATA_PATH} 必须带 _example=true，避免误用真实持仓。")
    return data


def layer_of(item):
    """Resolve public example layer dynamically from explicit layer/group/name."""
    explicit = str(item.get("layer") or item.get("anchor_layer") or "").strip()
    if explicit in LAYER_ORDER:
        return explicit
    group_layer = GROUP_TO_LAYER.get(item.get("group", ""))
    if group_layer:
        return group_layer
    name = str(item.get("name") or item.get("code") or "")
    for kw, layer in KEYWORD_TO_LAYER:
        if kw in name:
            return layer
    return "cash"


def item_value(item):
    """Use explicit market value first; otherwise shares * price."""
    if item.get("mv") is not None:
        return round(item.get("mv") or 0)
    return round(((item.get("shares", 0) or 0) * (item.get("price", 0) or 0)) or 0)


def compute_counts(by_layer):
    """Public example counts are structural examples, not real active positions."""
    counts = {"active": 0, "total": 0, "fund": 0, "stock": 0, "cash": 0}
    by_layer_counts = {}
    for layer, items in by_layer.items():
        by_layer_counts[layer] = len(items)
        for item in items:
            counts["active"] += 1
            counts["total"] += 1
            typ = item.get("type") or ("cash" if layer == "cash" else "fund")
            counts[typ] = counts.get(typ, 0) + 1
    parts = []
    if counts["fund"]:
        parts.append(f"{counts['fund']}只基金")
    if counts["stock"]:
        parts.append(f"{counts['stock']}只股票")
    if counts["cash"]:
        parts.append(f"{counts['cash']}项现金")
    counts["by_layer"] = by_layer_counts
    counts["layers"] = by_layer_counts
    counts["by_type"] = {"fund": counts["fund"], "stock": counts["stock"], "cash": counts["cash"]}
    counts["active_label"] = " + ".join(parts) if parts else "暂无持仓"
    return counts


def build_layer_rows(layer_mv, total, counts):
    rows = []
    for layer in LAYER_ORDER:
        meta = LAYER_META[layer]
        mv = layer_mv.get(layer, 0)
        rows.append({
            "key": layer,
            "icon": meta["icon"],
            "label": meta["label"],
            "cls": meta["cls"],
            "target": meta["target"],
            "mv": mv,
            "pct": round(mv / total * 100, 1) if total else 0,
            "count": counts.get("by_layer", {}).get(layer, 0),
        })
    return rows


def public_display_name(layer, item_type, index):
    """Return generic public names; never trust input names for a public page."""
    if item_type == "cash" or layer == "cash":
        return "现金预备"
    suffix = chr(ord("A") + index) if index < 26 else str(index + 1)
    if item_type == "stock":
        return f"示例股票{suffix}"
    return f"{EXAMPLE_NAME_BY_LAYER.get(layer, '示例基金')}{suffix}"


def sensitive_tokens_from_input(data):
    """Build a leak list from the source JSON, even when _example=true is set."""
    tokens = set(PRIVATE_TOKENS)
    for section in ("holdings_summary", "stock_holdings"):
        for item in data.get(section, []):
            for key in ("name", "code"):
                value = str(item.get(key, "")).strip()
                if value and not value.startswith("示例") and value != "现金预备":
                    tokens.add(value)
    for key in ("total_assets", "fund_account", "stock_account", "yuebao", "total_hold_pnl_est"):
        value = data.get(key)
        if isinstance(value, (int, float)) and value:
            tokens.add(str(int(round(value))))
    return sorted(tokens, key=len, reverse=True)


def contains_sensitive_token(text, token):
    """Match direct and whitespace-spaced variants of private tokens."""
    if not token:
        return False
    if token in text:
        return True
    compact_text = re.sub(r"\s+", "", text)
    compact_token = re.sub(r"\s+", "", token)
    return bool(compact_token and compact_token in compact_text)


def leaked_tokens(text, data):
    return [token for token in sensitive_tokens_from_input(data) if contains_sensitive_token(text, token)]


def build_data(data):
    """Build a sanitized data object for the public overview page."""
    holdings = [h for h in data.get("holdings_summary", []) if (h.get("mv", 0) or 0) >= 0]
    stocks = data.get("stock_holdings", [])
    total = round(data.get("total_assets", 0) or 0)
    total_pnl = round(data.get("total_hold_pnl_est", 0) or 0)
    update = data.get("update_date") or data.get("update_time", "")[:10]

    by_layer = {layer: [] for layer in LAYER_ORDER}
    name_index = {layer: 0 for layer in LAYER_ORDER}
    for h in holdings:
        layer = layer_of(h)
        mv = item_value(h)
        pnl = h.get("pnl", 0) or 0
        item_type = "cash" if layer == "cash" else "fund"
        display_name = public_display_name(layer, item_type, name_index[layer])
        name_index[layer] += 1
        by_layer[layer].append({
            "n": display_name,
            "v": mv,
            "c": "g" if pnl >= 0 else "r",
            "type": item_type,
        })
    for s in stocks:
        layer = layer_of(s) if (s.get("layer") or s.get("anchor_layer") or s.get("group")) else "bedrock"
        mv = item_value(s)
        pnl = s.get("pnl", 0) or 0
        display_name = public_display_name(layer, "stock", name_index[layer])
        name_index[layer] += 1
        by_layer[layer].append({
            "n": display_name,
            "v": mv,
            "c": "g" if pnl >= 0 else "r",
            "type": "stock",
        })

    layer_mv = {layer: sum(i["v"] for i in by_layer[layer]) for layer in LAYER_ORDER}
    stock_mv = sum(i["v"] for items in by_layer.values() for i in items if i.get("type") == "stock")
    cash_mv = layer_mv.get("cash", 0)
    fund_mv = sum(i["v"] for items in by_layer.values() for i in items if i.get("type") == "fund")
    if total and fund_mv + stock_mv + cash_mv == 0:
        fund_mv = max(total - stock_mv - cash_mv, 0)
    counts = compute_counts(by_layer)

    return {
        "update": update,
        "total_assets": total,
        "total_pnl": total_pnl,
        "fund_mv": fund_mv,
        "stock_mv": stock_mv,
        "cash_mv": cash_mv,
        "layer_mv": layer_mv,
        "holdings": by_layer,
        "holding_counts": counts,
        "layers": build_layer_rows(layer_mv, total, counts),
    }


def names_for(items, fallback):
    names = [i["n"] for i in items if i.get("n")]
    return " + ".join(names[:4]) if names else fallback


def json_block(data):
    """Generate the complete public var D block."""
    d = build_data(data)
    pyramid = []
    for layer in LAYER_ORDER:
        meta = LAYER_META[layer]
        pyramid.append({
            "l": meta["cls"],
            "icon": meta["icon"],
            "name": f"{meta['label']}层 · {meta['target']}%",
            "assets": names_for(d["holdings"][layer], meta["fallback"]),
            "detail": {
                "bedrock": "低波动资产 · 年操作 0-1 次 · 稳定组合地基",
                "core": "宽基 / 核心资产 · 定投为主 · 估值约束",
                "sat": "高弹性仓位 · 单只限额 · 快速纠错",
                "cash": "等待极端机会 · 保留安全垫",
            }[layer],
            "rule": {
                "bedrock": "长期持有",
                "core": "定投为主",
                "sat": "-8% 止损",
                "cash": "纪律备用",
            }[layer],
            "mv": d["layer_mv"][layer],
        })
    public = {
        "update": d["update"],
        "total_assets": d["total_assets"],
        "total_pnl": d["total_pnl"],
        "fund_mv": d["fund_mv"],
        "stock_mv": d["stock_mv"],
        "cash_mv": d["cash_mv"],
        "holding_counts": d["holding_counts"],
        "layers": d["layers"],
        "layer_order": LAYER_ORDER,
        "layer_meta": LAYER_META,
        "hero": [
            {"v": f"{d['total_assets']:,}", "c": "var(--accent)", "l": "示例总资产 ¥"},
            {"v": "4层", "c": "var(--green)", "l": "资产金字塔"},
            {"v": "96", "c": "var(--amber)", "l": "体系评分"},
            {"v": "0", "c": "#fff", "l": "示例违规"},
        ],
        "kpi": [
            {"v": "≤4笔", "c": "var(--green)", "l": "月操作上限", "s": "买入≤2 + 卖出≤2，降低过度交易"},
            {"v": "72h", "c": "var(--amber)", "l": "卖出冻结", "s": "清仓资金先冷却，再决定是否重开"},
            {"v": "-8%", "c": "var(--red)", "l": "单仓止损", "s": "卫星仓先保命，再谈收益"},
            {"v": "动态", "c": "var(--accent)", "l": "持仓数量", "s": "随市场与规则调整，由数据自动计算"},
        ],
        "copy": {
            "meta_description": "四层金字塔投资纪律体系。示例数据演示，少亏指南，不是赚钱秘籍。",
            "badge": "⚓ 示例交易复盘 · 脱敏数据 · v3.3 持续迭代",
            "portfolio_label": "Portfolio · 示例配置",
            "portfolio_title": "示例持仓",
            "evidence_lead": "建立体系后，目标不是追求暴利，而是减少冲动交易、限制回撤、让每次操作可复盘。",
            "history_title": "示例盈亏走势",
            "history_lead": "以下为脱敏样本走势，只展示体系记录方法，不代表真实收益。",
            "rules_lead": "每一条规则背后都对应可复盘的风险案例，是纪律约束，不是理论口号。",
            "forbidden_lead": "每一条禁令都对应常见错误操作。这些不是建议，是底线。",
            "cta_title": "用复盘成本换来的规则",
            "cta_text": "多笔样本交易 · 多只清仓样本 · 多月记录 · 开源 · 免费 · 永不收费",
            "monthly_sum_prefix": "样本合计",
        },
        "pyramid": pyramid,
        "holdings": {layer: d["holdings"].get(layer, []) for layer in LAYER_ORDER},
        "comparison": [
            {"dim": "决策方式", "before": "凭感觉追涨杀跌", "after": "规则先行，状态机执行", "change": "更稳定", "cls": "improve"},
            {"dim": "月交易笔数", "before": "频繁操作", "after": "≤4 笔/月", "change": "大幅下降", "cls": "improve"},
            {"dim": "持仓管理", "before": "名单和数量写死", "after": "从数据动态生成", "change": "可扩展", "cls": "improve"},
            {"dim": "公开数据", "before": "可能混入真实持仓", "after": "只发布示例 / 脱敏数据", "change": "安全", "cls": "improve"},
        ],
        "monthly": [
            {"m": "1月", "v": 60, "up": 1}, {"m": "2月", "v": -30, "up": 0},
            {"m": "3月", "v": 80, "up": 1}, {"m": "4月", "v": 40, "up": 1},
            {"m": "5月", "v": -20, "up": 0}, {"m": "6月", "v": 50, "up": 1},
            {"m": "7月", "v": -10, "up": 0}, {"m": "8月", "v": 30, "up": 1},
        ],
        "rules": [
            {"n": "01", "icon": "🛑", "title": "浮亏不加仓", "cost": "避免越跌越买", "desc": "卫星仓没有浮盈时，不把下跌误判为机会。"},
            {"n": "02", "icon": "🔒", "title": "卖出冻结72小时", "cost": "过滤冲动交易", "desc": "卖出后的资金先进入现金层，至少冷却三天。"},
            {"n": "03", "icon": "📉", "title": "-8% 止损", "cost": "限制单仓风险", "desc": "单笔错误不能拖垮整个组合。"},
            {"n": "04", "icon": "📊", "title": "组合回撤线", "cost": "系统级防御", "desc": "-5%、-10%、-15% 对应不同减仓动作。"},
        ],
        "forbidden": [
            {"n": "01", "act": "浮亏补仓", "cost": "扩大错误", "alt": "等浮盈或重新评估"},
            {"n": "02", "act": "当天换标的", "cost": "情绪交易", "alt": "72h 冷却"},
            {"n": "03", "act": "无预案买入", "cost": "无法复盘", "alt": "先写止损和目标"},
        ],
        "evo": [
            {"v": "v3.0", "s": 80, "c": "var(--amber)", "d": "四层结构\n基础纪律"},
            {"v": "v3.1", "s": 88, "c": "var(--green)", "d": "负面清单\n交易约束"},
            {"v": "v3.2", "s": 94, "c": "var(--green)", "d": "风险平价\n量化回撤"},
            {"v": "v3.3", "s": 96, "c": "var(--accent)", "d": "状态机\n动态持仓"},
        ],
    }
    block = "var D=" + json.dumps(public, ensure_ascii=False, indent=2)
    leaked = leaked_tokens(block, data)
    if leaked:
        raise SystemExit(f"[ERROR] 公开数据块包含私有标记：{', '.join(leaked[:5])}")
    return block


def main():
    data = load_public_data()
    if not PRO_HTML.exists():
        raise SystemExit(f"[ERROR] 未找到 {PRO_HTML}")
    html = PRO_HTML.read_text(encoding="utf-8")
    match = re.search(r"var\s+D\s*=\s*\{", html)
    if not match:
        raise SystemExit("[ERROR] 未找到 var D={...} 数据块，请检查模板格式")
    end = html.find("};", match.start())
    if end < 0:
        raise SystemExit("[ERROR] 未找到 var D 数据块结尾 ;")

    new_block = json_block(data)
    new_html = html[:match.start()] + new_block + html[end + 1:]
    replacements = {
        'content="109笔实盘迭代。四层金字塔体系。少亏指南，不是赚钱秘籍。"': 'content="四层金字塔投资纪律体系。示例数据演示，少亏指南，不是赚钱秘籍。"',
        "⚓ 109笔实盘交易 · 13个月数据 · v3.3 持续迭代": "⚓ 示例交易复盘 · 脱敏数据 · v3.3 持续迭代",
        "Portfolio · 当前配置": "Portfolio · 示例配置",
        "实盘<em>持仓</em>": "示例<em>持仓</em>",
        "7月16日建立体系。不是赚钱——是亏得更慢了。日均亏损从 -¥86 降到 -¥66。": "建立体系后，目标不是追求暴利，而是减少冲动交易、限制回撤、让每次操作可复盘。",
        "13个月<em>盈亏走势</em>": "示例<em>盈亏走势</em>",
        "2025年8月-2026年7月。红=亏损月，绿=盈利月。7个月盈利，6个月亏损。": "以下为脱敏样本走势，只展示体系记录方法，不代表真实收益。",
        "每一条规则背后都有真实亏损案例，是 ¥2,343 学费换来的纪律，不是理论推导。": "每一条规则背后都对应可复盘的风险案例，是纪律约束，不是理论口号。",
        "每一条禁令都对应一段真实亏损。这些不是建议，是底线。": "每一条禁令都对应常见错误操作。这些不是建议，是底线。",
        "¥2,343 学费换来的规则": "用复盘成本换来的规则",
        "109笔交易 · 28只清仓基金 · 13个月数据 · 开源 · 免费 · 永不收费": "多笔样本交易 · 多只清仓样本 · 多月记录 · 开源 · 免费 · 永不收费",
        "这是 109 笔交易迭代出的自我约束": "这是多次样本复盘沉淀出的自我约束",
        "这是 109笔交易迭代出的自我约束": "这是多次样本复盘沉淀出的自我约束",
        "109 笔交易迭代出的自我约束": "多次样本复盘沉淀出的自我约束",
        "13个月合计: ": "样本合计: ",
        "sum/13": "sum/Math.max(D.monthly.length,1)",
        "up+'/12'": "up+'/'+D.monthly.length",
    }
    for old, new in replacements.items():
        new_html = new_html.replace(old, new)
    leaked = [token for token in sensitive_tokens_from_input(data) if token in new_html]
    if leaked:
        raise SystemExit(f"[ERROR] 公开HTML包含私有标记：{', '.join(leaked[:5])}")
    PRO_HTML.write_text(new_html, encoding="utf-8")
    print(f"[OK] anchor-pro.html 已更新为公开示例数据: {PRO_HTML}")
    print(f"     示例总资产 {data.get('total_assets')} · 更新 {data.get('update_date', data.get('update_time', ''))}")


if __name__ == '__main__':
    main()
