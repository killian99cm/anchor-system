# Anchor 变更日志

> 每次改动必须记录：版本号 + 日期 + 变更内容 + 影响文件
> 更新时同步：portfolio_data.json / CLAUDE.md / 会话检查点.md / 本文件 / GitHub

---

## v3.5.5 — 2026-08-19

### 修复
- 🔴 **回撤安全垫口径修正（净值口径）**：8/19 深度复盘发现看板「距 -5% 线安全垫 ¥10,145」被**贷款残留虚增 3.3 倍**
  - **根因**：`compute_drawdown_state` 用 `totals['total']`（账户口径 44,017，余额宝含贷款残留 7,023.77）对比 peak_assets 35,655 → dd_pct 假新高 +23.5%、安全垫虚高
  - **修复**：JSON `_meta.liabilities` 记录贷款结构（total 23,000 / repaid_from_cash 15,976.23 / in_cash 7,023.77）；引擎新增 `liabilities_in_cash()`，回撤/安全垫改用**净值口径** `net_assets = total_assets - liabilities.in_cash`
  - **修复后**：净值 ¥36,993 → dd_pct **+3.75%（round +3.8%）**、距 -5% 线（¥33,872）安全垫 **¥3,121**（原虚高 ¥10,145）。一次像样回调即触发预警，口径与真实风险一致
  - `drawdown_state` 输出新增 `total_assets` / `net_assets` / `liabilities_in_cash` 字段；四层占比保持账户口径，现金层贷款残留由副标题标注

### 变更
- 🔧 **看板显示净值口径**：Total assets KPI 副标题加「自有 ¥36,993」；Drawdown KPI 副标题加「净值 ¥36,993」；回撤区新增「净值口径」行（自有净值+扣贷款）；安全垫规则文案改为「自有净值距 -5% 线…已扣贷款残留 ¥7,024」
- 🔧 **drawdown_alert.py**：文本输出加「自有净值」行，`--json` 输出新增 `net_assets` / `liabilities_in_cash` 字段
- 🧪 **测试**：test_calculations 新增 5 项净值口径用例（liabilities 解析、net_assets/dd_pct/cushion 净值计算、与 drawdown_status 等价、无贷款兼容），`test_drawdown_check` 改用引擎净值口径；46 项全通过

### 修改文件
portfolio_data.json（system_version v3.5.5 + _meta.liabilities）| 05-scripts/data_processor.py（liabilities_in_cash + compute_drawdown_state 净值口径 + 规则文案）| 05-scripts/rebuild.py（KPI/回撤区净值标注）| 05-scripts/drawdown_alert.py（净值输出）| 05-scripts/test_calculations.py（净值口径用例）| CHANGELOG.md

### 数据（8/19，决策记录，不 bump 版本）
- 📝 **贷款资金配置方案**：贷款 ¥28,619（余额宝 7,023.77 + 银行卡 21,595）用户确认**债券垫 20%**方案——立即建仓 ¥6,000（创新药 +3,000 + 纳指 +3,000）＋ 债券垫 ¥5,700（中银稳健增利）＋ 右侧子弹 ¥12,300（时机 A 站稳3,900→6,000 / B DDX连正→3,800 / C 跌至3,741→2,500）＋ 机动 ¥4,619；目标年化 10-13%、胜率 70%+、波动 5-8%
- 📄 文档：`04-reviews/special/2026-08-19-贷款配置方案.md`（新增）｜ pending_actions 贷款项已更新为执行中（银行卡 21,595 需先转入余额宝）

---

## v3.5.4 — 2026-08-18

### 新增
- 🆕 **数据更新后自动生成深度复盘（新制度）**：用户确认流程——每次持仓数据更新入库后，Claude 自动按标准模板生成深度复盘报告（①逐只持仓涨跌 + 板块技术面/基本面 + 明日/一周展望 ②操作建议 + 上次操作效果 ③新机会/新板块），无需用户再次下达指令
- 📄 首份按新制度自动生成：`04-reviews/daily/2026-08-18-深度复盘.md`（总资产 ¥37,251.98，半导体 DDX 转负 -0.181 计数归零、固态电池飘红中断、创新药浮亏缩至 -0.65%）

### 修复
- 🔧 **day_pct 口径修正**：portfolio_data.json 中持仓 day_pct 曾误填持有收益率，已修正为当日涨跌幅（引擎 gold_day_pct > 0.02 用于黄金过热判断，口径必须一致）

### 数据
- 📊 8/18 用户数据入库：总资产 ¥37,251.98（fund ¥31,571.98 + stock ¥5,680）、持有盈亏 +¥1,636.92；余额宝 +1,475.19 为银行卡转入（用户确认）；通利市值修正（8/17 记录含定投 135 误差 → 真实市值 2,632.41）

### 数据（8/19）
- 📊 **贷款 ¥23,000 到账余额宝**（用户确认，无息贷款提前到账）：yuebao 6,153.05 → 29,153.05、fund_account 31,571.98 → 54,571.98、**total_assets ¥37,252 → ¥60,252**、update_time 2026-08-19 14:39
  - transactions 新增 8/19 余额宝转入 23,000（无息贷款）；pending_actions 贷款项更新为「已到账待配置 → 8/31 归因后再定，暂不动用」；_meta.loan_status 记录纪律
  - ⚠️ 现金层 16.5% → **48.4% 严重超配**，按纪律「杠杆不给未验证的系统」，先看 8/31 归因再配置
- 🚨 **半导体 -7.54% 暴跌二次触发 -8% 止损**（8/19 盘中报告）：估算浮亏 -11.56%，上证 3,886 失守 3900、科创50 -7.24%；8/20 14:30 缓冲确认（跌>0.5% 执行止损一半）+ 创新药满 30 天评估双事件
- 📄 盘中研究报告：`04-reviews/daily/2026-08-19-盘中研究报告.md`（新增）
- 📊 **8/19 收盘数据入库**（用户晚 21:00 前后提供）：total_assets **¥44,016.90**、fund ¥38,308.90 + stock ¥5,708 + 余额宝 ¥13,176.82
  - **半导体坐实 -11.42%**（1023.26，-81.62 当日）二次触发止损；创新药浮亏扩至 -35.73（-1.42%）；黄金 -4.96%；证券 -4.56%；纳指A/C 浮盈收窄至 +10.77%/+13.19%；515180 1.427（+0.33%）唯一飘红
  - 贷款转出 15,976.23 至银行卡（用户确认），余额宝剩贷款部分约 7,023.77；现金层 48.4% → **29.9%**（仍超配目标 15%）
  - 四层：压舱石 43.0% / 核心 14.1% / 卫星 13.0% / 现金 29.9%；PnL +1,353（引擎重算）；1 RED（半导体止损）+ 2 AMBER
  - 行情确认（妙想 21:36）：上证 3,894.42（-2.40%）失守 3900、科创50 1,667.52（-6.89%）、半导体板块 -7.61%（DDX -0.457、超大单 -289.9亿）、恒生医疗 -0.63% 抗跌、溢价率 7.83%
- 📄 **深度复盘报告（v3.5.4 自动制度）**：`04-reviews/daily/2026-08-19-深度复盘.md`（新增）
- 🔧 **数据一致性修正**：total_hold_pnl_est 1636.92 → **1353.19**（8/18 残留旧值，按 _meta.pnl_total_note 口径重算 Σ活跃持仓）；market / daily_summaries / chart_data 补全 8/19 记录

### 修复（8/19）
- 🔧 **14:30 推送连续失败（WinError 10061）**：根因= Docker Desktop 未启动 → AstrBot 容器退出（8/12 起）→ 6185 端口无服务 → 每日推送登录被拒。已启动 Docker + `docker start astrbot`，API 恢复（HTTP 200）
- 🔧 **半导体止损信号自相矛盾**：portfolio_data.json 的 pending_action 残留 8/17「止损解除」旧文案（8/19 二次触发漏更新）→ 已更新为「8/19 二次触发，8/20 14:30 缓冲确认」；daily_advice.py 止损信号改为只拼 action（不拼 name+action 全文），防止过期状态文案污染决策信号
- 📌 确认：DDX 补仓规则为「连 2 日为正」（v3.3 手册 2.6 节），代码正确，无需改动

### 修改文件
portfolio_data.json（8/19 贷款 + 半导体止损状态 + system_version + 收盘入库 + total_hold_pnl_est 修正 + market/daily_summaries/chart_data）| 05-scripts/daily_advice.py | 04-reviews/daily/2026-08-19-盘中研究报告.md（新增）| 04-reviews/daily/2026-08-19-深度复盘.md（新增）| 00-system/会话检查点.md | CLAUDE.md | CHANGELOG.md

---

## v3.5.3 — 2026-08-17

### 修复（全面审查 8/17）
- 🔴 **隐私泄漏**：WeChat 会话 ID 从公开代码/文档移除（05-scripts/daily_advice.py + 00-system/每日建议推送说明.md），改读环境变量 WECHAT_SESSION（setx 已配置）；历史提交仍含旧 ID，如需彻底清除需重写历史或轮换会话
- 🔴 **失效 GitHub Action**：.github/workflows/anchor-daily.yml 引用的脚本已归档（gitignore 中不存在），每个工作日静默失败 → 已停用计划任务，保留手动触发；现行自动化 = Windows 计划任务（14:30 推送 / 21:30 知识库 / 21:40 兜底 / watch_sync 实时监听）
- 🟠 **时间止损截止日解析加固**：改为语义解析（建仓日+30 天 ±7 容差 + 建仓日合理性守卫），防止 pending_actions 文本杂项日期（如 8/31 归因）劫持截止日；5 场景测试通过
- 🟠 **watch_sync 失败退避**：同步失败后 5 分钟退避，防止 JSON 损坏时反复轰击 sync_all
- 🟠 **Excel 语法错误**：gen_excel_skill.py 红盈绿亏改造引入的括号错误（私有脚本不在 CI 覆盖范围，此前漏网）已修复
- 🟡 **私有看板版本标签**：v3.3 → v3.5（标题/徽标/页脚）
- 🟡 **噪声台账回填**：8/12-8/17 DDX/信号/规则命中（来源：已存档复盘报告），DDX 准确率统计可继续

### 新增
- 🆕 **DDX 补仓窗口进 14:30 推送**：daily_advice.py 新增第 5 组查询（半导体 DDX + 超大单），结合台账连击天数直接输出「连 X 日为正 / 补仓条件满足」信号，无需翻复盘
- 🆕 **smoke 新增全量编译检查**（7b）：本地 compileall 覆盖 gitignored 私有脚本（CI 覆盖不到），62 项
- 🆕 **决策效率**：14:30 推送信号链 = 止损确认自动判定 + DDX 补仓窗口 + 回撤安全垫 + 溢价率 + 时间止损倒计时（全部实时/台账数据，无人工查询）

### 修改文件
05-scripts/daily_advice.py | 05-scripts/data_processor.py | 05-scripts/watch_sync.py | 05-scripts/rebuild.py | 05-scripts/smoke_test.py | 05-scripts/gen_excel_skill.py（本地）| .github/workflows/anchor-daily.yml | 00-system/每日建议推送说明.md | ANCHOR_体系总览.md | 06-dashboard/noise/*.json | 00-system/会话检查点.md | CHANGELOG.md

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

---

## v3.4.1 — 2026-08-17

### 变更
- 🔧 **回撤基准上移**：peak_assets 32,961 → 35,655（8/10 真实高点，用户确认）
  - 原因：旧基准 8/6 清理后已失效，-5% 线需跌 11.9% 才触发（系统失去预警意义）
  - 新基准：-5% 线 ¥33,872（距当前 4.7%）
- ✅ 8/17 半导体 +4.9% + 超大单 +196.8亿 + DDX 转正（当日+0.28），浮亏预计缩至-5.5%

