# 📁 08-website · 公开页层（脱敏）

> **闭环位置**：对外输出（体系介绍/业绩页），与私有看板严格隔离。
> **生成方**：`05-scripts/gen_anchor_pro.py`（CI 校验防漂移：生成物必须与提交一致）。

## 内容
- `anchor-pro.html` / `anchor-pro-v2.html` / `track-record.html`
- `diagrams/`（体系图集）、`design-system/`

## 🔴 铁律
- **只用脱敏示例数据**（`portfolio_data_example.json`）；⛔ 严禁真实持仓/基准写入
- 生成后跑 `test_anchor_pro_privacy.py`（隐私护栏回归）；CI `git diff --exit-code` 防手工漂移
