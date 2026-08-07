---
name: anchor-system-optimization
description: Anchor v3.3 系统优化记录：模块拆分、测试、git、硬编码修复
metadata: 
  node_type: memory
  type: project
  modified: 2026-08-07T10:12:51.466Z
  originSessionId: 9a3d7c25-5603-4c48-b550-8304fca3ed81
---

## Anchor v3.3 系统优化（2026-08-07）

### 架构变化

```
Before: rebuild.py (700行单体)  →  所有逻辑混在一起
After:  data_processor.py (数据层) + rebuild.py (编排器/渲染)
```

**data_processor.py** — 独立数据层：
- `process_holdings()` — 四层分组
- `generate_rules()` — 数据驱动规则（不再硬编码）
- `generate_risk_matrix()` — 动态风险矩阵
- `validate_data()` — JSON schema 校验
- 所有核心函数可单独 import 和测试

**rebuild.py** — 精简编排器：
- 加载 JSON → 调用 data_processor → 渲染 HTML → 输出文件
- 保留完整的 HTML/CSS/JS 模板

### 规则数据驱动化

| 原来（硬编码） | 现在（数据驱动） |
|------|------|
| "DDX=-0.016（8/6转负）" | 从 market.note 提取 DDX 状态 |
| 回撤峰值 ¥37,535 | 从 _meta.peak_assets 读取 |
| "8月操作 0/4" | 从 transactions 数组计数 |
| 风险矩阵 8 条固定 | 根据 DDX/黄金/固收/成交量动态生成 |

### 测试套件

`test_calculations.py` — 28 个测试，5 个测试类：
- `TestProfitFormat` — 盈亏格式化
- `TestRateCalculation` — 收益率计算
- `TestLayerRatios` — 四层占比（含实盘数据验证）
- `TestDrawdownCheck` — 回撤级别判定
- `TestStopLoss` — -8% 止损触发
- `TestMonthlyOps` — 月度操作计数
- `TestRealPortfolioData` — 实盘数据集成测试

运行：`python test_calculations.py`

### Git 版本控制

- 仓库：`C:\Users\lenovo\Desktop\Anchor\.git`
- 首次提交：`fdfed18`
- .gitignore 排除：缓存、生成文件、__pycache__

### 文档清理

- v3.1/v3.2 规则手册 → `01-规则手册/归档/`
- 仅保留 v3.3 为活跃版本

### 错误处理改善

- sync_all.py：logging 替代 print，异常不静默
- rebuild.py：JSON 格式错误时 log.error + exit
- 日志文件：`05-脚本工具/rebuild.log`、`sync_all.log`

**Why**: 系统从手动编辑 JSON 起步，代码随需求增长变得臃肿、硬编码多、无测试、无版本控制。这次是 agent-skills 插件的实战应用。

**How to apply**: 
- 修改规则逻辑 → 编辑 `data_processor.py` 的 `generate_rules()`
- 修改看板样式 → 编辑 `rebuild.py` 的 HTML 模板
- 改完代码 → 先跑 `test_calculations.py`，通过再 git commit
- 日常使用命令不变（rebuild.py / sync_all.py）
- 关联记忆：[[project-investment-framework]] [[file-organization-rules]]
