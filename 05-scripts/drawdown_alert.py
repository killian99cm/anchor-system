#!/usr/bin/env python3
"""
Anchor 回撤预警器 (短板3)
每日运行，对比当前总资产 vs 基准 peak_assets，触发 -5%/-10%/-15% 线预警。
规则依据：规则手册 v3.3 第四章 §4.1

用法:
    python drawdown_alert.py                # 正常检查
    python drawdown_alert.py --json         # JSON 输出（供外部程序）
    python drawdown_alert.py --check        # 返回码 2=触发红线 1=黄线 0=安全
退出码: 0 安全 / 1 黄线(-5%但未到-10%) / 2 红线(-10%或更深) / 3 数据缺失
"""
import json
import sys
from pathlib import Path

# 强制 UTF-8 输出，避免 Windows GBK 终端无法编码中文/emoji/¥
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import paths
DESKTOP = paths.DESKTOP
DATA_PATH = paths.DATA_PATH

from data_processor import process_all


def load():
    with open(DATA_PATH, encoding='utf-8') as f:
        return json.load(f)


def main():
    try:
        data = load()
        embed = process_all(data)
    except Exception as e:
        print(f"❌ 数据缺失或无法计算：{e}")
        sys.exit(3)

    total = embed.get('total', 0)
    state = embed.get('drawdown_state', {})
    peak = state.get('peak_assets', 0)
    peak_note = state.get('peak_note', '')
    dd_pct = state.get('dd_pct', 0)
    level = state.get('dd_level', 'safe')
    line = state.get('triggered_line')
    action = state.get('action')
    lines = state.get('lines', {})
    cushion = state.get('safe_cushion', 0)

    if '--json' in sys.argv:
        out = {
            "total": round(total, 2),
            "peak": round(peak, 2),
            "dd_pct": round(dd_pct, 2),
            "level": level,
            "triggered": [line, action] if line else None,
            "safe_cushion": round(cushion, 2),
            "lines": lines,
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
            print(f"  ✅ 安全区：距 -5% 线还有 ¥{cushion:,.0f}")
            print(f"     -5% 线: ¥{lines.get('minus5', peak*0.95):,.0f} | -10%: ¥{lines.get('minus10', peak*0.90):,.0f} | -15%: ¥{lines.get('minus15', peak*0.85):,.0f}")
        elif level == "amber":
            print(f"  🟡 触发 {line}% 回撤线！")
            print(f"     行动: {action}")
        else:
            print(f"  🔴 触发 {line}% 回撤线！")
            print(f"     行动: {action}")
            print("     ⚠️ 请立即按规则执行减仓！")

    if '--check' in sys.argv:
        sys.exit(2 if level == "red" else (1 if level == "amber" else 0))
    sys.exit(0)


if __name__ == '__main__':
    main()
