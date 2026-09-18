# -*- coding: utf-8 -*-
"""gen_watchlist_status.py — watchlist「今日状态」生成器（v4.5.1 · 2026-09-18 立）

【为什么要建这个脚本】
  登记项：**「watchlist `today` 字段自 9/7 起停滞 9 个交易日」**。
  核实后发现**真正的病灶与登记描述不同**，且更严重：

    🔴 `watchlist[].today` 是**只写字段（write-only）—— 全仓零读者**。
       实测：`rebuild.py` 的 JS 读 `w.sector / w.etf_code / w.status / w.trigger`，**不读 `w.today`**；
       全仓 `.get('today')` 的命中全部指向 `embed['today']`（当日决策块，**同名不同物**）；
       `gen_intraday_auto.py` 的「五、新机会扫描」是一句**人工占位符**，从不读 watchlist。
       ⇒ **它不是「过期了」，是这个字段本来就没有下游。**
       ⇒ 登记项写的处方「**改数据源**」是**错的** —— 那等于为一个没人读的字段新建取数链路，
          正是本次会话主题（死定义／写对了没人接）的**反面再犯一次**。

  ⇒ 本脚本同时做两件事，把「只写字段」变成「真闭环」：
      ① **算**：按 **v4.5.0 新判据**（手册 §4.4）自动判定右侧确认是否成立 ——
         **条件① A2 不成立**（板块当日 <2% 且非连续 2 日飘红）＋
         **条件② 标的当日收盘价 ≥ 当日 MA5**。
      ② **被读**：写回 `watchlist[].today` ＋ `today_meta`，并由
         `rebuild.py` 关注面板 与 `gen_intraday_auto.py` §五 渲染 —— 消灭「零读者」。

【🔴 失败姿态：fail-loud，绝不静默给旧值】
  任一判据输入取不到 ⇒ 该条状态写「**无源·无法判定**」并注明缺什么，
  **绝不**沿用上一次的文本、**绝不**用近似值冒充。
  依据：附录E · F5（判据源强制）＋「数据必达铁律」＋ v4.4.13「拿到一个价 ≠ 拿到收盘价」。
  ⚠️ 盘中调用时 `daily_kline` 的末根 K 线是**盘中价不是收盘价** ⇒ 一律标 `close_confirmed`，
     未确认时状态写「**盘中·未定格**」，**不得**当作收盘价判据（F5）。

用法:
  python gen_watchlist_status.py            # 计算并写回 portfolio_data.json
  python gen_watchlist_status.py --dry-run  # 只打印，不写文件
  python gen_watchlist_status.py --json     # 只输出 JSON（供 sync_all / 其他脚本消费）
"""
import io
import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths  # noqa: E402
import fetch_public as fp  # noqa: E402

DATA_PATH = paths.DATA_PATH
CONTRACT_PATH = paths.RULE_CONTRACT_PATH


def _load_json(p, default=None):
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _norm_tencent(code: str):
    """'159755/159566' → 'sz159755'；'515180' → 'sh515180'；已是 sh/sz 前缀则原样返回。"""
    c = str(code or "").split("/")[0].strip()
    if not c:
        return None, None
    if c[:2].lower() in ("sh", "sz"):
        return c.lower(), c[2:]
    if c.startswith(("15", "16", "18")):      # 深市 ETF
        return "sz" + c, c
    if c.startswith(("51", "56", "58")):      # 沪市 ETF
        return "sh" + c, c
    return None, c


def _sector_lookup(sector: str, allboards: dict):
    """在**双宇宙全量**板块榜里找该主题。返回 (行, 原因)。

    🔴 必须用 `board_movers_all()` 而不是 `sector_movers()`：
       后者只查 `m:90+t:2` 行业宇宙且只取单页 100 条
       ⇒ 「固态电池／人形机器人／智能驾驶」**永远匹配不到**
       ⇒ 且失败长相是「该板块不存在」，**不是「查错了源」**（静默失效）。
    """
    if not allboards:
        return None, "板块榜源不可用"
    by_name = allboards.get("by_name") or {}
    if sector in by_name:                       # 精确命中优先
        return by_name[sector], None
    for nm, row in by_name.items():             # 退化为子串匹配
        if sector and (sector in nm or nm in sector):
            return row, None
    return None, (f"双宇宙板块榜（行业{allboards.get('universes', {}).get('行业板块', {}).get('total', '?')}"
                  f"＋概念{allboards.get('universes', {}).get('概念板块', {}).get('total', '?')}）"
                  f"中无「{sector}」")


def _eval_a2(sector: str, allboards: dict, a2_pct: float):
    """A2 判定。返回 (命中?, 可完全判定?, 说明)。

    A2 命中条件：**板块当日 ≥2%**  或  **连续 2 日飘红**（当日>0 且 前日>0）。

    🔴 关键推理（不是「判不了就一律拦」）：
       「连续 2 日飘红」**蕴含「当日 > 0」**。故可由当日涨幅严格三分：
         chg ≥ 2%        → **命中**（分支①，无需前日）
         chg ≤ 0         → **分支②逻辑上不可能成立** ⇒ A2 不成立 **且完全可判定**
         0 < chg < 2%    → 分支②真伪取决于前日 ⇒ **唯一真正无源的区间**
       ⇒ 板块前日涨幅无免费公共源（实测 2 主机），但**只有落在第三区间的条目**
         才是「部分可判」—— 前两区间结论**完全确定**。收缩无源面，不放弃严谨性。
    """
    row, why = _sector_lookup(sector, allboards)
    if row is None:
        return None, False, f"A2 判据缺板块涨幅：{why}"
    chg = row.get("chg_pct")
    try:
        chg = float(chg)
    except (TypeError, ValueError):
        return None, False, f"A2 判据板块涨幅非数值（{chg!r}）"

    src = f"{row.get('board_type', '?')}「{row.get('name')}」{chg:+.2f}%"
    if chg >= a2_pct:
        return True, True, f"{src} ≥ {a2_pct:.0f}% ⇒ **A2 命中**（分支①）"
    if chg <= 0:
        return False, True, (f"{src} ≤ 0 ⇒ 分支①不成立，且**分支②（连续2日飘红）"
                             f"逻辑上不可能** ⇒ A2 不成立（完全判定）")
    return None, False, (f"{src} ∈ (0, {a2_pct:.0f}%) ⇒ 分支①不成立，但分支②"
                         f"**真伪取决于板块前日涨幅，该源结构性无源**（实测 2 主机）⇒ A2 仅部分可判")


def evaluate_entry(item: dict, contract: dict, allboards: dict, now: datetime) -> dict:
    """对单条 watchlist 按 §4.4 判据求值，返回状态字典（**含失败原因，不掩盖**）。"""
    sector = str(item.get("sector", ""))
    code_raw = str(item.get("etf_code", ""))
    tx_code, plain = _norm_tencent(code_raw)
    ma_n = int((contract.get("rules") or {}).get("watchlist_confirm_ma_period") or 5)
    a2_pct = float((contract.get("rules") or {}).get("a2_red_day_pct") or 2.0)

    out = {
        "sector": sector, "code": tx_code or code_raw, "ma_period": ma_n,
        "close": None, "ma": None, "a2_ok": None, "a2_determined": False,
        "d5_ok": None, "close_confirmed": False, "verdict": None,
        "data_time": now.strftime("%Y-%m-%d %H:%M"), "missing": [],
        "sources": [], "caveats": [], "a2_gap": None,
    }

    # ---- 条件②：标的当日收盘价 ≥ 当日 MA5（判据源 = 标的自身 K 线）----
    if not tx_code:
        out["missing"].append(f"ETF 代码无法解析（{code_raw!r}）")
    else:
        kl = fp.daily_kline(tx_code, n=max(ma_n + 5, 10)) or []
        if len(kl) < ma_n + 1:
            out["missing"].append(f"{tx_code} K 线不足（得 {len(kl)} 根，需 ≥{ma_n + 1}）")
        else:
            today_bar = kl[-1]
            closes = [float(b["close"]) for b in kl]
            out["close"] = float(today_bar["close"])
            # 🔴 「当日 MA5」口径 = **含当日收盘**（行情软件图上的标准读法）。
            #    另一解（当日之前的 5 根）一并记录：若两解结论相反 ⇒ 主动报警，
            #    **不静默择一**（口径歧义必须显式暴露，不得由实现方暗定）。
            ma_incl = fp.ma(closes, ma_n)                 # 含当日 ← 采用
            ma_prev = fp.ma(closes[:-1], ma_n)            # 不含当日 ← 备查
            out["ma"] = ma_incl
            out["ma_alt"] = ma_prev
            # 🔴 末根 K 线若为【当日】且当前未收盘 → 它是盘中价，不是收盘价（F5）
            is_today_bar = str(today_bar.get("date")) == now.strftime("%Y-%m-%d")
            after_close = now.hour > 15 or (now.hour == 15 and now.minute >= 5)
            out["close_confirmed"] = bool(not is_today_bar or after_close)
            out["bar_date"] = str(today_bar.get("date"))
            if ma_incl is not None:
                out["d5_ok"] = out["close"] >= ma_incl
                if ma_prev is not None and (out["d5_ok"] != (out["close"] >= ma_prev)):
                    out["caveats"].append(
                        f"🔴 MA{ma_n} 口径歧义**改变结论**：含当日 {ma_incl} → {out['d5_ok']}，"
                        f"不含当日 {ma_prev} → {not out['d5_ok']}。当前按**含当日**（软件图标准读法）"
                        f"取值，**需用户裁决**，本条不得据此下单")
            out["sources"].append(f"腾讯日K {tx_code}")

    # ---- 条件①：A2 不成立（板块当日 <2% 且 非连续 2 日飘红）----
    hit, determined, a2_note = _eval_a2(sector, allboards, a2_pct)
    out["a2_hit"] = hit
    out["a2_ok"] = (not hit) if hit is not None else None
    out["a2_determined"] = determined
    out["a2_detail"] = a2_note
    # A2 判不了 ⇒ **软缺口**（区别于 K 线取不到的**硬缺口** `missing`）：
    # 软缺口下技术面仍可读、结论仍可给，但**不授予买入许可**；故不并入 missing
    # （并入会让 verdict 被第一分支吞成「⚪ 无源·无法判定」，丢失技术面信息）。
    out["a2_gap"] = None if determined else a2_note

    # ---- 合成结论（🔴 A2 未完全排除 ⇒ 不授予买入许可，fail-closed）----
    if out["missing"]:
        out["verdict"] = "⚪ 无源·无法判定"
        out["reason"] = "；".join(out["missing"])
    elif hit:
        out["verdict"] = "⛔ A2 禁买"
        out["reason"] = f"{a2_note} —— A2 优先于右侧确认（§2.1），不成交"
    elif not determined and out["d5_ok"]:
        out["verdict"] = "🟡 A2 仅部分可判"
        out["reason"] = (f"{a2_note}；技术面收盘 {out['close']} ≥ MA{ma_n} {out['ma']} "
                         f"**已成立**，但 A2 是 `X` 执行级 —— **判不了 ⇒ 不授予买入许可**"
                         f"（与 v4.5.0 第 7 项 fail-closed 同族）")
    elif not determined:
        out["verdict"] = "🟡 A2 仅部分可判·且条件②未成立"
        out["reason"] = f"{a2_note}；且收盘 {out['close']} < MA{ma_n} {out['ma']}"
    elif out["d5_ok"] and not out["close_confirmed"]:
        out["verdict"] = "🟡 盘中·未定格"
        out["reason"] = (f"A2 不成立（完全判定）；盘中 {out['close']} vs MA{ma_n} {out['ma']} "
                         f"⇒ 暂成立，**收盘价未定格，不得作触发线判据**（F5）")
    elif out["d5_ok"]:
        out["verdict"] = "🟢 右侧确认成立"
        out["reason"] = (f"A2 不成立（完全判定）；收盘 {out['close']} ≥ MA{ma_n} {out['ma']} "
                         f"⇒ 可 ¥300-500 试探；**E 级**：T+1 日 14:30 前须出显式裁定")
    else:
        out["verdict"] = "🟡 等回踩"
        out["reason"] = (f"A2 不成立（完全判定）；收盘 {out['close']} < MA{ma_n} {out['ma']} "
                         f"⇒ 条件②不成立")
    if out["caveats"]:
        out["reason"] += "　｜⚠️ " + "；".join(out["caveats"])
    return out


def build_status(data: dict, contract: dict, now: datetime) -> dict:
    wl = data.get("watchlist", []) or []
    try:
        allboards = fp.board_movers_all()
    except Exception as exc:  # noqa: BLE001
        allboards = {"_error": str(exc)}
    entries = [evaluate_entry(it, contract, allboards, now) for it in wl]
    uni = allboards.get("universes") or {}
    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "criteria": "手册 §4.4 v3.10：① A2 不成立 ＋ ② 标的当日收盘价 ≥ 当日 MA5",
        "board_source": {
            "universes": uni, "complete": bool(allboards.get("complete")),
            "total_all": allboards.get("total_all"),
            "ts": allboards.get("ts"),
        },
        "entries": entries,
        "any_missing_source": any(e["missing"] for e in entries),
        "any_partial_a2": any(not e["a2_determined"] for e in entries),
    }


def main() -> int:
    dry = "--dry-run" in sys.argv
    as_json = "--json" in sys.argv
    now = datetime.now()

    data = _load_json(DATA_PATH)
    if data is None:
        print(f"[ERR] 读不到 {DATA_PATH}")
        return 1
    contract = _load_json(CONTRACT_PATH, {}) or {}

    status = build_status(data, contract, now)

    if as_json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    print(f"=== watchlist 今日状态（{status['generated_at']}）===")
    print(f"判据：{status['criteria']}")
    bs = status["board_source"]
    _u = "；".join(f"{k} {v['fetched']}/{v['total']}" for k, v in (bs["universes"] or {}).items())
    print(f"板块源：{_u or '不可用'}　全量={bs['complete']}　{bs['ts']}")
    print()
    for e in status["entries"]:
        print(f"  {e['verdict']}  {e['sector']}（{e['code']}）")
        print(f"      {e['reason']}")
        print(f"      数据时点 {e['data_time']} · 收盘已定格={e['close_confirmed']}"
              f" · 源={e['sources'] or '无'}")
    print()

    if dry:
        print("[dry-run] 未写入 portfolio_data.json")
        return 0

    # ---- 写回：只改 watchlist[].today / .today_meta，其余一字不动 ----
    for item, e in zip(data.get("watchlist", []) or [], status["entries"]):
        item["today"] = f"{e['data_time'][5:]} {e['verdict']} —— {e['reason']}"
        item["today_meta"] = {
            "computed_at": e["data_time"], "code": e["code"],
            "close": e["close"], "ma": e["ma"], "ma_alt": e.get("ma_alt"),
            "ma_period": e["ma_period"],
            "a2_hit": e["a2_hit"], "a2_ok": e["a2_ok"],
            "a2_determined": e["a2_determined"], "a2_detail": e["a2_detail"],
            "d5_ok": e["d5_ok"], "close_confirmed": e["close_confirmed"],
            "verdict": e["verdict"], "missing": e["missing"], "a2_gap": e["a2_gap"],
            "caveats": e["caveats"], "sources": e["sources"],
        }
    backups = DATA_PATH.with_suffix(DATA_PATH.suffix + ".bak-watchlist")
    try:
        backups.write_bytes(DATA_PATH.read_bytes())
        with io.open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[OK] 已写回 {DATA_PATH}（备份 {backups.name}）")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] 写回失败：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
