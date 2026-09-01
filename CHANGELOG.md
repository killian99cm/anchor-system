# Anchor 变更日志

> 每次改动必须记录：版本号 + 日期 + 变更内容 + 影响文件
> 更新时同步：portfolio_data.json / CLAUDE.md / 会话检查点.md / 本文件 / GitHub
> ⚠️ 版本冻结协议（8/27 启动）：bump 必须 CHANGELOG+JSON+CLAUDE.md 三处一致，否则不进规则手册；用 `05-scripts/version_check.py` 校验

---

## v4.3.4 — 2026-09-01（E1 漏检反思 + pre_trade_check 契约兼容/A2 强制前置）

### 🔍 9/1 事件复盘：证券贷款 +2,000 超 E1 上限 129% 漏检（决策≠执行三源核验实证）
- 9/1 用户实际执行 2 笔贷款买入：证券 +2,000（14:56，站上770+主力+11.31亿，评分卡4/5）+ 鹏华债券 +3,300（压舱石归并），月限额 2/4
- **证券这笔违反 E1 单只卫星 ≤¥3,000 硬上限**（加仓后 6,873 超 129%），且与 8/31 归因裁决「证券压回超限止盈1/3」方向相反；评分卡 4/5 满足质量门槛，属**执行纪律违规**而非方向判断错
- 决策日志补录 #54（证券·标「超E1上限,执行违规」）/ #55（鹏华·压舱石归并），T+3（9/4）复盘核算
- 后果量化：证券超限敞口 ¥3,873 + 贷款杠杆（动用残留 7,023.77 的 75.5%）；若回调 -8% → 超限部分白亏约 -310 元（坏情景暴露，非已发生亏损）
- 影响文件：06-dashboard/decision_log.json（#54/#55）/ 会话检查点.md

### 根因修复（commit f36f96b，15:20 落地 + 本会话验证）
- **A · pre_trade_check 契约兼容**：extract_rule_contract 输出 `rules` 段（键 e1_sat_position_cap 等）与校验器内置键（e1_sat_single_limit 等）不匹配 → `load_thresholds()` 现在兼容 thresholds/rules 两段 + 键名映射，实测三场景回归通过（证券+500 ⛔拦截 / 创新药+359 ✅ / 鹏华+1000 ✅，8 测试全过）
- **B · A2 强制前置**：daily_advice 信号产出后对 pending_actions 含「买入/加仓」项强制跑 pre_trade_check 并输出结论到简报，堵「信号不校验」洞
- 反思补录：E1 漏检教训进 04-reviews 反思（判断 vs 执行分离归因）
- 影响文件：05-scripts/{pre_trade_check,daily_advice}.py / 05-scripts/test_pre_trade_check.py / 04-reviews/反思*

---

## v4.3.3 — 2026-08-27（报告深度标准 v2.0 升级）

### 报告深度标准 v1.0 → v2.0（用户指示「以后按此标准，要比 mx-data 深度版更详细更准确」）
- 基准模板：2026-08-27-深度复盘.md（mx-data 深度版）；v1.0 已标注废止（仅历史存档）
- v2.0 强化三处：
  ① 头部元信息三源拆分（持仓/行情/技术指标各注时点）
  ② 核心结论表双表制：KPI 摘要行 + 持仓全景大表（一行一只：市值/当日盈亏/当日%/累计/板块当日/MA5·10·20 精确值+站上跌破/DDX 当日3日5日10日/主力资金/结论）
  ③ 逐项分析 6 要素：当日价格路径/技术面（MA精确值+DDX四周期+主力资金）/基本面利好利空双面/明日关键价位/一周压力支撑/⭐星级+量化触发线
- 技术面数据源：mx-data（东方财富）为主（MA 序列自行计算 + DDX + 主力资金），westock 交叉验证
- A1 复盘自动化升级为「深度版 v2.0」（步骤 5 mx-data 技术面采集）
- 影响文件：01-rules/报告深度标准_v2.0.md（新）/ v1.0.md（标废止）/ A1 自动化 / CLAUDE.md / 07-memory 索引 / CHANGELOG.md / 检查点

### v4.3.3 补充：交易前校验器 pre_trade_check.py（8/27 22:48 提交 6567a0f，与 v2.0 同属 v4.3.3）
- 错配教训工具化（提案 #A 加仓前超限校验 / #B 贷款分批 / #C 目标可达性标注机制化）——六项校验：① 月操作额度 4/4 拦截 ② E1 单只卫星上限（加仓后市值）③ E4 月净投入 ④ 大额/贷款 334 分批提示 ⑤ 目标可达性标注 ⑥ 评分卡提醒
- 测试：证券+2500 ⛔拦截（月额度+E1）、创新药+359 ✅通过（9/1 可用）、半导体+300 贷款 ⚠️分批提示——全符合预期
- A2 盘中信号自动化步骤 7 强制接入（⛔ 自动转观察）；规则正式化待 8/31 仲裁，工具先行落地
- 影响文件：05-scripts/pre_trade_check.py / A2 自动化 / 00-system/改进提案台账.md / 01-rules/规则生效期登记表.md

---

## 2026-08-28 — GitHub 公开仓库优化日（不 bump 版本，三处一致仍 v4.3.3）

### GitHub 曝光度与公开仓库整理（7 笔提交，全部聚焦公开侧，投资逻辑零改动）
- **隐私加固**（git 6b6dcdc）：00-system 敏感档案移除跟踪（贷款/金额/预案等 11 份，git rm --cached 保留磁盘数据完整）；.gitignore 添加 `00-system/*` 白名单机制（白名单保留 mx_install_guide / repo_info / repo_info2 三份公开文件）；根级配套 SECURITY / CONTRIBUTING / CODE_OF_CONDUCT / TROUBLESHOOTING
- **README 首屏**：重排（448511f：数字横幅+截图+Live demo 置顶）+ 整理（73edc6c：语言切换/免责声明/徽章/速览）
- **文档入口补全**（c9ab988）：FAQ/setup 入库 + docs 索引页 + README Documentation 节
- **脱敏战绩页**（9f0b36b）：08-website/track-record.html + .github/workflows/pages.yml 部署扩展
- **feature_request 模板投票引导**（7f192a2）
- **文案统一 + 版本文件路径环境变量化**（831f45a，9 文件 23增21删）
- GitHub 诊断专题 2 份：04-reviews/special/2026-08-28-GitHub曝光度诊断.md / 2026-08-28-高星项目设计借鉴分析.md
- 投资侧例行（非改动）：04-reviews/daily/2026-08-28-盘中操作建议.md（14:30，8月额度 4/4 满零操作）+ 2026-08-28-盘中研究报告.md（14:57，六段式 v2.0：半导体 DDX 连正第 2 日未达成 / 杰克逊霍尔鹰派 / 纳指 A+C 全持暴露 8/29 净值最大变量）
- 影响文件：08-website/track-record.html（新）/ .github/workflows/pages.yml / README.md / README.zh-CN.md / docs/* / 00-system/.gitignore / 05-scripts/{gen_daily_hub,version_check}.py / 09-backtest/output/* / 04-reviews/special/* / 04-reviews/daily/2026-08-28-*.md / 会话检查点.md

---

## v4.3.2 — 2026-08-27（P0/P1 落地 + 版本冻结启动）

### P0 四项（提升建议优化版执行）
- 驾驶舱 app.py 补齐（Desktop/app.py，静态服务+AI助手端点），8765 端口 4/4 通过——start.bat 修复（此前 app.py 缺失从未跑通）
- 数据自动化 MVP：05-scripts/data_auto_fill.py（复用妙想 API，查询回退逻辑），7/7 持仓回填候选成功，守铁律不写 JSON
- 加仓专项回测：09-backtest/scripts/add_position_backtest.py——回调日维度证据：黄金+2.13pp/红利+1.70pp 有效，芯片-0.54pp/证券-0.14pp 无效 → 打分卡②需联合资金确认
- 仲裁材料补充：待仲裁项 6（月限额计数口径，预推荐 C：334 建仓计 1 笔）+ 第七节加仓证据

### P1 三项
- westock 港股代码支持验证（hk00700 正常）——回测扩展基础就绪
- 2022 熊市压力测试：09-backtest/scripts/stress_test_2022.py——止损在芯片/证券/纳指=回撤减半+收益提升（芯片 MDD 改善 36.2pct），红利误伤/黄金无触发 → 止损=卫星层规则再验证
- 决策日志扩容 28→51 条（补录 2025-10~2026-06 历史 23 条，样本目标 ≥50 达成）

### 版本冻结协议启动
- 版本号三处统一 v4.3.2（CHANGELOG/JSON×2/CLAUDE.md）；新增 version_check.py 三处一致校验；A1 自动化内置自检
- 规则生效期登记表（01-rules/规则生效期登记表.md）：每条规则标生效/失效日，防已废规则引用

### 8/27 收尾补缺（升级深度分析核验后，不 bump 版本——三处一致校验仍为 v4.3.2）
- **护栏真正接入执行链**：sync_all.py 新增第 7.6 步调用 version_check.py——原 CHANGELOG 声称"A1 自动化内置自检"但脚本未引用，属文档-实现脱节；现已落地（不一致 log error 中止后续同步）
- **collab 协议补护栏描述**：reference-workbuddy-collab.md 数据互通第 4 条——bump 版本号必须三处同步改
- **CLAUDE.md 主指标同步**：近期重点行旧口径（平均收益率≥+3%）→ 三步法新主指标（盈亏比≥1.5:1｜追高≤20%｜止损执行率100%）；决策日志行同步 28→51 条/准确率 80.0%/口径审计注释

### 8/27 晚间 决策-执行偏差修复（22:2x，不 bump——三处版本仍 v4.3.2）
- **根因**：8/27 深度复盘把决策 #27「执行止盈」误读为已成交（实为 superseded→#28 延期不卖，纳指从未卖出）；且报告「8月3买2卖」误把未执行 #27 计入卖出数（实际 transactions 权威 = 4 笔 3买1卖）
- **决策日志防污染（系统性）**：decision_log.py 新增 `_is_active()`（排除 superseded/tags 含 superseded 记录），接入 accuracy_report / pending_list / due_list / next_due / review_decision 五处——superseded 决策不再计入胜率/盈亏比/分桶统计、不再进待复盘/到期提醒、**禁止回填 outcome**（防止 8/29 误标 #27 污染统计）
- **报告修正 3 处**：2026-08-27-深度复盘.md 的 #27 改为「未执行·用户确认」、月操作额度改为「8月实际执行4笔=3买1卖」、删去 #22 无依据的「卖飞+25」估算
- 验证：编译通过；--report 统计不变（23 已复盘/80.0%/0.60:1）；review #27 被拦截；pending 排除 #27

### 影响文件
05-scripts/data_auto_fill.py / 09-backtest/scripts/{add_position_backtest,stress_test_2022}.py / Desktop/app.py / 09-backtest/2026-08-26-8月31日仲裁材料.md（seg2 矛盾句修复+第七节）/ 00-system/提升建议优化版.md / 00-system/规则生效期登记表.md（新）/ 05-scripts/version_check.py（新）/ 05-scripts/sync_all.py（7.6 步护栏）/ 07-memory/reference-workbuddy-collab.md / portfolio_data.json×2 / CLAUDE.md / CHANGELOG.md / 会话检查点.md / **05-scripts/decision_log.py（superseded 防污染）** / **04-reviews/daily/2026-08-27-深度复盘.md（3 处修正）**

---

## v4.3.1-backtest — 2026-08-26（完整执行链回测落地）

### 完整执行链回测 + 仪表盘/对比图 + 仲裁材料第六节（8/31 归因 P1-4 证据闭环）

**背景**：把 Anchor 真实执行链完整建模（替代此前「止盈单维度」实验），为 8/31 月度归因提供最贴近实盘的裁决证据。

- 🧪 **新增 `09-backtest/scripts/full_anchor_backtest.py`**：完整执行链回测脚本——
  - 建仓 **334 分批**（3:3:4，批间隔 3 交易日，次日开盘执行）
  - 止损 **-8%**（收盘触发 → 次日开盘清仓，含缓冲语义）
  - 止盈 **③疏档 +10%/+20%/+35% 各卖 25%** + 剩余 25% 奔跑仓（破 20 日线或自峰值回撤 ≥8% 出清）
  - 限额 **月操作 ≤4 笔**（自然月）+ 清仓后冷却 5 交易日
  - 区间 **5 标的 × 3 区间**：full(2021-09~2026-08) / seg1(2021-09~2023-08 跌市) / seg2(2023-09~2026-08 涨市)；信号收盘确认 → 次日开盘执行（无前视）；A股 ETF 100 份手数 + T+1 + 万三双边费
- 📊 **新增 `09-backtest/scripts/make_full_dashboard.py`**：生成三件套 + 对比图 + 仪表盘——`full_anchor_equity.csv` / `full_anchor_trades.csv` / `full_anchor_summary.json`（三件套）+ `full_anchor_vs_benchmark.png`（策略 vs 满仓对比）+ `index.html`（完整执行链仪表盘）+ `takeprofit_dashboard.html` 更新
- 📄 **仲裁材料第六节**（`09-backtest/2026-08-26-8月31日仲裁材料.md` 新增「六、完整执行链回测证据」）：
  - 核心结论 = **回撤保护**：5/5 标的回撤全面改善（9.1~20.1pct），4/5 在跌市（seg1）跑赢或接近满仓（芯片 -22.6% vs 满仓 -39.0%）——334 建仓 + 止损在跌市确实少亏
  - 涨市（seg2）收益仍被止盈结构拖累（5/5 跑输满仓，与止盈单维回测一致，③疏档未解决趋势市卖飞但回撤受控）
  - 止损循环 + 月限额协同：纳指 full 26 笔交易（止损 9 + 止盈 17）证明「止损后冷却再入场」机制持续运行，月限额未误伤
  - 区间依赖确认：「纪律体系 = 少亏型而非暴利型」定位再次验证；8/31 裁决证据链闭环（止盈单维 → 参数扫描 → 档位宽度 → 止损端 → 完整执行链）
- 📁 影响文件：`09-backtest/scripts/full_anchor_backtest.py`（新增）、`09-backtest/scripts/make_full_dashboard.py`（新增）、`09-backtest/output/full_anchor_equity.csv`（新增）、`09-backtest/output/full_anchor_trades.csv`（新增）、`09-backtest/output/full_anchor_summary.json`（新增）、`09-backtest/output/full_anchor_vs_benchmark.png`（新增）、`09-backtest/output/index.html`（更新）、`09-backtest/output/takeprofit_dashboard.html`（更新）、`09-backtest/2026-08-26-8月31日仲裁材料.md`（第六节）
- 📌 本轮文档同步：CHANGELOG/CLAUDE.md/会话检查点 全部版本统一为 **v4.3.1**

---

## v4.3.1-design — 2026-08-26（示例页自洽化三修）

### 示例持仓地图移除 + smoke 更新 + 示例数据自洽化（消除「资产0却有盈亏」矛盾）

**背景**：v4.3.0 后公开页示例数据自相矛盾（hero 显示资产 ¥0 却有月度盈亏）+ 持仓地图无真实数据支撑。三连修收尾 v4.3.1。

- 🗺️ **① 示例持仓地图整体移除**（`08-website/anchor-pro.html`）：删除持仓卡渲染 JS（31 行）+ `holdingsGrid` 容器；章节改为互动试算「试算你的配置方案」；导航「示例地图」→「配置试算」
- 🧪 **② smoke_test 2 项过时检查更新**（`05-scripts/smoke_test.py`）：持仓地图移除后，「使用动态持仓标签」→「数据含动态层级标签」（active_label）；「遍历动态层级」→「金字塔消费动态层级」（pyramidViz）
- 📐 **③ 示例数据自洽化**（`05-scripts/gen_anchor_pro.py` + `06-dashboard/portfolio_analysis_example.html` + `08-website/anchor-pro.html`）：
  - hero 示意本金 **0 → ¥50,000**（消除「资产 0 却有盈亏」矛盾）
  - monthly 改为 **8 个月 6 盈 2 亏**正期望序列（600/-450/800/350/-600/900/250/500）
  - history_lead 注明「基于示意本金 ¥50,000」
- 📁 影响文件：`08-website/anchor-pro.html`、`05-scripts/smoke_test.py`、`05-scripts/gen_anchor_pro.py`、`06-dashboard/portfolio_analysis_example.html`（示例数据同步）
- 📌 本轮文档同步：CHANGELOG/CLAUDE.md/会话检查点 全部版本统一为 **v4.3.1**

---

## v4.3.0-design — 2026-08-26（设计系统统一升级 · DesignMdArchitect 专家）

### 全部可视化页面按 DESIGN.md 规范统一升级（视觉层，不改变任何数据字段）

**背景**：用户启用「规范范」（DesignMdArchitect）专家，要求优化 Anchor 所有可视化页面——更符合逻辑、更吸引观众、更具艺术感与科技感、更便捷。产出统一设计系统规范 + 4 页幂等升级脚本。

- 📐 **新增 `08-website/design-system/DESIGN.md`**：9 章节完整设计规范（品牌混搭：Linear 排版 × Stripe 色彩 × Tesla 未来感），双 AI（WorkBuddy + Claude）可消费，280+ 行精确到 HEX/CSS 变量
- 🎨 **4 页统一注入 v4.3.0 设计层**（`05-scripts/design_v43_upgrade.py`，幂等可复跑）：
  - 玻璃拟态 tokens（glass-1/2/3 + blur 12-32px + edge 光效环 + 上缘高光）
  - 顶栏 sticky 毛玻璃导航、卡片 hover 蓝光上浮、深色滚动条、打印样式、选中文本高亮、移动端触控目标 ≥44px
- 🔢 **3 个私有看板注入章节自动编号**（v4.3.0 内置）：h2 自动生成 `01 · 02 · 03…` 编号 + 渐变分隔光带 + 表格行 hover 聚焦——信息逻辑一眼可读（原误标 v4.3.1-dash-enhance 已更正，实际随 v4.3.0 设计层内置）
- 🆙 **返回顶部按钮**（4 页，原生 JS 无依赖，滚动 420px 后浮现）
- 🐛 **修复遗留 bug**：portfolio_analysis.html title/badge 仍为 v3.5（上次版本统一遗漏）→ 已统一 v4.2.0 PRIVATE
- ✅ **质量验证**：smoke_test 79/79 通过、4 页 0 死链（portfolio 双基准链接除外）、体积受控（60/33/37/106 KB）、桌面副本 md5 一致

**影响文件**：`08-website/design-system/DESIGN.md`（新增）、`05-scripts/design_v43_upgrade.py`（新增）、`06-dashboard/portfolio_analysis.html`、`06-dashboard/daily_hub.html`、`06-dashboard/decision_dashboard.html`、`08-website/anchor-pro.html`、桌面副本 `portfolio_analysis.html`

---

## v4.2.0-collab — 2026-08-26（WorkBuddy 双 AI 协作接入）

### WorkBuddy 定时自动化 + 检查点/Viking 双向互通（Claude ↔ WorkBuddy）

**背景**：用户要求「深度学习 Claude 运行方式并与 Claude 运行数据互通，让 Anchor 更好用」。WorkBuddy 已配置 4 个定时自动化（8/26 17:30 起 ACTIVE），本次打通自动化成果回流到 Claude 上下文的通道。

- 🤖 **4 个 WorkBuddy 自动化**：①每日 21:00 收盘复盘（sync_all 9 步 + smoke 79 项 + 摘要 + Viking 沉淀 + 检查点回写）②工作日 14:30 盘中信号（含买点评分卡 5 维强制打分）③周五 17:00 周报骨架 ④每月 1 日 09:00 月度归因（八步清单核对表）
- 🔄 **检查点双向互通**：A1 复盘完成后回写 `00-system/会话检查点.md`（追加 `## {date} WorkBuddy 自动复盘` 记录 + 更新 `*最后更新*` 行）；Claude 会话读检查点即可见自动化产出，避免重复执行
- 🧠 **Viking 语义记忆共用**：WorkBuddy 每晚写 `viking://anchor/review/{date}`，Claude 可 viking_search 检索——双方共用同一记忆层
- 📋 **协作协议文档**：新增 `07-memory/reference-workbuddy-collab.md`（自动化清单/分工边界/冲突规避），MEMORY.md 索引置顶；CLAUDE.md 新增「WorkBuddy 自动化协作」章节
- 🛡️ **冲突规避**：WorkBuddy 只写 `{date}-收盘复盘报告.md`，Claude 手写 `{date}-深度复盘.md`；检查点只追加不覆盖；真实盈亏铁律双方共同遵守
- 📁 影响文件：CLAUDE.md（+协作章节）、07-memory/reference-workbuddy-collab.md（新增）、07-memory/MEMORY.md（索引）、00-system/会话检查点.md（WorkBuddy 回写约定）、WorkBuddy automation（4 条，非仓库文件）。未 bump system_version（由下次 Claude 会话按需处理）

---

## v4.2.0 — 2026-08-26

### 优化建议采纳落地：买点评分卡强制纳入 + 信号脚本编码修复 + 止盈档位回测

**背景**：用户评估「深度优化建议书.html + 优化执行报告.md」后拍板三项决策：①买点评分卡（5维≥3/5）强制纳入 14:30 盘中建议流程 ②贷款残留 ¥7,023.77 维持「8/31 归因后再定」（拒绝建议书 P0 的配置债券垫方向）③补齐变更管理五步 + 修 gen_intraday_signal 编码 bug。

- 🃏 **买点评分卡（5维≥3/5）强制纳入**：`daily_advice.py` SYSTEM_PROMPT 新增第 6 条硬性规则——输出任何「买入/加仓」建议前必须附 5 维打分（①估值锚 ②回调日 ③恐慌强度 ④资金确认 ⑤试探仓位），每 ✓ 记 1 分；**总分 <3 分 → 必须标注「追高型买入 · 按打分卡放弃」，不输出买入指令**；卖出/减仓/持有/等待建议不需打分。审计实证：8/7 半导体加仓 2/5 分（追高型）应被拦截
- 🐛 **gen_intraday_signal.py 编码修复**：Windows 控制台默认 GBK 无法编码 ¥（`UnicodeEncodeError: 'gbk' codec can't encode character '\xa5'`）→ 加 `sys.stdout.reconfigure(encoding="utf-8")`，直接运行（不加 PYTHONIOENCODING）输出合法 JSON ✅（建议书「实测输出合法 JSON」此前未测出此问题）
- 📊 **stop_profit_backtest.py 新增**：止盈档位回测脚本（读数据不硬编码金额，可复跑），9 只已清仓基金 + 31 笔卖出流水复盘——结论 **v3.4 档位设计成立无需回滚**（更早更小锁利 + 奔跑仓 + 止损硬Deadline 双引擎）；额外发现半导体 17+ 笔反复小额进出坐实过度交易弱点
- 🔍 **优化执行报告**：`04-reviews/special/2026-08-26-优化执行报告.md` 完成 T+3 检查/止盈回测/规则冲突扫描/打分卡审计；3 处规则模糊点（时间止损vs恐慌豁免 / 奔跑仓14天vs20日线破线 / 事件驱动A4vs打分卡A1）建议 8/31 归因评审仲裁
- ⏳ **贷款残留处置维持原框架**：`_meta.liabilities.in_cash ¥7,023.77` 不动用，8/31 归因后再定（现金 22.1% 超配定向留给进攻层，不追防御）
- 📁 影响文件：`05-scripts/gen_intraday_signal.py`（编码修复）、`05-scripts/daily_advice.py`（打分卡规则）、`05-scripts/stop_profit_backtest.py`（新增）、`04-reviews/special/2026-08-26-优化执行报告.md`（新增）、CLAUDE.md、会话检查点、system_version → v4.2.0

---

## v4.1.0 — 2026-08-25

### 当日指挥中心 Daily Hub（`06-dashboard/daily_hub.html` + `05-scripts/gen_daily_hub.py`）

**背景**：用户要求「做一个页面，可以让我快捷，方便，直观的看到当天需要看的文件，不需要一个一个找，结合到这一个页面上，直接转跳到文件，包含所有实时更新的网页，图表，仪表盘」，并「利用 skills，把页面打造的更好，可用性更高，跟美观协调」。

- 🏠 **单一入口聚合当天全部资源**：今日快照 KPI 行（总资产 ¥49,951 / 今日盈亏 -43 / 持有盈亏 +1,573 / 上证 3,889.44+0.19% / 决策 26 条 / 现金缓冲 22.1%）+ 四层配比条带（49.8/12.6/15.5/22.1，条宽∝配比）+ 今日信号红绿灯 6 项（半导体观察仓/创新药+3000暂缓/时机A待确认/月操作4/4满/回撤安全/决策日志）+ 实时仪表盘直达 4 大卡（私有看板/决策胜率/公开页/体系图集）+ 事件日历（未来 6 事件+关联文件）+ 报告中心（自动定位最新）+ 数据文件 4 + 系统工具 8 + 快捷口令 6
- 🔗 **点击直达 41 个有效链接**：主看板/决策仪表盘/公开页/图集/深度复盘/盘中研究/黄金专题/周报/归因/会话检查点/数据协议/规则手册 等，全部相对路径（`../04-reviews/...`），0 失效
- 📊 **数据全内联 + 权威口径**：`process_all()`（四层/风险/回撤/操作）与 `accuracy_report()`（26 条/78.9%/0.60:1）复用，与主看板 100% 一致；`__占位符__` 注入避免 f-string 与 HTML/JS 花括号冲突；file:// 下无 CORS 问题
- 🎬 **GSAP 轻量增强（复用 gsap-core skill）**：卡片 reveal 进场（IO 触发，KPI/信号/仪表盘/事件/文件/口令 59 元素）+ 四层条带从左砌入（scaleX 0→1）；`.no-gsap`（CDN 失败）与无 IO 均静态完整可见；`prefers-reduced-motion` 静态；复用看板主题色（`--bg:#02070f` 系）视觉协调
- 🛡️ **Workflow 对抗验证（4 独立维度 × 287k tokens）**：链接 41/41 有效 + 数据逐项 vs JSON 交叉一致（总资产/今日盈亏/持有盈亏/上证/四层/决策统计/事件/截止日期全过）；修复 **critical 1**（半导体观察仓把浮亏百分比误当金额「¥-15」→ 从 holdings 取市值「¥493」）+ **major 3**（IntersectionObserver 特性检测兜底 / `.gitignore` 补 `daily_hub.html` 防隐私泄漏 / `--dim` 对比度 3.4:1→4.5:1 提亮 #6b84a6）+ **minor 4**（图集文案精确化 / reduced-motion 补 !important / reveal 死代码激活为实际动效 / GSAP CDN 降级确认）
- ⚙️ **sync_all.py 集成**：新增步骤 7.5 自动生成 daily_hub.html（数据更新后自动刷新，无需手动跑）
- 📁 影响文件：`05-scripts/gen_daily_hub.py`（新增）、`06-dashboard/daily_hub.html`（生成产物）、`05-scripts/sync_all.py`（+步骤 7.5）、`.gitignore`（+daily_hub.html 隐私保护）、CLAUDE.md、会话检查点、system_version → v4.1.0

---

## v4.0.2 — 2026-08-23

### 公开页四层配比区重构：左对齐配比条带（anchor-pro.html）

**背景**：用户反馈四层金字塔区块「不够和谐美观」。此前居中层叠金字塔中，双 20% 层（核心/卫星）等宽形成「平边」，视觉失衡。用户选定「左对齐层带」方向。

- 🎨 **居中堆叠金字塔 → 左对齐配比条带**：四条条带左端对齐（探针证实 BANDLEFT 四等 291px）；条宽 ∝ 目标配比并归一化（最长条铺满轨道，45:20:20:15 比例忠实：397/175/175/131px）；图标在条首、百分比印在条尾；左侧色条 + 圆角右端，悬停发光
- 📊 **图例保留 + 双向高亮**：右列图例（色点+层名+纪律+占比）与条带 hover/focus 双向联动（无 GSAP 依赖，键盘/触屏可及）
- ✏️ **文案去重**：区块 p「层宽 = 目标配比」→「条宽即配比」；内部 h3「四层金字塔 · 层宽 = 目标配比」→「四层配比 · 条宽即配比」；aria-label「四层金字塔结构」→「四层配比结构」（配比仅出现一次）
- 🎬 **入场动效重构**：GSAP 效果 9「金字塔从地基建造」→「配比条带从左砌入」（条带 x:-28 左滑淡入 + 百分比印章弹入 + 图例右滑）；无 GSAP 时 CSS `pyrRise`→`pyrIn`（translateX 左滑）
- 🧹 移除：金字塔居中堆叠布局、flex-end 底锚定、clip-path 三角形背景、first/last-child 圆角特殊化
- ✅ **验证**：gen + smoke → **79 通过 / 0 失败**；Edge headless 4 路径（gsap 桌面 / no-gsap / 移动 390px / reduced-motion）零错误；BANDLEFT=291,291,291,291（左对齐）、BANDW=397,175,175,131（比例忠实）、PCTRIGHT=12（百分比在条尾）、双向高亮、aria/H3/legend 全对
- 📁 影响文件：`08-website/anchor-pro.html`（HTML/CSS/render JS/GSAP effect 9）、CLAUDE.md、会话检查点、system_version → v4.0.2

---

## v4.0.0 — 2026-08-22

### 公开页 GSAP 深度重构（最大程度使用 gsapskills · 架构大改，anchor-pro.html）

**背景**：用户要求「最大程度的使用 gsapskills，深度重构页面……有创意，流畅，视觉反馈强烈，深度交互能力」「优化每一个细节，不放过每一个角落」。v3.9/v3.10 的原生 canvas 粒子、打字机、3D tilt、演进时间线 sticky-pin 保留为降级路径，本次引入 **GSAP 全家桶**（ScrollSmoother + ScrollTrigger + SplitText + ScrambleText + ScrollToPlugin，全部免费）做架构级重构，对标 demos.gsap.com。

- 🔧 **架构**：6 个 GSAP CDN 外链全部放 `<head>`（内联 script 之前，满足 smoke 正则）；`body` 重构为 ScrollSmoother 要求的 `smooth-wrapper`/`smooth-content`（nav 外移到 wrapper 外、fixed 图层留在外）；CSS 末尾追加 `.js.gsap` 中和块；boot 加 `gsapOk` 六插件全校验 + `gsap`/`no-gsap` 类 + `registerPlugin`
- 🎬 **20 项 GSAP 效果**（`gsap.matchMedia` 桌面 + no-preference 门控，移动/reduced-motion 零动画静态可见）：① ScrollSmoother 全页惯性滚动 ② Hero h1 逐字进场（SplitText chars） ③ Command Card 3D 翻入 ④ 鼠标深度视差（quickTo 多深度 + 轴分离） ⑤ cursorGlow 顺滑跟手 ⑥ 标题逐字揭示（SplitText `ignore:"em"` 保住高亮） ⑦ kicker ScrambleText 乱码解码 ⑧ 分隔线生长 ⑨ 卡片网格 ScrollTrigger.batch stagger ⑩ 金字塔从地基建造 ⑪ 演进时间线 GSAP 横向 pin ⑫ 月度柱状图 scrub 生长 + hover ⑬ count-up 滚动触发 ⑭ 导航激活 + 锚点平滑 ⑮ 滚动进度条 ⑯ toTop ⑰ Hero 滚动视差 ⑱ 闭环总览联动揭示 ⑲ CTA/按钮微交互 ⑳ 卡片 3D tilt quickTo 顺滑升级
- 🛡️ **完整降级**：任一插件 CDN 失败 → `gsapOk=false` → `.no-gsap` 全原生（reveal/IO/原生 tilt/演进 sticky-pin/打字机），四路径运行时零报错
- 🔧 **对抗性复核 9 条确认修复**（20 子代理工作流，840k tokens）：① [HIGH] reduced-motion+GSAP 时演进时间线被 100vh/overflow 永久裁切 → 新增 reduced-motion CSS grid 回退（pin-stage static/auto/visible）② GSAP/原生 tilt 在持仓筛选 render() 重建卡片后失效 → 抽取 `bind`/`bindGsapTilt(scope)` + `window.__*` 重绑 ③ 移动端导航无汉堡 → 新增 nav-toggle 下拉 ④ gsapOk 缺插件检查 → 6 插件全校验 ⑤ Command Center 指标硬编码 vs D.hero 死字段 → 改为 D.hero 驱动（含体系评分大数字） ⑥ `--dim` 对比度 3.62:1→5.00:1（WCAG AA）⑦ 删死规则 `will-change` ⑧ batch `overwrite:true`→`"auto"`（保住 tilt 的 rotationX/Y） ⑨ 打字机按段数动态填充加固
- ✅ **验证**：`gen_anchor_pro.py` + `smoke_test.py` → **79 通过 / 0 失败**（新增 6 项检查：CDN-in-head/ScrollSmoother 结构/插件齐全/注册门控/关键 API/gsap-no-gsap 降级）；Edge headless 四路径（gsap 桌面 / no-gsap / 移动 390px / reduced-motion）全部零控制台错误；关键修复逐项运行时证实（reduced-motion 演进网格回退 pinH 805→286px、SplitText aria-label+aria-hidden、tilt 重建双模式生效、heroMetrics=D.hero、汉堡导航）
- 📁 影响文件：`08-website/anchor-pro.html`（架构重构 + 20 项效果 + 9 项修复）、`05-scripts/smoke_test.py`（6 项新检查）、CLAUDE.md、会话检查点、system_version → v4.0.0

---

## v4.0.1 — 2026-08-23

### 公开页修复与进化区重构（anchor-pro.html）

**背景**：用户反馈两个问题——① 首页 hero 有「固定界限」，文字遇到边界会消失；② 「体系持续进化」区块展示过于复杂，希望「简洁一些，或者增加讲述内容」。用户选定「简洁骨架 + 讲述」结合方案。

- 🐛 **① hero 固定界限修复**：`.hero{overflow:hidden}`（v3.9 为容纳 inset:-20% 光晕而加）在鼠标深度视差（`cmdX ±112px`）把 command-card 推出 hero 边界时**硬裁切右侧文字** → 移除 overflow:hidden + `.hero-glow` `inset:-20%→inset:0` + 视差幅度收敛（copyX 56 / cmdX 80 / glowX 110）。修复后 1366px 视口下 card 越界 61px < 侧边距 63px，**不再越出视口**，深度交互保留
- 🎨 **② 进化区「简洁骨架 + 讲述」重构**：6 卡横向 pin（v3.10.0/v4.0.0）→ **4 章节叙事**（地基/边界/自动化/下一站），各带一句话「为什么」故事；开头一句总述「规则不是设计出来的，是复盘长出来的」；横向连线生长 + 章节错峰入场（GSAP）替代长滚动 pin；分数仍由 `D.evo` 权威回填（数据驱动）
- 🧹 **同步清理**：删除 pin-shell/pin-stage/evo-track/pin-hint/timeline 全部 CSS+JS（原生 pin IIFE、GSAP pin 模块、reduced-motion 回退块）；count-up 目标 `.pin-stage .count-up`→`.evo-wrap .count-up`；smoke 检查「演进横向 pin」→「进化叙事章节」
- ✅ **验证**：gen + smoke → **79 通过 / 0 失败**；Edge headless 四路径（gsap/no-gsap/移动 390px/reduced-motion）全部零错误；chapters=4、D.evo 回填 80/96/96、heroOv=visible、移动 1 列
- 📁 影响文件：`08-website/anchor-pro.html`、`05-scripts/smoke_test.py`、CLAUDE.md、会话检查点、system_version → v4.0.1

---

## v3.10.0 — 2026-08-22

### 公开页演进时间线横向 Pin（GSAP 招牌技法 · 原生零依赖实现，anchor-pro.html）

**背景**：用户要求学习 demos.gsap.com 的设计创意与思路方法，找出适合 Anchor 的效果，把公开页升级为高级动态展示网站。GSAP demo 招牌技法中 **pin 固定 + 横向滚动**（ScrollTrigger pin + x 动画）最具冲击力；`#evolution` 六张版本卡（v3.0→v3.5，分数 80→96）是天然的横向叙事素材——把「体系逐版本进化」的推进感视觉化。用户确认：**原生 ES5 零依赖重实现**，只做此一个效果。

- 📌 **演进时间线横向 pin**：`#evoStrip` 外层加 `pin-shell`（JS 定高）/ `pin-stage`（`position:sticky;top:0;height:100vh`，天然实现 pin）/ `evo-track`（flex 横排，`transform:translate3d(-p*dist)` 随滚动进度横向滑动）；右下角「继续滚动探索 ↓」脉冲提示条
- 🧮 **滚动进度驱动**：`p=(0-shell.top)/(shell.height-100vh)` 映射到横向位移，rAF 节流 + passive，与既有 scroll 模块同构；resize/orientationchange/load 重测
- 📱 **优雅降级**：`(max-width:980px)` 或 `prefers-reduced-motion` 由 JS 加 `no-pin` 类回退原静态 grid（980px→3 列、640px→2 列保留）；noscript 无 `.js` 门控不触发 flex，时间线保持原排版
- 🎨 **卡片放大**：卡宽 `clamp(240px,24vw,380px)`，桌面任意宽度均保证横向滑距；stage 全屏出血（`width:100vw`），时间线横贯视口更富电影感
- ✅ **验证**：`python gen_anchor_pro.py` + `python smoke_test.py` → **73 通过 / 0 失败**（新增 1 项检查：演进时间线横向 pin）
- 📁 影响文件：`08-website/anchor-pro.html`（HTML 包裹 + CSS pin/回退 + JS 模块）、`05-scripts/smoke_test.py`（新检查）、CLAUDE.md、会话检查点、system_version → v3.10.0

---

## v3.9.2 — 2026-08-22

### 体系可视化简洁化：Diagrams 区 → 单一系统闭环总览（anchor-pro.html）

**背景**：用户连续两次反馈「体系可视化有点复杂，简洁一点，一目了然」「这块区域不够简洁」，并明确选择方案 A（单一系统闭环总览图）。

- 🔄 **Diagrams 区 3 张 iframe 图 → 单一系统闭环总览**：`#diagrams` 从「数据管道/决策闭环/系统架构」三张密集 iframe（均为 min-width:980px SVG 塞进 ~400px 卡片导致文字不可读）收敛为一张 HTML/CSS 内联四步闭环：**数据输入 → 规则处理 → 可视化输出 → 复盘迭代**（回流条标注「复盘结论回流规则与数据」）
- 📎 **详情保留为链接**：三张详细图改为底部胶囊链接（新标签打开），内容不丢失
- 📱 **响应式**：桌面四步横排箭头串联；移动端纵向堆叠、箭头旋转 ↓；reduced-motion 静态、stagger 交错进场保留
- 🧹 每步大字标题 + 一句话说明（图标 + 编号 + 顶边主题色），扫一眼即懂体系
- ✅ **验证**：`python gen_anchor_pro.py` + `python smoke_test.py` → **72 通过 / 0 失败**（新增 1 项检查：体系图简洁化——含 system-loop/loop-step、无 iframe 图）
- 📁 影响文件：`08-website/anchor-pro.html`（Diagrams 区重构）、`05-scripts/smoke_test.py`（新检查）、CLAUDE.md、会话检查点、system_version → v3.9.2

---

## v3.9.1 — 2026-08-22

### 公开页背景交互 + 体系可视化简洁化（anchor-pro.html）

**背景**：用户在 v3.9.0 基础上提出两点新要求——「① 鼠标滑动时背景内容可交互、画面随鼠标变化且符合主题；② 切换顺滑、由浅入深有代入感」，随后反馈「体系可视化有点复杂，简洁一点，一目了然」。

- 🖱️ **全页交互背景粒子场**：`#bgCanvas` 固定全屏 Canvas，资金流粒子随鼠标**推开形成涟漪**（rAF 节流 + passive，仅桌面 pointer:fine，移动端关闭，reduced-motion 静态）；配合既有 Hero 粒子**牵引**形成双层交互纵深
- 💡 **全页鼠标跟随光晕**：`#cursorGlow` 固定层低透明度泛光（z-index 夹在背景与内容之间），鼠标滑过全页光影随之变化
- 🎢 **由浅入深 reveal 门控**：`.js` 门控 fade + translateY(26px) + scale(.985) 深度入场（cubic-bezier 缓出），`.js .stagger>*` 交错保留；`.section` 加 `scroll-margin-top` 修正锚点定位；reduced-motion 全静态兜底
- 🧹 **体系可视化简洁化**：架构区从「金字塔 + 配比米尺」双栏收敛为**单一居中金字塔**（行宽即目标配比，每行只留一句话纪律 rule）；两段长注合并为一句隐私说明；`#allocationViz` 渲染移除（smoke/gen 均无引用，确认安全）
- ✅ **验证**：`python gen_anchor_pro.py` + `python smoke_test.py` → **71 通过 / 0 失败**（新增 2 项检查：全页交互背景粒子场、reveal 门控）
- 📁 影响文件：`08-website/anchor-pro.html`（背景交互 + 简洁化）、`05-scripts/smoke_test.py`（新检查）、CLAUDE.md、会话检查点、system_version → v3.9.1

---

## v3.9.0 — 2026-08-22

### 公开页首页 Command Center 高冲击重构（anchor-pro.html）

**背景**：用户「首页可以做成高端动态页面吗？」→ 方案确认方向为**高冲击 Command Center**（指挥中心观感），本次只重构公开页首页模板，私有看板 rebuild.py 不动。

- 🎨 **Hero 粒子资金流**：Canvas 蓝色/青色浮点 + 邻近连线（桌面 ≤72 / 移动 28，`prefers-reduced-motion` 单帧静态，`visibilitychange` 自动暂停）
- ⌨️ **打字机标题**：「不靠预测，靠纪律」逐字打出 + 琥珀光标；文案由 `D.copy.hero_typed` 驱动（copy 扩展 `hero_kicker`/`hero_typed`/`hero_sub`/`score_animated`）
- 🔢 **count-up 数字滚动**：Command Center 评分 96 + 时间线 6 版本分数从 0 滚动至终值（IntersectionObserver 触发，1.2s 缓出）
- ✨ **鼠标光晕 + 滚动视差 + 顶部进度条**：Hero 径向光晕跟随（仅 pointer:fine）、Hero 内容上移淡出、渐变滚动进度条（均 rAF 节流 + passive 监听）
- 🎴 **卡片 3D tilt**：KPI/规则/持仓/证据/噪声卡 ±7°X/±9°Y + translateZ 抬升（仅桌面 pointer:fine）
- 🎢 **stagger 交错进场**：9 个数据容器子卡片 70ms 级联入场；`.js` 门控（`documentElement.className+= " js"`）保证 noscript 不隐藏静态内容
- 🛡️ **无障碍/性能**：全部动效走 transform/opacity；`prefers-reduced-motion` 全静态兜底（打字机全文直显、count-up 直接终值、粒子单帧、tilt 关闭）
- ✅ **验证**：`python gen_anchor_pro.py` + `python smoke_test.py` → **69 通过 / 0 失败**（含新增 7 项 Command Center 结构检查）
- 📁 影响文件：`08-website/anchor-pro.html`（模板重构）、`05-scripts/gen_anchor_pro.py`（copy 字段扩展）、`05-scripts/smoke_test.py`（新结构检查）、`06-dashboard/portfolio_analysis_example.html`（数据块同步）、CLAUDE.md、会话检查点、system_version → v3.9.0

---

## v3.8.5 — 2026-08-21

### 8/21 收盘持仓同步 + 止损硬Deadline 修正（8/22 周六休市 → 8/25）

- 📊 **持仓同步**（用户 8/21 收盘提供 App 明细）：holdings_summary 10 项更新（基金+余额宝当日 **-7.90**、股票 515180 日亏 **-4**，组合当日 **-11.9**）
  - 半导体 mv 1018.47（浮亏 -136.65，-11.83%，整仓累计 +259.70）；创新药 +46.70（+1.85%）；黄金 -23.38（-1.13%）收窄；证券 4695.62（-104.38，-4.54%，8/21 +2500 后）
  - **total_assets 49866.68** = 基金 44134.68 + 股票 5732；净值口径 42842.91（扣贷款残留 7024）；四层 49.6 / 12.4 / 16.6 / 21.3%
  - 余额宝 13151.93 → 10627.21（-2524.72 = 证券 +2500 自余额宝扣款 + 当日净额）；8 月操作 3/4（8/7 半导体 + 8/20 债券 + 8/21 证券）
  - daily_summaries 追加 8/21；chart_data 08-21 pnl → -11.9；stop_loss_watch cur_pct → -11.83
- ⚠️ **止损硬Deadline 修正**：**8/22 为周六休市**（8/19 触发时误写 8/22）→ 修正为 **8/25（周二）**（触发后第 4 交易日，跳过 8/22-23 周末）；**8/24（周一）为最后缓冲日**；缓冲已用 2 次（8/20、8/21）
- 📁 影响文件：`portfolio_data.json`（holdings_summary / 汇总 / daily_summaries / chart_data / stop_loss_watch / system_version→v3.8.5）、`04-reviews/daily/2026-08-21-深度复盘.md`（新建）、CLAUDE.md、规则手册 v3.4、会话检查点、记忆备份（07-memory）

---

## v3.8.4 — 2026-08-21

### 半导体数据彻底更正（用户 8/21 提供完整真实流水）

- 🔍 **核心发现**：v3.8.1 只核对了 2026 年 6-8 月的 8 笔流水，**严重不全**。用户提供完整交易记录后确认：半导体基金（华夏半导体芯片ETF联接C 008888）**自 2025-10-10 建仓**，真实流水 **42 买 + 13 卖**（2025-10 至 2026-08）
- ✅ **整仓累计盈利 +253.36**（holdings cumul，含已实现；7/16 研究报告曾记载累计盈亏 **+452.07**，减仓锁利 + 后续回撤后为 +253.36）——此前把「当前持仓浮亏 -12.38%」误当整仓亏损的**叙事错误已纠正**：半导体不是亏损股
- ⚠️ **当前持仓浮亏 -142.99（-12.38%）真实**：止损（8/19 触发 → 8/25 硬Deadline）针对**当前持仓**，非整仓；净投入 **758.77**（42买+13卖，含 8/7 加仓 300；App 交易统计显示 408.77 未含 8/7，差异待 App 核实）
- ✅ **transactions 补全**：半导体 8 笔 → **55 笔**（总量 72 → 119 笔）；6/15 修正为「加仓（2025-10 已建仓）」；8/7 加仓 300 用户确认存在（流水表格漏行）
- ✅ **decision_log 修正**：#4 补口径澄清（止损针对当前持仓，整仓累计盈利 +253.36）；#6/#20 review_note 补整仓口径；#7 rationale 修正（去掉误导性「补到合计1000」，实为 7/16 建议 +¥300 ¥1549→¥1849，用户未执行反而减仓44%）；#10 实盈 **+14.87 确认自洽**（7/16 报告持仓盈亏 +34.15 × 减仓44% ≈ +15，pnl_pct=2.3%）——统计不变（80% / -6.23% / 0.93:1，加仓 50%）
- 📁 影响文件：`portfolio_data.json`（transactions + holdings note + system_version→v3.8.4）、`06-dashboard/decision_log.json`、CLAUDE.md、会话检查点、记忆备份（07-memory）

---

## v3.8.3 — 2026-08-21

### 创新药操作深度分析 + 决策日志准确化

- 🔬 **深度分析**（5 代理交叉归因 + 盈亏口径核实）：创新药 2025-08-19 建仓至 2026-08-21 全周期复盘 → `04-reviews/special/2026-08-21-创新药操作深度分析.md`
  - **核心结论**：12 个月累计净亏 **-258.58**（8/21 用户确认到今日，约 -10.7% 净投入口径；8/20 为 -248.04、当日亏 -10.54），当前 +2.27% 浮盈全靠 8/20 单日行情
  - **纠正此前推算**：回填时按 App 买入口径 7,224.46 推出「+171.96 盈利」为**低成本假象**——平台 `cumul=-258.58`（8/21 确认）反推买入口径为 7,655.00；真实拆解 = 已实现 ≈-315.82 + 浮盈 +57.24
  - **行为模式**：追涨/右侧惯性为主风险；「摊低→割肉」循环；高抛低吸实为亏损成交；唯一纪律 = 小额定投 + 底部回补
- 📝 **decision_log 准确化**：#14 review_note 补整仓累计口径（8/21 用户确认累计 -258.58 = 8/20 -248.04 − 当日亏 10.54，净投入约 -10.7%；7/21 位置正确 ≠ 整仓操作正确）；#1/#14 补 snapshot（8/20 HSSCID 3104.56 +5.36%、ETF 获利了结 2.84 亿；7/21 资金切换背景）——统计不变（80% / -6.23% / 0.93:1，加仓 50%）；决策仪表盘已重建（decision_dashboard.html）
- ✅ **买入口径澄清**（用户 8/21 补充）：9/25 实为**卖出 293.77**（非买入）；12/08 转换转入成本基数确认 = **208.87 份 × 净值 1.0986 = 229.46**（差 0.0046 舍入）；三口径分解：明细 7,594.46（纯买 6,950 + 定投 415 + 转换 229.46）、平台 7,655.00 = 明细 + 60.54、App 7,224.46 = 明细 - 370；**剩余 ~60 元来源未定**（C 类无申购费，用户 App 无可查字段，疑分红再投资/转换费/未导出流水，如实保持未定）；对外口径统一用平台 `cumul=-258.58`（8/21 用户确认到今日：8/20 累计 -248.04、**8/21 当日亏 -10.54**）
- 📁 影响文件：`portfolio_data.json`（system_version→v3.8.3）、`06-dashboard/decision_log.json`、`04-reviews/special/2026-08-21-创新药操作深度分析.md`（新建）、CLAUDE.md、会话检查点、记忆备份（07-memory）

---

## v3.8.2 — 2026-08-21

### 创新药/天弘通利 2026 真实流水回填（用户提供完整 App 导出）

- 🔍 **核对发现**：transactions 创新药仅 1 条（7/21 试探 300）、天弘通利仅 3 条定投，远不足以支撑月度操作统计；用户导出完整历史后确认回填 **仅 2026 年至今**
- ✅ **transactions 回填**（30 → **72** 笔，CRLF 保留）：
  - **创新药**（易方达港股创新药ETF联接C）：补 2026 买入 **12 笔**（1/8+500、1/26+300、2/26+1000、3/3+100、4/30+200、5/15+300、**5/18+350、5/19+150、5/28+200、6/2+200、6/3+200、7/21+300**——后 6 笔为用户确认）+ 卖出 **4 笔**（1/21 599.96、2/3 508.70、3/4 1292.48、4/1 634.32）；7/21 旧「买入试探」条目更新为完整名称+真实成交
  - **天弘通利**（混合A）：补 2026 定投 **21 笔**（1/5-8/3，含 7/6-8/3 之前流水）+ 手动买入 2 笔（1/30+100、2/4+200）+ 卖出 **4 笔**（2/2 524.56、3/4 669.89、5/15 741.75、**6/26 497.42**——按之前流水确认）
- ✅ **decision_log 修正**：#14 类型「建仓」→「**加仓**」（基金自 2025-08 已建仓，7/21 实为加仓）——**加仓准确率 40%→50%**（#14 correct 正确入桶）；总统计不变（80% / -6.23% / 0.93:1）
- 📌 定投条目全部标注「非手动不计月限额」；新增手动买卖计入对应月份操作统计（2026-01~07 更真实）；**不新增 decision_log 决策**（5-6 月买卖非 Anchor 建议，避免虚增胜率）
- 📁 影响文件：`portfolio_data.json`（transactions + system_version→v3.8.2）、`06-dashboard/decision_log.json`、CLAUDE.md、会话检查点、记忆备份（07-memory）

---

## v3.8.1 — 2026-08-21

### 半导体真实操作流水核对修正（用户提供 App 流水 8 笔）

- 🔍 **核对发现**：transactions 半导体仅 4 条且含错误——「7/16 加仓 300」是把 7/16 研究报告的**建议**误当**执行**（真实 7/16 是减仓 44%）；「卖出 674.57」金额错误（真实 637.99，与 deep_review 记载「减仓44%回笼¥638」吻合）；6 月建仓/加仓 5 笔缺失
- ✅ **transactions 修正**：补录 6/15 +200（建仓）、6/26 +300、6/30 -355.16、7/2 +300、7/3 +500 共 5 笔；删除虚构「7/16 加仓 300」；「7/16 减仓」金额 674.57→637.99。净投入 = 1,800-993.15 = **806.85**
- ✅ **decision_log 修正**：#7（7/16）verdict「执行买入」→「建议买入」（7/16 报告建议加仓但用户实际减仓，建议未执行）；#10 卖出金额 674.57→637.99（实盈待确认）。统计不变（80% / -6.23% / 0.93:1）
- ⚠️ **待续**：创新药（4/1 卖出前必有更早持仓）、天弘通利（6/26 卖出前必有更早定投）流水待用户补充后补录；持仓成本以 App 当前显示为准（holdings 未动）
- 📁 影响文件：`portfolio_data.json`（transactions + system_version→v3.8.1）、`06-dashboard/decision_log.json`、CLAUDE.md、会话检查点、记忆备份（07-memory）

---

## v3.8.0 — 2026-08-21

### 深度归因 → 优化方案（用户：「深刻思考原因，吸取失败经验，形成更好的优化方案，提高胜率收益率，决策表每天同步」）

- 🔬 **六透镜独立交叉归因**（6 个代理各自独立核读源文件后综合）：
  - **买点工程**：半导体 3 笔全错 = 三种追高形态（7/15 事件接刀 / 7/16 机械抄底 / 8/7 右侧追顶），坏买点=只验趋势不验位置；成功买点全部 = 估值锚+回调日+小仓试探（证券 3 笔+创新药）
  - **换仓**：已实现亏损 -1,109 的 **75%（-834）来自两次换仓**（#1 卫星→诺安 -383「伪换仓」同方向集中、#2 红利低波→中证2000 -418「防御换进攻」）——卖买绑一步、用「换」字豁免全部纪律
  - **止损拖延**：规则只有触发无截止时间，中证2000 从 -6% 拖到 -17% 放大 2.8×；但 7 笔止损判定全部 correct——判断力从不差，差的是执行速度
  - **盈亏比 0.93:1**（4赚12亏，均盈 +11.18% vs 均亏 -12.03%）——赚端小步收割、亏端拖延确认，方向准确率 80% 却落地亏损
  - **仓位结构**：压舱石+现金 +1,318 靠规则赚钱，卫星净浮亏 -193；证券 8/21 单笔 +2,500 推至 ¥4,692 超单只上限 56%
  - **决策闭环五环断裂**：记录/快照/字段/提醒/统计未接入每日主线
- 📄 **方案文档**：`04-reviews/special/2026-08-21-深度归因与优化方案-v3.8.md`（A-E 六大类新规则 + 7 项可量化目标，8/31 归因验证）

### 新增制度与脚本（v3.4 规则手册）

- 📘 **规则手册 v3.3 → v3.4**（`01-rules/投资规则手册_v3.4_正式版.md`，已重命名）：
  - **A 买点**：买点评分卡 ≥3/5（估值锚/回调日/恐慌强度/资金确认/试探仓）、追红日禁买、浮亏仓禁摊平、事件驱动 ≤¥300 试探
  - **B 止损**：硬Deadline（触发后缓冲+延期合计≤3 交易日，第 4 天 14:30 无条件执行）、负面清单 10 日清仓、逻辑证伪 1 日减仓 50%、`stop_loss_watch` 状态机
  - **C 止盈**：档位重构 +8%/+15%/+25% 各 25% + 25% 奔跑仓跟 20 日线；盈亏比记账 + 目标 ≥1.5:1（连续 2 次 <1.0 冻结买入）
  - **D 换仓**：7 项检查清单、强制拆两笔 + 72h 冻结、主动基金间转换永久禁止
  - **E 仓位**：单只卫星 ≤¥3,000、追高单次 ≤¥300、卫星月净投 ≤¥1,500、定投白名单+弱势熔断
- 🐍 **`decision_log.py` v3.4**：`--report` 分桶新增 **盈亏比（avg_win/avg_loss/pnl_ratio）+ 追高型买入占比**，仪表盘新增 2 个 KPI 卡；新增 **`--stopwatch`** 止损倒计时（读 `portfolio_data.json stop_loss_watch`，按硬Deadline 三态）
- 🔄 **`sync_all.py` 第 7 步**：决策日志每日同步扩为四步 `--due → --report → --stopwatch → --dashboard`（每天随数据更新自动执行）
- 📐 **数据更新协议 v1.3**：每日层「决策日志」自动同步 + 操作步骤第 10 步说明

### 数据
- 📊 **`portfolio_data.json` 新增 `stop_loss_watch`**：半导体 {触发 8/19、缓冲延期已用 2 次、硬Deadline **8/25**、浮亏 -12.38%}，system_version → **v3.8.0**
- 🎯 **盈亏比口径校正**：方案初稿 0.76:1 → 实算 0.93:1（decision_log.py 等权分桶，16 笔已复盘），已同步修正方案文档与规则手册

### 影响文件
- 新增：`04-reviews/special/2026-08-21-深度归因与优化方案-v3.8.md`、`01-rules/投资规则手册_v3.4_正式版.md`（原 v3.3 重命名）
- 修改：`05-scripts/decision_log.py`（--report 盈亏比/追高 + --stopwatch）、`05-scripts/sync_all.py`（第7步四步循环）、`00-system/数据更新协议.md`（v1.3）、`CLAUDE.md`（v3.8.0）、`portfolio_data.json`（stop_loss_watch + system_version v3.8.0）、`06-dashboard/decision_dashboard.html`（盈亏比/追高 KPI，gitignore）

---

## v3.7.2 — 2026-08-21

### 数据修复（7/24 证券+500 交易缺口回填）

- 📥 **回填 7/24 证券+500 至 transactions**：用户确认买入 + deep_review_20260724 复盘记载 → 补录 `{"date":"2026-07-24","name":"易方达证券ETF联接C","op":"加仓","amount":500}`（transactions 25→26 条）
- 🎯 **成本口径核对结论**：cost_basis **1.1606 已包含 7/24 这笔**——7/24 当日复盘「仓位 ¥2,266 + 浮亏 ¥34 = 成本 ¥2,300」，该成本 8/5（研究报告成本价 1.1606）与 8/20（¥2,300）保持一致，故**不改 cost_basis、不改 mv/pnl**，仅补交易记录
- 🔢 **平均收益率 -6.23% 三视角交叉验证**（账户盈亏/统计口径/亏损归因 3 个代理独立核读源文件）：确认是 16 笔补录 pnl_pct 的等权算术平均，混合「已实现盈亏率 + 未实现浮盈亏率」两种口径，金额加权后约 -10.0%；正确边界 = 「每笔决策平均落地幅度」，**不是**系统盈利，也**不是**「每笔操作平均亏 6.23%」
- ♻️ 重建看板（rebuild.py）：6-dashboard 双副本同步，总资产 ¥52,379（含证券+2500 T+1）

### 影响文件
- 修改：`portfolio_data.json`（transactions +1=26、system_version v3.7.2）、`06-dashboard/portfolio_analysis.html`、`06-dashboard/portfolio_snapshot.json`（重新生成）

---

## v3.7.1 — 2026-08-21

### 新增（决策日志历史补录：胜率覆盖完整历史）
- 🆕 **`decision_log.py` 新增 `--backfill`**：补录历史决策（`"日期|类型|标的|判定|金额|依据|预期"` 多行 CSV），自动标记 `backfilled=true`，T+3 到期日按记录日+3精确计算
- 📥 **补录 16 笔历史手动操作**（7/15–8/7 + 7/24，来自 portfolio_data.json transactions + 复盘报告交叉验证）：决策数 5 → **21 条**
- 📊 **回填 16 笔历史 outcome + 真实收益率**（依据 04-reviews 复盘报告/教训库明确记载）：
  - **准确率 80%**（correct 12 / wrong 3 / neutral 1）
  - **平均收益率 -6.23%**（真实：卖出=实现盈亏/成本，买入=当前浮盈浮亏位置级）——为负主因：① 半导体追高 3 笔 wrong 均 -12.4% ② 止损卖出的实现亏损（中证2000 -17%、光伏 -20.5%、诺安 -17.8% 等，方向对但落地为亏损截断）；TMT50 阶梯止盈 +22.1%/+18%、半导体减仓 +2.3% 为正
  - 🔍 **核心发现：加仓准确率仅 40%**（2对3错1中性）——3 笔全错均为**半导体追高补仓**（7/15 打新布局、7/16 触-12%加仓线、8/7 DDX未过建仓检查），印证教训库「追高/补仓摊平是亏损之源」
  - 卖出纪律优秀：减仓 100%（3/3）、清仓 100%（6/6）、建仓 100%（1/1）
- ⚠️ **发现数据缺口**：portfolio_data.json transactions **缺失 7/24 证券+500**（复盘报告 deep_review_20260724 明确记载，decision_log 已补录 #21，待用户确认是否回填 transactions）

### 影响文件
- 修改：`05-scripts/decision_log.py`（--backfill）、`06-dashboard/decision_log.json`（21 条，gitignore）、`06-dashboard/decision_dashboard.html`（重新生成，gitignore）

---

## v3.7.0 — 2026-08-21

### 新增（可视化升级：品牌体系图 + 决策闭环自动化）
- 🆕 **`08-website/diagrams/` 体系图集（4 张 Anchor 品牌 SVG 图）**：深色金融终端风格，统一品牌色——
  - **`pyramid-4layer.html` 四层金字塔**：目标比例 + 当前占比偏差 + 典型持仓，塔尖现金「弹药」/塔底压舱石「基石」
  - **`data-pipeline.html` 数据管道**：定位/获取/归因/验证 四层规范流程
  - **`decision-loop.html` 决策闭环**：建议→观察→T+3复盘→校准 循环
  - **`architecture.html` 系统架构**：数据源→处理→输出→发布 全链路
- 🆕 **`~/.diagram-design/profiles/anchor.md` + `Anchor/.diagram-design`**：diagram-design 品牌 profile（语义角色 token + 四层金字塔层级色）+ 项目标记
- 🆕 **`decision_log.py` v2.0 增强**：
  - `--due`：T+3 到期日精确计算（记录日+3自然日），今日到期/最近复盘日提醒
  - `--dashboard`：生成品牌化胜率仪表盘 `06-dashboard/decision_dashboard.html`
  - `sync_all.py` 新增第 7 步：自动生成决策仪表盘
- 🆕 **私有看板 `rebuild.py`**：四层配置面板新增**动态 SVG 金字塔**（数据来自 `D.layers`，底部压舱石→顶部现金）+ 页脚体系图集链接（JS 修正路径兼容桌面/06-dashboard 双副本）

### 修复（代码质量审查，mattpocock 方法）
- 🐛 **`anchor_to_astrbot.py`**：`os` 未导入 → AstrBot 同步启动即 NameError，补 `import os`
- 🐛 **`test_calculations.py`**：删除残留同义反复断言（`prefixes` 未定义 + 注释自证「发现不了误计」）
- ✅ 46 项测试 45 过 1 数据待办（证券+2500 加仓后 total_assets 待用户收盘数据同步，非代码 bug）

### 影响文件
- 新增：`08-website/diagrams/*.html`（4 张）、`.diagram-design`、`06-dashboard/decision_dashboard.html`（gitignore）、`04-reviews/special/2026-08-21-代码质量审查.md`
- 修改：`05-scripts/{decision_log,rebuild,sync_all,anchor_to_astrbot,test_calculations}.py`、`08-website/anchor-pro.html`、`.gitignore`

---

## v3.6.0 — 2026-08-20

### 新增（数据制度升级：准确性 → 可回溯）
- 🆕 **`05-scripts/data_pipeline.py`（数据管道四层规范）**：把 8/20 深度研究教训固化成代码——
  - **① 定位层** `DATA_PIPELINE_MAP`：9 类持仓 → 跟踪指数 → 市场 → 资金面来源 → 宏观归因 → mx查询模板 映射（防张冠李戴：港股看南向/债券看中国10Y/QDII看美股净值+溢价）
  - **② 获取层** `fund_flow_snapshot()`：mx-data raw JSON → 标准资金面快照（{ddx, ddx3, ddx10, 超大单净流入, 时间}），实测兼容双层嵌套结构 + 「亿元」单位 + 列名模糊匹配
  - **③ 归因层** `MACRO_DRIVER_MAP`：资产类别 → 正确宏观驱动（防因果错配，如债券归因美债）
  - **④ 验证层** `data_quality_check()`：报告前自检（时间戳/资金面/来源标注 + 持仓逐只覆盖）
- 🆕 **`05-scripts/decision_log.py`（决策闭环 + 胜率统计）**：用户「在一次次操作中吸取经验，提高胜率/收益率/准确率」的落地——
  - `--add` 记录决策（类型/标的/判定/金额/依据/预期方向 + 数据快照）→ `--review` 事后回填结果（correct/wrong/neutral + 收益率）→ `--report` 按类型统计准确率/平均收益率 → `--pending` 列出待复盘项（T+3）
  - 数据存 `06-dashboard/decision_log.json`（.gitignore，含判断依据属隐私）
  - 8/20 已录入 3 条种子决策：创新药+3,000 暂缓 / 纳指+3,000 暂缓 / 债券+5,700 执行

### 修改文件
05-scripts/data_pipeline.py（新增）| 05-scripts/decision_log.py（新增）| 06-dashboard/decision_log.json（新增，gitignore）| .gitignore（新增 decision_log 条目）| portfolio_data.json（system_version v3.6.0）| CHANGELOG.md | CLAUDE.md | 00-system/会话检查点.md

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

