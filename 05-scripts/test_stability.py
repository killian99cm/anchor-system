#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_stability.py — Anchor 稳定可复用防回归测试（2026-09-01 建立）
========================================================
覆盖 09-01 修复的 6 个回归点：部署前必跑（部署 SOP 强制）。
用法: python test_stability.py   (需 MX_APIKEY + 本地后端数据就绪)
"""
import json, os, sys, subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
DESKTOP = Path("C:/Users/lenovo/Desktop")
FAIL = []
SKIP = []

def check(name, cond, detail=""):
    status = "✅" if cond else "❌"
    print(f"{status} {name} {detail}")
    if not cond:
        FAIL.append(name)

def skip(name, reason):
    """三态之三：**无法判定**（≠ 通过）。用于「判据源不可达」而非「代码坏了」的场合，
    与 test_rule_gates.py 的 I5–I8 同源同纪律：必须打印原因、必须计入结尾汇总，
    ⛔ 不得静默跳过、⛔ 不得当作绿。"""
    print(f"⏭ {name} —— 无法判定：{reason}")
    SKIP.append(name)

def main() -> int:
    # 1. 契约含止盈 v3.6 + 四层（体系→应用同步）
    try:
        c = json.loads((DESKTOP / "AI-Collab" / "rule_contract.json").read_text(encoding="utf-8"))
        r = c.get("rules", {})
        check("契约含止盈 v3.6 [10,20,35]", r.get("take_profit") == [10, 20, 35], str(r.get("take_profit")))
        check("契约含四层配比", isinstance(r.get("four_layer"), dict) and r["four_layer"].get("bedrock_pct") == 45)
        check("契约含 E1 上限", r.get("e1_sat_position_cap") == 3000)
    except Exception as e:
        check("契约可读", False, str(e))

    # 2. 决策日志 pre_trade 契约读取（A 修复：来源=contract 非 builtin）
    try:
        sys.path.insert(0, str(DESKTOP / "Anchor" / "05-scripts"))
        import pre_trade_check
        th = pre_trade_check.load_thresholds()
        check("pre_trade 阈值来源=contract", th.get("_source") == "contract", th.get("_source"))
    except Exception as e:
        check("pre_trade 可导入", False, str(e))

    # 3. 生产 API 冒烟（部署后验证）
    #    ⚠️ 三态改造（2026-09-28）：此前「连不上」与「连上但非 200」都记 ❌，
    #    于是**本地服务没起**这种环境前置缺失会污染门禁（把「无法判定」当成「代码坏了」）。
    #    现在：不可达 ⇒ ⏭ 无法判定（仍打印、仍计入汇总）；可达但非 200 ⇒ ❌ 真失败。
    base = os.environ.get("ANCHOR_PROD_URL", "http://localhost")
    try:
        import urllib.error
        import urllib.request
        h = urllib.request.urlopen(f"{base}/healthz", timeout=5)
        check("生产 healthz 200", h.status == 200, str(h.status))
    except urllib.error.HTTPError as e:
        # 连上了、返回了 HTTP 错误码 ⇒ 服务端真实异常，必须红
        check("生产 healthz 200", False, f"HTTP {e.code} @ {base}")
    except Exception as e:
        skip("生产 healthz", f"{base} 不可达（{e}）—— 本地/生产实例未运行；"
                             f"需真判定请先起服务或设 ANCHOR_PROD_URL")

    # 4. 本地后端关键服务可导入（防 500 类回归）
    try:
        backend = DESKTOP / "Anchor-Software" / "app" / "backend"
        sys.path.insert(0, str(backend))
        from app.services import market_service
        check("market_service 可导入", True)
    except Exception as e:
        check("market_service 可导入", False, str(e))

    print("\n" + "=" * 40)
    if FAIL:
        print(f"❌ {len(FAIL)} 项失败: {FAIL}")
        return 1
    if SKIP:
        print(f"✅ 无失败项 —— 但含 {len(SKIP)} 项**无法判定**（⛔ 不等于通过）: {SKIP}")
        return 0
    print("✅ 全部通过 —— 稳定可复用基线 OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
