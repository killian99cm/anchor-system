#!/usr/bin/env python3
"""
Anchor 回撤预警器 (短板3)
每日运行，对比当前总资产 vs 基准 peak_assets，触发 -5%/-10%/-15% 线预警。
规则依据：规则手册 v3.3 第四章 §4.1

用法:
    python drawdown_alert.py                # 正常检查
    python drawdown_alert.py --json         # JSON 输出（供外部程序）
    python drawdown_alert.py --check        # 返回码 2=触发红线 1=黄线 0=安全
退出码: 0 安全 / 1 黄线(>=5%但<10%) / 2 红线(>=10%) / 3 数据缺失
"""
import json
import sys
from pathlib import Path

# 强制 UTF-8 输出，避免 Windows GBK 终端无法编码中文/emoji/¥
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DESKTOP = Path(r"C:\Users\lenovo\Desktop")
DATA_PATH = DESKTOP / "portfolio_data.json"

# 回撤线定义（百分比绝对值）
LINES = [(5, "🟡 卫星仓位减半，不开新仓"),
         (10, "🔴 卫星全部清仓，只留压舱石+核心增长"),
         (15, "🔴🔴 核心增长也减1/3，持有现金")]


def load():
    with open(DATA_PATH, encoding='utf-8') as f:
        return json.load(f)


def main():
    data = load()
    total = data.get('total_assets', 0)
    peak = data.get('_meta', {}).get('peak_assets', 0)
    peak_note = data.get('_meta', {}).get('peak_note', '')

    if not total or not peak:
        print("❌ 数据缺失：total_assets 或 peak_assets 为空")
        sys.exit(3)

    dd_pct = (total - peak) / peak * 100
    dd_abs = abs(dd_pct)

    # 判定级别
    level = "safe"
    triggered_line = None
    for pct, action in LINES:
        if dd_abs >= pct:
            level = "red" if pct >= 10 else "amber"
            triggered_line = (pct, action)
            break

    # 输出
    if '--json' in sys.argv:
        out = {
            "total": round(total, 2),
            "peak": round(peak, 2),
            "dd_pct": round(dd_pct, 2),
            "level": level,
            "triggered": triggered_line,
            "safe_cushion": round(total - peak * 0.95, 2),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        sign = "+" if dd_pct >= 0 else ""
        print("=" * 50)
        print("Anchor 回撤预警")
        print("=" * 50)
        print(f"  当前总资产: ¥{total:,.0f}")
        print(f"  基准(peak): ¥{peak:,.0f}  {peak_note}")
        print(f"  回撤幅度:   {sign}{dd_pct:.2f}%")
        print("-" * 50)
        if level == "safe":
            cushion = total - peak * 0.95
            print(f"  ✅ 安全区：距 -5% 线还有 ¥{cushion:,.0f}")
            print(f"     -5% 线: ¥{peak*0.95:,.0f} | -10%: ¥{peak*0.90:,.0f} | -15%: ¥{peak*0.85:,.0f}")
        elif level == "amber":
            print(f"  🟡 触发 {triggered_line[0]}% 回撤线！")
            print(f"     行动: {triggered_line[1]}")
        else:
            print(f"  🔴 触发 {triggered_line[0]}% 回撤线！")
            print(f"     行动: {triggered_line[1]}")
            print("     ⚠️ 请立即按规则执行减仓！")

    # 退出码
    if '--check' in sys.argv:
        sys.exit(2 if level == "red" else (1 if level == "amber" else 0))
    sys.exit(0)


if __name__ == '__main__':
    main()
