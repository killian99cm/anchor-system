# Anchor 变更日志

> 每次改动必须记录：版本号 + 日期 + 变更内容 + 影响文件
> 更新时同步：portfolio_data.json / CLAUDE.md / 会话检查点.md / 本文件 / GitHub

---

## v3.4 — 2026-08-10

### 新增
- 🆕 **噪声审计体系 v1.0**：三类噪声 + 四项指标 + 噪声评分卡
  - 新增 `00-system/噪声审计框架.md`
  - 新增 `05-scripts/noise_audit.py`
  - 新增 `06-dashboard/noise/`（已.gitignore）
- 🆕 **每日双报告制度**：14:30 操作建议 + 21:30 收盘复盘（含噪声审计）
  - 快捷指令："出报告" / "复盘报告"
- 🆕 **每日 14:30 盘中建议推微信**（8/9部署，8/10验证通过）
  - 新增 `05-scripts/daily_advice.py` + `00-system/每日建议推送说明.md`
- 🆕 **AstrBot 知识库每日自动同步**：`05-scripts/anchor_to_astrbot.py --upload`（21:30）
- 🆕 **研究报告自动存档**：每次报告保存到 `04-reviews/research/`
- 📁 **04-reviews/ 重组**：daily/intraday/weekly/monthly/research/special

### 变更
- 🔧 **DDX 规则升级**（试验中）：原"连3日为正"→"连3日为正+当日超大单净流入>0"
  - 依据：8/10 噪声审计 DDX 准确率 0%（2次触发2次假信号）
- 🔧 **场内纳指ETF建仓废弃**：溢价13%结构性问题，场外定投继续
- 🔧 **AstrBot kb_names 修复**：cmd_config.json 加 kb_names:["anchor"]
- 🔧 **凭据安全**：AstrBot 密码改环境变量 ASTRBOT_PASSWORD

### 新增文件
`00-system/噪声审计框架.md` | `00-system/每日建议推送说明.md` | `05-scripts/daily_advice.py` | `05-scripts/noise_audit.py` | `05-scripts/anchor_to_astrbot.py` | `04-reviews/research/` | `06-dashboard/noise/` | `CHANGELOG.md`

### 修改文件
`portfolio_data.json` | `CLAUDE.md` | `00-system/数据更新协议.md` | `00-system/会话检查点.md` | `AstrBot data/cmd_config.json`

---

## v3.3 — 2026-08-06 ~ 08-07

### 新增
- 状态合同（state/ops_state/risk_state/drawdown_state/freeze_state等）
- 公开发布边界（gen_anchor_pro.py --private 失败 + smoke_test脱敏）
- smart_classify 智能分类
- DDX做半导体加仓过滤器 / 纳指ETF溢价率≤3%建仓 / -8%止损 / 时间止损30天 / 卖出冻结72h

### 文件
`05-scripts/data_processor.py` | `05-scripts/rebuild.py` | `05-scripts/gen_anchor_pro.py` | `05-scripts/smoke_test.py` | `05-scripts/test_calculations.py`

---

## v3.2 — 2026-07-21
风口试探仓 + 反弹日清仓规则

## v3.1 — 2026-07 中旬
四层金字塔 + 月操作≤4笔

## v3.0 — 2026-07 初
初始框架：压舱石/核心/卫星/现金

---

*规则：每次改动 → 更新本文件 → 更新版本号 → 同步 CLAUDE.md/会话检查点 → git commit → git push*
