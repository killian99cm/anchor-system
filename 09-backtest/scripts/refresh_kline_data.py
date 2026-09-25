#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回测 K 线刷新器（单 158 · 2026-09-25）

背景
----
`data/_kline_*.md` 的最后一行停在 **2026-08-26**，而公开页 `08-website/track-record.html`
的回测窗口也写死在该日 ⇒ 此后每个交易日**都在拉大公开窗口与实际数据的差距**。

数据源与**判据**
----------------
- 原档来源不明（旧档在低价区只有 2–3 位有效精度）。本工具改用**腾讯前复权日K**（`fqkline`）。
- 🔴 **单次上限 ≈640 根**（实测：请求 2021-09-01~2026-09-24 只回**最后** 640 根 ⇒ 静默截断！）
  ⇒ **必须按年分页**（本工具做法）；`param` 支持显式 `start,end`，实测分页端点各自安好。
- 🔴 **护栏：重叠日差异必须是「舍入级」**（阈值 2%）—— 若某日差异超阈，说明两源**复权口径不同**
  ⇒ **拒绝写入并报红**（宁可窗口旧，也不把口径断层静默写进公开数据）。实测（2026-09-25，sz159995）：
  1207 个重叠日，**中位差 0.377%／最大 1.429%**，且最大值全落在 **0.35–0.41 元**的低价区
  ⇒ **是 3 位小数的量化误差，不是复权断层**。

用法
----
    python refresh_kline_data.py --check     # 只读：报各标的窗口/行数/差异，⛔ 不写盘
    python refresh_kline_data.py             # 抓取并写入 _kline_*.md（先过护栏）

⛔ 不改回测口径；⛔ 不删旧档（覆盖前先备份到 `data/_backup/`）。
"""
import argparse
import io
import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import date

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "..", "data")
BACKUP_DIR = os.path.join(DATA_DIR, "_backup")
SYMBOLS = ["sz159995", "sh512880", "sh515180", "sh518880", "sh513100"]
START = "2021-09-01"
TOL_PCT = 2.0          # 重叠日相对差阈值（%）：超过即判「口径不同」并拒绝写入
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
_ROW = re.compile(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|"
                  r"\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|")


def fetch_page(code: str, s: str, e: str) -> list:
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={code},day,{s},{e},640,qfq")
    req = urllib.request.Request(url, headers=UA)
    body = urllib.request.urlopen(req, timeout=25).read().decode("utf-8")
    node = (json.loads(body).get("data") or {}).get(code) or {}
    return node.get("qfqday") or node.get("day") or []


def fetch_all(code: str, end: str) -> list:
    """**按年分页**取全窗口（⛔ 单次会被 640 上限静默截断 —— 只回最后 640 根）。"""
    out: dict[str, list] = {}
    for y in range(int(START[:4]), int(end[:4]) + 1):
        s = max(START, f"{y}-01-01")
        e = min(end, f"{y}-12-31")
        rows = [r for r in fetch_page(code, s, e) if r and r[0]]
        for r in rows:
            out[r[0]] = r
        print(f"    {y}: {len(rows)} 根")
    return [out[d] for d in sorted(out)]


def read_old(code: str) -> dict:
    p = os.path.join(DATA_DIR, f"_kline_{code}.md")
    if not os.path.exists(p):
        return {}
    old = {}
    with io.open(p, encoding="utf-8") as f:
        for line in f:
            m = _ROW.match(line)
            if m:
                old[m.group(1)] = float(m.group(3))       # 第 3 列 = last/close
    return old


def diff_report(old: dict, new: list) -> tuple:
    """→ (n_overlap, median_pct, max_pct, max_day, n_new_tail)"""
    pairs = []
    for r in new:
        d, close = r[0], float(r[2])
        if d in old and old[d]:
            pairs.append((abs(close - old[d]) / old[d] * 100, d))
    if not pairs:
        return (0, 0.0, 0.0, "", 0)
    pairs.sort(reverse=True)
    med = sorted(p[0] for p in pairs)[len(pairs) // 2]
    tail = len([r for r in new if r[0] not in old])
    return (len(pairs), med, pairs[0][0], pairs[0][1], tail)


def write_dump(code: str, rows: list) -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    src = os.path.join(DATA_DIR, f"_kline_{code}.md")
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(BACKUP_DIR, f"_kline_{code}.md"))
    p = os.path.join(DATA_DIR, f"_kline_{code}.md")
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("| date | open | last | high | low | volume | amount | exchange |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for r in sorted(rows, key=lambda x: x[0], reverse=True):   # 最新在前（沿用旧档约定）
            vol = r[5] if len(r) > 5 else "-"
            f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {vol} | - | - |\n")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只读：不写盘")
    ap.add_argument("--end", default=date.today().isoformat(), help="窗口末端（默认今天）")
    a = ap.parse_args(argv)

    print(f"=== 回测 K 线刷新（腾讯前复权 · 分页）· 窗口 {START} ~ {a.end} ===")
    # 🔴 **先全量校验、通过才写**（fail-closed）：
    #    初版把「判红」写在写入之后 ⇒ 护栏形同虚设（坏数据已经落盘了）。
    #    公开回测数据的写入必须**先验后写**，且**任一标的不合格 ⇒ 全部不写**（原子性）。
    fetched: dict[str, list] = {}
    bad = []
    for code in SYMBOLS:
        print(f"  [{code}]")
        rows = fetch_all(code, a.end)
        old = read_old(code)
        n, med, mx, day, tail = diff_report(old, rows)
        print(f"    新档 {len(rows)} 根（{rows[0][0]} ~ {rows[-1][0]}）｜旧档 {len(old)} 根"
              f"｜重叠 {n}｜中位差 {med:.3f}%｜最大差 {mx:.3f}%（{day}）｜新增尾部 {tail} 日")
        if not rows:
            bad.append((code, float("inf"), "空"))
        elif n and mx > TOL_PCT:
            bad.append((code, mx, day))
        fetched[code] = rows

    if bad:
        print("\n🔴 拒绝写入：下列标的**重叠日差异超阈值**（两源可能复权口径不同，"
              "⛔ 不得静默覆盖公开回测数据）—— **本次一个文件都没写**：")
        for code, mx, day in bad:
            print(f"  - {code}: 最大差 {mx:.3f}%（{day}）> {TOL_PCT}%")
        return 1

    if a.check:
        print("\n✅ 全部标的差异均在舍入级（≤ %.1f%%）⇒ 口径一致，可安全替换" % TOL_PCT)
        print("（--check 模式：未写盘）")
        return 0

    print("\n✅ 全部标的差异均在舍入级（≤ %.1f%%）⇒ 开始写入（旧档备份至 data/_backup/）：" % TOL_PCT)
    for code, rows in fetched.items():
        print(f"  → {write_dump(code, rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
