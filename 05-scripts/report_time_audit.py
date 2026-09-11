#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""存量时间错标登记器  （2026-09-11 事故后建）

背景：2026-09-11 事件后对全库做了一次时间校验，发现历史归档里存在大量同类错标
（星期写错、场外基金用「收盘价」当触发线）。按 2026-09-11 用户裁决：
**只标注、不改写** —— 历史归档是时点记录，改写会破坏审计链；
但如果连登记都不做，这些错误就会在每次全库扫描时反复出现、无法与「新增错误」区分。

本脚本产出「时间错标存量登记.md」，把存量冻结成一个可核对的基线：
  · 记录扫描时刻、总处数、逐文件明细
  · 明确「此表只增不减」以外的变化都视为新增，须由写入门禁拦下

用法：
  python report_time_audit.py            # 重新扫描并覆盖登记表
  python report_time_audit.py --check    # 只比对当前扫描与登记基线，不写文件
"""
from __future__ import annotations

import argparse
import datetime
import io
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ANCHOR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from report_time_check import check_text, collect_all_md  # noqa: E402

OUT = ANCHOR / "00-system" / "时间错标存量登记.md"


def scan() -> list[dict]:
    rows = []
    for p in collect_all_md():
        try:
            text = io.open(p, "rb").read().decode("utf-8", "ignore")
        except OSError:
            continue
        res = check_text(text, datetime.date.today().year)
        if not res["a"] and not res["b"]:
            continue
        try:
            rel = p.relative_to(ANCHOR.parent).as_posix()
        except ValueError:
            rel = p.as_posix()
        rows.append({"path": rel, "a": res["a"], "b": res["b"]})
    rows.sort(key=lambda r: (-len(r["a"]), r["path"]))
    return rows


def summarize(rows: list[dict]) -> tuple[int, int]:
    return sum(len(r["a"]) for r in rows), sum(len(r["b"]) for r in rows)


def write_register(rows: list[dict]) -> None:
    na, nb = summarize(rows)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [
        "# 时间错标存量登记（只标注·不改写）",
        "",
        f"> 扫描时刻：**{now}** ｜ 扫描范围：`04-reviews/` `01-rules/` `00-system/` `AI-Collab/ai-bridge/`",
        f"> 基线：🔴 星期错标 **{na} 处** ／ 🟡 时点可执行性存疑 **{nb} 处**，分布于 **{len(rows)} 个文件**",
        "",
        "## 为什么只标注不改写",
        "",
        "2026-09-11 用户裁决。历史归档是**时点记录**：改写会破坏审计链，",
        "此后便无法从文件本身看出「系统曾经写错过什么」。",
        "但登记是必须的——否则存量会在每次扫描里反复出现，与**新增错误**混在一起，",
        "最终导致白名单吃掉真错。**本表的作用就是把存量冻结成一条基线。**",
        "",
        "**维护规则**：本表只增不减。若某次扫描数 **高于** 基线 → 说明有**新增**错标，",
        "须按被修文件逐个回查（写入门禁 `~/.claude/hooks/pretooluse_time_gate.py` 本应在落盘前拦下）。",
        "重扫：`python Anchor/05-scripts/report_time_audit.py`",
        "",
        "---",
        "",
        "## 逐文件明细",
        "",
    ]
    for r in rows:
        L.append(f"### `{r['path']}` — 🔴 {len(r['a'])} ／ 🟡 {len(r['b'])}")
        L.append("")
        if r["a"]:
            L.append("| 行 | 文中写法 | 实为 | 上下文 |")
            L.append("|----|---------|------|--------|")
            for h in r["a"]:
                ctx = h["context"].replace("|", "\\|")[:70]
                L.append(f"| {h['line']} | `{h['text']}` | {h['expected']} | {ctx} |")
            L.append("")
        if r["b"]:
            L.append("🟡 时点可执行性存疑（场外语境把「收盘/尾盘/盘后」当截止）：")
            L.append("")
            for h in r["b"]:
                L.append(f"- 行 {h['line']}：`{h['text']}` ｜ {h['context'][:80]}")
            L.append("")
    L += [
        "---",
        "",
        "## 类别说明",
        "",
        "**🔴 星期错标**：「M/D（周X）」与 `datetime` 实算不符。两类来源：",
        "① **反推**——从已知事件日期倒推星期（9/11 事故即此类，把 9/15 写成周一实为周二）；",
        "② **复制**——沿用上一份文件的星期标注。",
        "",
        "**🟡 时点可执行性存疑**：场外 / ETF联接 / QDII 标的，用「收盘价」当触发条件，",
        "却不写何时提交。实际执行走的是「收盘确认 → 次日盘中提交」（9/10 即如此），",
        "但报告从不写「次日几点提交」，读起来像当天收盘执行。",
        "**已由规则手册附录D（v3.7）定性**：场外须 15:00 前提交按当日净值，",
        "截止时点一律写具体钟点（如「14:30 前提交」）。",
        "",
    ]
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"[audit] 登记表已写入：{OUT}")
    print(f"[audit] 🔴 {na} 处 ／ 🟡 {nb} 处 ／ {len(rows)} 个文件")


def check_baseline(rows: list[dict]) -> int:
    """比对当前扫描与登记基线：多于基线即视为新增。"""
    import re
    if not OUT.exists():
        print(f"[audit] 尚无基线（{OUT.name} 不存在），请先运行不带 --check 的模式。")
        return 0
    m = re.search(r"🔴 星期错标 \*\*(\d+) 处\*\*.*?🟡 时点可执行性存疑 \*\*(\d+) 处\*\*",
                  OUT.read_text(encoding="utf-8"), re.S)
    if not m:
        print("[audit] 基线文件格式无法解析。")
        return 0
    base_a, base_b = int(m.group(1)), int(m.group(2))
    na, nb = summarize(rows)
    print(f"[audit] 基线 🔴{base_a}/🟡{base_b}  ｜  当前 🔴{na}/🟡{nb}")
    if na > base_a or nb > base_b:
        print("[audit] ❌ 高于基线 —— 存在**新增**时间错标，请逐个回查（门禁本应拦下）")
        return 1
    print("[audit] ✅ 未超过基线（存量未被清理，也不应清理）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="存量时间错标登记器")
    ap.add_argument("--check", action="store_true", help="只比对基线，不写文件")
    args = ap.parse_args()
    rows = scan()
    if args.check:
        return check_baseline(rows)
    write_register(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
