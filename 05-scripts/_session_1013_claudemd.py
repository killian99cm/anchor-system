# -*- coding: utf-8 -*-
"""10/13 会话：CLAUDE.md 版本行 v4.5.53 → v4.5.54（定点替换，不动其他内容）"""
import io

p = r"C:/Users/lenovo/CLAUDE.md"
raw = open(p, "rb").read()
txt = raw.decode("utf-8")

needle = "| 版本 | **Anchor v4.5.53**（"
assert txt.count(needle) == 1, "唯一性断言失败"

summary = (
    "| 版本 | **Anchor v4.5.54**（2026-10-13 盘中 —— **513120 破 MA20 的 E 级显式裁定**"
    "（**#74** · T+1 到期日 14:30 前出具 · 裁定＝**不减仓**：三项 X 级均未触发＋B3 母规则不满足＋"
    "裁量减仓无规则授权；**F6 本线收敛失效**，监视移交 −8% X 级止损＋B4 状态机；"
    "代理估算持有率 ≈ −5.97%、距线 ≈2.03pp）＋ 🔴 **重大发现：push2his 板块日K 可回填缺口日**"
    "（9/18「结构性无源」定性被实测推翻；口径校验＝close 序列自算与 f3 在 10 个重叠板块**逐位吻合**，"
    "kline 自带 chg 字段与 f3 不一致**已弃用**）⇒ **抢救落盘 10/8＋14、10/12＋14、10/9＋4**"
    "（watchlist 四主题缺口闭合，「空洞无法回填」文案订正）＋ ✅ **A2 读取侧接线**"
    "（`days_push2_partial` 入当日链/前日链；同口径族**不施容忍带**，仅 mx 施 ±1.00pp；"
    "来源五态可辨；🆕 test_a2_partial_fallback **8 项含 3 组反向**全过；test_rule_gates **179/179**）"
    "＋ 其余闸门实查（月额度 0/2·0/2／C2 未冻结／§1.4 四条全未触发／#72 逾期待今晚回填／"
    "黄金定投分支②逻辑上不可能、分支①盘末复核）｜📌 **本行缺口如实登记**：`会话检查点.md` 自 v4.5.44 后"
    "（v4.5.45~53 九段）未再追加，本版**恢复使用**并补指针；⛔ 零规则改写（手册 v3.22 未动）、"
    "零持仓变动、零生产变更）｜**前版 v4.5.53**（"
)
new_txt = txt.replace(needle, summary, 1)
assert new_txt != txt and new_txt.count("**Anchor v4.5.54**（") == 1

# 备份后写回
open(p + ".bak-v4554", "wb").write(raw)
open(p, "wb").write(new_txt.encode("utf-8"))

# 回读校验
chk = open(p, "rb").read().decode("utf-8")
assert "| 版本 | **Anchor v4.5.54**（" in chk
assert chk.count("**前版 v4.5.53**（") == 1
assert chk.count("**Anchor v4.5.53**（") == 0
print("替换完成；回读含 v4.5.54:", "| 版本 | **Anchor v4.5.54**（" in chk)
print("『**前版 v4.5.53**（』出现次数:", chk.count("**前版 v4.5.53**（"))
print("原『**Anchor v4.5.53**（』残留次数（应为0）:", chk.count("**Anchor v4.5.53**（"))
