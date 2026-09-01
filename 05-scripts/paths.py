#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paths.py — Anchor 项目唯一路径真源（single source of truth）

所有脚本统一 `import paths` 后消费这里的常量，禁止再硬编码
``C:\\Users\\lenovo\\...`` 或 ``Path.home() / "Desktop"``：
  - 换机器 / 换用户名时只改这一处（也可用环境变量 ANCHOR_DESKTOP 覆盖桌面根）
  - 运行 ``python paths.py --audit`` 扫描 05-scripts 是否有脚本重新硬编码绝对路径
    （行尾加 ``# paths-audit: ignore`` 可显式豁免，仅用于废弃/特殊脚本）

变更管理：新增目录常量统一在此登记；脚本侧只消费，不自行拼桌面绝对路径。
"""
import os
import re
import sys
from pathlib import Path

# ============ 根目录（桌面根可由环境变量覆盖，便于换机/迁移） ============
DESKTOP = Path(os.environ.get("ANCHOR_DESKTOP", str(Path.home() / "Desktop")))
ANCHOR = DESKTOP / "Anchor"

# ============ Anchor 内部目录 ============
SCRIPTS = ANCHOR / "05-scripts"
DASHBOARD_DIR = ANCHOR / "06-dashboard"
WEBSITE_DIR = ANCHOR / "08-website"
REVIEWS_DIR = ANCHOR / "04-reviews"
SYSTEM_DIR = ANCHOR / "00-system"
RULES_DIR = ANCHOR / "01-rules"
MEMORY_DIR = ANCHOR / "07-memory"
NOISE_DIR = DASHBOARD_DIR / "noise"
MX_PRECISE_DIR = ANCHOR / "_mx_precise"            # data_auto_fill 精确 MX 数据目录
BACKTEST_DIR = ANCHOR / "09-backtest"

# ============ 桌面权威产物（铁律：只保留这 4 个 portfolio 文件） ============
DATA_PATH = DESKTOP / "portfolio_data.json"
SNAPSHOT_PATH = DESKTOP / "portfolio_snapshot.json"
HTML_PATH = DESKTOP / "portfolio_analysis.html"
EXCEL_PATH = DESKTOP / "portfolio_holdings.xlsx"
XLSX_PATH = EXCEL_PATH                       # 别名（与 EXCEL_PATH 同一文件，向后兼容）
XLSX_NEW_PATH = DESKTOP / "portfolio_holdings_new.xlsx"
DECISION_LOG_PATH = DASHBOARD_DIR / "decision_log.json"   # 决策日志（私有，存 06-dashboard）

# ============ AI 协作层（WorkBuddy ⇄ Claude） ============
AI_COLLAB_DIR = DESKTOP / "AI-Collab"
RULE_CONTRACT_PATH = AI_COLLAB_DIR / "rule_contract.json"   # 规则/数据版本契约（软件读此判断同步）
BRIDGE_DIR = AI_COLLAB_DIR / "ai-bridge"
WB_STATE_PATH = BRIDGE_DIR / "wb_state.md"
CLAUDE_STATE_PATH = BRIDGE_DIR / "claude_state.md"
SYNC_LOG_PATH = BRIDGE_DIR / "sync_log.md"

# ============ 桌面其它目录 ============
MX_OUTPUT_DIR = DESKTOP / "mx_output"
ARCHIVE_DIR = DESKTOP / "Claude对话归档"
FINANCE_DIR = DESKTOP / "财务"

# ============ 用户级 Claude Code（与桌面无关的用户配置目录，允许 Path.home） ============
CLAUDE_HOME = Path.home() / ".claude"
CLAUDE_SETTINGS = CLAUDE_HOME / "settings.json"
CLAUDE_PROJECTS = CLAUDE_HOME / "projects"
CLAUDE_USER_MEMORY = CLAUDE_HOME / "CLAUDE.md"


# ============ 路径审计断言（C1：新脚本禁止硬编码 C:\\Users\\lenovo） ============
_IGNORE_MARKER = "paths-audit: ignore"
# 命中：盘符:\Users\xxx\Desktop、/Users/xxx/Desktop，或 Path.home()/"Desktop"
# 不命中 Path.home()/".claude" 这类用户级配置目录（与桌面路径无关，属合理用法）
_HARDCODED_RE = re.compile(
    r'[A-Za-z]:[\\/]Users[\\/][^\\/"]+[\\/]Desktop'
    r'|[\\/]Users[\\/][^\\/"]+[\\/]Desktop'
    r'|Path\.home\(\)\s*/\s*["\']Desktop'
)


def audit_hardcoded_paths(scripts_dir=SCRIPTS):
    """扫描脚本目录，返回 [(文件名, 行号, 行内容)] 硬编码桌面路径清单。

    豁免规则：
      - paths.py 自身（必须用 Path.home 推导桌面根）
      - 行内含 ``# paths-audit: ignore`` 注释的行（废弃脚本等特殊情况）
    """
    violations = []
    scripts_dir = Path(scripts_dir)
    if not scripts_dir.is_dir():
        return violations
    for py in sorted(scripts_dir.glob("*.py")):
        if py.name == "paths.py":
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if _IGNORE_MARKER in line:
                continue
            if _HARDCODED_RE.search(line):
                violations.append((py.name, lineno, line.strip()))
    return violations


def _print_layout():
    for name in ("DESKTOP", "ANCHOR", "SCRIPTS", "DASHBOARD_DIR", "WEBSITE_DIR",
                 "REVIEWS_DIR", "RULES_DIR", "MEMORY_DIR", "DATA_PATH",
                 "SNAPSHOT_PATH", "HTML_PATH", "XLSX_PATH", "RULE_CONTRACT_PATH",
                 "BRIDGE_DIR", "MX_PRECISE_DIR", "CLAUDE_HOME"):
        print(f"{name:20} = {globals()[name]}")


def main():
    if "--audit" in sys.argv:
        violations = audit_hardcoded_paths()
        if violations:
            print(f"[FAIL] 发现 {len(violations)} 处硬编码桌面路径（应改为 import paths）：")
            for name, lineno, txt in violations:
                print(f"  {name}:{lineno}: {txt[:100]}")
            sys.exit(1)
        print("[OK] 05-scripts 无硬编码桌面路径（统一走 paths.py）")
        sys.exit(0)
    _print_layout()


if __name__ == "__main__":
    main()
