#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_gate_trail_audit.py — 门禁留痕覆盖审计测试（裁决 #C1-25 · 2026-09-29）

覆盖三类断言，反向断言均为「改回旧写法即失败」：
  · **匹配键承重**：必须 (日期, 标的) **双键**；放宽任一键都会把真实缺口掩盖
    —— 尤其「全仓」类记录（如 #69「全仓·零主动操作」）不得充当覆盖，
    否则 9/28 那笔真实加仓缺口会被它盖掉（**本例即是现场发现的真实缺口**）。
  · **排除口径复用真源**：记账腿 / 已被取代 / 显式声明非手动 ⇒ 不要求门禁留痕。
  · **fail-loud**：数据不可读 ⇒ `unavailable` 且声张，⛔ 不得静默当合格。

⛔ 只读夹具，零网络、不触碰真实档案与决策日志。
用法：python test_gate_trail_audit.py    （退出码 0=全绿）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pre_trade_check as ptc  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'✅' if cond else '❌'} {name} {detail}")
    if not cond:
        FAIL.append(name)


def tx(d0, op, fund, amt, note="", **extra):
    t = {"date": d0, "op": op, "fund": fund, "amount": amt, "note": note}
    t.update(extra)
    return t


BASE_TXNS = [
    tx("2026-09-07", "买入", "易方达恒生港股通创新药ETF联接C", 300),        # 有留痕
    tx("2026-09-01", "买入", "鹏华畅享债券C", 3300),                          # 有留痕
    tx("2026-09-28", "加仓", "天弘通利混合A", 150),                           # 🔴 无留痕（真实现场）
    tx("2026-09-11", "赎回确认", "易方达证券ETF联接C", 3759.25),              # 记账腿 ⇒ 不要求
    tx("2026-09-01", "买入", "易方达证券ETF联接C", 2000, superseded=True),   # 已被取代 ⇒ 不要求
    tx("2026-09-05", "买入", "某基金", 100, note="智能定投自动扣款（非手动操作，不计入月限额）"),
]
BASE_LOG = [
    {"id": "59", "date": "2026-09-07", "fund": "易方达恒生港股通创新药ETF联接C"},
    {"id": "53", "date": "2026-09-01", "fund": "鹏华畅享债券C"},
]


def run(txns, log):
    return ptc.audit_gate_trail(2026, 9, data={"transactions": txns}, log_records=log)


# ---------------------------------------------------------------- T1 正向
r = run(BASE_TXNS, BASE_LOG)
check("T1a 只计主动买入类（记账腿/已取代/非手动声明均排除）",
      len(r["events"]) == 3, f"实得 {len(r['events'])} 笔：{[e['op'] for e in r['events']]}")
check("T1b 检出缺口语义：status=missing 且 missing 恰 1 笔",
      r["status"] == "missing" and len(r["missing"]) == 1
      and r["missing"][0]["fund"] == "天弘通利混合A",
      f"status={r['status']} missing={[e['fund'] for e in r['missing']]}")

# ---------------------------------------------------------------- T2 🔴 反向：补齐即归零
r2 = run(BASE_TXNS, BASE_LOG + [{"id": "71", "date": "2026-09-28", "fund": "天弘通利混合A"}])
check("T2 🔴 补齐留痕 ⇒ missing 归 0、status=ok（证明检测不是恒真常量）",
      r2["status"] == "ok" and len(r2["missing"]) == 0, f"status={r2['status']}")

# ---------------------------------------------------------------- T3 🔴 反向：承重断言 ——「全仓」不得充当覆盖
r3 = run(BASE_TXNS, BASE_LOG + [{"id": "Z", "date": "2026-09-28", "fund": "全仓"}])
check("T3a 🔴 同日的「全仓」记录 ⇒ **不得**构成覆盖（否则 9/28 真实缺口被 #69 掩盖）",
      r3["status"] == "missing" and len(r3["missing"]) == 1,
      f"status={r3['status']} missing={len(r3['missing'])}")
check("T3b 🔴 反证：若实现删掉「全仓不构成覆盖」这一条，T3a 必转为 ok ⇒ 该判据承重",
      not any("全仓" == str(e.get("covered_by")) for e in r3["events"]),
      "covered_by 不得回填「全仓」")

# ---------------------------------------------------------------- T4 🔴 反向：日期键承重
r4 = run(BASE_TXNS, BASE_LOG + [{"id": "Y", "date": "2026-09-27", "fund": "天弘通利混合A"}])
check("T4 🔴 仅同标的、**不同日** ⇒ 不构成覆盖（证明日期键不是装饰）",
      r4["status"] == "missing" and len(r4["missing"]) == 1,
      f"status={r4['status']} missing={len(r4['missing'])}")

# ---------------------------------------------------------------- T5 🔴 反向：标的不匹配
r5 = run(BASE_TXNS, BASE_LOG + [{"id": "X", "date": "2026-09-28", "fund": "天弘纳斯达克100指数(QDII)C"}])
check("T5 🔴 仅同日、**不同标的** ⇒ 不构成覆盖（证明标的键不是装饰）",
      r5["status"] == "missing", f"status={r5['status']}")

# ---------------------------------------------------------------- T6 fail-loud
r6 = run(BASE_TXNS, [])
check("T6a 日志为空列表 ⇒ 全部无留痕（⛔ 不得静默放行）",
      r6["status"] == "missing" and len(r6["missing"]) == 3, f"status={r6['status']}")

# 🔴 T6b 必须**真的**打到不可读路径 —— 首版这条只传 log_records=None 就断言，
#     结果**回落到读真实日志并成功** ⇒ 断言恒真、根本没覆盖 unavailable 分支
#     （＝「把无法判定当通过」，本库已多次立规禁止）。故显式把 LOG_FILE 指向不存在处。
_orig_log_file = ptc.LOG_FILE
try:
    ptc.LOG_FILE = Path("C:/__anchor_no_such_dir__/decision_log.json")
    r7 = ptc.audit_gate_trail(2026, 9, data={"transactions": BASE_TXNS}, log_records=None)
finally:
    ptc.LOG_FILE = _orig_log_file
check("T6b 🔴 决策日志不可读 ⇒ status=unavailable（⛔ 不得降级为 ok/missing 冒充判定）",
      r7["status"] == "unavailable", f"status={r7['status']}")
check("T6b-2 🔴 且 note 必须声张失败原因（⛔ 不得静默）",
      "不可读" in r7["note"] and "无法审计" in r7["note"], f"note={r7['note'][:70]}")
check("T6b-3 反向：真实日志未受影响（对照组必须能读）",
      ptc.audit_gate_trail(2026, 9, data={"transactions": BASE_TXNS})["status"] in ("ok", "missing"),
      "对照组若也不可读，说明上面是环境问题而非被测路径")

# ---------------------------------------------------------------- T7 空月
r8 = run([tx("2026-08-01", "买入", "某基金", 100)], [])
check("T7 当月无主动买入 ⇒ status=empty（≠ ok，须可分辨）",
      r8["status"] == "empty", f"status={r8['status']}")

# ---------------------------------------------------------------- T8 未识别 op 声张
r9 = run(BASE_TXNS + [tx("2026-09-20", "神秘操作", "某基金", 1)], BASE_LOG)
check("T8 未识别 op ⇒ 计入 unknown_ops 并在 note 声张（⛔ 不静默计入/排除）",
      len(r9["unknown_ops"]) == 1 and "未识别" in r9["note"], f"unknown={r9['unknown_ops']}")

# ---------------------------------------------------------------- 汇总
print("\n" + "=" * 46)
if FAIL:
    print(f"❌ {len(FAIL)} 项失败: {FAIL}")
    sys.exit(1)
print("✅ 全部通过 —— 门禁留痕审计基线 OK")
sys.exit(0)
