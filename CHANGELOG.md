# Changelog

所有值得记录的变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [v3.3] — 2026-08-06

### 新增
- 数据更新协议：实时/每日/每周/每月四级更新体系
- 会话检查点：跨对话状态恢复机制
- GitHub Pages 自动部署工作流
- `portfolio_analysis_example.html` 脱敏示例看板
- `portfolio_data_example.json` 脱敏示例数据
- `.gitignore` 敏感数据排除规则
- 数据新鲜度报告（rebuild.py 输出含市场数据年龄 + 规则警报）

### 变更
- rebuild.py 双路输出：Desktop + Anchor/06-看板数据/ 同时写入
- sync_all.py 完全重写，修复所有路径引用
- README.md 全面升级（badges + 架构图 + 快速开始）
- anchor-pro.html 数据驱动重写（27.8KB → 31.5KB）
- CLAUDE.md 重写为系统入口点

### 修复
- `06-看板数据/portfolio_analysis.html` 数据断连 → 双路输出
- `06-看板数据/portfolio_data.json` 旧数据差¥5,240 → 自动同步
- GitHub Actions CI 三处阻断错误（checkout@v5→v4, setup-python@v6→v5, 路径）
- anchor_calculator.html CSS 变量 `--text3` 未定义

### 移除
- `rebuild_anchor.py`（死代码）
- `portfolio_reference.csv`（死代码）
- `anchor-dark.html`、`anchor-glass.html`、`anchor-light.html`（过期可视化）
- 旧版 README（main 分支残留）

### 安全
- GitHub 脱敏：git rm --cached 5 个敏感文件
- .gitignore 防止重新提交

---

## [v3.2] — 2026-07

### 新增
- DDX 过滤器：半导体补仓需 DDX 连 2 日为正
- 纳指 ETF 溢价率规则：溢价率 ≤3% 才建仓
- 月度归因体系
- GitHub Actions 日度 CI

### 变更
- 投资规则手册 v3.1 → v3.2

---

## [v3.1] — 2026-06

### 新增
- AI 投资管理系统架构
- Claude Memory 持久化体系
- 07-记忆文件/ 目录

---

## [v3.0] — 2026-05

### 新增
- 四层金字塔结构
- 负面清单机制
- 规则进化机制
- 投资规则手册正式版

---

## [v2.x] — 2025.11 ~ 2026.03

### v2.5 (2026.03)
- FDIS 框架引入
- 正式规则手册首版

### v2.0 (2025.11)
- 四层结构成型
- 双轨策略

---

## [v1.0] — 2025.08

### 新增
- 三层结构
- 基础买卖规则

---

## [v0.1] — 2025.06

### 新增
- 初始持仓记录（手工 Excel）
