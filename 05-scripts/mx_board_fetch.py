#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mx_board_fetch.py — A2 板块判据的**当日档**取数器（2026-09-29 建立）

🔴 建立原因（实测发现，推翻此前的「当日档未生成」结论）：
   2026-09-29 之前，A2 判据在盘中反复记为「板块当日档未生成 ⇒ fail-closed」，
   据此在 9/28、9/29 两份报告里写「9/29 A2 判定权不下放」。**该结论是错的。**
   实测（2026-09-29 15:0x）：mx-data 用 **「<主题名> 板块 当前涨跌幅」** 问句
   即可返回**当日**值；用「<YYYY年M月D日> …板块涨跌幅」的**显式日期问句**则只回上一交易日
   ⇒ **病因是问句形态，不是源缺失。** 与 2026-09-18「DDX 被误判无源」同形：
   又一次「端点/问句 ≠ 无源」。

⚠️ 口径纪律（§二.13）：本器返回的是 **成份区间涨跌幅（流通市值加权平均）**，
   与东财 push2 板块 `f3` **不是同一指标族**，数值不可互换（容忍带 1.0pp）。
   ⛔ 不得与 push2/同花顺口径拼成同一条时间序列。

⛔ 铁律：**不得把「上一交易日值」当作「当日值」使用**。若返回的最新日期 ≠ 目标日，
   一律判 `stale` 并交由调用方 fail-closed —— 见 `fetch_boards()` 的 status 三态。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PY = os.environ.get("ANCHOR_PYTHON") or r"C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe"
MX_DATA_SCRIPT = Path(r"C:\Users\lenovo\.qoder-cn\skills\mx-data\mx_data.py")
OUT_DIR = Path(os.environ.get("ANCHOR_MX_OUT") or r"C:\Users\lenovo\AppData\Local\Temp\mxdata")

# A2 四主题（与 §2.1 / gen_watchlist_status.py 同一套）
A2_THEMES = ("固态电池", "人形机器人", "智能驾驶", "有色金属")

_PCT_RE = re.compile(r"^-?\d+(?:\.\d+)?%$")


def _parse_pct(s: object) -> float | None:
    """'1.315%' → 1.315；非法值 → None（⛔ 不静默按 0 处理）。"""
    if not isinstance(s, str) or not _PCT_RE.match(s.strip()):
        return None
    return float(s.strip().rstrip("%"))


def _find_tables(payload: object) -> list:
    """稳健定位 dataTableDTOList。

    ⚠️ 实测（2026-09-29）该列表在 ``data.data.searchDataResultDTO.dataTableDTOList``
    （**两层 data**），而另一些响应只有一层 ⇒ 不写死单一路径，按候选路径依次尝试，
    最后回退到递归查找。
    """
    for path in (
        ("data", "searchDataResultDTO", "dataTableDTOList"),
        ("data", "data", "searchDataResultDTO", "dataTableDTOList"),
    ):
        cur: object = payload
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        if isinstance(cur, list) and cur:
            return cur

    found: list = []

    def _walk(o: object) -> None:
        if found:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "dataTableDTOList" and isinstance(v, list) and v:
                    found.extend(v)
                    return
                _walk(v)
        elif isinstance(o, list):
            for v in o:
                _walk(v)

    _walk(payload)
    return found


_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _norm_date(key: object) -> str | None:
    """`2026-09-29(日)` / `2026-09-29 15:39` → `2026-09-29`（⛔ 带时间的键不得另行成行）。"""
    m = _DATE_RE.match(str(key).strip())
    return m.group(1) if m else None


def _all_values_are_pct(t: dict) -> bool:
    """该表所有单元格是否都是百分比形态（'1.315%'）。

    🔴 用途＝**回退闸门**：当响应里找不到 `entityName` 含「涨跌幅」的表时，只有
       「值全是百分比」的表才允许被当作涨跌序列。否则**必须 fail-closed 返回空**——
       实测反例（test T5c）：主力资金表的 `'10.52亿元'` 若被回退路径收下，
       会以 `None` 混进涨跌序列，看起来像「该主题当日无涨跌」而非「取错了表」。
    """
    vals = [
        v
        for k, col in (t.get("table") or {}).items()
        if k != "headName" and isinstance(col, list)
        for v in col
    ]
    return bool(vals) and all(isinstance(v, str) and _PCT_RE.match(v.strip()) for v in vals)


def parse_payload(payload: dict) -> dict:
    """从 mx-data `_raw.json` 解析 → {date: {theme: pct}}。

    ⚠️ 一个响应里常有**多张表**（涨跌幅表 + 主力资金表），且日期键异构
    （`2026-09-29(日)` vs `2026-09-29 15:39`）⇒ 必须**先按表过滤**：
    只取 `entityName` 含「涨跌幅」的表（实测为「成份区间涨跌幅(流通市值加权平均)」），
    否则会把资金表的读数混进涨跌序列（2026-09-29 实测踩过）。
    回退路径另加「值全为百分比」闸门，仍不满足 ⇒ 返回空（调用方 fail-closed）。
    """
    tables = _find_tables(payload)
    picked = [t for t in tables if "涨跌幅" in str(t.get("entityName") or "")]
    if not picked:
        picked = [t for t in tables if _all_values_are_pct(t)]
    if not picked:
        return {}

    series: dict[str, dict[str, float | None]] = {}
    for t in picked:
        tb = t.get("table") or {}
        dates = tb.get("headName")
        if not isinstance(dates, list):
            continue
        for col, vals in tb.items():
            if col == "headName" or not isinstance(vals, list):
                continue
            theme = re.sub(r"\((板块|指数)\)$", "", col).strip()
            for d, v in zip(dates, vals):
                day = _norm_date(d)
                if day is None:
                    continue
                series.setdefault(day, {})[theme] = _parse_pct(v)
    return series


def _run_mx(query: str) -> dict:
    """调用 mx_data.py 并回读其 `_raw.json`。"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    # ⚠️ 末位参数＝输出目录（脚本取 sys.argv[-1]）；不传会静默落到 C:\root\...
    r = subprocess.run(
        [PY, str(MX_DATA_SCRIPT), query, str(OUT_DIR).replace("\\", "/")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, env=env,
    )
    if r.returncode != 0:
        raise RuntimeError(f"mx_data.py 退出码 {r.returncode}: {(r.stdout or '')[-300:]}")
    # 取最新生成的 raw.json
    raws = sorted(OUT_DIR.glob("mx_data_*_raw.json"), key=lambda p: p.stat().st_mtime)
    if not raws:
        raise RuntimeError("未找到 mx_data_*_raw.json")
    return json.loads(raws[-1].read_text(encoding="utf-8"))


def a2_hit(chg: float | None, prev: float | None, a2_pct: float = 2.0) -> tuple[bool, str, str]:
    """A2 判定（与 gen_watchlist_status.py:163 同口径）。

    命中条件：**分支① 当日 ≥ a2_pct**  或  **分支② 连续 2 日飘红（当日>0 且 前日>0）**。

    🔴 反向断言要点（test_mx_board_fetch.py T4）：分支②**必须同时要求前日 > 0**。
       若简化为「当日 > 0 即命中」，9/29 四主题会被**全部误判命中**（当日全为正、
       前日全为负）⇒ 放行本该禁买的、或禁掉本该放行的。
    """
    if chg is None:
        return False, "缺值", "当日值缺失 ⇒ 不可判定"
    if chg >= a2_pct:
        return True, "分支①", f"当日 {chg:+.4f}% ≥ {a2_pct:.2f}% ⇒ A2 命中"
    if prev is None:
        return False, "缺前日", f"当日 {chg:+.4f}% < {a2_pct:.2f}%；前日缺值 ⇒ 分支②不可判定"
    if chg > 0 and prev > 0:
        return True, "分支②", f"当日 {chg:+.4f}% > 0 且 前日 {prev:+.4f}% > 0 ⇒ 连续 2 日飘红 ⇒ A2 命中"
    return False, "不成立", (
        f"当日 {chg:+.4f}%（<{a2_pct:.2f}%）；前日 {prev:+.4f}% "
        f"{'≤ 0 ⇒ 分支②不成立' if prev <= 0 else '> 0 但当日 ≤ 0 ⇒ 分支②不成立'}"
    )


def fetch_boards(themes=A2_THEMES, target_date: str | None = None) -> dict:
    """取板块**当日档**。

    status 三态：
      - ``ok``    最新日期 == target_date（或未指定 target 时视为当日）
      - ``stale`` 最新日期 **早于** target_date ⇒ ⛔ 调用方必须 fail-closed，不得当当日用
      - ``failed`` 取数异常
    """
    target_date = target_date or __import__("datetime").date.today().isoformat()
    query = f"{' '.join(themes)} 板块 当前涨跌幅"
    try:
        series = parse_payload(_run_mx(query))
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "reason": str(e), "target": target_date, "series": {}, "rows": []}

    if not series:
        return {"status": "failed", "reason": "解析后无数据行", "target": target_date, "series": {}, "rows": []}

    newest = max(series)
    status = "ok" if newest == target_date else "stale"
    dates = sorted(series)
    prev = next((d for d in reversed(dates) if d < newest), None)

    rows = []
    for th in themes:
        chg = series.get(newest, {}).get(th)
        prv = series.get(prev, {}).get(th) if prev else None
        hit, branch, note = a2_hit(chg, prv)
        rows.append({"theme": th, "chg": chg, "prev": prv, "hit": hit, "branch": branch, "note": note})

    return {
        "status": status, "target": target_date, "newest": newest, "prev": prev,
        "query": query, "series": series, "rows": rows,
    }


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else None
    res = fetch_boards(target_date=target)
    print(f"A2 板块当日档 · target={res['target']} · status=**{res['status']}**")
    if res["status"] == "failed":
        print("  ❌", res["reason"])
        return 2
    print(f"  最新日期={res.get('newest')} · 前日={res.get('prev')}")
    if res["status"] == "stale":
        print("  🔴 最新日期 ≠ 目标日 ⇒ fail-closed（⛔ 不得当当日值用）")
    for r in res["rows"]:
        flag = "🔴 命中" if r["hit"] else "✅ 不成立"
        print(f"  {r['theme']:8s} 当日 {r['chg']}% · 前日 {r['prev']}% ⇒ {flag}（{r['branch']}）")
    hit_any = any(r["hit"] for r in res["rows"])
    print(f"  合计：A2 {'命中 ⇒ 禁买' if hit_any else '四主题全部不成立 ⇒ 不构成禁买'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
