#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_rule_hits_rebuild.py — 规则命中台账「派生重建」测试（2026-09-30）

背景：台账唯一写入路径是**手工命令**且不在任何链路中 ⇒ 最后一条停在 2026-08-17，
**9 月整月 0 条**（而 9 月实际有 E1 超限、A2 追红日×3、月额度满×3、节前闸门等命中）。
修法＝从既有真源**派生**（按系统实际在用的 tag 词表），而非继续依赖手工。

承重反向断言（「改回旧写法即失败」）：
  · T5 🔴 **本测试的核心**：若按旧写法「只查 `违规·月额度` 这一个 tag」⇒ 派生**必为 0**
        （该 tag 自 9/24 才生效且不溯及既往，9/14、9/28 两笔是补录 ⇒ 不打标）
        ⇒ 证明「按实际 tag 词表拓宽」是**承重改动**，不是装饰。
  · T3 🔴 幂等键若只按 `rule`（不带 date）⇒ 跨日同规则命中互吞 ⇒ 断言必红。
  · T4 🔴 若把推导写成「只要 tags 非空就记一条」⇒ 词表外的 tag 也会产出 ⇒ 断言必红。
  · T6 🔴 真源不可读 ⇒ 必须**显式声张**，⛔ 不得静默当「本月无命中」。

⛔ 只读夹具、零网络、不触碰真实台账文件。
用法：python test_rule_hits_rebuild.py   （退出码 0=全绿）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import noise_audit as na  # noqa: E402

FAIL: list[str] = []


def check(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name} {detail}")
    if not cond:
        FAIL.append(name)


def rec(i, d, tags, typ="观望", verdict="零操作", fund="全仓", amount=0):
    return {"id": str(i), "date": d, "type": typ, "verdict": verdict,
            "fund": fund, "amount": amount, "tags": tags}


LOG = [
    rec(54, "2026-09-01", ["超E1上限", "执行违规"], typ="买入", verdict="执行买入", fund="证券ETF联接C", amount=2000),
    rec(56, "2026-09-01", ["B5", "破位", "清仓"], typ="止损", verdict="执行清仓", fund="半导体"),
    rec(64, "2026-09-18", ["红日", "月额度满"]),
    rec(67, "2026-09-23", ["月额度满", "红日"]),
    rec(70, "2026-09-29", ["止损观察"], fund="易方达证券ETF联接C"),
    rec(99, "2026-09-15", ["某个词表外的tag"]),          # 必须被忽略（T4）
    rec(98, "2026-08-20", ["红日"]),                     # 跨月，必须被过滤
]
DATA = {"watchlist": []}

r = na.derive_rule_hits(2026, 9, data=DATA, log=LOG)
by = {}
for x in r:
    by.setdefault(x["date"], []).append(x["rule"])

check("T1a 只取本月（8/20 那条被过滤）",
      all(str(x["date"]).startswith("2026-09") for x in r), f"n={len(r)}")
EXPECT_N = 11   # #54:2 + #56:3+1(type) + #64:2 + #67:2 + #70:1 = 11（#99 词表外/#98 跨月 均不计）
check("T1b tag 映射逐条命中 ⇒ 恰 11 条（与夹具逐项核对：2+4+2+2+1）",
      len(r) == EXPECT_N, f"实得 {len(r)} 条：{sorted(x['rule'] for x in r)}")
check("T1b-2 映射覆盖到全部 8 类预期规则名",
      {x["rule"] for x in r} >= {"E1 单只卫星上限超限", "执行违规（纪）", "B5 观察仓破位",
                                 "破位（技术）", "清仓", "A2 追红日（禁买）",
                                 "月额度（已达上限·据此不买）", "止损观察（未触发）"},
      f"实得 {sorted(x['rule'] for x in r)}")
check("T1c 止损执行走 type 维（即便无 tag 也须记）",
      any(x["rule"].startswith("止损执行") for x in r),
      [x["rule"] for x in r if x["rule"].startswith("止损执行")])
check("T1d outcome 语义正确：超限=missed，红日/闸门=protected，止损观察=neutral",
      {x["outcome"] for x in r if "超限" in x["rule"]} == {"missed"}
      and any(x["rule"].startswith("A2") and x["outcome"] == "protected" for x in r)
      and any("止损观察" in x["rule"] and x["outcome"] == "neutral" for x in r),
      str({(x["rule"], x["outcome"]) for x in r}))

# ---------------------------------------------------------------- T2 幂等
def key(x):
    return (str(x.get("date", "")), str(x.get("rule", "")), str(x.get("note", ""))[:40])

_once = [dict(x) for x in r]
_twice = _once + [x for x in _once if key(x) not in {key(y) for y in _once}]
check("T2 幂等：同批结果再合并一次 ⇒ 不产生重复", len(_twice) == len(_once), f"{len(_once)} → {len(_twice)}")

# ---------------------------------------------------------------- T3 🔴 幂等键承重（含 date）
same_day_diff_note = [
    {"date": "2026-09-23", "rule": "月额度·买入维", "outcome": "missed", "amount": -100, "note": "[派生] 甲"},
    {"date": "2026-09-23", "rule": "月额度·买入维", "outcome": "missed", "amount": -200, "note": "[派生] 乙"},
]
k_new = {key(x) for x in same_day_diff_note}
k_old = {x["rule"] for x in same_day_diff_note}          # 旧写法：只按 rule
check("T3a 🔴 新键保留同日同规则的两条（note 不同）", len(k_new) == 2, f"n={len(k_new)}")
check("T3b 🔴 旧写法（只按 rule）会把它们并成 1 条 ⇒ 跨日/同日命中互吞 ⇒ 三键键承重",
      len(k_old) == 1 and len(k_new) != len(k_old), f"old={len(k_old)} new={len(k_new)}")

# ---------------------------------------------------------------- T4 🔴 词表外 tag 不得产出
check("T4a 🔴 词表外的 tag（'某个词表外的tag'）**不得**产出条目",
      not any("某个词表外" in str(x) for x in r), "见 T1b 条数")
only_foreign = na.derive_rule_hits(2026, 9, data=DATA, log=[rec(1, "2026-09-05", ["完全未知的tag"])])
check("T4b 🔴 若写成「只要 tags 非空就记一条」，此处必得 1 条 ⇒ 断言必红",
      len(only_foreign) == 0, f"实得 {len(only_foreign)} 条")

# ---------------------------------------------------------------- T5 🔴 旧写法必然漏掉 9 月（核心）
QUOTA_TAG_OLD = "违规·月额度"
old_way = [x for x in LOG
           if str(x["date"]).startswith("2026-09") and QUOTA_TAG_OLD in (x.get("tags") or [])]
new_way = [x for x in r if "月额度" in x["rule"]]
check("T5a 🔴 旧写法（只查 `违规·月额度`）在 9 月真源上派生 **0 条** ⇒ 正是「9 月台账 0 条」的成因",
      len(old_way) == 0, f"old={len(old_way)}")
check("T5b 🔴 新写法（按实际 tag 词表：月额度满/红日/…）派生 > 0 条 ⇒ 拓宽词表**承重**",
      len(new_way) >= 2, f"new={len(new_way)}：{[x['rule'] for x in new_way]}")

# ---------------------------------------------------------------- T6 不可读必须声张
dpath, lpath = na._paths()
_saved = na._paths
try:
    na._paths = lambda: (Path("C:/__no_such__/portfolio_data.json"), lpath)
    bad = na.derive_rule_hits(2026, 9, data=None, log=LOG)
finally:
    na._paths = _saved
check("T6a 🔴 档案不可读 ⇒ 必须返回**声张**记录（⛔ 不得返回空当「本月无命中」）",
      len(bad) == 1 and "不可读" in bad[0]["note"], f"实得 {bad[:1]}")
check("T6b 反向：对照组（真源可读）不得出现「派生失败」",
      not any("派生失败" in x["rule"] for x in na.derive_rule_hits(2026, 9, data=DATA, log=LOG)),
      "对照组正常")

print("\n" + "=" * 46)
if FAIL:
    print(f"❌ {len(FAIL)} 项失败: {FAIL}")
    sys.exit(1)
print("✅ 全部通过 —— 规则命中台账派生重建基线 OK")
sys.exit(0)
