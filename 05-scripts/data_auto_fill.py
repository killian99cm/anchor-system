# -*- coding: utf-8 -*-
"""
Anchor 数据自动化 MVP（data_auto_fill.py）
- 作用：复用妙想 API 查询各持仓基金最新日涨跌，生成「数据回填候选」供用户确认
- 铁律：本脚本【只生成候选文件，绝不写入 portfolio_data.json】——数据权威仍以用户确认为准
- 输出：Anchor/04-reviews/daily/{date}-数据回填候选.json
"""
import json
import os
import sys
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from daily_advice import mx_query  # 复用妙想 API 查询

DESKTOP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JSON_PATH = os.path.join(DESKTOP, "portfolio_data.json")

# 权益类持仓（债券/余额宝稳定，不查）
QUERY_NAMES = [
    "华夏国证半导体芯片ETF联接C",
    "易方达恒生港股通创新药ETF联接C",
    "天弘纳斯达克100指数(QDII)C",
    "华泰柏瑞纳斯达克100ETF联接A",
    "易方达证券ETF联接C",
    "国泰黄金ETF联接A",
    "天弘通利混合A",
]


def load_holdings():
    with open(JSON_PATH, encoding="utf-8") as f:
        d = json.load(f)
    mv = {h["name"]: h.get("mv", 0) for h in d.get("holdings_summary", [])}
    return mv


def fetch_latest_pct(name: str) -> dict:
    """查询基金最新日涨跌幅，返回 {pct, date, entity}"""
    try:
        rows = mx_query(f"{name} 最新净值 日涨跌幅", timeout=40)
        # 取第一条非空涨跌数据
        for r in rows:
            v = r["value"].replace("%", "").strip()
            try:
                pct = float(v)
            except ValueError:
                continue
            return {"pct": pct, "date": r["date"], "entity": r["entity"]}
        return {"error": "无有效涨跌数据"}
    except Exception as e:
        return {"error": str(e)[:60]}


def main():
    mv = load_holdings()
    today = date.today().isoformat()
    results = []
    for name in QUERY_NAMES:
        r = fetch_latest_pct(name)
        base_mv = mv.get(name, 0)
        entry = {
            "fund": name,
            "base_mv_8_26": base_mv,
        }
        entry.update(r)
        if "pct" in r and base_mv:
            entry["est_day_pnl"] = round(base_mv * r["pct"] / 100, 2)
        results.append(entry)
        status = f"+{entry['pct']}%" if "pct" in entry else f"❌ {entry.get('error')}"
        print(f"  {name[:18]:<20} {status}")

    out = {
        "generated": today,
        "note": "数据回填候选——仅供用户确认，未写入 portfolio_data.json（数据铁律：权威以用户确认为准）",
        "candidates": results,
    }
    out_dir = os.path.join(DESKTOP, "Anchor", "04-reviews", "daily")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{today}-数据回填候选.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 候选已生成（未写入 JSON）: {out_path}")


if __name__ == "__main__":
    main()
