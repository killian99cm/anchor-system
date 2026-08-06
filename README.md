<div align="center" id="anchor">

<a href="https://github.com/killian99cm/anchor-system" title="Anchor">
  <img src="https://img.shields.io/badge/⚓_Anchor-v3.3-4d8af0?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0xMiAyQzYuNDggMiAyIDYuNDggMiAxMnM0LjQ4IDEwIDEwIDEwIDEwLTQuNDggMTAtMTBTMTcuNTIgMiAxMiAyem0wIDNjNC40MSAwIDggMy41OSA4IDhzLTMuNTkgOC04IDgtOC0zLjU5LTgtOCAzLjU5LTggOC04em0wIDJjLTMuMzEgMC02IDIuNjktNiA2czIuNjkgNiA2IDYgNi0yLjY5IDYtNi0yLjY5LTYtNi02em0wIDFjMi43NiAwIDUgMi4yNCA1IDVzLTIuMjQgNS01IDUtNS0yLjI0LTUtNSAyLjI0LTUgNS01em0wIDJjLTEuNjYgMC0zIDEuMzQtMyAzczEuMzQgMyAzIDMgMy0xLjM0IDMtMy0xLjM0LTMtMy0zem0wIDJjLjU1IDAgMSAuNDUgMSAxcy0uNDUgMS0xIDEtMS0uNDUtMS0xIC40NS0xIDEtMXoiLz48L3N2Zz4=" alt="Anchor v3.3" height="36">
</a>

🚀 规则驱动的个人投资管理系统 —— **用规则管住手，用数据代替直觉**

[![GitHub Stars](https://img.shields.io/github/stars/killian99cm/anchor-system?style=flat-square&logo=github&color=yellow)](https://github.com/killian99cm/anchor-system/stargazers)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
[![Version](https://img.shields.io/badge/version-v3.3-blue.svg)](https://github.com/killian99cm/anchor-system)
[![Trades](https://img.shields.io/badge/实盘-109笔-00d69e?style=flat-square)](https://github.com/killian99cm/anchor-system)
[![Period](https://img.shields.io/badge/验证-13个月-f0a830?style=flat-square)](https://github.com/killian99cm/anchor-system)

[![数据源-mxdata](https://img.shields.io/badge/数据源-mx_data_API-4d8af0?style=flat-square)](https://data.eastmoney.com/)
[![看板-零依赖](https://img.shields.io/badge/看板-纯HTML/零依赖-00d69e?style=flat-square)](https://killian99cm.github.io/anchor-system)
[![AI-Claude](https://img.shields.io/badge/AI-Claude-f04668?style=flat-square)](https://claude.ai)
[![自动化-GitHub Actions](https://img.shields.io/badge/自动化-GitHub_Actions-2088FF?style=flat-square&logo=github-actions)](https://github.com/killian99cm/anchor-system/actions)
[![部署-GitHub Pages](https://img.shields.io/badge/演示-GitHub_Pages-4285F4?style=flat-square&logo=github)](https://killian99cm.github.io/anchor-system)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat-square&logo=python)](https://www.python.org/)

</div>

<div align="center">

**中文** | **[English](README-EN.md)**

</div>

> 💡 **这是什么**：一套把投资纪律变成可执行代码的个人系统。不是选股策略、不是 AI 自动交易、不推荐具体产品。

<details>
<summary>🗺️ 点击展开：<strong>项目全景速览</strong></summary>
<br>

| 维度 | 内容 |
|:--|:--|
| 🎯 **目标** | 用规则消除情绪化交易，用量化清单替代直觉决策 |
| 🏗️ **架构** | 四层金字塔（压舱石45% / 核心增长20% / 卫星进攻20% / 现金预备15%） |
| 📜 **规则** | 4条铁律 + 6条永久禁令 + 月度操作限额 + 阶梯止盈 |
| 📊 **数据** | mx-data API → rebuild.py → 双路输出看板（桌面 + 仓库副本） |
| 🤖 **AI** | Claude 辅助：每日复盘、仓位点检、周报生成、月度归因 |
| 🔄 **节奏** | 实时行情 / 每日更新 / 每周点检 / 每月归因 |

</details>

<br>

## 📑 快速导航

<div align="center">

| [🧠 核心理念](#-核心理念) | [📜 规则体系](#-规则体系) | [⚡ 快速开始](#-快速开始) | [📂 目录结构](#-目录结构) | [📊 数据更新](#-数据更新节奏) |
|:---:|:---:|:---:|:---:|:---:|
| [🏗️ 系统架构](#️-系统架构) | [📈 版本演进](#-版本演进) | [🤖 AI 系统](#-ai-分析系统) | [🌐 在线演示](#-在线演示) | [📝 更新日志](#-更新日志) |

</div>

<br>

## ✨ 核心功能

### 🏗️ 四层金字塔体系

```
       ┌──────────────────────────────────┐
 20%   │  🔥 卫星进攻     -8% 硬止损       │  波段交易
       │  行业ETF + 个股   不补仓不转换     │  高赔率下注
       ├──────────────────────────────────┤
 20%   │  🚀 核心增长     定投 + 大跌补仓   │  长期成长
       │  宽基指数 + QDII  低估时逐步建仓   │  穿越周期
       ├──────────────────────────────────┤
 45%   │  🛡️ 压舱石       永远不卖         │  组合基石
       │  债券 + 固收      每季再平衡      │  稳定收益
       ├──────────────────────────────────┤
 15%   │  💰 现金预备     暴跌补仓弹药      │  灵活机动
       │  余额宝/货基     保持流动性       │  等待机会
       └──────────────────────────────────┘
```

| 层级 | 目标 | 仓位 | 管理规则 | 当前品种 |
|:--|:--|:--:|:--|:--|
| 🛡️ 压舱石 | 稳定收益、防回撤 | **45%** | 永远不卖，每季再平衡 | 债券×2 + 黄金 |
| 🚀 核心增长 | 长期增值 | **20%** | 定投为主，大跌补仓 | 混合基金 + 纳指×2 |
| 🔥 卫星进攻 | 波段增强 | **20%** | -8% 硬止损，浮亏不加仓 | 半导体 + 证券 + 创新药 |
| 💰 现金预备 | 流动性 + 抄底 | **15%** | 余额宝/货基，暴跌时动用 | 余额宝 |

> 💡 四层比例每月检查一次，偏离超过 5% 时触发再平衡

### 📜 量化规则引擎

**四条铁律**：

1. **浮亏不加仓** — 只平仓、不补仓、不转换，杜绝越跌越买
2. **-8% 硬止损** — 卫星层触及即砍，不考虑「反弹预期」
3. **72h 冷静期** — 任何买入想法强制冻结 72 小时再执行
4. **阶梯止盈** — +15% 卖 1/3 · +30% 卖 1/2 · +50% 清仓

**六条永久禁令**：

```
🚫 不转换    🚫 不补仓      🚫 不当天换仓
🚫 不碰过剩  🚫 不定投卫星  🚫 不 FOMO 追涨
```

**v3.3 新增过滤器**：

| 过滤器 | 条件 | 效果 |
|:--|:--|:--|
| 🔴 DDX 过滤器 | 半导体 DDX 连 2 日为正 | 才允许补仓 |
| 🔴 纳指溢价率 | 溢价率 ≤ 3% | 才允许建仓场内纳指 |
| 🟡 时间止损 | 买入满 30 天 | 浮亏未改善则清仓 |
| 🟡 月操作限额 | ≤ 4 笔/月 | 超限冻结至下月 |

> 💡 每次操作前跑一遍[持仓全面检查清单](01-规则手册/持仓全面检查清单.md)，红灯不过不操作

### 📊 双路数据看板

`rebuild.py` 一键生成，Desktop + 仓库副本同时输出：

```
portfolio_data.json (唯一可编辑数据源)
        │
        ▼
   rebuild.py ◀── 市场数据自动注入
        │
   ┌────┴────┐
   ▼         ▼
 Desktop/   Anchor/06-看板数据/
 看板HTML    看板HTML (仓库只读副本)
 快照JSON    快照JSON
 Excel       portfolio_data.json
```

> 💡 **数据新鲜度报告**：rebuild 输出含市场数据年龄、规则警报、时间止损倒计时

### 🤖 AI 分析系统

基于 Claude 的智能投资助手，支持自然语言交互：

- **📋 仓位点检**：说"仓位点检"，自动四层占比核对 + 红灯扫描
- **📝 每日复盘**：说"更新今日数据"，mx-data 获取收盘 → 更新 JSON → rebuild
- **📈 周报生成**：说"生成周报"，自动汇总本周操作 + 收益 + 规则触发
- **🔍 月度归因**：说"月度归因"，完整月度收益拆解 + 规则审议 + 版本升级
- **🔄 会话连续性**：说"继续"，读取会话检查点，秒级恢复上次上下文

### 🌐 在线演示看板

GitHub Pages 自动部署，纯 HTML 深色终端风，零外部依赖：

> 📋 **[在线演示 →](https://killian99cm.github.io/anchor-system)** 查看脱敏示例看板

| 看板功能 | 说明 |
|:--|:--|
| 📊 KPI 卡片 | 四层占比、规则状态、版本评分 |
| 🏗️ 金字塔可视化 | 四层比例图形化展示 |
| 🚦 规则检查面板 | 实时显示各规则触发状态 |
| 📈 收益走势图 | 每日 PnL + 大盘叠加对比 |
| ⚠️ 待办追踪 | DDX/溢价率/时间止损倒计时 |

### 🔧 零门槛使用

```bash
# 1. Clone
git clone https://github.com/killian99cm/anchor-system.git
cd anchor-system

# 2. 填入持仓（用编辑器改）
cp 06-看板数据/portfolio_data_example.json portfolio_data.json

# 3. 生成看板
python 05-脚本工具/rebuild.py

# 4. 双击打开
# → portfolio_analysis.html
```

**适用人群**：个人投资者、基金定投用户、想建立交易纪律的新手

**典型场景**：每日收盘更新、每周仓位检查、每月收益归因、新机会评估

<br>

## 📂 目录结构

```
Anchor/
├── 00-系统管理/         数据更新协议 + 会话检查点
├── 01-规则手册/         投资规则 v3.3 + 持仓检查清单 + 股票交易规则
├── 02-策略优化/         历史优化方案、可行性分析
├── 03-分析报告/         板块分析、市场评估、效果对比
├── 04-每日复盘/         深度复盘 + 周报 + 月度归因
├── 05-脚本工具/         rebuild.py · sync_all.py · 仓位计算器
├── 06-看板数据/         HTML看板 + JSON快照（数据不上传）
├── 07-记忆文件/         Claude Memory 持久化备份
├── 08-可视化网站/       Anchor Pro 体系介绍页
└── .github/workflows/   CI 日度检查 + Pages 部署
```

<br>

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────┐
│                    数据采集层                         │
│  mx-data API (主力)  │  AKShare (备用)  │  WebSearch  │
└────────────────────────┬─────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────┐
│                  数据处理层                           │
│  portfolio_data.json ──→ rebuild.py ──→ 双路输出     │
│  (唯一可编辑源)          (核心引擎)      Desktop+副本  │
└────────────────────────┬─────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ HTML看板 │  │ JSON快照 │  │  Excel   │
    │ 深色终端 │  │ 双副本   │  │ 桌面版   │
    └──────────┘  └──────────┘  └──────────┘
          │
          ▼
┌──────────────────────────────────────────────────────┐
│                  AI 分析层 (Claude)                    │
│  每日复盘 │ 仓位点检 │ 周报生成 │ 月度归因 │ 机会评估  │
└──────────────────────────────────────────────────────┘
```

<br>

## 📊 数据更新节奏

| 频率 | 操作 | 触发方式 | 命令 |
|:--:|------|------|:--|
| ⚡ 实时 | 查询行情/DDX/溢价率 | `mx-data` API | `用 mx-data 获取XXX` |
| 📅 每日 | 更新收盘数据 → rebuild | 手动或 CI | `更新今日数据` |
| 📋 每周 | 仓位点检 + 周报 | 对 Claude 说 | `仓位点检` / `生成周报` |
| 📈 每月 | 月度归因 + 规则审议 | 对 Claude 说 | `月度归因` |

<br>

## 📈 版本演进

| 版本 | 日期 | 里程碑 |
|:--|:--|:--|
| v0.1 | 2025.06 | 初始持仓记录，手工 Excel |
| v1.0 | 2025.08 | 三层结构 + 基础买卖规则 |
| v2.0 | 2025.11 | 四层金字塔 + 双轨策略成型 |
| v2.5 | 2026.03 | FDIS 引入 + 首版正式规则手册 |
| v3.0 | 2026.05 | 全面重构：负面清单 + 进化机制 |
| v3.1 | 2026.06 | AI 管理系统 + Claude Memory 体系 |
| v3.2 | 2026.07 | DDX 过滤器 + 月度归因体系 |
| **v3.3** | **2026.08** | **双路数据输出 + 会话连续性 + 四级数据协议** |

> 💡 详细版本变更见 [CHANGELOG.md](CHANGELOG.md)

<br>

## 📝 更新日志

### 2026/08/06 - v3.3

**🎉 系统全面升级**

1. **数据通道打通**
   - rebuild.py 双路输出：Desktop + Anchor/06-看板数据/ 同时写入
   - portfolio_data.json 自动同步：Desktop(主) → Anchor(只读副本)
   - sync_all.py 完全重写，修复所有路径引用

2. **可视化升级**
   - 看板 HTML Premium 深色终端风重写
   - anchor-pro.html 数据驱动重写（27.8KB → 31.5KB）
   - 三层 HTML 导航链接全部打通

3. **新增系统文件**
   - `数据更新协议.md`：实时/每日/每周/每月四级更新体系
   - `会话检查点.md`：跨对话状态恢复，新对话秒级续接
   - `数据新鲜度报告`：rebuild 输出含市场数据年龄 + 规则警报

4. **GitHub 化**
   - .gitignore 排除 5 个敏感数据文件
   - git rm --cached 脱敏已跟踪文件
   - GitHub Actions Pages 自动部署
   - 开源社区文件全补全（CONTRIBUTING / CODE_OF_CONDUCT / SECURITY / CHANGELOG）

5. **文档更新**
   - ANCHOR_体系总览 v3.2 → v3.3
   - 持仓全面检查清单 / 股票交易规则 更新至 8/6

**🔧 升级说明**（已有本地部署用户）：
- 必须更新：`rebuild.py`、`sync_all.py`、`06-看板数据/` 下所有文件
- 可选更新：README.md、.gitignore

<details>
<summary>👉 点击展开：<strong>历史更新</strong></summary>

### 2026/07 - v3.2

- DDX 过滤器：半导体补仓需 DDX 连 2 日为正
- 纳指 ETF 溢价率规则：溢价率 ≤ 3% 才建仓
- 月度归因体系完善
- GitHub Actions 日度 CI

### 2026/06 - v3.1

- AI 投资管理系统架构
- Claude Memory 持久化体系
- 07-记忆文件/ 目录建立

### 2026/05 - v3.0

- 四层金字塔结构成型
- 负面清单机制
- 规则进化机制
- 投资规则手册正式版

### 2025.06~2026.03 - v0.1~v2.5

- v0.1: 初始持仓记录（手工 Excel）
- v1.0: 三层结构 + 基础买卖规则
- v2.0: 四层金字塔 + 双轨策略
- v2.5: FDIS 引入 + 首版正式规则手册

</details>

<br>

## 🙏 致谢

感谢以下工具和服务使本项目成为可能：

- **数据支持** — [东方财富妙想 AI](https://data.eastmoney.com/) 提供 mx-data API，实时准确的 A 股行情数据
- **AI 支持** — [Claude](https://claude.ai) 提供复盘分析、规则优化、报告生成的智能辅助
- **基础设施** — [GitHub](https://github.com) 免费提供 Actions 自动化和 Pages 部署
- **启发项目** — [TrendRadar](https://github.com/sansan0/TrendRadar) 优秀的多平台聚合 + AI 分析架构

<br>

## 🤝 贡献

欢迎提 Issue 和 PR！贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

- 🐛 发现 Bug？开 [Bug Report](https://github.com/killian99cm/anchor-system/issues/new?template=bug_report.md)
- 💡 有改进想法？开 [Feature Request](https://github.com/killian99cm/anchor-system/issues/new?template=feature_request.md)
- 🔧 提交代码？Fork → Feature Branch → PR

> ⚠️ **严禁提交真实持仓数据**。`.gitignore` 已配置，用 `portfolio_data_example.json` 测试。

<br>

## ⚠️ 免责声明

**不构成投资建议。** 这是一个个人学习项目，记录了一个自学投资者的框架迭代过程。历史表现不代表未来收益。投资有风险，入市需谨慎。请勿直接跟单。

## 📄 License

MIT © [killian99cm](https://github.com/killian99cm) — 框架代码自由使用，填入你自己的持仓数据即可。
