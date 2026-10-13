# -*- coding: utf-8 -*-
"""10/13 会话桥回写：claude_state.md 顶部追加 v4.5.54 条 + 心跳更新"""
import io
import json
import datetime

BR = r"C:/Users/lenovo/Desktop/AI-Collab/ai-bridge/claude_state.md"
HB = r"C:/Users/lenovo/Desktop/AI-Collab/.claude_heartbeat.json"

txt = io.open(BR, encoding="utf-8").read()
anchor = "> 📌 **维护者变更（2026-09-23 起）**：Claude 侧职责已由 **Qoder** 接任，本文件现由 **Qoder** 维护；回写义务、铁律与继承内容不变。下文历史条目中的「Claude」＝同一职责位。\n"
assert txt.count(anchor) == 1, "锚点唯一性失败"

entry = """
- 2026-10-13 14:1x | 🔴 **【v4.5.54 · 513120 破 MA20 的 E 级显式裁定（#74 · 不减仓）＋ 重大发现：push2his 板块日K 可回填缺口日 ＋ A2 读取侧接线】** —— ⚠️ **本文件自 9/25 后停更，现恢复**；v4.5.33~v4.5.53 详情以 `Anchor/CHANGELOG.md` 为准（**勿据本文件旧条目行事**）。

  **1. 给 WorkBuddy 的三条可引用结论**：
  - 🔴 **「板块缓存空洞无法回填」的旧前提已被推翻**：2026-10-13 实测 **push2his 板块日K 端点可用**（9/18 判「结构性无源」至少是**时点性**的）⇒ 已抢救 **10/8、10/12 各 14 个关键板块 ＋ 10/9 补 4 主题**（watchlist 缺口闭合），落 `06-dashboard/board_pct_history.json → days_push2_partial`。**口径校验**：kline 自带 chg 字段与 f3 不一致（黄金 10/9：6.04 vs 5.98）**已弃用**；用 close 序列自算 ⇒ 与已入库 f3 值在 10 个重叠板块**逐位吻合**。
  - ✅ **A2 读取侧已接线**（`gen_watchlist_status.py`）：当日链 live→days→**days_push2_partial**→days_mx；前日链 days→**days_push2_partial**→days_mx。**前两档同口径族不施容忍带**，仅 mx 档施 ±1.00pp。若你的脚本读板块缓存，注意**新增命名空间**（⛔ 非全量，找不到 ≠ 不存在）。
  - 🔴 **档案数据日仍为 2026-10-09**：10/12（周一）收盘数据**尚未入库**（等用户回传 App 真值，预计今晚 10/12＋10/13 一起入）；`--due` 的 #72 红警**今晚入库后方可回填**（399975 715.39→721.09 ≈ +0.80%，price_move）。

  **2. 本日裁定（decision_log #74）**：513120 10/12 收 1.304 破 MA20（1.3070）⇒ T+1（今日 14:30 前）出 E 级显式裁定：**不减仓**（三项 X 级未触发：−8% 距线 ≈2.03pp／时间止损跑输 ≈2.0pp<5pp；B3 母规则不满足；裁量减仓无规则授权——承 9/2 先例）⇒ **F6 本线收敛失效**，监视移交 −8% X 级 ＋ B4 状态机（拟登记 创新药C 入 `stop_loss_watch`，待今晚 App 真值）。

  **3. ⏰ 今日未闭合**：① 黄金定投 A2——**前日（10/12）−4.75% ⇒ 分支②逻辑上不可能**；仅分支①取决于今日收盘（盘中在 +2% 线摆动）⇒ 盘末复核（若 A2 拦下将登记 #75）。② **#73 T+3 = 10/14**。③ **待用户确认成文**：#C1-29（A2 及于定投→§2.1）／#C1-34（时间止损窗口→§2.2）／#C1-13／#C1-30／#C1-38／#C1-39 并批。

  **4. 本版验收**：`data_pipeline --integrity` 零 🔴；`version_check` 三处一致 **v4.5.54**；`test_rule_gates` **179/179**、🆕 `test_a2_partial_fallback` 8 项（3 组反向）全过；本地提交 `a97e47b`（⛔ 未推送，origin 落后 14 提交）。⛔ 零规则改写（手册 v3.22 未动）／零持仓变动／零生产变更。
"""
txt = txt.replace(anchor, anchor + entry, 1)
io.open(BR, "w", encoding="utf-8").write(txt)

now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
hb = json.load(io.open(HB, encoding="utf-8"))
hb.update({
    "last_stop": now,
    "claude_state_mtime": now,
    "claude_state_lag_days": 0,
    "bridge_writeback_needed": False,
    "session_id": "qoder-2026-10-13-v4554",
    "writeback_by": "Qoder（Claude 侧继任者，手动回写）",
    "note": "Qoder 手动回写（v4.5.54：513120 E级裁定 #74 + 板块日K抢救发现 + A2 读取侧接线）。本文件不是 claude_state.md，也不替代它。",
})
io.open(HB, "w", encoding="utf-8").write(json.dumps(hb, ensure_ascii=False, indent=2))

chk = io.open(BR, encoding="utf-8").read()
assert "v4.5.54 · 513120 破 MA20 的 E 级显式裁定" in chk
print("✅ 桥回写完成；claude_state.md 大小:", len(chk.encode("utf-8")))
print("✅ 心跳已更新:", now)
