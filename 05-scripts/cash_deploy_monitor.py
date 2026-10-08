#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cash_deploy_monitor.py — §1.4 现金层补仓触发监控（2026-10-08 建立）

🔴 建立原因
   手册 **§1.4** 明文要求：「每日复盘把 515180 / 纳指 / 沪深300 自高回撤**写入复盘报告**」，
   并给了**量化的补仓触发条件**：
     · 压舱石暴跌 5%+：**515180 红利ETF 或 中证全债/中债综合财富指数** 收盘价自近 20 日高点 **回撤 ≥5%**
     · 核心暴跌 10%+：**纳指100（场外净值）或 沪深300** 自近 20 日高点 **回撤 ≥10%**
     · 执行：**回撤达标当日收盘确认 → 次日 14:30 复核 → 每次 ≤¥1,000，间隔 ≥7 个交易日**
   实测（2026-10-08）：`grep -rn "近 20 日高点|自高回撤" 05-scripts/` **为空**
   ⇒ **该条每日义务在代码层从未实现**，只靠人工记得（与 9/29→9/30 板块缓存断链同族：
   **「写进手册的每日动作，如果没有可执行的载体，就等于没有」**）。

⚖️ 定位
   本器**只读数、只判定、不写盘、不下单**（⛔ 无任何副作用）。
   它的产出是「今天这两条线到没到」＋「还差多少」＋「触发价是多少」，
   供复盘报告直接引用，并作为 §1.4 补仓动作的**唯一判据源**。

🔴 三态纪律（⛔ 不得静默）
   `触发` / `未触发` / **`不可判定`** 三态**必须分开**：
   · 源不可用 ⇒ **`不可判定`**，且**必须打印失败原因**（⛔ 不得落成「未触发」——那会把
     「没查到」伪装成「没到线」，正是 #C1-7「有源却没换」的同型错）
   · 退出码：`2` ＝ 有触发｜`1` ＝ 有不可判定｜`0` ＝ 全部可判定且均未触发

⚠️ 口径诚实披露
   · 「近 20 日高点」本器取**近 20 个交易日内收盘价的最高值**（not 盘中高）。
     §1.4 原文是「**收盘价**自近 20 日高点回撤」—— 基准也按**收盘价口径**取，两侧同口径。
     实测 10/8：515180 收盘高＝盘中高（同一日），沪深300 收盘高 4575.02 < 盘中高 4602.20
     ⇒ 若改用盘中高口径，沪深300 回撤会由 −5.79% 变为 −6.34%（**更易触发**）。
     ⛔ 本器**不选更易触发的那一侧**，取与原文一致的同口径（收盘/收盘）。
   · 「纳指100」按原文为「场外净值」，实测场外净值序列**无源**（mx 返回空）
     ⇒ 本器用 **mx-data 的纳斯达克100指数收盘价**作替代，并**显式标注为替代口径**。
   · 「中债综合财富指数」实测 mx 反复返回**成交量**而非点位 ⇒ 记为 **`不可判定`**（fail-loud）。
     📌 结构性备注：中债综合财富是**总回报指数**，长期单调上行、20 日内回撤 5% 几乎不可能
     ⇒ 该基准在实盘中**接近惰性**，压舱石线事实上等效于「只看 515180」。⚠️ 已登记待裁决。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

PY = os.environ.get("ANCHOR_PYTHON") or r"C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe"
MX_DATA = Path(r"C:\Users\lenovo\.qoder-cn\skills\mx-data\mx_data.py")
MX_OUT = Path(os.environ.get("ANCHOR_MX_OUT") or r"C:\Users\lenovo\AppData\Local\Temp\mxdata")
WINDOW = 20          # §1.4「近 20 日」——交易日的最近 20 个

# 四条基准线（§1.4 原文枚举，⛔ 不得增删）
LINES = (
    {"key": "515180",  "layer": "压舱石", "thr": 5.0,  "src": "tencent", "code": "sh515180",
     "label": "515180 红利ETF（§1.4 压舱石线）"},
    {"key": "cib",     "layer": "压舱石", "thr": 5.0,  "src": "mx",
     "query": "中债综合财富总值指数 最近25个交易日收盘点位",
     "label": "中债综合财富指数（§1.4 压舱石线·结构性惰性）"},
    {"key": "hs300",   "layer": "核心",   "thr": 10.0, "src": "tencent", "code": "sh000300",
     "label": "沪深300（§1.4 核心线）"},
    {"key": "ndx100",  "layer": "核心",   "thr": 10.0, "src": "mx",
     "query": "纳斯达克100指数 最近25个交易日收盘价",
     "label": "纳斯达克100（§1.4 核心线；原文明写「场外净值」⇒ 本器用指数收盘价替代）"},
)


def _num(v) -> float | None:
    """'31082.43点' / '1.4300' / 31082.43 → float；非法 → None（⛔ 不静默按 0）。"""
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    s = v.strip().replace(",", "").replace("%", "")
    for suf in ("点", "元", "亿元", "美元"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    try:
        return float(s)
    except ValueError:
        return None


def _asc(series: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """🔴 **按日期升序规范化**（契约：本模块内一律「先旧后新」）。

    病灶（2026-10-08 实测）：**mx-data 返回的日期是降序**（最新在前），
    而 `drawdown` 取 `series[-window:]` ⇒ 会取到**最旧的 20 条**、`w[-1]` 变成最旧那条
    ⇒ 报出「近20日 9/23~8/26」这种**倒序窗口**与**完全错误的回撤**。
    实测读数：纳指被算成高 30732.40(9/22)、现值 29224.52、回撤 **−4.91%**；
    真实应为高 **31224.47(10/6)**、现值 31082.43、回撤 **−0.46%** ⇒ **错 4.45pp**。
    ⇒ 统一在**取数层**规范化（⛔ 不在 `drawdown` 里偷偷排序 —— 那会掩盖上游乱序）。
    """
    out = sorted(series, key=lambda x: str(x[0]))
    if len(out) != len(series):
        raise RuntimeError("升序规范化后条数变化（日期有重复或不可比）")
    return out


def tencent_series(code: str, n: int = WINDOW + 6) -> list[tuple[str, float]]:
    """腾讯日 K → [(date, close)]（**升序**）；失败抛异常（由调用方转 `不可判定`）。"""
    u = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{n},qfq"
    r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0",
                                           "Referer": "https://gu.qq.com/"})
    raw = urllib.request.urlopen(r, timeout=20).read().decode("utf-8", errors="replace")
    dd = json.loads(raw)["data"][code]
    rows = dd.get("qfqday") or dd.get("day") or []
    out = []
    for row in rows:
        c = _num(row[2])
        if c is not None:
            out.append((str(row[0]), c))
    if not out:
        raise RuntimeError(f"腾讯 {code} 日K 解析后为空")
    return _asc(out)


def mx_series(query: str, out_dir: Path | None = None) -> list[tuple[str, float]]:
    """mx-data → [(date, close)]。结构：data.data.data.searchDataResultDTO.dataTableDTOList[0]
    的 `table` 为 {指标码: [值…], 'headName': [日期…]}。失败抛异常。

    🔴 产物定位＝**每次调用一个独立输出子目录**，⛔ 不用「问句前 N 字符 glob」、
       ⛔ 也不用「新增/变更文件里取最新」。前者实测病灶：脚本把问句里的**空格写成下划线**
       （`..._最近25个交易日收盘点位_raw.json`）而问句里是空格 ⇒ glob **永不命中**，
       明明取到了数据也报「未找到产物」⇒ **假缺口**（与「问句≠无源」同族）。
       后者实测病灶：**同一问句重跑会覆写同名文件**，多次调用后「变更集合」里有多个文件、
       mtime 可能**同秒并列** ⇒ `max(mtime)` **取错对象**（实跑中纳指那行因此报「结构不符」）。
       ⇒ 独立子目录让「本次产物」**唯一可辨**，从根上消除歧义。
    """
    d = out_dir or MX_OUT
    sub = d / f"_run_{uuid.uuid4().hex[:10]}"
    sub.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([PY, str(MX_DATA), query, str(sub)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=240, env=env)
    blob = (p.stdout or "") + (p.stderr or "")
    fresh = sorted(sub.glob("*_raw.json"), key=lambda q: q.stat().st_mtime)
    if not fresh:
        if "错误" in blob:
            raise RuntimeError(f"mx 报错且未产出：{blob.strip()[:150]}")
        raise RuntimeError("本次运行未产出 _raw.json（上游无数据或调用被拒）")
    payload = json.loads(fresh[-1].read_text(encoding="utf-8"))
    # ⛔ 路径逐层取，缺任一环即抛（不猜、不递归兜底）。
    # 🔴 2026-10-08 修正：真实嵌套是 **3 层 data**（`payload['data']['data']['searchDataResultDTO']`），
    #    我首版写了 **4 层** ⇒ 恒 KeyError ⇒ 两行 mx 全部误报「结构不符」。
    #    实测依据：诊断脚本逐层打印，顶层 keys＝['success','status','code','message','data','requestId']，
    #    `payload['data']` 内含 `code/message/status/requestId/data/stack`，
    #    `payload['data']['data']` 内含 `protocolType/id/refSeq/keyEntityList/searchDataResultDTO/...`。
    #    ⇒ 候选路径逐个试，**全失败则报错并列出已试路径**（fail-loud，⛔ 不静默返空）。
    _CANDIDATES = (
        ("data", "data", "searchDataResultDTO", "dataTableDTOList"),
        ("data", "searchDataResultDTO", "dataTableDTOList"),
        ("data", "data", "data", "searchDataResultDTO", "dataTableDTOList"),
    )
    dto, tried, cur = None, [], payload
    for path in _CANDIDATES:
        cur, ok = payload, True
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        tried.append(".".join(path) + ("" if ok else " ✗"))
        if ok and isinstance(cur, list):
            dto = cur
            break
    if dto is None:
        raise RuntimeError("mx payload 结构与预期不符；已试路径：" + " | ".join(tried))
    if not dto:
        raise RuntimeError("mx dataTableDTOList 为空")
    t = dto[0].get("table") or {}
    dates = t.get("headName")
    codes = [k for k in t if k != "headName"]
    if not dates or not codes:
        raise RuntimeError(f"mx table 缺 headName 或指标列（keys={list(t)[:4]}）")
    nm = (dto[0].get("nameMap") or {}).get(codes[0], "")
    vals = t[codes[0]]
    out = []
    for dt, v in zip(dates, vals):
        c = _num(v)
        if c is not None:
            out.append((str(dt), c))
    if not out:
        raise RuntimeError(f"mx 序列解析后为空（指标被识别成了「{nm}」而非价格，如成交量）")
    # 🔴 mx 返回**降序**（最新在前）⇒ 必须升序规范化，否则窗口取反（见 `_asc` docstring）
    return _asc(out)


def drawdown(series: list[tuple[str, float]], window: int = WINDOW) -> dict:
    """近 `window` 个交易日的收盘高点回撤。返回 dict（不足 window 条 ⇒ ok=False）。"""
    if len(series) < 2:
        return {"ok": False, "reason": f"序列仅 {len(series)} 条，无法计算"}
    w = series[-window:]
    hi_dt, hi = max(w, key=lambda x: x[1])
    last_dt, last = w[-1]
    dd = (hi - last) / hi * 100 if hi else 0.0
    return {"ok": True, "n": len(w), "window_from": w[0][0], "window_to": last_dt,
            "high": hi, "high_date": hi_dt, "last": last, "last_date": last_dt,
            "dd_pct": round(dd, 4), "truncated": len(series) < window}


def evaluate(line: dict, fetcher=None) -> dict:
    """对一条 §1.4 基准线出三态判定。`fetcher` 可注入（测试用）。"""
    f = fetcher or (lambda ln: tencent_series(ln["code"]) if ln["src"] == "tencent"
                    else mx_series(ln["query"]))
    out = dict(line)
    try:
        series = f(line)
    except Exception as exc:                                        # noqa: BLE001
        out.update(status="不可判定", reason=f"{type(exc).__name__}: {str(exc)[:150]}")
        return out
    dd = drawdown(series)
    if not dd.get("ok"):
        out.update(status="不可判定", reason=dd.get("reason"))
        return out
    thr = line["thr"]
    out.update(status="触发" if dd["dd_pct"] >= thr else "未触发",
               dd_pct=dd["dd_pct"], gap_pp=round(thr - dd["dd_pct"], 4),
               high=dd["high"], high_date=dd["high_date"], last=dd["last"],
               last_date=dd["last_date"], window_from=dd["window_from"],
               n_used=dd["n"], truncated=dd["truncated"],
               trigger_price=round(dd["high"] * (1 - thr / 100), 4))
    return out


def run(fetcher=None) -> dict:
    """对 §1.4 四条基准线出总判定。`fetcher` 可注入（测试用，⛔ 生产不传）。"""
    rows = [evaluate(ln, fetcher=fetcher) for ln in LINES]
    any_trig = any(r["status"] == "触发" for r in rows)
    any_unk = any(r["status"] == "不可判定" for r in rows)
    return {"rows": rows, "any_triggered": any_trig, "any_unknown": any_unk,
            "verdict": ("🔴 有补仓线触发 ⇒ 按 §1.4 次日 14:30 复核（每次 ≤¥1,000，间隔 ≥7 交易日）"
                        if any_trig else
                        ("🟡 有基准不可判定 ⇒ ⛔ 不得视为「未触发」" if any_unk
                         else "✅ 全部可判定且均未触发 ⇒ 现金层**不动**")),
            "rc": 2 if any_trig else (1 if any_unk else 0)}


def main() -> int:
    r = run()
    as_json = "--json" in sys.argv
    if as_json:
        print(json.dumps({k: v for k, v in r.items() if k != "rc"}, ensure_ascii=False, indent=1))
        return r["rc"]
    print("=" * 74)
    print("§1.4 现金层补仓触发监控 —— 近 20 个交易日收盘高点回撤")
    print("=" * 74)
    for x in r["rows"]:
        if x["status"] == "不可判定":
            print(f"  🟡 [{x['layer']}线] {x['label']}")
            print(f"      **不可判定** —— {x['reason']}")
            print(f"      ⛔ 不得视为「未触发」；阈值 {x['thr']}%")
        else:
            icon = "🔴" if x["status"] == "触发" else "✅"
            print(f"  {icon} [{x['layer']}线] {x['label']}")
            print(f"     {x['status']}｜近{x['n_used']}日({x['window_from']}~{x['last_date']}) "
                  f"高点 {x['high']:,.4f}({x['high_date']}) → 现值 {x['last']:,.4f}｜"
                  f"**回撤 {x['dd_pct']:.2f}%** vs 阈值 {x['thr']}%｜差 **{x['gap_pp']:.2f}pp**"
                  f"{'（序列不足20条!）' if x.get('truncated') else ''}")
            print(f"     触发价 = 高点 × (1 − {x['thr']}%) = **{x['trigger_price']:,.4f}**")
    print("-" * 74)
    print(f"  判定：{r['verdict']}")
    print(f"  退出码：{r['rc']}（2=有触发 / 1=有不可判定 / 0=全部未触发）")
    return r["rc"]


if __name__ == "__main__":
    sys.exit(main())
