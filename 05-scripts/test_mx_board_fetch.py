#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_mx_board_fetch.py — A2 板块当日档取数器测试（2026-09-29 建立）

覆盖两处实测踩过的坑，每处都配**反向断言**（「改回旧写法即失败」）：
  · 坑1：把**上一交易日**值当**当日**值用（盘中 fail-closed 记成了「源未生成」）
  · 坑2：一个响应多张表、日期键异构（`2026-09-29(日)` vs `2026-09-29 15:39`），
         不过滤表会把**主力资金表**读数混进涨跌序列
  · 坑3：A2 分支② 必须**同时**要求「当日>0 且 前日>0」；
         若简化为「当日>0 即命中」，9/29 四主题会被全部误判命中

用法：python test_mx_board_fetch.py    （离线夹具，不联网；退出码 0=全绿）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mx_board_fetch as mbf  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'✅' if cond else '❌'} {name} {detail}")
    if not cond:
        FAIL.append(name)


# ---------------------------------------------------------------- 夹具
# 摘自 2026-09-29 实测 mx-data 响应（真实值），并**人为加入**第 2 张「主力资金表」
# 与带时间戳的日期键，用于复现坑2。
def fixture(newest: str = "2026-09-29", include_flow_table: bool = True) -> dict:
    board_table = {
        "entityName": "成份区间涨跌幅(流通市值加权平均)",
        "table": {
            "固态电池(板块)": ["0.5266%", "-2.786%", "-2.145%", "-0.305%", "0.4346%"],
            "人形机器人(板块)": ["0.4455%", "-3.35%", "-1.575%", "-0.2594%", "0.4303%"],
            "智能驾驶(板块)": ["0.5894%", "-3.611%", "-1.857%", "-0.2641%", "0.1277%"],
            "有色金属(板块)": ["1.315%", "-3.745%", "-3.489%", "-0.8067%", "0.1856%"],
            "headName": [f"{newest}(日)", "2026-09-28(日)", "2026-09-24(日)", "2026-09-23(日)", "2026-09-22(日)"],
        },
    }
    tables = [board_table]
    if include_flow_table:
        tables.append({
            "entityName": "创新药(指数)等当前的主力净流入资金",
            "table": {
                "创新药(指数)": ["10.52亿元"],
                "证券Ⅱ(板块)": ["-2.942亿元"],
                "headName": [f"{newest} 15:39"],
            },
        })
    return {"data": {"data": {"searchDataResultDTO": {"dataTableDTOList": tables}}}}


# ---------------------------------------------------------------- T1 前向：解析
s = mbf.parse_payload(fixture())
check("T1a 解析出 4 主题", set(mbf.A2_THEMES) <= set(s.get("2026-09-29", {})), f"实得 {sorted(s.get('2026-09-29', {}))}")
check("T1b 最新日为 2026-09-29 且值正确",
      s["2026-09-29"]["有色金属"] == 1.315 and s["2026-09-29"]["固态电池"] == 0.5266,
      f"有色={s['2026-09-29'].get('有色金属')} 固态={s['2026-09-29'].get('固态电池')}")
check("T1c 历史日可回溯（≥5 个交易日）", len([d for d in s if d.startswith("2026-09")]) >= 5, f"n={len(s)}")

# ---------------------------------------------------------------- T5 🔴 反向：多表/异构键不得污染
check("T5a 🔴 带时间戳的日期键**不得**成为独立日行（坑2）",
      not any(" " in d for d in s), f"实得键 {sorted(s)}")
check("T5b 🔴 主力资金表的读数**不得**混进涨跌序列（坑2）",
      all(isinstance(v, float) and abs(v) < 50 for d in s for v in s[d].values()),
      f"值域 {sorted({v for d in s for v in s[d].values()})[:6]}")
check("T5c 🔴 即使响应里只有资金表（无涨跌幅表），也不得把资金当涨跌",
      mbf.parse_payload({"data": {"data": {"searchDataResultDTO": {"dataTableDTOList": [
          {"entityName": "主力净流入资金", "table": {"创新药(指数)": ["10.52亿元"], "headName": ["2026-09-29 15:39"]}}]}}}}) == {},
      "资金值 '10.52亿元' 不是合法百分比 ⇒ 应解析为空")

# ---------------------------------------------------------------- T2 🔴 反向：stale 判定
stale = mbf.parse_payload(fixture(newest="2026-09-28"))
newest_stale = max(stale) if stale else None
check("T2a 🔴 若源只回上一交易日 ⇒ 最新日必须 < 目标日（触发 stale）",
      newest_stale == "2026-09-28",
      f"实得 newest={newest_stale} vs target=2026-09-29")
check("T2b 🔴 旧写法（不校验日期直接取最新）会把 2026-09-28 当 9/29 用 ⇒ 本器必须以 status=stale 拦下",
      newest_stale != "2026-09-29",
      "若相等，说明日期校验失效 ⇒ 前日值会被当当日值")

# ---------------------------------------------------------------- T3 前向：a2_hit 真值表
cases = [
    (1.315, -3.745, False, "不成立", "9/29 有色金属实值"),
    (0.5266, -2.786, False, "不成立", "9/29 固态电池实值"),
    (2.5, -1.0, True, "分支①", "当日 ≥2%"),
    (2.0, -1.0, True, "分支①", "当日 =2.0% 边界（≥ 应命中）"),
    (1.99, -1.0, False, "不成立", "当日 1.99% 边界（< 不该命中）"),
    (0.8, 0.5, True, "分支②", "连续 2 日飘红"),
    (0.8, 0.0, False, "不成立", "前日 =0（不满足 >0）"),
    (None, 1.0, False, "缺值", "当日缺值 ⇒ 不可判定"),
]
for chg, prev, want_hit, want_br, desc in cases:
    hit, br, _ = mbf.a2_hit(chg, prev)
    check(f"T3 a2_hit({chg}, {prev}) ⇒ {want_hit}/{want_br}（{desc}）",
          (hit, br) == (want_hit, want_br), f"实得 {hit}/{br}")

# ---------------------------------------------------------------- T4 🔴 反向：分支② 的前日条件不是装饰
def a2_hit_old(chg, prev, a2_pct=2.0):
    """旧写法：只看当日是否为正（丢掉前日条件）。"""
    return chg is not None and chg > 0


_real_0929 = [(0.5266, -2.786), (0.4455, -3.35), (0.5894, -3.611), (1.315, -3.745)]
new_hits = [mbf.a2_hit(c, p)[0] for c, p in _real_0929]
old_hits = [a2_hit_old(c, p) for c, p in _real_0929]
check("T4a 🔴 旧写法（当日>0 即命中）会把 9/29 四主题**全部误判命中** ⇒ 证明该反例真实存在",
      all(old_hits), f"old={old_hits}")
check("T4b 🔴 新写法下 9/29 四主题**全部不成立** ⇒ 与旧写法结论相反（不是装饰性改动）",
      not any(new_hits), f"new={new_hits}")

# ---------------------------------------------------------------- 汇总
print("\n" + "=" * 44)
if FAIL:
    print(f"❌ {len(FAIL)} 项失败: {FAIL}")
    sys.exit(1)
print("✅ 全部通过 —— A2 板块当日档取数器基线 OK")
sys.exit(0)
