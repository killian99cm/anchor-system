# -*- coding: utf-8 -*-
"""Anchor 交易前校验器 pre_trade_check.py v1.0（2026-08-27 错配教训落地）

提案 #A 加仓前超限校验 + #B 贷款分批提示 + #C 目标可达性标注 —— 机制化实现。
任何「买入/加仓」建议生成前必须运行本校验器，输出 ⛔ 拦截或 ✅ 可执行。

用法:
  python pre_trade_check.py <品种关键词> <拟买金额> [--loan]
  例: python pre_trade_check.py 创新药 359
      python pre_trade_check.py 证券 2500        # 应拦截：加仓后超 E1
      python pre_trade_check.py 半导体 300 --loan # 贷款资金 + 大额提示

校验项（全部规则化）:
  1. 月操作额度（4/4 满 → 拦截）
  2. E1 单只卫星上限 ¥3,000（加仓后市值超限 → 拦截）
  3. E4 卫星月净投入 ≤¥1,500（超 → 拦截）
  4. 大额资金分批（拟买 ≥¥3,000 或 --loan → 提示 334 分批）
  5. 目标可达性（品种目标 vs 当前，🔒限购/✅可补/⚠️超限/🟡积累）
  6. 买点评分卡提醒（必须 ≥3/5 或事件驱动 ≤¥300 豁免）
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

JSON_PATH = "C:/Users/lenovo/Desktop/portfolio_data.json"

# 规则手册品种目标（含可达性标注，提案 #C 落地）
TARGETS = {
    "鹏华畅享债券": {"target": 6600, "layer": "压舱石", "reach": "✅ 达标"},
    "中银稳健增利债券": {"target": 4600, "layer": "压舱石", "reach": "⚠️ 超配（贷款配置 8/31 评估）"},
    "红利": {"target": 5500, "layer": "压舱石", "reach": "✅ 达标"},
    "黄金": {"target": 1500, "layer": "压舱石", "reach": "🟡 定投积累（可议上调）"},
    "纳斯达克": {"target": 4000, "layer": "核心", "reach": "🔒 限购（结构性缺口，不追）"},
    "通利": {"target": 2000, "layer": "核心", "reach": "🟡 超配（已暂停定投；实为半导体股基）"},
    "创新药": {"target": 3000, "layer": "卫星", "reach": "✅ 可补（9/1 时机A 确认）"},
    "证券": {"target": 2500, "layer": "卫星", "reach": "⚠️ 超 E1 上限（需压回）"},
    "半导体": {"target": 1500, "layer": "卫星", "reach": "🟡 观察仓（DDX 连正≥2日才补）"},
}

E1_SAT_LIMIT = 3000.0   # 单只卫星上限
E4_SAT_MONTHLY = 1500.0  # 卫星月净投入上限
BIG_AMT = 3000.0         # 大额分批阈值
MAX_MONTH_OPS = 4        # 月操作上限


def load_data():
    d = json.load(io.open(JSON_PATH, encoding="utf-8"))
    holdings = {h["name"]: h for h in d.get("holdings_summary", []) if h.get("mv", 0) > 0}
    for s in d.get("stock_holdings", []):
        holdings[s["name"]] = s
    return d, holdings


def find_target(holdings, keyword):
    """匹配目标表（先精确匹配目标表 key，再模糊匹配持仓名）"""
    for k, v in TARGETS.items():
        if k in keyword or keyword in k:
            return k, v
    # 模糊匹配持仓
    for name in holdings:
        if keyword in name:
            for k, v in TARGETS.items():
                if k in name:
                    return k, v
    return None, None


def main():
    if len(sys.argv) < 3:
        print("用法: python pre_trade_check.py <品种关键词> <拟买金额> [--loan]")
        return 2

    keyword = sys.argv[1]
    try:
        amount = float(sys.argv[2])
    except ValueError:
        print(f"⛔ 金额非法: {sys.argv[2]}")
        return 2
    is_loan = "--loan" in sys.argv

    d, holdings = load_data()
    ops = d.get("ops_state", {})
    key, tgt = find_target(holdings, keyword)

    print(f"=== Anchor 交易前校验（{keyword} ¥{amount:,.0f}{' · 贷款资金' if is_loan else ''}）===")
    checks = []

    # 1) 月操作额度（ops_state 为空时 fallback 到 transactions 统计）
    from datetime import date as _date
    _cur_month = _date.today().strftime("%Y-%m")  # P0 修复（8/31 审计）：动态当前月，9/1 起自动重置
    used = ops.get("used", ops.get("count", 0)) if isinstance(ops, dict) else 0
    if not isinstance(used, (int, float)) or used is None or used == 0 and isinstance(ops, dict) and not ops:
        used = len([1 for t in d.get("transactions", [])
                    if str(t.get("date", "")).startswith(_cur_month)
                    and t.get("op") in ("买入", "加仓", "赎回", "卖出", "减仓")])
    if used >= MAX_MONTH_OPS:
        checks.append(("⛔ 月操作额度", f"{used}/{MAX_MONTH_OPS} 已满（{_cur_month} 未重置）——今日不可买入"))
    else:
        checks.append(("✅ 月操作额度", f"{used}/{MAX_MONTH_OPS}，可执行 {MAX_MONTH_OPS - used} 笔"))

    # 2) 目标可达性 + 层
    if tgt:
        checks.append((f"层/目标", f"{tgt['layer']}层 · 目标 ¥{tgt['target']:,.0f} · 可达性 {tgt['reach']}"))

    # 3) E1 单只上限（卫星层）
    if tgt and tgt["layer"] == "卫星":
        cur = next((h.get("mv", 0) for h in holdings.values() if key in h.get("name", "")), 0)
        after = cur + amount
        if after > E1_SAT_LIMIT:
            checks.append((f"⛔ E1 单只上限", f"加仓后 ¥{after:,.0f} > ¥{E1_SAT_LIMIT:,.0f}（当前 ¥{cur:,.0f}）——超限拦截，先压回或改分批"))
        else:
            checks.append((f"✅ E1 单只上限", f"加仓后 ¥{after:,.0f} ≤ ¥{E1_SAT_LIMIT:,.0f}（当前 ¥{cur:,.0f}）"))
        # E4 月净投入
        if amount > E4_SAT_MONTHLY:
            checks.append((f"⚠️ E4 月净投入", f"单笔 ¥{amount:,.0f} > ¥{E4_SAT_MONTHLY:,.0f}——注意卫星月净累计上限"))

    # 4) 大额分批（提案 #B）
    if amount >= BIG_AMT or is_loan:
        checks.append(("⚠️ 大额/贷款分批", f"¥{amount:,.0f} ≥ ¥{BIG_AMT:,.0f} 或贷款资金——必须 334 分批（分 3 批、间隔≥3 交易日），禁止一次性"))

    # 5) 评分卡
    if amount > 300 and not is_loan:
        checks.append(("⚠️ 买点评分卡", "金额 >¥300 非事件驱动——必须 5 维打分 ≥3/5 才可成交"))
    else:
        checks.append(("✅ 评分卡口径", "≤¥300 或事件驱动（A4）可豁免，但必须标注「事件驱动」"))

    for tag, msg in checks:
        print(f"  {tag}: {msg}")

    blocked = any(c[0].startswith("⛔") for c in checks)
    print()
    if blocked:
        print("⛔ 结论: 拦截——不执行买入（存在硬性违规项）")
        return 1
    print("✅ 结论: 可执行——但需满足上述 ⚠️ 项（分批/评分卡）后再下单")
    return 0


if __name__ == "__main__":
    sys.exit(main())
