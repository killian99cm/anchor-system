---
name: auto-use-agent-skills
description: Anchor 系统开发时自动应用 agent-skills 插件的相关技能
metadata: 
  node_type: memory
  type: feedback
  modified: 2026-08-07T10:13:51.552Z
  originSessionId: 9a3d7c25-5603-4c48-b550-8304fca3ed81
---

## Anchor 系统开发 → 自动触发 agent-skills

对 Anchor 系统做以下操作时，**先调用对应的 Skill**，再执行：

| 操作场景 | 自动调用 Skill | 触发条件 |
|------|------|------|
| 修改 rebuild.py / data_processor.py | `code-review-and-quality` | 任何 .py 文件编辑前后 |
| 新增功能（如新指标、新规则） | `planning-and-task-breakdown` → `incremental-implementation` | 新增 >20 行代码 |
| 改完代码 | `test-driven-development` | 自动跑 `test_calculations.py` |
| 简化/重构 | `code-simplification` | 发现重复代码或过长函数 |
| 修改规则手册 | `documentation-and-adrs` | 规则变更时写 ADR |
| 提交代码 | `git-workflow-and-versioning` | 改完代码要提交时 |
| 遇到 bug / 数据异常 | `debugging-and-error-recovery` | 报错或数据不一致时 |
| 准备新增数据源或 API | `api-and-interface-design` | 接入新数据时 |

### 默认工作流

```
修改代码 → code-review-and-quality（审查）
       → test-driven-development（跑测试）
       → git-workflow-and-versioning（提交）
```

### 不适用场景

- 仅更新 portfolio_data.json 数值（纯数据，不涉及代码）
- 仅运行 mx-data 获取行情
- 仅生成研究报告

**Why**: agent-skills 已安装但需要主动触发。建立自动映射避免每次手动说"用某某skill"。这是用户反馈 "在以后可以用到这个skills时自动使用" 的落地。

**How to apply**: 每次对 Anchor 代码做修改时，在动手前检查本表，匹配则先 Skill 调用再执行。关联记忆：[[anchor-system-optimization]] [[project-investment-framework]]
