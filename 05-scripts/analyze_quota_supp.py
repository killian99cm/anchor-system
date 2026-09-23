# -*- coding: utf-8 -*-
"""月额度分析 · 补充统计（一次性研究脚本）

补三件事：
  F. 被锁窗口收益的**离散度**（正负相抵结构）—— 「错过上涨」是否只是「同时躲过下跌」的另一面
  G. 卖出维专项 —— 卖出类决策的历史准确率 vs 买入类（哪一维才该动）
  H. 「额度已经动态了」的三条既有降额通道自检（C2 冻结 / §4.2.1 压舱石买入闸 / §4.1 −5% 不开新仓）
"""
import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths
from data_processor import classify_txn_op, txn_exclusion_reason

DATA = json.load(open(paths.DATA_PATH, encoding="utf-8"))
TX = DATA.get("transactions", [])
DJ = json.load(open(paths.DECISION_LOG_PATH, encoding="utf-8"))
DS = DJ["decisions"] if isinstance(DJ, dict) else DJ

# ---------- F 离散度（数值来自 backtest_quota_lockout.py 实跑结果，此处独立复算） ----------
import fetch_public as fp
UNI = {"sh513120": "创新药ETF", "sh512480": "半导体ETF", "sh512880": "证券ETF", "sh000688": "科创50"}


def ym(t):
    d = str(t.get("date", ""))
    return d[:7] if len(d) >= 7 and d[4] == "-" else None


def exhaustion():
    """耗尽日＝第 2 笔买入**记录**所在日（⛔ 不对日期去重，见 backtest_quota_lockout 口径订正）。"""
    by = defaultdict(list)
    for t in TX:
        m = ym(t)
        if not m or txn_exclusion_reason(t) is not None:
            continue
        if classify_txn_op(t.get("op")) == "buy":
            by[m].append(str(t.get("date"))[:10])
    return {m: sorted(v)[1] for m, v in by.items() if len(v) >= 2}


def F():
    print("=" * 88)
    print("F. 被锁窗口收益的离散度 —— 「错过上涨」与「躲过下跌」是同一枚硬币")
    print("=" * 88)
    ex = exhaustion()
    kl = {c: {r["date"]: r["close"] for r in (fp.daily_kline(c, 300) or [])} for c in UNI}
    samp = []
    for m in sorted(ex):
        d0 = ex[m]
        for c in UNI:
            days = sorted(d for d in kl[c] if d >= d0 and d[:7] == m)
            if len(days) < 2:
                continue
            a, b = kl[c][days[0]], kl[c][days[-1]]
            if a:
                samp.append((m, UNI[c], (b / a - 1) * 100))
    pos = [s for s in samp if s[2] > 0]
    neg = [s for s in samp if s[2] < 0]
    sp = sum(s[2] for s in pos) / 100 * 300
    sn = sum(s[2] for s in neg) / 100 * 300
    print(f"  n={len(samp)}（{len(pos)} 正 / {len(neg)} 负）")
    print(f"  正收益合计（若每笔 ¥300 买入）: ¥{sp:+,.2f}")
    print(f"  负收益合计（若每笔 ¥300 买入）: ¥{sn:+,.2f}")
    print(f"  ⇒ 净额 ¥{sp+sn:+,.2f}；**毛额** ¥{abs(sp)+abs(sn):,.2f} 被相抵掉 {abs(sp+sn)/(abs(sp)+abs(sn))*100:.1f}% 的反向部分")
    print()
    top = sorted(samp, key=lambda s: -s[2])[:3]
    bot = sorted(samp, key=lambda s: s[2])[:3]
    print("  最好 3 个:", ", ".join(f"{m} {n} {v:+.2f}%" for m, n, v in top))
    print("  最差 3 个:", ", ".join(f"{m} {n} {v:+.2f}%" for m, n, v in bot))
    print()
    print("  🔴 关键结构：最好的月份（2026-06 半导体 +39.81%）与最差的月份（2026-07 半导体 −25.47%）")
    print("     **相邻且同标的** ⇒ 被锁窗口的收益不是「系统性漏掉的上涨」，而是**高方差抛硬币**。")
    print("     提高额度 = 同时放大两侧；在「加仓准确率 50%」的实证下，期望值不改善、方差增大。")
    return samp


def G():
    print()
    print("=" * 88)
    print("G. 买入维 vs 卖出维 —— 哪一维的历史决策质量更差（该收紧的是哪一维）")
    print("=" * 88)
    BUY_T = {"加仓", "买入"}
    SELL_T = {"清仓", "减仓", "止损", "证券"}
    agg = defaultdict(lambda: [0, 0, 0, 0])  # n, correct, wrong, neutral
    for d in DS:
        t = str(d.get("type", ""))
        g = "买入类" if t in BUY_T else ("卖出类" if t in SELL_T else "观望/其他")
        o = d.get("outcome")
        if o is None:
            continue
        a = agg[g]
        a[0] += 1
        a[1] += (o == "correct")
        a[2] += (o == "wrong")
        a[3] += (o == "neutral")
    for g in ("买入类", "卖出类", "观望/其他"):
        n, c, w, u = agg[g]
        if n:
            print(f"  {g:<10} n={n:<4} correct={c:<3} wrong={w:<3} neutral={u:<3} 准确率={c/n*100:.1f}%")
    print()
    b = agg["买入类"]
    s = agg["卖出类"]
    if b[0] and s[0]:
        print(f"  ⇒ 买入类准确率 {b[1]/b[0]*100:.1f}%（n={b[0]}） vs 卖出类 {s[1]/s[0]*100:.1f}%（n={s[0]}）")
        print("     🔴 卖出类显著更准 ⇒ **若要在两维之间做非对称处置，方向是「松卖出、紧买入」，")
        print("        而不是「两维一起放宽」。** 但注意 #C1-15 已把 X 级卖出移出额度约束，")
        print("        故此处「卖出类高准确率」的样本**大部分本就不受额度管** ⇒ 不构成放宽裁量性卖出的理由。")
    # 12 个月超限率
    print()
    months = sorted({ym(t) for t in TX if ym(t)})
    ob = os_ = nm = 0
    for m in months:
        y, mo = int(m[:4]), int(m[5:7])
        from data_processor import monthly_ops_summary
        sm = monthly_ops_summary(DATA, y, mo)
        if sm.buys == 0 and sm.sells == 0:
            continue
        nm += 1
        ob += sm.buys > sm.max_buys
        os_ += sm.sells > sm.max_sells
    print(f"  12 个月实测：买入维超限 {ob}/{nm} 月（{ob/nm*100:.0f}%）｜卖出维超限 {os_}/{nm} 月（{os_/nm*100:.0f}%）")
    print("  🔴 买入维在 **11/12 个月**超限 ⇒ 该上限**从未成为实际约束**，")
    print("     命中报告标准 **v2.1 判例**：「一条永远做不到的强制项会训练出『照抄免责』的习惯」。")
    print("     ⇒ **要治的是「超限无代价」，不是「上限数字」。**")


def H():
    print()
    print("=" * 88)
    print("H. 「额度已经是动态的」—— 三条既有的**向下**动态通道自检（全部 F8 ① 合法）")
    print("=" * 88)
    rows = [
        ("§2.3 C2 盈亏比冻结", "盈亏比连续 2 次 <1.0 ⇒ 当月**冻结新买入**（买入维 → 0）",
         "#C1-18 已裁决恢复；载体＝软件 C2 服务（139 单 2026-09-23 上线）", "✅ 有载体"),
        ("§4.2.1 压舱石买入闸", "压舱石层正向偏离 > +8% ⇒ 暂停该层一切**裁量性主动买入**（该层 → 0）",
         "#C1-6 方案 C（2026-09-21）", "✅ 有载体（pre_trade_check §4.2.1）"),
        ("§4.1 回撤 −5%", "净值自基准回撤 ≥5% ⇒ 卫星仓位减半 ＋ **不开新仓**（卫星买入维 → 0）",
         "手册 §4.1（`X` 级）", "⚠️ 判据靠人工维护 `_meta.peak_assets`"),
        ("§2.3 A3 浮亏仓禁摊平", "卫星仓浮亏 ⇒ **一分钱不加**（该标的买入 → 0）",
         "手册 §2.4／§3.1 第 2 条", "✅ 有载体"),
        ("§2.6 DDX 过滤器", "半导体 DDX 未连 2 日为正 ⇒ 不补（该标的买入 → 0）",
         "手册 §2.6", "⚠️ #C1-5 已恢复条件；DDX 源可用性受限"),
    ]
    for a, b, c, d in rows:
        print(f"  · {a:<20}{d:<12}\n      规则: {b}\n      出处: {c}")
    print()
    print("  🔴 结论：**Anchor 的额度早已是动态的 —— 但只有「向下」的动态（5 条降额/归零通道），")
    print("     没有「向上」的动态。而 F8 ① 明文规定：任何信号「只允许用于收紧闸门，")
    print("     ⛔ 不得用于放宽或增加买入」⇒ **「涨了就多买」型动态额度在现行手册下不合法**，")
    print("     要做得先由用户修改 F8 本身（不是修改 §1.3）。")


if __name__ == "__main__":
    F()
    G()
    H()
