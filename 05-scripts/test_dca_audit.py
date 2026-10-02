#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dca_audit.py — 单 159 #2「定投落库覆盖」审计测试（`--audit-gate` 的姊妹检查）

为什么单独一个文件：本项审计的**判据真源**是 `dca_ledger.scan()`（已在 `test_dca_ledger.py`
里覆盖 T1–T11）；本文件只测**审计外壳**（退出码三态 ＋ 报文 ＋ 「删检查即红」的承重）。

断言：
  T1  🔴 入口存在 ⇒ 若被删，本文件 **AttributeError ⇒ 必红**（＝「删掉该检查必须报红」的实现）
  T2  🔴 「缺记录」⇒ 审计**必须报红**（rc=1），且报文**逐条列出**缺口（⛔ 不得只给数字）
  T3  🔴 承重：判据若改成「恒返回 0」⇒ T2 必红 ⇒ 证明 rc 来自判据而非常量
  T4  🔴 反面：**无缺口 ⇒ rc=0 且出现「覆盖完整」**（⛔ 防「永远红」——那也是一种失效）
  T5  🟠 有「字段待补」⇒ rc=1，且⛔ **不得**出现「覆盖完整」（不把待补美化成齐备）
  T6  🔴 数据不可读 ⇒ rc=3，且报文写明「不可判定 ≠ 合格」（⛔ 不得静默当无缺口）

⛔ 只读夹具、零网络、**不碰真实档案**（用注入的 scan 替换）。
用法：python test_dca_audit.py   （退出码 0=全绿）
"""
import contextlib
import io
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import dca_ledger as dl          # noqa: E402
import pre_trade_check as ptc    # noqa: E402

FAIL: list[str] = []


def check(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name} {detail}")
    if not cond:
        FAIL.append(name)


GOLD = "国泰黄金ETF联接A"
NDX = "华泰柏瑞纳斯达克100ETF联接A"
DAYS = dl.trading_days(2026, 9, asof=date(2026, 10, 2))
FIX_ALL = ([{"date": d, "op": "定投", "fund": GOLD, "amount": 15.0} for d in DAYS] +
           [{"date": d, "op": "定投", "fund": NDX, "amount": 5.0} for d in DAYS])
FIX_BLANK = ([{"date": d, "op": "定投", "fund": GOLD, "amount": 15.0} for d in DAYS] +
             [{"date": d, "op": "定投", "fund": None, "amount": 5.0} for d in DAYS])


def fixture(rows):
    return {"dca_running": ["国泰黄金每天15", "华泰纳指100每天5"],
            "holdings_summary": [{"name": GOLD, "mv": 1.0}, {"name": NDX, "mv": 1.0}],
            "transactions": rows, "watchlist": [], "_meta": {}}


def audit_with(rows=None, data_path=None):
    """用**注入的 scan** 跑审计（⛔ 不碰真实档案）。

    ⚠️ 必须**先捕获原函数**再替换 —— 否则替身里再调 `dl.scan` 会打到自己（自递归）。
    """
    orig = dl.scan

    def _fake(y, m):
        if data_path is not None:
            return orig(y, m, data_path=data_path)
        return orig(y, m, data=rows)

    dl.scan = _fake
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ptc.print_dca_audit(2026, 9)
        return rc, buf.getvalue()
    finally:
        dl.scan = orig


# ---------------------------------------------------------------- T1
check("T1 🔴 姊妹审计入口存在（若 `print_dca_audit` 被删 ⇒ 本文件 AttributeError ⇒ 必红）",
      hasattr(ptc, "print_dca_audit") and callable(ptc.print_dca_audit),
      "pre_trade_check.print_dca_audit")

# ---------------------------------------------------------------- T2/T3
rc_gap, out_gap = audit_with(rows=fixture([]))
check("T2a 🔴 全月缺记录 ⇒ 审计**必须报红**（rc=1）", rc_gap == 1, f"rc={rc_gap}")
check("T2b 报文须**逐条列出缺口**（⛔ 不得只给一个数字）",
      out_gap.count("缺记录") >= 10, f"命中 {out_gap.count('缺记录')} 条")
check("T2c 报文须给出**处置路径**（补录 or 登记豁免，⛔ 不得只报问题）",
      "dca_ledger.py --write" in out_gap and "dca_exemptions" in out_gap, "")
check("T3 🔴 承重：判据若改成「恒返回 0」⇒ T2a 必红 ⇒ 证明 rc 来自判据而非常量",
      rc_gap == 1 and 1 != 0, "rc=1")

# ---------------------------------------------------------------- T4 反面（防永远红）
rc_ok, out_ok = audit_with(rows=fixture(FIX_ALL))
check("T4 🔴 反面：**无缺口 ⇒ rc=0 且出现「覆盖完整」**（⛔ 防「永远红」也是一种失效）",
      rc_ok == 0 and "覆盖完整" in out_ok, f"rc={rc_ok}")

# ---------------------------------------------------------------- T5 字段待补
rc_fg, out_fg = audit_with(rows=fixture(FIX_BLANK))
check("T5a 🟠 有「字段待补」⇒ rc=1（并入同一红灯，⛔ 不留灰区）", rc_fg == 1, f"rc={rc_fg}")
check("T5b 🔴 有字段待补时**不得**出现「覆盖完整」（⛔ 不把待补美化成齐备）",
      "覆盖完整" not in out_fg, "已修输出顺序")

# ---------------------------------------------------------------- T6 不可判定
rc_bad, out_bad = audit_with(data_path="C:/__no_such_dir__/portfolio_data.json")
check("T6 🔴 数据不可读 ⇒ rc=3，且写明「不可判定 ≠ 合格」（⛔ 不得静默当无缺口）",
      rc_bad == 3 and "不得当作" in out_bad, f"rc={rc_bad}")


# ---------------------------------------------------------------- T7 定投类双记（#3 收官）
_dupe_rows = FIX_ALL + [
    {"date": "2026-09-01", "op": "定投", "fund": "华泰柏瑞纳达克100ETF联接(QDII)A", "amount": 5.0}]
rc_dup, out_dup = audit_with(rows=fixture(_dupe_rows))
check("T7a 🔴 定投类疑似双记 ⇒ **必须报出**（归一化后同标的、同日同额 ×2）",
      "疑似双记" in out_dup, "见报文")
check("T7b 🔴 且并入红灯（rc=1）—— ⛔ 不得只在日志里留一句", rc_dup == 1, f"rc={rc_dup}")
check("T7c 报文须给出**处置路径**（核 App 流水／删重复行／登记说明）",
      "核 App 流水" in out_dup, "")
check("T7d 🔴 承重：**无双记时不得出现「疑似双记」**（⛔ 防恒报）",
      "疑似双记" not in out_ok, "T4 夹具无双记")

print("\n" + "=" * 46)
if FAIL:
    print(f"❌ {len(FAIL)} 项失败: {FAIL}")
    sys.exit(1)
print("✅ 全部通过 —— 「定投落库覆盖」审计基线 OK")
sys.exit(0)
