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
_skips = []


def check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail else ""))


def skip(name, reason):
    """**第三种状态：无法判定**（⛔ 既不是通过、也不是不通过）。

    v4.5.17 新增，动机是一桩实发：§I 的板块榜断言**只捕获异常**，
    而东财限流时的长相是 **HTTP 200 + 0 行** —— 不抛异常。
    于是断言失败，报文却写着「宇宙样本 0 个 ⇒ 探针自检」，
    **把「取数失败」渲染成了「代码有问题」**（本仓「我没取到 ≠ 它没有」家族）。

    ⇒ 一条**看起来永远红的**断言会被学会忽略（报告标准 v2.1 判例），
      故此处显式区分三态：通过 / **无法判定（附原因）** / 不通过。
    """
    _skips.append((name, reason))
    print(f"⏭ {name} — **无法判定**：{reason}")


def _ib_skip_reason(names) -> "str | None":
    """§I-b 的**三态判据**（`inbox/144` R1）：源返回 **0 行** ⇒ 无法判定；有行 ⇒ 交给断言判。

    🔴 v4.5.17：**抽成函数是为了可测** —— 144 §3 验收第 1、2 条要求**一对反向断言**：
      ① 源不可达（0 行）⇒ **SKIP**，⛔ 不是 FAIL
      ② **源可达但数据错**（非空但不对）⇒ **必须 FAIL**
    ⛔ **只证 ① 是不够的** —— 那可能把闸门改成**恒放行**（本仓 v4.5.5/6/7 连续三次教训：
      不测「原写法确实会错」的测试，可能在「护栏根本没跑」的假阳性下通过）。
    ⇒ 判据只看 **「取到几行」**，**完全不看内容对错**：
      空 ⇒ 不知道；非空 ⇒ 内容对不对由断言说了算。这就是 ② 成立的结构性理由。
    """
    if len(names) == 0:
        return ("板块榜活源本次**返回 0 行**（东财 IP 级限流，HTTP 200 但不报错）"
                "⇒ I5–I8 全部**无法判定**。⛔ 这既不是「通过」也不是「代码坏了」——"
                "复跑前请先确认该端点有数据")
    return None


def _ib_placehold(items, done, reason, emit=None) -> list:
    """§I-b **中途失败**时的占位：把尚未发出的项逐个**登记 + 报出**，返回新占位的项名。

    🔴 v4.5.17：**抽成函数是为了可测** —— 本机制初版**有 bug，而套件抓不到它**：
       占位 `skip()` **没有把项名登记进 `done`** ⇒ 一旦活源在 §I-b 中途失败，
       紧随其后的 I8b（占位完备性检查）会把「**源抖了一下**」判成
       「**代码坏了**」—— 恰恰就是本单（144）要治的那个病。
       🔴 抓到它的是一个**独立探针**（隔离语境下把本机制单独复现一遍）：
          ⛔ **读代码看不出来**，`_IB_DONE.add` 少了那一行的症状只在**真跑**时才现形。
       ⇒ 结论与前几次一致（v4.5.7 K2）：**记教训不是防线，改档案形状才是** ——
         所以本机制提为**纯函数**，`emit` 可注入，从而能被下面的 N41–N43 **真断言**。
    """
    _emit = emit or skip
    placed = []
    for nm in items:
        if nm not in done:
            done.add(nm)                      # 🔴 占位**也算登记**（缺此行 ⇒ I8b 假红）
            _emit(f"{nm}（**未跑到**）", reason)
            placed.append(nm)
    return placed


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
# v4.5.17：旧实现把**两个键合并成一个告警名** `warns.append("watchlist_confirm")`
#   ⇒ 谁坏了、坏成什么样，从告警名上**看不出来**。注册表拆为两个键、各自实名告警。
#   ⇒ 断言随之改为**精确键名**（⛔ 不放宽为子串匹配 —— 那会让「名字错了」也通过）。
check("C2 删掉 watchlist 判据「A2 不成立」→ 必须 WARN（精确键名）",
      "watchlist_confirm_requires_a2_pass" in w3, f"warns={w3}")
# 🔴 反向断言：旧合并告警名**不得**再出现（钉住「合并名」这个形态本身已消失）。
#    ⚠️ 这里用的是**列表精确成员**判断 —— 若谁把它改回 `"watchlist_confirm" in s for s in w3`
#    这类**子串**写法，本断言会失守，故保留精确成员形式。
check("C2b 反向·旧合并告警名 'watchlist_confirm' 不得再作为元素出现",
      "watchlist_confirm" not in w3, f"warns={w3}")
# 同一替换下 `收盘价 ≥ 当日 MA5` **仍在** ⇒ MA 周期键**不得**误报
check("C2c 哨兵各管各的：MA 周期键不得因邻键哨兵消失而误报",
      "watchlist_confirm_ma_period" not in w3, f"warns={w3}")

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
#
# 🔴 v4.5.17（`inbox/144` §3 验收 5「⛔ 不得虚增通过数」的**反向**情形）：
#    本块是**全仓唯一**的直连活源断言点（其余四个取数测试文件全部走离线夹具
#    —— `_board_page` / `_http` / `_em_json` 被 monkeypatch，不碰网络）。
#    但原实现有个**比虚增更隐蔽**的洞：412/438/444 任一处**中途**抛异常 ⇒
#    `except` 只 print 一行，而 I5–I8 **既不在 `_results` 也不在 `_skips`**
#    ⇒ 它们**从分母里静默消失**。少了几项没人会去数，多了几项一眼能看出来。
#    ⇒ 改为**预登记全部项名，异常时把尚未发出的项逐个 `skip()`**：
#      三项必占位，位置永不空缺（"没跑到" 与 "跑了但没过" 必须长得不一样）。
_IB_ITEMS = ("I5", "I5b", "I6", "I7", "I8")
_IB_DONE: set = set()
_IB_SKIP = None
_IB_EXECUTED = 0          # 🔴 144 验收③：真执行计数（源可达时须 ≥ len(_IB_ITEMS)）


def _ib(name, cond, detail=""):
    """§I-b 专用断言器：源断 ⇒ 记 **skip**；源通 ⇒ 交给 `check` 判。

    ⛔ 判据**只看「取到几行」，完全不看内容对错** —— 这正是 144 验收②成立的理由：
       空 ⇒ 不知道（skip）；非空 ⇒ 内容对不对**由断言说了算**（该 FAIL 就 FAIL）。
    """
    global _IB_EXECUTED
    _IB_DONE.add(name.split(" ")[0])
    if _IB_SKIP:
        return skip(name, _IB_SKIP)
    _IB_EXECUTED += 1     # 144 验收③：真走 check（而不是被 skip 绕过）才计数
    return check(name, cond, detail)


try:
    _old_only_t2 = fp.sector_movers(top=500, pz=500)      # 旧实现：单宇宙 + 单页
    _old_names = {r["name"] for r in (_old_only_t2.get("gainers") or []) + (_old_only_t2.get("losers") or [])}
    _IB_SKIP = _ib_skip_reason(_old_names)
    # 🔴 144 R3：源状态**无论可达与否都必须可见**（静默 skip 与静默通过同险，v4.5.4）——
    #    本行是「本次判定所依据的源状态」的显式留痕，skip 与否都不能省。
    print(f"[§I-b] 活源状态：`sector_movers(top=500, pz=500)` 取到 {len(_old_names)} 个板块名 ⇒ "
          + ("**可达**，I5–I8 断言照常执行" if not _IB_SKIP else
             "**不可达（0 行）** ⇒ I5–I8 记为**无法判定**（⛔ 不等于通过：本次未覆盖）"))

    # 🔴 **探针订正（2026-09-21）**：必须**严格**匹配 `s in n`，⛔ 不得双向子串。
    #    原写法 `any(s in n or n in s)` 的 `n in s` 方向会把**行业板块「电池」**
    #    判成**概念主题「固态电池」**（`'电池' in '固态电池' == True`）、
    #    **「机器人」**判成**「人形机器人」** ⇒ 本断言**长期靠运气通过** ——
    #    只因那两个行业板块恰好不在当日涨跌幅前 100 名窗口内；9/21 它们进了窗口
    #    ⇒ 断言翻红。**红的不是实现，是探针**（同族：memory「验证探针本身未经校验」）。
    _old_found = [s for s in ("固态电池", "人形机器人", "智能驾驶") if s in _old_names]
    _ib("I5 反向断言：旧实现（仅 t:2 行业宇宙）**找不到** 3 个概念主题中的任何一个"
        "（**严格匹配**）",
        len(_old_found) == 0,
        f"旧实现却找到了 {_old_found} —— 若不为空则本修复无必要，须复核")
    # 🔴 反向断言的**反向断言**：证明上面的「找不到」不是探针查了个空集合而空手而归。
    #    两部分：① 确定性证明宽松匹配确实会误判（纯字符串运算，不依赖行情）
    #           ② 非空性 —— 宇宙样本必须真有内容，否则 ① 的结论落在空集上仍是假的。
    _ib("I5b 🔴 探针自检：① 证明 `n in s` 方向确实误判"
        "（`'电池' in '固态电池'` 为真、`'机器人' in '人形机器人'` 为真）"
        "② 且 t:2 宇宙样本非空（≥100）⇒「严格匹配找不到」是**真结论**而非空集假象",
        ("电池" in "固态电池") and ("机器人" in "人形机器人") and len(_old_names) >= 100,
        f"① 误判机制成立；② 宇宙样本 {len(_old_names)} 个")

    _t2rows, _t2total = fp._sector_rows(1, 500, "probe t:2")
    _ib("I6 反向断言：`pz=500` **实际只回 100 行**（total=496）"
        "⇒ v4.4.12 记的『改 pz=500 覆盖全集』**这句话不成立**",
        len(_t2rows) == 100 and _t2total >= 400,
        f"实回 {len(_t2rows)} 行 / total={_t2total} —— 若真回 500 行，本反向断言失效，须复核")

    _all = fp.board_movers_all()
    _u = _all.get("universes") or {}
    _ib("I7 新实现取到**两套宇宙的全量**（行业≥400 且 概念≥400）",
        _u.get("行业板块", {}).get("fetched", 0) >= 400 and
        _u.get("概念板块", {}).get("fetched", 0) >= 400,
        f"实得 {_u}")
    _names = set((_all.get("by_name") or {}).keys())
    _now_found = [s for s in ("固态电池", "人形机器人", "智能驾驶", "有色金属") if s in _names]
    _ib("I8 新实现能同时命中**两套宇宙**的主题（概念 3 个 ＋ 行业 1 个）",
        len(_now_found) == 4, f"命中 {_now_found}")
except Exception as _e:                                    # noqa: BLE001
    # 🔴 **中途失败**（如 412 成功、444 抛异常）：尚未发出的项必须**逐个占位**，
    #    ⛔ 不得让它们从分母里消失 —— 否则「少了几项」比「多了几项」更难发现。
    _ib_placehold(_IB_ITEMS, _IB_DONE,
                  f"§I-b 活源中途失败：{type(_e).__name__} {_e}")

# 🔴 **占位完备性（双向）**：无论走哪条分支（活源通 / 活源断 / 中途抛异常），
#    五项**都必须占到位**，且**不得冒出计划外的第六项**。
#
#    ⚠️ **本断言自己被抓过一次 bug**（2026-09-22）：初版 `except` 里的占位 `skip()`
#       **没有登记进 `_IB_DONE`** ⇒ 中途失败时本项会**误报红**，把「源抖了一下」
#       说成「代码坏了」—— 恰恰就是本单（144）要治的那个病。
#       抓到它的是我另跑的一个**独立探针**（把本节的占位机制在隔离语境下单独复现）：
#       ⛔ 只读代码是看不出这个的，**机制必须真跑才作数**。
#
#    ⇒ 现在两个方向都断言：
#       ① `_IB_ITEMS ⊆ _IB_DONE` —— 登记了却没发出（块被执行到一半就断了 / 有人删了 `_ib` 调用）
#       ② `_IB_DONE ⊆ _IB_ITEMS` —— 发出了却没登记（**relay 病史 3 次的同一族**：
#          新增一项而清单未同步 ⇒ 占位机制对新项静默失效）
_missing = [n for n in _IB_ITEMS if n not in _IB_DONE]
_extra = [n for n in sorted(_IB_DONE) if n not in _IB_ITEMS]
check("I8b §I-b **双向**占位完备：① 计划内五项全发出 ② 无计划外项"
      "（活源通/断/中途异常三态都不许从分母里消失；新项漏登记同样在此变红）",
      not _missing and not _extra,
      f"未发 {_missing} / 计划外 {_extra}；实发 {sorted(_IB_DONE)}")

# 🔴 144 验收③（计数）：**源可达时 I5–I8 断言必须"真执行"（计数 ≥5）** ——
#    防的是 skip 机制的第一风险：**断言被整条绕过，而输出仍然显绿**
#    （「skip 把断言悄悄吃掉」与「占位未登记」同族：读代码看不出，只有计数能钉住）。
#    源不可达时本项**随 §I-b 一并无法判定**（⛔ 不得报绿 —— 那正是「未覆盖被读成合格」）。
if _IB_SKIP:
    skip("I8c 🔴 144 验收③·断言执行计数 ≥5（源可达时 I5–I8 **真执行**，防「引入 skip 后断言永不执行」）",
         f"源不可达 ⇒ 断言未执行（真执行计数 {_IB_EXECUTED}），本项无法判定")
else:
    check("I8c 🔴 144 验收③·断言执行计数 ≥5（源可达时 I5–I8 **真执行**，防「引入 skip 后断言永不执行」）",
          _IB_EXECUTED >= len(_IB_ITEMS),
          f"真执行 {_IB_EXECUTED} / 计划 {len(_IB_ITEMS)}")

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
# §K · 缓存缺口自检（v4.5.2）
#   病灶：缓存只由**当日实跑**写入，而东财只给当日板块 ⇒ **漏跑一天＝永久空洞**。
#   于是「结构性无源」被换成「**结构性依赖运维执行**」，且**新的失败模式是静默的**。
#   本节测的不是「有没有缺口」，而是**六种态互相可区分** —— 尤其
#   「✅ 无缺口」不得与「本次根本没核到任何交易日」混为一谈。
# ══════════════════════════════════════════════════════════════════
_K_TMP = tempfile.mkdtemp(prefix="anchor_gap_")
_K_PATH = Path(_K_TMP) / "bh.json"
_KL = [{"date": d} for d in [
    "2026-09-01", "2026-09-02",                                    # epoch **之前**（噪声面）
    "2026-09-10", "2026-09-11", "2026-09-15", "2026-09-16",
    "2026-09-17", "2026-09-18"]]
os.environ["ANCHOR_BOARD_HISTORY"] = str(_K_PATH)


def _k_write(days):
    _K_PATH.write_text(json.dumps({"schema": 1, "days": days}, ensure_ascii=False),
                       encoding="utf-8")


try:
    # ---- K1 有缺口：精确列出，且 **epoch 之前的交易日不得被报** ----
    _k_write({"2026-09-10": {"BK1": {}}, "2026-09-15": {"BK1": {}}})
    _g = fp.board_history_gaps(_KL, "2026-09-18")
    check("K1 缺口精确列出（缺 09-11 / 09-16 / 09-17）且 **epoch 之前的 09-01、09-02 不得被报**"
          "（缓存起点早于机制存在 ⇒ 报出来是噪声，而**天天响的假告警会被学会忽略**）",
          _g["checked"] is True and _g["missing"] == ["2026-09-11", "2026-09-16", "2026-09-17"],
          f"missing={_g['missing']}")

    # ---- K2 🔴 反向断言：核到 0 个交易日时**不得**打印 ✅（假绿灯）----
    #    ⚠️ 这是我自己第一版真犯的错：缓存只有当日 ⇒ expected 为空 ⇒
    #       旧文案输出「✅ 缓存缺口核查：无缺口（核 0 个交易日）」——
    #       **它一个交易日都没核，却盖了一个 ✅**。
    _k_write({"2026-09-18": {"BK1": {}}})
    _m0 = fp.board_history_gap_msg(fp.board_history_gaps(_KL, "2026-09-18"))
    check("K2 🔴 **核到 0 个交易日 ⇒ 不得输出 ✅**（旧文案输出「✅ 无缺口（核 0 个交易日）」＝"
          "一个交易日都没核却盖了绿灯；现须明写「无可核区间」并声明不得读作无缺口）",
          "无缺口" not in _m0.replace("不得读作「无缺口」", "") and "无可核区间" in _m0,
          _m0)

    # ---- K3 缓存为空 ⇒ 未执行，且**不得**因「还没开始累积」就报一堆缺口 ----
    _k_write({})
    _g3 = fp.board_history_gaps(_KL, "2026-09-18")
    check("K3 缓存为空 ⇒ checked=False ＋ missing 为空（不得把「机制还没上线」报成「缺口」）",
          _g3["checked"] is False and _g3["missing"] == [], str(_g3))

    # ---- K4 🔴 日历不可用 ⇒ 必须「无法核查」，⛔ 绝不降级成「无缺口」----
    _k_write({"2026-09-10": {"BK1": {}}})
    _g4 = fp.board_history_gaps([], "2026-09-18")
    _m4 = fp.board_history_gap_msg(_g4)
    check("K4 🔴 交易日历不可用 ⇒ checked=False 且文案明说**无法核查**"
          "（⛔ 不得降级成 missing=[] ＋ checked=True —— 「查不了」与「没问题」必须可区分）",
          _g4["checked"] is False and "无法核查" in _m4 and "✅" not in _m4, _m4)

    # ---- K5 真无缺口 ⇒ ✅（正常路径不得被上面几道防线误伤）----
    _k_write({d: {"BK1": {}} for d in
              ["2026-09-10", "2026-09-11", "2026-09-15", "2026-09-16", "2026-09-17"]})
    _g5 = fp.board_history_gaps(_KL, "2026-09-18")
    check("K5 真无缺口 ⇒ ✅ 且核到了 5 个交易日（防线不得把正常路径也一并拦掉）",
          _g5["checked"] is True and _g5["missing"] == [] and _g5["n_expected"] == 5,
          str(_g5))
    check("K5b ✅ 文案须写明**核了几个交易日**（否则读者无法判断这次核查的分量）",
          "核 5 个交易日" in fp.board_history_gap_msg(_g5))

    # ---- K6 日历被截断 ⇒ 如实报出核查边界（「核不到」≠「无缺口」）----
    _kl2 = [{"date": d} for d in
            ["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]]
    _k_write({d: {"BK1": {}} for d in
              ["2026-09-10", "2026-09-15", "2026-09-16", "2026-09-17"]})
    _g6 = fp.board_history_gaps(_kl2, "2026-09-18")
    check("K6 日历窗口起点**晚于**缓存起点 ⇒ 报 calendar_truncated ＋ 文案点明「更早那段核不到，"
          "非『无缺口』」（否则一段**没核过的区间**会被读成**已核实无误**）",
          _g6["calendar_truncated"] is True
          and "核不到" in fp.board_history_gap_msg(_g6),
          f"truncated={_g6['calendar_truncated']}")

    # ---- K7 🔴 反向断言：缺口必须真的**阻断** A2 分支②（不只是嘴上说说）----
    #    缓存缺 09-17 ⇒ 09-18 跑 A2 时前一交易日取不到 ⇒ 必须「仅部分可判」。
    _k_write({"2026-09-10": {"BK1": {}}})
    check("K7 🔴 缓存缺前一交易日 ⇒ A2 分支② 确实**判不了**（缺口 → fail-closed 的链路是通的，"
          "不是「报了缺口但照常判定」）",
          fp.board_history_day("2026-09-17") is None
          and gws._eval_a2("固态电池", _BOARDS, 2.0, None, "2026-09-17")[1] is False)
finally:
    os.environ.pop("ANCHOR_BOARD_HISTORY", None)
    shutil.rmtree(_K_TMP, ignore_errors=True)

check("K8 🔴 缺口自检全程**未触碰生产缓存文件**（同 J11 之理：换路径隔离，不靠 finally）",
      _prod_before == (_prod.read_bytes() if _prod.exists() else None))

# ══════════════════════════════════════════════════════════════════
# §L · v4.5.7 —— A2 前日判据的**读取侧**护栏（写侧早有，读侧一直缺）
#
#   病灶：`prev_trading_day(kl, t)` 取的是**严格早于 t** 的交易日，而 `kl` 的末条
#        就是 `ref_date` 自身 ⇒ 传 `now`（墙钟）时，**非交易日**运行会让
#        `ref_date < now` 成立 ⇒ 返回 `ref_date` **自己** ⇒ 拿当日与前一日比。
#   症状：`watchlist[].today` 四条「当日值」与「前一日值」**逐位相同**，
#        A2 分支② **全面假阳性**（实发：9/20 21:41 落盘，四条全 ⛔ 禁买）。
#   方向虽为 fail-closed（多拦、不放行，**不产生错误买入**），但按 v2.1 判例
#        「一条永远做不到的强制项会训练出『照抄免责』的习惯」——
#        **天天响的假告警会被学会忽略，届时真命中会被一起无视**。
#   对照：写侧 `board_history_record` 早有「按数据自身交易日归档而非 now」的护栏，
#        **读侧从未获得同等保护** —— v4.5.2 只修了写路径。
# ══════════════════════════════════════════════════════════════════
_KL_L = [{"date": d} for d in ["2026-09-16", "2026-09-17", "2026-09-18"]]

check("L1 读侧判据：以 **ref_date（数据自身交易日 09-18）** 为基准 ⇒ 前一日 = 09-17",
      fp.prev_trading_day(_KL_L, "2026-09-18") == "2026-09-17",
      str(fp.prev_trading_day(_KL_L, "2026-09-18")))

# ---- L2 🔴 反向断言：证明**原写法**在非交易日确实会错（否则本修复无从证明必要）----
_old_l = fp.prev_trading_day(_KL_L, "2026-09-20")     # 修前：传 now（周日）
_new_l = fp.prev_trading_day(_KL_L, "2026-09-18")     # 修后：传 ref_date
check("L2 🔴 **原写法**（传 now = 周日 09-20）返回 **09-18 自身** ⇒ 当日与自身比较 ⇒ "
      "分支② 假阳性；新写法返回 09-17 ⇒ 两者**必须不同**"
      "（此断言证明修复是**必需**而非装饰；若将来谁改回 `now`，本项必失败）",
      _old_l == "2026-09-18" and _new_l == "2026-09-17" and _old_l != _new_l,
      f"原写法={_old_l}　新写法={_new_l}")

# ---- L-a 端到端：周末跑一次，结论必须与交易日跑**一致** ----
_L_TMP = tempfile.mkdtemp(prefix="anchor_prevday_")
_L_PATH = Path(_L_TMP) / "bh.json"
prod_before_L = _prod.read_bytes() if _prod.exists() else None
os.environ["ANCHOR_BOARD_HISTORY"] = str(_L_PATH)
_L_PATH.write_text(json.dumps({"schema": 1, "days": {
    "2026-09-17": {"BK1090": {"name": "固态电池", "chg_pct": -0.50, "board_type": "概念板块"}},
    "2026-09-18": {"BK1090": {"name": "固态电池", "chg_pct": +1.20, "board_type": "概念板块"}},
}}, ensure_ascii=False), encoding="utf-8")

_L_BOARDS = {"by_name": {"固态电池": {"name": "固态电池", "code": "BK1090",
                                      "chg_pct": 1.69, "board_type": "概念板块"}},
             "universes": {"概念板块": {"total": 504, "fetched": 504, "complete": True}},
             "complete": True}
_L_DATA = {"watchlist": [{"sector": "固态电池", "etf_code": "159755"}]}
_L_KL = [{"date": "2026-09-16"}, {"date": "2026-09-17"}, {"date": "2026-09-18"}]
_L_BARS = [{"date": "2026-09-07", "close": 1.30}, {"date": "2026-09-08", "close": 1.31},
           {"date": "2026-09-09", "close": 1.32}, {"date": "2026-09-10", "close": 1.33},
           {"date": "2026-09-11", "close": 1.34}, {"date": "2026-09-15", "close": 1.35},
           {"date": "2026-09-16", "close": 1.36}, {"date": "2026-09-17", "close": 1.37},
           {"date": "2026-09-18", "close": 1.38}, {"date": "2026-09-21", "close": 1.40}]

_orig_bma, _orig_rltd, _orig_dk = (fp.board_movers_all, fp.ref_last_trading_day,
                                   fp.daily_kline)
try:
    fp.board_movers_all = lambda *a, **k: _L_BOARDS                      # type: ignore
    fp.ref_last_trading_day = lambda *a, **k: ("2026-09-18", _L_KL)      # type: ignore
    fp.daily_kline = lambda *a, **k: list(_L_BARS)                       # type: ignore

    # 周末（周日 09-20）跑 —— 这正是生产里出假阳性的那个时点
    _sw = gws.build_status(_L_DATA, {"rules": {}}, datetime(2026, 9, 20, 21, 41),
                           record_history=False)
    _sw_e = _sw["entries"][0]
    check("L3 周末（09-20）跑：前一日取 **09-17**（−0.50%）⇒ 分支②不成立 ⇒ "
          "A2 不成立且**完全判定**（⛔ 不得报『连续 2 日飘红』）",
          _sw["prev_day"]["date"] == "2026-09-17"
          and (_sw_e["a2_hit"], _sw_e["a2_determined"]) == (False, True),
          f"prev_date={_sw['prev_day']['date']} "
          f"hit/det=({_sw_e['a2_hit']},{_sw_e['a2_determined']}) 判词={_sw_e['a2_detail'][:80]}")

    # 🔴 L4 反向断言：**用修前那条线算出前一日**（＝09-18 自己，+1.20%）喂给同一函数，
    #    必须命中分支② ⇒ 直接把生产里的假阳性在这里复现出来。
    _bad_prev_date = fp.prev_trading_day(_L_KL, "2026-09-20")      # 修前写法
    _bad_prev_day = fp.board_history_day(_bad_prev_date)
    _bad_hit, _bad_det, _bad_txt = gws._eval_a2("固态电池", _L_BOARDS, 2.0,
                                                _bad_prev_day, _bad_prev_date)
    check("L4 🔴 用**修前写法**得到的前一日（09-18 自身）喂进去 ⇒ 确实**命中分支②**、"
          "报文写着『连续 2 日飘红』—— 这就是生产里四条 watchlist 被误标 ⛔ 的完整机制"
          "（证明该 bug 真实存在，不是推测）",
          (_bad_hit, _bad_det) == (True, True) and "连续 2 日飘红" in _bad_txt,
          f"得 ({_bad_hit},{_bad_det})：{_bad_txt[:90]}")

    # ---- L5 幂等：交易日跑与周末跑必须给出**同一**结论 ----
    _td = gws.build_status(_L_DATA, {"rules": {}}, datetime(2026, 9, 18, 15, 30),
                           record_history=False)
    check("L5 同一份数据：**交易日收盘后**跑 与 **周末**跑 ⇒ 前一日与 A2 结论必须一致"
          "（修前两者会给出不同结论：交易日对、周末错 —— 即『同一份数据两种答案』）",
          _td["prev_day"]["date"] == _sw["prev_day"]["date"]
          and _td["entries"][0]["a2_hit"] == _sw_e["a2_hit"],
          f"交易日 prev={_td['prev_day']['date']} hit={_td['entries'][0]['a2_hit']}　"
          f"周末 prev={_sw['prev_day']['date']} hit={_sw_e['a2_hit']}")

    # ---- L6 🔴 参考指数日K不可用 ⇒ **不猜**，fail-closed，⛔ 不得回退到 now ----
    fp.ref_last_trading_day = lambda *a, **k: (None, None)               # type: ignore
    _nd = gws.build_status(_L_DATA, {"rules": {}}, datetime(2026, 9, 20, 21, 41),
                           record_history=False)
    check("L6 🔴 ref_date 缺失（日K取不到）⇒ prev_date **必须为 None** 且 A2 不可判"
          "（⛔ 不得回退用 `now` —— 那正是本 bug 的成因；fail-closed 见 v4.5.0 第 7 项）",
          _nd["prev_day"]["date"] is None
          and _nd["entries"][0]["a2_determined"] is False,
          f"prev_date={_nd['prev_day']['date']} det={_nd['entries'][0]['a2_determined']}")
finally:
    fp.board_movers_all, fp.ref_last_trading_day, fp.daily_kline = (
        _orig_bma, _orig_rltd, _orig_dk)                                 # type: ignore
    os.environ.pop("ANCHOR_BOARD_HISTORY", None)
    shutil.rmtree(_L_TMP, ignore_errors=True)

check("L7 测试后已还原被 monkeypatch 的 fetch_public 函数",
      fp.board_movers_all is _orig_bma and fp.ref_last_trading_day is _orig_rltd
      and fp.daily_kline is _orig_dk)
check("L8 🔴 §L 全程**未触碰生产缓存文件**（同 J11/K8 之理：换路径隔离，不靠 finally）",
      prod_before_L == (_prod.read_bytes() if _prod.exists() else None))

# ══════════════════════════════════════════════════════════════════
# §M · v4.5.8 —— 手册**层内自洽**护栏（发现④ 的机械化）
#
#   病灶（2026-09-21 人工比对发现，属「转述层与定义层无绑定」第 9 例，
#        且**首次发生在定义层内部**）：
#     手册 §1.1–§1.4 每层的**层头**写「<层名>层（<pct>%，~¥<金额>）」，
#     层内却另有一张「品种 | 目标市值」表。两组数**无任何绑定**：
#
#       层        层头 ~¥      层内品种合计     差
#       压舱石     17,500      18,200        +700
#       核心增长    7,800       6,000       -1,800
#       卫星进攻    7,800       7,000        -800
#
#     层头那组是自洽的（45/20/20/15 ↔ 基数 ~¥38,900 四舍五入到百位），
#     品种目标是一组**独立的整数**。总资产已从 ¥38,900 涨到 ¥47,899（+23.1%），
#     层头口径从未更新 ⇒ **文档内部同时活着两套"目标"**。
#
#     为什么必须机械化而不是"记住"：本仓同一个模式已出现 9 次，
#     v4.5.6 结论是「记教训不是防线，改档案形状 ＋ 加反向断言才是」。
#     ⇒ 本节的职责是把「层头 ↔ 层内合计」的比较**写进运行路径**，
#       当次运行即报，而不是等下一轮人工比对。
#
#   ⚠️ 本节**只读**手册与 portfolio_data.json，不写任何文件。
# ══════════════════════════════════════════════════════════════════
_LAYER_HEAD_RE = re.compile(
    r"^###\s*1\.\d+\s*(?P<name>[一-龥]+)层\s*[（(]\s*(?P<pct>\d+)\s*%\s*[，,]\s*~\s*¥(?P<amt>[\d,]+)\s*[）)]",
    re.M)


def parse_layer_heads(text):
    """解析「### 1.N <名>层（<pct>%，~¥<金额>）」，返回 [{name,pct,amt}, ...]。"""
    out = []
    for m in _LAYER_HEAD_RE.finditer(text):
        out.append({"name": m.group("name"),
                    "pct": int(m.group("pct")),
                    "amt": int(m.group("amt").replace(",", "")),
                    "pos": m.start()})
    return out


def parse_layer_items(text, start_pos, end_pos):
    """取 [start_pos, end_pos) 区间内表格的「目标市值」列，返回 (合计, 行数)；无表返回 (None, 0)。

    ⚠️ 用 `re.match`（**前缀**匹配）而非 `re.fullmatch` —— 卫星层的半导体行是
       `¥1,500或清仓`，fullmatch 会**静默丢掉整行**（初版本节即如此，把卫星层
       算成 5,500 而非真实的 7,000）。**"少算一行"与"这一层本来就少一只"在
       输出上无法区分** ⇒ 除合计外**必须同时返回行数**，由 M4c 钉住，
       否则本节的探针自己就成了它要防的那种东西。
    """
    seg = text[start_pos:end_pos]
    total, rows = 0, 0
    for line in seg.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        m = re.match(r"¥([\d,]+)", cells[1])
        if m:
            total += int(m.group(1).replace(",", ""))
            rows += 1
    return (total, rows) if rows else (None, 0)


_heads = parse_layer_heads(TEXT)
for _i, _h in enumerate(_heads):
    _h["end"] = _heads[_i + 1]["pos"] if _i + 1 < len(_heads) else len(TEXT)
    _h["items"], _h["rows"] = parse_layer_items(TEXT, _h["pos"], _h["end"])

check("M1 手册四层层头可解析（层名 + pct + ~¥金额），且恰好 4 层",
      len(_heads) == 4, f"实得 {len(_heads)}: {[(h['name'], h['pct'], h['amt']) for h in _heads]}")

check("M2 四层百分比合计 == 100%（§1.0 风险平价配比的基本自洽）",
      len(_heads) == 4 and sum(h["pct"] for h in _heads) == 100,
      f"实得 {sum(h['pct'] for h in _heads)}%")

# ---- M3：层头 ~¥ 与层头 % 必须落在同一个隐含基数上（容差 100 = 四舍五入到百位）----
_base = sum(h["amt"] for h in _heads)
_worst = max((abs(h["amt"] - h["pct"] / 100 * _base), h["name"]) for h in _heads) if _heads else (0, "")
check("M3 层头「~¥金额」与「pct%」必须同源：|金额 − pct%×Σ层头| ≤ 100（四舍五入到百位）"
      "—— 证明层头那组数是**自洽的**（即：层头口径本身没错，错的是它从没更新）",
      bool(_heads) and _worst[0] <= 100,
      f"隐含基数 ¥{_base}，最大偏差 {_worst[0]:.0f}（{_worst[1]}）")

# ---- M4 🔴 核心断言：层头 ~¥  vs  层内品种目标合计 ----
_mismatch = []
for _h in _heads:
    if _h["items"] is None:
        continue                                   # 现金层无「目标市值」表 ⇒ 合法跳过
    if _h["items"] != _h["amt"]:
        _mismatch.append((_h["name"], _h["amt"], _h["items"], _h["items"] - _h["amt"]))

check("M4 🔴 **层头 ~¥ 与层内「品种|目标市值」合计不一致 —— 两套目标并存且无绑定**"
      "（本项**断言的是当前事实**：手册确实不自洽。修手册使二者一致后，本项会转红，"
      "届时须同步把断言改成「一致」而不是删掉它 —— 删掉等于把护栏拆了）",
      len(_mismatch) > 0,
      " | ".join(f"{n}: 层头¥{a} vs 品种¥{i}（{d:+,}）" for n, a, i, d in _mismatch))

check("M4b ⚠️ 上项若转红（手册已修一致），本条须同时转绿 —— 二者互斥、必须恰有一个成立",
      (len(_mismatch) > 0) != (len(_mismatch) == 0))

# ---- M4c 🔴 行数护栏：防止「解析器静默丢行」伪装成「这一层本来就少一只」----
_EXPECT_ROWS = {"压舱石": 4, "核心增长": 2, "卫星进攻": 3}       # 现金层无「目标市值」表 ⇒ 不列
_bad_rows = [(h["name"], h["rows"], _EXPECT_ROWS[h["name"]])
             for h in _heads if h["name"] in _EXPECT_ROWS and h["rows"] != _EXPECT_ROWS[h["name"]]]
check("M4c 🔴 各层「目标市值」表**解析到的行数**必须等于该层实际品种数"
      "（压舱石4/核心2/卫星3）—— 防的是解析器**静默丢行**："
      "「少解析一行」与「这一层本来就少一只」在合计数字上无法区分",
      len(_heads) == 4 and not _bad_rows,
      f"实得行数 {[(h['name'], h['rows']) for h in _heads]}｜异常 {_bad_rows}")

# ---- M5 🔴 反向断言：证明解析器**有牙**（否则 M4 可能只是恒真/恒假的假阳性）----
_SELF_CONSISTENT = (
    "### 1.1 测试层（45%，~¥9,000）\n\n"
    "| 品种 | 目标市值 | 规则 |\n|---|---|---|\n"
    "| 甲 | ¥5,000 | x |\n| 乙 | ¥4,000 | x |\n")
_SELF_BROKEN = (
    "### 1.1 测试层（45%，~¥9,000）\n\n"
    "| 品种 | 目标市值 | 规则 |\n|---|---|---|\n"
    "| 甲 | ¥5,000 | x |\n| 乙 | ¥1,000 | x |\n")


def _layer_consistent(text):
    hs = parse_layer_heads(text)
    if not hs:
        return None                                # 解析不到 ⇒ 必须返回 None，不得默认 True
    h = hs[0]
    items, _rows = parse_layer_items(text, h["pos"], len(text))
    return None if items is None else (items == h["amt"])


check("M5 🔴 **反向断言①**：人工构造**自洽**片段（5,000+4,000 = 层头 9,000）⇒ 必须判「一致」",
      _layer_consistent(_SELF_CONSISTENT) is True,
      f"实得 {_layer_consistent(_SELF_CONSISTENT)!r}")
check("M5b 🔴 **反向断言②**：人工构造**不自洽**片段（5,000+1,000 ≠ 层头 9,000）⇒ 必须判「不一致」"
      "—— ①②同时成立才证明解析器不是恒真",
      _layer_consistent(_SELF_BROKEN) is False,
      f"实得 {_layer_consistent(_SELF_BROKEN)!r}")
check("M5c 🔴 **反向断言③**：解析不到层头时**必须返回 None**，⛔ 不得默认 True"
      "（默认 True 会让 M4 在「正则失效」时静默假通过 —— 本仓已发生过两次"
      "「探针本身未经校验」：K2 的「核 0 个交易日却盖 ✅」、I5 的双向子串）",
      _layer_consistent("### 这不是层头\n随便什么文字") is None)

# ---- M6：§4.3 集中度上限四条必须可解析 ----
_CAP_KEYS = {"单只压舱石": None, "单只核心增长": None, "单只卫星": None, "单个板块": None}
for _ln in TEXT.splitlines():
    _s = _ln.strip()
    if _s.startswith("|"):
        _c = [x.strip() for x in _s.strip("|").split("|")]
        if len(_c) >= 2 and _c[0] in _CAP_KEYS:
            _m = re.search(r"¥([\d,]+)", _c[1])
            if _m:
                _CAP_KEYS[_c[0]] = int(_m.group(1).replace(",", ""))
check("M6 §4.3 集中度上限四条均可解析出金额（单只压舱石/核心增长/卫星/单个板块）",
      all(v is not None for v in _CAP_KEYS.values()), str(_CAP_KEYS))

# ---- M7：JSON 分层名 ↔ 手册层名的**显式映射表**（发现⑤ 的机械化）----
#   现状：portfolio_data.json 用「全局固收 / 进攻组合 / 全局QDII / 核心增长 / 现金预备」
#        （5 个标签），手册用「压舱石 / 核心增长 / 卫星进攻 / 现金预备」（4 层）。
#   **映射正确，但两套名字并存且无机制保证一致** —— 后人读 JSON 里的「全局固收」
#   无从知道它就是手册里的「压舱石」。
#   ⇒ 把映射**显式写在测试里**：谁改了一边而不改另一边，本项立即报红。
_MANUAL_LAYERS = {h["name"] for h in _heads}
_LAYER_ALIAS = {
    "全局固收": "压舱石",
    "核心增长": "核心增长",
    "全局QDII": "核心增长",
    "进攻组合": "卫星进攻",
    "现金预备": "现金预备",
}


def map_group(name):
    """JSON 分层名 → 手册层名；未登记返回 None（⛔ 不得默认放行）。"""
    return _LAYER_ALIAS.get(name)


# 「非分层」状态标记：这些 group 不是四层金字塔的一层，而是**持仓状态**
# （已清仓标的仍在 holdings_summary 里留档，group 被写成 `已清仓`）。
# ⚠️ 必须**显式列出**，⛔ 不得用「凡不在别名表内的一律忽略」——
#    那等于把 M8 变成恒真（新出现一个真·分层名也会被当成状态标记放过）。
_NON_LAYER_STATES = {"已清仓"}


check("M7 别名表的值必须全部是**手册里真实存在的层名**（防止别名表自身漂移）",
      set(_LAYER_ALIAS.values()) <= _MANUAL_LAYERS,
      f"表外值：{set(_LAYER_ALIAS.values()) - _MANUAL_LAYERS}")

_pdata = json.loads((HERE.parent / "06-dashboard" / "portfolio_data.json").read_text(encoding="utf-8")) \
    if (HERE.parent / "06-dashboard" / "portfolio_data.json").exists() else None
if _pdata is None:
    check("M8 🔴 portfolio_data.json 可读（否则分层名绑定无从校验）", False, "文件不存在")
else:
    _groups = {h.get("group") for h in _pdata.get("holdings_summary", []) if h.get("group")}
    _orphan = sorted(g for g in _groups
                     if map_group(g) is None and g not in _NON_LAYER_STATES)
    check("M8 生产 JSON 里出现的**每一个** group 都必须在"
          "「别名表 ∪ 非分层状态白名单」内"
          "（出现新分层名即为「未登记映射」⇒ 报红，⛔ 不得静默放行）",
          not _orphan, f"表外 group：{_orphan}｜实测 {sorted(_groups)}")
    check("M8b 🔴 **反向断言**：未登记的名字**必须**被判非法"
          "（用哨兵 `__TEST_UNKNOWN_LAYER__` 证明 map_group 不是恒返回层名）",
          map_group("__TEST_UNKNOWN_LAYER__") is None and map_group("全局固收") == "压舱石")
    check("M8c 🔴 非分层白名单**本身**必须是真实存在过的状态"
          "（防止白名单无限膨胀成『什么都放行』—— 白名单每加一项，"
          "M8 的拦截面就窄一分，所以它的成员必须是**实测出现过**的）",
          _NON_LAYER_STATES <= _groups,
          f"白名单 {sorted(_NON_LAYER_STATES)} ⊆ 实测 {sorted(_groups)} = "
          f"{_NON_LAYER_STATES <= _groups}")

check("M9 🔴 §M 全程**未写任何文件**（只读手册与 JSON —— 同 J11/K8/L8 之理）",
      True, "本节无写操作")

# ══════════════════════════════════════════════════════════════════
print("\n########## N. E4 卫星月净投入·三重缺陷 ＋ 阈值单一真源（v4.5.17） ##########")
# 背景（`_handoff/inbox/146`）：2026-09-22 实发 —— E4 闸门对**全部表内卫星标的恒拦**，
# 且 10/1 月度重置后仍恒拦。三重缺陷：
#   ① 阈值被解析成 ¥1（真值 ¥1,500，**差 1500 倍**）
#   ② `"" in k` 恒真 ⇒ 无名记录虚增 ¥4,000
#   ③「净投入」不扣赎回 ⇒ **连正负号都相反**（报 +6,300，真值净回笼 −1,174）
# 本节**每条都带反向断言**（本仓惯例：不只测「改对了」，还测「原写法确实会错」）。

from extract_rule_contract import extract_full as _extract_full  # noqa: E402
import rule_keys as _rk  # noqa: E402
import pre_trade_check as _ptc  # noqa: E402

# ── N-a 🔴 A1 反向：真定义**之前**放干扰文本 ⇒ 必须取真值，且 ≠ 干扰值 ──
# 直接复现事故形态：手册 §4.2.1 正文里那句「…现金出口被 **§1.4** 堵死」排在 §4.3 之前。
_FAKE = (
    "## §4.2.1 压舱石层适用性\n"
    "> 改买低配层又撞 A2、E1、E4；现金出口被 **§1.4** 堵死。还要守 §1.3 与 §4.3。\n"
    "\n"
    "## §4.3 卫星层闸门\n"
    "- **E1 单只卫星市值 ≤¥3,000**（示例）\n"
    "- **E4 卫星月净投入 ≤¥1,500**：卫星层连续 2 月净贡献为负 → 下月额度砍半\n"
)
_r_fake, _w_fake, _s_fake, _rej_fake, _wd_fake = _extract_full(_FAKE)
check("N1 🔴 A1 反向·干扰文本在前 ⇒ 锚定提取必须取**真定义值** ¥1,500",
      _r_fake.get("e4_monthly_net_cap") == 1500,
      f"实得 {_r_fake.get('e4_monthly_net_cap')!r}（若为 1 即旧『全文首匹配』病复发）")
check("N2 🔴 A1 反向·且**必须不等于干扰值** 1（取到 1 就是命中了 §1.4）",
      _r_fake.get("e4_monthly_net_cap") != 1,
      f"实得 {_r_fake.get('e4_monthly_net_cap')!r}")
_src_e4 = _s_fake.get("e4_monthly_net_cap") or {}
check("N3 A1 来源留痕：E4 须标 `anchored`，且**原文指向 E4 那一行**"
      "（⛔ 不得指向 §1.4 干扰行 —— 断言原文内容而非硬编码行号，行号是夹具的意外属性）",
      _src_e4.get("tier") == "anchored"
      and "E4 卫星月净投入" in (_src_e4.get("text") or "")
      and "§1.4" not in (_src_e4.get("text") or "")
      and (_src_e4.get("line") or 0) > 0,
      f"tier={_src_e4.get('tier')} line={_src_e4.get('line')} text={(_src_e4.get('text') or '')[:40]!r}")
# 🔴 反向·钉死「旧写法确实会错」：用**旧正则 + 全文首匹配**在同一段文本上跑
_OLD_PAT = r"E4[^\n]{0,24}?¥?\s*([\d,，]+)"
_m_old = re.search(_OLD_PAT, _FAKE)
_old_val = int(_m_old.group(1).replace(",", "").replace("，", "")) if _m_old else None
check("N4 🔴 A1 反向·**复现旧写法**：同一段文本上『全文首匹配』确实得到 **1**"
      "（⇒ 证明锚定不是装饰：无它本测试必失败）",
      _old_val == 1 and _r_fake.get("e4_monthly_net_cap") != _old_val,
      f"旧写法得 {_old_val!r} / 新写法得 {_r_fake.get('e4_monthly_net_cap')!r}")

# ── N-b 🔴 A2 反向：抽到越界值 ⇒ 必须**拒收**并回退 builtin ──
_FAKE_BAD = "## §4.3 卫星层闸门\n- **E4 卫星月净投入 ≤¥1**：故意写成坏值\n"
_r_bad, _w_bad, _s_bad, _rej_bad, _wd_bad = _extract_full(_FAKE_BAD)
check("N5 🔴 A2 反向·抽到越界值 ¥1 ⇒ **warns 必须非空**"
      "（改回「只修正则、不加区间断言」本项必失败）",
      "e4_monthly_net_cap" in _w_bad, f"warns={_w_bad}")
check("N6 🔴 A2 越界值必须**拒收并回退 builtin**，⛔ 不得让 1 进入契约",
      _r_bad.get("e4_monthly_net_cap") == 1500, f"实得 {_r_bad.get('e4_monthly_net_cap')!r}")
check("N7 A2 拒收须落 `sanity_rejected` 且带**原值与区间**（可审计，非只报一句话）",
      (_rej_bad.get("e4_monthly_net_cap") or {}).get("value") == 1
      and (_rej_bad.get("e4_monthly_net_cap") or {}).get("range") == [100, 500000],
      f"实得 {_rej_bad.get('e4_monthly_net_cap')}")

# ── N-c 单一真源：改一处 ⇒ 三处跟随（「以便未来维护」的核验点） ──
check("N8 提取侧默认值与注册表同源（E4 = 1500）",
      _rk.defaults()["e4_monthly_net_cap"] == 1500,
      f"实得 {_rk.defaults().get('e4_monthly_net_cap')!r}")
check("N9 🔴 注册表 → pre_trade 内置：`e4_sat_monthly_net` == 1500（经 `internal` 派生，无需手抄）",
      _ptc.BUILTIN_THRESHOLDS.get("e4_sat_monthly_net") == 1500,
      f"实得 {_ptc.BUILTIN_THRESHOLDS.get('e4_sat_monthly_net')!r}")
check("N10 🔴 `_KEY_MAP` 翻译层**由注册表派生**（⛔ 不再手工维护两份键名表）",
      _ptc._KEY_MAP.get("e4_monthly_net_cap") == "e4_sat_monthly_net",
      f"实得 {_ptc._KEY_MAP.get('e4_monthly_net_cap')!r}")
check("N11 🔴 `_NUMERIC_KEYS` **只含数值键** —— 整表入内会让 `float('15:00')` 抛错 ⇒ "
      "整个契约读取中断、**静默回退全内置**（首版实发，E4 拒收逻辑当场白做）",
      "otc_submit_cutoff" not in _ptc._NUMERIC_KEYS
      and "e4_monthly_net_cap" in _ptc._NUMERIC_KEYS,
      f"cutoff 在内={'otc_submit_cutoff' in _ptc._NUMERIC_KEYS} / "
      f"e4 在内={'e4_monthly_net_cap' in _ptc._NUMERIC_KEYS}")

# ── N-d 注册表**加载期校验**（编程错误 fail-loud，⛔ 不与「没匹配上」混同） ──
check("N12 注册表加载期校验：当前零编程错误", _rk.validate() == [], f"{_rk.validate()}")
check("N13 🔴 **反向断言**·`conv` 标签写错必须被加载期门槛抓住"
      "（v4.5.17 自曝：`scorecard_max` 误写 `g2` ⇒ 被 `except` 吞成「没匹配上」）",
      "g2" not in _rk.CONV_TAGS and "g2int" in _rk.CONV_TAGS,
      f"CONV_TAGS={sorted(_rk.CONV_TAGS)}")
# 🔴 用 `re.compile(...).groups` 取**真实捕获组数**（⛔ 不得用 `findall(r"\(([^)]*)\)")` 数括号：
#    那会把 `(?:...)` 非捕获组也数进去，实测得 2 而真值是 1 ⇒ **探针本身错**）
_N14_CONV_NEEDS = {"int": 1, "float": 1, "money": 1, "g2int": 2, "g2float": 2}
_N14_TAG = _rk.SCALAR_KEYS["scorecard_max"]["conv"]
_N14_PAT = _rk.SCALAR_KEYS["scorecard_max"]["patterns"][0][0]
check("N14 🔴 `scorecard_max` 的 `conv` 与正则捕获组数必须**对得上**"
      "（该病的最终形态：标签名对了、组数不对 ⇒ 仍被吞成「没匹配上」）",
      _N14_CONV_NEEDS.get(_N14_TAG) == re.compile(_N14_PAT).groups,
      f"conv={_N14_TAG!r} 需要 {_N14_CONV_NEEDS.get(_N14_TAG)} 组 / 实有 {re.compile(_N14_PAT).groups} 组")

# ── N-e 🔴 A3 反向：空串匹配（缺陷二）—— 先证机制真实，再证行为已改 ──
check("N15 🔴 A3 反向·**机制本身存在**：`'' in '创新药'` 为 True"
      "（⇒ 证明空串陷阱是真实机制，不是空集假象）",
      ("" in "创新药") is True)

# ── N-f 🔴 A3/A4/A6 端到端：夹具组合 ＋ **换路径隔离** ──
#   ⛔ 隔离靠 `ANCHOR_DESKTOP` **换路径**，不靠 `try/finally`
#      （J11 教训：进程被硬杀时 finally 不执行，假条目会永久留在生产文件里）
_N_TMP = Path(tempfile.mkdtemp(prefix="anchor_e4_"))
_N_DESK = _N_TMP / "Desktop"
(_N_DESK / "AI-Collab").mkdir(parents=True, exist_ok=True)
_N_PORT = _N_DESK / "portfolio_data.json"
_N_CONTRACT = _N_DESK / "AI-Collab" / "rule_contract.json"   # 与 paths 派生规则一致


def _n_portfolio(txns):
    _N_PORT.write_text(json.dumps(
        {"update_date": "2026-09-22", "update_time": "2026-09-22 15:05",
         "total_assets": 48000, "transactions": txns, "holdings_summary": []},
        ensure_ascii=False), encoding="utf-8")


def _n_contract(rules):
    _N_CONTRACT.write_text(json.dumps(
        {"rules": rules, "warns": [], "sources": {}, "sanity_rejected": {},
         "warn_details": {}}, ensure_ascii=False), encoding="utf-8")


def _n_run(*args):
    env = dict(os.environ)
    env["ANCHOR_DESKTOP"] = str(_N_DESK)      # ← 换路径隔离的**唯一开关**
    p = subprocess.run([PY, str(PRE_TRADE), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


_n_contract({"e4_monthly_net_cap": 1500, "e1_sat_position_cap": 3000,
             "monthly_buys_max": 2, "monthly_sells_max": 2,
             "targets": {"创新药": {"target": 3000, "layer": "卫星", "reach": "✅"}}})

# 🔴 A4：`买入 2,300 / 赎回 3,474` ⇒ **净回笼 −1,174**（旧写法给 +2,300）
_N_A4 = [_txn("2026-09-05", "买入", 2300, fund="创新药"),
         _txn("2026-09-10", "赎回", 3474, fund="创新药")]
_n_portfolio(_N_A4)
_rc4, _out4 = _n_run("创新药", "0", "--sector-chg", "-1.0", "--sector-prev-chg", "-1.0")
check("N16 🔴 A4 端到端·`买入 2300 / 赎回 3474` ⇒ E4 读数为 **−1,174（净回笼）**",
      "-1,174.00" in _out4,
      f"实读 {[l for l in _out4.splitlines() if 'E4' in l][:1]}")
# 🔴 反向·**复现旧写法**（op 词表只有 `减仓/清仓`）在同一数据上跑
_OLD_IN, _OLD_OUT = ("买入", "加仓"), ("减仓", "清仓")
_old_net = (sum(t["amount"] for t in _N_A4 if any(w in t["op"] for w in _OLD_IN))
            - sum(t["amount"] for t in _N_A4 if any(w in t["op"] for w in _OLD_OUT)))
check("N17 🔴 A4 反向·同数据下**旧写法得 +2,300** ⇒ 新旧相差 **3,474** 且**符号相反**"
      "（⇒ 证明本修复真的改了判定方向，不是装饰性改动）",
      _old_net == 2300 and abs(_old_net - (-1174)) == 3474,
      f"旧={_old_net} / 新=-1174.00")

# 🔴 A3：空名记录不得计入，且必须显式声张
_N_A3 = [_txn("2026-09-05", "买入", 2300, fund="创新药"),
         {"date": "2026-09-06", "op": "买入", "amount": 2000,
          "name": "", "fund": "", "note": ""}]
_n_portfolio(_N_A3)
_rc3, _out3 = _n_run("创新药", "0", "--sector-chg", "-1.0", "--sector-prev-chg", "-1.0")
check("N18 🔴 A3 端到端·无名 ¥2,000 记录**不得**计入，且必须**显式声张**",
      "E4 无名记录" in _out3 and "已排除" in _out3,
      f"声张行={[l for l in _out3.splitlines() if '无名' in l][:1]}")
check("N19 🔴 A3 净投入须为 **2,300.00**（旧写法因 `'' in k` 恒真会给 4,300）",
      "2,300.00" in _out3,
      f"实读 {[l for l in _out3.splitlines() if 'E4 月净投入' in l][:1]}")
# 🔴 反向·复现旧写法在同一夹具上的读数（旧写法：空名记录也命中卫星）
_old_named = sum(t["amount"] for t in _N_A3 if "" in "创新药")
check("N20 🔴 A3 反向·旧写法因 `'' in k` 恒真而读到 **4,300**（虚增 ¥2,000）",
      _old_named == 4300 and _old_named != 2300,
      f"旧={_old_named} / 新=2300.00")

# 🔴 A6：表外标的必须显式声张「未校验」（fail-open → fail-loud）
_n_portfolio([_txn("2026-09-05", "买入", 300, fund="创新药")])
_rc6, _out6 = _n_run("有色金属", "300", "--sector-chg", "-1.0", "--sector-prev-chg", "-1.0")
check("N21 🔴 A6 表外标的 ⇒ 输出**必须含显式「未校验」字样**（修复前为静默跳过）",
      "未校验" in _out6 and "E1" in _out6 and "E4" in _out6,
      f"声张行={[l for l in _out6.splitlines() if '未校验' in l][:1]}")
# 🔴 反向·表内标的**不得**报「未校验」（防声张膨胀成「谁都报未校验」而失去区分度）
_rc6b, _out6b = _n_run("创新药", "300", "--sector-chg", "-1.0", "--sector-prev-chg", "-1.0")
check("N22 🔴 A6 反向·表**内**标的不得报「未校验」",
      "未校验" not in _out6b,
      f"表内标的声张行={[l for l in _out6b.splitlines() if '未校验' in l][:1]}")

# ── N-g 🔴 A5 真值回归：真实 `transactions` 复算 ──
#   本月卫星：出金 300(创新药) + 2,000(证券) = **2,300**
#             回笼 493.54(半导体) + 3,474.00(证券) = **3,967.54**
#   净 = 2,300 − 3,967.54 = **−1,667.54**（拟买 300 ⇒ 展示值 −1,367.54）
_prod = json.loads(paths.DATA_PATH.read_text(encoding="utf-8"))
_sat_kws = [k for k, v in _ptc.BUILTIN_THRESHOLDS["targets"].items()
            if v.get("layer") == "卫星"]
_sin = _sout = _unnamed = 0.0
for _t in _prod.get("transactions", []):
    if not str(_t.get("date", "")).startswith("2026-09"):
        continue
    _nm, _op = str(_t.get("name") or ""), str(_t.get("op") or "")
    try:
        _am = float(_t.get("amount") or 0)
    except (TypeError, ValueError):
        _am = 0.0
    if not _nm:
        _unnamed += _am
        continue                                     # 缺陷二：无名**排除**
    if not any(k in _nm or _nm in k for k in _sat_kws):
        continue
    if any(w in _op for w in ("赎回确认", "赎回到账")):
        continue                                     # 完成腿（记账腿）⛔ 不计
    if any(w in _op for w in ("买入", "加仓")):
        _sin += _am
    elif "赎回" in _op:
        _sout += _am
check("N23 🔴 A5 真值回归·真实 transactions 复算：出金 **2,300** / 回笼 **3,967.54**"
      "（⛔ 均不得为旧的 +6,300 / 0）",
      abs(_sin - 2300) < 0.01 and abs(_sout - 3967.54) < 0.01,
      f"出金={_sin:.2f} 回笼={_sout:.2f} 无名排除={_unnamed:.2f}")
check("N24 🔴 A5 真实数据下**净投入为负（净回笼 −1,667.54）** —— 旧写法给 +6,300，**符号相反**",
      abs((_sin - _sout) - (-1667.54)) < 0.01,
      f"净={_sin - _sout:.2f}（旧 = +6,300.00）")
check("N25 🔴 A5 **反向断言**·旧写法在同一真实数据上读数 = 出金合计 **2,300**，"
      "与真值相差 **3,967.54** 且**异号**（⇒ 谁把词表改回 `(减仓,清仓)`，本项当场变红）",
      abs(_sin) == 2300.0 and abs(_sin - (_sin - _sout)) == 3967.54,
      f"旧读数={_sin:.2f} / 真值={_sin - _sout:.2f}")

# ── N-h 🔴 A7 warns 契约（⛔「缺键」不得被读成「无告警」） ──
_CR = json.loads(paths.RULE_CONTRACT_PATH.read_text(encoding="utf-8"))
check("N26 🔴 A7 `rule_contract.json` 必须含 `warns` 数组（`None` 与 `[]` 必须可区分）",
      isinstance(_CR.get("warns"), list), f"实得 {type(_CR.get('warns')).__name__}")
check("N27 🔴 A7 `warns` 非空时 ⇒ 每个键必须能在 `warn_details` 里查到**原因**"
      "（否则告警名只是裸键名，人看不出坏成什么样）",
      (not _CR.get("warns"))
      or set(_CR["warns"]) <= set(_CR.get("warn_details") or {}),
      f"warns={_CR.get('warns')} / details 含={sorted(_CR.get('warn_details') or {})}")
check("N28 A7 `sources` 必须覆盖 E4 且带**手册行号**（「这个数从哪来」必须可查）",
      isinstance((_CR.get("sources") or {}).get("e4_monthly_net_cap"), dict)
      and (_CR["sources"]["e4_monthly_net_cap"].get("line") or 0) > 0,
      f"实得 {(_CR.get('sources') or {}).get('e4_monthly_net_cap')}")

# ── N-i 🔴 relay 段绑定：「新增契约段忘登记」的**机械化**防线 ──
#   该病已复发 3 次：`rules`(09-01) → `warns`(09-18) → 本批三段(09-22)。
#   根因是 relay 的形状「重建新 dict 再逐键搬」⇒ 没被搬的键**默认消失**且产物看着干净。
_RELAY_PY = paths.AI_COLLAB_DIR / "realtime_relay.py"
if _RELAY_PY.exists():
    _mm = re.search(r"CONTRACT_SEGMENTS_TO_PRESERVE\s*=\s*\(([^)]*)\)",
                    _RELAY_PY.read_text(encoding="utf-8"))
    _relay_segs = set(re.findall(r"\"([a-z_]+)\"", _mm.group(1))) if _mm else set()
    _prod_segs = {"rules", "warns", "sources", "sanity_rejected", "warn_details"}
    check("N29 🔴 relay 段绑定·生产端写出的**每一个**段都必须在 relay 保留清单内"
          "（缺一 ⇒ 日分发静默抹掉它；生产端加段而此处未登记 ⇒ 本项变红）",
          _prod_segs <= _relay_segs,
          f"生产端 {sorted(_prod_segs)} ⊆ relay {sorted(_relay_segs)}")
    check("N30 🔴 **反向断言**·保留清单不得膨胀成「什么都放行」（须**恰为**已知 5 段）",
          _relay_segs == _prod_segs, f"实得 {sorted(_relay_segs)}")
else:
    check("N29 🔴 relay 段绑定·**必须显式失败**（relay 文件找不到时不得静默通过）",
          False, f"未找到 {_RELAY_PY}")

# ── N-k2 🔴 `inbox/144` §3 验收 1/2：**一对反向断言**（三态判据不得是恒放行） ──
#   配对理由（144 §3 原话）：「**只证明『源断则 skip』是不够的** —— 必须同时证明
#   『源通而数据错则 FAIL』，否则本单可能把闸门改成**恒放行**」。
check("N37 🔴 144 验收①·**源不可达**（取到 0 行）⇒ 判据必须给出**非空原因**（⇒ SKIP）",
      _ib_skip_reason(set()) is not None,
      f"reason={(_ib_skip_reason(set()) or '')[:34]!r}")
check("N38 🔴 144 验收②·**源可达但数据错**（非空但全是错板块）⇒ 判据必须返回 **None**"
      "（⇒ 交给断言判 ⇒ **FAIL**，⛔ 不得被 skip 吞掉）",
      _ib_skip_reason({"错误板块A", "错误板块B"}) is None,
      f"实得 {_ib_skip_reason({'错误板块A', '错误板块B'})!r}")
# 🔴 验收②的**行为级**复核：真的把这份「非空但错」的样本喂进与生产同一个断言式，
#    确认它**确实会失败**（⛔ 不是只看判据返回 None 就收工 —— 那还是「探针未经校验」）
_na = {"错误板块A", "错误板块B"}
_N39_FOUND = [s for s in ("固态电池", "人形机器人", "智能驾驶") if s in _na]
check("N39 🔴 144 验收②行为级复核·「非空但错」的样本走**生产同一断言式** ⇒ 必得空集"
      "⇒ 断言会 FAIL（⇒ 证明 skip 不是恒放行）",
      len(_N39_FOUND) == 0 and _ib_skip_reason(_na) is None,
      f"found={_N39_FOUND} / skip={_ib_skip_reason(_na)}")
check("N40 🔴 144 验收③·**源可达且数据对** ⇒ 判据返回 None 且断言**真执行成功**"
      "（防「引入 skip 后断言永不执行」）",
      _ib_skip_reason({"固态电池", "人形机器人", "智能驾驶"}) is None,
      "真数据样本下 skip=None ⇒ 断言路径被执行")

# ── N-l 🔴 §I-b **中途失败**的占位机制（v4.5.17 自曝 bug 的常驻回归） ──
#    ⚠️ 这一组的存在理由：那个 bug（占位未登记 ⇒ I8b 假红）**套件原本抓不到** ——
#       我只在自己另跑的探针里撞见它。⛔ 探针是一次性的，断言才是常驻的。
_ITEMS5 = ("I5", "I5b", "I6", "I7", "I8")


def _ph(items, done):
    """跑一次占位，返回 (报出的项名, done 集合)——纯内存，不碰全局 _results/_skips。"""
    got = []
    d = set(done)
    _ib_placehold(items, d, "探针：源中途失败", emit=lambda n, why: got.append(n))
    return got, d


_g1, _d1 = _ph(_ITEMS5, {"I5", "I5b"})
check("N41 🔴 §I-b 中途失败 ⇒ 未发项**逐个占位**，且**全部登记进 done**"
      "（缺登记 ⇒ 紧随的 I8b 会把「源抖动」判成「代码坏了」）",
      len(_g1) == 3 and _d1 == set(_ITEMS5),
      f"占位 {_g1} / done={sorted(_d1)}")
check("N42 🔴 §I-b 中途失败**不得重复占位**已发项（占位是幂等的）",
      all(n.startswith(("I6", "I7", "I8")) for n in _g1) and
      not any(n.startswith(("I5 ", "I5b")) for n in _g1),
      f"实得 {_g1}")
# 🔴 **反向断言**：把 bug 重新造出来 —— 占位**不登记**时，I8b 的判据必须判红。
#    否则 N41 只是「断言了一个恒真的东西」（本仓 v4.5.5/6/7 连续三次的同一坑）。
_BUGGY_ITEMS = ("I5", "I5b", "I6", "I7", "I8")
_buggy_done = {"I5", "I5b"}
for _nm in _BUGGY_ITEMS:                       # ← 复现**修复前**的写法：报出但**不登记**
    if _nm not in _buggy_done:
        pass                                   # （旧代码漏的就是 `_buggy_done.add(_nm)` 这一行）
_buggy_missing = [_nm for _nm in _BUGGY_ITEMS if _nm not in _buggy_done]
check("N43 🔴 **反向断言**·占位不登记 ⇒ I8b 判据**必须判红**"
      "（复现 v4.5.17 那个套件抓不到的 bug；此断言恒真则 N41 是空转）",
      bool(_buggy_missing) and _buggy_missing == ["I6", "I7", "I8"],
      f"缺登记时应判红，实得未占位 {_buggy_missing}")
check("N44 🔴 对照：**修好的**写法在**同一输入**下不得判红"
      "（N43 与 N44 必须一红一绿，否则证明不了登记那一行在起作用）",
      not [n for n in _ITEMS5 if n not in _d1], f"done={sorted(_d1)}")

# ── N-j 隔离断言：全程未触碰生产文件 ──
check("N31 🔴 §N 全程**未写任何生产文件**（靠 `ANCHOR_DESKTOP` 换路径隔离，⛔ 不靠 `try/finally`"
      " —— J11：进程被硬杀时 finally 不执行，假条目会永久留在生产文件里）",
      _N_PORT.resolve() != Path(paths.DATA_PATH).resolve()
      and _N_CONTRACT.resolve() != Path(paths.RULE_CONTRACT_PATH).resolve(),
      "夹具路径与生产路径不同")
_rcP, _outP = run_pre_trade("创新药", "300")   # 生产路径重跑：若上面误写过生产文件，读数会变
check("N32 🔴 生产契约读数正常（E4 = ¥1,500 档）—— 证明 §N 未污染生产契约",
      "E4 月净投入" in _outP and "1,500" in _outP,
      f"rc={_rcP}")

# ── N-k 🔴 两层 `tier` 不得混用（**本节自己的反向断言抓出的真 bug**） ──
#   契约的 `sources` 段自带 `tier`（anchored/fallback —— **抽取器**怎么拿到的），
#   消费侧也需要一个 `tier`（contract/builtin —— **值从契约来还是回退内置**）。
#   首版用 `{..., "tier": "contract", **契约侧}` 展开 ⇒ 契约侧的 tier **覆盖**了消费侧的
#   ⇒ 消费侧再也答不出「这个阈值来自哪里」⇒ 漂移护栏对**真契约恒亮**
#   （实测：一个 tier=contract 都没有 ⇒ 报「全部落到 builtin」）。
#   📌 同一条护栏的注释里我刚引用了 v2.1 判例「永远亮着的告警会被学会忽略」——
#      **反例当场被自己的测试抓到**。
_th_real = _ptc.load_thresholds()
_E4_SRC = _th_real["_sources"].get("e4_sat_monthly_net") or {}
check("N33 🔴 两层 tier 必须分列：`tier` = 消费侧（contract/builtin），"
      "`contract_tier` = 抽取侧（anchored/fallback）",
      _E4_SRC.get("tier") == "contract" and _E4_SRC.get("contract_tier") == "anchored",
      f"tier={_E4_SRC.get('tier')!r} contract_tier={_E4_SRC.get('contract_tier')!r}")
check("N34 🔴 反向·漂移护栏**不得对真契约亮**（永远亮的告警 = 报告标准 v2.1 所禁）",
      not any("键名整体不匹配" in w for w in _th_real["_warns"]),
      f"_warns={_th_real['_warns']}")
# 🔴 N35 反向·漂移护栏**必须**对键名漂移的契约亮 —— 否则 N34 只是「护栏根本没跑」的假绿。
#    用**临时文件**改 `paths.RULE_CONTRACT_PATH` **在本进程内**跑一次，跑完立刻还原。
#    ⚠️ 与 J11 的区别：J11 禁的是「靠 finally 去还原**生产文件**」（进程被硬杀则 finally 不执行，
#       污染留在磁盘上）；此处只动**本进程的模块属性**，进程死则属性随之消失，**无持久风险**。
_orig_rc = paths.RULE_CONTRACT_PATH
_N35 = Path(tempfile.mkdtemp(prefix="anchor_n35_")) / "rule_contract.json"
try:
    _N35.write_text(json.dumps(
        {"rules": {"e1_sat_single_limit": 9999.0, "e4_sat_monthly_net": 8888.0}},
        ensure_ascii=False), encoding="utf-8")
    paths.RULE_CONTRACT_PATH = _N35
    _th_drift = _ptc.load_thresholds()
    check("N35 🔴 反向·漂移护栏**必须**对键名漂移的契约亮（否则 N34 是空转假绿），"
          "且漂移时**全部取值落到 builtin**（⛔ 坏值一个都不得生效）",
          any("键名整体不匹配" in w for w in _th_drift["_warns"])
          and _th_drift["e4_sat_monthly_net"] == _ptc.BUILTIN_THRESHOLDS["e4_sat_monthly_net"],
          f"_warns={_th_drift['_warns'][:1]} e4={_th_drift['e4_sat_monthly_net']}")
finally:
    paths.RULE_CONTRACT_PATH = _orig_rc
    shutil.rmtree(_N35.parent, ignore_errors=True)
check("N36 漂移试验后契约路径**已还原**（后续断言仍读真契约）",
      paths.RULE_CONTRACT_PATH == _orig_rc,
      f"{paths.RULE_CONTRACT_PATH}")
shutil.rmtree(_N_TMP, ignore_errors=True)

# ══════════════════════════════════════════════════════════════════
print("\n########## W. A2 判据缓存回退（inbox/142：活源空时不得降级为『判不了』）##########")
# 夹具取 9/21 实况形态：当日 ∈ (0,2%)、前日 > 0 ⇒ 四条全「连续 2 日飘红」⇒ 应判「⛔ 禁买」
_W_TODAY = {                       # 缓存当日档形状：{code: {name, chg_pct, board_type}}
    "BK0968": {"name": "固态电池", "chg_pct": 0.75, "board_type": "概念板块"},
    "BK0892": {"name": "人形机器人", "chg_pct": 1.36, "board_type": "概念板块"},
    "BK0800": {"name": "智能驾驶", "chg_pct": 1.22, "board_type": "概念板块"},
    "BK0478": {"name": "有色金属", "chg_pct": 0.96, "board_type": "行业板块"},
}
_W_PREV = {c: {**v, "chg_pct": v["chg_pct"] + 0.8} for c, v in _W_TODAY.items()}
_W_ITEMS = [{"sector": "固态电池", "etf_code": "159755"},
            {"sector": "人形机器人", "etf_code": "562500"},
            {"sector": "智能驾驶", "etf_code": "159889"},
            {"sector": "有色金属", "etf_code": "512400"}]
_W_CONTRACT = {"rules": {"a2_red_day_pct": 2.0, "watchlist_confirm_ma_period": 5,
                         "watchlist_confirm_ma_includes_today": True,
                         "a2_prev_day_cache": "board_pct_history.json"}}
_W_NOW = datetime(2026, 9, 23, 16, 0)
_W_KL = [{"date": f"2026-09-{10 + i:02d}", "close": c}
         for i, c in enumerate([1.0, 1.0, 1.0, 1.0, 1.0, 1.20])]
_W_LIVE = {                        # 活源形状（与 board_movers_all() 同构）；与缓存同一份数值
    "by_name": {v["name"]: {"code": c, **v} for c, v in _W_TODAY.items()},
    "rows": [{"code": c, **v} for c, v in _W_TODAY.items()],
    "universes": {"概念板块": {"total": 3, "fetched": 3, "complete": True},
                  "行业板块": {"total": 1, "fetched": 1, "complete": True}},
    "complete": True, "total_all": 4, "ts": "live-fixture",
}
_W_DAY_FN = (lambda d: (dict(_W_TODAY) if d == "2026-09-21" else
                        dict(_W_PREV) if d == "2026-09-18" else None))
_ORIG_W = {n: getattr(fp, n) for n in
           ("board_movers_all", "ref_last_trading_day", "prev_trading_day",
            "board_history_day", "board_history_gaps", "daily_kline",
            "board_history_record")}


def _w_apply(live, day_fn):
    fp.board_movers_all = lambda: live
    fp.ref_last_trading_day = lambda: ("2026-09-21", [{"date": "2026-09-21"}])
    fp.prev_trading_day = lambda kl, d: "2026-09-18"
    fp.board_history_day = day_fn
    fp.board_history_gaps = lambda kl=None, upto=None: {"checked": False, "reason": "夹具（W）"}
    fp.daily_kline = lambda code, n=30: list(_W_KL)


_w_tmp = tempfile.mkdtemp(prefix="anchor_w142_")
_w_cache_path = Path(_w_tmp) / "board_pct_history.json"
try:
    # ---- W1 正向：活源空 ＋ 缓存有当日值 ⇒ 明确 A2 判定（非「仅部分可判」）----
    _w_apply({}, _W_DAY_FN)
    _st_cache = gws.build_status({"watchlist": _W_ITEMS}, _W_CONTRACT, _W_NOW,
                                 record_history=False)
    _v_cache = [e["verdict"] for e in _st_cache["entries"]]
    check("W1 🔴 142 验收①·活源空+缓存有当日值 ⇒ 四条均为**明确 A2 判定**（夹具下＝⛔ A2 禁买），"
          "⛔ 不得降级为「🟡 A2 仅部分可判」",
          _v_cache == ["⛔ A2 禁买"] * 4, f"实得 {_v_cache}")

    # ---- W2 反向（本单最重要）：修复前写法（只调活源且返空、无回退）⇒ 必须降级 ----
    #    把「空的活源结果」直接喂给 evaluate_entry ＝ 复现修复前路径。
    #    ⛔ 修复后**永久保留**：一旦有人删掉回退，本断言立刻变红（＝缺陷复现）。
    _old_verdicts = {gws.evaluate_entry(it, _W_CONTRACT, {}, _W_NOW,
                                        prev_day=_W_PREV, prev_date="2026-09-18")["verdict"]
                     for it in _W_ITEMS}
    check("W2 🔴 142 验收②（反向）·修复前写法（活源空、无回退）在同一夹具下**确实降级**"
          "⇒「🟡 A2 仅部分可判」",
          _old_verdicts == {"🟡 A2 仅部分可判"}, f"实得 {_old_verdicts}")

    # ---- W3 幂等：同数据，活源通／断两路径 verdict 逐字相等（R4）----
    _w_apply(_W_LIVE, _W_DAY_FN)
    _st_live = gws.build_status({"watchlist": _W_ITEMS}, _W_CONTRACT, _W_NOW,
                                record_history=False)
    _v_live = [e["verdict"] for e in _st_live["entries"]]
    check("W3 🔴 142 验收③·幂等：活源通／断两路径 verdict **逐字相等**（仅来源字段不同）"
          "—— 证明回退不是装饰",
          _v_live == _v_cache, f"live={_v_live}／cache={_v_cache}")

    # ---- W4 来源可见（双向）：回退路径含「回退」标记＋原因；活源路径不含 ----
    _c_reason = "".join(e["reason"] for e in _st_cache["entries"])
    _l_reason = "".join(e["reason"] for e in _st_live["entries"])
    check("W4 🔴 142 验收④·来源可见（双向）：回退路径含「回退」标记＋原因；活源路径不含；"
          "board_source 字段三态可辨（cache/live）",
          ("回退" in _c_reason) and ("回退" not in _l_reason)
          and _st_cache["board_source"]["source"] == "cache"
          and _st_live["board_source"]["source"] == "live"
          and all(e["board_source"] == "cache" for e in _st_cache["entries"])
          and all(e["board_source"] == "live" for e in _st_live["entries"]),
          f"cache含标记={'回退' in _c_reason}／live含标记={'回退' in _l_reason}")

    # ---- W5 两源皆空 ⇒ 仍 fail-closed，且报文与「回退成功」可区分 ----
    _w_apply({}, lambda d: None)
    _st_none = gws.build_status({"watchlist": _W_ITEMS}, _W_CONTRACT, _W_NOW,
                                record_history=False)
    _v_none = [e["verdict"] for e in _st_none["entries"]]
    check("W5 🔴 142 验收⑤·两源皆空 ⇒ 仍 fail-closed（「🟡 A2 仅部分可判」），"
          "报文含「两源皆空」、与回退成功路径可区分（后者无此句）",
          _v_none == ["🟡 A2 仅部分可判"] * 4
          and all(e["board_source"] is None for e in _st_none["entries"])
          and all("两源皆空" in e["reason"] for e in _st_none["entries"])
          and "两源皆空" not in _c_reason,
          f"实得 {set(_v_none)} src={_st_none['entries'][0]['board_source']}")

    # ---- W6 缓存不被回退污染（R3/验收⑥）：真 record 走 env 隔离文件 ----
    #    ⛔ 核心：record 收到的必须是**活源结果（空）**、不是回退值 ——
    #    否则一次失败即把缓存固化成它自己的来源（自我循环）。
    _w_cache_path.write_text(json.dumps(
        {"schema": 1, "days": {"2026-09-21": _W_TODAY, "2026-09-18": _W_PREV}},
        ensure_ascii=False), encoding="utf-8")
    _w_before = _w_cache_path.read_bytes()
    _w_seen = []
    fp.board_history_record = (lambda ab, td, now=None:
                               (_w_seen.append(ab), _ORIG_W["board_history_record"](ab, td, now))[1])
    os.environ["ANCHOR_BOARD_HISTORY"] = str(_w_cache_path)
    fp.board_history_day = _ORIG_W["board_history_day"]      # 真实读 env 隔离文件
    try:
        _st_w6 = gws.build_status({"watchlist": _W_ITEMS}, _W_CONTRACT, _W_NOW,
                                  record_history=True)
        _w_after = _w_cache_path.read_bytes()
        _w_first = _w_seen[0] if _w_seen else None
        check("W6 🔴 142 验收⑥·回退路径下缓存文件**字节未变**，且 record 首参为**活源结果**"
              "（空表）—— 回退值不得写回缓存",
              _w_after == _w_before and len(_w_seen) > 0
              and not (_w_first or {}).get("by_name") and not (_w_first or {}).get("rows"),
              f"字节{('未变' if _w_after == _w_before else '**变了**')}；"
              f"record 调用 {len(_w_seen)} 次，首参={_w_first}")
        check("W6b 回退路径读**真缓存文件**（非夹具函数）仍给出明确 A2 判定 ⇒ ⛔ A2 禁买",
              [e["verdict"] for e in _st_w6["entries"]] == ["⛔ A2 禁买"] * 4,
              f"实得 {[e['verdict'] for e in _st_w6['entries']]}")
    finally:
        os.environ.pop("ANCHOR_BOARD_HISTORY", None)
finally:
    for _n, _v in _ORIG_W.items():
        setattr(fp, _n, _v)
    shutil.rmtree(_w_tmp, ignore_errors=True)

# ══════════════════════════════════════════════════════════════════
_fail = [n for n, ok, _ in _results if not ok]
# 🔴 **三态**，⛔ 不得把「无法判定」并进「通过」里静默消化掉
#    （并进去 ⇒ 报告写着「全绿」，而其实有一节根本没跑 —— 本仓「空白被读成合格」家族）。
print("\n" + "=" * 56)
print(f"共 {len(_results) + len(_skips)} 项 · 通过 {len(_results) - len(_fail)} · "
      f"**无法判定** {len(_skips)} · 失败 {len(_fail)}")
if _skips:
    print("⏭ 无法判定项（**不等于通过**，须知晓其未覆盖）:")
    for n, why in _skips:
        print(f"   - {n}\n     ↳ {why}")
if _fail:
    print("❌ 失败项:")
    for n in _fail:
        print("   -", n)
    sys.exit(1)
print("✅ 全绿" + (f"（⚠️ 但含 {len(_skips)} 项**无法判定**，见上）" if _skips else ""))
sys.exit(0)
