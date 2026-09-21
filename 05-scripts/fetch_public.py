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
                            ⚠️ 该 fs 实有 **496 个板块**（非 ~86）；只取单端会得
                               「全部净流入」的**取样假象** —— 必须**两端都取**。
                            🔴 **勘误（2026-09-18 实测）**：本文件旧注写「必须 pz≥500
                               覆盖全集」，**这句话是错的** —— **`pz` 被服务端硬顶在
                               100**（实测 pz=100/500/1000 一律只回 100 行，total=496）。
                               代码传了 500，**端不认**。⇒ **要全量必须翻页**，
                               见 `board_movers_all()`。`sector_flow`/`sector_movers`
                               至今仍只取单页 100，**同为已知缺口**。
  🔴 板块有**两套互不覆盖的宇宙**（2026-09-18 实测，勿合并）
        m:90+t:2 行业板块 496 个 —— 有色金属 / 半导体 / 电池
        m:90+t:3 概念板块 504 个 —— 固态电池 / 人形机器人 / 智能驾驶
      只查一套时，另一套**永远匹配不到**，且失败**长得像「该板块不存在」**
      而不是「查错了宇宙」—— 静默失效的典型长相。见 `board_movers_all()`。
  ✅ **DDX / DDY / DDZ 四周期**  push2delay.eastmoney.com/api/qt/ulist.np/get
                            fields=f88(当日DDX),f396(3日),f91(5日),f94(10日)
                                   f89/f397/f92/f95 → DDY ｜ f90 → DDZ
                            🆕 **2026-09-18 新增，零 mx 配额**（见下「DDX 勘误」）
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
                                  🔴 **本条曾衍生出一个错误结论，务必连读**：
                                  「禁用**错码**」≠「**无源**」。2026-09-18 实测该码确为综合
                                  （26,404.86），据此写下「纳指100 无免费公共源」——
                                  **而正确码 `100.NDX100` 一直可用**（29,462.74）。
                                  与 v4.4.13 B4'（push2his 被误判无源，实为端点没找对）、
                                  v4.4.8（用错码 sz399811 ⇒ 结论反了）**同型**。
                                  ⇒ **判「无源」前必须穷尽端点，且须记录「正确码是什么」**
  ✗ 100.SOX / SOXS / PHLX      —— 费城半导体指数东财**不收录**（同批 DJIA/SPX/N225/KS11/TWII 均可用）
                                  → 费半只能取自 mx-data，失败即标缺口

🔴 DDX 勘误（2026-09-18）—— 「结构性无源」被证伪，且病因又一次是「端点 ≠ 无源」
--------------------------------------------------------------------------------
  ❌ 旧结论（写在 `01-rules/规则生效期登记表.md` 与多份报告中）：
     「**DDX 为结构性无源，非临时缺失**」，依据是 2026-09-17 用 513120 成分股取
     东财个股 DDE 字段（f66/f69/f72/f75/f78/f81/f87）**全为 null**。
  ✅ 实测推翻（2026-09-18）：**A 股 DDX 一直可得，且不止一个源** ——
     · mx-data  → 四周期齐全（ETF / 指数 / 板块均可）
     · 本模块   → `ulist.np` + f88 字段族，**同一实体逐位一致**（比对见下）
   📌 **两条独立路径逐位比对（2026-09-18，6 个标的全部命中）**：
        980017 国证芯片  0.218 / 0.293 / 0.21 / -0.111   （mx 与公网完全相同）
        000922 中证红利 -0.001 / -0.009 / -0.03 / -0.048  （完全相同）
        399975 证券公司  0.044                            （相同）
        513120 创新药ETF -0.342 / 0.06                    （完全相同）
        159992 创新药ETF -0.139                           （相同）
        BK1036 半导体    0.346 / 0.329 / 0.349 / 0.258    （完全相同）
     ⇒ **值可信；且公网这条路零 mx 配额**，DDX **不需要**动用那 500 次的账户池。

  🔴 **病因：`stock/get` 不供 f88 字段族，被读成了「DDX 无源」。**
     `push2delay/api/qt/stock/get?secid=...&fields=f88,...` **只回 f57/f58**
     （个股 600276、ETF 513120、指数 980017 实测**都一样**）——
     但**换列表类端点就供**：`ulist.np/get`（按 secids）与 `clist/get`（按 fs）。
     ⇒ **「某个端点不供这个字段」≠「这个数据没有源」。**
        判「无源」前必须**至少换一类端点**（单标的 ↔ 列表），**并记录「正确端点是什么」**。
     ⇒ 与 v4.5.5 的 `100.NDX` 案（**禁错码 ≠ 无源**）、v4.4.13 B4'（push2delay 只回
        1 条被当成全部）**同型**。**这是同一个病在本文件里第三次显形。**

  ✅ 真实边界（一句话）：**DDX 是 A 股体系指标** ——
     A 股指数 / ETF / 个股 / 行业板块(m:90+t:2) / 概念板块(m:90+t:3) **全部可得**；
     港股(124.HSSCID) / 美股(100.NDX100) / 外盘(101.GC00Y) **不供**（返回 `-`）。
     ⚠️ 后者是**真·不可得**（非端点问题），报告中须按替代口径五项登记。

  ⚠️ **未验证面（不得声称已验）**：本次验证的是「**mx 与东财公网两路一致**」，
     即 mx 未篡改/错列东财的 DDX；**未**验证「东财 DDX 公式 == 通达信/同花顺 DDX」——
     那是**厂商口径**问题，本机无第二厂商源可比。引用时按「东财口径 DDX」表述。

✅ 易错 secid 对照（已实测，勿凭记忆写）
--------------------------------------------------------------------------------
  创新药（恒生港股通创新药指数）→ **124.HSSCID**（不是 100.，写错即 data:null）
  半导体（国证芯片）            → 0.980017  （⛔ 0.399811 是 CSSW电子，量级差 2.2 倍）
  中证红利                      → 1.000922
  证券公司                      → 0.399975
  COMEX 黄金                    → 101.GC00Y
  道指 / 标普 / 恒生            → 100.DJIA / 100.SPX / 100.HSI
  **纳指100（纳斯达克100）**    → **100.NDX100**
                                  ⛔ 100.NDX 是**纳斯达克综合**（差约 3000 点，见上「已知不可用」）
                                  ⛔ 新浪 `gb_$ndx` ＝纳指100（可作第三源，需 Referer）
                                  📌 日K 序列 → 腾讯 `usfqkline`／code `usNDX`
                                     （`daily_kline("usNDX")` 已支持，见其 us 分支）
  **板块（DDX/资金/涨跌）**     → **90.BK<code>**，如 `90.BK1036` 半导体 / `90.BK0891` 存储芯片
                                  ⛔ **不要用 `stock/get` 取板块**（该端点只回 f57/f58）
                                  📌 板块码取自 `clist/get` 的 `f12`（形如 `BK1036`）

口径纪律（与《报告深度标准 v2.3》§二.13 对齐）
--------------------------------------------------------------------------------
  本模块返回的**盘中值一律不是收盘价**（`close_confirmed=False`）→ 不得作触发线判据。
  南向资金 datacenter 为 **T-1 日终值**（当日须收盘后才有）→ 报告中须标实际日期。
  中国10Y `cn10y()` **预期返回 None**（源不存在）→ 调用方须走替代口径并五项登记。
================================================================================
"""
from __future__ import annotations

import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

__all__ = [
    "index_quotes", "sector_flow", "sector_movers", "southbound",
    "cn10y", "bond_refs", "daily_kline", "ma",
    "fund_flow_series", "ddx", "PROBE_LOG",
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


# 🔴 两套**互不覆盖**的板块宇宙（2026-09-18 实测，勿合并）：
#    m:90+t:2 行业板块 496 个 —— 有色金属 / 半导体 / 电池 / 光伏电池组件
#    m:90+t:3 概念板块 504 个 —— 固态电池 / 人形机器人 / 智能驾驶
#    只查一套 → 另一套**结构性无源**（watchlist 4 条主题里 3 条命中此坑）
_BOARD_UNIVERSES = (("m:90+t:2", "行业板块"), ("m:90+t:3", "概念板块"))


def _board_page(fs: str, pn: int, source: str) -> tuple[list, int]:
    """板块榜单页。返回 (行, total)。**pz 固定 100** —— 见 board_movers_all 说明。"""
    js = _em_json("/api/qt/clist/get", {
        "pn": pn, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": "f3", "fs": fs, "fields": "f12,f14,f3,f62",
    }, source)
    if js is None:
        return [], 0
    return (js.get("diff") or []), int(js.get("total") or 0)


def board_movers_all(max_pages: int = 10) -> dict:
    """**全量**板块涨幅榜（分页 ＋ 双宇宙）。供 A2 判据 / watchlist 状态消费。

    🔴 修的是两处**「代码传了参数但没生效」**（2026-09-18 实测）：
      ① **`pz` 被服务端硬顶在 100**。实测 pz=100/500/1000 **一律只回 100 行**，
         `total` 字段 = 496 —— 故 v4.4.12 记的「改 `pz=500` 覆盖全集」**这句话不成立**：
         代码确实传了 500，**端不认**，实际可见 100/496。⇒ **必须翻页**。
         （`sector_movers` / `sector_flow` 至今仍只取单页 100，**本条同时是给它们的勘误**。）
      ② `fs` 有**两套互不覆盖的宇宙**（见 `_BOARD_UNIVERSES`）—— 只查 `t:2` 时，
         「固态电池／人形机器人／智能驾驶」**永远匹配不到**，且**失败长得像「板块不存在」
         而不是「查错了宇宙」**（静默失效的典型长相）。

    返回 `complete=False` ⇒ **不得**据此断言「全部板块如何如何」（取样偏差，
    与 v4.4.12「指数普跌却全板块净流入」同一类错）。
    """
    key = f"board_movers_all:{max_pages}"
    if key in _CACHE:
        return _CACHE[key]                                        # type: ignore[return-value]

    rows: list[dict] = []
    universes: dict[str, dict] = {}
    complete = True
    for fs, label in _BOARD_UNIVERSES:
        got, total = [], 0
        for pn in range(1, max_pages + 1):
            page, t = _board_page(fs, pn, f"板块榜·{label} p{pn}")
            total = total or t
            if not page:
                if pn == 1:
                    complete = False          # 首页就空 ⇒ 该宇宙整体取数失败
                break
            got += page
            if len(got) >= total:
                break
        universes[label] = {"fs": fs, "total": total, "fetched": len(got),
                            "complete": total > 0 and len(got) >= total}
        if not universes[label]["complete"]:
            complete = False
        for d in got:
            y = d.get("f62")
            rows.append({"code": d.get("f12"), "name": d.get("f14"),
                         "chg_pct": d.get("f3"),
                         # 🆕 v4.5.10（G-3 收口）：`f62` **一直在 fields 里、一直被下载、一直被丢掉**。
                         #   本函数自 v4.5.1 起就双宇宙取数，`f62` 也随之到达，
                         #   但旧写法只搬 f12/f14/f3 ⇒ **概念宇宙（固态电池／人形机器人／智能驾驶）
                         #   的主力资金读数在最后一跳被丢弃**，于是被登记成「结构性无源」。
                         #   ⇒ 与 v4.5.1「写了没人接」同族，只是这次是**取了没人接**。
                         #   ⚠️ 单位＝元 ⇒ ÷1e8 得亿；`None` 表示该板无读数（不得当 0）。
                         "net_yi": round(y / 1e8, 2) if isinstance(y, (int, float)) else None,
                         "board_type": label, "fs": fs})

    by_name = {r["name"]: r for r in rows if r.get("name")}
    res = {
        "rows": rows, "by_name": by_name, "universes": universes,
        "complete": complete, "total_all": sum(u["total"] for u in universes.values()),
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "close_confirmed": False,   # 盘中值；收盘判据须另证（F5）
    }
    _CACHE[key] = res
    return res


def board_prev_day_chg(board_code: str) -> dict:
    """板块**前日**涨幅（供 A2 「连续 2 日飘红」分支）。

    🔴 **实测结构性无源**（2026-09-18，已试 2 主机）：
        `push2his…/kline/get?secid=90.BKxxxx`  → **非 JSON**（限流/封禁长相）
        `push2delay…/同路径`                    → `klines` 长度 **0**
       ⇒ 本函数**返回 available=False ＋ 原因**，**不编造、不用代理值**。
       依据：附录E · F5 ＋「数据必达铁律」。
       调用方遇 `available=False` **不得**把该分支当作「未命中」静默放行 ——
       须在结论里显式写「A2 仅部分可判」（A2 是 `X` 执行级，判不了 ⇒ 不授予买入许可）。
    """
    tried = []
    for host in ("push2his.eastmoney.com", "push2delay.eastmoney.com"):
        url = (f"https://{host}/api/qt/stock/kline/get?secid=90.{board_code}"
               "&ut=fa5fd1943c7b386f172d6893dbfba10b"
               "&fields1=f1,f2,f3,f4,f5,f6"
               "&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
               "&klt=101&fqt=1&end=20500101&lmt=6")
        try:
            rc, body = _http(url, "https://quote.eastmoney.com/", 15, "utf-8")
            if rc != 200:
                tried.append(f"{host}: HTTP {rc}"); continue
            js = json.loads(body)
            kl = ((js or {}).get("data") or {}).get("klines") or []
            if len(kl) >= 2:
                _record("板块前日涨幅", url, True, f"n={len(kl)}")
                return {"available": True, "board_code": board_code,
                        "prev_chg_pct": None, "closes": kl,
                        "note": "kline 已取到，百分比由调用方自算"}
            tried.append(f"{host}: klines={len(kl)}")
            _record("板块前日涨幅", url, False, f"klines={len(kl)}")
        except json.JSONDecodeError:
            tried.append(f"{host}: 非 JSON（限流/封禁长相）")
            _record("板块前日涨幅", url, False, "非 JSON")
        except Exception as exc:                                  # noqa: BLE001
            tried.append(f"{host}: {type(exc).__name__}")
            _record("板块前日涨幅", url, False, type(exc).__name__)
    return {"available": False, "board_code": board_code, "prev_chg_pct": None,
            "tried": tried,
            "note": "板块前日涨幅无免费公共源（已试 2 主机）—— 不得用代理值冒充"}


# ------------------------------------------------------- 板块涨幅·日序列自建缓存
# 🔴 为什么必须**自建**而不是继续换源（2026-09-18 实测穷举）：
#    A2「连续 2 日飘红」需要**板块前一交易日涨幅**，而该值**无可靠免费公共源**——
#      · 东财 push2his 板块日K / 多日分时 → **IP 级限流**。判据不是「BK 不被支持」，
#        而是**对照实验**：同一时刻、同一主机上**已知可用**的 `fund_flow_series`
#        也一并失效 ⇒ 整台主机被限，与 B4' 同族。
#      · 东财 push2delay 同路径 → **忽略 `ndays`**（ndays=3 只回当日 241 点）
#        ⇒ 多日序列**只有 push2his 提供**，而它正是被限的那台。
#      · 同花顺板块日K（概念 886xxx / 行业 881xxx）→ 实测可用，但**同样限流**，
#        且需**手工维护「东财板块名 → 同花顺码」映射表**，属**替代口径**
#        （成分股构成不同、**偏差方向不确定**）。
#        🔴 而 A2 的错向**不对称**：替代源若**低估**涨幅 → 该拦却放行 →
#           **放行了一笔本该禁止的买入**。偏差方向未知时无法保证不低估 ⇒ ⛔ 不用。
#    ⇒ 而取数层**每个交易日已经在调 `board_movers_all()`**（sync_all 步骤 1.5）
#      ⇒ 把当日全量板块涨幅按日期落盘，「前一交易日涨幅」自**第 2 个交易日**起
#        即为**同源真值**：零跨源偏差、零新增外部依赖、零新死定义。
#
# 🔴 三条防静默失效的硬约束（缺一即退化成「拿到一个价 ≠ 拿到对的价」）：
#    ① **只在收盘定格后落盘** —— 盘中落盘会把盘中价当收盘价存下来（违反 F5），
#       而缓存**没有任何字段能事后分辨**它存的是哪一种。
#    ② **只在 `complete=True` 时落盘** —— 那天板块集合不全，日后查某主题会
#       「匹配不到」并被误读成「该板块不存在」（正是 `_BOARD_UNIVERSES` 那条的教训）。
#    ③ **按「数据自身的交易日期」落盘**（取参考指数日K的末日），**不按 `now` 的日期**——
#       否则周末/节假日跑一次就会把上一交易日的收盘值**标成今天**（日期错标，
#       与 v4.4.4 时间错标治理同族）。
#    ④ 读取侧：缓存里**没有**该前一交易日 ⇒ **报缺口**，⛔ **不得**用「最近一条记录」
#       冒充前一交易日（那正是 B4'「兜底只回 1 条且不报错」的形态）。
_BOARD_HISTORY_KEEP_DAYS = 60
_REF_INDEX_TENCENT = "sh000001"       # 参考交易日历：上证指数（稳定、长期可用）


def _board_history_path() -> str:
    """缓存文件路径。`ANCHOR_BOARD_HISTORY` 环境变量可覆盖 —— **测试必须用它**，
    否则测试会写进生产文件（v4.5.1 教训：`try/finally` 在进程被硬杀时不执行，
    「靠 finally 不污染」不成立，**换路径才是真隔离**）。"""
    env = os.environ.get("ANCHOR_BOARD_HISTORY")
    if env:
        return env
    try:
        import paths
        return str(paths.DASHBOARD_DIR / "board_pct_history.json")
    except Exception:                                             # noqa: BLE001
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "board_pct_history.json")


def board_history_load() -> dict:
    """读缓存。文件不存在/损坏 ⇒ 回空骨架（**不抛错**，由调用方按缺口处置）。"""
    try:
        with io.open(_board_history_path(), encoding="utf-8") as f:
            hist = json.load(f)
        if isinstance(hist, dict) and isinstance(hist.get("days"), dict):
            return hist
    except Exception:                                             # noqa: BLE001
        pass
    return {"schema": 1, "days": {}}


def ref_last_trading_day() -> tuple:
    """参考指数（上证）日K的**末个交易日** —— 既是交易日历，也是**数据自身的日期**。
    返回 `(date_str, kline)`；取不到返回 `(None, None)`。"""
    kl = daily_kline(_REF_INDEX_TENCENT, n=10)
    if not kl:
        return None, None
    return str(kl[-1].get("date")), kl


def prev_trading_day(kl: list, today: str | None = None) -> str | None:
    """从日K序列取**严格早于今天**的最近一个交易日。"""
    t = today or datetime.now().strftime("%Y-%m-%d")
    prior = [str(b.get("date")) for b in (kl or []) if str(b.get("date")) < t]
    return prior[-1] if prior else None


def board_history_record(allboards: dict, trade_date, now: datetime | None = None) -> dict:
    """把当日全量板块涨幅落盘到 `trade_date` 名下。返回 `{recorded, reason, ...}`。

    ⛔ 永远**不抛错**、**不部分写入**（临时文件 ＋ `os.replace` 原子替换）；
       任一前置条件不满足 ⇒ `recorded=False` ＋ **写明原因**，绝不静默跳过。"""
    now = now or datetime.now()
    if not allboards or allboards.get("_error"):
        return {"recorded": False, "reason": "板块榜源不可用"}
    if not allboards.get("complete"):
        return {"recorded": False,
                "reason": "板块榜不完整（complete=False）—— 落盘会让日后误判「该板块不存在」"}
    if not trade_date:
        return {"recorded": False, "reason": "无参考交易日（参考指数日K不可用）"}
    if (now.hour, now.minute) < (15, 5):
        return {"recorded": False,
                "reason": f"未到收盘定格时点（{now:%H:%M} < 15:05）"
                          f"—— 盘中价不得当收盘价落盘（F5）"}
    day = {}
    for r in (allboards.get("rows") or []):
        code = str(r.get("code") or "")
        if not code:
            continue
        day[code] = {"name": r.get("name"), "chg_pct": r.get("chg_pct"),
                     "board_type": r.get("board_type")}
    if not day:
        return {"recorded": False, "reason": "板块榜无有效行"}
    hist = board_history_load()
    days = hist.setdefault("days", {})
    days[str(trade_date)] = day
    for k in sorted(days)[:-_BOARD_HISTORY_KEEP_DAYS]:             # 只留最近 N 个交易日
        days.pop(k, None)
    hist["schema"] = 1
    hist["updated_at"] = now.strftime("%Y-%m-%d %H:%M")
    path = _board_history_path()
    tmp = path + ".tmp"
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as exc:                                       # noqa: BLE001
        return {"recorded": False, "reason": f"落盘失败：{type(exc).__name__}: {exc}"}
    return {"recorded": True, "date": str(trade_date), "n": len(day), "path": path}


def board_history_day(date_str) -> dict | None:
    """取某交易日的全量板块快照（`{code: {name, chg_pct, board_type}}`）。
    **不存在即返回 `None`** —— 调用方须报缺口，⛔ 不得回退到「最近一条」。"""
    if not date_str:
        return None
    days = board_history_load().get("days") or {}
    return days.get(str(date_str))


def board_history_gaps(kline: list | None = None, upto: str | None = None) -> dict:
    """缓存缺口自检（v4.5.2）。

    **为什么需要它**：缓存只由**当日实跑**写入，而东财**只给当日板块**
    （历史板块涨幅拿不到）⇒ **漏跑一天 ＝ 永久空洞，无法回填**。
    于是「结构性无源」被换成了「结构性依赖运维执行」—— 而且**新的失败模式是静默的**：
    没人会注意昨晚 sync 没跑，直到某天 A2 又冒出一句「判不了」，而那时原因已经看不见了。
    本函数把那个原因**在当时就说出来**。

    🔴 **判据面故意只覆盖「缓存开始累积之后」**（`epoch = min(缓存日期)`）：
    epoch 之前的日子**不算缺口** —— 那会儿这个机制还不存在，报出来只是**噪声**，
    而**天天响的假告警会被学会忽略，比不报更危险**（同 v2.1 判例）。

    ⚠️ **日历不可用时返回 `checked=False` ＋ 明说「无法核查」**，
    ⛔ **绝不降级成「无缺口」** —— 「查不了」与「没问题」必须可区分。

    返回 `{checked, reason?, epoch, upto, missing[], n_expected, outside_calendar?}`。
    """
    cache = board_history_load()
    days = cache.get("days") or {}
    if not days:
        return {"checked": False, "reason": "缓存为空（尚未开始累积）",
                "epoch": None, "upto": None, "missing": [], "n_expected": 0}

    epoch = min(days)
    kl = kline if kline is not None else ref_last_trading_day()[1]
    kdates = sorted({str(b.get("date")) for b in (kl or []) if b.get("date")})
    if not kdates:
        return {"checked": False,
                "reason": "参考指数日K不可用 ⇒ 交易日历不明，**无法核查**（非「无缺口」）",
                "epoch": epoch, "upto": None, "missing": [], "n_expected": 0}

    upper = str(upto) if upto else kdates[-1]
    # 只核对 [epoch, upper)：upper 当日（ref_date）在收盘前落盘是**正常未写**，不算缺口。
    expected = [d for d in kdates if epoch <= d < upper]
    missing = [d for d in expected if d not in days]
    return {
        "checked": True, "epoch": epoch, "upto": upper,
        "calendar_from": expected[0] if expected else None,
        "calendar_to": expected[-1] if expected else None,
        "n_expected": len(expected), "missing": missing,
        # 🔴 日历窗口起点**晚于**缓存起点 ⇒ 中间那段日子**核不到**（日历不够长），
        #    须如实报出核查边界 —— 「核不到」不等于「没问题」。
        "calendar_truncated": (kdates[0] > epoch),
    }


def board_history_gap_msg(gaps: dict) -> str:
    """把 `board_history_gaps()` 的结果变成一句可直接印给人看的话。

    🔴 **四种态必须互相可区分**，尤其「✅ 无缺口」**不得**与
    「本次根本没核到任何交易日」混为一谈 —— 后者是**假绿灯**（我自己第一版就写成了这样）。"""
    if not gaps.get("checked"):
        return f"⏭ 缓存缺口核查：未执行 —— {gaps.get('reason')}"

    miss = gaps.get("missing") or []
    if miss:
        shown = "、".join(miss[:5]) + ("…" if len(miss) > 5 else "")
        return (f"🔴 缓存缺口：{shown}（共 {len(miss)} 个交易日未落盘）"
                f"⇒ **这些日子之后的每个交易日，A2 分支② 的前日判据都判不了**"
                f"（fail-closed，且**空洞无法回填** —— 东财只给当日板块）")

    if not gaps.get("n_expected"):
        return (f"⏭ 缓存缺口核查：**无可核区间**（缓存自 {gaps.get('epoch')} 起、"
                f"本次核到 {gaps.get('upto')}，区间为空）"
                f"—— 本次未真正核查任何交易日，⛔ **不得读作「无缺口」**")

    tail = "（日历窗口起点晚于缓存起点 ⇒ 更早那段**核不到**，非「无缺口」）" \
        if gaps.get("calendar_truncated") else ""
    return (f"✅ 缓存缺口核查：无缺口"
            f"（核 {gaps['n_expected']} 个交易日：{gaps.get('calendar_from')}"
            f"~{gaps.get('calendar_to')}）{tail}")


# ---------------------------------------------------------------- 南向资金

_MUTUAL_TYPE = {"002": "港股通(沪)", "004": "港股通(深)"}

# 🔴 官方**合计行**（2026-09-21 实测确认，v4.5.11）。
#   该报表每日共 **6 行**，不是 2 行。**编号方案已钉死**：
#       **奇＝北向、偶＝南向；1/2＝沪、3/4＝深、5/6＝合计**
#   ⇒ `002/004/006` 南向族（沪腿/深腿/合计），`001/003/005` 北向族。
#   实测证据（2026-09-11/14/15/16/17/18 共 6 日）：
#     · `006 = 002+004` 与 `005 = 001+003`，NET/BUY/SELL/DEAL_AMT/DEAL_NUM 五字段
#       **42/42 全部精确相等，0 例不符**（非单日巧合）
#     · `DEAL_AMT = BUY_AMT + SELL_AMT`：6 日 × 6 类型 **18/18 精确相等**
#     · `006.INDEX_CLOSE_PRICE=24750.78`（恒生）、`LEAD_STOCKS_CODE=01879.HK`（港股）；
#       `001/003/005` 则是 3911.87（上证）/13640.87（深证）、`LEAD=603686.SH`
#   ⚠️ 该报表**无 `MUTUAL_TYPE_NAME` 列** ⇒ 「006=合计」是**算术恒等式 + 编号方案 +
#     指数佐证**共同认定，**不是读标签得来**。若数据方改动编号，`cross_check` 会当场
#     报 🔴 而不是静默算错 —— 这正是保留交叉校验的理由。
_MUTUAL_TOTAL = "006"

# 🔴 单位（本函数只读 NET/BUY/SELL 三个字段，它们同单位）：
#   `NET_DEAL_AMT` / `BUY_AMT` / `SELL_AMT` / `DEAL_AMT` / `ACCUM_DEAL_AMT` = **百万元**
#   非循环量级锚点：006 当日 DEAL_AMT 103197.01 ⇒ 按百万＝**1032 亿/日**（港股通实际量级）；
#   按万＝10.3 亿/日（不可能）。ACCUM 5514263.34 ⇒ 按百万＝**5.51 万亿**（累计净买入量级）。
#
#   🔴🔴 **同一张报表内混装两种单位** —— 成交额族＝**百万元**，`HOLD_MARKET_CAP`＝**元**
#       （006 = 11,974,517,599,915.6 ⇒ **11.97 万亿**，与成交额族相差 **10^6**）。
#       这两个字段**业务上天然会一起读**（「今天净买入多少、累计持仓多少」）⇒ 是最危险的口径混装。
#   ⚠️ 勿与本仓另一条南向链路 `push2delay/api/qt/kamt/get` 混用 —— **那个是「万元」，
#      与本报表相差 100 倍**，互相校验会得到「差 100 倍」的假异常（2026-09-21 登记）。
#   ⚠️ 空值约定在本报表内也不一致：`001/003` 的 HOLD_MARKET_CAP=`None` 而 `005`=`0`
#      ⇒ 判空必须显式 `is None`，`if r.get(x)` 会把 None 与 0 区别对待。
#
#   ⛔ **接入 `HOLD_MARKET_CAP` 读取端之前，必须先验证 `006` 层是否翻倍**（强指征、未获证明，
#      见 CHANGELOG v4.5.11 §⑥-2）：`006/002` 连续 6 个交易日恒为 `2.0003`，两腿相对差天天
#      吻合到 0.03%，而同两行的 `NET` 有 10/66 天符号相反 ⇒ 疑为 `006` 对两腿双计。
#      📌 **此为指针不是结论**（结论未证，刻意不写死）；**本字段当前全仓零读者**（v4.5.11 实测：
#      4 处命中全是散文、代码零读零写）⇒ **误差今天到不了报告，但接上读取端的那一天就会到**，
#      且形态是「**看起来正常的万亿数字**」而非报错 ⇒ 静默错值。
#      🔴 本仓该类死字段**都长出了读者**（`watchlist[].today` v4.5.1、`index_secid` 排队中）
#      ⇒ **「零读者」是今天为零、不是永远为零。**



# ---------------------------------------------------------------- kamt/get
# 🔴 **`kamt/get` 的字段集是显式契约，不是默认全给**：
#    实测 `fields2=f51..f56` 时**根本没有 `netBuyAmt` 这一列**（只回 6 键），
#    要宽到 f1..f79 才出现 16 键（含 `netBuyAmt`/`buyAmt`/`sellAmt`）。
#    📌 与 v4.5.6「`stock/get` 不供 `f88` 族」**同形**：**「没要这个字段」与
#    「这个字段没有值」返回值一样** —— 本仓同族第 4 次。故此处**故意要宽**。
_KAMT_FIELDS = ",".join(f"f{i}" for i in range(1, 80))
_KAMT_LEGS = (("sh2hk", "港股通(沪)"), ("sz2hk", "港股通(深)"))
# 官方每日额度（**万元**）—— 既是**单位锚点**，也是**「额度族 vs 流量族」判别式**。
# 实测 沪/深南向各 4200000 万元 = 420 亿、北向 5200000 = 520 亿，
# **逐位吻合官方人民币额度** ⇒ 该字段族为**人民币**。
_KAMT_QUOTA_WAN = {"sh2hk": 4200000.0, "sz2hk": 4200000.0,
                   "hk2sh": 5200000.0, "hk2sz": 5200000.0}
# ⛔ 这些键名读起来都像「净流入额」，**实测全是 `交易日数 × 日额度` 的额度分配**：
#    dayNetAmtIn = 4200000（＝全额度的 1 倍）、monthNetAmtIn = 15 ×（9 月 15 个交易日）、
#    yearNetAmtIn = 171 ×（2026 年 171 个交易日）。**一律禁止读取。**
_KAMT_QUOTA_KEYS = ("dayNetAmtIn", "monthNetAmtIn", "yearNetAmtIn", "allNetAmtIn")

def southbound(days: int = 3) -> dict:
    """南向资金（datacenter `RPT_MUTUAL_DEAL_HISTORY`）。

    ⚠️ 为 **T-1 日终值** —— 当日数据须港股收盘后才有。`date` 字段即真实交易日，
    报告中**必须按该日期标注**，不得写成报告当日。

    🔴 **取数方式（2026-09-21 修，v4.5.11）**：`total` **直取官方合计行 `006`**，
    ⛔ **不再自己把 `002+004` 相加**。原写法只在**两腿全挂**时才失败 ——
    单腿挂时 `per_type` 只剩一条，而 `set.intersection(*dates)` **对单个集合恒成功**
    ⇒ `date` 取该腿自身日期、`total` 只剩该腿，**却照旧返回 `ok: True`**。
    实测影响（2026-09-18 真值 1193.27 = 11.93 亿）：**深腿若挂即报 17.01（0.17 亿）
    —— 偏低 98.6%，无报错、探针日志干净、量级看起来仍正常**。
    📌 与 v4.5.6 记的 `ulist.np`「静默少返回一条」**同形，只是这次在本仓自己的循环里**。
    📌 **只加护栏不改取数＝把静默错误变成响的；改取合计行＝取消这个错误类别**（后者才是修）。
    """
    key = f"southbound:{days}"
    if key in _CACHE:
        return _CACHE[key]                                        # type: ignore[return-value]

    # **一次请求取回全部类型**（原写法分两次、每次一类 ⇒ 每类各自可能静默缺失）。
    # 不带 MUTUAL_TYPE 过滤：该报表每日 6 行，`days*10` 足以覆盖并留冗余；
    # 多取的行按类型分桶后自然丢弃，不依赖「每日恰好 6 行」这一假设。
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
           "?reportName=RPT_MUTUAL_DEAL_HISTORY&columns=ALL"
           f"&pageSize={max(days, 3) * 10}&sortColumns=TRADE_DATE&sortTypes=-1")
    rc, body = _http(url, "https://data.eastmoney.com/", 15, "utf-8")
    if rc != 200:
        _record("南向资金", url, False, body)
        res = {"ok": False, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "note": f"取数失败 rc={rc}"}
        _CACHE[key] = res
        return res
    try:
        rows_all = ((json.loads(body).get("result") or {}).get("data")) or []
    except json.JSONDecodeError:
        _record("南向资金", url, False, f"非 JSON: {body[:80]}")
        res = {"ok": False, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "note": "返回非 JSON"}
        _CACHE[key] = res
        return res
    _record("南向资金", url, True, f"{len(rows_all)} 行")

    if not rows_all:
        res = {"ok": False, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "note": "返回 0 行"}
        _CACHE[key] = res
        return res

    per_type: dict[str, list] = {}
    for r in rows_all:
        mt = r.get("MUTUAL_TYPE")
        if mt:
            per_type.setdefault(mt, []).append(r)

    _legs = tuple(_MUTUAL_TYPE)
    _missing_legs = [mt for mt in _legs if mt not in per_type]
    _has_total_row = _MUTUAL_TOTAL in per_type

    # 以「已取到的类型」共有的最新交易日为准（取不到的类型不参与 ⇒ 不会把它自己的日期当公共日）
    dates = [{r.get("TRADE_DATE", "")[:10] for r in v} for v in per_type.values()]
    common = sorted(set.intersection(*dates), reverse=True) if dates else []
    date = common[0] if common else None

    def _net(mt: str):
        """某类型在 `date` 当日的 NET_DEAL_AMT；取不到 → None（⛔ 不得当 0）。"""
        row = next((r for r in per_type.get(mt, []) if r.get("TRADE_DATE", "")[:10] == date), None)
        v = row.get("NET_DEAL_AMT") if row else None
        return v if isinstance(v, (int, float)) else None

    def _row(mt: str):
        return next((r for r in per_type.get(mt, []) if r.get("TRADE_DATE", "")[:10] == date), None)

    t_total = _net(_MUTUAL_TOTAL)
    leg_vals = {mt: _net(mt) for mt in _legs}

    # 🔴 合计的可信来源优先级，**并显式记下用的是哪一个**（⛔ 不静默降级）
    if t_total is not None:
        total, total_basis = t_total, f"官方合计行({_MUTUAL_TOTAL})"
    elif all(v is not None for v in leg_vals.values()) and leg_vals:
        total, total_basis = sum(leg_vals.values()), "分腿求和(002+004)"
    else:
        total, total_basis = None, None

    # 🔴 交叉校验：合计行在场且两腿齐全时，两者**必须**相等。不等即报 ——
    #    这既是「编号被东财改过」的探测器，也是「某腿少了几行」的探测器。
    cross = None
    if t_total is not None and all(v is not None for v in leg_vals.values()) and leg_vals:
        _s = round(sum(leg_vals.values()), 2)
        cross = {"total_row": round(t_total, 2), "legs_sum": _s,
                 "match": abs(round(t_total, 2) - _s) < 0.01}

    detail = [{
        "type": mt, "label": _MUTUAL_TYPE[mt],
        "net_mhkd": round(leg_vals[mt], 2) if leg_vals[mt] is not None else None,
        "buy_mhkd": (_row(mt) or {}).get("BUY_AMT"),
        "sell_mhkd": (_row(mt) or {}).get("SELL_AMT"),
        "index_close": (_row(mt) or {}).get("INDEX_CLOSE_PRICE"),
    } for mt in _legs]

    res = {
        "ok": True, "date": date, "unit": "百万港元",
        "total_mhkd": round(total, 2) if total is not None else None,
        "total_yi": round(total / 100, 2) if total is not None else None,
        "total_basis": total_basis,
        "detail": detail, "days": days,
        # 🔴 `complete` = **合计可信**（有官方合计行，或两腿齐可求和）；缺一即 False
        #    ⇒ ⛔ `complete=False` 时**不得**把 `total_*` 渲染成「合计」（那是假话）
        "complete": total_basis is not None,
        # `legs_complete` = **分腿明细齐全**（与 complete 分开：有合计行时即使缺腿，合计仍可信）
        "legs_complete": not _missing_legs,
        "legs_expected": len(_legs), "legs_found": len(_legs) - len(_missing_legs),
        "missing_legs": [f"{mt} {_MUTUAL_TYPE[mt]}" for mt in _missing_legs],
        "has_total_row": _has_total_row,
        "cross_check": cross,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_t_minus_1": date != datetime.now().strftime("%Y-%m-%d"),
    }
    _CACHE[key] = res
    return res

def southbound_intraday() -> dict:
    """南向资金 **T+0 当日实时值**（`kamt/get` 的 `netBuyAmt`）。

    ⛔⛔ **只读 `netBuyAmt` / `buyAmt` / `sellAmt`；`dayNetAmtIn` 那一族一律禁止读取。**

    **为什么必须写死这条禁令（2026-09-21 实测，v4.5.13）**：
        `dayNetAmtIn` 的**字面意思是「当日净流入额」**，但它**是额度字段不是流量字段**：
            `dayNetAmtIn  = 4200000   = 1 × 4200000`（＝**全额度**）
            `monthNetAmtIn= 63000000  = 15 × 4200000`（9 月已过 **15** 个交易日）
            `yearNetAmtIn = 718200000 = 171 × 4200000`（2026 年已过 **171** 个交易日）
        ⇒ **整族 ＝ 交易日数 × 日额度 ＝ 额度分配，与市场资金流无关。**
    🔴 **危险在于它每天恒等于 420 亿、量级很像个大额净流入、名字还就叫「净流入额」**
        ⇒ 谁按名字取数，就往每份报告注入一个**恒定 420 亿**，**不报错、无形态变化**
        （与 v4.5.5／v4.5.6／v4.5.11 同族）。

    **真正的流量字段 ＝ `netBuyAmt`**，实测 `netBuyAmt = buyAmt − sellAmt` **逐位相等**
    （沪 3047585.83−2737929.90＝309655.94 ✅／深 1645664.69−1540365.87＝105298.82 ✅），
    单位 **万元**，沪+深 ＝ 南向净买入。

    ⚠️ **币种 ＝ 人民币**，依据＝`dayAmtThreshold` 逐位吻合官方人民币额度（见
    `_KAMT_QUOTA_WAN`）；⛔ 但**与 `southbound()`（datacenter，单位「百万港元」）
    不得直接对拉** —— **币种不同**（差约 HKD/CNY），**且后者是 T-1 日终值**。
    📌 **「对不上」在这里不是端点坏了**，这正是要提前写下来的。

    ⚠️ **盘中值，`close_confirmed` 恒 False** ⇒ ⛔ **不得作任何触发线判据**
    （F5／v4.5.2「拿到一个价 ≠ 拿到收盘价」）。
    """
    key = "southbound_intraday"
    if key in _CACHE:
        return _CACHE[key]                                       # type: ignore[return-value]

    url = (f"https://push2delay.eastmoney.com/api/qt/kamt/get"
           f"?fields1={_KAMT_FIELDS}&fields2={_KAMT_FIELDS}")
    rc, body = _http(url, "https://data.eastmoney.com/", 15, "utf-8")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if rc != 200:
        _record("南向T+0", url, False, body)
        res = {"ok": False, "ts": ts, "note": f"取数失败 rc={rc}"}
        _CACHE[key] = res
        return res
    try:
        data = (json.loads(body) or {}).get("data") or {}
    except json.JSONDecodeError:
        _record("南向T+0", url, False, f"非 JSON: {body[:80]}")
        res = {"ok": False, "ts": ts, "note": "返回非 JSON"}
        _CACHE[key] = res
        return res

    if not isinstance(data, dict) or not data:
        _record("南向T+0", url, False, "data 为空")
        res = {"ok": False, "ts": ts, "note": "data 为空（港股休市或端点变更）"}
        _CACHE[key] = res
        return res

    detail, missing = [], []
    for leg, label in _KAMT_LEGS:
        v = data.get(leg)
        if not isinstance(v, dict):
            missing.append(f"{leg} {label}")
            continue
        net, buy, sell = v.get("netBuyAmt"), v.get("buyAmt"), v.get("sellAmt")
        if not isinstance(net, (int, float)):
            missing.append(f"{leg} {label}（无 netBuyAmt）")
            continue
        # 🔴 内部一致性：`netBuyAmt` 必须等于 `buyAmt − sellAmt`。
        #    不等 ⇒ 该腿**不参与合计**（⛔ 不静默采纳，也不静默丢弃 —— 报出来）。
        ident = None
        if isinstance(buy, (int, float)) and isinstance(sell, (int, float)):
            ident = abs(round(buy - sell, 2) - round(net, 2)) < 0.02
        detail.append({
            "leg": leg, "label": label,
            "net_buy_wan": round(net, 2), "buy_wan": buy, "sell_wan": sell,
            "identity_ok": ident,
            "quota_wan": v.get("dayAmtThreshold"),
        })

    bad_ident = [d["label"] for d in detail if d["identity_ok"] is False]
    usable = [d for d in detail if d["identity_ok"] is not False]
    complete = (len(missing) == 0 and len(usable) == len(_KAMT_LEGS))
    total_wan = round(sum(d["net_buy_wan"] for d in usable), 2) if complete else None

    _record("南向T+0", url, True,
            f"{len(data)} 腿；净买入合计={'%.2f 万元' % total_wan if total_wan is not None else '不完整'}")

    res = {
        "ok": True, "date": (data.get("sh2hk") or {}).get("date2"),
        "ts": ts,
        "net_buy_wan": total_wan,
        "net_buy_yi": round(total_wan / 10000.0, 2) if total_wan is not None else None,
        "detail": detail,
        "complete": complete,
        "legs_expected": len(_KAMT_LEGS), "legs_found": len(detail),
        "missing_legs": missing,
        "identity_failed": bad_ident,
        "unit": "万元", "currency": "CNY", "currency_proven": False,
        "currency_basis": ("dayAmtThreshold 沪/深 4200000＝420 亿、北向 5200000＝520 亿，"
                           "逐位吻合官方人民币额度"),
        # ⛔ **恒 False**：这是盘中/当日实时值，不是定格收盘值
        "close_confirmed": False,
        "source": "push2delay kamt/get netBuyAmt",
        "forbidden_use": "⛔ 不得作触发线判据（盘中值）；⛔ 不得与 datacenter T-1 值直接对拉（币种不同）",
        "note": ("南向 T+0（沪+深），单位万元人民币。"
                 "⛔ 本函数**刻意不读** dayNetAmtIn 族（那是额度分配，恒为交易日数×420 亿）。"),
    }
    _CACHE[key] = res
    return res


# ---------------------------------------------------------------- 国债收益率 / 替代

# ⚠️ **已证伪路径**（保留供审计 / 作末位兜底）—— 这 4 个码走 `push2` 的 `stock/get`，
#    实测全部 `rc:100/102 data:null`。**但「这些码取不到」≠「东财不提供国债收益率」**（见下）。
_CN10Y_SECIDS = ("100.CN10Y", "100.CN10YR", "1.CN10Y", "100.US10Y")

# ✅ **正确源（2026-09-21 实测，v4.5.12）**：`datacenter-web` 报表端点在供，
#    `reportName=RPTA_WEB_TREASURYYIELD`，中国 10 年期国债收益率字段 = `EMM00166466`
#    （实测 2026-09-14~09-20 连续 6 个交易日：1.6888/1.6865/1.6858/1.6862/1.682/1.6818）。
# 🔴 **原注释写「东财公开 API 不提供任何国债收益率」—— 已被实测证伪。**
#    病根 ＝ 只在 `push2/api/qt/stock/get`（**另一套服务**）上试了 4 个码，就把结论下在
#    「东财」这个整体上 —— **试的是 A 服务，结论下在 B 服务**。
#    📌 与 v4.5.6「`stock/get`（单标的）不供 ≠ 该指标无源」（病十四）**同型，本次是服务级版本**。
#    📌 **禁用项必须与正确项成对登记**（v4.5.5 病十三）：只写「不能用什么」的档案，
#       会让每个后来人独立地重得出同一个「无源」结论。
#    ⛔ 不得据此断言「新浪/中债/货币网也无源」—— 那三家**本轮未逐家实测**，「未试」不是「没有」。
_CN10Y_DC = ("RPTA_WEB_TREASURYYIELD", "EMM00166466")


def cn10y() -> dict:
    """中国10年期国债收益率（主源＝东财 `datacenter` 报表 `RPTA_WEB_TREASURYYIELD`）。

    ✅ **2026-09-21 换源（v4.5.12）**：本函数此前**预期返回 `value=None`** 并据此出报告，
    原因写在旧 docstring 里 —— 「东财公开 API 不提供任何国债收益率」。**该断言已证伪**：
    东财 `datacenter-web` 的该报表**一直可用**（见上方 `_CN10Y_DC` 实测值）。
    旧写法之所以「4 源全失败」，是因为它**只试了 `push2` 那一套服务的 `stock/get`**，
    而收益率在 **`datacenter-web` 这套服务**里 —— **两套服务，试错了那一套**。

    取数优先级：① `datacenter` 报表（主源） → ② 旧 secid 循环（末位兜底，已证伪但仍留）。
    ⚠️ 返回值带 `n_sources_tried`（**含两类源的尝试总数**）；调用方仍须在 `value=None` 时
    走 `bond_refs()` 替代口径并做五项登记 —— **换源不等于保证永远拿得到**。

    ⚠️⚠️ **`date` 可能落在「交易所休市日」上 —— 那不是数据错误，是两套日历不同**（2026-09-21 实测）：
      实测 `date=2026-09-20`，而 `trading_calendar.is_trading_day(2026-09-20) = False`
      （该日**是调休上班日**：`MAKEUP_WORKDAYS` 含它，但**A股调休周末不开市** ⇒ 交易所日历判 False）。
      🔴 **银行间债市按银行工作日运行，调休上班日照常发布** ⇒ 该行**合法**。
      ⛔ **不得据「日历说休市」反推「取数出错了」** —— 那会制造一条**必然误报的告警**
      （v2.1 判例：**一条永远做不到/永远响的强制项会被学会忽略**）。
      📌 **本仓的交易日历是「交易所日历」，不适用于债市** —— 两者**不得互相校验**。
    """
    if "cn10y" in _CACHE:
        return _CACHE["cn10y"]                                   # type: ignore[return-value]

    attempts, got, src = [], None, None

    # ① 主源：datacenter 报表端点
    name, field = _CN10Y_DC
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
           f"?reportName={name}&columns=ALL&pageSize=5"
           "&sortColumns=SOLAR_DATE&sortTypes=-1")
    rc, body = _http(url, "https://data.eastmoney.com/", 15, "utf-8")
    if rc == 200:
        try:
            rows = ((json.loads(body).get("result") or {}).get("data")) or []
        except Exception:
            rows = []
        for r in rows:
            v = r.get(field)
            attempts.append({"source": f"datacenter:{name}", "date": str(r.get("SOLAR_DATE"))[:10],
                             "value": v})
            if isinstance(v, (int, float)) and 0 < v < 20:        # 收益率合理区间
                got, src = v, f"datacenter:{name}({field})"
                break
        if got is None and not rows:
            attempts.append({"source": f"datacenter:{name}", "date": None, "value": None})
    else:
        attempts.append({"source": f"datacenter:{name}", "date": None, "value": None})
        _record("中国10Y·datacenter", url, False, body)

    # ② 末位兜底：旧 secid 循环（已证伪，保留防报表下线）
    if got is None:
        for secid in _CN10Y_SECIDS:
            data = _em_json("/api/qt/stock/get", {
                "fltt": 2, "invt": 2, "fields": "f43,f57,f58,f169,f170", "secid": secid,
            }, f"中国10Y·{secid}")
            v = (data or {}).get("f43")
            attempts.append({"source": f"stock/get:{secid}", "date": None, "value": v})
            if isinstance(v, (int, float)) and 0 < v < 20:
                got, src = v, f"stock/get:{secid}"
                break

    # ⚠️ `ts` 是**取数时刻**，`date` 才是**数据自身日期** —— 两者必须分开暴露：
    #    值恒为 None 时这个区别看不见，一旦换源成功就会把取数时刻误当数据时点
    #    （同族：#138「拿到一个价 ≠ 拿到收盘价」、v4.5.2「按数据自身交易日归档而非 now」）。
    data_date = attempts[0].get("date") if (got is not None and attempts) else None
    res = {
        "value": got, "date": data_date, "source": src, "attempts": attempts,
        "n_sources_tried": len(attempts),
        "note": (f"主源=datacenter {name}（{field}）。已试 %d 源，%s"
                 % (len(attempts),
                    f"命中 {src}" if got is not None else "全部失败")),
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
    """腾讯前复权日K。code 例 'sh000001' / 'sz399975' / 'sh515180' / 'usNDX'。

    ⚠️ 返回的**最后一根若为当日，其收盘价＝盘中即时价**（盘中调用时），
    不是收盘价 —— 不得作收盘价判据（附录E · F5）。

    🔴 **A 股与美股走不同 host**（2026-09-18 实测，勿凭直觉合并）：
         A 股 `fqkline`   → `data.<code>.qfqday`（真前复权）
         美股 `usfqkline` → `data.<code>.day`（**无 qfqday**，下面已兜底）
       ⛔ **用错 host 的失败长相是「静默只回 1 条」而不是报错**：
          `fqkline` + `usNDX` → **rows=1**（rc=200，无异常）。
       这正是入库 note 里「腾讯仅回 1 条」的真因 —— **不是无源，是 host 用错**，
       与 v4.4.13 B4'「push2delay 只回当日 1 条被当成全部」**同型**。
       ⇒ 调用方见 `len(rows) <= 1` 时**不得**当成「该标的无历史序列」。
    """
    host = "usfqkline" if code.lower().startswith("us") else "fqkline"
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/{host}/get"
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


# ---------------------------------------------------------------- DDX / DDY / DDZ

# 字段码（东财口径）：f88/f396/f91/f94 = 当日/3日/5日/10日 DDX；f89/f397/f92/f95 = DDY；f90 = DDZ
# 🔴 **只有 A 股体系供这族字段**。港股 124./ 美股 100./ 外盘 101. 段**返回 `-`（即 None）**，
#    那是**真·不可得**（非端点问题）⇒ 调用方须按替代口径五项登记，**不得当成取数失败重试**。
_DDX_COLS: dict[str, dict[str, str]] = {
    "ddx": {"d1": "f88", "d3": "f396", "d5": "f91", "d10": "f94"},
    "ddy": {"d1": "f89", "d3": "f397", "d5": "f92", "d10": "f95"},
    "ddz": {"d1": "f90"},
}
_DDX_FIELDS = "f12,f13,f14," + ",".join(sorted({
    f for grp in _DDX_COLS.values() for f in grp.values()
}))


def _num(v: object) -> float | None:
    """东财「无此字段」的长相是字符串 `'-'`（不是 None）⇒ 必须显式转 None。

    ⚠️ 不转的话 `float('-')` 会抛，而**静默 `continue` 会让「无源」长得像
    「本标的没有 DDX 读数」——那正是本次要修的病的形态**。
    """
    if v is None or v == "-" or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def ddx(secids: list[str] | str, source: str = "DDX") -> dict:
    """东财 **DDX / DDY / DDZ 多周期** —— 免费公网，**不消耗 mx 配额**。

    secids 例：`['0.980017','1.000922','1.513120','90.BK1036','124.HSSCID']`
    （板块码形如 `90.BK1036`；A 股指数 `0./1.`；ETF 同段；港股 `124.`；美股 `100.`）

    返回::

        {secid: {"name": str|None, "ddx": {"d1","d3","d5","d10"}, "ddy": {...},
                 "ddz": {"d1"}, "available": bool, "close_confirmed": False}}

    🔴 **端点纪律（本次修正的核心）**：DDX 字段族**只在列表类端点**上供——
    `ulist.np/get`（按 secids）与 `clist/get`（按 fs）**都供**；
    **`stock/get`（单标的端点）不供**（只回 f57/f58，个股/ETF/指数实测一致）。
    ⇒ **不许因为 `stock/get` 试不出来就写「DDX 无源」** —— 那正是 2026-09-18 修掉的错。

    ✅ 值已双路交叉验证（2026-09-18，6 个标的与 mx-data **逐位一致**），见模块头注。
    ⚠️ `available=False` 有两义，**调用方须分辨**：
         ① **真·不可得**（港股/美股/外盘，DDX 是 A 股体系指标）→ 走替代口径五项登记
         ② 取数失败（网络/限流）→ 可按需重试
       区分办法：若同批 A 股标的都拿到了，那 `False` 的那些是 ①，**不是** ②。

    ⚠️ `close_confirmed` 恒为 False：15:00 前是盘中值，**不得作触发线判据**（附录E · F5）。
    """
    if isinstance(secids, str):
        secids = [secids]
    key = "ddx:" + ",".join(secids)
    if key in _CACHE:
        return _CACHE[key]                                    # type: ignore[return-value]

    data = _em_json("/api/qt/ulist.np/get", {
        "fltt": 2, "invt": 2, "fields": _DDX_FIELDS,
        "secids": ",".join(secids),
    }, source)

    out: dict = {}
    for d in (data or {}).get("diff", []) or []:
        code = f"{d.get('f13')}.{d.get('f12')}"
        item: dict = {"name": d.get("f14"), "close_confirmed": False}
        for grp, cols in _DDX_COLS.items():
            item[grp] = {per: _num(d.get(fld)) for per, fld in cols.items()}
        # 以「当日 DDX 是否拿到」作为该标的可得性判据（四周期缺项时仍是部分可用）
        item["available"] = item["ddx"]["d1"] is not None
        out[code] = item

    # 请求成功但某 secid 一个字段都没回 → 记留痕（区分「没这张表」与「表里没值」）
    missing = [s for s in secids if s not in out]
    if missing:
        _record(source, f"ddx 缺 {','.join(missing)}", False, "端点未返回该 secid")

    _CACHE[key] = out
    return out


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

    print("\n[6] DDX 四周期（★ 本次新增；含 A股 / 板块 / 及【应不可得】的港股美股对照）")
    dd = ddx(["0.980017", "1.000922", "0.399975", "1.513120",
              "90.BK1036", "124.HSSCID", "100.NDX100"])
    for code, v in dd.items():
        flag = "✅" if v["available"] else "⛔ 不供（A股体系外，真·不可得）"
        d1, d3, d5, d10 = (v["ddx"][k] for k in ("d1", "d3", "d5", "d10"))
        print(f"  {code:<14}{str(v['name'])[:14]:<16}"
              f"当日={d1} 3日={d3} 5日={d5} 10日={d10}  {flag}")

    print("\n[7] 取数留痕（报告「附录取数留痕」可直接引用）")
    for r in PROBE_LOG:
        print(f"  {'✅' if r['ok'] else '🔴'} {r['source']:<22} {r['note']}")
    print(f"\n共 {len(PROBE_LOG)} 次请求，成功 {sum(1 for r in PROBE_LOG if r['ok'])}")
