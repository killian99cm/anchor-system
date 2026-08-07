#!/usr/bin/env python3
"""Daily NAV puller + Excel updater + Alert checker. Run after 8pm daily."""
import json, subprocess, sys, os
from datetime import datetime

DESKTOP = os.path.dirname(os.path.abspath(__file__))
PYTHON = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe"
MX_DATA = r"C:\Users\lenovo\.claude\skills\mx-data\mx_data.py"
OUTPUT = os.path.join(DESKTOP, "mx_output")

FUND_QUERIES = [
    "华夏国证半导体芯片ETF联接C 008888 最新净值 日涨跌幅",
    "招商TMT50联接A 217019 最新净值 日涨跌幅",
    "国泰黄金ETF联接 最新净值 日涨跌幅",
    "鹏华畅享债券C 015257 最新净值 日涨跌幅",
    "中银稳健增利债券A 最新净值",
    "华泰纳指100 天弘纳指100 天弘全球高端制造 最新净值 日涨跌幅",
    "诺安研究精选C 天弘通利混合A 最新净值 日涨跌幅",
    "创新药ETF 159992 最新净值 涨跌幅",
    "华泰中证2000增强C 景顺长城衡瑞 最新净值",
    "平安光伏产业C 平安卫星产业C 最新净值",
    "易方达证券ETF联接C 最新净值",
    "上证红利联接A 最新净值",
    "上证指数 科创50 最新收盘 涨跌幅 成交额"
]

def pull_all():
    print(f"[{datetime.now():%H:%M:%S}] Pulling NAVs...")
    for q in FUND_QUERIES:
        print(f"  {q[:60]}...")
        subprocess.run([PYTHON, MX_DATA, q, OUTPUT], capture_output=True, timeout=60)
    print("All NAVs pulled.")

def update_files():
    gen = os.path.join(DESKTOP, "gen_excel_skill.py")
    subprocess.run([PYTHON, gen], capture_output=True, timeout=30)
    print("Excel regenerated.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--excel-only":
        update_files()
    else:
        pull_all()
        update_files()
    print("[OK] Done at " + datetime.now().strftime("%H:%M:%S"))
