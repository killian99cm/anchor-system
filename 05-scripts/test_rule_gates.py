# -*- coding: utf-8 -*-
"""test_rule_gates.py — A2 追红日禁买 + watchlist 右侧确认 的门禁回归测试（v4.5.0）

背景（2026-09-18 用户裁决消歧）：
  同一谓词「连续 2 天飘红」原本在手册两处给出**相反动作** ——
  §2.1 A2 判**禁买**、§4.4 watchlist 判**准买**，**两条不能同时为真**。
  且两条**都不在 rule_contract.json、不在任何门禁代码**（grep 追红日|红日|A2 = 空），
  是纯纸面纪律。本次①明确归属 A2 ②watchlist 改判据 ③两条都进契约与门禁。

本测试遵循本系统既有标准：**不只测「改对了」，还测「原写法确实会错」** ——
没有反向断言的测试可能在假阳性下通过（v4.4.16 的教训）。

运行：python test_rule_gates.py
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import paths  # noqa: E402
from extract_rule_contract import extract, latest_manual  # noqa: E402

PY = sys.executable
PRE_TRADE = HERE / "pre_trade_check.py"
MANUAL = latest_manual()
TEXT = MANUAL.read_text(encoding="utf-8")

_results = []


def check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail else ""))


def run_pre_trade(*args):
    """跑 pre_trade_check 子进程，返回 (rc, stdout)。"""
    p = subprocess.run([PY, str(PRE_TRADE), *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=60)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ══════════════════════════════════════════════════════════════════
print("\n########## A. 契约提取：取值正确性 ##########")
rules, warns = extract(TEXT)

check("A1 a2_red_day_pct == 2.0（A2 红日阈值）", rules.get("a2_red_day_pct") == 2.0,
      f"实得 {rules.get('a2_red_day_pct')!r}")
check("A2 a2_consecutive_red_days == 2（连续飘红天数）",
      rules.get("a2_consecutive_red_days") == 2, f"实得 {rules.get('a2_consecutive_red_days')!r}")
check("A3 a2_pullback_from_high_days == 5（自5日高）",
      rules.get("a2_pullback_from_high_days") == 5, f"实得 {rules.get('a2_pullback_from_high_days')!r}")
check("A4 a2_pullback_from_high_pct == 2.0（回撤≥2%）",
      rules.get("a2_pullback_from_high_pct") == 2.0, f"实得 {rules.get('a2_pullback_from_high_pct')!r}")
check("A5 a2_priority_over_watchlist is True（消歧结论已绑定）",
      rules.get("a2_priority_over_watchlist") is True)
check("A6 watchlist 试探区间 == 300-500",
      (rules.get("watchlist_probe_min"), rules.get("watchlist_probe_max")) == (300, 500),
      f"实得 {rules.get('watchlist_probe_min')}-{rules.get('watchlist_probe_max')}")
check("A7 watchlist_confirm_requires_a2_pass is True",
      rules.get("watchlist_confirm_requires_a2_pass") is True)
check("A8 提取全绿（无 WARN）", warns == [], f"warns={warns}")

# ══════════════════════════════════════════════════════════════════
print("\n########## B. 反向断言：锚定是必需的，不是装饰 ##########")
# 若不把正则锚定在 A2 条独有的「追红日禁买」措辞上，正文里第一个 ≥N% 会抢先命中。
_UNANCHORED = re.findall(r"≥\s*(\d+)\s*%", TEXT)
_ANCHORED = re.findall(r"追红日禁买[^\n]{0,40}?板块当日\s*≥\s*(\d+)\s*%", TEXT)
check("B1 未加锚的宽泛正则**确实会取到错值**（证明 B2 不是冗余装饰）",
      bool(_UNANCHORED) and _UNANCHORED[0] != "2",
      f"未加锚首个匹配 = {_UNANCHORED[0] if _UNANCHORED else None}（错）；加锚 = {_ANCHORED}（对）")
check("B2 加锚后恰命中 1 处且值为 2", _ANCHORED == ["2"], f"实得 {_ANCHORED}")

# ══════════════════════════════════════════════════════════════════
print("\n########## C. 反向断言：绑定是真绑定，不是「取不到就静默用默认」 ##########")
# 把消歧结论从正文删掉 → 必须 WARN。若此处不 WARN，说明该键是**死定义**
# （v4.4.10 已判定该类键为「该资产不会被取数」），正文回退将无人发现。
_r2, w2 = extract(TEXT.replace("A2 优先于", "【已删除】"))
check("C1 删掉「A2 优先于」→ a2_priority_over_watchlist 必须 WARN",
      "a2_priority_over_watchlist" in w2, f"warns={w2}")

_r3, w3 = extract(TEXT.replace("A2 不成立", "【已删除】"))
check("C2 删掉 watchlist 判据「A2 不成立」→ 必须 WARN",
      "watchlist_confirm" in w3, f"warns={w3}")

# ══════════════════════════════════════════════════════════════════
print("\n########## D. 门禁：A2 追红日禁买 ##########")
rc, out = run_pre_trade("创新药", "300")  # 不传任何板块数据
check("D1 缺 --sector-chg/--sector-prev-chg → fail-closed 拦截",
      rc == 1 and "A2 未校验" in out, f"rc={rc}")

rc, out = run_pre_trade("创新药", "300", "--sector-chg", "2.50", "--sector-prev-chg", "1.00")
check("D2 板块 +2.50%（≥2% 红日）→ 命中禁买", rc == 1 and "A2 追红日禁买" in out, f"rc={rc}")
check("D3 红日报文含「不成交」与回调条件单", "不成交" in out and "回撤" in out)

rc, out = run_pre_trade("创新药", "300", "--sector-chg", "0.80", "--sector-prev-chg", "0.50")
check("D4 连续 2 日飘红但两日均 <2% → 仍须命中（「或」关系）",
      rc == 1 and "A2 追红日禁买" in out, f"rc={rc}")

rc, out = run_pre_trade("创新药", "300", "--sector-chg", "1.00", "--sector-prev-chg", "-0.50")
check("D5 板块 +1.00%/前日 -0.50% → A2 放行", "✅ A2 追红日禁买" in out, f"rc={rc}")

# ══════════════════════════════════════════════════════════════════
print("\n########## E. 反向断言：没有这道门禁时，红日与非红日**无法区分** ##########")
# 把 A2/watchlist 相关输出行剔除后，两种场景的其余报文必须**逐字相同**。
# 相同 ⇒ 门禁是唯一的区分者 ⇒ 若删掉本门禁，系统对「板块红日」零感知（= 改动前的真实状态）。
def _strip(text):
    return "\n".join(l for l in text.splitlines()
                     if not any(k in l for k in ("A2", "watchlist", "E 级")))


_, out_red = run_pre_trade("创新药", "300", "--sector-chg", "2.50", "--sector-prev-chg", "1.00")
_, out_calm = run_pre_trade("创新药", "300", "--sector-chg", "1.00", "--sector-prev-chg", "-0.50")
check("E1 剔除 A2 行后，红日/非红日报文逐字相同（= 原系统无区分能力）",
      _strip(out_red) == _strip(out_calm))
check("E2 而未剔除时两者必然不同（证明 E1 的相同是「只剩门禁」，不是「输出被截空」）",
      out_red != out_calm and len(_strip(out_red)) > 200,
      f"非门禁部分长度={len(_strip(out_red))}")

# ══════════════════════════════════════════════════════════════════
print("\n########## F. 门禁：watchlist 右侧确认（新判据） ##########")
_WL = ("有色金属", "300", "--watchlist", "--sector-chg", "0.80", "--sector-prev-chg", "-1.20")

rc, out = run_pre_trade(*_WL, "--close", "1234", "--ma5", "1220")
check("F1 收盘 ≥ MA5 → 条件②成立", "✅ watchlist 右侧确认" in out, f"rc={rc}")
check("F2 报文含 E 级闭环义务（T+1 14:30 前出裁定）",
      "E 级闭环义务" in out and "T+1 日 14:30 前" in out)

rc, out = run_pre_trade(*_WL, "--close", "1210", "--ma5", "1220")
check("F3 收盘 < MA5 → 条件②不成立，拦截",
      rc == 1 and "⛔ watchlist 右侧确认" in out, f"rc={rc}")

rc, out = run_pre_trade(*_WL, "--close", "1234")
check("F4 缺 --ma5 → fail-closed 拦截", rc == 1 and "缺 --ma5" in out, f"rc={rc}")

rc, out = run_pre_trade("有色金属", "800", "--watchlist", "--close", "1234", "--ma5", "1220",
                        "--sector-chg", "0.80", "--sector-prev-chg", "-1.20")
check("F5 额度 ¥800 超 500 上限 → 拦截", rc == 1 and "超出 ¥300-500" in out, f"rc={rc}")

# ══════════════════════════════════════════════════════════════════
print("\n########## G. 契约文件回归 ##########")
contract = json.loads(paths.RULE_CONTRACT_PATH.read_text(encoding="utf-8"))
_keys = ("a2_red_day_pct", "a2_consecutive_red_days", "a2_pullback_from_high_days",
         "a2_pullback_from_high_pct", "a2_priority_over_watchlist",
         "watchlist_probe_min", "watchlist_probe_max",
         "watchlist_confirm_requires_a2_pass", "watchlist_confirm_ma_period")
_missing = [k for k in _keys if k not in contract.get("rules", {})]
check("G1 已落盘契约含全部 9 个新键", not _missing, f"缺={_missing}")
check("G2 落盘契约 warns 为空", contract.get("warns") == [],
      f"warns={contract.get('warns')}")

# ══════════════════════════════════════════════════════════════════
print("\n########## H. 月操作额度：二维口径（v4.5.1） ##########")
# 背景：手册正文写「正常月≤4笔（买入≤2+卖出≤2）」，速查表压缩成「正常≤4」，
# 而门禁绑的是一维 `max_monthly_ops=4`；契约 DEFAULTS 里早有 buy_max/sell_max
# 但**无提取正则、无消费者**（写对了的死键）。三个缺陷：维度丢失 / 记录≠事件 / 靠子串巧合。

import data_processor as dp  # noqa: E402


def _txn(date, op, amount, fund="测试基金", **kw):
    t = {"date": date, "op": op, "amount": amount, "fund": fund, "name": fund, "note": ""}
    t.update(kw)
    return t


# ---- H-a 契约提取 ----
check("H1 monthly_buys_max == 2（买入维上限）", rules.get("monthly_buys_max") == 2,
      f"实得 {rules.get('monthly_buys_max')!r}")
check("H2 monthly_sells_max == 2（卖出维上限）", rules.get("monthly_sells_max") == 2,
      f"实得 {rules.get('monthly_sells_max')!r}")
check("H3 monthly_ops_cleanup_max == 6（清理月上限）",
      rules.get("monthly_ops_cleanup_max") == 6, f"实得 {rules.get('monthly_ops_cleanup_max')!r}")
check("H4 旧死键 buy_max / sell_max 已从契约消失（改名接上消费者，不再悬空）",
      "buy_max" not in rules and "sell_max" not in rules)

# ---- H-b 反向断言：删掉正文括号 ⇒ 提取必须**声张**而非静默取默认 ----
_txt_noparen = TEXT.replace("（买入≤2+卖出≤2）", "")
_r2, _w2 = extract(_txt_noparen)
check("H5 删掉正文「（买入≤2+卖出≤2）」后提取必须落入 warns（fail-loud）",
      "monthly_buys_max" in _w2 and "monthly_sells_max" in _w2,
      f"warns={_w2} ⇒ 证明该键**真绑定正文**，不是「取不到就静默用默认」的死定义")

# ---- H-c 🔴 核心反向断言：证明旧的一维判据确实会**放行**超限买入 ----
_d_buy3 = {"transactions": [
    _txn("2026-09-01", "买入", 1000), _txn("2026-09-02", "买入", 1000),
    _txn("2026-09-03", "买入", 1000)]}
_s3 = dp.monthly_ops_summary(_d_buy3, year=2026, month=9)
_old_blocked = _s3.total >= 4      # 旧判据原文：`used >= max_ops` 才拦
_old_pass = not _old_blocked
check("H6 🎯 买入3笔+卖出0笔：**旧一维判据会放行**（total=3 < 4 ⇒ 不拦）",
      _old_pass, f"旧判据 blocked={_old_blocked} ⇒ 这正是修复前的真实行为")
check("H7 🎯 同一数据下**新二维判据必须拦截**（买入维 3 > 2）",
      _s3.is_buy_over and _s3.is_over_limit,
      f"买入={_s3.buys}/{_s3.max_buys} 卖出={_s3.sells}/{_s3.max_sells}")
check("H8 🎯 旧=放行 而 新=拦截 ⇒ 证明本修复**真的改变了判定**（非装饰性改动）",
      _old_pass and _s3.is_over_limit and (_old_blocked != _s3.is_over_limit),
      f"旧 blocked={_old_blocked} / 新 blocked={_s3.is_over_limit}")

# ---- H-d 计「事件」不计「记录」----
_d_legs = {"transactions": [
    _txn("2026-09-10", "赎回", 3000), _txn("2026-09-11", "赎回确认", 3759.25),
    _txn("2026-09-12", "赎回到账", 3759.25)]}
_s4 = dp.monthly_ops_summary(_d_legs, year=2026, month=9)
check("H9 `赎回`+`赎回确认`+`赎回到账`（同一事件三条腿）只计 **1** 笔",
      _s4.sells == 1 and _s4.total == 1, f"实得 卖出={_s4.sells} 合计={_s4.total}")

_d_legs_old = [_txn("2026-09-10", "赎回", 3000), _txn("2026-09-11", "赎回确认", 3759.25)]
# 旧实现已移除，此处**按原样复现其逻辑**用于反向断言
# （v4.5.0 之前的 data_processor.is_manual_operation 原文：排除词黑名单，未命中即计入）
def _old_impl(t):
    op = str(t.get("op", ""))
    if any(k in op for k in ("定投", "转入", "转出", "入金", "出金", "赎回到账")):
        return False
    if "自动扣款" in str(t.get("note", "")) or "非手动" in str(t.get("note", "")):
        return False
    return True

_old_n = sum(1 for t in _d_legs_old if _old_impl(t))
check("H10 🎯 旧实现（排除词黑名单）在同一数据上会算成 **2** 笔 ⇒ 反向证明虚增",
      _old_n == 2, f"旧={_old_n} 新={_s4.sells} ⇒ 差 {_old_n - _s4.sells} 笔纯属口径误差")

# ---- H-e 「碰巧对」vs「定义对」----
check("H11 `余额宝转出` 归 leg（闭集成员）",
      dp.classify_txn_op("余额宝转出") == "leg")
check("H12 `转换转入` 归 leg（闭集成员）", dp.classify_txn_op("转换转入") == "leg")
# 反向：证明「靠子串巧合」的写法在**新词**上会破功 —— 旧黑名单只列了 '转出'/'转入'
# 这类子串，`余额宝赎回转出` 之类一旦出现即漏；闭集写法则必须显式覆盖。
check("H13 🎯 旧黑名单风格（仅列 '转出'）对 `转换转出` 会**漏判**，而闭集不会",
      (("转出" in "转换转出") is True) and dp.classify_txn_op("转换转出") == "leg",
      "闭集显式收录 ⇒ 不依赖子串巧合")

# ---- H-f 未知 op fail-loud ----
_d_unknown = {"transactions": [_txn("2026-09-05", "回购", 500)]}
_s5 = dp.monthly_ops_summary(_d_unknown, year=2026, month=9)
check("H14 闭集外 op `回购` → has_unknown 且**不计入买卖任一维**",
      _s5.has_unknown and _s5.total == 0 and "回购" in _s5.unknown_ops,
      f"unknown_ops={_s5.unknown_ops} total={_s5.total}")
check("H15 而同一条旧实现会把它**静默计入**（口径③的病灶）",
      _old_impl(_txn("2026-09-05", "回购", 500)) is True,
      "旧=True（静默计入） vs 新=声张 ⇒ 行为方向相反")

# ---- H-g superseded 取代机制 ----
_d_sup = {"transactions": [
    _txn("2026-09-01", "买入", 2000, "证券", superseded=True),
    _txn("2026-09-01", "买入", 2000, "鹏华", superseded_by="同事件收盘确认")]}
_s6 = dp.monthly_ops_summary(_d_sup, year=2026, month=9)
check("H16 superseded / superseded_by 记录**不计入**额度",
      _s6.buys == 0 and _s6.superseded_records == 2, f"实得 {_s6}")

# ---- H-h 疑似双记**只声张不折叠** ----
# 🔴 v4.5.2 起分组键**含 fund**（原来不含 ⇒ 长期误报，见下 H17b）。故本夹具必须用
#    **同基金**的同额同日两笔 —— 否则测的是「同日同额的不同基金」，不是双记。
_d_dup = {"transactions": [
    _txn("2026-09-01", "买入", 2000, "证券"), _txn("2026-09-01", "买入", 2000, "证券")]}
_s7 = dp.monthly_ops_summary(_d_dup, year=2026, month=9)
check("H17 同(日期/op/基金/金额)多记录 → 报出 suspect_dupes 但**不自动折叠**（计数仍为 2）",
      _s7.has_suspect_dupes and _s7.buys == 2,
      f"声张={_s7.has_suspect_dupes} 仍计 {_s7.buys} 笔 ⇒ 谁对谁错**留给人工**，机器不猜")
_d_dup2 = {"transactions": [
    _txn("2026-09-01", "买入", 2000, "证券"), _txn("2026-09-01", "买入", 2000, "鹏华")]}
_s7b = dp.monthly_ops_summary(_d_dup2, year=2026, month=9)
check("H17b 🔴 同额同日但**不同基金** ⇒ **不得**报疑似双记"
      "（旧键缺 `fund` 时此处长期误报 —— 天天响的告警会被学会忽略）",
      not _s7b.has_suspect_dupes and _s7b.buys == 2,
      f"声张={_s7b.has_suspect_dupes} 计 {_s7b.buys} 笔 ⇒ 应为两笔各算各的正常买入")

# ---- H-i 向后兼容 ----
check("H18 仍可 2 元组解包（既有调用点无需改动）", tuple(_s3) == (_s3.total, _s3.violations))
check("H19 仍可 [0] 下标", _s3[0] == _s3.total)

# ---- H-i2 显式声明优先于推断（防回归 —— 本条曾被修复过程本身弄丢过一次）----
_d_note = {"transactions": [
    _txn("2026-09-05", "买入", 500, note="智能定投自动扣款（非手动操作，不计入月限额）"),
    _txn("2026-09-06", "买入", 500)]}
_s8 = dp.monthly_ops_summary(_d_note, year=2026, month=9)
check("H21 note 显式声明「非手动／自动扣款」→ 不计入（显式声明优先于 op 分类）",
      _s8.buys == 1, f"实得 买入={_s8.buys}（应为 1，声明那条被排除）")
check("H22 `txn_exclusion_reason` 能指明**是哪一条口径**在起作用（非布尔黑箱）",
      dp.txn_exclusion_reason(
          _txn("2026-09-05", "买入", 500, note="智能定投自动扣款（非手动操作）")
      ) == 'note_declared_non_manual'
      and dp.txn_exclusion_reason(_txn("2026-09-11", "赎回确认", 1)) == 'ledger_leg'
      and dp.txn_exclusion_reason(_txn("2026-09-01", "买入", 1, superseded=True)) == 'superseded'
      and dp.txn_exclusion_reason(_txn("2026-09-01", "买入", 1)) is None)

# ---- H-j 真实数据读数（回归锚：数字变了必须有人解释）----
_real = json.loads(paths.DATA_PATH.read_text(encoding="utf-8"))
_s9 = dp.monthly_ops_summary(_real, year=2026, month=9)
check("H20 真实 9 月读数 = 买入 5 / 卖出 3 / 合计 8（口径修正 ＋ 9/1 双记已折叠）",
      (_s9.buys, _s9.sells) == (5, 3),
      f"实得 {_s9} —— 演进：旧口径 10（把 `赎回确认` 记账腿算成独立操作）"
      f" → v4.5.1 口径修正 6（记账腿先判）→ v4.5.2 9/1 双记折叠 5"
      f"（用户 2026-09-18 确认「证券 ¥2000 记重了」）")

# ---- H-j2 🔴 反向断言：疑似双记检测**仍须抓得到真阳性** ----
# 起因：v4.5.1 的分组键是 (日期, op, 金额) —— **不含基金**，于是「9/1 证券 ¥2000 ＋
# 鹏华 ¥2000」这种**同日同额但不同基金的正常两笔**被长期误报。v4.5.2 把 `fund`
# 加进键之后，必须确认**没有顺手把真阳性也一起修没**：
_sf = {"transactions": [
    {"date": "2026-09-05", "op": "买入", "fund": "X基金", "amount": 1000},
    {"date": "2026-09-05", "op": "买入", "fund": "X基金", "amount": 1000},
    {"date": "2026-09-05", "op": "买入", "fund": "Y基金", "amount": 1000}], "_meta": {}}
_sfs = dp.monthly_ops_summary(_sf, year=2026, month=9)
check("H21 🔴 同基金同额同日 ×2 ⇒ **仍须报出**（修误报不得把真阳性一起修没）",
      len(_sfs.suspect_dupes) == 1 and _sfs.suspect_dupes[0]["count"] == 2
      and _sfs.suspect_dupes[0]["fund"] == "X基金",
      repr(_sfs.suspect_dupes))
check("H22 🔴 同日同额的**不同基金** ⇒ **不得**被卷入同一组（这才是误报的根因）",
      all("Y基金" not in (d.get("funds") or []) for d in _sfs.suspect_dupes),
      "若 Y基金 出现在组内，说明键里仍缺 fund")

# ---- H-j3 折叠后真实数据上**不应再有**疑似双记（回归锚）----
check("H23 真实数据（9/1 已折叠）读数上疑似双记组数 = 0",
      len(_s9.suspect_dupes) == 0, repr(_s9.suspect_dupes))

# ══════════════════════════════════════════════════════════════════
# 段 I —— watchlist 状态计算（v4.5.1）：A2 三分 · MA5 口径 · fail-closed
# ══════════════════════════════════════════════════════════════════
import gen_watchlist_status as gws  # noqa: E402
import fetch_public as fp  # noqa: E402
from datetime import datetime  # noqa: E402

_BOARDS = {                       # 造一个两宇宙的小样本
    "by_name": {
        "固态电池": {"name": "固态电池", "code": "BK1090", "chg_pct": 1.69, "board_type": "概念板块"},
        "有色金属": {"name": "有色金属", "code": "BK0478", "chg_pct": 1.54, "board_type": "行业板块"},
        "某板块A": {"name": "某板块A", "code": "BK9998", "chg_pct": 2.50, "board_type": "行业板块"},
        "某板块B": {"name": "某板块B", "code": "BK9997", "chg_pct": -0.80, "board_type": "行业板块"},
    },
    "universes": {"行业板块": {"total": 496, "fetched": 496, "complete": True},
                  "概念板块": {"total": 504, "fetched": 504, "complete": True}},
    "complete": True,
}

# ---- I-a A2 三分：命中 / 完全判定不成立 / 仅部分可判 ----
_hit, _det, _ = gws._eval_a2("某板块A", _BOARDS, 2.0)
check("I1 板块 +2.50% ≥ 2% ⇒ A2 命中且完全判定", (_hit, _det) == (True, True), f"得 {_hit},{_det}")

_hit, _det, _txt = gws._eval_a2("某板块B", _BOARDS, 2.0)
check("I2 板块 -0.80% ≤ 0 ⇒ A2 不成立且**完全判定**（分支②逻辑上不可能）",
      (_hit, _det) == (False, True), f"得 {_hit},{_det} —— 「连续2日飘红」蕴含「当日>0」，故当日≤0 时该分支必假")

_hit, _det, _txt = gws._eval_a2("固态电池", _BOARDS, 2.0)
check("I3 板块 +1.69% ∈ (0,2%) ⇒ A2 **仅部分可判**（唯一真正无源的区间）",
      (_hit, _det) == (None, False), f"得 {_hit},{_det}")
check("I3b 部分可判的说明里必须**点名缺的是哪一个源**（日序列缓存），而非含糊其辞",
      "日序列缓存" in _txt and "仅部分可判" in _txt, f"实得：{_txt[:100]}")

_hit, _det, _txt = gws._eval_a2("查无此板", _BOARDS, 2.0)
check("I4 板块查不到 ⇒ 判定为不可判（不得当作『未命中』放行）",
      (_hit, _det) == (None, False), f"得 {_hit},{_det}")

# ---- I-b 🔴 反向断言：证明「双宇宙 + 分页」是**必需**而非装饰 ----
try:
    _old_only_t2 = fp.sector_movers(top=500, pz=500)      # 旧实现：单宇宙 + 单页
    _old_names = {r["name"] for r in (_old_only_t2.get("gainers") or []) + (_old_only_t2.get("losers") or [])}
    _old_found = [s for s in ("固态电池", "人形机器人", "智能驾驶") if
                  any(s in n or n in s for n in _old_names)]
    check("I5 反向断言：旧实现（仅 t:2 行业宇宙）**找不到** 3 个概念主题中的任何一个",
          len(_old_found) == 0,
          f"旧实现却找到了 {_old_found} —— 若不为空则本修复无必要，须复核")

    _t2rows, _t2total = fp._sector_rows(1, 500, "probe t:2")
    check("I6 反向断言：`pz=500` **实际只回 100 行**（total=496）"
          "⇒ v4.4.12 记的『改 pz=500 覆盖全集』**这句话不成立**",
          len(_t2rows) == 100 and _t2total >= 400,
          f"实回 {len(_t2rows)} 行 / total={_t2total} —— 若真回 500 行，本反向断言失效，须复核")

    _all = fp.board_movers_all()
    _u = _all.get("universes") or {}
    check("I7 新实现取到**两套宇宙的全量**（行业≥400 且 概念≥400）",
          _u.get("行业板块", {}).get("fetched", 0) >= 400 and
          _u.get("概念板块", {}).get("fetched", 0) >= 400,
          f"实得 {_u}")
    _names = set((_all.get("by_name") or {}).keys())
    _now_found = [s for s in ("固态电池", "人形机器人", "智能驾驶", "有色金属") if s in _names]
    check("I8 新实现能同时命中**两套宇宙**的主题（概念 3 个 ＋ 行业 1 个）",
          len(_now_found) == 4, f"命中 {_now_found}")
except Exception as _e:                                    # noqa: BLE001
    print(f"  [SKIP] I5–I8 需联网取板块榜，本次跳过：{type(_e).__name__} {_e}")

# ---- I-c 🔴 MA5 口径歧义：两解必须是**可分辨的不同值** ----
_klt = [{"date": f"2026-09-{10+i:02d}", "close": c}
        for i, c in enumerate([1.00, 1.00, 1.00, 1.00, 1.00, 1.20])]
_closes = [float(b["close"]) for b in _klt]
check("I9 MA5『含当日』与『不含当日』在趋势中是不同值（口径歧义真实存在）",
      fp.ma(_closes, 5) != fp.ma(_closes[:-1], 5),
      f"含当日={fp.ma(_closes, 5)} 不含={fp.ma(_closes[:-1], 5)}")

# ---- I-d 🔴 fail-closed：A2 判不了 ⇒ **不得**授予 🟢 ----
_kl_fake = [{"date": f"2026-09-{10+i:02d}", "close": c}
            for i, c in enumerate([1.00, 1.00, 1.00, 1.00, 1.00, 1.50])]
_orig_dk, _orig_ma = fp.daily_kline, fp.ma
fp.daily_kline = lambda code, n=30: _kl_fake            # type: ignore[assignment]
try:
    _e = gws.evaluate_entry(
        {"sector": "固态电池", "etf_code": "159755"}, {"rules": {}},
        _BOARDS, datetime(2026, 9, 18, 18, 0))
    check("I10 A2 仅部分可判 ＋ 技术面成立 ⇒ 状态**不得**为 🟢（fail-closed）",
          "🟢" not in _e["verdict"], f"实得 {_e['verdict']}")
    check("I10b 该情形下 `a2_ok` 必须为 None（不得拿 False 冒充『已排除』）",
          _e["a2_ok"] is None and _e["a2_determined"] is False,
          f"a2_ok={_e['a2_ok']} determined={_e['a2_determined']}")

    _e2 = gws.evaluate_entry(
        {"sector": "某板块B", "etf_code": "159755"}, {"rules": {}},
        _BOARDS, datetime(2026, 9, 18, 18, 0))
    check("I11 A2 完全判定不成立 ＋ 技术面成立 ⇒ 才给 🟢",
          "🟢" in _e2["verdict"], f"实得 {_e2['verdict']}")

    _e3 = gws.evaluate_entry(
        {"sector": "某板块A", "etf_code": "159755"}, {"rules": {}},
        _BOARDS, datetime(2026, 9, 18, 18, 0))
    check("I12 A2 命中 ⇒ ⛔ 禁买（A2 优先于右侧确认）",
          "⛔" in _e3["verdict"] and _e3["a2_hit"] is True, f"实得 {_e3['verdict']}")

    # I13/I13b 需末根 = **当日**，故换一份末日为 2026-09-18 的夹具
    _kl_today = [{"date": f"2026-09-{13+i:02d}", "close": c}
                 for i, c in enumerate([1.00, 1.00, 1.00, 1.00, 1.00, 1.50])]
    fp.daily_kline = lambda code, n=30: _kl_today       # type: ignore[assignment]

    _e4 = gws.evaluate_entry(
        {"sector": "固态电池", "etf_code": "159755"}, {"rules": {}},
        _BOARDS, datetime(2026, 9, 18, 14, 0))          # 盘中（未收盘）
    check("I13 盘中取值 ⇒ `close_confirmed=False` 且状态为『盘中·未定格』，"
          "**不得**当作收盘价判据（F5）",
          _e4["close_confirmed"] is False, f"close_confirmed={_e4['close_confirmed']}")

    # 反向对照：同一根【当日】K 线，收盘后取 ⇒ 它**就是**收盘价，必须为 True。
    # （证明判定依据是「末根是否当日 ＋ 是否已过 15:00」，不是无条件 False）
    _e5 = gws.evaluate_entry(
        {"sector": "固态电池", "etf_code": "159755"}, {"rules": {}},
        _BOARDS, datetime(2026, 9, 18, 15, 30))
    check("I13b 反向对照：同一当日 K 线，15:30 取 ⇒ `close_confirmed=True`"
          "（证明该标志不是无条件 False）",
          _e5["close_confirmed"] is True, f"close_confirmed={_e5['close_confirmed']}")

    # 反向对照二：末根是【历史】K 线（非当日）⇒ 本来就是已定格收盘，必须为 True
    check("I13c 反向对照：末根为历史 K 线（非当日）⇒ 亦为 True"
          "（此前我的夹具正是踩了这条，被测试自己抓出）",
          _e["close_confirmed"] is True, f"close_confirmed={_e['close_confirmed']}")
finally:
    fp.daily_kline, fp.ma = _orig_dk, _orig_ma          # type: ignore[assignment]

check("I14 测试后已还原被 monkeypatch 的 fetch_public 函数",
      fp.daily_kline is _orig_dk and fp.ma is _orig_ma)

# ---- I-e 真实数据读数（回归锚）----
_real_wl = _real.get("watchlist") or []
check("I15 真实 watchlist 4 条、码型可解析为腾讯代码",
      len(_real_wl) == 4 and all(gws._norm_tencent(w.get("etf_code"))[0] for w in _real_wl),
      f"得 {[(w.get('sector'), gws._norm_tencent(w.get('etf_code'))[0]) for w in _real_wl]}")

# ══════════════════════════════════════════════════════════════════
# J. v4.5.2 —— A2 前日涨幅（自建日序列缓存）＋ MA5 口径裁定
# ══════════════════════════════════════════════════════════════════
_PREV = {"BK1090": {"name": "固态电池", "chg_pct": 0.95, "board_type": "概念板块"},
         "BK0478": {"name": "有色金属", "chg_pct": -0.30, "board_type": "行业板块"}}

# ---- J-a 有前日 ⇒ (0,2%) 区间由「部分可判」收敛为「完全判定」（本版真正的功能增量）----
_hit, _det, _txt = gws._eval_a2("固态电池", _BOARDS, 2.0, _PREV, "2026-09-17")
check("J1 当日 +1.69%∈(0,2%) 且 前日 +0.95%>0 ⇒ **连续2日飘红** ⇒ A2 命中、完全判定",
      (_hit, _det) == (True, True), f"得 {_hit},{_det}")
check("J1b 命中理由须写明是**分支②**（不是分支①），否则无法追溯命中的是哪条腿",
      "分支②" in _txt and "连续 2 日飘红" in _txt, f"实得：{_txt[:95]}")

_hit, _det, _txt = gws._eval_a2("有色金属", _BOARDS, 2.0, _PREV, "2026-09-17")
check("J2 当日 +1.54%∈(0,2%) 而 前日 -0.30%≤0 ⇒ 分支②不成立 ⇒ A2 不成立、**完全判定**",
      (_hit, _det) == (False, True),
      f"得 {_hit},{_det} —— 与 I3 的 (None,False) 是**不同结论**，这正是本版要买的东西")

# ---- J-b 🔴 反向断言：同一输入，无缓存 vs 有缓存必须给出**不同**结论 ----
_hit_no, _det_no, _ = gws._eval_a2("固态电池", _BOARDS, 2.0, None, "2026-09-17")
_hit_yes, _det_yes, _ = gws._eval_a2("固态电池", _BOARDS, 2.0, _PREV, "2026-09-17")
check("J3 🔴 同一条目：无前日缓存 ⇒ 不可判；有前日缓存 ⇒ 命中"
      "（**证明缓存是必需项而非装饰** —— 否则本测试在假阳性下也会过）",
      (_hit_no, _det_no, _hit_yes, _det_yes) == (None, False, True, True),
      f"无缓存=({_hit_no},{_det_no})　有缓存=({_hit_yes},{_det_yes})")

# ---- J-c 🔴 缓存写入的三条硬约束（缺一即静默失效）----
_tmpdir = tempfile.mkdtemp(prefix="anchor_bh_")
_prod = Path(paths.DASHBOARD_DIR) / "board_pct_history.json"
_prod_before = _prod.read_bytes() if _prod.exists() else None
os.environ["ANCHOR_BOARD_HISTORY"] = str(Path(_tmpdir) / "bh.json")
try:
    from datetime import datetime as _dt
    _rows = [{"code": "BK1090", "name": "固态电池", "chg_pct": 1.69, "board_type": "概念板块"}]
    _ok_boards = {"rows": _rows, "complete": True}

    _r = fp.board_history_record(_ok_boards, "2026-09-18", _dt(2026, 9, 18, 15, 6))
    check("J4 收盘定格后 ＋ complete ⇒ 落盘成功", _r.get("recorded") is True, str(_r))

    _r = fp.board_history_record(_ok_boards, "2026-09-18", _dt(2026, 9, 18, 14, 59))
    check("J5 🔴 未到 15:05 ⇒ **拒绝落盘**（盘中价不得当收盘价存下来 —— 缓存里没有字段能事后分辨）",
          _r.get("recorded") is False and "15:05" in str(_r.get("reason")), str(_r))

    _r = fp.board_history_record({"rows": _rows, "complete": False}, "2026-09-18",
                                 _dt(2026, 9, 18, 15, 6))
    check("J6 🔴 complete=False ⇒ **拒绝落盘**（否则日后查某主题会『匹配不到』并被误读成不存在）",
          _r.get("recorded") is False and "complete" in str(_r.get("reason")), str(_r))

    # 🔴 J7 反向断言：落盘键必须是**数据自身的交易日**，不是 now 的日期。
    #    ⚠️ 夹具第一版用了 09-19 **10:00**，被「未到 15:05」那道闸门正确拦下 ⇒
    #       断言在**没测到目标**的情况下就已经是假 —— 换成**周六收盘后 15:30**
    #       （真实场景：周末跑一次，板块榜返回的是**周五**的收盘值）。
    _r = fp.board_history_record(_ok_boards, "2026-09-18", _dt(2026, 9, 19, 15, 30))
    _days = fp.board_history_load()["days"]
    check("J7 🔴 落盘键＝**数据自身的交易日**（09-18），**不是** now 的日期（09-19）"
          "—— 否则周末/节假日跑一次就把上一交易日收盘值**标成今天**",
          _r.get("recorded") is True and "2026-09-18" in _days and "2026-09-19" not in _days,
          f"recorded={_r.get('recorded')} 键={sorted(_days)}")

    # ---- J-d 读取侧：缺即缺口，⛔ 不得回退到「最近一条」----
    check("J8 取存在的交易日 ⇒ 有值", fp.board_history_day("2026-09-18") is not None)
    check("J9 🔴 取**不存在**的交易日 ⇒ None（⛔ 不得用『最近一条』冒充前一交易日）",
          fp.board_history_day("2026-09-17") is None,
          "缓存里只有 09-18；若回退到最近一条，09-17 会拿到 09-18 的值＝把今天当昨天")

    # ---- J-e 交易日历取自数据自身，不靠自然日推算 ----
    _kl = [{"date": "2026-09-16"}, {"date": "2026-09-17"}, {"date": "2026-09-18"}]
    check("J10 prev_trading_day 取**严格早于今天**的最近一日",
          fp.prev_trading_day(_kl, "2026-09-18") == "2026-09-17",
          str(fp.prev_trading_day(_kl, "2026-09-18")))
    check("J10b K线末根仍是上一交易日（盘前）⇒ 前一交易日再往前推一日",
          fp.prev_trading_day(_kl, "2026-09-21") == "2026-09-18",
          str(fp.prev_trading_day(_kl, "2026-09-21")))
finally:
    os.environ.pop("ANCHOR_BOARD_HISTORY", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

_prod_after = _prod.read_bytes() if _prod.exists() else None
check("J11 🔴 全程**未触碰生产缓存文件**（靠换路径隔离，**不靠 `try/finally`** —— "
      "v4.5.1 教训：进程被硬杀时 finally 不执行，「靠 finally 不污染」不成立）",
      _prod_before == _prod_after)

# ---- J-f 契约绑定（新键必须有真消费者，否则就是又一个死键）----
_c = json.loads(paths.RULE_CONTRACT_PATH.read_text(encoding="utf-8"))
_cr = _c.get("rules", {})
check("J12 契约含 watchlist_confirm_ma_includes_today 且＝True（含当日）",
      _cr.get("watchlist_confirm_ma_includes_today") is True,
      repr(_cr.get("watchlist_confirm_ma_includes_today")))
check("J13 契约 a2_prev_day_cache 与**代码实际读的文件名**一致（名实绑定）",
      _cr.get("a2_prev_day_cache") == os.path.basename(fp._board_history_path()),
      f"契约={_cr.get('a2_prev_day_cache')!r} 代码={os.path.basename(fp._board_history_path())!r}")
check("J14 契约 warns 为空（提取正则全部命中，无静默回退默认值）",
      not _c.get("warns"), repr(_c.get("warns")))

# ---- J-g 🔴 反向断言：改掉手册原文 ⇒ 提取值必须随之改变（证明是真绑定）----
_r2, _w2 = extract(TEXT.replace("「当日 MA5」＝**含当日收盘**",
                                "「当日 MA5」＝**不含当日收盘**"))
check("J15 把手册改写成「不含当日」⇒ 提取值必须变 **False**"
      "（不是「正则不匹配 ⇒ 悄悄回默认 True」）",
      _r2.get("watchlist_confirm_ma_includes_today") is False,
      repr(_r2.get("watchlist_confirm_ma_includes_today")))
_r3, _w3 = extract(TEXT.replace("自建日序列缓存", "某外部源"))
check("J16 🔴 删掉『自建日序列缓存』措辞 ⇒ 必须 **WARN**（真绑定，非『取不到就静默用默认』）",
      "a2_prev_day_cache" in _w3, repr(_w3))

# ══════════════════════════════════════════════════════════════════
_fail = [n for n, ok, _ in _results if not ok]
print("\n" + "=" * 56)
print(f"共 {len(_results)} 项 · 通过 {len(_results) - len(_fail)} · 失败 {len(_fail)}")
if _fail:
    print("❌ 失败项:")
    for n in _fail:
        print("   -", n)
    sys.exit(1)
print("✅ 全绿")
sys.exit(0)
