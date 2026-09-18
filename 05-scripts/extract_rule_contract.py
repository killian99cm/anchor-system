# -*- coding: utf-8 -*-
"""056-A：从规则手册自动提取结构化规则参数 → AI-Collab/rule_contract.json。

用法：python extract_rule_contract.py [--manual <路径>] [--out <路径>]
- 读取 01-rules/投资规则手册_v*.md（取最新版本），正则提取关键阈值；
- 提取失败项 → 保留内置默认值并 WARN（幂等，不阻塞）；
- 输出结构见 02-方案 2.2（rule_contract.json 由 realtime_relay --distribute 刷新）。
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULTS = {
    "stop_loss_pct": -8,
    "watch_break_line_pct": -15,
    "watch_break_ma20": True,
    "monthly_ops_max": 4,
    # v4.5.1（09-18）：原为 `buy_max`/`sell_max` —— 有默认值、**无提取正则、无消费者**，
    # 是「写对了的死键」（手册 §1.3 正文早有「买入≤2+卖出≤2」，契约却没接上，
    # 而唯一生效的门禁是 monthly_ops_max=4 一维 ⇒ **绑到了速查表的压缩转述**）。
    # 本次接上提取正则并改名与 monthly_ops_max 同族；语义见手册 §1.3 口径定义。
    "monthly_buys_max": 2,
    "monthly_sells_max": 2,
    "monthly_ops_cleanup_max": 6,
    "e1_sat_position_cap": 3000,
    "e4_monthly_net_cap": 1500,
    "scorecard_min": 3,
    "scorecard_max": 5,
    "event_exempt": 300,
    # 09-01 修复：原默认值 40/15-25/30/10 与规则手册 45/20/20/15 不符（4.3 集中度上限）
    "four_layer": {"bedrock_pct": 45, "core_min_pct": 20, "core_max_pct": 20, "sat_pct": 20, "cash_pct": 15},
    "t3_days": 3,
    "premium_gate_pct": 3,
    # 09-01 止盈 v3.6（用户拍板）：+10/+20/+35 各卖25% + 25%奔跑仓
    "take_profit": [10, 20, 35],
    # 09-01 新增：4.3 集中度上限（单只压舱石≤8000 / 核心≤4000 / 卫星≤3000 / 板块≤12000）
    "single_position_caps": {"压舱石": 8000, "核心": 4000, "卫星": 3000},
    "sector_cap": 12000,
    # 09-11 新增：附录D 执行时点规则（事故后立）
    # 场外基金 15:00 前提交方按当日净值成交；建议一律写 14:30 前（留 30 分钟缓冲）。
    # 放在这里不是为了让脚本「知道」——是为了让它可被程序读取、可被 pre_trade_check 点检。
    "otc_submit_cutoff": "15:00",
    "otc_advice_deadline": "14:30",
    "otc_confirm_days": 1,
    "otc_settle_days": 2,
    "hk_connect_cutoff": "16:00",
    "exec_time_declaration_required": True,
    # v4.5.0 新增（09-18 用户裁决消歧）：A2 追红日禁买（§2.1）＋ watchlist 右侧确认（§4.4）。
    # 背景：同一谓词「连续 2 日飘红」原本在 A2 判**禁买**、在 watchlist 判**准买**，
    # **两条不能同时为真**；且两条此前**都不在契约、不在任何门禁代码里**（grep 追红日|A2 = 空），
    # 属纯纸面纪律。本次①明确归属 A2 ②watchlist 改判据 ③把结论本身写进契约使其可被程序读取。
    # ⚠️ watchlist 右侧确认的**级别**（`E` 评估级）**刻意不提取进契约** —— 它在手册正文里以
    #    散文形式声明，无法用稳定正则锚定；强行加一个「取不到就静默用默认」的键，就是在造
    #    新的死定义（v4.4.10 已判定该类键为「该资产不会被取数」）。级别以手册 §4.4 为权威源。
    "a2_red_day_pct": 2.0,
    "a2_consecutive_red_days": 2,
    "a2_pullback_from_high_days": 5,
    "a2_pullback_from_high_pct": 2.0,
    "a2_priority_over_watchlist": True,
    "watchlist_probe_min": 300,
    "watchlist_probe_max": 500,
    "watchlist_confirm_requires_a2_pass": True,
    "watchlist_confirm_ma_period": 5,
}

# 规则手册路径（默认取 01-rules 下最新 v*）
RULES_DIR = Path(__file__).resolve().parents[1] / "01-rules"


def latest_manual() -> Path:
    candidates = sorted(RULES_DIR.glob("投资规则手册_v*.md"), key=lambda p: p.name)
    if not candidates:
        raise FileNotFoundError(f"未找到规则手册：{RULES_DIR}")
    return candidates[-1]


def extract(text: str) -> dict:
    rules: dict = {}
    warns: list[str] = []

    def grab(name, patterns, conv, default):
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                try:
                    rules[name] = conv(m)
                    return
                except (ValueError, TypeError):
                    continue
        warns.append(name)
        rules[name] = default

    grab("stop_loss_pct", [r"[-－]\s*8\s*%", r"止损[^\n]{0,12}[-－]\s*8\s*%"], lambda m: -8.0, DEFAULTS["stop_loss_pct"])
    grab("watch_break_line_pct", [r"浮亏\s*[≤≤<=]?\s*[-－]\s*15\s*%", r"[-－]\s*15\s*%\s*(或|或收盘|或跌破)"], lambda m: -15.0, DEFAULTS["watch_break_line_pct"])
    grab("monthly_ops_max", [r"月[^\n]{0,8}操作[^\n]{0,6}≤\s*([0-9]+)\s*笔", r"操作[^\n]{0,8}≤\s*([0-9]+)\s*笔"], lambda m: int(m.group(1)), DEFAULTS["monthly_ops_max"])
    # v4.5.1（09-18）：月额度**买卖两维**（手册 §1.3「正常月≤4笔（买入≤2+卖出≤2），清理月≤6笔」）。
    # 🔴 正则一律以「操作频率」为锚 —— 手册 §1.3 新增的口径定义块里也含「买入 ≤2」「卖出 ≤2」
    #    字样（散文引用），锚定后可保证取的是**定义所在行**而非正文中的引用；
    #    与 v4.4.0「E1 被非贪婪正则抓成 4」、v4.5.0「A2 ≥% 未加锚首匹配抓成 5」**同族坑**。
    _int1 = lambda m: int(m.group(1))
    grab("monthly_buys_max", [r"操作频率[^\n]{0,40}?买入\s*≤\s*([0-9]+)"], _int1, DEFAULTS["monthly_buys_max"])
    grab("monthly_sells_max", [r"操作频率[^\n]{0,40}?卖出\s*≤\s*([0-9]+)"], _int1, DEFAULTS["monthly_sells_max"])
    grab("monthly_ops_cleanup_max", [r"清理月\s*≤\s*([0-9]+)\s*笔"], _int1, DEFAULTS["monthly_ops_cleanup_max"])
    # 09-01 修复：手册用 `¥3,000**` 加粗标记，原正则要求数字后紧跟"元"导致提取失败 → 改为兼容 ¥ + 可选加粗
    _num = lambda m: int(m.group(1).replace(",", "").replace("，", ""))
    # v4.4.0 修复：原正则 `E1[^\n]{0,24}?¥?\s*([\d,，]+)` 在手册 "月限额/E1-E4/评分卡"（规则枚举行）
    # 从 E1 起非贪婪命中 "-E4" 里的 4 → 契约 e1_sat_position_cap 被误抓成 4（本应为 ¥3,000）。
    # 修复：排除 E1-… 连写（-E4 是并列枚举非规则句），并强制金额边界（单只/市值/≤/上限/¥）。
    grab("e1_sat_position_cap", [r"E1(?![-－—])\s*[^\n]{0,20}?(?:单只|市值|投入|上限|≤|<=|不超|¥)[^\n]{0,12}?¥?\s*([\d,，]+)", r"单只卫星[^\n]{0,12}?¥?\s*([\d,，]+)"], _num, DEFAULTS["e1_sat_position_cap"])
    grab("e4_monthly_net_cap", [r"E4[^\n]{0,24}?¥?\s*([\d,，]+)", r"卫星月净投入[^\n]{0,12}?¥?\s*([\d,，]+)"], _num, DEFAULTS["e4_monthly_net_cap"])
    grab("scorecard_min", [r"≥\s*([0-9])\s*/\s*([0-9])", r"([0-9])\s*分[^\n]{0,6}才可买"], lambda m: int(m.group(1)), DEFAULTS["scorecard_min"])
    grab("event_exempt", [r"事件驱动[^\n]{0,8}?¥?\s*([\d,，]+)", r"事件[^\n]{0,8}¥?\s*([\d,，]+)", r"豁免[^\n]{0,8}¥?\s*([\d,，]+)"], _num, DEFAULTS["event_exempt"])
    grab("t3_days", [r"T\+3", r"([0-9]+)\s*个交易日内复核"], lambda m: 3, DEFAULTS["t3_days"])
    grab("premium_gate_pct", [r"溢价[^\n]{0,8}([0-9]+)\s*%"], lambda m: int(m.group(1)), DEFAULTS["premium_gate_pct"])
    m_tp = re.findall(r"\+(\d{1,2})%\s*→\s*(再)?卖25%", text)
    if len(m_tp) >= 1:
        rules["take_profit"] = [int(x[0]) for x in m_tp[:3]]
        if len(m_tp) < 3:
            warns.append("take_profit 档位数不足 3")
    else:
        rules["take_profit"] = DEFAULTS["take_profit"]

    # 四层配比（09-01 修复：原正则 "压舱石[^\n]{0,10}([0-9]+)%" 误匹配波动率 2%，
    # 改为锚定 "权重XX%" 句式，默认值与手册 45/20/20/15 一致）
    four = dict(DEFAULTS["four_layer"])
    _layer_pat = {
        "bedrock_pct": r"压舱石[^\n]{0,40}?权重\s*([0-9]+)\s*%",
        "sat_pct": r"卫星[^\n]{0,40}?权重\s*([0-9]+)\s*%",
        "cash_pct": r"现金[^\n]{0,40}?权重\s*([0-9]+)\s*%",
    }
    for k, pat in _layer_pat.items():
        m = re.search(pat, text)
        if m:
            four[k] = int(m.group(1))
        else:
            warns.append(f"four_layer.{k}")
    m = re.search(r"核心[^\n]{0,40}?权重\s*([0-9]+)\s*%", text)
    if m:
        four["core_min_pct"] = four["core_max_pct"] = int(m.group(1))
    else:
        warns.append("four_layer.core")
    rules["four_layer"] = four

    # 4.3 集中度上限（单只压舱石≤8000 / 核心≤4000 / 卫星≤3000 / 板块≤12000）
    caps = dict(DEFAULTS["single_position_caps"])
    for layer in ("压舱石", "核心", "卫星"):
        m = re.search(rf"单只{layer}[^\n]{{0,16}}?¥?\s*([\d,，]+)", text)
        if m:
            caps[layer] = int(m.group(1).replace(",", "").replace("，", ""))
        else:
            warns.append(f"single_position_caps.{layer}")
    rules["single_position_caps"] = caps
    m = re.search(r"单个板块[^\n]{0,16}?¥?\s*([\d,，]+)", text)
    if m:
        rules["sector_cap"] = int(m.group(1).replace(",", "").replace("，", ""))
    else:
        rules["sector_cap"] = DEFAULTS["sector_cap"]
        warns.append("sector_cap")

    # ── 附录D 执行时点规则（09-11 事故后立）──
    # 全部锚定在附录D 独有的措辞上，避免 re.search 命中正文里的旧句而取到错值。
    grab("otc_submit_cutoff", [r"场外申赎截止\s*(\d{1,2}:\d{2})"],
         lambda m: m.group(1), DEFAULTS["otc_submit_cutoff"])
    grab("otc_advice_deadline", [r"建议钟点\s*(\d{1,2}:\d{2})"],
         lambda m: m.group(1), DEFAULTS["otc_advice_deadline"])
    grab("otc_confirm_days", [r"T\+(\d)\s*确认份额"], lambda m: int(m.group(1)), DEFAULTS["otc_confirm_days"])
    grab("otc_settle_days", [r"T\+(\d)\s*资金到账"], lambda m: int(m.group(1)), DEFAULTS["otc_settle_days"])
    grab("hk_connect_cutoff", [r"港股通截止\s*(\d{1,2}:\d{2})"],
         lambda m: m.group(1), DEFAULTS["hk_connect_cutoff"])
    # 存在性规则：不是取值，是「这条契约还在不在」——附录D 若被删/改标题，此处会 WARN
    if "禁止不可执行表述" in text:
        rules["exec_time_declaration_required"] = True
    else:
        rules["exec_time_declaration_required"] = DEFAULTS["exec_time_declaration_required"]
        warns.append("exec_time_declaration_required")

    # ── A2 追红日禁买 ＋ watchlist 右侧确认（v4.5.0 · 2026-09-18 消歧）──
    # 正则一律**加锚**（锚定 A2 条独有的「追红日禁买」措辞）：正文里「≥2%」出现多次，
    # 不锚定就会抓到别的 2%。这不是洁癖 —— v4.4.0 的 E1 就因为非贪婪正则从 "-E4" 抓走
    # 一个 4，把 3000 静默变成 4，且 extract 全程只打 WARN 不报错。
    grab("a2_red_day_pct", [r"追红日禁买[^\n]{0,40}?板块当日\s*≥\s*(\d+)\s*%"],
         lambda m: float(m.group(1)), DEFAULTS["a2_red_day_pct"])
    grab("a2_consecutive_red_days", [r"追红日禁买[^\n]{0,90}?连续\s*(\d+)\s*日飘红"],
         lambda m: int(m.group(1)), DEFAULTS["a2_consecutive_red_days"])
    m = re.search(r"自\s*(\d+)\s*日高回撤\s*≥\s*(\d+)\s*%", text)
    if m:
        rules["a2_pullback_from_high_days"] = int(m.group(1))
        rules["a2_pullback_from_high_pct"] = float(m.group(2))
    else:
        rules["a2_pullback_from_high_days"] = DEFAULTS["a2_pullback_from_high_days"]
        rules["a2_pullback_from_high_pct"] = DEFAULTS["a2_pullback_from_high_pct"]
        warns.append("a2_pullback_from_high")
    # 消歧结论本身（存在性规则，与 exec_time_declaration_required 同型）：
    # 「A2 优先于」这句若被删/被改回，此处 WARN —— 防止正文悄悄回退而契约继续声称已消歧。
    if "A2 优先于" in text:
        rules["a2_priority_over_watchlist"] = True
    else:
        rules["a2_priority_over_watchlist"] = DEFAULTS["a2_priority_over_watchlist"]
        warns.append("a2_priority_over_watchlist")
    m = re.search(r"¥\s*(\d+)\s*[-－~～]\s*(\d+)\s*试探", text)
    if m:
        rules["watchlist_probe_min"] = int(m.group(1))
        rules["watchlist_probe_max"] = int(m.group(2))
    else:
        rules["watchlist_probe_min"] = DEFAULTS["watchlist_probe_min"]
        rules["watchlist_probe_max"] = DEFAULTS["watchlist_probe_max"]
        warns.append("watchlist_probe_range")
    if "A2 不成立" in text and "收盘价 ≥ 当日 MA5" in text:
        rules["watchlist_confirm_requires_a2_pass"] = True
        rules["watchlist_confirm_ma_period"] = 5
    else:
        rules["watchlist_confirm_requires_a2_pass"] = DEFAULTS["watchlist_confirm_requires_a2_pass"]
        rules["watchlist_confirm_ma_period"] = DEFAULTS["watchlist_confirm_ma_period"]
        warns.append("watchlist_confirm")

    return rules, warns


def main() -> None:
    parser = argparse.ArgumentParser(description="提取规则契约")
    parser.add_argument("--manual", default=None)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "AI-Collab" / "rule_contract.json"))
    args = parser.parse_args()

    manual = Path(args.manual) if args.manual else latest_manual()
    text = manual.read_text(encoding="utf-8")
    rules, warns = extract(text)

    version_match = re.search(r"v(\d+(?:\.\d+)?)", manual.name)
    version = f"v{version_match.group(1)}" if version_match else "v?.?"

    contract = {
        "rule_version": version,
        "updated_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": str(manual),
        "rules": rules,
        "warns": warns,
    }
    # 09-01 修复：保留既有 data 字段（data_date/total_assets/updated/note），
    # 防止 relay 因数据 hash 未变而跳过分发时契约缺数据段
    out = Path(args.out)
    if out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
            for k in ("data_date", "total_assets", "updated", "note"):
                if k in old:
                    contract[k] = old[k]
        except Exception:
            pass
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[rules] contract written: {out}")
    print(f"[rules] version={version} extracted={len(rules) - 1} keys")
    if warns:
        print(f"[rules] WARN 提取失败（使用默认值）: {', '.join(warns)}")


if __name__ == "__main__":
    main()
