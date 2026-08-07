#!/usr/bin/env python3
"""
Anchor smoke 测试 — 端到端完整性验证 (短板1)
在 rebuild.py 运行后，验证生成产物是否完整、关键数据是否嵌入。

用法: python smoke_test.py
"""
import json
import os
import re
import sys
import subprocess
from pathlib import Path

DESKTOP = Path(r"C:\Users\lenovo\Desktop")
ANCHOR = DESKTOP / "Anchor"
SCRIPTS = ANCHOR / "05-scripts"
PY = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python"

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def main():
    print("=" * 60)
    print("Anchor smoke 测试 — 端到端产物完整性")
    print("=" * 60)

    # 0. 确保最新产物（先跑 rebuild）
    print("\n[0] 运行 rebuild.py ...")
    r = subprocess.run(
        f'"{PY}" "{SCRIPTS / "rebuild.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=120
    )
    check("rebuild.py 退出码 0", r.returncode == 0, f"(rc={r.returncode})")

    # 1. 源 JSON
    print("\n[1] 源数据 portfolio_data.json")
    data_path = DESKTOP / "portfolio_data.json"
    check("portfolio_data.json 存在", data_path.exists())
    if data_path.exists():
        with open(data_path, encoding='utf-8') as f:
            data = json.load(f)
        check("total_assets 为正数", data.get('total_assets', 0) > 0,
              f"(total={data.get('total_assets')})")
        check("holdings_summary 非空", len(data.get('holdings_summary', [])) > 0)
        check("_meta.peak_assets 存在", data.get('_meta', {}).get('peak_assets') is not None,
              "回撤基准缺失!")

    # 2. HTML 产物
    print("\n[2] portfolio_analysis.html")
    html_path = DESKTOP / "portfolio_analysis.html"
    check("HTML 存在", html_path.exists())
    if html_path.exists():
        html = html_path.read_text(encoding='utf-8')
        check("HTML 大小 > 20KB", len(html) > 20000, f"({len(html)} bytes)")
        check("HTML 含峰值数据", "peak_assets" in html)
        check("HTML 含今日结论", '"today"' in html)
        check("HTML 含操作计数", "aug_ops" in html)
        check("HTML 含四层数据", '"bedrock"' in html and '"sat"' in html)
        check("HTML 含 chart 数据", '"chart"' in html)
        # 提取 embed 检查关键数值
        m = re.search(r'var D = (\{.*?\});\n', html, re.DOTALL)
        if m:
            try:
                embed = json.loads(m.group(1))
                check("embed.total ≈ total_assets", abs(embed['total'] - data.get('total_assets', 0)) < 100,
                      f"(embed={embed['total']} vs json={data.get('total_assets')})")
                check("embed.dd_pct 合理范围", -50 < embed.get('dd_pct', 0) < 50,
                      f"(dd_pct={embed.get('dd_pct')})")
            except json.JSONDecodeError:
                check("embed JSON 可解析", False, "HTML 内嵌 JSON 解析失败!")

    # 3. 快照
    print("\n[3] portfolio_snapshot.json")
    snap_path = DESKTOP / "portfolio_snapshot.json"
    check("快照存在", snap_path.exists())
    if snap_path.exists():
        with open(snap_path, encoding='utf-8') as f:
            snap = json.load(f)
        check("快照 total_assets 一致", abs(snap.get('total_assets', 0) - data.get('total_assets', 0)) < 100,
              f"(snap={snap.get('total_assets')} vs json={data.get('total_assets')})")
        check("快照 layer_summary 四层完整", all(k in snap.get('layer_summary', {}) for k in ['bedrock', 'core', 'sat', 'cash']))

    # 4. Excel 产物
    print("\n[4] portfolio_holdings.xlsx")
    xlsx_path = DESKTOP / "portfolio_holdings.xlsx"
    xlsx_anchor = ANCHOR / "06-dashboard" / "portfolio_holdings.xlsx"
    check("Excel 存在(桌面)", xlsx_path.exists())
    check("Excel 存在(Anchor)", xlsx_anchor.exists())
    if xlsx_path.exists():
        check("Excel 大小 > 10KB", xlsx_path.stat().st_size > 10000, f"({xlsx_path.stat().st_size} bytes)")

    # 5. 副本一致性
    print("\n[5] 桌面 vs Anchor 副本")
    check("HTML 副本一致", (DESKTOP / "portfolio_analysis.html").stat().st_size == (ANCHOR / "06-dashboard" / "portfolio_analysis.html").stat().st_size)
    check("快照副本一致", (DESKTOP / "portfolio_snapshot.json").stat().st_size == (ANCHOR / "06-dashboard" / "portfolio_snapshot.json").stat().st_size)

    # 6. 运行核心测试
    print("\n[6] 核心计算测试 test_calculations.py")
    r2 = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_calculations.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    check("核心测试通过", "ALL TESTS PASSED" in r2.stdout, f"(rc={r2.returncode})")

    print("\n" + "=" * 60)
    print(f"结果: {PASS} 通过 / {FAIL} 失败")
    if FAIL == 0:
        print("SMOKE TEST PASSED — 产物完整，数据一致")
    else:
        print(f"SMOKE TEST FAILED — {FAIL} 项异常，请检查")
        sys.exit(1)
    print("=" * 60)


if __name__ == '__main__':
    main()
