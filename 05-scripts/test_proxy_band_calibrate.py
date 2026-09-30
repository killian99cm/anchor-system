#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_proxy_band_calibrate.py — 代理误差带重定标器测试（2026-09-30）

承重反向断言（「改回旧写法即失败」）：
  · T3 🔴 若把「配对」改成**按顺序直接相减**（不用日期键对齐，旧式写法）
        ⇒ 遇缺日错位 ⇒ Δ 统计必须改变 ⇒ 证明日期对齐**不是装饰**。
  · T5 🔴 若删掉「符号相反」的统计 ⇒ 2/16 的关键发现消失
        （符号相反＝代理给出**反向**信号，最危险的误差形态）。
  · T7 🔴 若把「系统偏置 signed_mean」当成 0（或忘记计算）
        ⇒ 无法发现「proxy 系统性高估 ⇒ 止损判定偏乐观」这一**方向性**风险。

⛔ 只读夹具，零网络。
用法：python test_proxy_band_calibrate.py   （退出码 0=全绿）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import proxy_band_calibrate as pbc  # noqa: E402

FAIL: list[str] = []


def check(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name} {detail}")
    if not cond:
        FAIL.append(name)


# ---------------------------------------------------------------- T1 正向：pct_series
cl = {"2026-09-10": 100.0, "2026-09-11": 110.0, "2026-09-12": 99.0}
ps = pbc.pct_series(cl)
check("T1a 首个交易日无前收 ⇒ 不得出现（不得凭空造 0%）",
      "2026-09-10" not in ps, f"实得 {sorted(ps)}")
check("T1b +10% / −10% 计算正确",
      abs(ps["2026-09-11"] - 10.0) < 1e-9 and abs(ps["2026-09-12"] + 10.0) < 1e-9,
      f"{ps}")
check("T1c 🔴 乱序输入也必须按日期排序后计算（⛔ 不得按 dict 插入序）",
      abs(pbc.pct_series({"2026-09-12": 99.0, "2026-09-11": 110.0, "2026-09-10": 100.0})["2026-09-11"] - 10.0) < 1e-9,
      "乱序版结果与顺序版必须一致")

# ---------------------------------------------------------------- T2 正向：stats
s = pbc.stats([0.5, -0.5, 1.5, -1.5])
check("T2a stats 用 |Δ| 计算 max/mean", s["max"] == 1.5 and abs(s["mean"] - 1.0) < 1e-9, str(s))
check("T2b 符号分布可分辨（正 2 / 负 2）", s["sign_pos"] == 2 and s["sign_neg"] == 2, str(s))
check("T2c signed_mean 保留符号（此处 0）", abs(s["signed_mean"]) < 1e-9, str(s))

# ---------------------------------------------------------------- T3 🔴 反向：日期对齐承重
# ⚠️ 首版夹具是**空转断言**：prx 只缺中间一天时，「按序直减」与「按日期对齐」恰好同值
#    ⇒ 正反两版分不出来（＝「改回旧写法也不失败」）。已改为**两端错位**的夹具：
#    nav 有 d1..d3，prx 缺 d1 且多 d4 ⇒ 按序 zip 会把 d1 配到 d2、d3 配到 d4。
nav = {"d1": 1.0, "d2": 2.0, "d3": 3.0}
prx = {"d2": 9.0, "d3": 9.5, "d4": 1.0}
aligned = pbc.calibrate(nav, prx, "对齐")
naive = [a - b for a, b in zip([nav[k] for k in sorted(nav)], [prx[k] for k in sorted(prx)])]
check("T3a 对齐版只取交集 ⇒ n=2（d2/d3）", aligned["n"] == 2, f"n={aligned['n']}")
check("T3b 🔴 旧式（按序 zip）会得 **3** 个 Δ 且日期配错 ⇒ 与对齐版结果不同 ⇒ 日期键承重",
      len(naive) != aligned["n"]
      and sorted(round(x, 4) for x in naive) != sorted(r["delta_pp"] for r in aligned["rows"]),
      f"naive={sorted(round(x,4) for x in naive)} vs aligned={sorted(r['delta_pp'] for r in aligned['rows'])}")
check("T3c 🔴 对齐版 Δ 应恰为 [d2, d3] 两日之值 ⇒ 逐值可验",
      sorted(r["date"] for r in aligned["rows"]) == ["d2", "d3"],
      f"实得日期 {sorted(r['date'] for r in aligned['rows'])}")

# ---------------------------------------------------------------- T4 正向：真实样本（内置）
res = pbc.calibrate(pbc.NAV_159316, pbc.pct_series(pbc.tencent_closes("sh513120")), "ETF价")
check("T4a 🔴 真实样本配对 n=16（与 2026-09-30 实取一致）", res["n"] == 16, f"n={res['n']}")
check("T4b 🔴 |Δ|max > 1.0pp ⇒ **原 0.6pp 带已不成立**（这是本次重定标的根据）",
      res["stats"]["max"] > 1.0, f"max={res['stats']['max']}pp")

# ---------------------------------------------------------------- T5 🔴 反向：符号相反统计承重
opposite = [r for r in res["rows"]
            if (r["truth_nav_pct"] > 0) != (r["proxy_pct"] > 0)]
check("T5a 🔴 存在**符号相反**样本（实际跌而代理涨，或反之）",
      len(opposite) > 0, f"{len(opposite)} 天：{[r['date'] for r in opposite]}")
check("T5b 🔴 符号相反率已算出（12.5% = 2/16）⇒ 若删掉该统计，本发现即消失",
      len(opposite) / res["n"] >= 0.12, f"{len(opposite)/res['n']*100:.1f}%")

# ---------------------------------------------------------------- T6 正向：p95
check("T6a p95 ≤ max 且 ≥ median（单调性）",
      res["stats"]["median"] <= res["stats"]["p95"] <= res["stats"]["max"],
      f"med={res['stats']['median']} p95={res['stats']['p95']} max={res['stats']['max']}")

# ---------------------------------------------------------------- T7 🔴 反向：系统偏置承重
check("T7a 🔴 signed_mean ≠ 0 ⇒ 代理**有系统性方向偏置**（不得只看 |Δ|）",
      abs(res["stats"]["signed_mean"]) > 0.1, f"signed_mean={res['stats']['signed_mean']}pp")
check("T7b 🔴 偏置为**负** ⇒ proxy 系统性**高估** ⇒ 对止损判定是**危险方向**（低估风险）",
      res["stats"]["signed_mean"] < 0, f"{res['stats']['signed_mean']}pp")

print("\n" + "=" * 46)
if FAIL:
    print(f"❌ {len(FAIL)} 项失败: {FAIL}")
    sys.exit(1)
print("✅ 全部通过 —— 代理误差带重定标器基线 OK")
sys.exit(0)
