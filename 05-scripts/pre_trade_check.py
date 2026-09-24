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
  9. 🆕 节前闸门（v4.5.20）—— 手册 §4.5。**连续休市 ≥5 个自然日**的假期前**最后一个交易日**，
     **禁开新卫星仓／禁加仓**。`X` 执行级，零裁量、不复议、不顺延。
     🔴 判据源 ＝ `trading_calendar` **实算**：`(next_trading_day(d) − d).days − 1 ≥ 5`。
     ⚠️ **本项读「提交时刻」（`date.today()` / `--asof`），⛔ 不读数据日期** —— 这与
     `board_history_record`「按数据自身交易日归档」**方向相反**，故**强制打印两个日期**，
     一旦被搞混当场可见。日历不可用 ⇒ **fail-closed**（⛔ 不得按星期几心算）。
"""
import io
import json
import os
import sys
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths  # C1/C5：统一路径真源
from data_processor import current_ops_period, monthly_ops_summary  # C5：月操作单一真源

JSON_PATH = paths.DATA_PATH

import rule_keys  # v4.5.17：阈值**单一真源**（键名/正则/默认/区间/护栏全在一处）

# ============ 内置默认阈值（契约缺失时的 fallback；权威值在 rule_contract.json） ============
# 🔴 v4.5.17 结构性重构：**本表不再手写** —— 由 `rule_keys` 派生。
#
#   修复前，同一个阈值最多在**四处**各写一遍（extract 的 DEFAULTS / extract 的 grab 默认 /
#   本文件的 BUILTIN_THRESHOLDS / 契约键↔内置键的 `_KEY_MAP` 翻译层），再加手册原文是第五处。
#   2026-09-22 实发的 E4 事故（阈值被解析成 ¥1、真值 ¥1,500）正是这套结构的产物：
#   抽取器静默拿到坏值 → 覆盖这里的 1500 → **没有任何一处比对过「1500 与 1 谁合理」**。
#
#   现在：改一个阈值 ⇒ **只改 `rule_keys.py` 一行**，此处、extract、契约、护栏**全部自动跟随**；
#   越界值会被 `grab_spec` 的区间护栏当场拒收并落 `warns`（见 extract_rule_contract）。
BUILTIN_THRESHOLDS = rule_keys.pre_trade_builtins()

# 数值型阈值键（契约里出现即覆盖内置）—— **契约键名，由注册表按 `conv` 类型派生**。
# 🔴 `big_amount_batch` **不在注册表内**（无手册依据，见 `rule_keys.DEAD_NOTES`），单列。
_NUMERIC_KEYS = rule_keys.numeric_keys() + ("big_amount_batch",)

# 契约键名 → 内置键名。**只由注册表的 `internal` 字段派生**；
# 注册表里 `internal is None` 的键（四个 monthly、A2/watchlist 族）**契约键名与内置键名同名**，
# 不出现在本映射里。⇒ 原先手工维护的「翻译层」整个消失（翻译层本身就是缺陷来源）。
_KEY_MAP = {k: v for k, v in rule_keys.internal_map().items() if k != v}


def _src_of(sources: dict, ck: str) -> dict:
    """把契约侧 `sources[契约键]` 展平成**消费侧**留痕，⚠️ 但**改名** `tier`。

    🔴 v4.5.17 自曝（**被本节自己的反向断言当场抓出**）：契约的 `sources` 段自带一个
    `tier`（`anchored` / `fallback` / `sentinel` —— 说的是「**抽取器**怎么拿到这个值」），
    而我原先用 `{..., "tier": "contract", **契约侧}` 展开 ⇒ **契约侧的 tier 把消费侧的
    `tier` 覆盖掉了** ⇒ 消费侧再也答不出「这个阈值究竟来自契约还是内置」。

    两个问题看起来都叫 tier、其实问的是两件事：
      · 消费侧 `tier`       ：「值从**契约**来的，还是回退**内置**默认？」
      · 契约侧 `contract_tier`：「抽取器是**锚定**命中，还是**兜底**拿到的？」
    混用同一个键名 ⇒ 后者覆盖前者 ⇒ **我的漂移护栏因此对真契约恒亮**
    （实测：真契约下 `_sources` 里一个 `tier=contract` 都没有 ⇒ 报「全部落到 builtin」）。
    📌 这正是本仓「名字看着像，就当它是」家族 —— 而同一条护栏的注释里
      我刚引用了 v2.1 判例「永远亮着的告警会被学会忽略」。**反例当场被我自己的测试抓到。**
    """
    s = sources.get(ck) or {}
    if not isinstance(s, dict):
        return {}
    out = {k: v for k, v in s.items() if k != "tier"}
    if "tier" in s:
        out["contract_tier"] = s["tier"]
    return out


def load_thresholds():
    """从 rule_contract.json 读 rules 段；缺失/异常回退内置默认并 [WARN]（C5 + 09-01 A 修复）。

    v4.5.17 两项结构变更：
      ① 翻译层 `_KEY_MAP` **由注册表派生**（不再手工维护两份键名表）。
      ② 新增 `_sources` / `_warns` 回传 —— 让**「这个阈值是从手册哪一行来的」**成为
         可见信息。⛔ 修复前这个答案无处可查：E4 事故里没有任何人能不看源码答出
         「契约里的 1 是从哪来的」，这正是一个坏值能潜伏数天的原因。
    """
    th = json.loads(json.dumps(BUILTIN_THRESHOLDS, ensure_ascii=False))  # 深拷贝
    th["_sources"] = {}   # {内部键: 契约侧来源留痕（含手册行号）}
    th["_warns"] = []     # 阈值侧的告警（与契约 self-report 的 warns 合并展示）
    try:
        contract = json.loads(paths.RULE_CONTRACT_PATH.read_text(encoding="utf-8"))
        # 09-01 A 修复：兼容两段（extract 输出 rules；旧约定 thresholds）
        cth = contract.get("thresholds") or contract.get("rules")
        if not isinstance(cth, dict):
            raise KeyError("thresholds/rules 段缺失或非对象")
        _sources = contract.get("sources") or {}
        # ⚠️ `_NUMERIC_KEYS` 是**契约键名**；`th` / `_sources` 一律用**内部键名**索引
        #   （消费者只认内部键）。两者由注册表的 `internal` 字段单向派生 —— `_KEY_MAP`。
        for _ck in _NUMERIC_KEYS:
            _internal = _KEY_MAP.get(_ck, _ck)
            raw = cth.get(_ck)
            if raw is None:
                # 契约无此键 ⇒ 用内置默认。**这也须留痕** ——
                # 「契约里没有这个键」是发现「死定义 / 抽取器没接上」的唯一线索。
                th["_sources"][_internal] = {"contract_key": _ck, "tier": "builtin",
                                             "note": "契约无此键 ⇒ 用内置默认"}
                continue
            # 🔴 v4.5.17 第三道防线：**消费侧也验区间**
            #   抽取侧的护栏保护「契约怎么生成」；这里保护「**拿到手的契约信不信**」——
            #   若契约是旧版本、被人手工改过、或抽取器被回退，坏值仍会从这里进来。
            #   （三道防线互相独立：锚定提取 → 抽取侧区间 → 消费侧区间）
            lo, hi = rule_keys.sanity_of(_ck)
            if lo is not None and not (lo <= float(raw) <= hi):
                # ⚠️ 报「改用内置默认 X」时**必须取内部键的默认**：
                #   首版误写 `th.get(k)`（`k` 是**契约键**，如 `e4_monthly_net_cap`）⇒
                #   打印出 `改用内置默认 None`，**读数骗人**（v4.5.3 ③ 同族）。
                _fallback = BUILTIN_THRESHOLDS.get(_internal)
                th["_warns"].append(
                    f"🔴 {_internal}: 契约值 {raw!r} 越界合理区间 [{lo}, {hi}] ⇒ **拒收**，"
                    f"改用内置默认 {_fallback!r}（契约键 {_ck}）")
                # 🔴 **被拒收的键恰恰是最该留痕的那个** —— 首版在此 `continue` 掉，
                #   结果 `_sources` 里既无好值也无坏值 ⇒ **「它被拒了」这件事本身不可见**。
                th["_sources"][_internal] = {
                    **_src_of(_sources, _ck), "contract_key": _ck, "tier": "rejected",
                    "rejected_value": raw, "range": [lo, hi]}
                continue
            th[_internal] = float(raw)
            th["_sources"][_internal] = {
                **_src_of(_sources, _ck), "contract_key": _ck, "tier": "contract"}
        if isinstance(cth.get("targets"), dict) and cth["targets"]:
            th["targets"].update(cth["targets"])
        # 09-01 修复：合并契约 single_position_caps（extract 从手册 4.3 提取的权威值）
        if isinstance(cth.get("single_position_caps"), dict) and cth["single_position_caps"]:
            th["single_position_caps"].update(
                {k: float(v) for k, v in cth["single_position_caps"].items()})
        # 契约自报的提取失败，纳入本侧告警面（否则只出现在 extract 的 stdout 里，随日志滚走）
        for _w in (contract.get("warns") or []):
            th["_warns"].append(f"⚠️ 契约自报提取失败：{_w}")
        _rej = contract.get("sanity_rejected") or {}
        for _k, _v in _rej.items():
            th["_warns"].append(f"🔴 契约侧合理性拒收：{_k} = {_v.get('value')!r}"
                                f"（手册行 {_v.get('line')}）⇒ 已回退 builtin")
        th["_source"] = "contract"
        # 🔴 v4.5.17 新增：**「契约里一个数都没被认出来」不是「契约没这些键」**。
        #    本函数按**契约键名**取值，而契约由 `extract_rule_contract` 生成 —— 键名唯一。
        #    ⚠️ 改前此处有一条**反向查表兜底**（按内部名找不到就反查 `_KEY_MAP`），
        #       于是同一个阈值在契约里**有两个合法键名**；已随重构删除。
        #       删除是**收紧**，但收紧后若键名整体漂移（如契约由旧版本/手工生成），
        #       症状是**全部数值静默回退 builtin** —— 而 `tier="builtin"` 的单条留痕
        #       在 36 条里毫不起眼（v4.5.7 L2 的教训：单独看每条都正常）。
        #    ⇒ 判据很锐利：**契约存在且非空，却一个数值键都没认出来** ⇒ 那是**键名不匹配**，
        #      ⛔ 不是「契约本来就没有这些键」。两者必须长得不一样。
        _n_from_contract = sum(1 for v in th["_sources"].values()
                               if v.get("tier") == "contract")
        _n_rejected = sum(1 for v in th["_sources"].values() if v.get("tier") == "rejected")
        if _NUMERIC_KEYS and _n_from_contract == 0 and _n_rejected == 0 and cth:
            th["_warns"].append(
                f"🔴 契约**非空**（rules 段 {len(cth)} 键）却**没有任何一个数值阈值被认出**"
                f"（实查 {len(_NUMERIC_KEYS)} 个契约键，全部落到 builtin）"
                f" ⇒ 极可能是**键名整体不匹配**（契约由旧版本或手工生成？），"
                f"⛔ 这不是「契约没有这些键」—— 两种情形必须区分。"
                f"本次**全部阈值取内置默认**，契约数值**未生效**")
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


def holiday_closure(asof, min_days):
    """§4.5 节前闸门**核心判据（纯函数）**。

    返回 dict：`{"trading": bool, "next_td": date|None, "closure_days": int|None,
                "hit": bool, "naive_days": int|None}`

    🔴 **为什么必须提成纯函数**（v4.5.7 K2）：内联在 `main()` 里的逻辑**无法被断言** ——
    只能靠人眼读代码确认，而「读代码确认」在本仓已被证明抓不到同类缺陷
    （`_ib_placehold` 初版漏一行、套件抓不到，只有独立探针能抓）。
    ⇒ 判据提出来，`test_pre_trade_check.py` 才能**正面断言「怎么写是对的」＋ 反向断言
    「原来那种写法确实会错」**。⛔ 本函数**不读时钟、不读文件** —— `asof` 与 `min_days`
    一律由调用方显式传入（这正是它能被断言的前提）。

    `naive_days` ＝ **少减 1 的写法**（`(next_td − d).days`）。它**故意被算出来**，
    唯一用途是让测试能确定性地证明「那个 `−1` 是承重的，不是装饰」。
    """
    import trading_calendar as tc
    if not tc.is_trading_day(asof):
        return {"trading": False, "next_td": None, "closure_days": None,
                "hit": False, "naive_days": None}
    nxt = tc.next_trading_day(asof)
    gap = (nxt - asof).days
    closure = gap - 1          # 中间那些**完整休市**的自然日
    return {"trading": True, "next_td": nxt, "closure_days": closure,
            "hit": closure >= int(min_days), "naive_days": gap}


def _arg_date(flag):
    """读 `--flag YYYY-MM-DD` 形式的日期参数；不存在或非法返回 None。

    v4.5.20：节前闸门（§4.5）需要「**提交时刻**」这一概念，而它**不是**数据日期。
    `--asof` 存在的唯一目的是**让闸门可被测试与回溯**（⛔ 不是给人日常用的后门）——
    常规运行一律取 `date.today()`，且**所用日期必须打印出来**（见校验项 9）。
    """
    if flag not in sys.argv:
        return None
    i = sys.argv.index(flag)
    if i + 1 >= len(sys.argv):
        return None
    try:
        return date.fromisoformat(sys.argv[i + 1])
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
        # 🔴 F7 例外出口披露（裁决 #C1-21 方案 A-2 · 手册 v3.18 §1.3 ⑥ · 立单 151）
        #    背景：**F7** 规定「**状态信号**（…／**额度用尽**／…）属**枷锁** ⇒ **必须自带一条可核验的
        #    例外出口**（写明出口的判据与判据源），**否则不得单独作为最终拦截**」；违反形态 ＝
        #    「无出口的状态信号**每日复现**、永不消解 ＝ 事实上的永久禁止」。出口**早已存在**于 §2.4
        #    （全局豁免），但 §1.3 未引用、**工具未打印** ⇒ 命中 F7 违反形态（#C1-21 实测：9/24 三条
        #    候选全部只印「不可买入」、读者看不到任何出口）。
        #    ⛔ 本项**只披露、不放行**：判定仍由上面那条 ⛔ 决定（`blocked` 只看 `⛔` 前缀）。
        checks.append(("  ↳ 🔴 F7 例外出口",
                       "买入维已满属**状态信号** ⇒ 依 F7 须附**可核验出口**："
                       "**① 用户书面/语音明确指示 ＋ ② `decision_log` 留痕（记 `#XX 违规`）＋ ③ T+3 强制复盘**"
                       "（**三项须同时**；判据源＝手册 **§1.3 ⑥** ＋ **§2.4 既有豁免**）。"
                       "⚠️ 走出口 ＝ **接受违规标记**（不隐藏、不抹除）"))
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
    # 🔴 v4.5.17 修复 fail-open：原为 `if tgt:` ⇒ **表外标的静默跳过 E1**。
    #    `targets` 表是手工维护的闭集，而「表外新标的」恰恰是**约束最弱的路径**
    #    （2026-09-22 研究实测：表外新标的仅 1 道硬拦，E1/E4 双双缺席，而该路径
    #    历史 `加仓` 准确率只有 **50%**）⇒ 静默跳过＝把最该盯的路径放在护栏之外。
    #    ⇒ 改为**显式声张**：判不了就说判不了，⛔ 绝不静默当作「已通过」。
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
        else:
            checks.append((f"⚠️ 单只{layer}层上限·无阈值",
                           f"契约/内置均无「{layer}」层上限 ⇒ **本层上限未校验**（未知层名？）"))
    else:
        checks.append(("⚠️ E1 单只上限·**未校验**",
                       f"「{keyword}」**不在 targets 品种表内** ⇒ 层别未知 ⇒ "
                       f"E1 单只上限、E4 月净投入**双双未校验**。"
                       f"⛔ 这不等于「已通过」—— 表外标的须先补进 `rule_keys.TARGETS` 再下单"))

    # 4) E4 卫星月净投入（累计口径）—— 09-01 修复：原实现只查单笔，实际应按"本月卫星净投入+拟买"累计
    #
    # 🔴 v4.5.17 修复三重缺陷（2026-09-22 实发，详见 `_handoff/inbox/146`）：
    #   · 缺陷一（阈值被解析成 ¥1）已由**抽取侧锚定**＋**两道区间护栏**修掉，见 `rule_keys` /
    #     `extract_rule_contract` / 本文件 `load_thresholds` 的消费侧区间校验 —— 本函数不再参与。
    #   · 缺陷二：`tname in k` 在 `tname=''` 时 **恒真** ⇒ 两条无名 ¥2,000 记录被计入（虚增 ¥4,000）
    #     ⇒ 现要求 `tname` 非空**先于**卫星匹配，且无名记录**显式声张**。
    #   · 缺陷三：op 词表只有 `(减仓,清仓)`，导致 9 月卫星减仓（`赎回`/`赎回确认`）**完全未扣**
    #     ⇒ 分子只增不减、连正负号都相反 ⇒ 现按**三腿模型**分类（见下）。
    #
    # ── 📌 指挥端裁定（146 §3 裁定 4 要求指挥端定，⛔ 执行端不得自行决定）──
    #   `赎回` / `赎回确认` / `赎回到账` 三者关系（以 2026-09 真实数据为据）：
    #     9/02 `赎回` ¥493.54  → 9/03 `赎回到账` ¥493.54   （半导体，同额）
    #     9/02 `赎回` ¥1037.48 → 9/03 `赎回到账` ¥1037.48  （黄金，同额）
    #     9/10 `赎回` ¥3474.00 → 9/11 `赎回确认` ¥3759.25  （证券，**不同额**）
    #   ⇒ **`赎回` 是发起腿（真实资金动作）；`赎回确认`/`赎回到账` 是同一笔赎回的完成腿（记账腿）。**
    #   ⇒ **只按发起腿计减**；完成腿**不再计减**（否则同一笔赎回被扣两次）。
    #   ⇒ **偏差方向 = fail-closed**：完成腿金额可高于发起腿（证券 +¥285.25），
    #     取发起腿 ⇒ **回笼被低估 ⇒ 净投入偏高 ⇒ 闸门偏紧**。闸门偏紧是安全方向。
    #   ⇒ **孤儿完成腿**（当月无对应发起腿，如跨月赎回）⇒ **计减 ＋ 显式声张**，
    #     ⛔ 不得静默丢弃（丢了就是「只增不减」的老毛病换个位置复发）。
    #   ⚠️ 与手册 §1.3 ③ 的区别：§1.3 量的是**操作笔数**（记账腿不计「笔」）；
    #     E4 量的是**资金净投入** ⇒ 两者口径不同，⛔ **不得直接照搬 §1.3 的结论**。
    if tgt and tgt["layer"] == "卫星":
        month_prefix = f"{ops_year:04d}-{ops_month:02d}"
        _LEG_IN = ("买入", "加仓")                  # 出金腿（+）
        _LEG_OUT = ("赎回",)                        # 发起腿（−）—— 真实资金动作
        _LEG_BOOK = ("赎回确认", "赎回到账")         # 完成腿（0）—— 同一笔赎回的确认
        legs = {"in": [], "out": [], "book": []}
        no_name, unknown_ops = [], []
        for tx in d.get("transactions", []):
            if not str(tx.get("date", "")).startswith(month_prefix):
                continue
            tname = str(tx.get("name") or "")
            op = str(tx.get("op") or "")
            try:
                amt = float(tx.get("amount", 0) or 0)
            except (TypeError, ValueError):
                amt = 0.0
            # 🔴 缺陷二：空名**不得**进入卫星匹配（`"" in k` 恒真）
            if not tname:
                no_name.append((tx.get("date"), op, amt))
                continue
            sat_kw = [k for k, v in targets.items()
                      if v.get("layer") == "卫星" and (k in tname or tname in k)]
            if not sat_kw:
                continue
            # 🔴 顺序即正确性：完成腿**先判**（`赎回确认` 含子串 `赎回`，
            #    顺序一旦颠倒就会被当成发起腿再扣一次 —— v4.5.1 同族教训）
            if any(w in op for w in _LEG_BOOK):
                legs["book"].append((tx.get("date"), sat_kw[0], amt, op))
            elif any(w in op for w in _LEG_IN):
                legs["in"].append((tx.get("date"), sat_kw[0], amt, op))
            elif any(w in op for w in _LEG_OUT):
                legs["out"].append((tx.get("date"), sat_kw[0], amt, op))
            else:
                unknown_ops.append((tx.get("date"), sat_kw[0], op, amt))

        # 孤儿完成腿：当月该标的**没有发起腿** ⇒ 计减＋声张（跨月赎回的合理情形）
        _out_funds = {f for _d, f, _a, _o in legs["out"]}
        orphans = [b for b in legs["book"] if b[1] not in _out_funds]
        # 已配对的完成腿：仅作信息展示（⛔ 不参与计算）
        paired = [b for b in legs["book"] if b[1] in _out_funds]

        net_in = sum(a for _d, _f, a, _o in legs["in"])
        net_out = sum(a for _d, _f, a, _o in legs["out"]) + sum(a for _d, _f, a, _o in orphans)
        net = net_in - net_out
        after_net = net + amount
        _detail = (f"本月出金 ¥{net_in:,.2f} − 减仓回笼 ¥{net_out:,.2f}"
                   f"（拟买 ¥{amount:,.0f}）")
        if after_net > e4_monthly:
            checks.append(("⛔ E4 月净投入",
                           f"卫星月净投入 ¥{after_net:,.2f} > ¥{e4_monthly:,.0f}（{_detail}）——超限拦截"))
        else:
            checks.append(("✅ E4 月净投入",
                           f"卫星月净投入 ¥{after_net:,.2f} ≤ ¥{e4_monthly:,.0f}（{_detail}）"))
        # 明细（让「净投入」这个数**可复算** —— 修复前只报一个总数，无从对账）
        if legs["in"] or legs["out"]:
            _rows = "；".join(f"{d} {f} ¥{a:,.2f}({o})" for d, f, a, o in legs["in"] + legs["out"])
            checks.append(("📋 E4 明细", _rows))
        if paired:
            checks.append(("📋 E4 完成腿（记账腿·⛔ 不计减）",
                           "；".join(f"{d} {f} ¥{a:,.2f}({o})" for d, f, a, o in paired)
                           + " —— 已由发起腿计减，**避免同笔赎回扣两次**"))
        # 🔴 三条声张（fail-loud）
        if orphans:
            checks.append(("⚠️ E4 孤儿完成腿·已代计减",
                           "；".join(f"{d} {f} ¥{a:,.2f}({o})" for d, f, a, o in orphans)
                           + " —— 当月无对应发起腿（跨月赎回？）⇒ **按完成腿代计减**，请人工确认"))
        if no_name:
            _amt = sum(a for _d, _o, a in no_name)
            checks.append(("⚠️ E4 无名记录·**已排除**",
                           f"{len(no_name)} 条 `name` 为空的记录（合计 ¥{_amt:,.2f}，op="
                           f"{'、'.join(sorted({o for _d, o, _a in no_name}))}）"
                           f" —— **无法判定归属，已排除**。修复前 `\"\" in k` 恒真会全部计入"
                           f"（虚增 ¥4,000），⛔ 请补齐 `name` 后重跑"))
        if unknown_ops:
            checks.append(("⚠️ E4 未识别 op·**未计入**",
                           "；".join(f"{d} {f} {o!r} ¥{a:,.2f}" for d, f, o, a in unknown_ops)
                           + " —— 闭集外 op，**净投入结论不可信**，请先归类"))
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

    # 9) 节前闸门（手册 §4.5，v3.14 新增；v4.5.20 首次进契约与门禁）
    #
    # 🔴 本项读的是「**提交时刻**」，⛔ **不是数据日期** —— 这是**故意的**，
    #   且与 `gen_watchlist_status` / `board_history_record` 那条教训**方向相反**：
    #     · 那里用 `now` 是 bug（应按**数据自身交易日**归档，v4.5.7 L2 反向断言钉死）；
    #     · 这里用 `now` 是**语义本身**（闸门问的是「**现在提交，撞不撞长假**」）。
    #   ⚠️ **正因为两个方向相反、长相一样，误用风险更高** ⇒ 强制把「所用日期」印出来，
    #      并同时印出「数据日期」，让二者一旦被搞混就**当场可见**（v2.1 判例：静默即失效）。
    gate_days = int(th["holiday_gate_min_closure"])
    _asof_override = _arg_date("--asof")
    _asof = _asof_override or date.today()
    _tag_src = (f"提交时刻 {_asof}{'（--asof 覆盖）' if _asof_override else ''}"
                f"｜数据日期 {d.get('update_date', '?')}")
    try:
        # 🔴 判据**全部**来自纯函数 `holiday_closure()` —— 本处只负责渲染与分层，
        #    ⛔ 不再就地算 `(next_td − d).days − 1`（算在渲染里＝算不进测试里）。
        g = holiday_closure(_asof, gate_days)
    except ImportError:
        checks.append(("⛔ 节前闸门·未校验",
                       "`trading_calendar` 不可导入 ⇒ 日历无法实算 ⇒ fail-closed 拦截。"
                       "⛔ 不得按星期几心算近似（会把 9/25 中秋当成交易日）"))
    except Exception as e:                       # noqa: BLE001 —— CalendarUnavailable 等一律 fail-closed
        checks.append(("⛔ 节前闸门·未校验",
                       f"{type(e).__name__}: {e} ⇒ fail-closed 拦截。⛔ 不得静默跳过本项"))
    else:
        if not g["trading"]:
            checks.append(("➖ 节前闸门", f"**不适用** —— {_asof} 非交易日（{_tag_src}）"))
        elif not g["hit"]:
            checks.append(("✅ 节前闸门",
                           f"下一交易日 {g['next_td']}（连续休市 **{g['closure_days']}** 天 "
                           f"< {gate_days}）—— 非长假前最后交易日（{_tag_src}）"))
        else:
            _layer = tgt["layer"] if tgt else None
            _hit_head = (f"下一交易日 {g['next_td']}（连续休市 **{g['closure_days']}** 天 "
                         f"≥ {gate_days}）＝**长假前最后交易日**")
            if _layer is None:
                checks.append(("⛔ 节前闸门·层别未知",
                               f"{_hit_head}；而「{keyword}」**不在 targets 品种表内** ⇒ "
                               f"层别未知 ⇒ **按 fail-closed 拦截**（⛔ 不等于「已通过」，"
                               f"表外标的本就是约束最弱路径）。{_tag_src}"))
            elif _layer != "卫星":
                checks.append(("✅ 节前闸门·本层不适用",
                               f"{_hit_head}，但目标是**{_layer}层** ⇒ §4.5 只禁卫星层"
                               f"新建/加仓。{_tag_src}"))
            else:
                checks.append(("⛔ 节前闸门",
                               f"{_hit_head} ⇒ **禁开新卫星仓／禁加仓**（`X` 执行级，"
                               f"零裁量、不复议、不顺延）。⛔ 今日不可下单。{_tag_src}"))

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
