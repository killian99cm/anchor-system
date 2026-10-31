# 📁 05-scripts · 工具链层

> **闭环位置**：运营环 ③派生/自检、④报告、⑥T+3 的全部**载体脚本**。
> **路径真源**：一切路径经 `paths.py`（禁硬编码；`python paths.py --audit` 自查）。

## 按依赖分层（改脚本先看层）
1. **基座**：`paths.py`（路径）→ `trading_calendar.py`（交易日历）→ `rule_keys.py`（阈值单一注册表）
2. **状态层**：`data_processor.py`（**状态合同唯一计算层**）→ `sync_derived_fields.py`
3. **取数层**：`fetch_public.py`（公共兜底）→ `data_source_health.py`（健康矩阵/五跳兜底）→ `data_pipeline.py`（管道+`--verify-codes`）
4. **产线**：`rebuild.py`（看板）→ `sync_all.py`（**总链**）→ `gen_*.py`（报告/看板生成器群）
5. **校验/门禁**：`pre_trade_check.py`（9 项）→ `report_time_check.py`／`report_time_audit.py` → `version_check.py` → `smoke_test.py`
   - 🔴 **v4.5 新增（2026-10-31）账本不变量层**：`ledger_audit.py`（37 项断言／9 组）＋ `safe_write.py`（唯一写入口，FAIL 即回滚）＋ `evidence_index.py`（多模式检索，防「找不到＝不存在」）
6. **测试**：`test_*.py`（运行 `python test_xxx.py`；smoke 第 7 步批量跑）

## 常用入口
```
python sync_all.py            # 一键全链（含自检/契约/看板/指挥中心/账本审计）
python data_pipeline.py --check --coverage   # 报告前必跑
python ledger_audit.py        # 账本 37 项不变量，FAIL 时任何结论都不可引用
python ledger_audit.py --fix-hints   # 失败时附修复建议
python safe_write.py --check  # 写前体检（等价 ledger_audit，供门禁调用）
python evidence_index.py --month 2026-10   # 某月证据覆盖（补台账前必跑）
python test_ledger_audit.py   # 17 项故障注入，改审计逻辑后必跑
python decision_log.py --due / --trigger-lines / --report
python test_rule_gates.py     # 规则门禁回归（含反向断言）
```

## 写数据必须走门禁（#C1-57）
```python
from safe_write import commit

def mutate(data):
    data['total_assets'] = 47114.14
    ...

commit(mutate, reason="#C1-53 更新 10/22 在途")   # FAIL 会抛 AuditRejected 并回滚
```
⛔ 禁止再对 `portfolio_data.json` 直接 `json.dump`。
> ⚠️ `sync_all.py` 不入 git（改动靠 `AI-Collab/README.md` 记录）；`归档/`＝废弃脚本。
