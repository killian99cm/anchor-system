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
import re
import subprocess
import sys
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
