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
  python data_pipeline.py --integrity  → 结构化入库自检（v4.4.0，sync_all 步骤0 致命闸门）
  python data_pipeline.py --coverage   → 取数覆盖度校验（v4.4.11，任务单 #137）：
                                         活跃持仓 ↔ fetch_registry.json 双向差集 + A-2 双向断言。
                                         🔴 与 --check 的分工：--check 查「映射表内部自洽」，
                                         --coverage 查「该取的资产是否真的有取数定义」——
                                         后者才能发现「债券有定义却从未被取数」这类缺口。
  python data_pipeline.py --verify-codes <报告|--all> [--refresh]
                                       → 指数代码—名称一致性校验（inbox/135，2026-09-23）：
                                         报告表格行 (代码,名称) 对子 ↔ index_registry.json；
                                         有 🔴（代码-名称不符）⇒ rc=1。--refresh 联机双源复核注册表。
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
# 取数覆盖度校验（任务单 #137 需求B，2026-09-16）
# ============================================================
# 🔴 支持环境变量覆盖（v4.5.1）—— 供测试指向临时副本，永不触碰生产注册表。
#    理由同 data_auto_fill.py 处说明：try/finally 挡不住硬杀，会留下测试夹具污染生产文件。
REGISTRY_PATH = Path(os.environ.get("ANCHOR_FETCH_REGISTRY")
                     or Path(__file__).resolve().parent / "fetch_registry.json")


def _active_holdings(data: dict) -> list:
    """活跃持仓 = mv>0 且 group≠已清仓；读【两个段】（红利在 stock_holdings）。"""
    out = []
    for h in data.get("holdings_summary", []):
        if (h.get("mv") or 0) > 0 and h.get("group") != "已清仓":
            out.append({"name": h.get("name", ""), "mv": h.get("mv") or 0,
                        "group": h.get("group", ""), "segment": "holdings_summary"})
    for h in data.get("stock_holdings", []):
        mv = h.get("mv")
        if mv in (None, ""):
            try:
                mv = round(float(h.get("shares", 0)) * float(h.get("price", 0)), 2)
            except (TypeError, ValueError):
                mv = 0
        if (mv or 0) > 0 and h.get("group") != "已清仓":
            out.append({"name": h.get("name", ""), "mv": mv or 0,
                        "group": h.get("group", ""), "segment": "stock_holdings"})
    return out


def coverage_check() -> tuple:
    """双向差集校验。返回 (problems, notes)。

    (A) 每只【活跃持仓】必须至少被一个注册表条目覆盖（按 holdings_match 关键词）
    (B) A-2 双向断言：每个条目的 pipeline_key ∈ DATA_PIPELINE_MAP，
        且 DATA_PIPELINE_MAP 每个键都有条目指向它  —— 防止「改了分析口径忘了改取数」或反之
    """
    problems, notes = [], []

    try:
        data = json.loads(paths.DATA_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"无法读取 {paths.DATA_PATH}: {e}"], notes

    try:
        reg = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"🔴 取数注册表不可读 {REGISTRY_PATH}: {e} —— 取数层无真值，覆盖度不可判"], notes

    entries = reg.get("entries") or []
    if not entries:
        return [f"🔴 注册表 {REGISTRY_PATH.name} 无 entries"], notes

    holds = _active_holdings(data)
    notes.append(f"活跃持仓 {len(holds)} 只（mv>0 且非已清仓）｜注册表条目 {len(entries)} 条")

    # ---- (A) 活跃持仓 → 是否有取数定义 ----
    for h in holds:
        hit = [e for e in entries
               if any(kw and kw in h["name"] for kw in (e.get("holdings_match") or []))]
        if not hit:
            problems.append(f"持仓「{h['name']}」(mv={h['mv']}, {h['segment']}) "
                            f"→ ❌ 无任何取数定义（该持仓不会被取数）")
        else:
            keys = "/".join(e.get("key", "?") for e in hit)
            notes.append(f"  ✅ {h['name'][:22]:<24}→ {keys}")

    # ---- (B) A-2 双向断言 ----
    map_keys = set(DATA_PIPELINE_MAP.keys())
    reg_keys = {e.get("pipeline_key") for e in entries if e.get("pipeline_key")}

    orphan_reg = reg_keys - map_keys
    if orphan_reg:
        problems.append(f"注册表 pipeline_key 在 DATA_PIPELINE_MAP 中不存在：{sorted(orphan_reg)}"
                        f"（分析口径无此资产 → 取数结果无处归因）")

    uncovered_map = map_keys - reg_keys
    if uncovered_map:
        problems.append(f"DATA_PIPELINE_MAP 有定义但取数层无条目：{sorted(uncovered_map)}"
                        f"（＝ 死定义，该资产不会被取数 —— 9/16「债券从未取数」即此形态）")

    if not orphan_reg and not uncovered_map:
        notes.append(f"  ✅ A-2 双向断言通过：MAP {len(map_keys)} 键 ↔ 注册表 {len(reg_keys)} 键，双向差集为空")

    return problems, notes


# ============================================================
# 主入口
# ============================================================
# 指数代码—名称一致性校验 ＋ 量级跳变护栏（inbox/135）
#
# 事故（2026-09-14）：报告把 `sz399811` 标成「国证芯片」（真名 **CSSW电子**），
# 数值从 15,812 骤降到 7,127（−55%，量级差 2.2 倍），而 data_pipeline --check /
# report_time_check / report_time_audit **三层校验全部放行**。
# 根因：报告里手写的 (代码, 名称) 对子，与机器可读的注册表之间**从未被绑定**。
# 本块补这条绑定：注册表（index_registry.json）＋ --verify-codes ＋ 量级护栏。
# ⛔ 只读不改：护栏只**报**，不自动改写任何报告/数据（135 §3）。
# ⛔ 不把标的校验塞进 report_time_check（职责单一）；这里是**新增独立检查**。
# ============================================================
import re as _re
import urllib.request as _urlreq

INDEX_REGISTRY_PATH = Path(__file__).parent / "index_registry.json"
_CODE_RE = _re.compile(r"(?<![0-9A-Za-z])(?:s[hz])?([0-9]{6})(?![0-9])")
_TOKEN_SPLIT_RE = _re.compile(r"[|*`（）()\[\]「」【】\s]+")
_CJK_RE = _re.compile(r"[\u4e00-\u9fff]")


def load_index_registry(path=None):
    """读 index_registry.json → (doc, None) 或 (None, 原因)。"""
    p = Path(path) if path else INDEX_REGISTRY_PATH
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"注册表 {p.name} 不存在"
    except Exception as e:                                        # noqa: BLE001
        return None, f"注册表解析失败: {e}"
    if not isinstance(doc.get("indices"), dict):
        return None, f"{p.name} 结构异常（缺 indices 段）"
    return doc, None


_NAME_TOKEN_RE = _re.compile(r"[\u4e00-\u9fffA-Za-z0-9·]{2,}")


def _row_cells(raw):
    s = raw.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return s.split("|")


def extract_code_claims(text):
    """保守提取「代码 ↔ 附近名称」的主张（135 §2-A2 规则 1，v2 单元格邻近语义）。

    规则（⛔ 宁漏勿错，防把示例清单/正文数字当主张）：
      ① 只看**表格行**；② 只看**单元格内恰含 1 个代码**的格（多代码格＝示例清单，跳过计数）；
      ③ 名称候选 = **同格紧邻**代码的 token（间隙 ≤3 字符，容忍 `**`/括号/空格）
         ＋ **左右相邻格**内的名称 token（当同格无候选时）；
      ④ 全行无候选 ⇒ 计「无相邻名」，不产出判定。
    返回 (claims, stat)。claim = {line, code, cands}。
    """
    claims = []
    n_code_cells = n_multi_code = n_no_cand = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        if "|" not in raw:
            continue
        cells = _row_cells(raw)
        for ci, cell in enumerate(cells):
            codes = _CODE_RE.findall(cell)
            if not codes:
                continue
            n_code_cells += 1
            if len(codes) > 1:
                n_multi_code += 1
                continue
            code = codes[0]
            cm = _CODE_RE.search(cell)
            toks = [(m.group(0), m.start(), m.end()) for m in _NAME_TOKEN_RE.finditer(cell)
                    if _CJK_RE.search(m.group(0))]      # ⛔ 纯数字/字母 token 不算名称候选
            before = [t for t in toks if t[2] <= cm.start()]
            after = [t for t in toks if t[1] >= cm.end()]
            same = [t[0] for t in (before[-1:] + after[:1])
                    if cm.start() - t[2] <= 3 and t[1] - cm.end() <= 3]
            if same:
                claims.append({"line": lineno, "code": code, "cands": same})
                continue
            adj = []
            for nb in (cells[ci - 1] if ci > 0 else "", cells[ci + 1] if ci + 1 < len(cells) else ""):
                adj += [m.group(0) for m in _NAME_TOKEN_RE.finditer(nb)
                        if _CJK_RE.search(m.group(0))]
            if adj:
                claims.append({"line": lineno, "code": code, "cands": adj[:4]})
            else:
                n_no_cand += 1
    stat = {"code_cells": n_code_cells, "multi_code_cells": n_multi_code, "no_name": n_no_cand}
    return claims, stat


def verify_codes_in_text(text, registry_indices):
    """返回 (findings, stat)。判定：
      ✅ 相邻名 == 官方名或 alias ｜ 🔴 相邻名命中**其它**已登记指数的名（张冠李戴）／
      🔴 该代码的**己名缺失**但邻名是别的指数名 ｜ 🟡 代码未登记 ／ 🟡 相邻串非注册名（明说未校验）。
    """
    claims, stat = extract_code_claims(text)
    # 全部已登记名（官方+别名）→ token 集合，用于「这名属于谁」反查
    owner = {}
    for c, ent in registry_indices.items():
        for nm in [ent.get("official_name")] + list(ent.get("aliases") or []):
            if nm:
                owner[nm] = c
    findings = []
    for cl in claims:
        code, cands = cl["code"], cl["cands"]
        ent = registry_indices.get(code)
        own_names = ({ent.get("official_name")} | set(ent.get("aliases") or [])) if ent else set()
        own_names.discard(None)
        hit_own = [t for t in cands if t in own_names]
        hit_other = [t for t in cands if t in owner and owner[t] != code]
        if ent is None:
            findings.append({"level": "🟡", "line": cl["line"],
                             "msg": (f"未登记：{code}（相邻名 {cands[:2]}）—— 若为**指数**请双源核名后"
                                     f"补进 index_registry.json；若为 ETF/基金代码可忽略或另行登记")})
        elif hit_own:
            findings.append({"level": "✅", "line": cl["line"],
                             "msg": f"{code} {ent['official_name']}"})
        elif hit_other:
            findings.append({"level": "🔴", "line": cl["line"],
                             "msg": (f"代码-名称不符：{code} 相邻名「{'/'.join(hit_other[:2])}」"
                                     f"属 {owner[hit_other[0]]}，本码官方名「{ent['official_name']}」")})
        else:
            findings.append({"level": "🟡", "line": cl["line"],
                             "msg": (f"相邻串「{'/'.join(cands[:2])}」非注册名 ⇒ **未校验**"
                                     f"（建议报告改用 `名称(代码)` 或独立单元格写法）")})
    return findings, stat


def refresh_registry(reg_doc):
    """联机复核注册表（腾讯 qt.gtimg.cn ＋ 东财 f58 尽力双源）。

    一致 ⇒ 更新 `_meta.verified_at`/`verified_source`；任一不符 ⇒ 🔴 且**不更新**；
    源不可达 ⇒ 🟡 逐条明说（⛔ 不静默通过）。
    """
    import datetime as _dt
    idx = reg_doc["indices"]
    ok, mism, fail_hard, fail_partial = 0, [], [], []
    for code, ent in idx.items():
        secid = ent.get("secid") or ""
        pfx = "sz" if secid.startswith("0.") else "sh"
        tx = em = None
        tx_err = None
        try:                                                      # 腾讯（GBK）
            with _urlreq.urlopen(f"http://qt.gtimg.cn/q={pfx}{code}", timeout=8) as r:
                txt = r.read().decode("gbk", errors="replace")
            tx = txt.split("~")[1].strip() if "~" in txt else None
        except Exception as e:                                    # noqa: BLE001
            tx_err = f"{type(e).__name__}"
        if secid:                                                 # 东财 f58（尽力）
            try:
                with _urlreq.urlopen(
                        "http://push2delay.eastmoney.com/api/qt/stock/get?"
                        f"secid={secid}&fields=f58", timeout=8) as r:
                    em = (((json.loads(r.read().decode("utf-8")) or {}).get("data")) or {}).get("f58")
            except Exception:                                     # noqa: BLE001
                pass
        got = tx or em
        if not got:
            fail_hard.append(f"{code}（腾讯 {tx_err or '无名'}；东财不可达）")
            continue
        if not em:
            fail_partial.append(f"{code} 东财不可达（IP 级限流常见）")
        if tx and em and tx != em:
            mism.append(f"{code} 源间不一致：腾讯「{tx}」vs 东财「{em}」（⚠️ 先查 secid 前缀）")
        elif got != ent.get("official_name"):
            mism.append(f"{code} 注册「{ent.get('official_name')}」≠ 源「{got}」")
        else:
            ok += 1
    print(f"  联机复核：一致 {ok} / 不符 {len(mism)} / 无源可用 {len(fail_hard)}"
          f" / 东财单源不可达 {len(fail_partial)}（腾讯可用时不阻塞）")
    for m in mism:
        print(f"  🔴 {m}")
    for f_ in fail_hard[:6]:
        print(f"  🟡 {f_}{'…' if len(fail_hard) > 6 else ''}")
    if mism:
        print("  🔴 存在不符 ⇒ 注册表**未更新**（先核对 secid 前缀与源头是否改了指代）")
        return 1
    reg_doc.setdefault("_meta", {})["verified_at"] = _dt.date.today().isoformat()
    src = ("腾讯 qt.gtimg.cn" + ("（东财当日不可达）" if (fail_partial or fail_hard) else " ＋ 东财 f58"))
    reg_doc["_meta"]["verified_source"] = f"{src}；本次复核一致 {ok} 条"
    INDEX_REGISTRY_PATH.write_text(json.dumps(reg_doc, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
    print(f"  ✅ 已更新 verified_at = {reg_doc['_meta']['verified_at']}")
    return 0


def verify_codes(argv):
    """`--verify-codes <报告> | --all [--refresh]` 主入口。有 🔴 ⇒ rc=1。"""
    refresh = "--refresh" in argv
    use_all = "--all" in argv
    target = None
    i = argv.index("--verify-codes")
    for a in argv[i + 1:]:
        if not a.startswith("--"):
            target = a
            break
    doc, err = load_index_registry()
    if err:
        print(f"🔴 {err}")
        return 1
    meta = doc.get("_meta") or {}
    print(f"— 指数代码—名称一致性校验（inbox/135）· 注册表 {INDEX_REGISTRY_PATH.name}"
          f"（{len(doc['indices'])} 条 · verified_at {meta.get('verified_at')}）—")
    refresh_rc = refresh_registry(doc) if refresh else 0
    if use_all:
        files = sorted(paths.REVIEWS_DIR.rglob("*.md"))
    elif target:
        p = Path(target)
        if not p.exists():
            alt = paths.REVIEWS_DIR / target
            p = alt if alt.exists() else p
        if not p.exists():
            print(f"🔴 找不到报告文件：{target}")
            return 1
        files = [p]
    else:
        print("用法: --verify-codes <报告路径> | --verify-codes --all [--refresh]")
        return 0
    tot = {"✅": 0, "🟡": 0, "🔴": 0}
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        findings, stat = verify_codes_in_text(text, doc["indices"])
        cnt = {"✅": 0, "🟡": 0, "🔴": 0}
        for fd in findings:
            cnt[fd["level"]] += 1
            tot[fd["level"]] += 1
        try:
            rel = f.relative_to(ROOT)
        except ValueError:
            rel = f
        extra = (f"；代码格 {stat['code_cells']}（**未校验**：多代码格 {stat['multi_code_cells']}"
                 f"／无相邻名 {stat['no_name']} —— ⛔ 非「全部覆盖」）")
        print(f"\n▸ {rel}（✅{cnt['✅']} / 🟡{cnt['🟡']} / 🔴{cnt['🔴']}{extra}）")
        show = [fd for fd in findings if fd["level"] != "✅"] if use_all else findings
        for fd in show:
            print(f"  {fd['level']} L{fd['line']} {fd['msg']}")
        if use_all and not show:
            print("  （全部一致）")
    print(f"\n汇总：✅ {tot['✅']} · 🟡 {tot['🟡']} · 🔴 {tot['🔴']}（扫描 {len(files)} 个文件）")
    if tot["🔴"] or refresh_rc:
        print("🔴 存在代码-名称不符 ⇒ rc=1。⛔ 护栏只报不改（不顺手改报告，交指挥端裁决）")
        return 1
    print("✅ 无代码-名称不符")
    return 0


def magnitude_guard(closes_by_code, warn=8.0, hard=15.0):
    """纯函数：{code: (前收, 当收)} → 逐条 {code, prev, cur, pct, level}。

    135 §2-B1：指数几乎不可能单日 |±15%| ⇒ >15% 🔴（专抓「换了标的却以为没换」）；
    15%>|涨跌|>8% 🟡（可能真实暴跌/暴涨，人工确认）。
    """
    rows = []
    for code, pair in closes_by_code.items():
        prev, cur = pair
        if not prev:
            continue
        pct = (cur - prev) / prev * 100.0
        level = "🔴" if abs(pct) > hard else ("🟡" if abs(pct) > warn else "✅")
        rows.append({"code": code, "prev": prev, "cur": cur, "pct": pct, "level": level})
    return rows


def magnitude_check_live():
    """从注册表取数（腾讯日K，取**最近两根不同日期**的收盘）→ (closes, fails), None | None, 原因。"""
    doc, err = load_index_registry()
    if err:
        return None, err
    import fetch_public as fp
    closes, fails = {}, []
    for code, ent in doc["indices"].items():
        secid = ent.get("secid") or ""
        pfx = "sz" if secid.startswith("0.") else "sh"
        try:
            bars = fp.daily_kline(f"{pfx}{code}", n=5) or []
        except Exception as e:                                    # noqa: BLE001
            fails.append(f"{code} {type(e).__name__}")
            continue
        if len(bars) < 2 or str(bars[-1].get("date")) == str(bars[-2].get("date")):
            fails.append(f"{code} K线不足两根不同日期（{len(bars)} 根）")
            continue
        closes[code] = (float(bars[-2]["close"]), float(bars[-1]["close"]))
    return (closes, fails), None


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

    if "--integrity" in sys.argv:
        # v4.4.0 结构化入库自检：读桌面权威 JSON → data_processor.validate_integrity
        # 🔴 硬项命中 rc=1（sync_all 步骤0 用作致命闸门）；🟡 软提示仅打印。
        try:
            data = json.loads(paths.DATA_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"🔴 无法读取 {paths.DATA_PATH}: {e}")
            return 1
        from data_processor import validate_integrity
        problems = validate_integrity(data)
        hard = [p for p in problems if p.startswith("🔴")]
        soft = [p for p in problems if p.startswith("🟡")]
        print(f"— 结构化入库自检（v4.4.0）· update_date={data.get('update_date')} · total={data.get('total_assets')} —")
        for p in soft:
            print("  ", p)
        for p in hard:
            print("  ", p)
        if not problems:
            print("✅ 入库数据完整：chart 无重复 / 时间轴对齐 / 星期正确 / 顶层自洽 / market 日期一致")
        else:
            print(f"{'🔴' if hard else '🟡'} 共 {len(hard)} 硬项 + {len(soft)} 提示")
        return 1 if hard else 0

    if "--coverage" in sys.argv:
        # 任务单 #137 需求B（2026-09-16）：取数覆盖度校验。
        #   缘起：DATA_PIPELINE_MAP 有「债券」定义（占组合 42.43%），而取数层 QUERY_SPECS 无对应
        #   条目 → 债券【从未被发起取数】。--check 只校验映射表内部自洽，删掉债券条目依然全绿。
        #   本分支补的正是这一层：把「持仓」与「取数定义」做双向差集，非空即 🔴。
        # ⛔ 只读 portfolio_data.json 与 fetch_registry.json，绝不写入任何文件。
        problems, notes = coverage_check()
        print(f"— 取数覆盖度校验（#137）· 注册表 {REGISTRY_PATH.name} —")
        for n in notes:
            print("  ", n)
        if problems:
            print(f"\n🔴 取数覆盖度未通过（{len(problems)} 项）：")
            for p in problems:
                print("  -", p)
            print("\n   处置：把缺口条目补进 fetch_registry.json（含 pipeline_key / holdings_match / queries），"
                  "或确认该持仓确无取数必要并显式登记原因。")
            return 1
        print("\n✅ 取数覆盖度通过：活跃持仓与取数定义双向对应，无孤儿。")
        return 0

    if "--verify-codes" in sys.argv:
        # inbox/135：报告正文 (代码,名称) 对子 ↔ index_registry.json 一致性校验
        return verify_codes(sys.argv)

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

        # (C) 指数量级跳变护栏（inbox/135 B2：新增一节是**追加**，不动既有两节语义）
        if "--map-only" not in sys.argv:
            print("\n— 指数量级跳变护栏（相邻交易日 |涨跌|：>15% 🔴 / >8% 🟡）—")
            _gres, _gerr = magnitude_check_live()
            if _gerr:
                print(f"  🟡 跳过：{_gerr}（⛔ 不静默通过）")
            else:
                _closes, _fails = _gres
                _rows = magnitude_guard(_closes)
                _flag = [r for r in _rows if r["level"] != "✅"]
                for r in _flag:
                    print(f"  {r['level']} 量级异常：{r['code']} {r['prev']:.2f} → "
                          f"{r['cur']:.2f}（{r['pct']:+.2f}%）—— 指数单日 |±15%| 几乎不可能，"
                          f"先查「是不是换了标的」")
                if not _flag and _rows:
                    print(f"  ✅ {len(_rows)} 个已登记指数相邻交易日无 >8% 跳变")
                if _fails:
                    print(f"  🟡 未取得 {len(_fails)} 个：{'；'.join(_fails[:5])}"
                          f"{'…' if len(_fails) > 5 else ''}（⛔ 不静默通过）")
                if any(r["level"] == "🔴" for r in _rows):
                    hard_fail = 1

        if hard_fail:
            print("\n🔴 --check 未通过：请先按上述 🔴 项处理（通常先跑 sync_all.py）")
            return 1
        print("\n✅ --check 全部通过")
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
