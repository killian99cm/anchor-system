# Anchor

Anchor 是一套规则驱动的个人投资管理系统，围绕四层金字塔、数据处理链路和零依赖 HTML 看板构建。

它的目标是帮助你：
- 维持压舱石 / 核心增长 / 卫星进攻 / 现金预备四层配置
- 把投资规则变成可执行的检查
- 用本地 `portfolio_data.json` 生成私有看板
- 用脱敏示例数据发布 GitHub Pages 公开页

## 公开与私有的边界

- **本地私有工作区**：`00-system/`、`01-rules/`、`02-strategy/`、`03-analysis/`、`04-reviews/`、`07-memory/` 以及你本机的 `portfolio_data.json`
- **GitHub 公共仓库**：只保留代码、公开文档和脱敏示例
- **公开页面**：使用 `06-dashboard/portfolio_data_example.json` 和 `08-website/anchor-pro.html`

## 快速开始

1. 克隆仓库
2. 把 `06-dashboard/portfolio_data_example.json` 复制成你本地的 `portfolio_data.json`
3. 用自己的持仓修改本地文件
4. 运行：

```bash
python "05-scripts/rebuild.py"
```

5. 打开桌面的 `portfolio_analysis.html`

## 日常使用流程

- **更新今日数据**：更新本地持仓数据后执行 `rebuild.py`
- **仓位点检**：交易前检查层级占比、冻结状态、回撤和规则
- **生成周报**：从本地数据生成周报
- **月度归因**：回顾月度收益和规则执行结果

## 公开页面

- **示例首页**：`06-dashboard/portfolio_analysis_example.html`
- **体系总览**：`08-website/anchor-pro.html`

## 本地运行的脚本

- `05-scripts/data_processor.py`：计算状态、风险、回撤和层级合同
- `05-scripts/rebuild.py`：生成私有看板
- `05-scripts/gen_anchor_pro.py`：把脱敏数据注入公开页
- `05-scripts/smoke_test.py`：检查输出完整性和隐私边界

## 说明

- 仓库里不会保留真实持仓文件。
- 真实持仓只放在本机的 `portfolio_data.json`。
- 公开示例数据仅用于演示结构，不代表你的真实组合。
