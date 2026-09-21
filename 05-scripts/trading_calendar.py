#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A 股交易日历（**离线** · 无网络 · 无第三方依赖 · 显式登记）

**口径**：交易日 = 周一至周五 **且** 不在 `CLOSED` 中。

**数据来源**：国务院办公厅《关于 2026 年部分节假日安排的通知》
（国办发明电〔2025〕7 号，2025-11-04）
<https://www.gov.cn/zhengce/zhengceku/202511/content_7047091.htm>

**本模块为何存在**（2026-09-21 立 · 登记表 §六 #C1-8）：
`decision_log.py` 的 T+3 原口径是**自然日 +3**，跨周末时**只覆盖 1 个交易日**
（周五记录 → 周一到期），导致「准确率」把 **1 日与 3 日两种评价期**的样本混在一起算
（64 条中 14 条为周五创建 ＝ 21.9%）。用户 2026-09-21 裁决：**T+3 改用交易日**。
⇒ **交易日历是本裁决的前置条件**（原 `fetch_public.prev_trading_day()` **依赖 K 线序列**，
不是纯日历，且**无法向前推算未来**）。

---

## 🔴 三条硬护栏（治的是「静默近似」）

1. **调休上班日不是交易日** —— 2026-09-20（周日）、2026-10-10（周六）机关**上班**，
   但 **A 股不开市**。⛔ **不得用「工作日近似」代替本表**。

2. **超出核定区间 ⇒ 抛 `CalendarUnavailable`（fail-loud）**，
   ⛔ **绝不静默回退「按星期几猜」** —— 那会把 **2026-09-25（周五 · 中秋）当成交易日**。
   这正是本模块立项要治的那个静默错误：**近似值不报错，只是答案是错的。**
   📌 与 **#138「拿到一个价 ≠ 拿到收盘价」**、**v4.5.3 六态语义**同族。

3. **纯离线查表** —— 不联网、不读 K 线、不依赖交易所接口。
   （对比：`fetch_public.prev_trading_day(kl, today)` 要**先有 K 线序列**才能反推，
    既不能算未来，也会因「K 线只回 1 条」而静默失效 —— 见 v4.5.8 §六。）

---

**维护**：新年度的官方放假通知发布后，**扩展 `CLOSED` 与 `VERIFIED_THROUGH`**
（⚠️ **两者必须同时改** —— 只改 `CLOSED` 不改 `VERIFIED_THROUGH` 会让护栏失效）。
"""

from datetime import date, timedelta

__all__ = [
    "CalendarUnavailable", "VERIFIED_FROM", "VERIFIED_THROUGH", "CLOSED",
    "is_trading_day", "next_trading_day", "prev_trading_day",
    "add_trading_days", "trading_days_between", "naive_weekday_approx",
]


class CalendarUnavailable(RuntimeError):
    """本日历**不覆盖**请求的日期 —— 调用方必须显式处置，⛔ 不得静默近似。"""


# ============ 核定区间（超出即 fail-loud） ============
VERIFIED_FROM = date(2026, 1, 1)
VERIFIED_THROUGH = date(2026, 12, 31)


# ============ 2026 年**落在工作日**的休市日 ============
# 说明：节假日区间内的**周末**天无需列入（已由「周一至周五」规则排除）。
#       下列每一行都对应官方通知里的一段区间，区间首/末日及其星期见 `_SELF_CHECK`。
CLOSED = frozenset({
    # 元旦 1/1(周四)–1/3(周六)          → 工作日：1/1、1/2
    "2026-01-01", "2026-01-02",
    # 春节 2/15(周日)–2/23(周一)        → 工作日：2/16–2/20、2/23
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-02-23",
    # 清明 4/4(周六)–4/6(周一)          → 工作日：4/6
    "2026-04-06",
    # 劳动节 5/1(周五)–5/5(周二)        → 工作日：5/1、5/4、5/5
    "2026-05-01", "2026-05-04", "2026-05-05",
    # 端午 6/19(周五)–6/21(周日)        → 工作日：6/19
    "2026-06-19",
    # 中秋 9/25(周五)–9/27(周日)        → 工作日：9/25
    "2026-09-25",
    # 国庆 10/1(周四)–10/7(周三)        → 工作日：10/1、10/2、10/5、10/6、10/7
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07",
})

# 官方通知里明示的**调休上班日**（机关上班、**A 股不开市**）
MAKEUP_WORKDAYS = ("2026-09-20", "2026-10-10")


# ============ 表与通知的一致性自检（防我手抄错星期） ============
# 通知原文的星期：元旦 1/1周四｜春节 2/15周日、2/23周一｜清明 4/4周六、4/6周一
#                劳动节 5/1周五、5/5周二｜端午 6/19周五｜中秋 9/25周五｜国庆 10/1周四、10/7周三
#                调休上班：9/20周日、10/10周六
_SELF_CHECK = (
    ("2026-01-01", 3), ("2026-02-15", 6), ("2026-02-23", 0),
    ("2026-04-04", 5), ("2026-04-06", 0),
    ("2026-05-01", 4), ("2026-05-05", 1),
    ("2026-06-19", 4), ("2026-09-25", 4),
    ("2026-10-01", 3), ("2026-10-07", 2),
    ("2026-09-20", 6), ("2026-10-10", 5),
)


def _run_self_check() -> None:
    """「通知里写的星期」与「本机实算的星期」必须一致 —— 不一致说明我抄错了区间。"""
    for iso, expect_wd in _SELF_CHECK:
        got = date.fromisoformat(iso).weekday()
        if got != expect_wd:
            raise AssertionError(
                f"交易日历自检失败：{iso} 通知写星期{expect_wd}，实算星期{got} —— "
                f"CLOSED 表区间抄错，须回读国务院通知原文订正"
            )


_run_self_check()


def _check_range(d: date) -> None:
    if not (VERIFIED_FROM <= d <= VERIFIED_THROUGH):
        raise CalendarUnavailable(
            f"交易日历不覆盖 {d.isoformat()}（核定区间 {VERIFIED_FROM} ~ {VERIFIED_THROUGH}）。"
            f"⛔ 不得按星期几近似 —— 请扩展 trading_calendar.CLOSED 与 VERIFIED_THROUGH。"
        )


def _as_date(d) -> date:
    if isinstance(d, date) and not hasattr(d, "hour"):
        return d
    # datetime 也走这里（datetime 是 date 的子类，但带 hour 属性）
    return date(d.year, d.month, d.day)


# ============ 主 API ============

def is_trading_day(d) -> bool:
    """d 是否为交易日。超出核定区间 ⇒ CalendarUnavailable（fail-loud）。"""
    d = _as_date(d)
    _check_range(d)
    if d.weekday() >= 5:          # 周末休市（含调休上班的周末）
        return False
    return d.isoformat() not in CLOSED


def next_trading_day(d) -> date:
    """**严格晚于** d 的第一个交易日。"""
    d = _as_date(d)
    cur = d
    while True:
        cur = cur + timedelta(days=1)
        if is_trading_day(cur):
            return cur


def prev_trading_day(d) -> date:
    """**严格早于** d 的最后一个交易日。"""
    d = _as_date(d)
    cur = d
    while True:
        cur = cur - timedelta(days=1)
        if is_trading_day(cur):
            return cur


def add_trading_days(d, n: int) -> date:
    """**d 之后**的第 n 个交易日（n=0 返回 d 本身；n<0 向前）。

    ⚠️ d **本身不必是交易日** —— 从 d 出发向指定方向数交易日。
       例：2026-08-29（周六）+ 3 → 08-31(一)、09-01(二)、09-02(三) ⇒ 09-02。
    """
    d = _as_date(d)
    if n == 0:
        return d
    step = 1 if n > 0 else -1
    remaining = abs(n)
    cur = d
    while remaining:
        cur = cur + timedelta(days=step)
        if is_trading_day(cur):
            remaining -= 1
    return cur


def trading_days_between(a, b) -> int:
    """区间 [a, b) 内的交易日数（a、b 均可非交易日）。"""
    a, b = _as_date(a), _as_date(b)
    if a >= b:
        return 0
    n, cur = 0, a
    while cur < b:
        if is_trading_day(cur):
            n += 1
        cur += timedelta(days=1)
    return n


# ============ 仅供测试的「反面样板」 ============

def naive_weekday_approx(d) -> bool:
    """🔴 **错误示范**：仅按「周一到周五」近似（本仓旧 `freshness_watchdog` 口径）。

    ⛔ **生产代码不得调用本函数** —— 它的存在只是为了在测试里做**反向断言**：
    证明「不用本日历」确实会得出错误答案（否则假日表可能只是装饰）。
    """
    d = _as_date(d)
    return d.weekday() < 5


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print(f"A 股交易日历 · 核定区间 {VERIFIED_FROM} ~ {VERIFIED_THROUGH}")
    print(f"休市日（工作日中的）{len(CLOSED)} 天｜调休上班日 {len(MAKEUP_WORKDAYS)} 天（**均不开市**）")
    print()
    print("2026-09-18（周五）之后的 8 个交易日：")
    cur = date(2026, 9, 18)
    for i in range(8):
        cur = next_trading_day(cur)
        print(f"  {i+1}. {cur.isoformat()}（{'一二三四五六日'[cur.weekday()]}）")
    print()
    print("关键抽查：")
    for iso in ("2026-09-18", "2026-09-21", "2026-09-25", "2026-09-28",
                "2026-09-20", "2026-10-10", "2026-10-01"):
        d = date.fromisoformat(iso)
        mark = "✅ 开市" if is_trading_day(d) else "🚫 休市"
        print(f"  {iso}（{'一二三四五六日'[d.weekday()]}）{mark}")
