---
name: anchor-system-optimization
description: Anchor v3.3 系统优化全记录：架构、审计12项、智能分类、自动化脚本、端到端测试、git
metadata: 
  node_type: memory
  type: project
  modified: 2026-08-07T11:40:25.515Z
  originSessionId: 9a3d7c25-5603-4c48-b550-8304fca3ed81
---

## Anchor v3.3 系统优化（2026-08-07 · 四阶段）

### 阶段四：补齐三大短板（端到端验证 + 动态化 + 回撤预警）

**短板1 smoke_test.py** — 端到端产物验证（23项检查）：
- rebuild后验证 HTML/快照/Excel 存在性、大小
- 数据一致性（embed vs JSON total_assets）
- 桌面 ↔ Anchor 副本一致性
- 自动运行核心测试套件
- 运行：`python smoke_test.py`

**短板2 gen_anchor_pro.py** — anchor-pro.html 动态化：
- 从 portfolio_data.json 生成实时数据块（总资产/四层/持仓）
- 叙事部分（胜率/教训/规则/演变）完整保留
- 占位符 `__NARRATIVE__` 机制注入，避免双重闭合 bug
- 验证：D 对象 JS 执行 OK（15 keys），接入 sync_all

**短板3 drawdown_alert.py** — 回撤预警：
- 对比当前资产 vs `_meta.peak_assets`
- 触发 -5%/-10%/-15% 线预警
- `--check` 退出码：0安全/1黄线/2红线/3数据缺失
- UTF-8 输出兼容 Windows GBK 终端（sys.stdout.reconfigure）
- 接入 sync_all

**完整一键流程（sync_all.py）**：
```
更新数据 → rebuild → Excel → anchor-pro动态化 → 回撤预警 → 每日快照
```

**综合评分**：88 → 94（测试覆盖8→9.5、可维护性9→9.5、自动化8→9）

### 阶段三：智能分类 + 自动化脚本

```
Before: rebuild.py (700行单体)  →  所有逻辑混在一起
After:  data_processor.py (数据层) + rebuild.py (编排器/渲染)
```

**data_processor.py** — 独立数据层：
- `process_holdings()` — 四层分组（P1-1 后：group字段驱动 + ANCHOR_MAP覆盖 + 关键词兜底）
- `generate_rules()` — 数据驱动规则（不再硬编码）
- `generate_risk_matrix()` — 动态风险矩阵
- `monthly_ops_summary()` — 统一操作计数（generate_rules/risk_matrix/测试三处共用）
- `generate_today_conclusion()` — 今日结论三态（P1-2 新增，HTML 不再硬编码）
- `validate_data()` — JSON schema 校验
- 所有核心函数可单独 import 和测试

**rebuild.py** — 精简编排器：加载 JSON → data_processor → 渲染 HTML → 输出

### 阶段二：系统审计 12 项修复

**🔴 数据一致性（关键）**：
- #1 **回撤基准统一为 ¥32,961**（8/6清理后真实资产）。原¥39,510含已清仓虚值 → 误触发-15%线。写入 `_meta.peak_assets`，规则手册v3.3§4.1同步修正。当前组合回撤 +0.9% 安全区
- #2 HTML "August Ops" 改数据驱动（正确显示 1/4）
- #3 anchor-pro.html 更新至8/7数据
- #4 chart_data 补8/7点 + update_date
- #5 操作计数统一 monthly_ops_summary()

**🟡 代码健壮性**：#6 双Excel统一为gen_excel_skill.py(10Sheet)；#7 setup.py分类优先ANCHOR_MAP；#8 密钥无明文(关闭)；#9 02-strategy/标注历史归档

**🟢 流程**：#10 HTML回撤文案数据驱动；#11 README止盈口径加注(基金+10/+20 vs 股票+15/+30/+50)；#12 预生成8月10日盘点清单

### 阶段三：智能分类 + 自动化脚本

**P1-1 智能持仓分类**：`resolve_layer()` 三级判定 — ANCHOR_MAP精确覆盖 → group字段(数据驱动) → 关键词兜底。**新基金自动归类，不需改代码**。返回 dropped 列表告警
**P1-2 今日结论自动化**：`generate_today_conclusion()` 数据驱动三态，重建后 HTML 自动生成
**P2-1 周报脚本** `gen_weekly_report.py`：合并 chart_data 补全缺失交易日，命名对齐 `weekly_report_YYYYMM_Wx`，**防覆盖**(已有文件→生成_draft)
**P2-2 归因脚本** `gen_monthly_attribution.py`：自动统计交易/违规扫描，真实盈亏留用户填
**P3 归档**：4闲置脚本 → `05-scripts/归档/`（anchor_analyzer/fetch_market/pull_market_data/anchor_daily_report），CI workflow路径已更新

### 测试套件（29 个测试）

`test_calculations.py` — 从 data_processor import 权威实现（单一事实源）：
- TestProfitFormat / TestRateCalculation / TestLayerRatios
- TestDrawdownCheck / TestStopLoss / TestMonthlyOps / TestRealPortfolioData

运行：`python test_calculations.py`

### Git 版本控制

- 仓库：`C:\Users\lenovo\Desktop\Anchor\.git`，远程 origin/main（单一主线）
- 关键提交：fdfed18(架构) → 557a5c5(审计12项) → a6d12c3(智能分类+脚本) → fbb3530(检查点)
- 数据源 portfolio_data.json 在桌面，**不同步 GitHub**（私有持仓数据）

### 文档清理

- 规则手册 v3.1/v3.2 → 归档，仅 v3.3 活跃
- 02-strategy/ → README 标注历史归档（口径矛盾勿据此操作）
- 资产口径 ¥45,109 为错误数据 → _meta.data_provenance 注明

### 错误处理

- sync_all.py：logging + 异常捕获 + 返回值
- rebuild.py：JSON 校验 + 日志
- 日志：`05-scripts/rebuild.log`、`sync_all.log`

**Why**: 系统从手动编辑 JSON 起步，代码随需求增长变臃肿。agent-skills 插件实战应用，分三阶段系统性治理：架构/数据一致性/自动化。
**How to apply**: 
- 改规则逻辑 → `data_processor.py` 的 `generate_rules()`
- 加基金 → 不需改码（group字段自动归类）
- 改看板样式 → `rebuild.py` HTML 模板
- 生成周报 → `python gen_weekly_report.py`；月度归因 → `python gen_monthly_attribution.py`
- 改完代码 → 跑 `test_calculations.py` → git commit → push origin main
- 关联记忆：[[project-investment-framework]] [[file-organization-rules]] [[auto-use-agent-skills]]
