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
       [--sector-chg <板块当日涨幅%>] [--sector-prev-chg <板块前一日涨幅%>]
       [--watchlist --close <收盘价> --ma5 <MA5>]
  例: python pre_trade_check.py 创新药 359 --sector-chg 1.00 --sector-prev-chg -0.50
      python pre_trade_check.py 有色金属 300 --watchlist --close 1234.5 --ma5 1220.0 \
                                     --sector-chg 0.80 --sector-prev-chg -1.20

校验项（全部规则化）:
  1. 月操作额度（**买卖两维**，v4.5.1）—— ① **买入维**满（买入≥2）→ 拦截（**总数未满不豁免**）
     ② 总数满（≥4）→ 拦截 ③ 未识别 op / 疑似双记 → ⚠️ 声张（额度结论不可信）
     口径见手册 §1.3 v3.11「月操作额度·口径定义」。**计事件不计记录**。
  2. E1 单只卫星上限 ¥3,000（加仓后市值超限 → 拦截）
  3. E4 卫星月净投入 ≤¥1,500（超 → 拦截）
  4. 大额资金分批（拟买 ≥¥3,000 或 --loan → 提示 334 分批）
  5. 目标可达性（品种目标 vs 当前，🔒限购/✅可补/⚠️超限/🟡积累）
  6. 买点评分卡提醒（必须 ≥3/5 或事件驱动 ≤¥300 豁免）
  7. 🆕 A2 追红日禁买（v4.5.0）—— 板块当日 ≥2% 或连续 2 日飘红 → 拦截。
     ⚠️ **fail-closed**：--sector-chg / --sector-prev-chg 缺任一 → 判「无法判定」并拦截，
     **不静默放行**。A2 是 `X` 执行级条款（附录E · F2），缺数据时的正确姿态是
     「无法判定 ⇒ 不成交」，不是「无法判定 ⇒ 照买」。
  8. 🆕 watchlist 右侧确认（v4.5.0，须配 --watchlist）—— ① A2 不成立 ② 收盘 ≥ MA5。
     判据订正见手册 §4.4（原「连续 2 天飘红」判据已作废，归属 A2）。级别 `E`，
     条件成立后 T+1 日 14:30 前须出显式裁定。
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
    "max_monthly_ops": 4,             # 月操作**总数**上限
    # v4.5.1（09-18）：月额度**买卖两维**（手册 §1.3 正文「买入≤2+卖出≤2」）。
    # 🔴 修复前契约 DEFAULTS 里早有 `buy_max`/`sell_max` 但**无提取正则、无消费者**
    #    （写对了的死键），唯一生效的是上面那条一维上限 ⇒ 绑到了速查表的压缩转述。
    "monthly_buys_max": 2,            # 月操作**买入**上限
    "monthly_sells_max": 2,           # 月操作**卖出**上限
    "monthly_ops_cleanup_max": 6,     # 清理月上限
    "scorecard_event_exempt": 300.0,  # 事件驱动评分卡豁免金额
    # v4.5.0 新增（09-18 用户裁决消歧）：A2 追红日禁买 + watchlist 右侧确认
    "a2_red_day_pct": 2.0,            # A2：板块当日涨幅 ≥ 此值 = 红日，禁买
    "a2_consecutive_red_days": 2,     # A2：连续 N 日飘红 = 禁买
    "watchlist_probe_min": 300.0,     # watchlist 试探下限
    "watchlist_probe_max": 500.0,     # watchlist 试探上限
    "a2_pullback_from_high_days": 5.0,   # A2 回调条件单：自 N 日高
    "a2_pullback_from_high_pct": 2.0,    # A2 回调条件单：回撤 ≥ 此值再买
    # 09-01 修复（手册 4.3 集中度上限）：原实现只查卫星层 E1，压舱石/核心单只上限未实现
    "single_position_caps": {"压舱石": 8000.0, "核心": 4000.0, "卫星": 3000.0},
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
    # v4.5.1：月额度买卖两维（契约键名与内置键名同名，无需 _KEY_MAP 映射）
    "monthly_buys_max", "monthly_sells_max", "monthly_ops_cleanup_max",
    # v4.5.0：A2 / watchlist 四条，契约键名与内置键名同名（无需 _KEY_MAP 映射）
    "a2_red_day_pct", "a2_consecutive_red_days",
    "watchlist_probe_min", "watchlist_probe_max",
    "a2_pullback_from_high_days", "a2_pullback_from_high_pct",
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
        # 09-01 修复：合并契约 single_position_caps（extract 从手册 4.3 提取的权威值）
        if isinstance(cth.get("single_position_caps"), dict) and cth["single_position_caps"]:
            th["single_position_caps"].update(
                {k: float(v) for k, v in cth["single_position_caps"].items()})
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


def _arg_float(flag):
    """读 `--flag <number>` 形式的参数值；flag 不存在或值非法返回 None。
    v4.5.0：A2 / watchlist 判据需要外部传入板块涨幅与均线值 —— 本校验器**不自行取数**
    （取数归 fetch_public / mx-data），只做规则判定，与既有架构一致。
    """
    if flag not in sys.argv:
        return None
    i = sys.argv.index(flag)
    if i + 1 >= len(sys.argv):
        return None
    try:
        return float(sys.argv[i + 1])
    except ValueError:
        return None


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
    # v4.5.0：A2 / watchlist 判据的外部输入
    sector_chg = _arg_float("--sector-chg")
    sector_prev_chg = _arg_float("--sector-prev-chg")
    is_watchlist = "--watchlist" in sys.argv
    close_px = _arg_float("--close")
    ma5_px = _arg_float("--ma5")

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

    # 1) 月操作额度 —— 复用 data_processor 单一真源（记账腿不计，严格日期匹配）
    #    v4.5.1（09-18）：改为**二维**判定（手册 §1.3 正文「买入≤2+卖出≤2」）。
    #    🔴 修复前只判 `总数 >= 4`，存在**假阴性路径**：买入 3 笔 + 卖出 0 笔时报「3/4 可执行 1 笔」✅
    #       放行，而买入维早已超限。故本项对**买入**操作同时判「买入维」与「总数」。
    ops_year, ops_month, ops_label = current_ops_period(d)
    s = monthly_ops_summary(d, year=ops_year, month=ops_month)
    max_buys = int(th.get("monthly_buys_max", 2) or 2)
    ops_bits = f"买入 {s.buys}/{max_buys} · 卖出 {s.sells}/{s.max_sells} · 合计 {s.total}/{max_ops}"
    ops_head = f"（{ops_year}-{ops_month:02d}）"
    if s.buys >= max_buys:
        checks.append(("⛔ 月操作额度·买入维",
                       f"{ops_bits} —— 买入维已满{ops_head}，今日不可买入（**总数未满不构成豁免**）"))
    elif s.total >= max_ops:
        checks.append(("⛔ 月操作额度·总数", f"{ops_bits} —— 总数已满{ops_head}，今日不可买入"))
    else:
        checks.append(("✅ 月操作额度", f"{ops_bits}，买入维尚可执行 {max(max_buys - s.buys, 0)} 笔"
                                       + (f"（含 {s.violations} 笔违规标记）" if s.violations else "")))
    # 🔴 fail-loud 两条：额度结论**不可信**时必须声张，不得静默按「未超限」放行
    if s.has_unknown:
        checks.append(("⚠️ 月操作额度·未识别 op",
                       f"闭集外 op {list(s.unknown_ops)} —— **该 op 未被计入任何维度，额度结论不可信**，"
                       f"请先在手册 §1.3 口径定义中归类"))
    if s.has_suspect_dupes:
        _d = s.suspect_dupes[0]
        checks.append(("⚠️ 月操作额度·疑似双记",
                       f"{len(s.suspect_dupes)} 组同(日期/op/金额)多记录（如 {_d['date']} {_d['op']} "
                       f"¥{_d['amount']} × {_d['count']} 条，涉 {_d['funds']}）—— "
                       f"**额度可能虚高**，须人工确认是否同一事件"))

    # 2) 目标可达性 + 层
    if tgt:
        checks.append(("层/目标", f"{tgt['layer']}层 · 目标 ¥{tgt['target']:,.0f} · 可达性 {tgt['reach']}"))

    # 3) 单只持仓上限（手册 4.3 分层：压舱石≤8000 / 核心≤4000 / 卫星=E1≤3000）
    # 09-01 修复：原实现只查卫星层 E1，压舱石/核心单只上限漏检（9/1 鹏华超压舱石上限即实证）
    if tgt:
        layer = tgt["layer"]
        cap = th["single_position_caps"].get(layer)
        if cap:
            cur = next((h.get("mv", 0) for h in holdings.values() if key in h.get("name", "")), 0)
            after = cur + amount
            label = "E1 单只卫星上限" if layer == "卫星" else f"单只{layer}上限"
            if after > cap:
                checks.append(("⛔ " + label, f"{layer}层加仓后 ¥{after:,.0f} > ¥{cap:,.0f}（当前 ¥{cur:,.0f}）——超限拦截，先压回或改分批"))
            else:
                checks.append(("✅ " + label, f"{layer}层加仓后 ¥{after:,.0f} ≤ ¥{cap:,.0f}（当前 ¥{cur:,.0f}）"))

    # 4) E4 卫星月净投入（累计口径）—— 09-01 修复：原实现只查单笔，实际应按"本月卫星净投入+拟买"累计
    if tgt and tgt["layer"] == "卫星":
        month_prefix = f"{ops_year:04d}-{ops_month:02d}"
        net = 0.0
        for tx in d.get("transactions", []):
            if not str(tx.get("date", "")).startswith(month_prefix):
                continue
            tname = tx.get("name", "")
            sat_kw = [k for k, v in targets.items()
                      if v.get("layer") == "卫星" and (k in tname or tname in k)]
            if not sat_kw:
                continue
            op = str(tx.get("op", ""))
            try:
                amt = float(tx.get("amount", 0) or 0)
            except (TypeError, ValueError):
                amt = 0.0
            if any(w in op for w in ("买入", "加仓")):
                net += amt
            elif any(w in op for w in ("减仓", "清仓")):
                net -= amt
        after_net = net + amount
        if after_net > e4_monthly:
            checks.append(("⛔ E4 月净投入", f"卫星月净投入 ¥{after_net:,.0f} > ¥{e4_monthly:,.0f}（本月已投入 ¥{net:,.0f} + 拟买 ¥{amount:,.0f}）——超限拦截"))
        else:
            checks.append(("✅ E4 月净投入", f"卫星月净投入 ¥{after_net:,.0f} ≤ ¥{e4_monthly:,.0f}（本月已投入 ¥{net:,.0f} + 拟买 ¥{amount:,.0f}）"))

    # 5) 大额分批（提案 #B）
    if amount >= big_amt or is_loan:
        checks.append(("⚠️ 大额/贷款分批", f"¥{amount:,.0f} ≥ ¥{big_amt:,.0f} 或贷款资金——必须 334 分批（分 3 批、间隔≥3 交易日），禁止一次性"))

    # 6) 评分卡 —— 09-01 修复：贷款资金不再豁免（9/1 证券+2,000 贷款买入评分为 4/5 仍超 E1，
    #    贷款≠事件驱动，需与其他资金同样打分；原逻辑 is_loan 直接进豁免分支漏检）
    if amount > exempt_amt:
        checks.append(("⚠️ 买点评分卡", f"金额 >¥{exempt_amt:,.0f} 非事件驱动——必须 5 维打分 ≥3/5 才可成交"))
    else:
        checks.append(("✅ 评分卡口径", f"≤¥{exempt_amt:,.0f} 可豁免（A4 事件驱动），但必须标注「事件驱动」"))

    # 7) A2 追红日禁买（手册 §2.1，v3.10 加优先级；v4.5.0 首次进契约与门禁）
    #    此前 grep 追红日|红日|A2 → 空：本条**从未被任何代码实现过**，是纯纸面纪律。
    a2_pct = th["a2_red_day_pct"]
    a2_days = int(th["a2_consecutive_red_days"])
    if sector_chg is None or sector_prev_chg is None:
        _missing = [f for f, v in (("--sector-chg", sector_chg),
                                   ("--sector-prev-chg", sector_prev_chg)) if v is None]
        checks.append(("⛔ A2 未校验",
                       f"缺 {'、'.join(_missing)} —— A2 两条件（① 板块当日 ≥{a2_pct:g}% "
                       f"② 连续 {a2_days} 日飘红）**无法完整判定**。按 fail-closed 拦截，"
                       f"补传后重跑。⛔ 不得在此状态下下单。"))
    else:
        _hit = []
        if sector_chg >= a2_pct:
            _hit.append(f"板块当日 {sector_chg:+.2f}% ≥ {a2_pct:g}%（红日）")
        if sector_prev_chg > 0 and sector_chg > 0:
            _hit.append(f"连续 {a2_days} 日飘红（前日 {sector_prev_chg:+.2f}%、当日 {sector_chg:+.2f}%）")
        if _hit:
            checks.append(("⛔ A2 追红日禁买",
                           "；".join(_hit) + " —— **不成交**（`X` 执行级，零裁量）。"
                           f"改挂回调条件单（自 {th.get('a2_pullback_from_high_days', 5):g} 日高"
                           f"回撤 ≥{th.get('a2_pullback_from_high_pct', 2):g}% 再买）"))
        else:
            checks.append(("✅ A2 追红日禁买",
                           f"当日 {sector_chg:+.2f}% < {a2_pct:g}%；且非连续 {a2_days} 日飘红"
                           f"（前日 {sector_prev_chg:+.2f}%）"))

    # 8) watchlist 右侧确认（手册 §4.4，v3.10 判据订正）
    #    原判据「连续 2 天飘红」与 A2 冲突、已作废 → 新判据 ① A2 不成立 ② 收盘 ≥ MA5。
    #    仅当显式传 --watchlist 时运行（面向机会候选，非现有持仓）。
    if is_watchlist:
        wl_lo, wl_hi = th["watchlist_probe_min"], th["watchlist_probe_max"]
        if amount < wl_lo or amount > wl_hi:
            checks.append(("⛔ watchlist 额度",
                           f"¥{amount:,.0f} 超出 ¥{wl_lo:,.0f}-{wl_hi:,.0f} 试探区间"))
        else:
            checks.append(("✅ watchlist 额度", f"¥{amount:,.0f} 在 ¥{wl_lo:,.0f}-{wl_hi:,.0f} 内"))
        if close_px is None or ma5_px is None:
            _m = [f for f, v in (("--close", close_px), ("--ma5", ma5_px)) if v is None]
            checks.append(("⛔ watchlist 右侧确认",
                           f"缺 {'、'.join(_m)} —— 条件②（收盘价 ≥ 当日 MA5）无法判定，fail-closed 拦截"))
        elif close_px >= ma5_px:
            checks.append(("✅ watchlist 右侧确认",
                           f"② 收盘 {close_px:g} ≥ MA5 {ma5_px:g} 成立（① A2 须不成立，见上条）"))
        else:
            checks.append(("⛔ watchlist 右侧确认",
                           f"② 收盘 {close_px:g} < MA5 {ma5_px:g} —— 未站上短均线，条件不成立"))
        checks.append(("⏳ E 级闭环义务",
                       "本线为 `E` 评估级（附录E · F1）——条件成立后须于 **T+1 日 14:30 前**出"
                       "**显式裁定**（执行／顺延／撤销），顺延 ≤1 次，**沉默即违规**（F3/F4）"))

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
