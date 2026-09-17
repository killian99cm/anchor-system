#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_public.py — Anchor 公共行情取数模块（免费公开 API，零 key，零配额）
================================================================================
存在理由：mx-data 为 500 次/日账户池配额（6 个妙想 skill 共用），耗尽即静默返回空
→ `gen_intraday_auto.py` 产出**表格全空的报告**（2026-09-17 实发事故）。
本模块是「📡 数据必达铁律」的**工程化兜底层**：mx 拿不到时换源重试。

实测端点复核：2026-09-17 14:45–14:50
--------------------------------------------------------------------------------
  ✅ 指数 / ETF / 板块点位   push2delay.eastmoney.com/api/qt/ulist.np/get
  ✅ 板块资金（两端）        push2delay.eastmoney.com/api/qt/clist/get  fs=m:90+t:2
                            ⚠️ 该 fs 实有 **496 个板块**（非 ~86）；只取单端 + pz=100
                               会得「全部净流入」的**取样假象** —— 必须 pz≥500 且两端都取
  ✅ 南向资金                datacenter-web.eastmoney.com  RPT_MUTUAL_DEAL_HISTORY
  ✅ 日K / MA（前复权）      web.ifzq.gtimg.cn/appstock/app/fqkline/get
  ✅ 主力资金【日序列】       push2his.eastmoney.com/api/qt/stock/fflow/daykline/get
                            ⚠️ **必须带 ut token**，否则返回空
                            🔴 **有 IP 级限流**：实测一次成功拿到 **121 条**，随后**连打
                               19 次请求全部 RemoteDisconnected** → 纳入 `_BANNED` 冷处理，
                               **调用要省**（一次拿够，勿循环重试）
                            ⚠️ push2delay / push2 **同路径只回当日 1 条**（不是序列）
                               → 故本端点**不复用 `_EM_HOSTS`**，主机优先级独立
                            📌 用途：判「连续 N 日主力净流出」——此前被误判为「无源」

🔴 已知不可用（勿再试，勿写进 fallback 链）
--------------------------------------------------------------------------------
  ✗ push2.eastmoney.com        —— 限流封禁，短时高频即 RemoteDisconnected（push2delay 正常）
  ✗ 1.push2 / 82.push2         —— 同上
  ✗ 100.CN10Y / CN10YR / US10Y —— rc:100 / rc:102 `data:null`；**东财不提供国债收益率**
  ✗ 新浪 hq.sinajs.cn          —— 需 Referer 才 200，且**只有现券价格，无收益率**
  ✗ 中债 / 中国货币网           —— 公开路径 404，无稳定 JSON
  ✗ 100.NDX                    —— 实为纳斯达克综合、非纳指100（差约 3000 点，禁用）
  ✗ 100.SOX / SOXS / PHLX      —— 费城半导体指数东财**不收录**（同批 DJIA/SPX/N225/KS11/TWII 均可用）
                                  → 费半只能取自 mx-data，失败即标缺口

✅ 易错 secid 对照（已实测，勿凭记忆写）
--------------------------------------------------------------------------------
  创新药（恒生港股通创新药指数）→ **124.HSSCID**（不是 100.，写错即 data:null）
  半导体（国证芯片）            → 0.980017  （⛔ 0.399811 是 CSSW电子，量级差 2.2 倍）
  中证红利                      → 1.000922
  证券公司                      → 0.399975
  COMEX 黄金                    → 101.GC00Y
  道指 / 标普 / 恒生            → 100.DJIA / 100.SPX / 100.HSI

口径纪律（与《报告深度标准 v2.3》§二.13 对齐）
--------------------------------------------------------------------------------
  本模块返回的**盘中值一律不是收盘价**（`close_confirmed=False`）→ 不得作触发线判据。
  南向资金 datacenter 为 **T-1 日终值**（当日须收盘后才有）→ 报告中须标实际日期。
  中国10Y `cn10y()` **预期返回 None**（源不存在）→ 调用方须走替代口径并五项登记。
================================================================================
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

__all__ = [
    "index_quotes", "sector_flow", "sector_movers", "southbound",
    "cn10y", "bond_refs", "daily_kline", "ma",
    "fund_flow_series", "PROBE_LOG",
]

# ---------------------------------------------------------------- 基础设施

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

_EM_HOSTS = ("push2delay.eastmoney.com", "push2.eastmoney.com")
_BANNED: dict[str, float] = {}          # host -> 解禁 unix 时间戳
_CACHE: dict[str, object] = {}          # 同一进程内同参数去重，减少源压力

# 取数留痕：每次真实网络请求记一行，供报告「附录取数留痕」直接引用
PROBE_LOG: list[dict] = []

_BACKOFF = (0.8, 1.6, 2.8)              # 三次尝试的退避秒数
_BAN_SECONDS = 120                       # 某 host 连续失败后冷处理时长


def _record(source: str, url: str, ok: bool, note: str = "") -> None:
    PROBE_LOG.append({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "url": url[:160],
        "ok": ok,
        "note": note[:200],
    })


def _http(url: str, referer: str, timeout: int, enc: str) -> tuple[int, str]:
    """单次 GET。容错解码——绝不因编码崩溃（GBK 输出是实发事故根因）。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        return e.code, f"[HTTPError {e.code}]"
    except Exception as e:                                    # noqa: BLE001
        return -1, f"[{type(e).__name__}] {e}"
    for e in (enc, "utf-8", "gbk", "cp936"):                  # 容错解码链
        try:
            return 200, raw.decode(e)
        except (UnicodeDecodeError, LookupError):
            continue
    return 200, raw.decode("utf-8", "replace")


def _em_json(path: str, params: dict, source: str, timeout: int = 15) -> dict | None:
    """东财 JSON 取数：**host 轮换 + 退避重试**（push2 被限流时自动落 push2delay）。"""
    qs = urllib.parse.urlencode(params)
    now = time.time()
    hosts = [h for h in _EM_HOSTS if _BANNED.get(h, 0.0) < now] or list(_EM_HOSTS)

    for attempt, host in enumerate(hosts + hosts[:1]):         # 至多 3 次
        url = f"https://{host}{path}?{qs}"
        if attempt:
            time.sleep(_BACKOFF[min(attempt, len(_BACKOFF)) - 1])
        rc, body = _http(url, "https://quote.eastmoney.com/", timeout, "utf-8")
        if rc != 200:
            _record(source, url, False, body)
            _BANNED[host] = time.time() + _BAN_SECONDS        # 网络层失败 → 该 host 冷处理
            continue
        try:
            js = json.loads(body)
        except json.JSONDecodeError:
            _record(source, url, False, f"非 JSON: {body[:80]}")
            continue
        if js.get("data") is None:
            # 数据层失败（如 rc=100 无此证券）——换 host 结果相同，直接收敛，不再白烧请求
            _record(source, url, False, f"rc={js.get('rc')} data=null")
            return None
        _record(source, url, True, f"rc={js.get('rc')}")
        return js["data"]

    return None


# ---------------------------------------------------------------- 指数 / ETF

def index_quotes(secids: list[str] | str, source: str = "指数") -> dict:
    """批量取指数/ETF 实时价。secids 例 ['1.000001','399975.SZ'→'0.399975']。

    返回 {代码: {"name","price","chg_pct","chg","raw"}}；**盘中值，非收盘价**。
    """
    if isinstance(secids, str):
        secids = [secids]
    key = "idx:" + ",".join(secids)
    if key in _CACHE:
        return _CACHE[key]                                        # type: ignore[return-value]

    data = _em_json("/api/qt/ulist.np/get", {
        "fltt": 2, "invt": 2,
        "fields": "f1,f2,f3,f4,f12,f13,f14",
        "secids": ",".join(secids),
    }, source)
    out: dict = {}
    for d in (data or {}).get("diff", []) or []:
        code = f"{d.get('f13')}.{d.get('f12')}"
        out[code] = {
            "name": d.get("f14"), "price": d.get("f2"),
            "chg_pct": d.get("f3"), "chg": d.get("f4"), "raw": d,
        }
    _CACHE[key] = out
    return out


# ---------------------------------------------------------------- 板块资金

def _sector_rows(order: int, pz: int, source: str) -> tuple[list, int]:
    """order=1 降序（净流入端）/ 0 升序（净流出端）。返回 (行列表, 板块总数)。"""
    data = _em_json("/api/qt/clist/get", {
        "pn": 1, "pz": pz, "po": order, "np": 1, "fltt": 2, "invt": 2,
        "fid": "f62", "fs": "m:90+t:2", "fields": "f12,f14,f3,f62",
    }, source)
    if not data:
        return [], 0
    return data.get("diff", []) or [], int(data.get("total") or 0)


def sector_flow(top: int = 10, pz: int = 500) -> dict:
    """板块主力资金**两端**。

    🔴 修复记录（2026-09-17）：原实现 `pz=100 & po=1` 只取净流入端前 100 名，
    而该 fs 实有 **496 个板块** → 第 100 名附近仍是正值（实测尾部 +0.43 亿），
    遂得出「指数普跌却全板块净流入」的自相矛盾结论。**根因是取样偏差，非接口口径。**
    现改为 pz=500 覆盖全集 + 两端都取。
    """
    key = f"sector_flow:{top}:{pz}"
    if key in _CACHE:
        return _CACHE[key]                                        # type: ignore[return-value]

    inflow_rows, total = _sector_rows(1, pz, "板块资金·净流入端")
    outflow_rows, total2 = _sector_rows(0, pz, "板块资金·净流出端")
    total = total or total2

    def _fmt(rows: list) -> list[dict]:
        out = []
        for d in rows[:top]:
            y = d.get("f62")
            out.append({
                "code": d.get("f12"), "name": d.get("f14"),
                "chg_pct": d.get("f3"),
                "net_yi": round(y / 1e8, 2) if isinstance(y, (int, float)) else None,
            })
        return out

    res = {
        "total_sectors": total,
        "inflow": _fmt(inflow_rows),
        "outflow": _fmt(outflow_rows),
        "complete": total > 0 and bool(inflow_rows) and bool(outflow_rows),
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "close_confirmed": False,
    }
    _CACHE[key] = res
    return res


def sector_movers(top: int = 10, pz: int = 500) -> dict:
    """板块涨/跌幅榜（fid=f3）。"""
    def _rows(order: int, source: str) -> list:
        data = _em_json("/api/qt/clist/get", {
            "pn": 1, "pz": pz, "po": order, "np": 1, "fltt": 2, "invt": 2,
            "fid": "f3", "fs": "m:90+t:2", "fields": "f12,f14,f3,f62",
        }, source)
        return (data or {}).get("diff", []) or []

    def _fmt(rows: list) -> list[dict]:
        return [{"code": d.get("f12"), "name": d.get("f14"), "chg_pct": d.get("f3")}
                for d in rows[:top]]

    return {
        "gainers": _fmt(_rows(1, "板块涨幅榜")),
        "losers": _fmt(_rows(0, "板块跌幅榜")),
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "close_confirmed": False,
    }


# ---------------------------------------------------------------- 南向资金

_MUTUAL_TYPE = {"002": "港股通(沪)", "004": "港股通(深)"}


def southbound(days: int = 3) -> dict:
    """南向资金（datacenter `RPT_MUTUAL_DEAL_HISTORY`）。

    ⚠️ 为 **T-1 日终值** —— 当日数据须港股收盘后才有。`date` 字段即真实交易日，
    报告中**必须按该日期标注**，不得写成报告当日。
    单位：`NET_DEAL_AMT` 为**百万港元**（由 BUY+SELL=DEAL_AMT 反推验证）。
    """
    key = f"southbound:{days}"
    if key in _CACHE:
        return _CACHE[key]                                        # type: ignore[return-value]

    per_type: dict[str, dict] = {}
    for mt, label in _MUTUAL_TYPE.items():
        flt = urllib.parse.quote(f'(MUTUAL_TYPE="{mt}")')
        url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
               f"?reportName=RPT_MUTUAL_DEAL_HISTORY&columns=ALL&filter={flt}"
               f"&pageSize={days}&sortColumns=TRADE_DATE&sortTypes=-1")
        rc, body = _http(url, "https://data.eastmoney.com/", 15, "utf-8")
        if rc != 200:
            _record("南向资金", url, False, body)
            continue
        try:
            rows = ((json.loads(body).get("result") or {}).get("data")) or []
        except json.JSONDecodeError:
            _record("南向资金", url, False, f"非 JSON: {body[:80]}")
            continue
        _record("南向资金", url, True, f"{label} {len(rows)} 行")
        per_type[mt] = {"label": label, "rows": rows}

    if not per_type:
        res = {"ok": False, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "note": "两类型均取数失败"}
        _CACHE[key] = res
        return res

    # 以两类型共有的最新交易日为准
    dates = [{r["TRADE_DATE"][:10] for r in v["rows"]} for v in per_type.values()]
    common = sorted(set.intersection(*dates), reverse=True) if dates else []
    date = common[0] if common else None

    detail, total = [], 0.0
    for mt, v in per_type.items():
        row = next((r for r in v["rows"] if r["TRADE_DATE"][:10] == date), None)
        net = row.get("NET_DEAL_AMT") if row else None
        if isinstance(net, (int, float)):
            total += net
        detail.append({
            "type": mt, "label": v["label"],
            "net_mhkd": round(net, 2) if isinstance(net, (int, float)) else None,
            "buy_mhkd": row.get("BUY_AMT") if row else None,
            "sell_mhkd": row.get("SELL_AMT") if row else None,
            "index_close": row.get("INDEX_CLOSE_PRICE") if row else None,
        })

    res = {
        "ok": True, "date": date, "unit": "百万港元",
        "total_mhkd": round(total, 2), "total_yi": round(total / 100, 2),
        "detail": detail, "days": days,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_t_minus_1": date != datetime.now().strftime("%Y-%m-%d"),
    }
    _CACHE[key] = res
    return res


# ---------------------------------------------------------------- 国债收益率 / 替代

_CN10Y_SECIDS = ("100.CN10Y", "100.CN10YR", "1.CN10Y", "100.US10Y")


def cn10y() -> dict:
    """中国10年期国债收益率。

    🔴 **预期返回 `value=None`** —— 已实测 4 个东财 secid 全部 `rc:100/102 data:null`，
    即**东财公开 API 不提供任何国债收益率**。保留本函数是为了：
      ① 留痕「已试 N 源」（数据必达铁律要求）
      ② 源头将来若开放可自动生效，调用方不必改
    调用方**不得**用 `None` 占位出报告，必须走 `bond_refs()` 替代口径并做五项登记。
    """
    if "cn10y" in _CACHE:
        return _CACHE["cn10y"]                                   # type: ignore[return-value]

    attempts, got = [], None
    for secid in _CN10Y_SECIDS:
        data = _em_json("/api/qt/stock/get", {
            "fltt": 2, "invt": 2, "fields": "f43,f57,f58,f169,f170", "secid": secid,
        }, f"中国10Y·{secid}")
        v = (data or {}).get("f43")
        attempts.append({"secid": secid, "value": v})
        if isinstance(v, (int, float)) and 0 < v < 20:            # 收益率合理区间
            got = v
            break

    res = {
        "value": got, "attempts": attempts, "n_sources_tried": len(attempts),
        "note": ("东财公开 API 无国债收益率字段；新浪/中债/货币网无稳定 JSON。"
                 "已试 %d 源全部失败。" % len(attempts)),
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _CACHE["cn10y"] = res
    return res


_BOND_REFS = ("1.019547", "1.511010")      # 16国债19 现券 / 国债ETF国泰


def bond_refs() -> dict:
    """债券替代口径：国债现券 + 国债ETF 价格。

    《报告深度标准 v2.3》§二.13 —— 替代口径五项登记由**调用方报告**补齐，本函数
    只提供数据。已知偏差方向：**价格上行 = 收益率下行**（方向相反，非同一量纲）。
    """
    q = index_quotes(list(_BOND_REFS), source="债券替代口径")
    return {
        "quotes": {
            "16国债19(019547)": q.get("1.019547"),
            "国债ETF国泰(511010)": q.get("1.511010"),
        },
        "direction_note": "价格↑ ⇒ 收益率↓（方向相反，量纲不同，不得当作收益率引用）",
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "close_confirmed": False,
    }


# ---------------------------------------------------------------- 日K / MA

def daily_kline(code: str, n: int = 30) -> list[dict]:
    """腾讯前复权日K。code 例 'sh000001' / 'sz399975' / 'sh515180'。

    ⚠️ 返回的**最后一根若为当日，其收盘价＝盘中即时价**（盘中调用时），
    不是收盘价 —— 不得作收盘价判据（附录E · F5）。
    """
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={code},day,,,{n},qfq")
    rc, body = _http(url, "https://gu.qq.com/", 15, "utf-8")
    if rc != 200:
        _record("日K", url, False, body)
        return []
    try:
        node = (json.loads(body).get("data") or {}).get(code) or {}
    except json.JSONDecodeError:
        _record("日K", url, False, f"非 JSON: {body[:80]}")
        return []
    rows = node.get("qfqday") or node.get("day") or []
    _record("日K", url, True, f"{code} {len(rows)} 根")
    out = []
    for r in rows:
        if len(r) < 5:
            continue
        try:
            out.append({"date": r[0], "open": float(r[1]), "close": float(r[2]),
                        "high": float(r[3]), "low": float(r[4])})
        except (TypeError, ValueError):
            continue
    return out


def ma(closes: list[float], n: int) -> float | None:
    """简单均线实算（不取现成值——避免源方 MA 口径差异）。"""
    if len(closes) < n or n <= 0:
        return None
    return round(sum(closes[-n:]) / n, 4)


# ---------------------------------------------------------------- 资金流日序列

# ⚠️ 本端点**不复用 `_EM_HOSTS`**：只有 push2his 提供**序列**，push2delay/push2 同路径
#    只回**当日 1 条**。把 push2delay 放前面会静默拿到「1 条」而被误当完整序列。
_FLOW_HOSTS = ("push2his.eastmoney.com", "push2delay.eastmoney.com")
_UT = "7eea3edcaed734bea9cbfc24409ed989"        # 东财公开 ut token（缺它返回空）
_FLOW_F2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"


def fund_flow_series(secid: str, days: int = 10,
                     source: str = "资金流日序列") -> dict:
    """东财主力资金**日序列** —— 「连续 N 日主力净流出」类判据的判据源。

    实测（2026-09-17）：
      ✅ `push2his` → **返回全序列**（实测 121 条）。
      🔴 但**有 IP 级限流**：同一分钟连打 19 次请求**全部 `RemoteDisconnected`**。
         ⇒ 本函数纳入 `_BANNED` 冷处理；**调用要省**（一次拿够，勿循环重试）。
      ⚠️ `push2delay` / `push2` → 同路径**只回当日 1 条**，仅作「完全无值」兜底。

    返回::

        {"secid", "name", "rows": [{"date","main_net_yi","main_pct"}, ...],
         "count": 实际条数, "complete": count >= days, "close_confirmed": False}

    🔴 `complete=False` 时**不得**据此判「连续 N 日」—— 序列不足即判据不成立，
       调用方应显式声明缺口，**不得以「当日为负」外推**。

    ⚠️ `close_confirmed` 恒为 False：**当日那条在 15:00 前是盘中值**（附录E · F5）。
    """
    key = f"flow:{secid}:{days}"
    if key in _CACHE:
        return _CACHE[key]                                  # type: ignore[return-value]

    now = time.time()
    hosts = [h for h in _FLOW_HOSTS if _BANNED.get(h, 0.0) < now] or list(_FLOW_HOSTS)
    rows: list[dict] = []
    name = None

    for attempt, host in enumerate(hosts):
        if attempt:
            time.sleep(_BACKOFF[min(attempt, len(_BACKOFF)) - 1])
        url = (f"https://{host}/api/qt/stock/fflow/daykline/get"
               f"?lmt=0&klt=101&ut={_UT}&secid={secid}"
               f"&fields1=f1,f2,f3,f7&fields2={_FLOW_F2}")
        rc, body = _http(url, "https://quote.eastmoney.com/", 20, "utf-8")
        if rc != 200:
            _record(source, url, False, body)
            _BANNED[host] = time.time() + _BAN_SECONDS      # 网络层失败 → 冷处理
            continue
        try:
            js = json.loads(body)
        except json.JSONDecodeError:
            _record(source, url, False, f"非 JSON: {body[:80]}")
            continue
        data = js.get("data")
        if data is None:
            _record(source, url, False, f"rc={js.get('rc')} data=null")
            return {"secid": secid, "name": None, "rows": [], "count": 0,
                    "complete": False, "close_confirmed": False}
        name = data.get("name")
        for r in (data.get("klines") or []):
            c = r.split(",")
            if len(c) < 7:
                continue
            try:
                rows.append({"date": c[0],
                             "main_net_yi": round(float(c[1]) / 1e8, 4),
                             "main_pct": float(c[6])})
            except (TypeError, ValueError):
                continue
        _record(source, url, True, f"{secid} {len(rows)} 条 host={host}")
        break

    if not rows:
        _record(source, f"fflow/{secid}", False, "所有 host 均失败")

    out = {"secid": secid, "name": name, "rows": rows[-days:] if days > 0 else rows,
           "count": len(rows), "complete": len(rows) >= days,
           "close_confirmed": False}
    _CACHE[key] = out
    return out


# ---------------------------------------------------------------- 自检

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 72)
    print("fetch_public.py 自检 —", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 72)

    print("\n[1] 指数（上证/深证/创业板）")
    print(json.dumps(index_quotes(["1.000001", "0.399001", "0.399006"]),
                     ensure_ascii=False, indent=1))

    print("\n[2] 板块资金两端（★ 本次修复项）")
    f = sector_flow(top=5)
    print(f"  板块总数 = {f['total_sectors']}（原实现只取前 100 → 取样偏差）")
    print("  净流入端:", [(x["name"], x["net_yi"]) for x in f["inflow"]])
    print("  净流出端:", [(x["name"], x["net_yi"]) for x in f["outflow"]])

    print("\n[3] 南向资金（★ 本次修复项）")
    print(json.dumps(southbound(), ensure_ascii=False, indent=1, default=str))

    print("\n[4] 中国10Y（★ 预期失败 → 走替代口径）")
    print(json.dumps(cn10y(), ensure_ascii=False, indent=1))
    print("  替代口径:", json.dumps(bond_refs(), ensure_ascii=False, indent=1, default=str))

    print("\n[5] 日K + MA 实算（sh515180 红利ETF）")
    k = daily_kline("sh515180", 30)
    if k:
        cl = [r["close"] for r in k]
        print(f"  末根 {k[-1]['date']} close={k[-1]['close']}  ⚠️若为今日=盘中价")
        print(f"  MA5={ma(cl,5)} MA10={ma(cl,10)} MA20={ma(cl,20)}")

    print("\n[6] 取数留痕（报告「附录取数留痕」可直接引用）")
    for r in PROBE_LOG:
        print(f"  {'✅' if r['ok'] else '🔴'} {r['source']:<22} {r['note']}")
    print(f"\n共 {len(PROBE_LOG)} 次请求，成功 {sum(1 for r in PROBE_LOG if r['ok'])}")
