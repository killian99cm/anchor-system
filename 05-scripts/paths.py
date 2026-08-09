#!/usr/bin/env python3
"""
路径统一入口 — 平台无关（CI / 换机可运行）。
所有脚本从这里取路径，不再硬编码 Windows 绝对路径。

- 私有数据仍在桌面（Portfolio 文件协议），可用环境变量 ANCHOR_DESKTOP 覆盖
- 仓库内路径一律由 __file__ 推导
"""
import os
from pathlib import Path

DESKTOP = Path(os.environ.get("ANCHOR_DESKTOP", str(Path.home() / "Desktop")))
ANCHOR = Path(__file__).resolve().parent.parent
SCRIPTS = ANCHOR / "05-scripts"
DASHBOARD_DIR = ANCHOR / "06-dashboard"
REVIEWS_DIR = ANCHOR / "04-reviews"

DATA_PATH = DESKTOP / "portfolio_data.json"
HTML_PATH = DESKTOP / "portfolio_analysis.html"
SNAPSHOT_PATH = DESKTOP / "portfolio_snapshot.json"
EXCEL_PATH = DESKTOP / "portfolio_holdings.xlsx"
