# Anchor 变更日志

> 每次改动必须记录：版本号 + 日期 + 变更内容 + 影响文件
> 更新时同步：portfolio_data.json / CLAUDE.md / 会话检查点.md / 本文件 / GitHub

---

## v3.5.2 — 2026-08-15

### 新增
- 🆕 **止损确认自动化**：daily_advice.py 14:30 推送新增「止损确认」自动判定——实时板块涨跌 vs 文案阈值（默认 0.5%）→ 输出【执行止损一半】/【延期一天】/【人工确认】，消除人工判断延迟（三场景实测通过）
- 🆕 **噪声审计 v1.1**：noise_audit.py 新增盘中振幅比（--log-swing）、操作时机偏差（--log-timing）、规则命中台账（--log-rule）采集；每周评分卡改为真实数据评分（原为默认值）+ 台账汇总
- 🆕 **规则命中台账**：noise/rule_hits.json + 7 月已文档化命中回填基线（7 条：浮亏不加仓/恐慌豁免/反弹清仓/风口确认/DDX/冻结/止损缓冲）
- 🆕 **月度归因自动化补全**：gen_monthly_attribution.py 自动汇总规则台账（新增第七章）、操作计数改用 monthly_ops_summary（定投不计）、输出目录对齐 04-reviews/monthly/
- 🆕 **8/20 时间止损执行预案**（00-system/8月20日时间止损执行预案.md）：规则优先级 + 判定流程 + 错了怎么办 + 记录要求
- 🆕 **现金补仓条件量化提案** + **watchlist 左右侧逻辑统一** + **持仓收敛路径** + **示例指数基金通利定位**（规则手册 §1.4/§5.1）
- 🆕 **优化时间表**（00-system/优化时间表.md）：8/20 → 8/31 → 9月 → 10月验证项排期与续优化条件

### 修复
- 🔧 **数据口径统一**：total_hold_pnl_est 改为引擎按用户逐项数据求和（+1,565 → +1,441.23），_meta.pnl_total_note 记录口径，消除看板与 JSON 盈亏数字打架

### 修改文件
portfolio_data.json（total_hold_pnl_est + watchlist trigger）| 05-scripts/daily_advice.py | 05-scripts/noise_audit.py | 05-scripts/gen_monthly_attribution.py | 01-rules/投资规则手册_v3.3_正式版.md | 00-system/噪声审计框架.md（v1.1）| 00-system/每日建议推送说明.md | 00-system/8月20日时间止损执行预案.md（新增）| 00-system/优化时间表.md（新增）| 00-system/会话检查点.md | CHANGELOG.md

---

## v3.5.1 — 2026-08-15

### 修复
- 🔧 **回撤基准上移**：peak_assets ¥32,961 → **¥35,655**（8/10 本周最高点，用户确认）
  - 旧基准过时 8 天：-5% 线需先跌 11.9% 才触发，回撤预警系统失效
  - 新回撤线：-5% ¥33,872 / -10% ¥32,090 / -15% ¥30,307；8/14 总资产 ¥35,556 → 回撤 -0.3%，距 -5% 线缓冲 ¥1,684
  - 同步：规则手册 v3.3 §4.1、体系总览、07-memory、test_calculations（基准相关测试）、会话检查点

### 修改文件
portfolio_data.json（_meta.peak_assets/peak_note）| 01-rules/投资规则手册_v3.3_正式版.md | ANCHOR_体系总览.md | 07-memory/project-investment-framework.md | 07-memory/project-anchor-strategy-direction.md | 07-memory/user-investor-profile.md | 00-system/会话检查点.md | 05-scripts/test_calculations.py | CHANGELOG.md

---

## v3.5 — 2026-08-15

### 新增
- 🆕 **实时数据同步（watch_sync.py）**：监听桌面 portfolio_data.json 变化 → 自动全量同步（看板 HTML/快照/Excel/06-dashboard 副本/公开示例页），彻底杜绝数据滞后
  - 机制：sha256 变化检测 + 60s 稳定防抖 + 单实例锁 + watch_sync.log 日志 + .watch_sync_state.json 幂等状态
  - 启动：登录自启（Startup 启动项 Anchor实时同步.vbs）+ 每日 21:40 兜底计划任务「Anchor每日兜底同步」
  - 首次启动自动同步一次，保证开机即最新；同步失败下一轮自动重试
- 🆕 8/14 收盘数据完整同步：总资产 ¥35,556，持有盈亏 +¥1,565，回撤 +7.9%（安全区）

### 修复
- 🔧 **月操作计数口径**：monthly_ops_summary 排除定投/出入金（非手动操作，与交易备注「不计入月限额」及 gen_monthly_attribution 分类一致），8 月操作恢复 1/4 正确口径（原误计 2/4）
- 🔧 **每日快照目录**：sync_all.py 快照写入 04-reviews/daily/（对齐文件归类规则，原误写 04-reviews/ 根目录）

### 新增文件
05-scripts/watch_sync.py（本地私有工具，已 .gitignore）| 05-scripts/.watch_sync_state.json（已 .gitignore）

### 修改文件
portfolio_data.json（system_version v3.4→v3.5）| 05-scripts/data_processor.py（新增 is_manual_operation）| 05-scripts/test_calculations.py（35 项，含定投排除测试）| 05-scripts/sync_all.py | .gitignore | 00-system/数据更新协议.md | 00-system/会话检查点.md | CHANGELOG.md

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

