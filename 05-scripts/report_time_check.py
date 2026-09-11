#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Anchor 报告时间校验器 v1.0  （2026-09-11 事故后建）

【为什么存在】
2026-09-11 盘中研究报告 + 会话检查点 §144 里，把 9/15 写「周一」（实为周二）、
9/13 写「周六」（实为周日）；并写出场外基金根本无法执行的截止表述
「9/15（周一）收盘仍超限 → 无条件收尾」（场外须 15:00 前提交，写「收盘」当天提交不了）。
系统原有校验（data_processor.validate_integrity V1-V7）全部只覆盖 portfolio_data.json，
报告正文 / 检查点 / 信息桥 —— 零校验面。本脚本补的就是这一段。

【两个检测器】
  A（🔴 确定性）：文中所有「M/D（周X）」与 datetime 实算比对，不符即失败。
                  星期是可计算事实，不由模型心算。
  B（🟡 启发式）：在场外/QDII/联接 语境的「块」内，把「收盘/尾盘/盘后」当作执行截止
                  的表述判为不可执行（场外基金须 15:00 前提交方按当日净值成交）。
                  B 用「结构定位」（先定块再判时点），不用行级邻近正则 —— 因为
                  标的与截止时点常常不在同一行。

【用法】
  python report_time_check.py <文件> [<文件>...]    # 校验；有 🔴 则退出码 1
  python report_time_check.py --latest              # 04-reviews 下 mtime 最新的报告
  python report_time_check.py --all                 # 全库只读审计（恒退出码 0）
  选项：--year 2026   --json   --no-b   --quiet
  行内豁免：行尾写  # noqa:time

【设计约束（踩过的坑，勿改）】
  1. 必须跳过「勘误/引用」行 —— 检查点 §144 的勘误原文里正写着「9/15（周一）」，
     不跳过则首跑就把「记录错误」本身标红，维护者只好加白名单，白名单最终吃掉真错。
  2. B 检测器必须在「块」内判，不能只在行内判 —— 9/11 事故里标的在表 A 行、
     截止时点在表 B 行。
  3. 🔴 才影响退出码，🟡 只提示。闸门职责在 PreToolUse hook，不在本脚本。
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ANCHOR_DIR = SCRIPT_DIR.parent
DESKTOP_DIR = ANCHOR_DIR.parent

# ── 输出编码（Windows 上必须，勿删）─────────────────────────────────────
# 本脚本输出含 🔴/🟡/📄，而 Windows 控制台默认代码页是 GBK（cp936），
# 直接 print 会抛 UnicodeEncodeError 并让整个脚本崩掉——sync_all 用管道抓输出
# 时同样会崩（管道在 3.13 仍按区域编码）。sync_all.run() 以 utf-8/errors=replace
# 解码子进程输出，故此处统一把本进程 stdout/stderr 设为 utf-8，两边对齐。
# 放在模块级：冒烟测试与门禁 import 本模块时一并生效，避免漏改一处。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WEEKDAYS_CN = "一二三四五六日"
WEEKDAY_ALIAS = {"天": "日"}

# ── 行级豁免：回溯/勘误/引用行不参与校验 ────────────────────────────────
SKIP_MARKERS = (
    "勘误", "原写", "曾写", "误写", "错标", "实为", "修正", "更正", "改回",
    "引用", "出处", "前科", "先例", "历史错标", "已改", "教训", "已知线索",
)
INLINE_IGNORE = "# noqa:time"

# ── A 检测器：日期 + 星期 ──────────────────────────────────────────────
_D = r"(?<![\d/])(\d{1,2})\s*(?:[/\-]|月)\s*(\d{1,2})\s*日?"
A_PAREN = re.compile(_D + r"[（(]\s*周?\s*([一二三四五六日天])\s*[）)]")
A_BARE = re.compile(_D + r"\s+周\s*([一二三四五六日天])(?![一-鿿])")

# ── B 检测器：不可执行时点 ─────────────────────────────────────────────
BAD_TIME = r"(?:收盘|尾盘|盘后)"
ACT = r"(?:收尾|提交|赎回|卖出|减仓|清仓|补仓|买入|加仓|止盈|止损)"
B_PAT = re.compile(rf"{BAD_TIME}[^。；\n]{{0,20}}?{ACT}|{ACT}[^。；\n]{{0,20}}?{BAD_TIME}")
GOOD_CLOCK = (
    "14:30", "15:00", "14 点", "15 点", "盘中", "早盘", "开盘", "T+1", "T+2",
    "前一交易日", "次交易日", "下一交易日",
)
# B 只在「指令性」上下文里报警：叙述句（「尾盘恐慌赎回是历史教训」）、
# 标题收尾语（「（22:08 收尾）」）不是指令，报出来只会淹没真问题。
DIRECTIVE = ("→", "触发", "若", "如", "则", "截止", "硬回退", "执行", "条件")
# 这些语境里的「收盘」是事实而非截止：QDII 净值本就按海外收盘计。
EXEMPT_TIME = ("美股收盘", "海外收盘", "隔夜收盘", "境外收盘", "收盘权威入库", "收盘复盘")
OTC_MARKERS = ("场外", "联接", "QDII", "基金C", "基金 C", "C 类", "C类", "C份额", "赎回费")

HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")


def _norm(text: str) -> list[str]:
    """按行切分，兼容 CRLF / 双 CR，保持与原文件一致的可读行号。"""
    return text.replace("\r\r\n", "\n").replace("\r\n", "\n").split("\n")


def _blocks(lines: list[str]) -> list[tuple[int, list[str]]]:
    """按 Markdown 标题切块，返回 [(起始行号(1-based), 块内各行)]。"""
    out, cur, start = [], [], 1
    for i, ln in enumerate(lines, 1):
        if HEADING_RE.match(ln) and cur:
            out.append((start, cur))
            cur, start = [], i
        cur.append(ln)
    if cur:
        out.append((start, cur))
    return out


def check_text(text: str, year: int, *, do_b: bool = True) -> dict:
    lines = _norm(text)
    blocks = _blocks(lines)
    blk_of: dict[int, list[str]] = {}
    for s, blk in blocks:
        for j in range(s, s + len(blk)):
            blk_of[j] = blk
    doc_is_otc = any(any(k in ln for k in OTC_MARKERS) for ln in lines)

    a_hits, b_hits = [], []

    for i, ln in enumerate(lines, 1):
        if INLINE_IGNORE in ln:
            continue
        skipped = any(m in ln for m in SKIP_MARKERS)

        # ── A：星期实算 ──
        if not skipped:
            spans, seen = [], set()
            for rx in (A_PAREN, A_BARE):
                for m in rx.finditer(ln):
                    if (m.start(), m.end()) in seen:
                        continue
                    seen.add((m.start(), m.end()))
                    spans.append(m)
            for m in sorted(spans, key=lambda x: x.start()):
                mo, dy = int(m.group(1)), int(m.group(2))
                wd = WEEKDAY_ALIAS.get(m.group(3), m.group(3))
                try:
                    dt = datetime.date(year, mo, dy)
                except ValueError:
                    continue
                expect = WEEKDAYS_CN[dt.weekday()]
                if expect != wd:
                    a_hits.append({
                        "line": i, "text": m.group(0),
                        "expected": f"周{expect}", "actual": f"周{wd}",
                        "context": ln.strip()[:100],
                    })

        # ── B：不可执行时点（结构定位）──
        if do_b and not skipped:
            bm = B_PAT.search(ln)
            if (bm
                    and any(k in ln for k in DIRECTIVE)
                    and not any(g in ln for g in GOOD_CLOCK)
                    and not any(e in ln for e in EXEMPT_TIME)):
                blk = blk_of.get(i, [])
                otc = any(k in ln for k in OTC_MARKERS) or (
                    doc_is_otc and any(any(k in x for k in OTC_MARKERS) for x in blk)
                )
                if otc:
                    b_hits.append({
                        "line": i, "text": bm.group(0),
                        "context": ln.strip()[:100],
                    })

    return {"a": a_hits, "b": b_hits, "lines": len(lines)}


# 排除：本校验器的「存量登记表」由 report_time_audit.py 生成，其内容按设计
# 就是大量错误示例的**引文**。若把它纳入扫描，登记表会登记自己——实测处数
# 每跑一次就翻倍（32 → 83）。这不是「用白名单掩盖真错」，是切断自引用回路：
# 该文件不描述现实，只描述本校验器的历史输出。
EXCLUDE_NAMES = {"时间错标存量登记.md"}


def collect_all_md() -> list[Path]:
    roots = [
        ANCHOR_DIR / "04-reviews",
        ANCHOR_DIR / "01-rules",
        ANCHOR_DIR / "00-system",
        DESKTOP_DIR / "AI-Collab" / "ai-bridge",
    ]
    out: list[Path] = []
    for r in roots:
        if r.is_dir():
            out.extend(p for p in sorted(r.rglob("*.md")) if p.name not in EXCLUDE_NAMES)
    return out


def latest_report() -> Path | None:
    root = ANCHOR_DIR / "04-reviews"
    if not root.is_dir():
        return None
    md = [p for p in root.rglob("*.md") if p.is_file()]
    return max(md, key=lambda p: p.stat().st_mtime) if md else None


def render(path: Path | None, res: dict, quiet: bool = False) -> int:
    tag = str(path) if path else "(内联文本)"
    a, b = res["a"], res["b"]
    if not quiet:
        print(f"\n📄 {tag}  （{res['lines']} 行）")
    if not a and not b:
        if not quiet:
            print("   ✅ 时间校验通过（星期实算一致 / 无可执行性存疑时点）")
        return 0
    if a:
        print(f"   🔴 星期错标 {len(a)} 处：")
        for h in a:
            print(f"      行{h['line']:>5}  「{h['text']}」→ {h['expected']}（写的是 {h['actual']}）")
            print(f"              {h['context']}")
    if b:
        print(f"   🟡 时点可执行性存疑 {len(b)} 处（场外语境把「收盘/尾盘/盘后」当截止）：")
        for h in b:
            print(f"      行{h['line']:>5}  「{h['text']}」")
            print(f"              {h['context']}")
        print("      → 场外基金须 15:00 前提交方按当日净值成交，应写明确钟点（如「14:30 前提交」）")
    return 1 if a else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Anchor 报告时间校验器")
    ap.add_argument("files", nargs="*", help="待校验的 .md 文件")
    ap.add_argument("--latest", action="store_true", help="校验 04-reviews 下 mtime 最新报告")
    ap.add_argument("--all", action="store_true", help="全库只读审计（恒退出码 0）")
    ap.add_argument("--year", type=int, default=datetime.date.today().year)
    ap.add_argument("--json", action="store_true", help="输出 JSON（供 hook 消费）")
    ap.add_argument("--no-b", action="store_true", help="只跑 A 检测器（确定性）")
    ap.add_argument("--quiet", action="store_true")
    # 只报告不阻断：恒退出码 0。供 sync_all 扫描用——那里的 run() 会把 rc≠0 记成
    # 「命令失败」ERROR，与「报告有问题」是两回事，混在一起会淹没真信号。
    ap.add_argument("--advisory", action="store_true",
                    help="只报告不阻断（恒退出码 0），供 sync_all 事后扫描用")
    args = ap.parse_args(argv)

    targets: list[Path | None] = []
    if args.all:
        targets = collect_all_md()
    elif args.latest:
        p = latest_report()
        if not p:
            print("⚠️ 找不到 04-reviews 下的报告")
            return 0
        targets = [p]
    elif args.files:
        targets = [Path(f) for f in args.files]
    else:
        ap.print_help()
        return 2

    payload, worst = [], 0
    for p in targets:
        if p and not p.is_file():
            print(f"⚠️ 跳过（非文件）：{p}")
            continue
        text = io.open(p, "rb").read().decode("utf-8", "ignore") if p else sys.stdin.read()
        res = check_text(text, args.year, do_b=not args.no_b)
        payload.append({"path": str(p) if p else "(stdin)", **res})
        if args.json:
            continue
        rc = render(p, res, quiet=args.quiet)
        if args.all:
            worst += len(res["a"]) + len(res["b"])
        else:
            worst = max(worst, rc)

    if args.json:
        print(json.dumps({"ok": not any(x["a"] for x in payload), "results": payload},
                         ensure_ascii=False, indent=1))
        return 0

    if args.all:
        na = sum(len(x["a"]) for x in payload)
        nb = sum(len(x["b"]) for x in payload)
        print(f"\n═══ 全库审计 ═══")
        print(f"  扫描 {len(payload)} 份文档 ｜ 🔴 星期错标 {na} 处 ｜ 🟡 时点存疑 {nb} 处")
        print("  提示：历史归档里的旧错标属「存量」，不阻断；新增报告请以 🔴=0 为准。")
        return 0

    if worst:
        print("\n❌ 校验未通过（🔴 星期错标必须修；🟡 请人工确认表述是否可执行）")
    return 0 if args.advisory else worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
