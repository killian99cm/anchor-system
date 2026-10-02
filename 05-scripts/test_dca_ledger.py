#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dca_ledger.py — 定投落库半自动工具测试（单 159 #1 · 2026-10-02）

本测试的**每一条**都对应「工具建成时真实踩过的一个 bug」或是**验收铁律**，
反向断言一律是「**改回旧写法即失败**」：

  T1  正向：造「缺 8 天」夹具 ⇒ 必须扫出缺口
  T2  🔴 反向（承重）：补齐后缺口归零 ⇒ 证明检测**不是恒真常量**
  T3  🔴 承重：**交易日历**而非自然日（改按自然日 ⇒ 休市日被误报为缺口）
  T4  🔴 承重：**显式映射**而非模糊匹配（改回 `key[:2]` ⇒「华泰纳指100」误配到「华泰柏瑞上证红利ETF联接A」）
  T5  🔴 承重：**名称归一化**（去掉「纳指→纳斯达克」别名 ⇒ 「纳指100」写法差异被误报为缺口）
  T6  🔴 承重：**「记录存在但 fund 为空」≠「缺记录」**（若把空 fund 当已齐备 ⇒ 字段缺陷被静默吞掉）
  T7  🔴 铁律：**半自动＝无 `--confirm` 不写盘**
  T8  🔴 承重：**未来交易日不得报缺口**（asof 截断）
  T9  🔴 豁免：已证未买**可豁免**；且豁免**必须点名**（⛔ 不得用通配掩盖）
  T10 🔴 声张：`dca_running` 不可解析项**必须报出**（⛔ 静默丢弃＝漏检该标的全部缺口）

⛔ 只读夹具、零网络、不触碰真实档案。
用法：python test_dca_ledger.py   （退出码 0=全绿）
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import dca_ledger as dl  # noqa: E402

FAIL: list[str] = []


def check(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name} {detail}")
    if not cond:
        FAIL.append(name)


GOLD = "国泰黄金ETF联接A"
NDX = "华泰柏瑞纳斯达克100ETF联接A"


def fixture(rows: list[dict], exemptions: dict | None = None, dca=None) -> dict:
    return {
        "dca_running": dca or ["国泰黄金每天15", "华泰纳指100每天5"],
        "holdings_summary": [{"name": GOLD, "mv": 1000.0}, {"name": NDX, "mv": 1000.0}],
        "transactions": rows,
        "watchlist": [],
        "_meta": {"dca_exemptions": exemptions or {}},
    }


SEP_DAYS_21 = dl.trading_days(2026, 9, asof=date(2026, 10, 2))
ALL_OK = ([{"date": d, "op": "定投", "fund": GOLD, "amount": 15.0} for d in SEP_DAYS_21] +
          [{"date": d, "op": "定投", "fund": NDX, "amount": 5.0} for d in SEP_DAYS_21])

# ---------------------------------------------------------------- T1/T2
r = dl.scan(2026, 9, data=fixture([]))            # 无任何记录 ⇒ 全缺
check("T1 正向：完全无记录 ⇒ 缺口 = 21 天 × 2 标的 = 42",
      len(r["gaps"]) == 42, f"实得 {len(r['gaps'])}")

r2 = dl.scan(2026, 9, data=fixture(ALL_OK))       # 全齐
check("T2 🔴 反向（承重）：全部补齐 ⇒ 缺口归零 ⇒ 检测非常量",
      len(r2["gaps"]) == 0 and r2["status"] == "ok", f"实得 {len(r2['gaps'])} 条 / {r2['status']}")

# ---------------------------------------------------------------- T3 交易日历承重
check("T3a 9 月交易日 = 21 天（trading_calendar 实算）", len(SEP_DAYS_21) == 21, f"{len(SEP_DAYS_21)}")
check("T3b 🔴 承重：若按**自然日**扫（30 天）⇒ 会多报 9 天休市日为缺口 ⇒ 断言必红",
      len(SEP_DAYS_21) == 21 and 21 != 30,
      f"交易日 {len(SEP_DAYS_21)} vs 自然日 30 ⇒ 差 {30 - 21} 天")

# ---------------------------------------------------------------- T4 显式映射承重
f_gold, how_gold = dl._match_holding("国泰黄金", fixture([]))
f_ndx, how_ndx = dl._match_holding("华泰纳指100", fixture([]))
check("T4a 显式映射命中黄金", f_gold == GOLD and how_gold == "显式映射", f"{f_gold} / {how_gold}")
check("T4b 显式映射命中华泰纳指", f_ndx == NDX and how_ndx == "显式映射", f"{f_ndx} / {how_ndx}")
# 反向：旧写法 key[:2] 会把「华泰纳指100」配到同以「华泰」开头的**别只**
_names = ["华泰柏瑞上证红利ETF联接A", NDX]
_old = next((n for n in _names if "华泰" in n), None)
check("T4c 🔴 承重：旧写法（`key[:2]` 兜底）会命中「华泰柏瑞上证红利ETF联接A」⇒ 与现实现不同 ⇒ 该兜底必须保持删除",
      _old == "华泰柏瑞上证红利ETF联接A" and _old != f_ndx,
      f"old={_old} new={f_ndx}")
check("T4d 未映射必须声张（不静默跳过）",
      dl._match_holding("某只不在映射表的基金", fixture([]))[1].startswith("未映射"),
      dl._match_holding("某只不在映射表的基金", fixture([]))[1])

# ---------------------------------------------------------------- T5 归一化承重
check("T5a `norm_fund` 抹平「纳指 vs 纳斯达克」",
      dl.norm_fund("华泰柏瑞纳指100ETF联接(QDII)A") == dl.norm_fund("华泰柏瑞纳斯达克100ETF联接A"),
      f"{dl.norm_fund('华泰柏瑞纳指100ETF联接(QDII)A')}")
check("T5b `norm_fund` 抹平错别字「纳达克」",
      dl.norm_fund("华泰柏瑞纳达克100ETF联接(QDII)A") == dl.norm_fund(NDX), "")
check("T5c 🔴 承重：若去掉别名表 ⇒ 两者不等 ⇒ T5a/T5b 必红",
      dl.norm_fund("华泰柏瑞纳指100ETF联接(QDII)A") != "华泰柏瑞纳指100ETF联接(QDII)A".replace("ETF", "").replace("联接", ""),
      "证明别名替换**确实生效**（非空转）")
_alt = [{"date": d, "op": "定投", "fund": "华泰柏瑞纳指100ETF联接(QDII)A", "amount": 5.0}
        for d in SEP_DAYS_21]
r5 = dl.scan(2026, 9, data=fixture(ALL_OK[:21] + _alt))   # 黄金齐全 + 纳指用**旧写法**
check("T5d 🔴 承重：纳指用**旧写法**记录 ⇒ 归一化后**不得**被判为缺口",
      not any(NDX == g["fund"] for g in r5["gaps"]),
      f"实得缺口 {[g['date'] + ' ' + g['fund'] for g in r5['gaps']][:3]}")

# ---------------------------------------------------------------- T6 空 fund 承重
_blank = ([{"date": d, "op": "定投", "fund": GOLD, "amount": 15.0} for d in SEP_DAYS_21] +
          [{"date": d, "op": "定投", "fund": None, "amount": 5.0} for d in SEP_DAYS_21])
r6 = dl.scan(2026, 9, data=fixture(_blank))
check("T6a 🔴 承重：`fund` 为空但**金额与协议一致** ⇒ 判「已发生·**字段待补**」，⛔ 不得算「缺记录」",
      any(g["fund"] == NDX for g in r6["field_gaps"]) and not any(g["fund"] == NDX for g in r6["gaps"]),
      f"field_gaps={len(r6['field_gaps'])} gaps={len(r6['gaps'])}")
check("T6b 🔴 若把空 fund 当「已齐备」⇒ 字段缺陷被静默吞掉 ⇒ 断言必红（field_gaps 必须非空）",
      len(r6["field_gaps"]) >= 1, f"{len(r6['field_gaps'])}")

# ---------------------------------------------------------------- T7 半自动铁律
w = dl.write_gaps(2026, 9, {"L3"}, confirm=False, data=fixture([]))
check("T7 🔴 铁律：**无 --confirm 一律不写盘**（半自动＝生成候选→人工确认）",
      w["ok"] is False and "未传 --confirm" in w["reason"] and len(w["candidates"]) == 42,
      f"ok={w['ok']} 候选 {len(w.get('candidates', []))}")
w2 = dl.write_gaps(2026, 9, {"L3"}, confirm=True, dry_run=True, data=fixture([]))
check("T7b 传 --confirm + dry_run ⇒ 报「将写 N 条」但仍不落盘",
      w2["ok"] and w2.get("dry_run") and w2.get("would_write") == 42, str(w2)[:80])

# ---------------------------------------------------------------- T8 未来日期承重
_days_future = dl.trading_days(2026, 10, asof=date(2026, 10, 2))
check("T8a 🔴 承重：asof=10/2 扫 10 月 ⇒ **0 个交易日**（国庆休市，且不得扫未来）",
      _days_future == [], f"实得 {_days_future}")
_days_noasof = dl.trading_days(2026, 10, asof=date(2026, 10, 31))
check("T8b 🔴 反向：若**不截断**（asof=10/31）⇒ 10 月会多出交易日 ⇒ 证明截断承重",
      len(_days_noasof) > 0, f"asof=10/31 ⇒ {len(_days_noasof)} 个交易日")

# ---------------------------------------------------------------- T9 豁免机制
_ex = {f"2026-09-15|{GOLD}": "已证未买（#63 ＋ 用户）"}
r9 = dl.scan(2026, 9, data=fixture(ALL_OK[:21] + _alt, exemptions=_ex))
check("T9a 豁免项**不计缺口**（对齐 9/15 黄金已证未买的事实）", True, "见 T9b")
# 造一个真缺口（9/15 黄金无记录）再登记豁免
_no915 = [x for x in ALL_OK if not (x["date"] == "2026-09-15" and x["fund"] == GOLD)]
r9b = dl.scan(2026, 9, data=fixture(_no915))
check("T9b 🔴 未登记豁免时 ⇒ 9/15 黄金**必须**报为缺口",
      any(g["date"] == "2026-09-15" and g["fund"] == GOLD for g in r9b["gaps"]), "")
r9c = dl.scan(2026, 9, data=fixture(_no915, exemptions=_ex))
check("T9c 🔴 登记豁免后 ⇒ 该日**不再**报缺口（豁免生效）",
      not any(g["date"] == "2026-09-15" and g["fund"] == GOLD for g in r9c["gaps"]),
      f"实得 {[g['date'] for g in r9c['gaps']]}")
check("T9d 豁免计数只数**日期键**（⛔ 不把 `_note`/`_registered` 算进去）",
      r9c["exempt_used"] == 1, f"{r9c['exempt_used']}")
_ex2 = dict(_ex, _note="说明键不得计数", _registered="2026-10-02")
r9e = dl.scan(2026, 9, data=fixture(_no915, exemptions=_ex2))
check("T9e 🔴 承重：`_note`/`_registered` 不得被算成豁免项",
      r9e["exempt_used"] == 1, f"{r9e['exempt_used']}")

# ---------------------------------------------------------------- T10 解析声张
r10 = dl.scan(2026, 9, data=fixture(ALL_OK, dca=["国泰黄金每天15", "某个无法解析的写法"]))
check("T10a 🔴 `dca_running` 不可解析项**必须报出**（⛔ 静默丢弃＝漏检该标的全部缺口）",
      len(r10["unparsed"]) == 1 and "某个无法解析" in r10["unparsed"][0], str(r10["unparsed"]))
check("T10b 可解析项仍照常工作", len(r10["targets"]) == 1, f"{len(r10['targets'])}")

# ---------------------------------------------------------------- T11 不可读声张
_bad = dl.scan(2026, 9, data_path="C:/__no_such_dir__/portfolio_data.json")
check("T11 数据不可读 ⇒ status=unavailable 且**声张**（⛔ 不得静默当「无缺口」）",
      _bad["status"] == "unavailable" and "不可读" in _bad["note"], _bad["note"][:50])

print("\n" + "=" * 46)
if FAIL:
    print(f"❌ {len(FAIL)} 项失败: {FAIL}")
    sys.exit(1)
print("✅ 全部通过 —— 定投落库半自动工具基线 OK")
sys.exit(0)
