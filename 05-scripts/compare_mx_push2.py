#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mx ↔ push2 **两口径对拉**（读研工具 · 只读 · 不改任何数据）

存在理由
--------
裁决 **#C1-20**（2026-09-23）给 A2 开了「mx 口径第三级回落」，并附**四条硬约束**，
其中**约束③＝容忍带 `MX_TOL_PP = 0.15pp`**，其**书面目的**是：
「两口径（mx＝成份区间加权 vs push2 `f3`）**在带内可能给出相反结论**」⇒ 带内 fail-closed。

⚠️ 该带宽度的**依据从未被测量过** —— 裁定当时 mx 与 push2 **没有同日的可比值**
（push2 全族限流，`days` 缺 9/23）。2026-09-24 push2 恢复后**首次两级皆备**，
本脚本就是做那次对拉，回答两个问题：

  ① 同日同板块，两口径**差多少**（Δpp ＝ mx − push2）？
  ② 若当日 mx 档被启用，**A2 判定会不会与 push2 档相反**？（＝容忍带是否真的兜得住）

🔴 为什么必须查②而不是只看①：A2 的错向**不对称**（`gen_watchlist_status._eval_a2` 注释：
「**低估即放行本该禁买的**」）⇒ 只要有一条板块**判定翻转且方向是「mx 放行」**，
容忍带就**没有起到它被写下来的作用**。

口径纪律
--------
· 两边的「板块榜」对象**一律由生产函数构造**（`_boards_from_cache` ／ `_boards_from_mx_cache`），
  ⛔ **本脚本不自己拼 dict** —— 否则对拉测的是本脚本的复述，不是生产行为。
· A2 判定**一律调用生产函数** `_eval_a2`，⛔ **不复制判定逻辑**。
· 关联键用**板块代码**（BK####），⛔ 不用名字 —— 名字匹配有子串回退，会把错配读成命中。
· 本脚本**只读**：不写 `board_pct_history.json`、不动 `rule_contract.json`、不发单。

用法
----
    python compare_mx_push2.py                # 全部有 mx 的日期
    python compare_mx_push2.py 2026-09-23     # 指定日期

退出码：0 ＝ 跑完（**不代表对拉通过**）；1 ＝ 无可对拉日期。
"""
from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import paths  # noqa: E402
import fetch_public as fp  # noqa: E402
import gen_watchlist_status as gws  # noqa: E402

HIST = paths.DASHBOARD_DIR / "board_pct_history.json"


def _load():
    with open(HIST, encoding="utf-8") as f:
        return json.load(f)


def _prev_trading_day(days: dict, date_str: str) -> str | None:
    ks = sorted(k for k in days if k < date_str)
    return ks[-1] if ks else None


def _a2_boards(day: dict | None, date_str: str | None, mx: bool) -> dict:
    if mx:
        return gws._boards_from_mx_cache(day, date_str)
    return gws._boards_from_cache(day, date_str)


def _fmt(v) -> str:
    return "—" if v is None else f"{v:+.4f}"


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    hist = _load()
    days = hist.get("days") or {}
    days_mx = hist.get("days_mx") or {}
    meta = hist.get("days_mx_meta") or {}
    # 契约真源：与生产同路（paths.RULE_CONTRACT_PATH）；缺失则回退内置默认并显式标注
    a2_pct, a2_src = 2.0, "内置默认（⛔ 契约未读到）"
    try:
        with open(paths.RULE_CONTRACT_PATH, encoding="utf-8") as f:
            a2_pct = float((json.load(f).get("rules") or {}).get("a2_red_day_pct") or 2.0)
        a2_src = str(paths.RULE_CONTRACT_PATH)
    except Exception as exc:  # noqa: BLE001
        a2_src = f"内置默认（⛔ 读契约失败：{exc}）"

    todo = sorted(d for d in days_mx if (not only or d == only) and d in days)
    skipped = sorted(d for d in days_mx if only and d != only)

    print("=" * 78)
    print(f"mx ↔ push2 对拉｜历史档：{HIST}")
    print(f"days 日期={sorted(days)}｜days_mx 日期={sorted(days_mx)}")
    print(f"契约 a2_red_day_pct={a2_pct}（源：{a2_src}）")
    print(f"容忍带（现值 MX_TOL_PP）={fp.MX_TOL_PP}pp")
    if not todo:
        print("\n⛔ 无可对拉日期：days_mx 的每一天在 days 里都没有同日 push2 档。")
        if skipped:
            print(f"   （被 --date 过滤掉的有：{skipped}）")
        print("=" * 78)
        return 1

    worst = 0.0
    flips: list[tuple[str, str, str, str]] = []
    per_date = {}

    for d in todo:
        m_day, p_day = days_mx[d], days[d]
        prev_d = _prev_trading_day(days, d)
        p2_boards = _a2_boards(p_day, d, mx=False)
        mx_boards = _a2_boards(m_day, d, mx=True)
        p2_prev = days.get(prev_d) if prev_d else None
        mx_prev = days_mx.get(prev_d) if prev_d else None

        print(f"\n【{d}】前一交易日={prev_d or '（无，A2 分支②判不了）'}"
              f"（mx 档{'有' if mx_prev else '无'}）  mx_meta={json.dumps(meta.get(d), ensure_ascii=False)}")
        print(f"{'代码':<8}{'板块':<12}{'mx':>10}{'push2':>10}{'Δpp':>10}   {'A2(mx)':<14}{'A2(push2)':<14}翻转")
        print("-" * 78)

        deltas = []
        for code, mv in sorted(m_day.items()):
            if not isinstance(mv, dict):
                continue
            name = str(mv.get("name") or code)
            pv = p_day.get(code)
            if not isinstance(pv, dict):
                print(f"{code:<8}{name:<12}{_fmt(mv.get('chg_pct')):>10}{'（push2 无此键）':>10}")
                continue
            mx_v, p2_v = mv.get("chg_pct"), pv.get("chg_pct")
            try:
                delta = float(mx_v) - float(p2_v)
            except (TypeError, ValueError):
                delta = None
            if delta is not None:
                deltas.append(abs(delta))
                worst = max(worst, abs(delta))

            # A2：两边各调一次生产判定（mx 侧前日＝mx 档；push2 侧前日＝push2 档）
            m_hit, m_full, _ = gws._eval_a2(name, mx_boards, a2_pct,
                                            prev_day=None, prev_date=prev_d,
                                            prev_day_mx=mx_prev)
            p_hit, p_full, _ = gws._eval_a2(name, p2_boards, a2_pct,
                                            prev_day=p2_prev, prev_date=prev_d)

            def lab(hit, full):
                return ("命中" if hit else ("不成立(完全)" if full else "判不了"))

            flip = ""
            if m_hit is not None and p_hit is not None and m_hit != p_hit:
                flip = "🔴 翻转"
                flips.append((d, code, name, f"mx={lab(m_hit, m_full)} push2={lab(p_hit, p_full)}"))
            elif m_hit != p_hit and (m_hit is None or p_hit is None):
                flip = "⚠️ 一侧判不了"
            print(f"{code:<8}{name:<12}{_fmt(mx_v):>10}{_fmt(p2_v):>10}"
                  f"{(f'{delta:+.4f}' if delta is not None else '—'):>10}   "
                  f"{lab(m_hit, m_full):<14}{lab(p_hit, p_full):<14}{flip}")

        if deltas:
            per_date[d] = (sum(deltas) / len(deltas), max(deltas), len(deltas))
            signs = [float(m_day[c]['chg_pct']) - float(p_day[c]['chg_pct'])
                     for c in m_day if isinstance(m_day[c], dict) and isinstance(p_day.get(c), dict)]
            neg = sum(1 for s in signs if s < 0)
            print(f"  └ n={len(deltas)}　|Δ|均值={per_date[d][0]:.4f}pp　|Δ|最大={per_date[d][1]:.4f}pp"
                  f"　Δ 符号：负 {neg}/{len(signs)}")

    print("\n" + "=" * 78)
    print("结论")
    print("=" * 78)
    tot_n = sum(v[2] for v in per_date.values())
    print(f"· 样本：{len(per_date)} 个交易日 / {tot_n} 条板块（n 很小 ⇒ 只作**首次偏差读数**，"
          f"⛔ 不足以定标）")
    print(f"· |Δ| 最大值 = {worst:.4f}pp　（容忍带现值 {fp.MX_TOL_PP}pp "
          f"⇒ {'⛔ 兜不住' if worst > fp.MX_TOL_PP else '✅ 覆盖'}）")
    if flips:
        print(f"· 🔴 **判定翻转 {len(flips)} 条**（同一交易日、同一板块，两口径 A2 结论相反）：")
        for d, code, name, desc in flips:
            print(f"    - {d} {code} {name}：{desc}")
        print("  ⇒ 容忍带**没有起到它被写下来的作用**（其目的＝防两口径相反结论）⇒ 须重定标。")
        print(f"  ⇒ 按本次实测，容忍带至少须 ≥ {worst:.2f}pp（建议取整到 0.05 的倍数并留余量）。")
    else:
        print("· ✅ 本次未见判定翻转。")
    print("· ⛔ 本脚本只出读数；**是否改 `MX_TOL_PP` ＝ 另一件事**"
          "（改常数＝动 #C1-20 已被用户裁决的约束③，须留痕并报用户）。")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
