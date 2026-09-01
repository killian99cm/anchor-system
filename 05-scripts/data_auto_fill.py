# -*- coding: utf-8 -*-
"""
Anchor 数据自动化 MVP（data_auto_fill.py）v2（2026-09-01 A1 修复）
- 作用：复用妙想 API 查询各持仓基金最新日涨跌，生成「数据回填候选」供用户确认
- 铁律：本脚本【只生成候选文件，绝不写入 portfolio_data.json】——数据权威仍以用户确认为准
- 输出：Anchor/04-reviews/daily/{date}-数据回填候选.json

v2 修复（系统优化审计剩余项 A1）：
  1. 查询词与持仓名解耦：QUERY_SPECS 分离「查询问法 queries（规范名/代码）」与
     「持仓匹配关键词 match」——不再把"全名+代码"整串同时当查询词和持仓 key
     （旧版 mv.get("华夏…C 008888") 因持仓名无代码后缀恒为 0，估算日盈亏静默失效）
  2. 匹配失败 / 全部问法无数据 → 收集到 failed，结尾 [WARN] 汇总并以退出码 1 提示，不静默
  3. 日期清洗：去掉时间/区间后缀，统一输出 YYYY-MM-DD（区间取首个日期）
  4. diff 确认：每个候选带组合现值（current_day_pnl）与新算值（est_day_pnl）及差值，
     控制台打印 diff 表，便于用户核对后再决定是否回填（脚本本身永不写 JSON）
"""
import json
import os
import re
import sys
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths
from daily_advice import mx_query  # 复用妙想 API 查询

JSON_PATH = paths.DATA_PATH
OUT_DIR = paths.REVIEWS_DIR / "daily"

# 查询规格：label=展示名；queries=妙想问法候选（规范名/代码，按序尝试，不拼后缀）；
# match=在 portfolio_data.json 持仓名中的匹配关键词（与查询解耦，按序命中第一个 mv>0 的持仓）
QUERY_SPECS = [
    {"label": "半导体C", "queries": ["华夏国证半导体芯片ETF联接C", "008888"], "match": ["半导体芯片", "半导体"]},
    {"label": "创新药C", "queries": ["易方达恒生港股通创新药ETF联接C"], "match": ["创新药"]},
    {"label": "纳指C", "queries": ["天弘纳斯达克100指数(QDII)C"], "match": ["纳斯达克100指数"]},
    {"label": "纳指A", "queries": ["华泰柏瑞纳斯达克100ETF联接A", "008887"], "match": ["纳斯达克100ETF"]},
    {"label": "证券C", "queries": ["易方达证券ETF联接C", "012590"], "match": ["证券ETF"]},
    {"label": "黄金A", "queries": ["国泰黄金ETF联接A"], "match": ["国泰黄金"]},
    {"label": "通利A", "queries": ["天弘通利混合A"], "match": ["通利"]},
]

# 问法后缀（对每个 query 依次尝试）
QUERY_SUFFIXES = [" 最新净值 日涨跌幅", " 复权单位净值增长率", " 最新日涨跌幅"]


def load_holdings():
    """返回持仓列表（name/mv/day_pnl/pnl/group），只保留有效持仓。"""
    with open(JSON_PATH, encoding="utf-8") as f:
        d = json.load(f)
    out = []
    for h in d.get("holdings_summary", []):
        out.append({
            "name": h.get("name", ""),
            "mv": h.get("mv", 0) or 0,
            "day_pnl": h.get("day_pnl", 0),
            "pnl": h.get("pnl", 0),
            "group": h.get("group", ""),
        })
    return out


def match_holding(spec, holdings):
    """按 spec.match 关键词在持仓中找第一个 mv>0 的持仓（与查询词解耦）。"""
    for kw in spec["match"]:
        for h in holdings:
            if kw in h["name"] and h["mv"] > 0:
                return h
    # 退一步：mv=0 也返回（便于展示名称），但标记无市值
    for kw in spec["match"]:
        for h in holdings:
            if kw in h["name"]:
                return h
    return None


def clean_date(raw):
    """清洗妙想返回日期：去时间/区间后缀，统一 YYYY-MM-DD；区间取首个日期。"""
    s = str(raw or "").strip()
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})[-/](\d{1,2})", s)  # 仅 MM-DD，补当前年
    if m:
        return f"{date.today().year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return ""


def fetch_latest_pct(spec: dict) -> dict:
    """对 spec.queries × 问法后缀依次尝试，取第一个可解析为百分比的结果。"""
    tried = []
    for q in spec["queries"]:
        for suffix in QUERY_SUFFIXES:
            v = f"{q}{suffix}"
            tried.append(v)
            try:
                rows = mx_query(v, timeout=40)
            except Exception as exc:
                continue
            for r in rows:
                val = str(r.get("value", "")).replace("%", "").strip()
                try:
                    pct = float(val)
                except ValueError:
                    continue
                return {
                    "pct": pct,
                    "date": clean_date(r.get("date")),
                    "entity": r.get("entity", ""),
                    "query": v,
                }
    return {"error": "全部问法无数据", "tried": tried}


def main():
    holdings = load_holdings()
    today = date.today().isoformat()
    results = []
    failed = []

    print(f"=== 数据回填候选生成（{today}）===")
    print(f"{'标的':<8}{'查询涨跌':>10}{'现日盈亏':>11}{'估算日盈亏':>12}{'差值':>9}  数据日期")
    for spec in QUERY_SPECS:
        holding = match_holding(spec, holdings)
        r = fetch_latest_pct(spec)
        base_mv = holding["mv"] if holding else 0
        matched_name = holding["name"] if holding else ""

        entry = {
            "label": spec["label"],
            "matched_holding": matched_name,
            "base_mv": base_mv,
        }
        if holding is None:
            failed.append(f"{spec['label']}（持仓未匹配，关键词 {spec['match']}）")
        entry.update(r)

        cur_day_pnl = holding["day_pnl"] if holding else None
        est = round(base_mv * r["pct"] / 100, 2) if ("pct" in r and base_mv) else None
        if est is not None:
            entry["est_day_pnl"] = est
        if isinstance(cur_day_pnl, (int, float)):
            entry["current_day_pnl"] = cur_day_pnl
            if est is not None:
                entry["diff_vs_current"] = round(est - cur_day_pnl, 2)

        if "pct" in r:
            diff = entry.get("diff_vs_current")
            diff_s = f"{diff:+.1f}" if isinstance(diff, (int, float)) else "--"
            cur_s = f"{cur_day_pnl:+.1f}" if isinstance(cur_day_pnl, (int, float)) else "--"
            est_s = f"{est:+.1f}" if est is not None else "--"
            print(f"{spec['label']:<8}{r['pct']:>+9.2f}%{cur_s:>11}{est_s:>12}{diff_s:>9}  {r.get('date','')}")
        else:
            failed.append(f"{spec['label']}（{r.get('error')}）")
            print(f"{spec['label']:<8}{'❌ 无数据':>10}{'--':>11}{'--':>12}{'--':>9}")
        results.append(entry)

    out = {
        "generated": today,
        "note": "数据回填候选——仅供用户确认，未写入 portfolio_data.json（数据铁律：权威以用户确认为准）；"
                "diff_vs_current=新算估算日盈亏-组合现值，核对后再决定是否回填",
        "failed": failed,
        "candidates": results,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{today}-数据回填候选.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n候选已生成（未写入 JSON）: {out_path}")

    # A1：匹配/取数失败不静默——显式 WARN 汇总，并用非 0 退出码提示调用方
    if failed:
        print(f"\n[WARN] {len(failed)} 项未成功取数/匹配：")
        for msg in failed:
            print(f"  - {msg}")
        print("候选文件已含成功项；请检查查询词或稍后重试。")
        return 1
    print("\n全部标的取数成功。请对照 diff_vs_current 确认后再回填。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
