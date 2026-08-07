#!/usr/bin/env python3
"""
Anchor 体系总览页 (anchor-pro.html) 数据生成器 (短板2)
从 portfolio_data.json 动态生成实时数据块，替换 anchor-pro.html 内嵌的 var D={...}
叙事部分（胜率/教训/对比/规则/演变）保持模板内容不变，仅更新实时数字。

用法: python gen_anchor_pro.py
输出: 08-可视化网站/anchor-pro.html (就地更新 var D 数据块)
"""
import json
import os
import re
from pathlib import Path

DESKTOP = Path(r"C:\Users\lenovo\Desktop")
ANCHOR = DESKTOP / "Anchor"
DATA_PATH = DESKTOP / "portfolio_data.json"
PRO_HTML = ANCHOR / "08-可视化网站" / "anchor-pro.html"

# 持仓显示名映射（与页面一致）
NAME_MAP = {
    "华泰柏瑞上证红利ETF联接A": "515180 红利ETF",
    "国泰黄金ETF联接A": "国泰黄金ETF联接A",
    "易方达恒生港股通创新药ETF联接C": "创新药ETF联接C",
    "华夏国证半导体芯片ETF联接C": "半导体芯片ETF联接C",
    "易方达证券ETF联接C": "证券ETF联接C",
    "天弘通利混合A": "天弘通利混合A",
    "鹏华畅享债券C": "鹏华畅享债券C",
    "中银稳健增利债券A": "中银稳健增利债券A",
    "天弘纳斯达克100指数(QDII)C": "天弘纳指100 QDII C",
    "华泰柏瑞纳斯达克100ETF联接A": "华泰纳指100 ETF联接A",
    "余额宝": "余额宝",
}

GROUP_LAYER = {"bed": "bedrock", "core": "core", "sat": "sat", "cash": "cash"}
LAYER_GROUP = {v: k for k, v in GROUP_LAYER.items()}
# 层序
LAYER_ORDER = ["bedrock", "core", "sat", "cash"]


def load():
    with open(DATA_PATH, encoding='utf-8') as f:
        return json.load(f)


def build_data(data):
    """从 JSON 构建实时数据块。返回 dict 对应页面 var D 的实时部分。"""
    holdings = data.get('holdings_summary', [])
    active = [h for h in holdings if (h.get('mv', 0) or 0) > 0]
    stocks = data.get('stock_holdings', [])

    # 总资产（与 snapshot 逻辑一致：基金 + 股票 + 现金）
    total = data.get('total_assets', 0)
    total_pnl = data.get('total_hold_pnl_est', 0)
    # 四层
    def group_mv(layer):
        return sum(h.get('mv', 0) or 0 for h in active if _layer_of(h.get('group', '')) == layer)

    layers = {l: round(group_mv(l), 0) for l in LAYER_ORDER}

    # 持仓盈亏颜色
    def _c(pnl):
        return "g" if pnl >= 0 else "r"

    # 各持仓市值（带盈亏色）
    by_layer = {l: [] for l in LAYER_ORDER}
    for h in active:
        lyr = _layer_of(h.get('group', ''))
        by_layer[lyr].append({
            "n": NAME_MAP.get(h['name'], h['name']),
            "v": round(h.get('mv', 0) or 0, 0),
            "c": _c(h.get('pnl', 0) or 0)
        })
    for s in stocks:
        by_layer["bedrock"].append({"n": "515180 红利ETF", "v": round(s.get('mv', 0) or 0, 0), "c": _c(s.get('pnl', 0) or 0)})

    stock_mv = sum(s.get('mv', 0) or 0 for s in stocks)
    fund_mv = total - stock_mv - (layers.get("cash", 0) or 0)
    update = data.get('update_date', '')
    return {
        "update": update,
        "total_assets": round(total),
        "total_pnl": round(total_pnl),
        "fund_mv": round(fund_mv),
        "stock_mv": round(stock_mv),
        "cash_mv": round(layers.get("cash", 0)),
        "bed_mv": round(layers.get("bedrock", 0)),
        "core_mv": round(layers.get("core", 0)),
        "sat_mv": round(layers.get("sat", 0)),
        "cash_mv_l": round(layers.get("cash", 0)),
        "holdings": by_layer,
    }


def _layer_of(group):
    if group in ("全局固收",):
        return "bedrock"
    if group in ("核心增长", "全局QDII"):
        return "core"
    if group == "进攻组合":
        return "sat"
    if group == "现金预备":
        return "cash"
    return "cash"  # 兜底


def json_block(data):
    """生成页面需要的数据块（保留叙事部分）。"""
    d = build_data(data)
    hero_list = [
        {"v": f"{d['total_assets']:,}", "c": "var(--accent)", "l": "总资产 ¥"},
        {"v": "87.5%", "c": "var(--green)", "l": "卫星胜率"},
        {"v": "96", "c": "var(--amber)", "l": "体系评分"},
        {"v": "0", "c": "#fff", "l": "违规操作"},
    ]
    pyramid = [
        {"l": "bed", "icon": "🛡️", "name": "压舱石层 · 45%", "assets": "鹏华债券C + 中银债券A + 515180红利ETF + 国泰黄金A", "detail": "年化 3-6% · 年操作 0-1 次 · 最大回撤 <5%", "rule": "永远不卖", "mv": d["bed_mv"]},
        {"l": "core", "icon": "🚀", "name": "核心增长层 · 20%", "assets": "华泰纳指100 A + 天弘纳指100 C + 天弘通利A", "detail": "年化 10-12% · 定投为主 · PE>35才减仓", "rule": "定投为主", "mv": d["core_mv"]},
        {"l": "sat", "icon": "🔥", "name": "卫星进攻层 · 20%", "assets": "创新药C + 证券ETF C + 半导体C", "detail": "年化 15-25% · 快进快出 · 单只≤3,000 · 同时≤4只", "rule": "-8% 止损", "mv": d["sat_mv"]},
        {"l": "cash", "icon": "💰", "name": "现金预备层 · 15%", "assets": "余额宝", "detail": "仅用于压舱石暴跌补仓 · 不参与卫星交易", "rule": "暴跌才动", "mv": d["cash_mv_l"]},
    ]

    # 实时数据统一组装为 dict，用 json.dumps 序列化避免手工逗号错误
    kpi = [
        {"v": "-2,343", "c": "var(--red)", "l": "七月真实盈亏", "s": "科创50月跌 -17% · 组合跑赢大盘"},
        {"v": "5 次", "c": "var(--amber)", "l": "浮亏不加仓 · 拦下", "s": "每次拦住的第二天半导体都在跌"},
        {"v": "7 笔", "c": "var(--green)", "l": "月操作 · 从 80→", "s": "降低 91% · 连续数月零违规"},
        {"v": "+513", "c": "var(--accent)", "l": "清仓少亏", "s": "反弹日五只清仓 vs 持有到今天"},
    ]
    realtime = {
        "update": d["update"],
        "total_assets": d["total_assets"],
        "total_pnl": d["total_pnl"],
        "fund_mv": d["fund_mv"],
        "stock_mv": d["stock_mv"],
        "cash_mv": d["cash_mv"],
        "hero": hero_list,
        "kpi": kpi,
        "pyramid": pyramid,
        "holdings": {lyr: d["holdings"].get(lyr, []) for lyr in LAYER_ORDER},
    }
    # 保留后续叙事部分（comparison/monthly/rules/forbidden/evo）
    # 用占位符 __NARRATIVE__，main 里替换为原叙事段落。
    # 先序列化实时 dict，去掉最后 '}'，注入 ",\n 叙事" 再补 '}'。
    base = json.dumps(realtime, ensure_ascii=False, indent=2)
    base = base[:-1] + ",\n__NARRATIVE__\n}"
    return "var D=" + base


def main():
    data = load()
    if not PRO_HTML.exists():
        print(f"[ERROR] 未找到 {PRO_HTML}")
        return
    with open(PRO_HTML, encoding='utf-8') as f:
        html = f.read()

    # 定位 var D={ 和 }; 之间的数据块
    start = html.find("var D={")
    end = html.find("};", start)
    if start < 0 or end < 0:
        print("[ERROR] 未找到 var D={...} 数据块，请检查模板格式")
        return

    # 提取"叙事尾部"（从 comparison 开始，去掉末尾 D 对象闭合 '}'）
    # 策略：保留原文件中 comparison/rules/forbidden/evo 等叙事段落
    orig_block = html[start:end]
    # 找到 "comparison" 开始位置（叙事数据起点）
    comp_start = orig_block.find('"comparison"')
    if comp_start > 0:
        narrative = orig_block[comp_start:]  # comparison 之后的叙事数据
        # 去掉末尾 D 对象闭合 '}'（json_block 已提供闭合）
        narrative = narrative.rstrip().rstrip('}').rstrip()
    else:
        narrative = ""
        print("[WARN] 未找到 comparison 叙事段，仅更新实时数据")

    new_block = json_block(data)
    # 拼接：把 narrative 注入占位符（D 对象属性段）
    if narrative:
        # narrative 是 'comparison: [...], ... evo: [...]'（含结尾逗号）
        new_block = new_block.replace("__NARRATIVE__", narrative)
    else:
        new_block = new_block.replace("__NARRATIVE__", "")
    # html[end] 是 D 对象结尾 '}'，html[end+1] 是 ';'。
    # 新 block 以 '}' 结尾（含叙事），替换 [start, end+1]，接原 end+1 之后。
    new_html = html[:start] + new_block + html[end + 1:]
    with open(PRO_HTML, 'w', encoding='utf-8') as f:
        f.write(new_html)
    print(f"[OK] anchor-pro.html 已更新: {PRO_HTML}")
    print(f"     总资产 {data.get('total_assets')} · 更新 {data.get('update_date')}")


if __name__ == '__main__':
    main()
