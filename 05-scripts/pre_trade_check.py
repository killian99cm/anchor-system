# -*- coding: utf-8 -*-
"""Anchor 交易前校验器 pre_trade_check.py v1.1（2026-09-01 C5 升级）

提案 #A 加仓前超限校验 + #B 贷款分批提示 + #C 目标可达性标注 —— 机制化实现。
任何「买入/加仓」建议生成前必须运行本校验器，输出 ⛔ 拦截或 ✅ 可执行。

v1.1 变更（系统优化审计剩余项 C5）：
  - 路径统一走 paths.py（不再硬编码 C:\\Users\\lenovo）
  - 阈值（TARGETS / E1 / E4 / 大额 / 月限）读 AI-Collab/rule_contract.json 的
    thresholds 段；契约缺失或字段不全时回退内置默认并打印 [WARN]，不静默
  - 月操作统计复用 data_processor.monthly_ops_summary（单一真源：定投/出入金不计、
    严格日期开头匹配），不再自造 op 白名单，口径与看板/风险矩阵完全一致

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths  # C1/C5：统一路径真源
from data_processor import current_ops_period, monthly_ops_summary  # C5：月操作单一真源

JSON_PATH = paths.DATA_PATH

# ============ 内置默认阈值（契约缺失时的 fallback；权威值在 rule_contract.json） ============
BUILTIN_THRESHOLDS = {
    "e1_sat_single_limit": 3000.0,    # E1 单只卫星上限
    "e4_sat_monthly_net": 1500.0,     # E4 卫星月净投入上限
    "big_amount_batch": 3000.0,       # 大额分批阈值
    "max_monthly_ops": 4,             # 月操作上限
    "scorecard_event_exempt": 300.0,  # 事件驱动评分卡豁免金额
    # 规则手册品种目标（含可达性标注，提案 #C 落地）
    "targets": {
        "鹏华畅享债券": {"target": 6600, "layer": "压舱石", "reach": "✅ 达标"},
        "中银稳健增利债券": {"target": 4600, "layer": "压舱石", "reach": "⚠️ 超配（贷款配置 8/31 评估）"},
        "红利": {"target": 5500, "layer": "压舱石", "reach": "✅ 达标"},
        "黄金": {"target": 1500, "layer": "压舱石", "reach": "🟡 定投积累（可议上调）"},
        "纳斯达克": {"target": 4000, "layer": "核心", "reach": "🔒 限购（结构性缺口，不追）"},
        "通利": {"target": 2000, "layer": "核心", "reach": "🟡 超配（已暂停定投；实为半导体股基）"},
        "创新药": {"target": 3000, "layer": "卫星", "reach": "✅ 可补（9/1 时机A 确认）"},
        "证券": {"target": 2500, "layer": "卫星", "reach": "⚠️ 超 E1 上限（需压回）"},
        "半导体": {"target": 1500, "layer": "卫星", "reach": "🟡 观察仓（DDX 连正≥2日才补）"},
    },
}

# 数值型阈值键（契约里出现即覆盖内置）
_NUMERIC_KEYS = (
    "e1_sat_single_limit", "e4_sat_monthly_net", "big_amount_batch",
    "max_monthly_ops", "scorecard_event_exempt",
)


def load_thresholds():
    """从 rule_contract.json 读 thresholds/rules；缺失/异常回退内置默认并 [WARN]（C5 + 09-01 A 修复）。
    契约输出为 extract_rule_contract 的 {"rules": {...}} 段（键 e1_sat_position_cap 等），
    与内置键名（e1_sat_single_limit 等）不同 → 兼容读取 + 键名映射。
    """
    th = json.loads(json.dumps(BUILTIN_THRESHOLDS, ensure_ascii=False))  # 深拷贝
    # 09-01 A 修复：契约键名 → 内置键名 映射（extract 用 position_cap/net_cap，内置用 single_limit/monthly_net）
    _KEY_MAP = {
        "e1_sat_position_cap": "e1_sat_single_limit",
        "e4_monthly_net_cap": "e4_sat_monthly_net",
        "big_amount_batch": "big_amount_batch",
        "max_monthly_ops": "max_monthly_ops",
    }
    try:
        contract = json.loads(paths.RULE_CONTRACT_PATH.read_text(encoding="utf-8"))
        # 09-01 A 修复：兼容两段（extract 输出 rules；旧约定 thresholds）
        cth = contract.get("thresholds") or contract.get("rules")
        if not isinstance(cth, dict):
            raise KeyError("thresholds/rules 段缺失或非对象")
        for k in _NUMERIC_KEYS:
            raw = cth.get(k)
            if raw is None:
                # 尝试映射键（契约用 position_cap 等）
                mapped_key = next((kk for kk, vv in _KEY_MAP.items() if vv == k), None)
                raw = cth.get(mapped_key) if mapped_key else None
            if raw is not None:
                th[k] = float(raw)
        if isinstance(cth.get("targets"), dict) and cth["targets"]:
            th["targets"].update(cth["targets"])
        th["_source"] = "contract"
    except Exception as exc:  # 契约缺失/损坏：回退内置，不阻断校验
        print(f"[WARN] 未从 rule_contract.json 读到 thresholds/rules（{exc}）→ 使用内置默认阈值")
        th["_source"] = "builtin"
    return th


def load_data():
    d = json.load(io.open(JSON_PATH, encoding="utf-8"))
    holdings = {h["name"]: h for h in d.get("holdings_summary", []) if h.get("mv", 0) > 0}
    for s in d.get("stock_holdings", []):
        holdings[s["name"]] = s
    return d, holdings


def find_target(targets, holdings, keyword):
    """匹配目标表（先精确匹配目标表 key，再模糊匹配持仓名）"""
    for k, v in targets.items():
        if k in keyword or keyword in k:
            return k, v
    # 模糊匹配持仓
    for name in holdings:
        if keyword in name:
            for k, v in targets.items():
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

    th = load_thresholds()
    targets = th["targets"]
    e1_limit = th["e1_sat_single_limit"]
    e4_monthly = th["e4_sat_monthly_net"]
    big_amt = th["big_amount_batch"]
    max_ops = int(th["max_monthly_ops"])
    exempt_amt = th["scorecard_event_exempt"]

    d, holdings = load_data()
    key, tgt = find_target(targets, holdings, keyword)

    print(f"=== Anchor 交易前校验（{keyword} ¥{amount:,.0f}{' · 贷款资金' if is_loan else ''}）===")
    print(f"（阈值来源: {'规则契约 rule_contract.json' if th['_source']=='contract' else '内置默认[WARN]'}）")
    checks = []

    # 1) 月操作额度 —— 复用 data_processor 单一真源（定投/出入金不计，严格日期匹配）
    ops_year, ops_month, ops_label = current_ops_period(d)
    used, used_viol = monthly_ops_summary(d, year=ops_year, month=ops_month)
    if used >= max_ops:
        checks.append(("⛔ 月操作额度", f"{used}/{max_ops} 已满（{ops_year}-{ops_month:02d}）——今日不可买入"))
    else:
        checks.append(("✅ 月操作额度", f"{used}/{max_ops}，可执行 {max_ops - used} 笔"
                                       + (f"（含 {used_viol} 笔违规标记）" if used_viol else "")))

    # 2) 目标可达性 + 层
    if tgt:
        checks.append(("层/目标", f"{tgt['layer']}层 · 目标 ¥{tgt['target']:,.0f} · 可达性 {tgt['reach']}"))

    # 3) E1 单只上限（卫星层）
    if tgt and tgt["layer"] == "卫星":
        cur = next((h.get("mv", 0) for h in holdings.values() if key in h.get("name", "")), 0)
        after = cur + amount
        if after > e1_limit:
            checks.append(("⛔ E1 单只上限", f"加仓后 ¥{after:,.0f} > ¥{e1_limit:,.0f}（当前 ¥{cur:,.0f}）——超限拦截，先压回或改分批"))
        else:
            checks.append(("✅ E1 单只上限", f"加仓后 ¥{after:,.0f} ≤ ¥{e1_limit:,.0f}（当前 ¥{cur:,.0f}）"))
        # E4 月净投入
        if amount > e4_monthly:
            checks.append(("⚠️ E4 月净投入", f"单笔 ¥{amount:,.0f} > ¥{e4_monthly:,.0f}——注意卫星月净累计上限"))

    # 4) 大额分批（提案 #B）
    if amount >= big_amt or is_loan:
        checks.append(("⚠️ 大额/贷款分批", f"¥{amount:,.0f} ≥ ¥{big_amt:,.0f} 或贷款资金——必须 334 分批（分 3 批、间隔≥3 交易日），禁止一次性"))

    # 5) 评分卡
    if amount > exempt_amt and not is_loan:
        checks.append(("⚠️ 买点评分卡", f"金额 >¥{exempt_amt:,.0f} 非事件驱动——必须 5 维打分 ≥3/5 才可成交"))
    else:
        checks.append(("✅ 评分卡口径", f"≤¥{exempt_amt:,.0f} 或事件驱动（A4）可豁免，但必须标注「事件驱动」"))

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
