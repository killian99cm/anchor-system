#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evidence_index.py — 证据索引器（Anchor v4.5 · 落实 #C1-55）

【为什么存在】
2026-10-31 补 10 月日台账时，脚本只按 `daily_snapshot_202610XX.md` 一种命名检索，
漏掉 `2026-10-XX-深度复盘.html` 整套文件，于是宣布「10 个交易日没有数据」。
真实覆盖是 15/17（88.2%）。**「我没找到」被当成了「它不存在」。**

更糟的是那套 `daily_snapshot` 里有 8 份是空壳：文件名改了日期，内容还是 10/09 的，
总资产一律 57,125。**文件名说今天是 X，内容说今天是 Y —— 这种文件比没有文件更危险**，
因为它会让检索程序「找到了」而停下。

本脚本做三件事：
  1. 多模式全量匹配（文件名 ISO / 紧凑 / 短月日 / 内容），⛔ 不用单一模式定论
  2. 空壳检测：内容里的日期与文件名日期不符 ⇒ 标 SHELL，不计入有效证据
  3. 输出某月每个交易日的证据覆盖，直接给出「哪些天是真没有，哪些天是我没找到」

【用法】
    python evidence_index.py --month 2026-10        # 覆盖表
    python evidence_index.py --date 2026-10-22      # 单日全部证据
    python evidence_index.py --month 2026-10 --json # 机器可读
    python evidence_index.py --month 2026-10 --write-meta   # 写入 _meta 供 audit 消费

退出码：0 正常 / 1 存在疑似空壳文件 / 2 参数错误
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import paths

# ============ 扫描范围（宁可多扫，不可漏扫） ============
SCAN_DIRS = [
    paths.REVIEWS_DIR,
    paths.DASHBOARD_DIR,
    paths.SYSTEM_DIR,
    paths.DESKTOP / "deliverables",
    paths.DESKTOP / "Tmp",
    paths.MX_PRECISE_DIR,
]
SCAN_GLOBS = ["*.md", "*.html", "*.txt", "*.json", "*.csv"]
TEXT_SUFFIX = {".md", ".html", ".htm", ".txt", ".json", ".csv"}
MAX_BYTES = 6000           # 空壳检测只读开头，够用且快
SKIP_NAME_PARTS = ("node_modules", ".git", "__pycache__", "_整理备份", "backup")

RE_ISO = re.compile(r"20\d{2}-\d{2}-\d{2}")
RE_COMPACT = re.compile(r"20\d{6}")


def all_files():
    """列出扫描范围内全部候选文件（含大小与 mtime），供多模式匹配。"""
    out = []
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for pat in SCAN_GLOBS:
            for p in base.rglob(pat):
                s = str(p)
                if any(x in s for x in SKIP_NAME_PARTS):
                    continue
                if p.suffix.lower() not in TEXT_SUFFIX:
                    continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                out.append({"path": p, "size": st.st_size, "mtime": st.st_mtime})
    return out


def read_head(p, n=MAX_BYTES):
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(n)
    except OSError:
        return ""


def first_date(text):
    """内容里第一个出现的日期，作为「这个文件在讲哪一天」的判据。"""
    m = RE_ISO.search(text)
    if m:
        return m.group(0)
    m = RE_COMPACT.search(text)
    if m:
        s = m.group(0)
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return None


def name_dates(name):
    """文件名里的全部日期（多模式）。返回 (iso_list, compact_list)。"""
    iso = RE_ISO.findall(name)
    comp = [f"{s[:4]}-{s[4:6]}-{s[6:]}" for s in RE_COMPACT.findall(name)]
    return iso, comp


DOC_SUFFIX = {".md", ".html", ".htm", ".txt"}
DATA_SUFFIX = {".csv", ".json"}


def classify(rec, target: date):
    """判断一个文件对目标日而言属于哪类证据。

    分级理由（2026-10-31 首版的两个误报）：
      · alipay_1031.csv 含有全月日期 ⇒ 曾被当成每一天的证据，实际它是**全月账单**，
        属于辅助数据，不能算「这一天有复盘」。
      · 2026-10-07-10月8日复市分析.md 文件名 10-07、正文讲 10-08 ⇒ 曾被判空壳，
        实际是「当晚写的次日预案」，属正常。
    所以只有**同类命名体系（前缀+8位日期）内内容日期不符**才判 SHELL。
    """
    t_iso = target.isoformat()
    t_comp = target.strftime("%Y%m%d")
    t_md = target.strftime("%m-%d")
    t_md2 = target.strftime("%m%d")
    p = rec["path"]
    name = p.name
    suffix = p.suffix.lower()

    iso, comp = name_dates(name)
    hit_name_iso = t_iso in iso                 # 2026-10-22-xxx.md
    hit_name_comp = t_iso in comp               # daily_snapshot_20261022.md
    hit_short = (t_md in name) or (t_md2 in name)

    text = read_head(p)
    hit_content = t_iso in text or t_comp in text
    head_date = first_date(text)

    # —— 文件名以「完整日期」命中的两类
    if hit_name_iso or hit_name_comp:
        if suffix in DATA_SUFFIX:
            return {"verdict": "AUX", "why": "数据文件（非复盘文档），不计入覆盖率",
                    "head_date": head_date}
        if head_date and head_date != t_iso:
            # 紧凑日期式命名（前缀_YYYYMMDD）是「命名错位」的高发区
            if hit_name_comp:
                later = head_date > t_iso
                return {"verdict": "SHELL",
                        "why": (f"内容日期 {head_date} 晚于文件名 {t_iso} —— 不可能，必为人工笔误"
                                if later else
                                f"文件名 {t_iso}，内容实为 {head_date}（命名滞后，内容才有值）"),
                        "head_date": head_date, "name_date": t_iso, "time_reversed": later}
            # ISO 式命名（YYYY-MM-DD-标题）常写次日预案，降级为待查而非错位
            return {"verdict": "WEAK",
                    "why": f"文件名 {t_iso}，正文主讲 {head_date}（可能是次日预案），需人工确认",
                    "head_date": head_date, "name_date": t_iso, "time_reversed": head_date > t_iso}
        if not hit_content:
            return {"verdict": "WEAK",
                    "why": f"文件名含 {t_iso}，但正文前 {MAX_BYTES} 字未出现该日期",
                    "head_date": head_date}
        return {"verdict": "OK", "why": "文件名与内容日期一致", "head_date": head_date}

    # —— 文件名无完整日期，但内容含目标日
    if hit_content:
        if suffix in DATA_SUFFIX:
            return {"verdict": "AUX", "why": "数据文件（如全月账单），含该日流水但不等于当日复盘",
                    "head_date": head_date}
        return {"verdict": "OK", "why": f"文件名无日期，但内容出现 {t_iso}", "head_date": head_date}

    if hit_short:
        return {"verdict": "WEAK", "why": f"文件名只有短日期 {t_md}，可能是误匹配", "head_date": head_date}

    return {"verdict": "NO", "why": "", "head_date": head_date}


def scan_day(files, target: date):
    hits = []
    for rec in files:
        r = classify(rec, target)
        if r["verdict"] == "NO":
            continue
        hits.append({
            "file": str(rec["path"]),
            "name": rec["path"].name,
            "size": rec["size"],
            "verdict": r["verdict"],
            "why": r["why"],
            "head_date": r.get("head_date"),
            "name_date": r.get("name_date"),
            "time_reversed": bool(r.get("time_reversed")),
        })
    order = {"OK": 0, "WEAK": 1, "AUX": 2, "SHELL": 3}
    hits.sort(key=lambda x: (order[x["verdict"]], -x["size"]))
    return hits


def trading_days(month: str):
    """列出该月的工作日（不含法定节假日表，节假日在 <3 天缺口时人工确认）。"""
    y, m = map(int, month.split("-"))
    d = date(y, m, 1)
    out = []
    while d.month == m:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def render_month(month, files, as_json=False, write_meta=False):
    days = trading_days(month)
    result = []
    for d in days:
        hits = scan_day(files, d)
        ok = [h for h in hits if h["verdict"] == "OK"]
        weak = [h for h in hits if h["verdict"] == "WEAK"]
        aux = [h for h in hits if h["verdict"] == "AUX"]
        shell = [h for h in hits if h["verdict"] == "SHELL"]
        result.append({"date": d.isoformat(), "ok": len(ok), "weak": len(weak),
                       "aux": len(aux), "shell": len(shell), "files": hits})

    # 系统里已经「认为」有数据的日子（台账 / 图表），用于区分
    # 「那天本来就不该有记录」和「库里以为有、实际找不到证据」
    claimed = set()
    try:
        with open(paths.DATA_PATH, encoding="utf-8") as f:
            dd = json.load(f)
        for x in dd.get("chart_data", []) or []:
            v = str(x.get("date") or x.get("d") or "")
            if len(v) == 5:
                claimed.add(f"{month}-{v}")
        for blk in (dd.get("_meta") or {}).values():
            if isinstance(blk, dict) and blk.get("daily"):
                for r in blk["daily"]:
                    if r.get("total_assets"):
                        claimed.add(str(r.get("date")))
    except (OSError, ValueError):
        pass

    covered = [r for r in result if r["ok"] > 0]
    cov_pct = round(len(covered) / len(result) * 100, 1) if result else 0
    shells = [(r["date"], h) for r in result for h in r["files"] if h["verdict"] == "SHELL"]
    gaps = [r["date"] for r in result if r["ok"] == 0]
    lying = [d for d in gaps if d in claimed]

    if as_json:
        print(json.dumps({
            "month": month,
            "trading_days": len(result),
            "covered_days": len(covered),
            "coverage_pct": cov_pct,
            "gap_days": gaps,
            "gap_but_claimed_by_data": lying,
            "shell_files": [{"date": d, "file": h["file"], "why": h["why"]} for d, h in shells],
            "days": result,
        }, ensure_ascii=False, indent=2))
    else:
        print("=" * 88)
        print(f"  证据索引 · {month} · 扫描 {len(files)} 个文件（6 目录 / 4 命名模式 / 内容检索）")
        print("=" * 88)
        print(f"\n  {'日期':<12}{'周':<4}{'有效':<6}{'待查':<6}{'辅助':<6}{'空壳':<6} 主要证据")
        print("  " + "-" * 82)
        wk = "一二三四五六日"
        for r in result:
            d = date.fromisoformat(r["date"])
            top = next((h for h in r["files"] if h["verdict"] == "OK"), None)
            top_s = top["name"][:32] if top else "—"
            flag = "  ⬅ 无有效证据" if r["ok"] == 0 else ""
            if r["ok"] == 0 and r["date"] in claimed:
                flag = "  ⬅ 🔴 数据里声称有、证据找不到"
            print(f"  {r['date']:<12}{wk[d.weekday()]:<4}{r['ok']:<6}{r['weak']:<6}"
                  f"{r['aux']:<6}{r['shell']:<6} {top_s}{flag}")
        print()
        print("  " + "-" * 82)
        print(f"  覆盖 {len(covered)}/{len(result)} 个工作日 = {cov_pct}%")
        if gaps:
            quiet = [d for d in gaps if d not in claimed]
            lie = [d for d in gaps if d in claimed]
            if lie:
                print(f"  🔴🔴 最危险的一类：{', '.join(lie)}")
                print("      数据文件声称这些天有记录，但四种模式全扫都找不到证据 ——")
                print("      说明数值有出处却不可追溯，或证据文件被移动/删除。必须当轮定位。")
            if quiet:
                print(f"  🟡 无记录日（数据里也没声称有）：{', '.join(quiet)}")
                print("      多半是法定休市（国庆/春节等）。⛔ 只能写「库里确实没有」，不得据此推断任何数值；")
                print("      若确认不是休市，则这是真缺口，须补证据。")
        else:
            print("  🟢 无真空日")
        if shells:
            print(f"\n  ⚠️  发现 {len(shells)} 份空壳文件（同类命名体系内，内容日期 ≠ 文件名日期）：")
            for d, h in shells[:12]:
                print(f"      {h['name']}  ← {h['why']}")
            print("      ⛔ 这类文件会被「找到」并骗过检索，比没有文件更危险，须清理或重生成")

    if write_meta:
        p = paths.DATA_PATH
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        key = f"evidence_index_{month.replace('-', '')}"
        data.setdefault("_meta", {})[key] = {
            "generated_at": date.today().isoformat(),
            "month": month,
            "scanned_files": len(files),
            "trading_days": len(result),
            "covered_days": len(covered),
            "coverage_pct": cov_pct,
            "gap_days": gaps,
            "gap_but_claimed_by_data": lying,
            "shell_files": [h["file"] for _d, h in shells],
            "shell_detail": [{"file": h["file"], "name": h["name"],
                              "name_date": h.get("name_date"), "head_date": h.get("head_date"),
                              "time_reversed": h.get("time_reversed")} for _d, h in shells],
            "time_reversed_count": sum(1 for _d, h in shells if h.get("time_reversed")),
            "method": "多模式全扫（文件名 ISO/紧凑/短月日 + 内容前 6000 字），非单一命名模式（#C1-55）",
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n  ✅ 已写入 _meta.{key}")

    return 1 if (shells or lying) else 0


def render_day(dstr, files):
    d = date.fromisoformat(dstr)
    hits = scan_day(files, d)
    print("=" * 84)
    print(f"  证据索引 · {dstr}（{d.strftime('%a')}）· 命中 {len(hits)} 个文件")
    print("=" * 84)
    if not hits:
        print("\n  🔴 四种命名模式 + 内容检索全部未命中。")
        print("     结论：库里确实没有这一天的证据。⛔ 不得据此推断任何数值。")
        return 0
    for h in hits:
        icon = {"OK": "✅", "WEAK": "⚠️ ", "SHELL": "❌"}[h["verdict"]]
        print(f"\n  {icon} {h['name']}  ({h['size'] / 1024:.1f} KB)")
        print(f"      {h['why']}")
        print(f"      {h['file']}")
    ok = [h for h in hits if h["verdict"] == "OK"]
    print(f"\n  → 有效证据 {len(ok)} 份" + ("" if ok else "（⛔ 不可用于重建台账）"))
    return 1 if any(h["verdict"] == "SHELL" for h in hits) else 0


def main():
    argv = sys.argv[1:]
    month = dstr = None
    for i, a in enumerate(argv):
        if a == "--month" and i + 1 < len(argv):
            month = argv[i + 1]
        if a == "--date" and i + 1 < len(argv):
            dstr = argv[i + 1]
    if not month and not dstr:
        print(__doc__)
        sys.exit(2)

    files = all_files()
    if dstr:
        sys.exit(render_day(dstr, files))
    sys.exit(render_month(month, files,
                          as_json="--json" in argv,
                          write_meta="--write-meta" in argv))


if __name__ == "__main__":
    main()
