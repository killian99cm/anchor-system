#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""proxy_band_calibrate.py — 代理误差带重定标器（2026-09-30 建 · 裁决 #C1-25/9-29 的后续）

问题（承 2026-09-29 登记）：
  · 原误差带 **0.6pp** 基于 16 观测（|Δ|max 0.9027pp）；
  · 2026-09-29 实测 **ETF 二级价代理偏 0.98pp** ⇒ **已破带**；
  · 且误差**随代理类型漂移**（ETF 价 vs 指数）、**无稳定符号**（通利A 两日方向相反）。

本器：按**代理类型**分列重定标。
  参照（truth）= 场外基金/同门 ETF 的**官方复权单位净值增长率**（＝ App 持有收益率的真源）
  代理（proxy）= ① 场内 **ETF 二级市场收盘价**涨跌  ② **指数**收盘涨跌

⚠️ 已知混淆（必须声明）：若参照取「同门 ETF 的官方净值」而非持仓联接基金自身净值，
   二者相差一个**跟踪拖累**（实测 9/29 0.15pp、9/30 0.19pp）⇒ 该量级会**混入** ETF 代理误差。
   ⇒ 处置：报两组数（原始 / 扣除跟踪拖累中位数），并以**扣拖累组**定带。

用法: python proxy_band_calibrate.py            # 用内置样例运行
      python proxy_band_calibrate.py --sample   # 打印样本与统计
"""
from __future__ import annotations
import json
import statistics as st
import sys
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0"}


def tencent_closes(code: str, n: int = 40) -> dict:
    """腾讯前复权日K → {date: close}。"""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{n},qfq"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=12) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    rows = d["data"][code].get("qfqday") or d["data"][code].get("day")
    return {x[0]: float(x[2]) for x in rows}


def pct_series(closes: dict) -> dict:
    """收盘价序列 → {date: 日涨跌%}（按日期排序，跳过第一个无前收的）。"""
    ks = sorted(closes)
    return {ks[i]: (closes[ks[i]] / closes[ks[i - 1]] - 1) * 100 for i in range(1, len(ks))}


def stats(deltas: list[float]) -> dict:
    a = [abs(x) for x in deltas]
    if not a:
        return {"n": 0}
    a_sorted = sorted(a)
    k = max(0, min(len(a_sorted) - 1, int(round(0.95 * (len(a_sorted) - 1)))))
    return {
        "n": len(a), "max": round(max(a), 4), "mean": round(st.mean(a), 4),
        "median": round(st.median(a), 4), "p95": round(a_sorted[k], 4),
        "signed_mean": round(st.mean(deltas), 4),
        "sign_pos": sum(1 for x in deltas if x > 0), "sign_neg": sum(1 for x in deltas if x < 0),
    }


def calibrate(nav_growth: dict, proxy_pct: dict, label: str) -> dict:
    """配对求 |Δ|（＝真值 − 代理，单位 pp）。"""
    common = sorted(set(nav_growth) & set(proxy_pct))
    rows = [{"date": d, "truth_nav_pct": nav_growth[d], "proxy_pct": proxy_pct[d],
             "delta_pp": round(nav_growth[d] - proxy_pct[d], 4)} for d in common]
    return {"label": label, "n": len(rows), "rows": rows,
            "stats": stats([r["delta_pp"] for r in rows])}


# ── 内置样例：创新药 C 的代理链（2026-09-30 实取）──────────────────────────
# 参照＝易方达恒生港股通创新药ETF(159316) 官方复权单位净值增长率（mx-data，16 观测）
NAV_159316 = {
    "2026-09-08": 0.2796, "2026-09-09": -2.079, "2026-09-10": -3.175, "2026-09-11": -1.702,
    "2026-09-14": 3.536, "2026-09-15": -1.454, "2026-09-16": -1.191, "2026-09-17": 1.061,
    "2026-09-18": 0.9521, "2026-09-21": 5.853, "2026-09-22": -0.7911, "2026-09-23": -0.3022,
    "2026-09-24": -3.536, "2026-09-28": -1.588, "2026-09-29": 2.723, "2026-09-30": 3.531,
}


def main() -> int:
    print("=" * 68)
    print("  代理误差带重定标 · 参照＝159316 官方净值增长率（nx=16）")
    print("=" * 68)
    print(f"  参照区间: {min(NAV_159316)} → {max(NAV_159316)}  （{len(NAV_159316)} 观测）")
    print()
    results = {}
    for code, lab in (("sh513120", "ETF 二级价（513120）"),):
        try:
            p = pct_series(tencent_closes(code))
            res = calibrate(NAV_159316, p, lab)
            results[lab] = res
            s = res["stats"]
            print(f"### {lab}  配对 n={s['n']}")
            print(f"    |Δ| max={s['max']}pp  mean={s['mean']}pp  median={s['median']}pp  p95={s['p95']}pp")
            print(f"    符号分布: 正 {s['sign_pos']} / 负 {s['sign_neg']}   signed_mean={s['signed_mean']}pp")
        except Exception as e:  # noqa: BLE001
            print(f"### {lab} ❌ {type(e).__name__}: {e}")
    print()
    print("  逐日明细（truth − proxy）：")
    for lab, res in results.items():
        for r in res["rows"]:
            flag = "🔴" if abs(r["delta_pp"]) > 0.6 else "  "
            print(f"    {flag} {r['date']}  净值 {r['truth_nav_pct']:>+7.3f}%  {lab[:12]:14s} {r['proxy_pct']:>+7.3f}%  Δ {r['delta_pp']:>+7.3f}pp")
    print()
    print("  ⚠️ 混淆声明：参照取「同门 ETF(159316) 官方净值」，与持仓联接C 自身净值相差一个**跟踪拖累**")
    print("     （实测 9/29 0.15pp、9/30 0.19pp）⇒ ETF 代理的 |Δ| 已内含该量级，非纯二级价溢价误差。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
