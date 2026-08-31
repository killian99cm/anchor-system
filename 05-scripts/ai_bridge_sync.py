# -*- coding: utf-8 -*-
"""
ai_bridge_sync.py — 双 AI 信息桥同步脚本（WorkBuddy ⇄ Claude）

用法：
    python ai_bridge_sync.py --push    # WorkBuddy→Claude：刷新 wb_state.md 数据区
    python ai_bridge_sync.py --pull    # Claude→WorkBuddy：聚合 claude_state.md 摘要并打印
    python ai_bridge_sync.py --status  # 查看桥两侧状态（最近更新时间）

原则：只更新自己一方（WorkBuddy 写 wb_state.md + sync_log.md），
      不触碰 claude_state.md 内容（Claude 专属）；数据只读 portfolio_data.json。
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

# ---------- 路径 ----------
BRIDGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "00-system", "ai-bridge")
BRIDGE_DIR = os.path.normpath(BRIDGE_DIR)
WB_STATE = os.path.join(BRIDGE_DIR, "wb_state.md")
CLAUDE_STATE = os.path.join(BRIDGE_DIR, "claude_state.md")
SYNC_LOG = os.path.join(BRIDGE_DIR, "sync_log.md")
PORTFOLIO_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "portfolio_data.json")
PORTFOLIO_JSON = os.path.normpath(PORTFOLIO_JSON)


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def log_sync(direction: str, summary: str) -> None:
    """sync_log.md 只追加"""
    entry = f"- {now_str()} | {direction} | {summary}\n"
    with open(SYNC_LOG, "a", encoding="utf-8") as f:
        f.write(entry)


def read_portfolio() -> dict:
    """只读 portfolio_data.json，失败返回空 dict"""
    try:
        with open(PORTFOLIO_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] 读取 portfolio_data.json 失败: {e}")
        return {}


def build_data_section(p: dict) -> str:
    """从 portfolio_data.json 生成数据状态表格"""
    market = p.get("market", {})
    rows = [
        ("数据日期", p.get("update_time", "未知").split("（")[0] if p.get("update_time") else "未知"),
        ("总资产", f"¥{p.get('total_assets', '—'):,}" if isinstance(p.get("total_assets"), (int, float)) else str(p.get("total_assets", "—"))),
        ("基金账户", f"¥{p.get('fund_account', '—'):,}" if isinstance(p.get("fund_account"), (int, float)) else "—"),
        ("股票账户", f"¥{p.get('stock_account', '—'):,}" if isinstance(p.get("stock_account"), (int, float)) else "—"),
        ("余额宝", f"¥{p.get('yuebao', '—'):,}" if isinstance(p.get("yuebao"), (int, float)) else "—"),
        ("总持有盈亏(估)", f"¥{p.get('total_hold_pnl_est', '—'):,}" if isinstance(p.get("total_hold_pnl_est"), (int, float)) else "—"),
        ("上证", f"{market.get('close', '—')}（{market.get('change', '—')}）"),
    ]
    lines = ["| 项目 | 值 |", "|------|-----|"]
    for k, v in rows:
        lines.append(f"| {k} | {v} |")
    return "\n".join(lines)


def replace_section(md: str, marker: str, new_content: str) -> str:
    """用 ### marker 锚点替换/插入区块"""
    pattern = re.compile(rf"({marker}.*?)(?=\n## |\Z)", re.S)
    if pattern.search(md):
        return pattern.sub(lambda m: m.group(1) + new_content, md, count=1)
    return md


def do_push() -> None:
    p = read_portfolio()
    data_table = build_data_section(p)
    ts = now_str()

    if not os.path.exists(WB_STATE):
        print("[ERROR] wb_state.md 不存在，请先初始化桥文件")
        sys.exit(1)

    with open(WB_STATE, encoding="utf-8") as f:
        md = f.read()

    # 1) 刷新「最近更新」时间戳
    md = re.sub(r"- \d{4}-\d{2}-\d{2} \d{2}:\d{2} \| 信息桥.*",
                f"- {ts} | 信息桥自动同步（ai_bridge_sync --push）", md, count=1)

    # 2) 刷新数据状态表格（保留头部行，替换数据行）
    md = re.sub(r"(?<=\| 项目 \| 值 \|\n\|------\|\n)(.*?)(?=\n\n)", data_table.replace("\n", "\n") + "\n", md, count=1, flags=re.S)

    with open(WB_STATE, "w", encoding="utf-8") as f:
        f.write(md)

    log_sync("WB→Claude", f"推送 wb_state.md（数据日期 {p.get('update_time', '未知')[:16]}）")
    print(f"[OK] {ts} wb_state.md 已刷新")
    print(data_table)


def do_pull() -> None:
    """聚合 Claude 侧状态并打印"""
    print("=" * 60)
    print(f"📥 Claude 侧状态聚合（{now_str()}）")
    print("=" * 60)
    if os.path.exists(CLAUDE_STATE):
        with open(CLAUDE_STATE, encoding="utf-8") as f:
            md = f.read()
        # 提取最近更新
        m = re.search(r"- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \|[^\n]*", md)
        print(f"\n最近更新: {m.group(0) if m else '未知'}")
        # 提取给 WorkBuddy 的留言区
        m = re.search(r"## 💬 给 WorkBuddy 的留言.*", md, re.S)
        if m:
            print(f"\n留言区:\n{m.group(0)[:800]}")
    else:
        print("[WARN] claude_state.md 不存在")
    print("=" * 60)


def do_status() -> None:
    print(f"桥目录: {BRIDGE_DIR}")
    for name in ["wb_state.md", "claude_state.md", "sync_log.md", "README.md"]:
        path = os.path.join(BRIDGE_DIR, name)
        if os.path.exists(path):
            mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
            size = os.path.getsize(path)
            print(f"  ✅ {name:<20} {mtime}  {size}B")
        else:
            print(f"  ⚠️ {name:<20} 缺失")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="双 AI 信息桥同步")
    ap.add_argument("--push", action="store_true", help="WorkBuddy→Claude 推送状态")
    ap.add_argument("--pull", action="store_true", help="Claude→WorkBuddy 拉取状态")
    ap.add_argument("--status", action="store_true", help="查看桥状态")
    args = ap.parse_args()

    if args.push:
        do_push()
    elif args.pull:
        do_pull()
    elif args.status:
        do_status()
    else:
        ap.print_help()
