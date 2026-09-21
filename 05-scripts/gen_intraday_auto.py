#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_intraday_auto.py — Anchor 盘中深度报告全自动生成器（v2.0, 2026-09-01 #18 提案落地）
========================================================
全自动：mx-data 行情采集（A股+美股+板块+黄金）→ 规则信号 → 六段式 v2.0 模板 → 落盘 research/

用法: python gen_intraday_auto.py [--dry-run]
产出: Anchor/04-reviews/research/YYYY-MM-DD-盘中研究报告.md（六段式 v2.0）
"""
import json, os, sys, re, subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import fetch_public as fp          # 公共取数兜底层（mx 配额耗尽/失败时的换源）
except ImportError:                     # 兜底：模块缺失不致命，仅失去兜底能力
    fp = None

# ---------- 路径 ----------
DESKTOP = Path("C:/Users/lenovo/Desktop")
ANCHOR = DESKTOP / "Anchor"
DATA = DESKTOP / "portfolio_data.json"
OUT_DIR = ANCHOR / "04-reviews" / "research"
MX_DATA_DIR = Path("C:/Users/lenovo/.workbuddy/skills/mx-data")
MX_PY = Path("C:/Users/lenovo/.workbuddy/binaries/python/envs/mxdata/Scripts/python.exe")
MX_SCRIPT = MX_DATA_DIR / "mx_data.py"
MX_OUT = DESKTOP / "mx_output"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------- 行情采集（mx-data 全自动）----------
QUERIES = [
    "上证指数 科创50 沪深300 中证红利 最新价 涨跌幅",
    "中证全指证券公司指数 国证半导体芯片指数 最新价 涨跌幅 主力资金净流入",
    "恒生港股通创新药指数 最新价 涨跌幅",
    "COMEX黄金期货 最新价 涨跌幅",
    "费城半导体指数 纳斯达克100 最新收盘价 涨跌幅",
]
# 数据必达：主查询失败时换词兜底（禁止空值占位）
FALLBACK_QUERIES = {
    "纳指100": ["纳斯达克100指数 最新收盘", "纳斯达克100 收盘价 涨跌幅", "纳斯达克100指数 今日 收盘价"],
    "费半": ["费城半导体 指数 涨跌幅 收盘", "SOX 费城半导体 最新"],
    "COMEX黄金": ["黄金期货 最新价格 涨跌幅", "上海金 最新价 涨跌幅"],
    "创新药": ["港股通创新药 指数 最新", "恒生创新药 收盘"],
}

def _decode(raw: bytes) -> str:
    """容错解码链。

    🔴 修复记录（2026-09-17）：原实现 `subprocess.run(..., text=True, encoding="utf-8")`
    直接读 mx_data.py 的输出，而其在 Windows 下按 **GBK/cp936** 写出 →
    抛 `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb4` →
    `fetch_mx` 整体走 except 返回错误串 → **指数 0 / 板块 0 / 美股 0，
    却仍生成了一份表格全空的报告**（实发事故，违反「数据必达铁律」）。
    修法：先收 bytes，再按 utf-8 → gbk → cp936 依次尝试，全失败用 replace 兜底。
    """
    if not raw:
        return ""
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def fetch_mx(query: str) -> str:
    """调 mx_data.py，返回 stdout 文本（容错解码，绝不因编码崩溃）"""
    try:
        r = subprocess.run([str(MX_PY), str(MX_SCRIPT), query, str(MX_OUT)],
                           capture_output=True, timeout=120)
        out = _decode(r.stdout or b"")
        if not out.strip():
            return f"[mx-empty] rc={r.returncode} {_decode(r.stderr or b'')[:200]}"
        return out
    except Exception as e:
        return f"[mx-error] {e}"

def _val_chg(c2: str, c3: str) -> tuple[str, str]:
    """按「哪个单元格带 %」判定列序，返回 (值, 涨跌幅)。

    🔴 修复记录（2026-09-17）：mx 对不同查询返回的列序**不固定**——
    A股指数实测返回 `| 上证指数 | -0.37% | 3877.03 |`（涨跌幅在前），
    而美股/黄金返回 `| 收盘价 | 涨跌幅 |`。原实现只在**日期行**分支做了这个判定，
    **名称行**分支直接 `val=c2, chg=c3` → A股指数被**静默地价/涨跌对调**
    （报告里出现「上证 最新 -0.37%，涨跌 3877.03」）。现统一走本函数。
    """
    c2, c3 = (c2 or "").strip(), (c3 or "").strip()
    if c2.endswith("%") and not c3.endswith("%"):
        return c3, c2          # 涨跌幅在前 → 交换
    return c2, c3              # 已正确，或两列/两空无法判定 → 不擅动


def _pick(c2: str, c3: str, cols: tuple | None) -> tuple[str, str]:
    """定列序取 (值, 涨跌幅)。**表头优先**，无表头退化为 `%` 启发式。

    🔴 修复记录（2026-09-17）：`%` 启发式**会失效**——mx 的「最新涨跌幅」列
    实测返回**不带 % 的纯小数**（费半 `| 2026-09-16(日) | 0.6314 | 11246.11点 |`，
    其中 0.6314 就是 0.6314%）。此时两列都不带 % → 不交换 → 报告写成
    「费半 最新 0.6314，涨跌 11246.11点」。mx 同页会输出表头行
    `| date | 最新涨跌幅 | 收盘价 |`，**表头才是权威的列序定义**。
    """
    if cols:
        _, n2, n3 = cols
        is_pct = lambda n: any(k in n for k in ("涨跌", "幅度", "涨幅"))   # noqa: E731
        is_px = lambda n: any(k in n for k in ("收盘", "最新价", "价格", "点位"))  # noqa: E731
        if is_pct(n2) and is_px(n3):
            return c3, c2
        if is_px(n2) and is_pct(n3):
            return c2, c3
    return _val_chg(c2, c3)


def parse_mx(text: str) -> dict:
    """从 mx_data stdout 提取 名称→(最新值, 涨跌幅)。
    兼容两种输出：①名称行（| 名称 | 值 | 涨跌 |）②标题行（**名称(代码)的xx** + 历史数据表首行=最新）"""
    out = {}
    cur_name = None
    cols = None                 # 当前表的表头列名——权威列序定义
    lines = text.splitlines()
    for i, line in enumerate(lines):
        # 标题行：**费城半导体指数(SOX.GI)(指数)的涨跌幅、收盘价**
        m = re.match(r"\*\*(.+?)[(（][^)]*[)）]?.*?(?:指数|的)", line)
        if m:
            nm = m.group(1).strip()
            if nm and len(nm) < 30:
                cur_name = nm
                out.setdefault(nm, {"val": None, "chg": None})
            cols = None                      # 新表开始 → 表头作废
            continue
        # 数据行：| 2026-08-31(日) | 0.57% | 11535.05点 | 或 | 名称 | 值 | 涨跌 |
        m = re.match(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            c1, c2, c3 = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            # 分隔行 | --- | --- | --- | → 跳过
            if re.match(r"^[-:\s]+$", c2) and re.match(r"^[-:\s]+$", c3):
                continue
            # 表头行：**下一行是分隔行**且本行无数字 → 本行定义列序（权威列序定义）
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if re.match(r"^\|[\s\-:|]+\|?\s*$", nxt) and not re.search(r"\d", c2 + c3):
                cols = (c1, c2, c3)
                continue
            # 首列是日期 → 表数据行（最新=第一行）；首列是中文名 → 名称行
            if re.match(r"^\d{4}-\d{2}-\d{2}", c1):
                if cur_name and out.get(cur_name, {}).get("val") is None:
                    out[cur_name]["val"], out[cur_name]["chg"] = _pick(c2, c3, cols)
            elif re.match(r"^[\u4e00-\u9fa5]", c1) and len(c1) < 30:
                name = re.split(r"[(（]", c1)[0].strip()
                v, ch = _pick(c2, c3, cols)
                out[name] = {"val": v, "chg": ch}
    return out

# 公共 API 兜底映射（东财 secid）。mx 取不到的类别走这里换源，
# 落实「📡 数据必达铁律：禁止空值占位，拿不到就换源重试」。
# 🔴 勘误（2026-09-18）：原注释写「纳指100 **刻意不列**」，理由是「东财 100.NDX 实为
#    纳斯达克综合」——**前半句对，后半句是错误外推**：**禁用一个错码 ≠ 该指数无源**。
#    正确码 `100.NDX100` 一直可用（实测 29,462.74），腾讯 `usNDX` 亦回 91 根日K。
#    ⇒ 该类别**升级为一级源**，ETF 513100 降为**二级兜底**（见 `_PUBLIC_OTHER` / `_PUBLIC_SUB`）。
#    ⚠️ 同型两次：v4.4.13 B4'（push2his 被误判无源，实为端点没找对）／v4.4.8（用错码 sz399811）。
#    📌 **纪律**：写下「无源」前必须穷尽端点，且必须记录**「正确码/正确端点是什么」** ——
#       只记「某个码不能用」的档案，会让后人重复得出同一个错误结论。
_PUBLIC_IDX = {
    "上证": "1.000001", "科创50": "1.000688", "沪深300": "1.000300",
    "中证红利": "1.000922",
}
# 🔴 修复记录（2026-09-17）：板块项原先混在 _PUBLIC_IDX 里，而兜底只回填
# `market["indices"]` → **板块永远拿不到兜底**，熔断时恒报「板块 0/3」。
# 现按落地类别拆成两张表，`_public_fallback` 各归其位。
_PUBLIC_SECTOR = {
    "证券": "0.399975",        # 中证全指证券公司指数
    "半导体": "0.980017",      # 国证芯片（⛔ 勿用 sz399811＝CSSW电子，量级差 2.2 倍）
    "创新药": "124.HSSCID",    # 恒生港股通创新药指数（⛔ 非 987018＝港股通创新药，差约 39%）
}
# ⚠️ 费半（SOX）**无免费公共源**：实测 `100.SOX/SOXS/PHLX/SOXX` 全部 data:null，
#    而同批 `100.DJIA/SPX/N225/KS11/TWII` 均可用 → 东财确实不收录 SOX。
#    → 费半只能取自 mx-data；mx 失败时按「数据必达铁律」显式标缺口，不得占位。
# 🔴 纳指100 一级源 = **东财 `100.NDX100`**（真指数点位，2026-09-18 修复）。
#    ⛔ `100.NDX` 是**纳斯达克综合**（差约 3000 点）—— 勿写回。
#    `_public_fallback` 的外盘分支按 label 落 `market["us"]`，故此处加入即可生效，
#    且因「权威源优先 + 先写先赢」，`_PUBLIC_SUB` 的 ETF 兜底会自动让位（顺序即优先级）。
_PUBLIC_OTHER = {"COMEX黄金": "101.GC00Y", "纳指100": "100.NDX100"}
# 二级兜底：真指数也取不到时，才退回 ETF 替代口径（量纲不同，见《v2.3》§二.13 O1）。
_PUBLIC_SUB = {"纳指100": ("1.513100", "纳指100ETF(513100)")}


def _public_fallback(market: dict) -> None:
    """mx 缺失项 → 公共 API 换源补齐。补齐的每条打 `_src` 标记，报告须据实标注来源。"""
    if fp is None:
        return
    q = fp.index_quotes(list(_PUBLIC_IDX.values()) + list(_PUBLIC_SECTOR.values()),
                        source="兜底·指数/板块")
    for cat, mp in (("indices", _PUBLIC_IDX), ("sectors", _PUBLIC_SECTOR)):
        for label, secid in mp.items():
            if market[cat].get(label, {}).get("val"):
                continue                                # mx 已有值，不覆盖（权威源优先）
            d = q.get(secid)
            if d and d.get("price") is not None:
                market[cat][label] = {
                    "val": d["price"], "chg": f"{d['chg_pct']}%", "_src": "东财·公共API"}

    q2 = fp.index_quotes(list(_PUBLIC_OTHER.values()), source="兜底·外盘")
    for label, secid in _PUBLIC_OTHER.items():
        cat = "gold" if label == "COMEX黄金" else None
        cur = market["gold"] if cat else market["us"].get(label)
        if cur and cur.get("val"):
            continue
        d = q2.get(secid)
        if d and d.get("price") is not None:
            item = {"val": d["price"], "chg": f"{d['chg_pct']}%", "_src": "东财·公共API"}
            if cat:
                market["gold"] = item
            else:
                market["us"][label] = item

    for label, (secid, shown) in _PUBLIC_SUB.items():
        if market["us"].get(label, {}).get("val"):
            continue
        d = fp.index_quotes([secid], source="兜底·纳指替代口径").get(secid)
        if d and d.get("price") is not None:
            market["us"][label] = {"val": d["price"], "chg": f"{d['chg_pct']}%",
                                   "_src": f"替代口径 {shown}（非指数点位）"}


def collect_market() -> dict:
    """全自动采集：8 查询 → 汇总 dict"""
    market = {"indices": {}, "sectors": {}, "us": {}, "gold": None, "queries": len(QUERIES)}
    for q in QUERIES:
        txt = fetch_mx(q)
        parsed = parse_mx(txt)
        for k, v in parsed.items():
            if "上证" in k: market["indices"]["上证"] = v
            elif "科创" in k: market["indices"]["科创50"] = v
            elif "沪深300" in k: market["indices"]["沪深300"] = v
            elif "红利" in k: market["indices"]["中证红利"] = v
            elif "证券" in k: market["sectors"]["证券"] = v
            elif "芯片" in k: market["sectors"]["半导体"] = v
            elif "创新药" in k: market["sectors"]["创新药"] = v
            elif "COMEX" in k or "黄金" in k: market["gold"] = v
            elif "费城" in k or "半导体指数" in k: market["us"]["费半"] = v
            elif "纳斯达克100" in k: market["us"]["纳指100"] = v
    # 数据必达兜底：缺失项换查询词重试
    for cat, key in (("us", "费半"), ("us", "纳指100"), ("gold", None), ("sectors", "创新药")):
        tgt = market[cat] if key is None else market[cat].get(key)
        if tgt is None or (isinstance(tgt, dict) and not tgt.get("val")):
            for alt in FALLBACK_QUERIES.get(key or "COMEX黄金", []):
                for k, v in parse_mx(fetch_mx(alt)).items():
                    if key is None and ("COMEX" in k or "黄金" in k): market["gold"] = v
                    elif key == "费半" and ("费城" in k or "半导体" in k): market["us"]["费半"] = v
                    elif key == "纳指100" and "纳斯达克" in k: market["us"]["纳指100"] = v
                    elif key == "创新药" and "创新药" in k: market["sectors"]["创新药"] = v
    # 二级兜底：公共 API 换源（mx 配额耗尽时唯一出路）
    _public_fallback(market)
    # 补充数据块：板块资金两端 / 南向 / 中国10Y（含替代口径）—— 免费公开 API
    if fp is not None:
        market["sector_flow"] = fp.sector_flow(top=10)
        market["southbound"] = fp.southbound()
        market["cn10y"] = fp.cn10y()
        market["bond_refs"] = fp.bond_refs()
    return market


def coverage(market: dict) -> dict:
    """各类别**实际取到值**的条数——零值熔断的判据。"""
    n = lambda d: sum(1 for v in d.values() if v and v.get("val") is not None)  # noqa: E731
    return {
        "指数": n(market["indices"]), "指数_需": len(_PUBLIC_IDX),
        "板块": n(market["sectors"]), "板块_需": len(_PUBLIC_SECTOR),
        "美股": n(market["us"]), "美股_需": 2,
        "黄金": 1 if (market.get("gold") or {}).get("val") else 0, "黄金_需": 1,
    }

# ---------- 持仓数据 ----------
def load_portfolio() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))

# ---------- 渲染辅助 ----------
def _srcmark(d: dict | None) -> str:
    """来源标记：非 mx 权威源取到的值必须标出，供读者判断可信度。"""
    s = (d or {}).get("_src")
    return f" ⚠️源:{s}" if s else ""


def _append_flow(lines: list, market: dict) -> None:
    """板块资金两端 / 南向资金 / 中国10Y —— 三个 2026-09-17 修复项的输出段。"""
    sf = market.get("sector_flow")
    if sf:
        lines.append(f"\n### 板块资金（东财公共API｜{sf['ts']} 快照，**非收盘**）\n")
        lines.append(f"板块总数 **{sf['total_sectors']}**"
                     "（⚠️ 只取单端前 N 名会得「全部净流入」的取样假象——"
                     "本表**两端都取**，故能看见真实分化）\n")
        lines.append("| 净流入端（主力） | 亿 | 板块涨跌 | ｜ | 净流出端（主力） | 亿 | 板块涨跌 |")
        lines.append("|---|---|---|---|---|---|---|")
        for i in range(max(len(sf["inflow"]), len(sf["outflow"]))):
            a = sf["inflow"][i] if i < len(sf["inflow"]) else None
            b = sf["outflow"][i] if i < len(sf["outflow"]) else None
            ca = f"**{a['name']}** | {a['net_yi']:+} | {a['chg_pct']}%" if a else "— | — | —"
            cb = f"**{b['name']}** | {b['net_yi']:+} | {b['chg_pct']}%" if b else "— | — | —"
            lines.append(f"| {ca} ｜ | {cb} |")
    else:
        lines.append("\n### 板块资金\n- 🔴 **取数失败**（已试 mx + 东财公共API 两端）\n")

    sb = market.get("southbound")
    if sb and sb.get("ok"):
        lines.append(f"\n### 南向资金（东财 datacenter）\n")
        flag = "⚠️ **T-1 日终值**（当日须港股收盘后才有）" if sb.get("is_t_minus_1") else "当日"
        lines.append(f"**数据日期 {sb['date']}**（{flag}）｜单位：{sb['unit']}\n")
        lines.append("| 通道 | 净流入(百万港元) | 买入 | 卖出 |")
        lines.append("|---|---|---|---|")
        for d in sb["detail"]:
            n = d.get("net_mhkd")
            lines.append(f"| {d['label']} | {n:+} | {d['buy_mhkd']} | {d['sell_mhkd']} |"
                         if n is not None else
                         f"| {d['label']} | 🔴 缺 | {d['buy_mhkd']} | {d['sell_mhkd']} |")
        # 🔴 「合计」行只在 **合计可信**（`complete`）时输出（2026-09-21 改，v4.5.11）——
        #    原写法**自己把两腿相加**，单腿挂时贴出一个**偏低 98.6%** 的数
        #    （实测 9/18：报 0.17 亿，真值 11.93 亿），且 `ok=True`、无报错。
        #    现改为**直取官方合计行 `006`**，并把「依据」显式写出来。
        if sb.get("complete") and sb.get("total_mhkd") is not None:
            lines.append(f"| **合计** | **{sb['total_mhkd']:+}（{sb['total_yi']:+} 亿）** | | |")
            basis = sb.get("total_basis") or ""
            if "006" not in basis:
                lines.append("")
                lines.append(f"- ⚠️ 合计口径＝**{basis}**（官方合计行 `006` 当日缺失，**已降级为分腿求和**）")
            cc = sb.get("cross_check") or {}
            if cc and not cc.get("match"):
                lines.append("")
                lines.append(f"- 🔴 **合计行与分腿不符**：合计行 **{cc.get('total_row')}** vs 分腿之和 "
                             f"**{cc.get('legs_sum')}** —— 已按合计行取值，但**须人工复核**"
                             f"（`006` 的编号含义可能被数据方改动）")
            if not sb.get("legs_complete", True):
                miss = "、".join(sb.get("missing_legs") or [])
                lines.append("")
                lines.append(f"- ⚠️ 分腿不齐（缺 {miss}）；**合计行在场 ⇒ 上方合计仍可信**，"
                             f"但该腿明细缺失、不可从合计倒推")
        else:
            miss = "、".join(sb.get("missing_legs") or []) or "官方合计行"
            lines.append("")
            lines.append(f"- 🔴 **无法给出可信的南向合计**（缺 {miss}）—— **上方不列「合计」行**。"
                         f"⛔ 各腿之和不等于南向净流入，**不得相加后当合计引用**。")
    else:
        lines.append(f"\n### 南向资金\n- 🔴 **取数失败**：{(sb or {}).get('note', '未知')}\n")

    c = market.get("cn10y") or {}
    br = market.get("bond_refs") or {}
    lines.append("\n### 中国 10 年期国债收益率\n")
    if c.get("value") is not None:
        # 🔴 **数据日期与取数时刻分开标注** —— 不得只写其中一个：
        #    只写 `ts` 会把「我今天取的」误当成「今天的数据」（v2.3 §二.13 三源拆分各注时点）。
        _dd = c.get("date") or "⚠️未知"
        lines.append(f"- **{c['value']}%**（**数据日期 {_dd}**｜取数时刻 {c['ts']}｜源 "
                     f"{c.get('source') or '—'}）\n")
    else:
        # ⚠️ `n_sources_tried` **缺键**与**真的试了 0 个源**必须长得不一样 ——
        #    原写法 `.get(..., 0)` 把两者渲染成同一句「已试 0 源全部失败」，
        #    而缺键的真实含义是「**这个 key 根本没进 market**」（如 `fp is None`，
        #    见本文件上方 `if fp is not None:` 守卫）⇒ **「没发起」被读成「试过并失败」**。
        n = c.get("n_sources_tried")
        if n is None:
            lines.append("- 🔴 **无法获取** —— ⚠️ **未发起取数**（该结果不在 market 中，"
                         "非「试过 N 源皆失败」）\n")
        else:
            lines.append(f"- 🔴 **无法获取** —— 已试 **{n} 源**全部失败；"
                         f"{c.get('note', '')}\n")
        q = br.get("quotes") or {}
        if q:
            lines.append("- **替代口径**（国债现券 / 国债ETF 价格）：")
            for k, v in q.items():
                if v:
                    lines.append(f"\n  - {k}：**{v['price']}**（{v['chg_pct']:+}%）")
            lines.append(f"\n  - ⚠️ 已知偏差方向：{br.get('direction_note', '')}")
            lines.append("\n  - ⛔ 禁止用途：**不得当作收益率数值引用**（量纲不同、方向相反）")


# ---------- 六段式模板 ----------
def render_report(market: dict, data: dict, ts: str) -> str:
    idx = market["indices"]; sec = market["sectors"]; us = market["us"]
    g = lambda d, k, f: d[k][f] if k in d else "—"
    lines = []
    lines.append(f"# 📈 Anchor 盘中研究报告 — {ts}")
    lines.append(f"\n**数据时点**：{ts}（mx-data 全自动采集 {market['queries']} 查询 ＋ 东财公共API 兜底）"
                 f"｜ 持仓 = {data.get('update_date','?')}")
    lines.append("\n> ⚠️ **本表行情为采集时点的盘中快照，非收盘价**。"
                 "按《报告深度标准 v2.3》§二.13 与手册附录E · **F5**，"
                 "**未经收盘确认的价不得作任何触发线判据**。标 `⚠️源:` 者来自兜底源，非 mx 权威源。")
    lines.append("\n---\n\n## 一、市场实时全景\n")
    lines.append("| 指数 | 最新 | 涨跌 |")
    lines.append("|------|------|------|")
    for k in ("上证","科创50","沪深300","中证红利"):
        if k in idx: lines.append(f"| {k} | {idx[k]['val']} | {idx[k]['chg']}{_srcmark(idx[k])} |")
    lines.append("\n### 板块\n")
    lines.append("| 板块 | 最新 | 涨跌 |")
    lines.append("|------|------|------|")
    for k in ("证券","半导体","创新药"):
        if k in sec: lines.append(f"| {k} | {sec[k]['val']} | {sec[k]['chg']}{_srcmark(sec[k])} |")
    lines.append(f"\n### 隔夜美股（自动采集）\n")
    lines.append("| 指数 | 收盘 | 涨跌 |")
    lines.append("|------|------|------|")
    for k in ("费半","纳指100"):
        if k in us: lines.append(f"| {k} | {us[k]['val']} | {us[k]['chg']}{_srcmark(us[k])} |")
    if market["gold"]:
        g = market["gold"]
        lines.append(f"\n**COMEX 黄金**：{g['val']}（{g['chg']}）{_srcmark(g)}")
    _append_flow(lines, market)
    lines.append("\n---\n\n## 二、持仓全景（自动）\n")
    lines.append("| 持仓 | 市值(估) | 备注 |")
    lines.append("|------|---------|------|")
    for h in data.get("holdings_summary", []):
        if h.get("mv", 0) > 0:
            lines.append(f"| {h['name']} | ¥{h['mv']:,.2f} | {h.get('note','')[:40]} |")
    stk = data.get("stock_holdings") or []
    for s in stk:
        lines.append(f"| {s['name']} | ¥{s.get('mv',0):,.2f} | 股票 |")
    lines.append(f"\n**总资产**：¥{data.get('total_assets',0):,.2f}（基金 {data.get('fund_account',0):,.2f} + 股票 {data.get('stock_account',0):,.2f}）")
    lines.append("\n---\n\n## 三、规则信号（自动）\n")
    # 信号：读 daily_advice 或 data_processor（此处简版：pending_actions + 额度）
    ops = (data.get("_meta") or {}).get("ops_state") or {}
    lines.append(f"- 月操作额度：{ops.get('count','?')}/{ops.get('max','4')}")
    for a in data.get("pending_actions", []):
        lines.append(f"- ⏰ {a.get('name','')}：{a.get('action','')[:60]}")
    lines.append("\n---\n\n## 四、操作建议（模板待人工填充规则引用）\n")
    lines.append("- 依据评分卡 + pre_trade_check 输出（手动核对触发条件）")
    lines.append("\n---\n\n## 五、新机会扫描（watchlist 自动）\n")
    # 🔴 v4.5.1：原为**人工占位符**（「人工补充：连红天数/触发条件」），
    #    与 `watchlist[].today` 字段同属「写了没人接」。现改为**计算并渲染**。
    lines.append(f"> 判据：**手册 §4.4 v3.10** —— ① A2 不成立（§2.1 原文口径）＋ ② 标的当日收盘价 ≥ 当日 MA5。"
                 f"**额度限 ¥300-500 试探**，级别 `E`（条件成立后 T+1 日 14:30 前须出显式裁定）。\n")
    try:
        import gen_watchlist_status as _gws
        _st = _gws.build_status(data, _gws._load_json(_gws.CONTRACT_PATH, {}) or {}, datetime.now())
        _u = _st["board_source"]["universes"] or {}
        _us = "；".join(f"{k} {v['fetched']}/{v['total']}" for k, v in _u.items()) or "不可用"
        lines.append(f"**板块源**：{_us}（全量={_st['board_source']['complete']}）"
                     f"—— 🔴 板块有**两套互不覆盖的宇宙**（行业 / 概念），只查一套时另一套主题"
                     f"**永远匹配不到**且失败长相是「该板块不存在」。\n")
        lines.append("| 板块 | 标的 | 收盘/M | A2 | 条件② | 状态 |")
        lines.append("|------|------|--------|----|-------|------|")
        for e in _st["entries"]:
            _tech = (f"{e['close']} / MA{e['ma_period']} {e['ma']}" if e["ma"] is not None
                     else "—")
            _a2 = ("⛔命中" if e["a2_hit"] else ("✅不成立" if e["a2_ok"] else "⚪部分可判"))
            _d5 = ("✅成立" if e["d5_ok"] else ("❌未成立" if e["d5_ok"] is not None else "—"))
            lines.append(f"| {e['sector']} | {e['code']} | {_tech} | {_a2} | {_d5} | {e['verdict']} |")
        lines.append("")
        for e in _st["entries"]:
            lines.append(f"- **{e['sector']}**：{e['reason']}")
            lines.append(f"  - 数据时点 {e['data_time']} · 收盘已定格={e['close_confirmed']}"
                         f" · 源：{'、'.join(e['sources']) or '无'}")
            _gaps = list(e["missing"]) + ([e["a2_gap"]] if e.get("a2_gap") else [])
            if _gaps:
                lines.append(f"  - ⚪ **缺口声明**：{'；'.join(_gaps)}")
            if e["caveats"]:
                lines.append(f"  - ⚠️ **须裁决**：{'；'.join(e['caveats'])}")
        if _st["any_partial_a2"]:
            lines.append(f"\n> 🔴 **A2 判据部分无源声明**：手册 §2.1 要求读「**前一交易日板块指数收盘涨幅**」，"
                         f"该源**结构性无源**（东财板块日K：`push2his` 非 JSON、`push2delay` 回 0 条，"
                         f"已试 2 主机）。**只有落在 (0%, 2%) 区间的条目**受影响 —— "
                         f"当日 ≤0 时「连续 2 日飘红」逻辑上不可能，结论完全确定。"
                         f"受影响条目的状态**一律不授予买入许可**（A2 是 `X` 执行级，判不了 ⇒ 不放行）。")
    except Exception as _exc:  # noqa: BLE001
        lines.append(f"- ⚪ **watchlist 状态生成失败**：{type(_exc).__name__} {_exc}")
        lines.append("- （**不以旧值或占位符冒充** —— 数据必达铁律 / fail-loud）")
    lines.append("\n---\n\n## 六、风险快照\n")
    lines.append("- 自动提示：板块涨跌极端值/黄金方向/美股联动（人工确认 B5/止损线）")
    lines.append(f"\n---\n\n*全自动生成：{ts} ｜ gen_intraday_auto.py v2.1（#18 提案 ＋ 2026-09-17 修复）"
                 "｜ 行情 mx-data 为主、东财公共API 兜底，非记忆值*")
    if fp is not None and fp.PROBE_LOG:
        ok = sum(1 for r in fp.PROBE_LOG if r["ok"])
        lines.append(f"\n**附·取数留痕**：本报告共发起 {len(fp.PROBE_LOG)} 次公共API 请求，"
                     f"成功 {ok} 次。逐条明细见脚本 `fetch_public.PROBE_LOG`。")
    return "\n".join(lines)

# ---------- main ----------
def main() -> int:
    dry = "--dry-run" in sys.argv
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    market = collect_market()
    cov = coverage(market)

    # ---------- 🚨 零值熔断（2026-09-17 新增）----------
    # 取数全灭时**拒绝出报告**，而不是产出一份表格全空的骨架、打印「✅ 已生成」。
    # 触发本熔断的真实事故：GBK 解码崩溃 → 指数 0/板块 0/美股 0，报告照出（2968 字节）。
    # 语义：**「拿到一个价」与「拿到报告」是两回事**——没有数据就没有报告。
    dead = [k for k in ("指数", "板块", "美股") if cov[k] == 0]
    if dead:
        print("🔴 零值熔断：以下类别完全没有取到任何值 → **拒绝生成报告**")
        for k in dead:
            print(f"   ✗ {k}：0/{cov[k + '_需']}")
        print(f"   取数覆盖度：{json.dumps(cov, ensure_ascii=False)}")
        if fp is not None:
            fails = [r for r in fp.PROBE_LOG if not r["ok"]]
            for r in fails[:8]:
                print(f"   · [{r['source']}] {r['note']}")
            if len(fails) > 8:
                print(f"   · …另有 {len(fails) - 8} 条失败留痕")
        print("\n   处置：① 查 mx-data 配额（返回 code=113 ＝ 6 个妙想 skill 共用池耗尽）"
              "\n         ② 公共 API 兜底已自动启用；仍为空说明网络亦不可达"
              "\n         ③ ⛔ 不得手工放行空报告 —— violates「📡 数据必达铁律」")
        return 2

    data = load_portfolio()
    md = render_report(market, data, ts)
    if dry:
        print(f"[dry-run] 熔断通过，覆盖度 {json.dumps(cov, ensure_ascii=False)}；未落盘")
        print(md[:600])
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fname = OUT_DIR / f"{datetime.now().strftime('%Y-%m-%d')}-盘中研究报告.md"

    # ---------- 🛡️ 防覆盖护栏（2026-09-17 新增）----------
    # 本脚本与人工正式报告**共用同一路径**。若无条件写入，一次误跑就会把
    # 指挥端手写的完整报告换成自动骨架 —— 而「历史归档是时点记录，
    # 改写破坏审计链」。故：目标文件若**不含自动生成标记**即判定为人工报告，
    # 拒绝覆盖，改写入 `<名>.auto.md`。
    if fname.exists():
        try:
            existing = fname.read_text(encoding="utf-8", errors="replace")
        except OSError:
            existing = ""
        if "gen_intraday_auto.py" not in existing:
            alt = fname.with_suffix(".auto.md")
            print(f"🛡️ 防覆盖护栏：{fname.name} 为**人工报告**（无自动生成标记）")
            print(f"   → 拒绝覆盖，改写 {alt.name}")
            fname = alt

    fname.write_text(md, encoding="utf-8")
    print(f"✅ 全自动报告已生成: {fname}")
    print(f"   取数覆盖度: {json.dumps(cov, ensure_ascii=False)}")
    if fp is not None:
        ok = sum(1 for r in fp.PROBE_LOG if r["ok"])
        print(f"   取数留痕: {ok}/{len(fp.PROBE_LOG)} 次请求成功")
    return 0

if __name__ == "__main__":
    sys.exit(main())
