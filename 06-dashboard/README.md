# 📁 06-dashboard · 看板产物层

> **闭环位置**：运营环 ②入库的呈现产物 ＋ 使用入口页。
> **生成方**：`rebuild.py`／`sync_all.py`（⛔ 手工改动会被重建覆盖）。

## 内容
- `daily_hub.html` —— **当日指挥中心**（全部入口一页直达；数据内联，隐私不提交）
- `portfolio_analysis.html`（＋`_example` 脱敏版）、`portfolio_snapshot.json`、`portfolio_holdings.xlsx`、`portfolio_data.json`（副本）
- `decision_dashboard.html`、`decision_log.json`（决策日志正本）
- `board_pct_history.json`（A2 判据缓存，取数层写）、`noise/`（噪声审计数据）
- `backup/`、`*.bak-*`：历史备份

## 约定
- 桌面同名 4 文件是**权威产物**；本目录为副本/归档（`@rebuild` 时同步）
- ⛔ 不得手工编辑本目录 HTML/JSON 产物
