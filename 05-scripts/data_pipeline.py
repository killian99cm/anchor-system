#!/usr/bin/env python3
"""
Anchor 数据管道规范 v1.0（8/20 确立，最高优先级数据纪律）

目标：让每次搜索/查询的数据「更准确、更合理、更适合 Anchor」。
四层规范：
  ① 定位层：持仓 → 跟踪指数 → 市场 → 资金面来源 → 宏观归因 映射（防张冠李戴）
  ② 获取层：mx-data 查询模板 + 标准资金面快照解析（防查询失败、口径混乱）
  ③ 归因层：资产类别 → 正确宏观驱动指标（防因果错配，如债券归因到美债）
  ④ 验证层：data_quality_check() 报告前自检（防未标注时间戳/来源）

用法:
  python data_pipeline.py --map        → 打印全部持仓的数据管道映射
  python data_pipeline.py --lookup 创新药 → 查单只持仓的管道定义
  python data_pipeline.py --check      → 跑数据质量自检（报告生成前必跑）
"""
import json
import os
import subprocess
import sys
import time as _time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "05-scripts"))
import paths  # B2：数据就绪自检需要桌面产物路径


# ============================================================
# ① 定位层 + 归因层：DATA_PIPELINE_MAP
#    每只持仓 → 跟踪指数 / 市场 / 资金面来源 / 宏观归因 / mx 查询模板
# ============================================================
# 关键原则（8/20 教训）：
#   - 港股基金必须看南向资金 / 港股 ETF 资金流，不能拿 A股 DDX 判断
#   - 债券类压舱石看中国 10Y 国债收益率，不是美债
#   - QDII 看当晚美股净值确认 + 场内溢价率
DATA_PIPELINE_MAP = {
    "创新药": {
        "fund": "易方达恒生港股通创新药ETF联接C",
        "index": "恒生港股通创新药指数",
        "index_code": "HSSCID.HI",
        "market": "港股",
        "flow_source": "南向资金 + 港股创新药ETF资金流（非A股DDX）",
        "macro_driver": "中国创新药产业政策 + 港股流动性 + 全球医药催化",
        "mx_query": "恒生港股通创新药指数 最新点位 涨跌幅 今日",
    },
    "纳指": {
        "fund": "华泰柏瑞纳指100联接A / 天弘纳指100C",
        "index": "纳斯达克100",
        "index_code": "NDX",
        "market": "美股(美东)",
        "flow_source": "QDII当晚净值确认 + 场内ETF溢价率",
        "macro_driver": "美股科技盈利 + 美元流动性 + 费城半导体",
        "mx_query": "纳斯达克100指数 最新点位 涨跌幅",
    },
    "半导体": {
        "fund": "华夏国证半导体芯片ETF联接C",
        "index": "国证半导体芯片指数",
        "index_code": "980017",
        "market": "A股",
        "flow_source": "A股半导体板块 DDX + 主力/超大单流向",
        "macro_driver": "中国半导体周期 + 海外费半 + 政策",
        "mx_query": "半导体 板块 主力资金流向 DDX 今日",
    },
    "证券": {
        "fund": "易方达证券ETF联接C",
        "index": "证券公司指数",
        "index_code": "399975",
        "market": "A股",
        "flow_source": "A股证券板块 DDX + 主力流向",
        "macro_driver": "大盘量能 + 券商政策 + 市场情绪",
        "mx_query": "证券 板块 主力资金流向 DDX 今日",
    },
    "黄金": {
        "fund": "国泰黄金ETF联接A",
        "index": "SGE黄金9999 / 伦敦金",
        "index_code": "AU9999",
        "market": "商品",
        "flow_source": "黄金ETF实时价 + 金价现货",
        "macro_driver": "美债实际利率 + 美元指数 + 避险情绪",
        "mx_query": "黄金ETF 最新价 涨跌幅",
    },
    "债券": {
        "fund": "鹏华畅享债券C / 中银稳健增利债券A",
        "index": "中债综合",
        "index_code": "CBA",
        "market": "中国债券",
        "flow_source": "中国10Y国债收益率 + 债基净值",
        "macro_driver": "中国10Y国债收益率（非美债！）+ 央行政策 + 经济数据",
        "mx_query": "中国10年期国债收益率 最新",
    },
    "红利": {
        "fund": "515180 中证红利ETF",
        "index": "中证红利指数",
        "index_code": "000922",
        "market": "A股",
        "flow_source": "A股红利ETF资金流",
        "macro_driver": "高股息 + 避险 + 利率下行",
        "mx_query": "中证红利 指数 最新点位 涨跌幅",
    },
    "通利": {
        "fund": "天弘通利混合A",
        "index": "沪深300 (混合参考)",
        "index_code": "000300",
        "market": "A股",
        "flow_source": "A股大盘主力流向",
        "macro_driver": "中国宏观 + 大盘风格",
        "mx_query": "沪深300指数 最新点位 涨跌幅",
    },
    "现金": {
        "fund": "余额宝",
        "index": "货币基金7日年化",
        "index_code": "-",
        "market": "现金",
        "flow_source": "余额宝金额 + 7日年化",
        "macro_driver": "无（现金流动性管理）",
        "mx_query": "",
    },
}

# 资产类别 → 正确宏观驱动（归因层核心，防因果错配）
MACRO_DRIVER_MAP = {
    "A股板块": "中国利率 + 政策 + 板块资金面（DDX）",
    "港股": "南向资金 + 港股流动性 + 全球风险偏好",
    "美股QDII": "美股当晚净值 + 场内溢价率 + 美元流动性",
    "中国债券": "中国10Y国债收益率 + 央行宽松 + 经济数据",
    "黄金": "美债实际利率 + 美元指数 + 避险",
}


def lookup(name: str) -> dict:
    """按别名查持仓管道定义（支持部分匹配）"""
    name = str(name)
    for key, val in DATA_PIPELINE_MAP.items():
        if name in key or key in name:
            return {"key": key, **val}
    # 遍历 fund 名称匹配
    for key, val in DATA_PIPELINE_MAP.items():
        if name in val.get("fund", ""):
            return {"key": key, **val}
    return {}


# ============================================================
# ② 获取层：fund_flow_snapshot() 标准资金面快照解析
# ============================================================
def _find_tables(raw) -> list:
    """递归查找第一个 dataTableDTOList（兼容不同封装深度）。
    实测：mx_data.py 的 raw JSON 为 data → data → searchDataResultDTO → dataTableDTOList
    部分查询为 data → dataTableDTOList（skill 文档结构）。"""
    if isinstance(raw, dict):
        if "dataTableDTOList" in raw and isinstance(raw["dataTableDTOList"], list):
            return raw["dataTableDTOList"]
        for v in raw.values():
            found = _find_tables(v)
            if found:
                return found
    elif isinstance(raw, list):
        for v in raw:
            found = _find_tables(v)
            if found:
                return found
    return []


def _num_yi(v):
    """解析金额单位（亿元），返回 (数值, 单位)。如 '-62.46亿元' → (-62.46, '亿元')"""
    if v is None:
        return None, ""
    s = str(v)
    unit = ""
    for u in ("万亿元", "亿元", "万元"):
        if u in s:
            unit = u
            s = s.replace(u, "")
            break
    try:
        return float(s.replace(",", "").replace("+", "")), unit
    except ValueError:
        return None, ""


def fund_flow_snapshot(raw: dict) -> dict:
    """把 mx-data 返回的原始 JSON 解析成标准资金面快照。
    输入：mx_data 的完整 raw JSON（dict）。
    输出统一结构：{index, ddx, ddx3, ddx10, super_large_flow, main_flow,
                   change, time, date, unit}
    解析失败返回空 dict（调用方需标注 '未知'，不编造）。"""
    try:
        tables = _find_tables(raw)
        if not tables:
            return {}
        t = tables[0]
        table = t.get("table", {}) or {}
        name_map = t.get("nameMap", {}) or {}

        # 字段 → 中文名 反查
        cols = {}
        for code, name in name_map.items():
            if isinstance(name, str):
                cols[str(name)] = code

        def get_col(chinese):
            # 精确匹配（如「当日DDX」）
            code = cols.get(chinese)
            if not code:
                # 包含匹配（真实列名常带后缀：'超大单净流入资金' 匹配 '超大单净流入'）
                for name, c in cols.items():
                    if chinese in name:
                        code = c
                        break
            if not code and "当日" in chinese:
                code = cols.get(chinese.replace("当日", ""))
            if code and code in table:
                vals = table[code]
                return vals[-1] if vals else None
            return None

        # 时间：真实数据在 table['headName']（如 '2026-08-20 14:40'）
        time_val = None
        if "headName" in table:
            hv = table["headName"]
            time_val = hv[-1] if hv else None
        if not time_val:
            time_val = get_col("date") or (t.get("headName") or [None])[-1]

        flow_val, flow_unit = _num_yi(get_col("超大单净流入"))

        return {
            "index": t.get("entityName", ""),
            "change": _num(get_col("涨跌幅")),
            "ddx": _num(get_col("当日DDX")),
            "ddx3": _num(get_col("3日DDX")),
            "ddx10": _num(get_col("10日DDX")),
            "super_large_flow": flow_val,
            "main_flow": _num(get_col("主力净流入")),
            "unit": flow_unit,  # 资金单位：亿元
            "time": time_val,
            "date": str(time_val)[:10] if time_val else "",
        }
    except Exception:
        return {}


def _num(v):
    """转 float，容忍 None/字符串/百分比"""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("%", "").replace("+", "").replace("亿", ""))
    except (ValueError, TypeError):
        return None


# ============================================================
# ④ 验证层：data_quality_check() 报告前自检
# ============================================================
REQUIRED_MARKERS = {
    "持仓日期": ["update_date", "update_time", "8/19", "8/20"],
    "行情时间": ["14:", "15:", "盘中", "收盘", "午评"],
    "资金面": ["DDX", "净流入", "净流出", "资金"],
    "来源": ["妙想", "mx", "http", "eastmoney", "wallstreet"],
}


def data_quality_check(report_text: str, holdings: list = None) -> list:
    """报告前自检。返回问题列表（空 = 通过）。
    holdings: 本次报告涉及的持仓别名列表，逐只检查是否在报告中出现。
    """
    issues = []
    if not report_text:
        return ["报告为空"]

    # ① 三类日期/时间戳标注
    for marker, keys in REQUIRED_MARKERS.items():
        if not any(k in report_text for k in keys):
            issues.append(f"缺「{marker}」标注（需出现任一关键词：{keys[:3]}...）")

    # ② 每只持仓是否出现（防漏写/张冠李戴）
    if holdings:
        for h in holdings:
            if h not in report_text:
                issues.append(f"持仓「{h}」未在报告中出现，或用了其他名称（检查是否张冠李戴）")

    return issues


# ============================================================
# B2 数据就绪 6 项自检（报告生成前必跑；--check 调用）
# ============================================================
def _latest_mtime(directory):
    """返回目录下最新文件的 mtime（递归），无文件/目录不存在返回 None。"""
    dp = Path(directory)
    files = [f for f in dp.rglob("*") if f.is_file()] if dp.exists() else []
    if not files:
        return None
    return max(f.stat().st_mtime for f in files)


def artifact_readiness_check():
    """报告生成前数据就绪 6 项自检。返回 (issues, warns)：
    issues=硬问题（产物缺失/损坏/逾期未复盘），应阻断；warns=陈旧提示，不阻断。"""
    issues, warns = [], []

    # 1) 源 JSON：存在 / 可解析 / total 正 / 有日期
    data = None
    if not paths.DATA_PATH.exists():
        issues.append(f"[1·JSON] 缺少 {paths.DATA_PATH.name}")
    else:
        try:
            data = json.loads(paths.DATA_PATH.read_text(encoding="utf-8"))
            if data.get("total_assets", 0) <= 0:
                issues.append("[1·JSON] total_assets 非正数")
            if not (data.get("update_date") or data.get("update_time")):
                issues.append("[1·JSON] 缺 update_date/update_time")
        except Exception as e:
            issues.append(f"[1·JSON] 解析失败: {e}")
    json_mtime = paths.DATA_PATH.stat().st_mtime if paths.DATA_PATH.exists() else 0

    # 2) Excel：存在 / 足够大 / 不旧于源 JSON
    if not paths.EXCEL_PATH.exists():
        issues.append("[2·Excel] 缺少 portfolio_holdings.xlsx（先跑 sync_all）")
    else:
        size = paths.EXCEL_PATH.stat().st_size
        if size < 10000:
            issues.append(f"[2·Excel] 文件仅 {size}B，可能生成不完整")
        elif paths.EXCEL_PATH.stat().st_mtime < json_mtime:
            warns.append("[2·Excel] Excel 早于源 JSON（数据更新后未重跑 sync_all）")

    # 3) HTML：存在 / 含 var D 数据块 / 不旧于源 JSON
    if not paths.HTML_PATH.exists():
        issues.append("[3·HTML] 缺少 portfolio_analysis.html")
    else:
        html_text = paths.HTML_PATH.read_text(encoding="utf-8", errors="replace")
        if len(html_text) < 20000 or "var D" not in html_text:
            issues.append("[3·HTML] 过小或缺 var D 数据块，rebuild 可能失败")
        elif paths.HTML_PATH.stat().st_mtime < json_mtime:
            warns.append("[3·HTML] HTML 早于源 JSON（未重跑 rebuild/sync_all）")

    # 4) 快照：存在 / 可解析 / total 与源 JSON 偏差 <100
    if not paths.SNAPSHOT_PATH.exists():
        issues.append("[4·快照] 缺少 portfolio_snapshot.json")
    elif data:
        try:
            snap = json.loads(paths.SNAPSHOT_PATH.read_text(encoding="utf-8"))
            if abs(snap.get("total_assets", 0) - data.get("total_assets", 0)) >= 100:
                issues.append("[4·快照] total_assets 与源 JSON 偏差≥100（快照过期，重跑 sync_all）")
        except Exception as e:
            issues.append(f"[4·快照] 解析失败: {e}")

    # 5) 决策日志近 3 日复盘：T+3 到期未复盘（输出含 🔴）→ 阻断
    try:
        proc = subprocess.run(
            [sys.executable, str(paths.SCRIPTS / "decision_log.py"), "--due"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if "🔴" in (proc.stdout or ""):
            issues.append("[5·决策复盘] 有已到 T+3 未复盘决策（先 decision_log.py --review 再写报告）")
    except Exception as e:
        warns.append(f"[5·决策复盘] --due 检查异常: {e}")

    # 6) mx-data 新鲜度：mx_output 最新采集 >4 自然日 → WARN；空目录 → WARN
    latest = _latest_mtime(paths.MX_OUTPUT_DIR)
    if latest is None:
        warns.append(f"[6·mx-data] {paths.MX_OUTPUT_DIR.name} 目录无采集文件")
    else:
        age_days = (_time.time() - latest) / 86400
        latest_str = _time.strftime("%Y-%m-%d", _time.localtime(latest))
        if age_days > 4:
            warns.append(f"[6·mx-data] 最新采集为 {latest_str}（{age_days:.1f} 天前），行情可能陈旧")

    return issues, warns


# ============================================================
# 主入口
# ============================================================
def main() -> int:
    if "--map" in sys.argv:
        for key, val in DATA_PIPELINE_MAP.items():
            print(f"\n[{key}] {val['fund']}")
            print(f"  跟踪指数: {val['index']} ({val['index_code']}) | 市场: {val['market']}")
            print(f"  资金面来源: {val['flow_source']}")
            print(f"  宏观归因: {val['macro_driver']}")
            print(f"  mx查询模板: {val['mx_query']}")
        return 0

    if "--lookup" in sys.argv:
        idx = sys.argv.index("--lookup")
        name = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else ""
        result = lookup(name)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"未找到「{name}」的管道定义，请先补充到 DATA_PIPELINE_MAP")
        return 0

    if "--check" in sys.argv:
        hard_fail = 0

        # (A) 数据管道映射完整性（--map-only 时可单独跳过就绪检查）
        map_issues = []
        for key, val in DATA_PIPELINE_MAP.items():
            for field in ("index", "market", "flow_source", "macro_driver"):
                if not val.get(field):
                    map_issues.append(f"[{key}] 缺 {field}")
        if map_issues:
            print("🔴 数据管道映射缺失：")
            for i in map_issues:
                print(" -", i)
            hard_fail = 1
        else:
            print(f"✅ 数据管道映射完整：{len(DATA_PIPELINE_MAP)} 只持仓/资产全部定义资金面来源与宏观归因")
            print("   （8/20 纪律：港股看南向、债券看中国10Y、QDII看美股净值+溢价）")

        # (B) 报告前数据就绪 6 项（B2）；--map-only 仅查映射
        if "--map-only" not in sys.argv:
            print("\n— 数据就绪 6 项自检 —")
            r_issues, r_warns = artifact_readiness_check()
            for w in r_warns:
                print("  ⚠️", w)
            if r_issues:
                for i in r_issues:
                    print("  🔴", i)
                hard_fail = 1
            else:
                print("  ✅ JSON / Excel / HTML / 快照 / 决策复盘 / mx-data 六项就绪")

        if hard_fail:
            print("\n🔴 --check 未通过：请先按上述 🔴 项处理（通常先跑 sync_all.py）")
            return 1
        print("\n✅ --check 全部通过")
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
