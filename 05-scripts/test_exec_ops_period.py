#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_exec_ops_period.py — 额度闸门「执行周期校正」防回归（v4.5.47 · 2026-10-07）
================================================================================
病灶：`current_ops_period(data)` 兜底读 **`update_date`＝数据日期**。这对**月度归因**正确，
但对**交易前门禁**错误 —— 门禁要回答「这一笔消耗**哪个月**的额度」，答案取决于**执行日**。

真实触发（2026-10-07 23:2x，为 10/8 国庆复市做预案）：档案 `update_date=2026-09-30`
⇒ 门禁报「9月 买入 6/2 ⇒ 买入维已满」并拦下**全部**买入；而该笔在 10/8 执行、
消耗的是 **10 月**额度（0/2）⇒ **假拦截**。长假后首个交易日早盘**必然**踩中
（档案要到当日收盘后才更新）⇒ 与 §4.5 节前闸门「读提交时刻、⛔ 不读数据日期」同源。

用法: python test_exec_ops_period.py
"""
import sys
import os
from datetime import date

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pre_trade_check as ptc  # noqa: E402

FAIL = []


def check(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name} {detail}")
    if not cond:
        FAIL.append(name)


def main() -> int:
    f = ptc.exec_ops_period

    # ---- T1 交易日提交：执行周期＝提交日所属月 ⇒ 校正 ----
    y, m, note = f(date(2026, 10, 8), 2026, 9)
    check("T1 10/8（交易日）· 数据周期 9 月 ⇒ 校正为 10 月", (y, m) == (2026, 10), f"实得 {(y, m)}")
    check("T1b 校正须留痕（note 非空且含两个周期）",
          bool(note) and "2026-09" in note and "2026-10" in note, str(note)[:70])

    # ---- T2 非交易日提交：执行日顺延到次一交易日（场外 15:00 后同口径）----
    y2, m2, _ = f(date(2026, 10, 7), 2026, 9)      # 10/7 周三＝国庆休市
    check("T2 10/7（休市）⇒ 执行日 10/8 ⇒ 校正为 10 月", (y2, m2) == (2026, 10), f"实得 {(y2, m2)}")
    # 跨月边界：9/30 是交易日 ⇒ 不顺延
    y2b, m2b, n2b = f(date(2026, 9, 30), 2026, 9)
    check("T2b 9/30（交易日·同月）⇒ 不校正、note 为 None",
          (y2b, m2b) == (2026, 9) and n2b is None, f"实得 {(y2b, m2b)} note={n2b}")

    # ---- T3 同周期不校正（不得无谓改写）----
    y3, m3, n3 = f(date(2026, 10, 15), 2026, 10)
    check("T3 执行周期＝数据周期 ⇒ note 严格为 None（⛔ 不得打印噪声）",
          (y3, m3, n3) == (2026, 10, None), f"实得 {(y3, m3, n3)}")

    # ---- T4 反向：执行周期**早于**数据周期 ⇒ 不校正 + 告警（时钟回拨/回测不静默改写）----
    y4, m4, n4 = f(date(2026, 9, 15), 2026, 10)
    check("T4 执行周期早于数据周期 ⇒ **保留数据周期**（不校正）", (y4, m4) == (2026, 10), f"实得 {(y4, m4)}")
    check("T4b 且必须打印告警（不得静默）",
          bool(n4) and "早于" in n4 and "不校正" in n4, str(n4)[:70])

    # ---- T5 🔴 反向断言：改回旧写法（直接用 current_ops_period 的结果）即失败 ----
    # 证明本次校正**真的改变了额度闸门的结论**，而不是只多打一行字。
    # 旧写法＝不校正 ⇒ 读 9 月（买入 2/2 已满 ⇒ ⛔ 拦截）；
    # 新写法＝校正到 10 月（0/2 ⇒ ✅ 放行）。两者必须**结论相反**。
    #
    # 🔴 **2026-10-08 修正（我自己埋的日历炸弹 · 同族第 5 例）**：本组此前**读真实档案**并断言
    #    「档案数据周期确为 2026-09 且买入维已满」。这在 2026-10-07 晚成立，但 10/8 真值入库后
    #    档案 update_date 变成 2026-10-08、10 月买入 0/2 ⇒ 前置断言与主断言**双双转红**。
    #    ⇒ 教训与我昨晚刚写进项目记忆的第 5 条**完全同型**：「夹具期间必须显式钉住，⛔ 不要追
    #       『与被测代码同源』」—— 我写 T5 时恰恰又去追了真实档案的状态。
    #    ⇒ 改为**自带合成夹具**（不读真实档案、不读时钟），断言与运行日期彻底解耦。
    import data_processor as dp

    def _fx(n_buys, ym):
        """合成一份最小档案：把 n_buys 笔「买入」打在 ym（'YYYY-MM'）月内。"""
        return {
            "update_date": f"{ym}-28",
            "update_time": f"{ym}-28 15:05",
            "total_assets": 1000.0,
            "holdings_summary": [],
            "_meta": {},                      # ⛔ 故意**不**钉 ops_year/ops_month
            "transactions": [
                {"date": f"{ym}-0{i+1}", "op": "买入", "name": "创新药C", "amount": 100.0}
                for i in range(n_buys)
            ],
        }

    fx = _fx(2, "2026-09")                   # 数据周期＝9 月，且买入维**已满**（2/2）
    dy, dm, _ = dp.current_ops_period(fx)
    check("T5 前置：合成夹具的数据周期＝2026-09 且买入维已满（否则本用例失去意义）",
          (dy, dm) == (2026, 9) and dp.monthly_ops_summary(fx, 2026, 9).buys >= 2,
          f"实得 {(dy, dm)} buys={dp.monthly_ops_summary(fx, 2026, 9).buys}")
    s_old = dp.monthly_ops_summary(fx, year=dy, month=dm)          # 旧写法：数据周期
    ny, nm, _ = f(date(2026, 10, 8), dy, dm, fx)                   # 新写法：执行周期
    s_new = dp.monthly_ops_summary(fx, year=ny, month=nm)
    check("T5 🔴 旧写法判「买入维已满」⛔ vs 新写法判「有余量」✅ —— 结论必须相反",
          s_old.buys >= 2 and s_new.buys < 2,
          f"9月 buys={s_old.buys} / 10月 buys={s_new.buys}")
    check("T5b 校正不得改动 `current_ops_period` 本身（月度归因口径不受污染）",
          dp.current_ops_period(fx) == (dy, dm, f"{dm}月"),
          f"实得 {dp.current_ops_period(fx)}")
    # 🔴 T5c：夹具必须真的**没有**钉住期间（否则 T5 测的是「钉住」而不是「校正」）
    check("T5c 反向守卫：夹具未钉 ops_year/ops_month（否则 T5 退化为 T8 的重复）",
          not fx["_meta"].get("ops_year") and ny == 2026 and nm == 10,
          f"_meta={fx['_meta']} 校正结果={(ny, nm)}")

    # ---- T6 fail-closed：日历不可导入 ⇒ 退回数据周期 + 显式留痕 ----
    saved = sys.modules.get("trading_calendar", "__absent__")
    try:
        sys.modules["trading_calendar"] = None      # 令 `import trading_calendar` 抛 ImportError
        y6, m6, n6 = f(date(2026, 10, 8), 2026, 9)
        check("T6 日历不可用 ⇒ **不校正**（fail-closed 退回数据周期）", (y6, m6) == (2026, 9), f"实得 {(y6, m6)}")
        check("T6b 且必须写明 fail-closed 与「未按星期几心算」",
              bool(n6) and "fail-closed" in n6 and "心算" in n6, str(n6)[:80])
    finally:
        if saved == "__absent__":
            sys.modules.pop("trading_calendar", None)
        else:
            sys.modules["trading_calendar"] = saved

    # ---- T7 校正后日历仍可用（T6 的 monkeypatch 未泄漏）----
    y7, m7, _ = f(date(2026, 10, 8), 2026, 9)
    check("T7 monkeypatch 已还原：校正功能恢复", (y7, m7) == (2026, 10), f"实得 {(y7, m7)}")

    # ---- T8 🔴 `_meta.ops_year/ops_month` 显式覆盖优先级最高，本函数不得越过 ----
    pinned = {"_meta": {"ops_year": 2026, "ops_month": 9}}
    y8, m8, n8 = f(date(2026, 10, 8), 2026, 9, pinned)
    check("T8 显式钉住 9 月 ⇒ **不校正**（显式优先于派生）", (y8, m8) == (2026, 9), f"实得 {(y8, m8)}")
    check("T8b 且必须打印「显式覆盖」留痕（不得静默不校正）",
          bool(n8) and "显式覆盖" in n8 and "不做执行日校正" in n8, str(n8)[:70])
    # 🔴 反向断言：同一 asof、同一数据周期，**不钉**就必须校正 ⇒ 证明 T8 的「不校正」
    #    是覆盖生效的结果，而不是函数整体失效（否则 T8 会恒真、什么都测不到）。
    y8c, m8c, _ = f(date(2026, 10, 8), 2026, 9, None)
    check("T8c 🔴 反向：不钉住则**必须**校正为 10 月（否则 T8 是空断言）",
          (y8c, m8c) == (2026, 10), f"实得 {(y8c, m8c)}")
    # 空 _meta / 只有其中一个键 ⇒ 视为未钉住（⛔ 不得把半配置当显式声明）
    y8d, m8d, _ = f(date(2026, 10, 8), 2026, 9, {"_meta": {"ops_year": 2026}})
    check("T8d 半配置（只有 ops_year）⇒ 视为未钉住，照常校正", (y8d, m8d) == (2026, 10), f"实得 {(y8d, m8d)}")

    print("\n" + "=" * 46)
    if FAIL:
        print(f"❌ {len(FAIL)} 项失败: {FAIL}")
        return 1
    print("✅ 全部通过 —— 额度闸门执行周期校正 OK（长假后首日不再假拦截）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
