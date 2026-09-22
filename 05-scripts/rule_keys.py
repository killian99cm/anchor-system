# -*- coding: utf-8 -*-
"""Anchor 规则阈值**单一注册表**（v4.5.17 新增 · 2026-09-22）

================================================================================
为什么存在这个文件（先读这段，再改任何阈值）
================================================================================
修复前，**同一个阈值最多在四处各写一遍**：

  ① `extract_rule_contract.py` 的 `DEFAULTS`（内置默认）
  ② 同文件 `grab(...)` 调用里的默认值（与 ① 往往字面重复）
  ③ `pre_trade_check.py` 的 `BUILTIN_THRESHOLDS`（内置默认 —— **键名还跟 ①② 不同**）
  ④ 同文件的 `_NUMERIC_KEYS` ＋ `_KEY_MAP`（契约键名 ↔ 内置键名的**翻译层**）
  而「手册里到底写的是什么」是第五处。

🔴 **2026-09-22 实发的 E4 事故，正是这套结构的产物**：
   `e4_monthly_net_cap` 用 `re.search` **全文取首匹配**，抓到了手册 §4.2.1 正文里的一句
   引用（「…现金出口被 **§1.4** 堵死」里的 `1`），而真定义在 §4.3 行 341 的 `≤¥1,500`。
   契约 `warns: []`、抽取器自报「33 keys」一切正常 ⇒
   **一个坏值静默覆盖了内置默认 `1500`，并持续生效**。
   根因不是「正则写错了」，是**没有任何一处检查过「抽出来的值合不合理」**。

本文件把「同一件事」收敛成**一行**：
  键名 / 抽取正则 / 内置默认 / 合理性区间 / 消费者键名 / 手册出处 / 是否锚定行首

⛔ **新增或修改阈值必须在此登记** —— 否则：
   · `extract_rule_contract.py` 不会提取它；
   · `pre_trade_check.py` 没有它的**合理性区间护栏**；
   · 它就是本仓反复出现的「**写对了的死键**」（v4.5.1 `buy_max`/`sell_max`）。

================================================================================
字段说明
================================================================================
  internal          `pre_trade_check.py` 内部键名（历史命名）。**二者不同处只在本表体现**
                    ⇒ `_KEY_MAP` 这种「翻译层」整个消失（翻译层本身就是缺陷来源）。
  builtin           内置默认（契约缺失/抽取失败/合理性越界时使用）
  lo / hi           合理性区间（闭区间）。越界 ⇒ **拒收 + 落 `sanity_rejected` + 落 `warns`**
  patterns          [(正则, 是否要求行首匹配), ...] —— **按序尝试**
  anchor_required   True ⇒ **不允许退回非锚定匹配**。
                    抽不到就落 builtin + 落 `warns`（fail-loud），
                    ⛔ **绝不让正文里的一句引用顶替定义**（E4 事故的正面防线）
  conv              取值方式。合法标签见 `CONV_TAGS` —— **加载期即校验**
                    （v4.5.17 自曝：`scorecard_max` 误写 `"g2"` ⇒ `_conv` 抛错被吞 ⇒
                     **表现为「正则没匹配上」**。标签写错是编程错误，不是数据缺失）
  manual            手册出处。`None` ⇒ **本仓无手册依据的内置阈值**（须显式登记，见 DEAD_NOTES）
  desc              一句话说明

================================================================================
"""
import sys

#: 合法的 `conv` 取值标签。⛔ 新增标签须同时改 `extract_rule_contract._conv()`
CONV_TAGS = frozenset({"money", "int", "float", "g2int", "g2float", "text", "bool"})

# ══════════════════════════════════════════════════════════════════════════════
# 标量阈值（契约 `rules.<key>` ↔ `pre_trade_check` 内部键）
# ══════════════════════════════════════════════════════════════════════════════

#: 行首锚的前缀：允许的行首标记（缩进 / 列表项）。⛔ 故意**不含** `>`（引用块）
#: —— E4 事故里那句干扰文本正是以 `> ` 开头的引用块正文，排除它是修复的一半。
_LS = r"^[ \t]*(?:[-*][ \t]+)?"
LINE_START = _LS   #: 公开别名（`extract_rule_contract` 复用；⛔ 不得在别处另立一份）

SCALAR_KEYS = {

    # ── 止损 / 观察仓破位线 ─────────────────────────────────────────────
    "stop_loss_pct": dict(
        internal=None, builtin=-8.0, lo=-100, hi=-0.1, conv="const:-8.0",
        patterns=[(r"[-－]\s*8\s*%", False), (r"止损[^\n]{0,12}[-－]\s*8\s*%", False)],
        anchor_required=False, manual="§3 交易纪律（止损 -8%）",
        desc="单只止损线（%）"),

    "watch_break_line_pct": dict(
        internal=None, builtin=-15.0, lo=-100, hi=-0.1, conv="const:-15.0",
        patterns=[(r"浮亏\s*[≤≤<=]?\s*[-－]\s*15\s*%", False),
                  (r"[-－]\s*15\s*%\s*(或|或收盘|或跌破)", False)],
        anchor_required=False, manual="§2.2 B5 观察仓破位线",
        desc="观察仓破位浮亏线（%）"),

    # ── 月操作额度（§1.3 · v3.11 口径定义；权威定义行 = 手册行 57「操作频率：…」）──
    "monthly_ops_max": dict(
        internal="max_monthly_ops", builtin=4, lo=1, hi=24, conv="int",
        patterns=[(_LS + r"\*{0,2}操作频率[^\n]{0,40}?≤\s*([0-9]+)\s*笔", True),
                  (r"月[^\n]{0,8}操作[^\n]{0,6}≤\s*([0-9]+)\s*笔", False),
                  (r"操作[^\n]{0,8}≤\s*([0-9]+)\s*笔", False)],
        anchor_required=True, manual="§1.3（行 57）",
        desc="月操作**总数**上限（正常月）"),

    "monthly_buys_max": dict(
        internal="monthly_buys_max", builtin=2, lo=1, hi=24, conv="int",
        patterns=[(_LS + r"\*{0,2}操作频率[^\n]{0,40}?买入\s*≤\s*([0-9]+)", True)],
        anchor_required=True, manual="§1.3（行 57）",
        desc="月操作**买入维**上限"),

    "monthly_sells_max": dict(
        internal="monthly_sells_max", builtin=2, lo=1, hi=24, conv="int",
        patterns=[(_LS + r"\*{0,2}操作频率[^\n]{0,40}?卖出\s*≤\s*([0-9]+)", True)],
        anchor_required=True, manual="§1.3（行 57）",
        desc="月操作**卖出维**上限"),

    "monthly_ops_cleanup_max": dict(
        internal="monthly_ops_cleanup_max", builtin=6, lo=1, hi=24, conv="int",
        patterns=[(_LS + r"\*{0,2}操作频率[^\n]{0,60}?清理月\s*≤\s*([0-9]+)\s*笔", True),
                  (r"清理月\s*≤\s*([0-9]+)\s*笔", False)],
        anchor_required=True, manual="§1.3（行 57）",
        desc="月操作上限（清理月）"),

    # ── E1 / E4 卫星闸门（§4.3）──────────────────────────────────────────
    # 🔴 E4 是本表的「起因键」：修复前全文首匹配 ⇒ 抓到行 301 的 `§1.4` → 阈值 `1`。
    #    现改为**行首锚定 + 合理区间双保险**：
    #      锚定  → 正文引用（行 301 以 `> 全部撞上…` 开头）永远不可能匹配
    #      区间  → 即使锚定被后人改坏，`1 < lo(=100)` 也会当场拒收并落 warns
    "e1_sat_position_cap": dict(
        internal="e1_sat_single_limit", builtin=3000, lo=100, hi=500000, conv="money",
        patterns=[(_LS + r"\*{0,2}E1[ \t]+单只卫星[^\n]{0,12}?¥?\s*([\d,，]+)", True),
                  (r"E1(?![-－—])\s*[^\n]{0,20}?(?:单只|市值|投入|上限|≤|<=|不超|¥)[^\n]{0,12}?¥?\s*([\d,，]+)", False),
                  (r"单只卫星[^\n]{0,12}?¥?\s*([\d,，]+)", False)],
        anchor_required=True, manual="§4.3（行 338）",
        desc="E1 单只卫星市值上限"),

    "e4_monthly_net_cap": dict(
        internal="e4_sat_monthly_net", builtin=1500, lo=100, hi=500000, conv="money",
        patterns=[(_LS + r"\*{0,2}E4[ \t]+卫星月净投入[^\n]{0,12}?¥?\s*([\d,，]+)", True),
                  (r"卫星月净投入[^\n]{0,12}?¥?\s*([\d,，]+)", False)],
        anchor_required=True, manual="§4.3（行 341）",
        desc="E4 卫星层月净投入上限"),

    # ── 评分卡（§2.1 行 103）─────────────────────────────────────────────
    # v4.5.17：`scorecard_max` 此前在 DEFAULTS 里**有默认值、无提取正则** ⇒ 手册无处取，
    #   而 `Anchor-Software/app/.../report_service.py:551` **一直在读它**
    #   （`rules.get('scorecard_max', 5)`）⇒ **软件永远拿到兜底 5**。
    #   属「写了没人接」的镜像形态：**有人接、但写的人从没写过**。本次接上提取。
    "scorecard_min": dict(
        internal=None, builtin=3, lo=1, hi=10, conv="int",
        patterns=[(_LS + r"\*{0,2}买点评分卡[^\n]{0,40}?≥\s*([0-9])\s*/\s*[0-9]", True),
                  (r"≥\s*([0-9])\s*/\s*([0-9])", False),
                  (r"([0-9])\s*分[^\n]{0,6}才可买", False)],
        anchor_required=True, manual="§2.1（行 103）",
        desc="买点评分卡通过门槛（分子）"),

    "scorecard_max": dict(
        internal=None, builtin=5, lo=2, hi=10, conv="int",
        patterns=[(_LS + r"\*{0,2}买点评分卡[^\n]{0,40}?≥\s*[0-9]\s*/\s*([0-9])", True)],
        anchor_required=True, manual="§2.1（行 103）",
        desc="买点评分卡维度总数（分母）—— 消费者在软件侧 report_service.py"),

    # ── 事件驱动豁免（§2.1 A4 行 121）────────────────────────────────────
    "event_exempt": dict(
        internal="scorecard_event_exempt", builtin=300, lo=10, hi=100000, conv="money",
        patterns=[(_LS + r"\*{0,2}事件驱动\s*≤\s*¥?\s*([\d,，]+)", True),
                  (r"事件驱动[^\n]{0,8}?¥?\s*([\d,，]+)", False),
                  (r"事件[^\n]{0,8}¥?\s*([\d,，]+)", False),
                  (r"豁免[^\n]{0,8}¥?\s*([\d,，]+)", False)],
        anchor_required=True, manual="§2.1 A4（行 121）",
        desc="事件驱动试探仓金额上限（评分卡豁免线）"),

    # ── 纳指 ETF 溢价门槛 ────────────────────────────────────────────────
    "premium_gate_pct": dict(
        internal=None, builtin=3, lo=0.1, hi=50, conv="int",
        patterns=[(_LS + r"(?:\[[ xX]?\][ \t]*)?纳指ETF溢价[^\n]{0,8}?([0-9]+)\s*%", True),
                  (r"溢价[^\n]{0,8}([0-9]+)\s*%", False)],
        anchor_required=True, manual="§5 持仓检查清单 / §7 速查（行 417）",
        desc="纳指 ETF 建仓溢价率门槛（%）"),

    # ── 集中度上限（§4.3 表格 行 319-322）────────────────────────────────
    "sector_cap": dict(
        internal=None, builtin=12000, lo=1000, hi=10 ** 7, conv="money",
        patterns=[(_LS + r"\|[ \t]*单个板块[ \t]*\|[ \t]*≤?\s*¥?\s*([\d,，]+)", True),
                  (r"单个板块[^\n]{0,16}?¥?\s*([\d,，]+)", False)],
        anchor_required=True, manual="§4.3（行 322）",
        desc="单个板块集中度上限"),

    # ── T+3 复盘（附录E ／ §6 复盘体系）─────────────────────────────────
    "t3_days": dict(
        internal=None, builtin=3, lo=1, hi=10, conv="const:3",
        patterns=[(r"T\+3", False), (r"([0-9]+)\s*个交易日内复核", False)],
        anchor_required=False, manual="附录E F3（T+1 14:30）／§6 T+3 复盘",
        desc="复盘周期（交易日数）"),

    # ── 附录D 执行时点（T 系列）──────────────────────────────────────────
    "otc_submit_cutoff": dict(
        internal=None, builtin="15:00", lo=None, hi=None, conv="text",
        patterns=[(r"场外申赎截止\s*(\d{1,2}:\d{2})", False)],
        anchor_required=False, manual="附录D",
        desc="场外申赎当日截止钟点"),

    "otc_advice_deadline": dict(
        internal=None, builtin="14:30", lo=None, hi=None, conv="text",
        patterns=[(r"建议钟点\s*(\d{1,2}:\d{2})", False)],
        anchor_required=False, manual="附录D",
        desc="建议钟点（留 30 分钟缓冲）"),

    "otc_confirm_days": dict(
        internal=None, builtin=1, lo=0, hi=10, conv="int",
        patterns=[(r"T\+(\d)\s*确认份额", False)],
        anchor_required=False, manual="附录D",
        desc="场外确认份额 T+N"),

    "otc_settle_days": dict(
        internal=None, builtin=2, lo=0, hi=10, conv="int",
        patterns=[(r"T\+(\d)\s*资金到账", False)],
        anchor_required=False, manual="附录D",
        desc="场外资金到账 T+N"),

    "hk_connect_cutoff": dict(
        internal=None, builtin="16:00", lo=None, hi=None, conv="text",
        patterns=[(r"港股通截止\s*(\d{1,2}:\d{2})", False)],
        anchor_required=False, manual="附录D",
        desc="港股通截止钟点"),

    # ── A2 追红日禁买（§2.1 · v3.10 加优先级）──────────────────────────
    # 正则已锚定 A2 条独有措辞「追红日禁买」——正文里「≥2%」出现多次，不锚定会抓错。
    "a2_red_day_pct": dict(
        internal="a2_red_day_pct", builtin=2.0, lo=0.1, hi=20, conv="float",
        patterns=[(r"追红日禁买[^\n]{0,40}?板块当日\s*≥\s*([0-9.]+)\s*%", False)],
        anchor_required=False, manual="§2.1 A2",
        desc="A2 红日阈值（板块当日涨幅 %）"),

    "a2_consecutive_red_days": dict(
        internal="a2_consecutive_red_days", builtin=2, lo=2, hi=20, conv="int",
        patterns=[(r"追红日禁买[^\n]{0,90}?连续\s*(\d+)\s*日飘红", False)],
        anchor_required=False, manual="§2.1 A2",
        desc="A2 连续飘红天数阈值"),

    "a2_pullback_from_high_days": dict(
        internal="a2_pullback_from_high_days", builtin=5, lo=1, hi=120, conv="int",
        patterns=[(r"自\s*(\d+)\s*日高回撤\s*≥\s*(\d+)\s*%", False)],
        anchor_required=False, manual="§2.1 A2",
        desc="A2 回调条件单：自 N 日高"),

    "a2_pullback_from_high_pct": dict(
        # 与 `..._from_high_days` **共用同一条正则**（`自 N 日高回撤 ≥ M%`）：days 取组1、pct 取组2
        internal="a2_pullback_from_high_pct", builtin=2.0, lo=0.1, hi=50, conv="g2float",
        patterns=[(r"自\s*(\d+)\s*日高回撤\s*≥\s*(\d+)\s*%", False)],
        anchor_required=False, manual="§2.1 A2",
        desc="A2 回调条件单：回撤 ≥ 此百分比"),

    # ── watchlist 右侧确认（§4.4 · v3.10 判据订正）─────────────────────
    "watchlist_probe_min": dict(
        internal="watchlist_probe_min", builtin=300, lo=10, hi=100000, conv="int",
        patterns=[(r"¥\s*(\d+)\s*[-－~～]\s*(\d+)\s*试探", False)],
        anchor_required=False, manual="§4.4",
        desc="watchlist 试探下限"),

    "watchlist_probe_max": dict(
        # 与 `..._min` 共用同一条正则（`¥A-B 试探`）：min 取组1、max 取组2
        internal="watchlist_probe_max", builtin=500, lo=10, hi=100000, conv="g2int",
        patterns=[(r"¥\s*(\d+)\s*[-－~～]\s*(\d+)\s*试探", False)],
        anchor_required=False, manual="§4.4",
        desc="watchlist 试探上限"),

}

#: 存在性规则 / 文本型规则（不是「取值」，是「这条契约还在不在」）
EXISTENCE_KEYS = {
    "exec_time_declaration_required": dict(
        internal=None, builtin=True, sentinel="禁止不可执行表述",
        manual="附录D", desc="附录D 执行时点规则存在性"),
    "a2_priority_over_watchlist": dict(
        internal=None, builtin=True, sentinel="A2 优先于",
        manual="§2.1", desc="A2 优先于一切「右侧确认」类买入条件（消歧结论存在性）"),
    "watchlist_confirm_requires_a2_pass": dict(
        internal=None, builtin=True, sentinel="A2 不成立",
        manual="§4.4", desc="watchlist 右侧确认须先过 A2（消歧结论存在性）"),

    # v4.5.17 迁入：原在 SCALAR_KEYS 里 `patterns=[]` ⇒ **每轮必报「提取未命中」**
    #   （一条永远亮着的告警，v2.1 判例所禁）。它本来就是**哨兵型**键：
    #   周期 5 不是「从手册某个数字抽出来的」，而是**规则措辞存在时即为 5** ——
    #   与旧实现（`"A2 不成立" in text and "收盘价 ≥ 当日 MA5" in text`）语义一致。
    #   故改用 `sentinel` ＋ `value=5`，**规则措辞消失时照样告警**，措辞在则静默通过。
    "watchlist_confirm_ma_period": dict(
        internal=None, builtin=5, sentinel="收盘价 ≥ 当日 MA5", value=5,
        manual="§4.4", desc="右侧确认所用均线周期（措辞存在即为 5）"),
}

#: 结构化 / 表格型内置值（抽取逻辑在 extract_rule_contract 内单独实现）
STRUCTURED_BUILTINS = {
    "four_layer": {"bedrock_pct": 45, "core_min_pct": 20, "core_max_pct": 20,
                   "sat_pct": 20, "cash_pct": 15},
    "single_position_caps": {"压舱石": 8000, "核心": 4000, "卫星": 3000},
    "take_profit": [10, 20, 35],
    "a2_prev_day_cache": "board_pct_history.json",
    "watchlist_confirm_ma_includes_today": True,
}

#: 结构化键的合理性区间（逐项）
STRUCTURED_RANGES = {
    "single_position_caps": (100, 500000),
    "sector_cap": (1000, 10 ** 7),
}

# ══════════════════════════════════════════════════════════════════════════════
# 无手册依据 / 无消费者的内置阈值 —— **显式登记，不静默留着**
# ══════════════════════════════════════════════════════════════════════════════
DEAD_NOTES = {
    "big_amount_batch": (
        3000.0, "pre_trade_check 内置独有",
        "手册只有「334 分批法」的方法描述（§2.1 行 91），**没有任何一处写「≥¥3,000 须分批」**"
        "⇒ 本阈值**无手册依据**，且契约里也不存在该键（`_KEY_MAP` 里那条是恒等映射的死映射）。"
        "⚠️ 现状＝一个无出处的数字在当规则用（本仓「把没有定义的数当事实引用」同族）。"
        "登记于此，⛔ 不得据此声称「手册规定 ¥3,000 分批」。"),

    "watch_break_ma20": (
        True, "extract_rule_contract.DEFAULTS 独有",
        "🔴 三重死键：手册有该规则（§2.2 B5「或收盘跌破 MA20」行 133）"
        "／DEFAULTS 有默认值／**无提取正则、契约中不存在该键、全仓无消费者**。"
        "v4.5.1 清理过同型的 `buy_max`/`sell_max`。本次**保留但登记**——"
        "B5 是 `X` 执行级条款（附录E §二），其 MA20 分支**当前无任何程序载体**。"),

    "scorecard_max": (
        5, "**已修复**（v4.5.17 接入提取）",
        "修复前：软件 `report_service.py:551` 一直在读 `rules.get('scorecard_max', 5)`，"
        "而抽取器**从无该键的正则** ⇒ 软件永远拿到兜底 5。本次接入提取（见 SCALAR_KEYS）。"),

    "targets": (
        None, "pre_trade_check 独有（不进契约）",
        "品种目标市值表，非契约规则。⚠️ 与 §4.3 E1 的关系见 TARGETS 表头注释（#C1-12 倒挂）。"),
}

# ══════════════════════════════════════════════════════════════════════════════
# 品种目标表（原在 pre_trade_check.BUILTIN_THRESHOLDS["targets"]）
# ══════════════════════════════════════════════════════════════════════════════
# 🔴 **维护提醒（#C1-12 · 2026-09-22 待裁决）**：
#    §1.3 给「创新药」的目标市值 **¥3,000** 与 §4.3 的 **E1 单只卫星上限 ¥3,000 完全相等**
#    ⇒ **达标即永久无法加仓**（`current + amount > cap` 恒真）。
#    这不是笔误，是**参数标定问题**：目标与上限用了同一个数。
#    ⛔ 改动方向属**松绑类**，须用户裁决后才能动（登记表 §六 #C1-12）。
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

# ══════════════════════════════════════════════════════════════════════════════
# 派生视图（**唯一真源 → 各消费者**；⛔ 下游不得再各自维护一份）
# ══════════════════════════════════════════════════════════════════════════════


def defaults() -> dict:
    """标量键的内置默认 `{契约键: 值}`（`extract_rule_contract.DEFAULTS` 由此派生）。"""
    d = {k: v["builtin"] for k, v in SCALAR_KEYS.items()}
    d.update({k: v["builtin"] for k, v in EXISTENCE_KEYS.items()})
    d.update({k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
              for k, v in STRUCTURED_BUILTINS.items()})
    return d


def internal_map() -> dict:
    """`{契约键: pre_trade_check 内部键}` —— 取代 `pre_trade_check._KEY_MAP` 翻译层。"""
    return {k: v["internal"] for k, v in SCALAR_KEYS.items() if v.get("internal")}


#: 数值型 `conv` 标签（可以被 `float()` 消费）。其余（`text` / `bool` / `const:`）不是。
NUMERIC_CONV = frozenset({"money", "int", "float", "g2int", "g2float"})


def numeric_keys() -> tuple:
    """`pre_trade_check` **能按数值消费**的契约键。

    🔴 v4.5.17 自曝：首版把 `tuple(SCALAR_KEYS)` **整表**当数值键喂给 `float()`，
    而表里含 `otc_submit_cutoff="15:00"` 这类**时刻字符串** ⇒ `float("15:00")` 抛错
    ⇒ **整个契约读取中断、静默回退全内置**（E4 的拒收逻辑当场白做）。
    ⇒ **「契约里有这个键」≠「这个键是个数」** —— 消费侧必须按类型分流，
    这正是本仓「名字/形状看着像，就当它是」家族的又一例。
    """
    return tuple(k for k, v in SCALAR_KEYS.items() if v.get("conv") in NUMERIC_CONV)



def pre_trade_builtins() -> dict:
    """`{pre_trade_check 内部键: 内置默认}`（原 `BUILTIN_THRESHOLDS` 的标量部分）。"""
    out = {}
    for k, v in SCALAR_KEYS.items():
        if v.get("internal"):
            out[v["internal"]] = v["builtin"]
    for k, (val, _src, _note) in DEAD_NOTES.items():
        if val is not None and k == "big_amount_batch":
            out[k] = val          # 无契约键、无手册依据，只在 pre_trade_check 内生效
    out["single_position_caps"] = dict(STRUCTURED_BUILTINS["single_position_caps"])
    out["targets"] = {k: dict(v) for k, v in TARGETS.items()}
    return out


def sanity_of(key):
    """返回 `(lo, hi)`；该键无区间约束时返回 `(None, None)`。"""
    if key in SCALAR_KEYS:
        return SCALAR_KEYS[key].get("lo"), SCALAR_KEYS[key].get("hi")
    if key == "sector_cap":
        return STRUCTURED_RANGES["sector_cap"]
    if key in STRUCTURED_RANGES:
        return STRUCTURED_RANGES[key]
    return None, None


def validate() -> list:
    """**加载期校验**（`extract_rule_contract` 导入后立即调用）。

    与「正则没匹配上」**必须区分开**：这里查的全是**编程错误**，不是数据缺失。
    ⇒ 返回错误清单**且调用方须抛错**（fail-loud），⛔ 不得降级为 warn 继续跑。

    查三件：
      ① `conv` 标签是否在 `CONV_TAGS` 内（v4.5.17 自曝的 `"g2"` 病）
      ② `anchor_required=True` 的键**是否真的有锚定模式**（否则永远抽不到）
      ③ `lo > hi` / `builtin` 落在区间外（自相矛盾的登记）
    """
    errs = []
    for name, spec in {**SCALAR_KEYS, **EXISTENCE_KEYS}.items():
        conv = spec.get("conv")
        if conv and conv not in CONV_TAGS and not str(conv).startswith("const:"):
            errs.append(f"{name}: conv={conv!r} 不在 CONV_TAGS {sorted(CONV_TAGS)}")
        pats = spec.get("patterns") or []
        if spec.get("anchor_required") and not any(a for _p, a in pats):
            errs.append(f"{name}: anchor_required=True 却没有任何锚定模式（永远抽不到）")
        lo, hi = spec.get("lo"), spec.get("hi")
        if lo is not None and hi is not None:
            if lo > hi:
                errs.append(f"{name}: 区间倒挂 lo={lo} > hi={hi}")
            b = spec.get("builtin")
            if isinstance(b, (int, float)) and not (lo <= b <= hi):
                errs.append(f"{name}: builtin={b} 落在自身区间 [{lo}, {hi}] 之外")
    return errs


def audit() -> int:
    """`python rule_keys.py --audit` —— 注册表自检（供人工维护时随时跑）。"""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    d = defaults()
    print("=" * 78)
    print("Anchor 规则阈值注册表 · 自检")
    print("=" * 78)
    print(f"标量键 {len(SCALAR_KEYS)} · 存在性键 {len(EXISTENCE_KEYS)} "
          f"· 结构化键 {len(STRUCTURED_BUILTINS)} · 合计登记 {len(d)} 键")
    print()
    _errs = validate()
    print(f"【加载期校验（编程错误）】{'✅ 无' if not _errs else '🔴 ' + str(len(_errs)) + ' 项'}")
    for e in _errs:
        print(f"   - {e}")
    print()

    anchored = [k for k, v in SCALAR_KEYS.items() if v.get("anchor_required")]
    print(f"【锚定行首 · 不许退回全文匹配】{len(anchored)} 键：")
    for k in sorted(anchored):
        print(f"   - {k:34s} builtin={SCALAR_KEYS[k]['builtin']!r:>10}  "
              f"区间=[{SCALAR_KEYS[k]['lo']}, {SCALAR_KEYS[k]['hi']}]  "
              f"出处={SCALAR_KEYS[k]['manual']}")
    print()

    print("【无手册依据 / 无消费者 —— 显式登记】")
    for k, (val, src, note) in DEAD_NOTES.items():
        print(f"   - {k}（{src}）")
        print(f"     {note}")
    print()

    missing = [k for k, v in SCALAR_KEYS.items()
               if v.get("lo") is None and v.get("conv") not in ("text", "bool")]
    print(f"【缺合理性区间】{'无' if not missing else '、'.join(missing)}")
    print()

    # E1/E4 交叉检查：目标 == 上限 的倒挂（#C1-12）
    e1 = SCALAR_KEYS["e1_sat_position_cap"]["builtin"]
    over = [(k, v["target"]) for k, v in TARGETS.items()
            if v["layer"] == "卫星" and v["target"] >= e1]
    print(f"【目标 ≥ 单只卫星上限（达标即无法加仓 · #C1-12）】E1={e1}")
    for k, t in over:
        print(f"   - {k}：目标 ¥{t:,} ≥ 上限 ¥{e1:,}")
    print()
    return 0


if __name__ == "__main__":
    if "--audit" in sys.argv:
        sys.exit(audit())
    print(__doc__)
    sys.exit(0)
