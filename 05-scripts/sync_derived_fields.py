# -*- coding: utf-8 -*-
"""sync_derived_fields.py — 派生字段归一（v4.5.4，2026-09-18）

定位：把 portfolio_data.json 里**可由定义式算出**的标量重算并写回，
让人工彻底退出这些字段的维护环。

缘起（真实缺陷，非假想）：
  `total_hold_pnl_est` 此前**全仓无任何自动写入方** —— 唯一写入者是 `setup.py` 的一次性
  初始化，其余全是**读**（gen_anchor_pro 公开页 / gen_weekly_report 周报 /
  sync_all 日快照 / ai_bridge_sync 信息桥 / stop_profit_backtest 回测脚本，共 5 处），
  且 `00-system/数据更新协议.md` 第 77-78 行的入库字段清单里**没有它**。
  ⇒ 只能靠人工入库时手改。实测漂移史：

      9/1   文件 1970.69  实算 1836.13  差 +134.56
      9/2   文件 1970.69  实算 1590.47  差 +380.22   ← 持续 3 个备份快照
      9/10  一致 / 9/14 一致 / 9/16 一致 / 9/17 一致
      9/18  文件 1175.97  实算 1366.36  差 -190.39   ← 本次入库漏更

  「9/10~9/17 全对」正说明它**确实在被人工维护**，只是**必然周期性漏**
  —— 一个靠人记的字段，其漏更不是意外而是特性。
  ⇒ 定性：**它不是「一个待更新的字段」，而是「一个可派生的标量」**。

处置：
  ① 定义式收敛到 `data_processor.total_hold_pnl()`（单一真源）；
  ② 本脚本按定义式重算写回（`--check` 为只读模式，供测试用）；
  ③ `data_processor.validate_integrity` 新增 **V8 🔴** 断言 —— 顺序护栏：
     本步骤**必须跑在 sync_all 步骤 0「写库自检」之前**，否则 V8 会响。
     「步骤存在」与「步骤在自检之前跑过」是两件事，V8 钉的是后者。

🔴 声张纪律：`changed=True` 时**必须打印 old→new**，不得静默改掉 ——
   **静默自愈与静默漂移是同一个病的两面**。若只在漂移时悄悄修正，
   就没人知道「它曾漂过、漂了多少」，与 v4.5.2「把静默失效变响」同旨。

用法：
  python sync_derived_fields.py --sync     # 重算并写回（sync_all 自动调用）
  python sync_derived_fields.py --check    # 只读比对，不写任何文件
"""

import argparse
import json
import os
import sys
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import paths  # noqa: E402  (Anchor/05-scripts/paths.py —— 数据中心路径单一真源)


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load(path=None) -> dict:
    p = path or paths.DATA_PATH
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def compute(data: dict) -> dict:
    """返回 {字段名: (old, new, changed, delta)}。新增派生字段时在此登记。"""
    from data_processor import sync_total_hold_pnl
    r = sync_total_hold_pnl(data)
    return {"total_hold_pnl_est": (r["old"], r["new"], r["changed"], r["delta"])}


def run(check_only: bool = False, path=None) -> int:
    p = path or paths.DATA_PATH
    try:
        data = load(p)
    except Exception as e:
        print(f"🔴 [{now_str()}] 无法读取 {p}: {e}")
        return 1

    before = json.dumps(data, ensure_ascii=False, sort_keys=True)
    results = compute(data)
    after = json.dumps(data, ensure_ascii=False, sort_keys=True)

    print(f"— 派生字段归一 · data_date={data.get('update_date')} · {'只读比对' if check_only else '重算写回'} —")
    drifted = False
    for name, (old, new, changed, delta) in results.items():
        if changed:
            drifted = True
            d = f"{delta:+.2f}" if isinstance(delta, (int, float)) else "?"
            print(f"  🔧 {name}: {old} → {new}（差 {d}）—— 原值与本字段定义式不符，已按定义式重算")
        else:
            print(f"  ✅ {name}: {new}（与定义式一致，未变）")

    if check_only:
        if drifted:
            print(f"  🔴 存在漂移字段（只读模式不写回）—— 跑 `--sync` 或 rerun sync_all 修复")
            return 1
        return 0

    if before != after:
        # 🔴 必须走 safe_write 门禁（#C1-57 / A9.4）：本模块的「正常写入」若绕过门禁，
        #    每天同步一次就会把 A9.2 推红一次，最后一定演变成关掉断言。
        from safe_write import commit, AuditRejected

        def _apply(d):
            compute(d)          # 原地重算；⛔ 不要 return compute 的 dict，那会整个替换数据
            return None

        # 生产路径必须全量审计；非生产路径（测试 fixture）只跑门禁组 ——
        # 合成的迷你数据跑三口径/台账断言毫无意义，硬跑只会逼人加「跳过审计」的开关。
        is_prod = os.path.abspath(str(p)) == os.path.abspath(str(paths.DATA_PATH))
        try:
            commit(_apply, tag="sync_derived", verbose=False, data_path=p,
                   audit_scope="full" if is_prod else "gate",
                   reason="sync_derived_fields 派生字段归一（total_hold_pnl_est 按定义式重算）")
            print(f"  💾 已写回 {p}（经 safe_write 门禁）")
        except AuditRejected as e:
            print(f"🔴 [{now_str()}] 门禁拒绝写入（原文件未改）：\n{e}")
            return 1
        except Exception as e:
            print(f"🔴 [{now_str()}] 写回失败（原文件未改）: {e}")
            return 1
    else:
        print("  💾 无变化，未改文件")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="派生字段归一")
    ap.add_argument("--sync", action="store_true", help="重算并写回")
    ap.add_argument("--check", action="store_true", help="只读比对，不写任何文件")
    ap.add_argument("--path", default=None, help="指定 JSON 路径（测试隔离用，默认桌面权威文件）")
    a = ap.parse_args()
    if a.sync:
        sys.exit(run(check_only=False, path=a.path))
    elif a.check:
        sys.exit(run(check_only=True, path=a.path))
    else:
        ap.print_help()
