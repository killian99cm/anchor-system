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

【v4.5.2 变更（2026-09-18 用户裁决）—— 只剩「判据源」这一段的最后一块拼图】
  ① **A2 分支② 的前日涨幅源＝自建日序列缓存**（`fetch_public.board_history_record /
     board_history_day`，落盘 `06-dashboard/board_pct_history.json`）。
     外部换源已**穷举并否决**：东财 push2his 被 **IP 级限流**（对照实验证明——同一时刻
     该主机上**已知可用**的 `fund_flow_series` 也一并失效）；`push2delay` **忽略 ndays**；
     同花顺可用但属**替代口径**、偏差方向不确定，而 A2 的错向**不对称**（低估 ⇒ 放行本该禁买的）
     ⇒ ⛔ 不用。缓存自第 2 个交易日起即为**同源真值**：零跨源偏差、零新增外部依赖。
     缓存缺该日 ⇒ **报缺口、fail-closed**，⛔ 不用「最近一条」冒充前一交易日。
  ② **MA5 口径已明文裁定为「含当日」**（手册 §4.4 v3.12 ＋ 契约键
     `watchlist_confirm_ma_includes_today`）—— 消灭「实现方暗定口径」。
     另一解仍一并算出：**两解结论相反时主动报警**（口径敏感条款不得据此下单）。

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


def _eval_a2(sector: str, allboards: dict, a2_pct: float,
             prev_day: dict | None = None, prev_date: str | None = None):
    """A2 判定。返回 (命中?, 可完全判定?, 说明)。

    A2 命中条件：**板块当日 ≥2%**  或  **连续 2 日飘红**（当日>0 且 前日>0）。

    🔴 关键推理（不是「判不了就一律拦」）：
       「连续 2 日飘红」**蕴含「当日 > 0」**。故可由当日涨幅严格三分：
         chg ≥ 2%        → **命中**（分支①，无需前日）
         chg ≤ 0         → **分支②逻辑上不可能成立** ⇒ A2 不成立 **且完全可判定**
         0 < chg < 2%    → 分支②真伪取决于前日 ⇒ **唯一真正需要前日的区间**

    🔴 前日涨幅来源（v4.5.2）：**自建日序列缓存**（`fetch_public.board_history_day`）。
       外部换源已穷举并否决（东财 push2his IP 限流；同花顺可用但属**替代口径**、
       偏差方向不确定，而 A2 的错向**不对称**——低估即放行本该禁买的）。
       缓存里**没有**该前一交易日 ⇒ 落回「仅部分可判」（fail-closed），
       ⛔ **不得**用「最近一条记录」冒充前一交易日。
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
    # ---- 落在 (0, a2_pct)：分支②唯一可能命中的区间，需要前一交易日涨幅 ----
    code = str(row.get("code") or "")
    prow = (prev_day or {}).get(code) if code else None
    pchg = prow.get("chg_pct") if isinstance(prow, dict) else None
    try:
        pchg = float(pchg)
    except (TypeError, ValueError):
        return None, False, (
            f"{src} ∈ (0, {a2_pct:.0f}%) ⇒ 分支①不成立；分支②需**前一交易日"
            f"（{prev_date or '交易日不明'}）板块涨幅**，而日序列缓存"
            f"（board_pct_history.json）中{'无该日记录' if prev_day is None else '无该板块记录'}"
            f" ⇒ **A2 仅部分可判**（fail-closed：判不了 ⇒ 不授予买入许可）")
    if pchg > 0:
        return True, True, (
            f"{src} ∈ (0, {a2_pct:.0f}%) 且 前一交易日（{prev_date}）同板块 "
            f"{pchg:+.2f}% > 0 ⇒ **连续 2 日飘红** ⇒ **A2 命中**（分支②）")
    return False, True, (
        f"{src} ∈ (0, {a2_pct:.0f}%) 但 前一交易日（{prev_date}）同板块 "
        f"{pchg:+.2f}% ≤ 0 ⇒ 分支②不成立 ⇒ A2 不成立（完全判定）")


def evaluate_entry(item: dict, contract: dict, allboards: dict, now: datetime,
                   prev_day: dict | None = None, prev_date: str | None = None) -> dict:
    """对单条 watchlist 按 §4.4 判据求值，返回状态字典（**含失败原因，不掩盖**）。"""
    sector = str(item.get("sector", ""))
    code_raw = str(item.get("etf_code", ""))
    tx_code, plain = _norm_tencent(code_raw)
    _rules = contract.get("rules") or {}
    ma_n = int(_rules.get("watchlist_confirm_ma_period") or 5)
    a2_pct = float(_rules.get("a2_red_day_pct") or 2.0)
    # 🔴 MA5 口径（v4.5.2 已明文裁定，见手册 §4.4）：含当日。契约键缺失时按手册裁定取 True，
    #    但**记录实际取值**并进 caveats，使「实现方暗定口径」不会再次发生。
    ma_incl_today = bool(_rules.get("watchlist_confirm_ma_includes_today", True))

    out = {
        "sector": sector, "code": tx_code or code_raw, "ma_period": ma_n,
        "close": None, "ma": None, "a2_ok": None, "a2_determined": False,
        "d5_ok": None, "close_confirmed": False, "verdict": None,
        "data_time": now.strftime("%Y-%m-%d %H:%M"), "missing": [],
        "sources": [], "caveats": [], "a2_gap": None,
        "prev_date": prev_date, "ma_includes_today": ma_incl_today,
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
            # 🔴 「当日 MA5」口径 = **含当日收盘** —— v4.5.2 已由用户明文裁定
            #    （手册 §4.4，契约键 `watchlist_confirm_ma_includes_today`）。
            #    另一解**一并算出并记录**：两解结论相反时**主动报警**，
            #    **不静默择一**（口径歧义必须显式暴露，不得由实现方暗定）。
            ma_incl = fp.ma(closes, ma_n)                      # 含当日
            ma_prev = fp.ma(closes[:-1], ma_n)                 # 不含当日
            ma_used = ma_incl if ma_incl_today else ma_prev
            out["ma"] = ma_used
            out["ma_alt"] = ma_prev if ma_incl_today else ma_incl
            # 🔴 末根 K 线若为【当日】且当前未收盘 → 它是盘中价，不是收盘价（F5）
            is_today_bar = str(today_bar.get("date")) == now.strftime("%Y-%m-%d")
            after_close = now.hour > 15 or (now.hour == 15 and now.minute >= 5)
            out["close_confirmed"] = bool(not is_today_bar or after_close)
            out["bar_date"] = str(today_bar.get("date"))
            if ma_used is not None:
                out["d5_ok"] = out["close"] >= ma_used
                if ma_incl is not None and ma_prev is not None and (
                        (out["close"] >= ma_incl) != (out["close"] >= ma_prev)):
                    out["caveats"].append(
                        f"🔴 MA{ma_n} 口径**改变结论**：含当日 {ma_incl} → "
                        f"{out['close'] >= ma_incl}，不含当日 {ma_prev} → "
                        f"{out['close'] >= ma_prev}。已按**手册 §4.4 v3.12 裁定**取"
                        f"「{'含当日' if ma_incl_today else '不含当日'}」，"
                        f"但本条**对口径敏感**，须人工复核后方可下单")
            out["sources"].append(f"腾讯日K {tx_code}")

    # ---- 条件①：A2 不成立（板块当日 <2% 且 非连续 2 日飘红）----
    hit, determined, a2_note = _eval_a2(sector, allboards, a2_pct, prev_day, prev_date)
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


def build_status(data: dict, contract: dict, now: datetime,
                 record_history: bool = True) -> dict:
    wl = data.get("watchlist", []) or []
    try:
        allboards = fp.board_movers_all()
    except Exception as exc:  # noqa: BLE001
        allboards = {"_error": str(exc)}

    # ---- 交易日历 ＋ 板块涨幅日序列缓存（v4.5.2）----
    # 🔴 交易日历取自**参考指数自身日K的末日**，而不是 `now` 的日期 ——
    #    否则周末/节假日跑一次就会把上一交易日的收盘值标成今天（日期错标）。
    ref_date, ref_kl = fp.ref_last_trading_day()
    prev_date = fp.prev_trading_day(ref_kl, now.strftime("%Y-%m-%d"))
    prev_day = fp.board_history_day(prev_date) if prev_date else None
    record = (fp.board_history_record(allboards, ref_date, now) if record_history
              else {"recorded": False, "reason": "本次未落盘（dry-run / --json）"})

    # 🔴 绑定校验：手册 §2.1 声称的判据源文件名 vs 代码**实际**读的文件名。
    #    不符即报警 —— 这正是本系统反复出现的那族缺陷（转述层与定义层无绑定）
    #    的对症解法：让「声称」与「实际」在**同一次运行里**被比对，
    #    而不是靠人事后记得去核对。
    _declared = str(((contract.get("rules") or {}).get("a2_prev_day_cache") or "")).strip()
    _actual = os.path.basename(fp._board_history_path())
    source_binding = {
        "declared": _declared, "actual": _actual,
        "ok": bool(_declared) and _declared == _actual,
    }
    if _declared and _declared != _actual:
        source_binding["warn"] = (
            f"🔴 手册声称 A2 前日涨幅取自 `{_declared}`，而代码实际读 `{_actual}`"
            f" —— 判据源**名实不符**，须改契约或改代码（不得两边并存）")

    entries = [evaluate_entry(it, contract, allboards, now, prev_day, prev_date)
               for it in wl]
    uni = allboards.get("universes") or {}
    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "criteria": ("手册 §4.4 v3.12：① A2 不成立 ＋ ② 标的当日收盘价 ≥ 当日 MA5"
                     "（MA5＝**含当日**收盘的 5 日均）"),
        "board_source": {
            "universes": uni, "complete": bool(allboards.get("complete")),
            "total_all": allboards.get("total_all"),
            "ts": allboards.get("ts"),
        },
        "prev_day": {
            "date": prev_date,
            "status": ("已取到（%d 个板块）" % len(prev_day)) if prev_day else
                      ("缓存中无该日记录 ⇒ A2 分支②不可判（fail-closed）"
                       if prev_date else "参考指数日K不可用 ⇒ 交易日历不明"),
            "boards": len(prev_day) if prev_day else 0,
            "source": "board_pct_history.json" if prev_day else None,
        },
        "history_record": record,
        "source_binding": source_binding,
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

    status = build_status(data, contract, now,
                          record_history=not (dry or as_json))

    if as_json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    print(f"=== watchlist 今日状态（{status['generated_at']}）===")
    print(f"判据：{status['criteria']}")
    bs = status["board_source"]
    _u = "；".join(f"{k} {v['fetched']}/{v['total']}" for k, v in (bs["universes"] or {}).items())
    print(f"板块源：{_u or '不可用'}　全量={bs['complete']}　{bs['ts']}")
    pd = status["prev_day"]
    print(f"前一交易日：{pd['date'] or '不明'} —— {pd['status']}（源 {pd['source'] or '无'}）")
    hr = status["history_record"]
    if hr.get("recorded"):
        _hr_txt = f"✅ 已写 {hr['date']}（{hr['n']} 个板块）"
    else:
        _hr_txt = f"⏭ 未写 —— {hr.get('reason')}"
    print(f"日序列落盘：{_hr_txt}")
    sb = status.get("source_binding") or {}
    if sb.get("ok"):
        print(f"判据源绑定：✅ 一致（{sb.get('actual')}）")
    elif sb.get("warn"):
        print(f"判据源绑定：{sb['warn']}")
    else:
        print("判据源绑定：⚠️ 契约未声明 `a2_prev_day_cache`"
              "（run extract_rule_contract.py 重建契约）")
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
