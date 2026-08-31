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
    "buy_max": 2,
    "sell_max": 2,
    "e1_sat_position_cap": 3000,
    "e4_monthly_net_cap": 1500,
    "scorecard_min": 3,
    "scorecard_max": 5,
    "event_exempt": 300,
    "four_layer": {"bedrock_pct": 40, "core_min_pct": 15, "core_max_pct": 25, "sat_pct": 30, "cash_pct": 10},
    "t3_days": 3,
    "premium_gate_pct": 3,
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
    grab("e1_sat_position_cap", [r"E1[^\n]{0,20}?([\d,，]+)\s*元", r"单只卫星[^\n]{0,8}([\d,，]+)\s*元"], lambda m: int(m.group(1).replace(",", "").replace("，", "")), DEFAULTS["e1_sat_position_cap"])
    grab("e4_monthly_net_cap", [r"E4[^\n]{0,20}?([\d,，]+)\s*元", r"卫星月净投入[^\n]{0,8}([\d,，]+)\s*元"], lambda m: int(m.group(1).replace(",", "").replace("，", "")), DEFAULTS["e4_monthly_net_cap"])
    grab("scorecard_min", [r"≥\s*([0-9])\s*/\s*([0-9])", r"([0-9])\s*分[^\n]{0,6}才可买"], lambda m: int(m.group(1)), DEFAULTS["scorecard_min"])
    grab("event_exempt", [r"事件[^\n]{0,8}([\d,，]+)\s*元", r"豁免[^\n]{0,8}([\d,，]+)\s*元"], lambda m: int(m.group(1).replace(",", "").replace("，", "")), DEFAULTS["event_exempt"])
    grab("t3_days", [r"T\+3", r"([0-9]+)\s*个交易日内复核"], lambda m: 3, DEFAULTS["t3_days"])
    grab("premium_gate_pct", [r"溢价[^\n]{0,8}([0-9]+)\s*%"], lambda m: int(m.group(1)), DEFAULTS["premium_gate_pct"])

    # 四层配比
    four = dict(DEFAULTS["four_layer"])
    m = re.search(r"压舱石[^\n]{0,10}([0-9]+)\s*%", text)
    if m:
        four["bedrock_pct"] = int(m.group(1))
    else:
        warns.append("four_layer.bedrock_pct")
    m = re.search(r"核心[^\n]{0,8}([0-9]+)\s*[-~至到]\s*([0-9]+)\s*%", text)
    if m:
        four["core_min_pct"], four["core_max_pct"] = int(m.group(1)), int(m.group(2))
    else:
        warns.append("four_layer.core")
    m = re.search(r"卫星[^\n]{0,10}([0-9]+)\s*%", text)
    if m:
        four["sat_pct"] = int(m.group(1))
    else:
        warns.append("four_layer.sat_pct")
    m = re.search(r"现金[^\n]{0,10}([0-9]+)\s*%", text)
    if m:
        four["cash_pct"] = int(m.group(1))
    else:
        warns.append("four_layer.cash_pct")
    rules["four_layer"] = four

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
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[rules] contract written: {out}")
    print(f"[rules] version={version} extracted={len(rules) - 1} keys")
    if warns:
        print(f"[rules] WARN 提取失败（使用默认值）: {', '.join(warns)}")


if __name__ == "__main__":
    main()
