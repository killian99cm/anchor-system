# 📁 05-scripts · 工具链层

> **闭环位置**：运营环 ③派生/自检、④报告、⑥T+3 的全部**载体脚本**。
> **路径真源**：一切路径经 `paths.py`（禁硬编码；`python paths.py --audit` 自查）。

## 按依赖分层（改脚本先看层）
1. **基座**：`paths.py`（路径）→ `trading_calendar.py`（交易日历）→ `rule_keys.py`（阈值单一注册表）
2. **状态层**：`data_processor.py`（**状态合同唯一计算层**）→ `sync_derived_fields.py`
3. **取数层**：`fetch_public.py`（公共兜底）→ `data_source_health.py`（健康矩阵/五跳兜底）→ `data_pipeline.py`（管道+`--verify-codes`）
4. **产线**：`rebuild.py`（看板）→ `sync_all.py`（**总链**）→ `gen_*.py`（报告/看板生成器群）
5. **校验/门禁**：`pre_trade_check.py`（9 项）→ `report_time_check.py`／`report_time_audit.py` → `version_check.py` → `smoke_test.py`
6. **测试**：`test_*.py`（运行 `python test_xxx.py`；smoke 第 7 步批量跑）

## 常用入口
```
python sync_all.py            # 一键全链（含自检/契约/看板/指挥中心）
python data_pipeline.py --check --coverage   # 报告前必跑
python decision_log.py --due / --trigger-lines / --report
python test_rule_gates.py     # 规则门禁回归（含反向断言）
```
> ⚠️ `sync_all.py` 不入 git（改动靠 `AI-Collab/README.md` 记录）；`归档/`＝废弃脚本。
