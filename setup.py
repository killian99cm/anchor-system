#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚓ Anchor 投资管理系统 — 交互式配置向导
========================================
第一次使用？运行此脚本，按提示输入持仓信息，自动生成 portfolio_data.json。
无需手动编辑 JSON，无需懂 Python。

使用方式：
    python setup.py          # 交互式配置
    python setup.py --reset  # 重新配置（覆盖现有数据）
    python setup.py --demo   # 生成演示数据（体验用）
"""

import json
import os
import sys
from datetime import date

VERSION = "v4.3.3"

# ── 颜色支持 ─────────────────────────────────────────
def green(s):  return f"\033[92m{s}\033[0m"
def blue(s):   return f"\033[94m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"
def red(s):    return f"\033[91m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"
def cyan(s):   return f"\033[96m{s}\033[0m"

# ── 工具函数 ─────────────────────────────────────────
def ask(prompt, default=None):
    """询问用户输入，支持默认值"""
    if default:
        result = input(f"  {prompt} [{default}]: ").strip()
        return result if result else str(default)
    return input(f"  {prompt}: ").strip()

def ask_float(prompt, default=None):
    """询问数字"""
    while True:
        val = ask(prompt, default)
        try:
            return float(val.replace(",", "").replace("¥", "").replace(" ", ""))
        except ValueError:
            print(red(f"  ⚠ 请输入数字（如 10000 或 10,000）"))

def ask_yesno(prompt, default="y"):
    """询问是/否"""
    d = "Y/n" if default == "y" else "y/N"
    val = ask(f"{prompt} ({d})", d)
    return val.lower().startswith("y") or val == ""

# ── 预设模板 ──────────────────────────────────────────
# 单一事实源：精确名称映射来自 data_processor.ANCHOR_MAP
# setup.py 优先精确匹配 ANCHOR_MAP，未命中再用关键词兜底。
FUND_GROUPS = {
    "1": {"name": "全局固收", "desc": "债券、固收+、黄金等稳健品种 → 压舱石层", "layer": "bedrock"},
    "2": {"name": "核心增长", "desc": "宽基指数、QDII、主动混合 → 核心增长层", "layer": "core"},
    "3": {"name": "进攻组合", "desc": "行业ETF、主题基金、个股 → 卫星进攻层", "layer": "sat"},
    "4": {"name": "现金预备", "desc": "余额宝、货币基金 → 现金预备层", "layer": "cash"},
}

# layer -> group 名
LAYER_TO_GROUP = {
    "bedrock": "全局固收",
    "core": "核心增长",
    "sat": "进攻组合",
    "cash": "现金预备",
}

try:
    # data_processor 位于 05-scripts/，从仓库根运行时需显式加入 path
    _scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "05-scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
    from data_processor import ANCHOR_MAP
    ANCHOR_NAME_TO_GROUP = {
        name: LAYER_TO_GROUP.get(layer_info[0], "核心增长")
        for name, layer_info in ANCHOR_MAP.items()
    }
except ImportError:
    ANCHOR_NAME_TO_GROUP = {}

FUND_TEMPLATES = {
    "债券基金": {"group": "全局固收", "note": "压舱石 — 稳定收益"},
    "黄金ETF联接": {"group": "全局固收", "note": "压舱石 — 对冲通胀"},
    "混合基金": {"group": "核心增长", "note": "核心 — 主动管理"},
    "指数增强": {"group": "核心增长", "note": "核心 — 宽基指数"},
    "纳指100": {"group": "全局QDII", "note": "核心 — 全球配置"},
    "行业ETF": {"group": "进攻组合", "note": "卫星 — 波段交易"},
    "主题基金": {"group": "进攻组合", "note": "卫星 — 风口试探"},
}

# ── 主流程 ────────────────────────────────────────────
def main():
    print()
    print(bold(blue("  ⚓ Anchor 投资管理系统 ")) + bold(f"{VERSION} — 配置向导"))
    print(cyan("  " + "─" * 50))
    print()

    # 检查是否已有数据
    data_path = "portfolio_data.json"
    if os.path.exists(data_path) and "--reset" not in sys.argv:
        existing = input(yellow("  ⚠ 已有 portfolio_data.json，是否覆盖？(y/N): "))
        if not existing.lower().startswith("y"):
            print(green("  ✓ 保留现有数据，退出。运行 --reset 可重新配置。"))
            return

    if "--demo" in sys.argv:
        generate_demo()
        return

    # ── Step 1: 基本信息 ──
    print(bold("\n  📋 Step 1/4: 基本信息"))
    today = date.today().isoformat()
    update_time = ask("配置日期", today)

    # ── Step 2: 基金持仓 ──
    print(bold("\n  📊 Step 2/4: 基金持仓"))
    print(yellow("  按提示添加你的每只基金。输入空名称结束添加。\n"))

    holdings = []
    fund_count = 0
    while True:
        print(cyan(f"  ── 基金 #{fund_count + 1} ──"))
        name = ask("  基金名称（空=结束）")
        if not name:
            if fund_count == 0:
                print(yellow("  ⚠ 至少添加一只基金"))
                continue
            break

        # 尝试自动匹配分组（优先精确匹配 ANCHOR_MAP 单一事实源，再关键词兜底）
        matched_group = None
        if name in ANCHOR_NAME_TO_GROUP:
            matched_group = {"group": ANCHOR_NAME_TO_GROUP[name], "note": "精确匹配 ANCHOR_MAP"}
        else:
            for keyword, template in FUND_TEMPLATES.items():
                if keyword in name:
                    matched_group = template
                    break

        if matched_group:
            print(green(f"  ✓ 自动识别: {matched_group['group']} — {matched_group['note']}"))
            group = ask("  分组（回车确认）", matched_group['group'])
        else:
            print(yellow("  请选择分组:"))
            for k, v in FUND_GROUPS.items():
                print(f"    [{k}] {v['name']} — {v['desc']}")
            g = ask("  分组编号", "2")
            group = FUND_GROUPS.get(g, FUND_GROUPS["2"])["name"]

        mv = ask_float("  当前市值（元）", "0")
        pnl = ask_float("  持仓盈亏（元，浮亏填负数）", "0")
        cost = ask("  成本价（元/份，可选）", "")

        holding = {
            "name": name,
            "mv": mv,
            "pnl": pnl,
            "cumul": pnl,
            "day_pnl": 0,
            "day_pct": 0,
            "group": group,
            "note": ""
        }
        if cost:
            holding["cost_basis"] = float(cost)

        holdings.append(holding)
        fund_count += 1
        print(green(f"  ✓ 已添加: {name} (¥{mv:,.0f})\n"))

    # ── Step 3: 股票持仓 ──
    print(bold("\n  📈 Step 3/4: 股票持仓（可选）"))
    print(yellow("  如有股票持仓（如 ETF、个股），在此添加。空名称跳过。\n"))

    stocks = []
    while True:
        print(cyan(f"  ── 股票 #{len(stocks) + 1} ──"))
        name = ask("  股票/ETF 名称（空=跳过）")
        if not name:
            break

        shares = ask_float("  持有股数", "0")
        cost = ask_float("  成本价（元/股）", "0")
        price = ask_float("  当前价（元/股）", cost)
        pnl = (price - cost) * shares if cost else 0

        stocks.append({
            "name": name,
            "shares": int(shares),
            "cost": cost,
            "price": price,
            "pnl": round(pnl, 2),
            "mv": round(price * shares, 2),
            "day_pnl": 0
        })
        print(green(f"  ✓ 已添加: {name} ×{int(shares)} 股，浮盈 ¥{pnl:,.0f}\n"))

    # ── Step 4: 现金 ──
    print(bold("\n  💰 Step 4/4: 现金与收尾"))
    yuebao = ask_float("  余额宝/货币基金金额", "0")

    # 计算总资产
    fund_total = sum(h["mv"] for h in holdings)
    stock_total = sum(s["mv"] for s in stocks)
    total = fund_total + stock_total + yuebao
    total_pnl = sum(h["pnl"] for h in holdings) + sum(s["pnl"] for s in stocks)

    # 检查四层比例
    bedrock_mv = sum(h["mv"] for h in holdings if h["group"] == "全局固收")
    core_mv = sum(h["mv"] for h in holdings if h["group"] in ("核心增长", "全局QDII"))
    sat_mv = sum(h["mv"] for h in holdings if h["group"] == "进攻组合") + stock_total
    cash_mv = yuebao + sum(h["mv"] for h in holdings if h["group"] == "现金预备")

    # 添加余额宝
    if yuebao > 0:
        holdings.append({
            "name": "余额宝",
            "mv": yuebao,
            "pnl": 0,
            "cumul": 0,
            "day_pnl": 0,
            "day_pct": 0,
            "group": "现金预备",
            "note": "现金预备层，仅用于暴跌补仓"
        })

    # ── 生成数据 ──
    portfolio_data = {
        "update_time": f"{today} 20:00",
        "total_assets": round(total, 2),
        "fund_account": round(fund_total, 2),
        "stock_account": round(stock_total, 2),
        "yuebao": yuebao,
        "total_hold_pnl_est": round(total_pnl, 2),
        "market": {
            "sh": {"close": 0, "change": ""},
            "kc": {"close": 0, "change": ""},
            "date": today,
            "day": "待更新",
            "note": "运行 '更新今日数据' 获取实时行情"
        },
        "holdings_summary": holdings,
        "stock_holdings": stocks,
        "dca_running": [],
        "watchlist": [],
        "pending_actions": [],
        "daily_summaries": [],
        "chart_data": [],
        "update_date": today,
        "transactions": [],
        "pending_clearance_total": 0,
        "system_version": "v3.3",
    }

    # ── 写入文件 ──
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(portfolio_data, f, ensure_ascii=False, indent=2)

    print(green(f"\n  ✅ 配置完成！已写入 {data_path}"))
    print()

    # ── 摘要 ──
    print(bold(blue("  ⚓ 配置摘要")))
    print(cyan("  " + "─" * 40))
    print(f"  总资产:    ¥{total:,.0f}")
    print(f"  基金持仓:  {fund_count} 只  (¥{fund_total - yuebao:,.0f})")
    print(f"  股票持仓:  {len(stocks)} 只   (¥{stock_total:,.0f})")
    print(f"  现金预备:  ¥{yuebao:,.0f}")
    print(f"  持仓盈亏:  ¥{total_pnl:+,.0f}")
    print()

    if total > 0:
        print(bold("  四层占比:"))
        print(f"  🛡️ 压舱石:  {bedrock_mv/total*100:5.1f}%  (目标 45%)")
        print(f"  🚀 核心增长: {core_mv/total*100:5.1f}%  (目标 20%)")
        print(f"  🔥 卫星进攻: {sat_mv/total*100:5.1f}%  (目标 20%)")
        print(f"  💰 现金预备: {cash_mv/total*100:5.1f}%  (目标 15%)")
        print()

    # ── 下一步 ──
    print(bold(green("  🎉 下一步:")))
    print(f"  {blue('1.')} 运行 {cyan('python 05-scripts/rebuild.py')} 生成看板")
    print(f"  {blue('2.')} 双击打开 {cyan('portfolio_analysis.html')} 查看")
    print(f"  {blue('3.')} 说 {cyan('更新今日数据')} 即获取实时行情")
    print()

    if not ask_yesno("  是否立即运行 rebuild.py 生成看板？", "y"):
        print(yellow("  好的，稍后手动运行即可。"))
        return

    # 运行 rebuild
    print()
    print(cyan("  🔧 正在生成看板..."))
    print()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    rebuild_path = os.path.join("05-scripts", "rebuild.py")
    if os.path.exists(rebuild_path):
        os.system(f'python "{rebuild_path}"')
    else:
        print(red(f"  ⚠ 找不到 {rebuild_path}，请手动运行"))


def generate_demo():
    """生成演示数据"""
    print(bold(blue("\n  🎬 生成演示数据...\n")))
    demo = {
        "update_time": date.today().isoformat(),
        "total_assets": 100000,
        "fund_account": 85000,
        "stock_account": 0,
        "yuebao": 15000,
        "total_hold_pnl_est": 5200,
        "market": {
            "sh": {"close": 3900, "change": "+0.57%"},
            "kc": {"close": 1701, "change": "+0.45%"},
            "date": date.today().isoformat(),
            "day": "示例",
            "note": "演示数据 — 运行 setup.py 填入你的真实持仓"
        },
        "holdings_summary": [
            {"name": "示例债券基金A", "mv": 25000, "pnl": 800, "cumul": 800, "day_pnl": 15, "day_pct": 0.0006, "group": "全局固收", "note": "压舱石 — 替换为你的债券基金"},
            {"name": "示例债券基金B", "mv": 20000, "pnl": 500, "cumul": 500, "day_pnl": 8, "day_pct": 0.0004, "group": "全局固收", "note": "压舱石 — 替换为你的固收+"},
            {"name": "示例黄金ETF联接", "mv": 5000, "pnl": 200, "cumul": 200, "day_pnl": 25, "day_pct": 0.005, "group": "全局固收", "note": "压舱石 — 替换为你的黄金"},
            {"name": "示例混合基金", "mv": 10000, "pnl": 600, "cumul": 600, "day_pnl": 30, "day_pct": 0.003, "group": "核心增长", "note": "核心 — 替换为你的主动基金"},
            {"name": "示例纳指100", "mv": 10000, "pnl": 1200, "cumul": 1200, "day_pnl": 50, "day_pct": 0.005, "group": "全局QDII", "note": "核心 — 替换为你的QDII"},
            {"name": "示例行业ETF", "mv": 8000, "pnl": -300, "cumul": -300, "day_pnl": 120, "day_pct": 0.015, "group": "进攻组合", "note": "卫星 — 替换为你的行业基金"},
            {"name": "示例主题基金", "mv": 7000, "pnl": 200, "cumul": 200, "day_pnl": -50, "day_pct": -0.007, "group": "进攻组合", "note": "卫星 — 替换为你的主题基金"},
            {"name": "余额宝", "mv": 15000, "pnl": 0, "cumul": 0, "day_pnl": 0, "day_pct": 0, "group": "现金预备", "note": "现金预备层"}
        ],
        "stock_holdings": [],
        "dca_running": ["示例定投: 纳指100 每天10元"],
        "watchlist": [
            {"rank": 1, "sector": "示例关注板块", "etf_code": "000000", "trigger": "回调X%", "amount": 1000, "status": "🟡 关注"}
        ],
        "pending_actions": [],
        "daily_summaries": [],
        "chart_data": [
            {"d": "08-01", "sh": 3800, "star": 1600, "pnl": -200},
            {"d": "08-02", "sh": 3850, "star": 1650, "pnl": 150},
            {"d": date.today().strftime("%m-%d"), "sh": 3900, "star": 1701, "pnl": 100}
        ],
        "update_date": date.today().isoformat(),
        "transactions": [],
        "pending_clearance_total": 0,
        "system_version": "v3.3",
    }
    with open("portfolio_data.json", "w", encoding="utf-8") as f:
        json.dump(demo, f, ensure_ascii=False, indent=2)
    print(green("  ✅ portfolio_data.json 已生成（演示数据）"))
    print(green("  运行 python setup.py 填入真实数据\n"))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(yellow("\n\n  ⚠ 已取消。随时重新运行 python setup.py\n"))
    except Exception as e:
        print(red(f"\n  ❌ 出错了: {e}\n"))
        print(yellow("  请截图此错误信息，在 GitHub 提 Issue:\n"))
        print("  https://github.com/killian99cm/anchor-system/issues/new\n")
