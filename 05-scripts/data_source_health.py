# -*- coding: utf-8 -*-
"""
Anchor 数据源健康矩阵 v1.0（2026-09-16 · 任务单 #138 需求 A/B/C/D）

【为什么存在】
9/16 深度复盘 §④ 的四项方法论限制是同一个病：
    「源不可用 / 不可判时，系统没有机器可读的降级记录，只能由指挥端人工写一段声明。」
本模块把三件事从【人工叙述】变成【机器可读字段】：
    ① 源健康      —— grade 三态 + 每次尝试留痕（源名/结果/时刻）
    ② 是否已收盘  —— close_confirmed（不同市场收盘时刻不同）
    ③ 降级与替代  —— substitute.used / kind / known_bias

【铁律】
  - 本模块【只读】portfolio_data.json，绝不写入（归 WorkBuddy）
  - 不得为拿数据突破 mx-data 配额：#131 专治，500 次/日为 6 个妙想 skill 共用账户池
  - 不承诺「所有源永远可用」——承诺的是【失败可见、降级可读、偏差可算】

【用法】
  python data_source_health.py --show           # 打印当前健康矩阵
  python data_source_health.py --probe 124.HSSCID --label 恒生港股通创新药指数
  python data_source_health.py --close 港股     # 查某资产类别的收盘判定
"""
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
HEALTH_PATH = HERE / "data_source_health.json"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Anchor/1.0"}


# ============================================================
# 需求 B（#138）· 时段感知：资产类别 → 收盘时刻（北京时间）
# ============================================================
# 「拿到一个价」不等于「拿到收盘价」——不同市场收盘时刻不同。
# 本表把「跨日界事件必须实算，不得推算」这条铁律（宏观事件应对预案 §5.4）变成代码里的一张表，
# 而不是每次靠人算。
CLOSE_RULES = {
    "a_share": {
        "confirmed_after": "15:00",
        "note": "A股当日 15:00 收盘",
    },
    "hk": {
        "confirmed_after": "16:00",
        "note": "港股当日 16:00 收盘",
    },
    "cn_fund_nav": {
        "confirmed_after": "20:00",
        "note": "场外基金净值通常 20:00–24:00 陆续披露（各基金公司不同）；QDII 为 T+1",
    },
    "us": {
        # 美东 16:00 收盘 = 北京次日 04:00（冬令时 05:00）。EDT = ET+12。
        "confirmed_after": "05:00",
        "open_from": "21:30",
        "note": "美股交易时段 = 北京 21:30–次日 04:00(EDT)；05:00 后视为前一场已收盘确认",
    },
    "cash": {
        "confirmed_after": "00:00",
        "note": "现金类无收盘概念",
    },
}


def _t(s):
    h, m = str(s).split(":")
    return int(h) * 60 + int(m)


def close_confirmed(close_class, now=None, data_date=None):
    """判断【现在读到的一个值】是否已是收盘确认值。

    返回 (confirmed: bool, reason: str)

    ⚠️ 语义（勿误用）：
      - confirmed=False 的读数必须在报告中显式标为「盘中读数」，
        且【不得作为任何触发线的判据】—— 手册 附录E · F5 要求声明「读哪个价 + 读价钟点」，
        盘中价与收盘价是两个不同的判据源。
      - data_date 若早于今天，说明读到的是【已结算的历史收盘值】，一律 confirmed=True。
    """
    now = now or datetime.now()
    cls = str(close_class or "").strip()
    rule = CLOSE_RULES.get(cls)
    if not rule:
        return False, f"未知资产类别「{cls}」——收盘判定不可得（标为盘中读数，勿作触发判据）"

    if cls == "cash":
        return True, "现金类无收盘概念"

    today = now.strftime("%Y-%m-%d")
    if data_date and str(data_date)[:10] < today:
        return True, f"读到的是已结算历史值（数据日期 {data_date} < 今日 {today}）"

    cur = now.hour * 60 + now.minute
    after = _t(rule["confirmed_after"])

    if cls == "us":
        open_at = _t(rule.get("open_from", "00:00"))
        # 美股交易时段（北京 21:30–次日 04:00）内 → 盘中
        if cur >= open_at or cur < after:
            return False, f"美股交易时段内（{rule['note']}）"
        return True, f"美股前一场已收盘（{rule['note']}）"

    if cur >= after:
        return True, f"{rule['note']}（当前 {now.strftime('%H:%M')} ≥ {rule['confirmed_after']}）"
    return False, f"未到收盘时刻（{rule['note']}；当前 {now.strftime('%H:%M')} < {rule['confirmed_after']}）"


def close_class_of(market_or_class):
    """宽松解析：接受 '港股' / 'A股' / '美股' / '场外基金' 等中文，映射到 CLOSE_RULES 键。"""
    s = str(market_or_class or "")
    if s in CLOSE_RULES:
        return s
    if any(k in s for k in ("A股", "沪深", "场内")):
        return "a_share"
    if any(k in s for k in ("港股", "香港", "HS")):
        return "hk"
    if any(k in s for k in ("美股", "美东", "QDII", "纳指")):
        return "us"
    if any(k in s for k in ("场外", "净值", "债券", "基金")):
        return "cn_fund_nav"
    if "现金" in s:
        return "cash"
    return ""


# ============================================================
# 需求 A（#138）· 健康矩阵
# ============================================================
GRADES = ("real", "degraded", "rate_limited", "unavailable")


def grade_for_failure(prev: dict | None) -> str:
    """inbox/140 R1：失败态判据——**只看历史是否成功过**（⛔ 不看错误类型/错误文案）。

    历史成功证据：`prev.last_ok` 非空，或 `attempted_sources` 中存在 `ok=true` 的记录。
    有 → `rate_limited`（端点存在，本次限流/间歇失败——判不触发＋留痕，不修源）；
    无 → `unavailable`（结构性无源——走替代口径，不重复尝试）。
    """
    if not prev:
        return "unavailable"
    if prev.get("last_ok"):
        return "rate_limited"
    for a in (prev.get("attempted_sources") or []):
        if isinstance(a, dict) and a.get("ok"):
            return "rate_limited"
    return "unavailable"


class HealthMatrix:
    """机器可读的源健康记录。每次源尝试都留痕 —— 这是排查「为什么又没取到」的唯一依据。

    grade 四态（inbox/140 R1 裁定 · 2026-09-23 由三态扩为四态）：
      real         = 原始口径可用
      degraded     = 用了替代口径（必须带 substitute.used/kind/known_bias）
      rate_limited = **端点确认存在，本次因限流/间歇失败取不到** ⇒ 判不触发＋留痕；
                     ⛔ **不修源**（限流是待尊重的事实），下次再试
      unavailable  = **结构性无源**（该源从未成功过，源本身不提供该字段）
    判据（141 R1）：失败态**只看历史是否成功过**（`grade_for_failure()`）——
    ⛔ 不得靠错误类型猜测（RemoteDisconnected 也可能是网络故障）。
    """

    def __init__(self):
        self.targets = {}
        self._reset_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")

    # ---- 跨运行追加（#138 B-4：两次读数都保留，不得覆盖）----
    @classmethod
    def load(cls, path=None):
        """加载既有矩阵并【保留其 readings】——当日盘中一次 + 次日清晨一次必须共存。

        为什么必须跨运行保留：B-4 要的是「同一标的、不同时刻的两个读数并存」。
        若每次运行都新建空矩阵，盘中读数会被清晨重取覆盖，
        报告端就再也无法回溯「这个收盘值是怎么从盘中值变过来的」。
        """
        m = cls()
        p = Path(path or HEALTH_PATH)
        if not p.exists():
            return m
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return m
        prev = d.get("targets") or {}
        for k, v in prev.items():
            m.targets[k] = {
                "official_name": v.get("official_name"),
                "grade": v.get("grade"),
                # attempted_sources 保留最近若干轮，避免无限膨胀
                "attempted_sources": list(v.get("attempted_sources") or [])[-60:],
                "substitute": v.get("substitute"),
                "series_days": v.get("series_days"),
                "last_ok": v.get("last_ok"),
                "readings": list(v.get("readings") or []),
            }
        return m

    def reading(self, target, value, close_confirmed=None, at=None,
                source=None, close_class=None, note="", data_date=None, field=None):
        """登记一次【读数】。**append-only，永不覆盖**（#138 B-4）。

        同一标的当日可有多条：盘中一条（close_confirmed=false）+ 收盘后/次日清晨一条
        （true）。报告端据此判断「用的是哪一个读数」。

        ⚠️ `data_date` = 该读数【所属的数据日期】（不是读到的时刻，`at` 才是时刻）。
           2026-09-17 新增，起因是一次真事故：复用路径拿不到数据日期，就把复用时的
           `today` 填了进去 —— 【9/16 的净值涨跌被标成 9/17 的数据】。
           时间准确性铁律：不确定就标未知，**不得编造一个**。
        """
        t = self.targets.setdefault(str(target), {
            "official_name": None, "grade": None, "attempted_sources": [],
            "substitute": None, "series_days": None, "last_ok": None, "readings": [],
        })
        t.setdefault("readings", [])
        rec = {
            "value": value,
            "at": at or datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "close_confirmed": close_confirmed,
            "close_class": close_class,
            "data_date": data_date,
            "field": field,
            "source": source,
            "note": note,
        }
        t["readings"].append(rec)
        return rec

    def latest_reading(self, target, confirmed_only=False):
        """取【时间上最新】的一条读数。

        ⚠️ 为什么按 at 排序而不是取 list 末条：readings 是 append-only，
        而写库顺序未必等于时间顺序——例如用 --at 注入「次日清晨 06:30」时，
        它排在「当日盘中 23:50」之后，但时间更早。按追加顺序取末条会取错。
        confirmed_only=True 时只在 close_confirmed 为真的读数里取
        （＝「用收盘值，别用盘中读数」，对应手册 附录E · F5）。
        """
        t = self.targets.get(str(target)) or {}
        rs = [r for r in (t.get("readings") or []) if r.get("at")]
        if confirmed_only:
            rs = [r for r in rs if r.get("close_confirmed")]
        if not rs:
            return None
        return max(rs, key=lambda r: str(r["at"]))

    # ---- 记录 ----
    def attempt(self, target, source, result, ok=False):
        """记录一次源尝试（A-2）。失败与成功都记 —— 只记最终状态无法排查。"""
        t = self.targets.setdefault(str(target), {
            "official_name": None, "grade": None, "attempted_sources": [],
            "substitute": None, "series_days": None, "last_ok": None, "readings": [],
        })
        stamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
        t["attempted_sources"].append({
            "source": str(source), "result": str(result)[:300], "ok": bool(ok), "at": stamp,
        })
        if ok:
            t["last_ok"] = stamp
        return t

    def finalize(self, target, grade, official_name=None, substitute=None,
                 series_days=None, extra=None):
        """置最终等级。grade 必须 ∈ GRADES；degraded 必须带完整 substitute（A-3）。"""
        if grade not in GRADES:
            raise ValueError(f"grade 必须是 {GRADES} 之一，收到「{grade}」")
        t = self.targets.setdefault(str(target), {
            "official_name": None, "grade": None, "attempted_sources": [],
            "substitute": None, "series_days": None, "last_ok": None, "readings": [],
        })
        if substitute:
            missing = [k for k in ("used", "kind", "known_bias") if not substitute.get(k)]
            if missing:
                raise ValueError(f"substitute 缺字段 {missing} —— A-3 要求 used/kind/known_bias 三字段齐备")
        if grade == "degraded" and not substitute:
            raise ValueError("grade=degraded 必须提供 substitute（A-3：替代口径必须机器可读）")
        t["grade"] = grade
        if official_name:
            t["official_name"] = official_name
        if substitute is not None:
            t["substitute"] = substitute
        if series_days is not None:
            t["series_days"] = series_days
        if extra:
            t.update(extra)
        return t

    # ---- 输出 ----
    def payload(self, probe_time=None):
        return {
            "generated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "probe_time": probe_time or self._reset_at,
            "spec": "Anchor-Software/_handoff/inbox/138_*.md 需求A；本文件由脚本自动写，不得手工维护",
            "grade_meaning": {g: d for g, d in zip(
                GRADES, ("原始口径可用", "用了替代口径（须读 substitute）",
                         "限流性取不到（端点存在、本次失败——判不触发＋留痕；⛔ 不修源，下次再试）",
                         "结构性无源（从未成功过）"))},
            "close_rules": CLOSE_RULES,
            "targets": self.targets,
        }

    def write(self, path=None):
        p = Path(path or HEALTH_PATH)
        p.write_text(json.dumps(self.payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p


# ============================================================
# 需求 C（#138）· 多源兜底链（每跳都记进健康矩阵）
# ============================================================
def _http_json(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _http_text(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _src_eastmoney_push2delay(secid):
    """① 东财 push2delay。⛔ push2his / push2 主域已被 IP 限流（RemoteDisconnected），勿用。"""
    d = _http_json(f"https://push2delay.eastmoney.com/api/qt/stock/get"
                   f"?secid={secid}&fields=f57,f58,f43,f169,f170")
    data = (d or {}).get("data")
    if not data:
        raise ValueError(f"data=null (rc={d.get('rc')})")
    px = data.get("f43")
    if px in (None, "-", ""):
        raise ValueError("f43 为空")
    return {
        "code": data.get("f57"), "name": data.get("f58"),
        "price": px / 100.0 if isinstance(px, (int, float)) else None,
        "chg": (data.get("f169") / 100.0) if isinstance(data.get("f169"), (int, float)) else None,
        "pct": (data.get("f170") / 100.0) if isinstance(data.get("f170"), (int, float)) else None,
    }


def _src_tencent_kline(code, n=30):
    """② 腾讯 fqkline —— 唯一可拿到 K 线序列的源（东财 push2his 全被挡）。"""
    txt = _http_text(f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
                     f"?param={code},day,,,{n},qfq")
    d = json.loads(txt)
    node = (d.get("data") or {}).get(code)
    if not node:
        raise ValueError("data 无该 code 节点")
    bars = node.get("qfqday") or node.get("day") or []
    if not bars:
        raise ValueError("0 根K线")
    last = bars[-1]
    return {"code": code, "bars": len(bars), "last_date": last[0],
            "close": float(last[2]), "source_seq": [b[0] for b in bars[-5:]]}


def _src_sina_kline(symbol, scale=240, datalen=30):
    """③ 新浪 K 线。覆盖有限（部分港股指数无数据）。"""
    txt = _http_text(f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                     f"CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&datalen={datalen}")
    if not txt or txt.strip() in ("null", "[]"):
        raise ValueError("无数据")
    rows = json.loads(txt)
    if not rows:
        raise ValueError("空数组")
    return {"symbol": symbol, "bars": len(rows),
            "last_date": rows[-1].get("day"), "close": float(rows[-1].get("close"))}


def fetch_with_fallback(target, attempts, matrix=None):
    """按序跑 attempts=[(源名, 调用函数)]，第一个成功即返回；**每一跳都记进健康矩阵**。

    返回 (ok: bool, payload: dict|None, chain: list[(源名, 结果, 是否成功)])
    """
    chain = []
    for name, fn in attempts:
        try:
            payload = fn()
            chain.append((name, f"OK: {json.dumps(payload, ensure_ascii=False)[:200]}", True))
            if matrix:
                matrix.attempt(target, name, chain[-1][1], ok=True)
            return True, payload, chain
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"[:300]
            chain.append((name, msg, False))
            if matrix:
                matrix.attempt(target, name, msg, ok=False)
    return False, None, chain


def _src_ths_quote(code):
    """⑤ 同花顺。最后一跳：覆盖前四源均无数据的冷门标的。

    ⚠️ 诚实边界：同花顺无公开稳定 JSON 接口，此处走其行情页的静态片段抓取，
       **不保证可用**——正因如此它排在链尾，且失败会照常留痕（不静默）。
    """
    import re as _re
    txt = _http_text(f"https://d.10jqka.com.cn/v6/line/hs_{code}/01/last.js")
    m = _re.search(r'"price"\s*:\s*"?([\d.]+)"?', txt)
    if not m:
        raise ValueError("未匹配到 price 字段（页面结构可能已变）")
    return {"code": code, "price": float(m.group(1)), "src": "10jqka"}


def _src_mx_first(query):
    """① 妙想 mx-data —— 链首，但**默认不启用**（见下方 index_chain 说明）。"""
    from daily_advice import mx_query
    rows = mx_query(query, timeout=40)
    if not rows:
        raise ValueError("mx-data 无返回行")
    return {"rows": len(rows), "first": rows[0]}


def index_chain(secid, tencent_code=None, sina_symbol=None, ths_code=None,
                mx_query=None, hops=None):
    """需求 C 的**五跳兜底链**（#138）：①mx-data ②东财push2delay ③腾讯fqkline ④新浪 ⑤同花顺。

    ⚠️ mx-data 默认【不在链内】——它按次计费且是 6 个妙想 skill 共用池（500/日，见 #131），
       自动烧额度会挤占报告取数。要纳入链首须显式传 mx_query 字符串，
       且此参数与 hops 都不传时链从第②跳开始。

    hops 可用于只跑指定跳（排查用），如 hops=[2, 4]。
    返回 [(源名, 调用函数)]，顺序即尝试顺序，**每一跳的结果都会进健康矩阵**。
    """
    all_hops = []
    if mx_query:
        all_hops.append(("mx_data", lambda: _src_mx_first(mx_query)))
    all_hops.append(("eastmoney_push2delay", lambda: _src_eastmoney_push2delay(secid)))
    if tencent_code:
        all_hops.append(("tencent_fqkline", lambda: _src_tencent_kline(tencent_code)))
    if sina_symbol:
        all_hops.append(("sina_kline", lambda: _src_sina_kline(sina_symbol)))
    if ths_code:
        all_hops.append(("ths_10jqka", lambda: _src_ths_quote(ths_code)))
    if hops:
        all_hops = [h for n, h in enumerate(all_hops, 1) if n in hops]
    return all_hops


# ============================================================
# 需求 D（#138）· 主力资金多日序列 —— 结论型字段必须带 series_days
# ============================================================
def flow_field(series_days, grade, main_flow=None, ddx=None, note=""):
    """构造一个【携带可信度】的资金字段。

    D-3/D-4：拿不到多日时，【不得】用「单日 + 记忆中的昨日值」拼出「连续 N 日」的结论；
             必须置 grade=degraded 且标 series_days，报告侧据此降级表述。
    「连续 N 日为正/为负」这类结论型字段必须携带 series_days 与 grade 一同输出，
    不得只给一个布尔值。
    """
    if series_days is None:
        raise ValueError("series_days 必填 —— D-4：结论型字段不得只给布尔值")
    if series_days < 2 and grade == "real":
        grade = "degraded"
        note = (note + " ｜ 仅单日序列，grade 自动降级为 degraded——"
                        "不得据此断言「连续 N 日」").strip(" ｜")
    return {
        "series_days": int(series_days),
        "grade": grade,
        "main_flow": main_flow,
        "ddx": ddx,
        "can_assert_consecutive": bool(series_days >= 2 and grade == "real"),
        "note": note,
    }


# ============================================================
# CLI
# ============================================================
def main():
    argv = sys.argv[1:]

    if "--probe" in argv:
        i = argv.index("--probe")
        secid = argv[i + 1]
        label = None
        if "--label" in argv:
            label = argv[argv.index("--label") + 1]
        target = label or secid
        # 可选：--mx "<问法>" 把妙想纳入链首；--ths <代码> / --sina <symbol> / --tencent <code> 补齐后几跳
        opt = lambda f: argv[argv.index(f) + 1] if f in argv else None
        m = HealthMatrix.load()
        ok, payload, chain = fetch_with_fallback(
            target,
            index_chain(secid, tencent_code=opt("--tencent"), sina_symbol=opt("--sina"),
                        ths_code=opt("--ths"), mx_query=opt("--mx")),
            matrix=m)
        _prev = m.targets.get(target)
        _grade = "real" if ok else grade_for_failure(_prev)    # 140 R1：失败态按历史成功判四态
        m.finalize(target, _grade)
        m.reading(target, (payload or {}).get("price"), close_confirmed=True, source="probe")
        m.write()
        print(f"— 兜底链探测：{target}（secid={secid}）— 共 {len(chain)} 跳")
        for n, (name, result, good) in enumerate(chain, 1):
            print(f"  {n}. {'✅' if good else '❌'} {name}: {result}")
        if ok:
            print("  → grade = real")
        elif _grade == "rate_limited":
            print("  → grade = rate_limited（全跳失败，但**历史上成功过** ⇒ 端点存在、本次限流/间歇"
                  "——判不触发＋留痕；⛔ 不修源，下次再试）")
        else:
            print("  → grade = unavailable（全跳失败且**从未成功过** ⇒ 结构性无源；⛔ 不重复尝试）")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if payload else "  (全败)")
        return 0

    if "--close" in argv:
        i = argv.index("--close")
        cls = close_class_of(argv[i + 1])
        # --at HH:MM：注入「假定当前时刻」，使收盘判定【可复现】。
        # 验收要求「两个不同时刻各跑一次」——不能靠等钟点，要能指定。
        now, stamp = None, "（实际当前时刻）"
        if "--at" in argv:
            at = argv[argv.index("--at") + 1]
            h, m = (int(x) for x in at.split(":"))
            now = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
            stamp = f"（注入时刻 {at}）"
        ok, reason = close_confirmed(cls, now=now)
        print(f"close_class={cls or '(未识别)'} {stamp} → close_confirmed={ok}")
        print(f"  {reason}")
        return 0

    if "--retake" in argv:
        # #138 B-4：登记一次读数（append-only）。当日盘中一次 + 收盘后一次共存，互不覆盖。
        i = argv.index("--retake")
        target = argv[i + 1]
        value = argv[i + 2] if len(argv) > i + 2 else None
        cls = close_class_of(argv[i + 3]) if len(argv) > i + 3 else ""
        at = argv[argv.index("--at") + 1] if "--at" in argv else None
        if at:
            h, m = (int(x) for x in at.split(":"))
            at = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0
                                        ).strftime("%Y-%m-%dT%H:%M:%S+08:00")
        m = HealthMatrix.load()
        cc, why = close_confirmed(cls, now=datetime.fromisoformat(at) if at else None)
        rec = m.reading(target, value, close_confirmed=cc, at=at, source="manual/retake",
                        close_class=cls, note=why)
        m.write()
        t = m.targets[target]
        print(f"已登记读数：{target} = {value} @ {rec['at']}  close_confirmed={cc}")
        print(f"  {why}")
        print(f"该标的现有 {len(t['readings'])} 条读数（append-only，互不覆盖）：")
        for r in t["readings"]:
            print(f"    - {r['at'][:19]}  {r['value']}  close_confirmed={r['close_confirmed']}")
        return 0

    if "--show" in argv:
        if not HEALTH_PATH.exists():
            print(f"健康矩阵尚未生成：{HEALTH_PATH}")
            return 1
        d = json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
        print(f"生成于 {d.get('generated')} ｜ 标的数 {len(d.get('targets', {}))}")
        for k, v in d.get("targets", {}).items():
            grade = v.get("grade") or "?"
            mark = {"real": "✅", "degraded": "🟡", "rate_limited": "🟠", "unavailable": "🔴"}.get(grade, "❓")
            print(f"  {mark} {k}  grade={grade}  尝试源={len(v.get('attempted_sources', []))}")
            if v.get("substitute"):
                print(f"      替代: {v['substitute'].get('used')}（{v['substitute'].get('kind')}）"
                      f" 已知偏差: {v['substitute'].get('known_bias')}")
            if v.get("series_days") is not None:
                print(f"      序列天数: {v['series_days']}")
            rs = v.get("readings") or []
            if rs:
                print(f"      读数 {len(rs)} 条（append-only）：")
                for r in rs[-4:]:
                    cc = r.get("close_confirmed")
                    tag = "收盘值" if cc else ("盘中读数" if cc is False else "未判")
                    print(f"        - {str(r.get('at'))[:19]}  {r.get('value')}  [{tag}]")
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
