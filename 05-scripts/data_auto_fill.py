# -*- coding: utf-8 -*-
"""
Anchor 数据自动化（data_auto_fill.py）v3（2026-09-16 · 任务单 #137 需求A-3 ＋ #138 需求A/B/D）

- 作用：读取【取数注册表】逐只查最新涨跌，生成「数据回填候选」供用户确认
- 铁律：本脚本【只生成候选文件，绝不写入 portfolio_data.json】——数据权威仍以用户确认为准
- 输出：Anchor/04-reviews/daily/{date}-数据回填候选.json
        Anchor/05-scripts/data_source_health.json（源健康矩阵，脚本自动写）

v3 改动（#137/#138，2026-09-16）：
  1. 🔴 **取数定义改由 `fetch_registry.json` 提供**——QUERY_SPECS 从「唯一真值」降为
     **legacy fallback**（注册表缺失时才用，且会打印告警）。根治「DATA_PIPELINE_MAP 有债券、
     QUERY_SPECS 没有 → 债券从未被取数（占组合 42.43%）」这一结构性缺陷：**只有一处真值**。
  2. 🔴 `load_holdings()` **同时读 `holdings_summary` 与 `stock_holdings`**——515180 中证红利ETF
     在后者，此前 `match_holding` 对红利恒返回 None（「持仓未匹配」的真正原因）。
  3. `fetch: when_held` 条目：无活跃持仓时不空跑（清仓标的只保留定义）。
  4. 每次源尝试（成功/失败）写入健康矩阵 —— 失败可见，不再只留一句「无数据」。
  5. 候选条目新增 `close_class` / `close_confirmed` / `grade` / `series_days`：
     报告侧据此区分「收盘值」与「盘中读数」（#138 需求B/D）。
"""
import json
import os
import re
import sys
import time
from datetime import date, datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths
from daily_advice import mx_query  # 复用妙想 API 查询

JSON_PATH = paths.DATA_PATH
OUT_DIR = paths.REVIEWS_DIR / "daily"
REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_registry.json")

# 两次妙想查询之间的最小间隔（秒）——规避 code=112「请求频率过高」。
QUERY_GAP_SEC = float(os.environ.get("ANCHOR_QUERY_GAP", "1.2"))

# ── 以下 QUERY_SPECS / QUERY_SUFFIXES 仅作【fallback】，注册表可用时一律不读 ──
#    （保留原因：注册表损坏时脚本仍能出候选，而不是整体崩掉。）
LEGACY_QUERY_SUFFIXES = [" 最新净值 日涨跌幅", " 复权单位净值增长率", " 最新日涨跌幅"]
LEGACY_QUERY_SPECS = [
    {"label": "半导体C", "queries": ["华夏国证半导体芯片ETF联接C", "008888"], "match": ["半导体芯片", "半导体"]},
    {"label": "创新药C", "queries": ["易方达恒生港股通创新药ETF联接C"], "match": ["创新药"]},
    {"label": "纳指C", "queries": ["天弘纳斯达克100指数(QDII)C"], "match": ["纳斯达克100指数"]},
    {"label": "纳指A", "queries": ["华泰柏瑞纳斯达克100ETF联接A", "008887"], "match": ["纳斯达克100ETF"]},
    {"label": "证券C", "queries": ["易方达证券ETF联接C", "012590"], "match": ["证券ETF"]},
    {"label": "黄金A", "queries": ["国泰黄金ETF联接A"], "match": ["国泰黄金"]},
    {"label": "通利A", "queries": ["天弘通利混合A"], "match": ["通利"]},
]


# ============================================================
# 注册表加载（#137 需求A-3：只有一处真值）
# ============================================================
def load_registry():
    """读 fetch_registry.json。返回 (entries, suffixes, source_note)。

    失败时返回 (None, LEGACY_QUERY_SUFFIXES, 告警文案) —— 调用方须把告警打出来，
    **不得静默回退**（静默回退会让「注册表坏了」表现为「取数一切正常」）。
    """
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            reg = json.load(f)
        entries = reg.get("entries") or []
        if not entries:
            return None, LEGACY_QUERY_SUFFIXES, f"注册表 {REGISTRY_PATH} 无 entries"
        return entries, reg.get("default_suffixes") or LEGACY_QUERY_SUFFIXES, ""
    except FileNotFoundError:
        return None, LEGACY_QUERY_SUFFIXES, f"注册表不存在：{REGISTRY_PATH}"
    except Exception as exc:
        return None, LEGACY_QUERY_SUFFIXES, f"注册表读取失败 {type(exc).__name__}: {exc}"


def registry_to_specs(entries, suffixes):
    """注册表条目 → 取数规格。**按 query 展开**：一个条目下有几个 query，就产几条 spec。

    为什么必须展开（2026-09-16 修正）：
      「债券」条目下有两只债基（鹏华畅享 / 中银稳健增利），各带自己的 match 与 queries。
      若把一个条目当成一条 spec，取到第一只就 early-return —— **第二只从未被发起取数**，
      正是本单要根治的「静默漏取」，会在自己身上复发。
    与旧 QUERY_SPECS 的差异：queries 可为 str 或 {q, match}；条目级 holdings_match 作兜底；
    每条 spec 带 fetch / target_kind / close_class（供 when_held 跳过与收盘判定用）。
    """
    specs = []
    for e in entries:
        raw_q = e.get("queries") or []
        items = []  # [(query|None, match_list)]
        for item in raw_q:
            if isinstance(item, dict):
                if item.get("q"):
                    items.append((item["q"], item.get("match") or e.get("holdings_match") or []))
            elif item:
                items.append((str(item), e.get("holdings_match") or []))
        if not items:                       # 现金类：无 query，仅登记覆盖度
            items = [(None, e.get("holdings_match") or [])]

        # 按【匹配目标】分组：目标不同 = 不同持仓（必须各自取数）；目标相同 = 别名兜底
        # （如 纳指A 的 "华泰柏瑞纳斯达克100ETF联接A" 与代码 "008887"，第一条成则不烧第二条配额）。
        groups = {}
        order = []
        for q, match in items:
            gk = tuple(match or e.get("holdings_match") or [])
            if gk not in groups:
                groups[gk] = []
                order.append(gk)
            if q:
                groups[gk].append(q)

        multi = len(order) > 1
        for gk in order:
            qs = groups[gk]
            specs.append({
                "key": e.get("key") or e.get("label") or "?",
                # 多目标时才带 query 名，避免日志/候选两行同名无法区分
                "label": f"{e.get('key')}·{qs[0]}" if (multi and qs) else (e.get("label") or e.get("key") or "?"),
                "queries": qs,
                "match": list(gk),
                "suffixes": e.get("suffixes") or suffixes,
                "fetch": e.get("fetch", "always"),
                "target_kind": e.get("target_kind"),
                "close_class": e.get("close_class"),
                "pipeline_key": e.get("pipeline_key"),
                "index_secid": e.get("index_secid"),
            })
    return specs


def load_holdings():
    """返回持仓列表（name/mv/day_pnl/pnl/group），读【两个段】。

    🔴 v3 修复：`holdings_summary`（场外基金）＋ `stock_holdings`（场内股票/ETF）。
    515180 中证红利ETF 只在 stock_holdings——此前只读前者，故红利恒「持仓未匹配」。
    """
    with open(JSON_PATH, encoding="utf-8") as f:
        d = json.load(f)
    out = []
    for h in d.get("holdings_summary", []):
        out.append({
            "name": h.get("name", ""),
            "mv": h.get("mv", 0) or 0,
            "day_pnl": h.get("day_pnl", 0),
            "pnl": h.get("pnl", 0),
            "group": h.get("group", ""),
            "segment": "holdings_summary",
        })
    for h in d.get("stock_holdings", []):
        # stock_holdings 的 mv 可能缺省，用 shares × price 兜底
        mv = h.get("mv")
        if mv in (None, ""):
            try:
                mv = round(float(h.get("shares", 0)) * float(h.get("price", 0)), 2)
            except (TypeError, ValueError):
                mv = 0
        out.append({
            "name": h.get("name", ""),
            "mv": mv or 0,
            "day_pnl": h.get("day_pnl", 0),
            "pnl": h.get("pnl", 0),
            "group": h.get("group", ""),
            "segment": "stock_holdings",
        })
    return out


def match_holding(spec, holdings):
    """按 spec.match 关键词在持仓中找第一个 mv>0 的持仓（与查询词解耦）。"""
    for kw in spec["match"]:
        for h in holdings:
            if kw in h["name"] and h["mv"] > 0:
                return h
    # 退一步：mv=0 也返回（便于展示名称），但标记无市值
    for kw in spec["match"]:
        for h in holdings:
            if kw in h["name"]:
                return h
    return None


def clean_date(raw):
    """清洗妙想返回日期：去时间/区间后缀，统一 YYYY-MM-DD；区间取首个日期。"""
    s = str(raw or "").strip()
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})[-/](\d{1,2})", s)  # 仅 MM-DD，补当前年
    if m:
        return f"{date.today().year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return ""


def _classify_failure(exc_errors, tried):
    """把「全败」拆成【源不可用】与【真无数据】。返回 (error_kind, message)。

    🔴 为什么必须拆（2026-09-16 深夜实测，见检查点 §118 教训1）：
       9/16 23:55 的 sync 0.6 步把 5 项**妙想 code=112（请求频率过高）**记成
       「全部问法无数据」。读日志的人会得出「这些标的没有数据」的结论——
       而真相是**配额被本脚本前一轮自己烧完了**。
       「查不到」和「查不了」若在日志里长得一样，就会反复产出错误结论。
    """
    if not exc_errors:
        return ("no_data",
                f"全部问法无数据（源已应答，{len(tried)} 种问法均无可解析百分比）")
    joined = " | ".join(e for _, e in exc_errors)
    n = len(exc_errors)
    if "112" in joined or "频率" in joined:
        return ("rate_limited",
                f"源限频（妙想 code=112 请求频率过高）×{n} 次 —— **非无数据**，"
                f"间隔后重跑即可，无需改查询词")
    if "113" in joined or "调用次数" in joined or "上限" in joined or "配额" in joined:
        return ("quota_exhausted",
                f"源日配额耗尽（妙想 code=113；500 次/日为 6 个妙想 skill 共用池）×{n} 次 "
                f"—— **非无数据**，次日恢复")
    if any(k in joined for k in ("Timeout", "URLError", "Connection", "timed out")):
        return ("network", f"源不可达/超时 ×{n} 次 —— **非无数据**（{joined[:120]}）")
    return ("source_error", f"源报错 ×{n} 次：{joined[:200]}")


def fetch_latest_pct(spec: dict, matrix=None, target=None) -> dict:
    """对 spec.queries × 后缀依次尝试，取第一个可解析为百分比的结果。

    v3：**每一次尝试都写进健康矩阵**（成功与失败都写）——失败可见是 #138 A-2 的要求。
    v3.1（2026-09-16 深夜）：失败时返回**分类后的**原因（error_kind），
         不再把限频/配额一律说成「无数据」。
    """
    tried = []
    seen = set()
    exc_errors = []   # [(query, 异常文本)]；无异常但解析不出的问法不记这里（＝真无数据）
    for q in spec["queries"]:
        for suffix in spec["suffixes"]:
            # 护栏（2026-09-16）：query 若已含该后缀就不再追加，并跳过重复问法。
            # 实测踩坑：注册表写成 "中证红利ETF 515180 最新价 涨跌幅" + 条目后缀
            #   → 实际发出 "…最新价 涨跌幅 最新价 涨跌幅"，白烧配额且污染日志（健康矩阵原样留痕）。
            v = q if suffix.strip() and suffix.strip() in q else f"{q}{suffix}"
            if v in seen:
                continue
            seen.add(v)
            tried.append(v)
            try:
                rows = mx_query(v, timeout=40)
                err = None
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                exc_errors.append((v, err))
                rows = []
            # 节流（2026-09-16 实测）：连续发问会触发妙想 code=112「请求频率过高」，
            # 与 #131 的日配额（113）不是同一回事——112 靠拉开间隔即可规避。
            time.sleep(QUERY_GAP_SEC)
            hit = None
            for r in rows:
                val = str(r.get("value", "")).replace("%", "").strip()
                try:
                    pct = float(val)
                except ValueError:
                    continue
                hit = {
                    "pct": pct,
                    "date": clean_date(r.get("date")),
                    "entity": r.get("entity", ""),
                    "query": v,
                }
                break
            if matrix and target:
                matrix.attempt(
                    target,
                    f"mx-data: {v}",
                    f"OK pct={hit['pct']}% date={hit['date']}" if hit else (err or "无可解析百分比"),
                    ok=bool(hit),
                )
            if hit:
                return hit
    kind, msg = _classify_failure(exc_errors, tried)
    return {"error": msg, "error_kind": kind, "tried": tried}


def main():
    # ── 注册表优先（#137 A-3）──
    entries, suffixes, reg_warn = load_registry()
    if entries:
        specs = registry_to_specs(entries, suffixes)
        print(f"[注册表] {REGISTRY_PATH} → {len(specs)} 条取数定义，后缀 {len(suffixes)} 种")
    else:
        specs = [dict(s, suffixes=LEGACY_QUERY_SUFFIXES, fetch="always",
                      target_kind=None, close_class=None, per_query_match={}, key=s["label"])
                 for s in LEGACY_QUERY_SPECS]
        print(f"[WARN] 🔴 注册表不可用（{reg_warn}）——已回退到 legacy QUERY_SPECS（{len(specs)} 条）。")
        print(f"[WARN] 该回退路径【不含债券/红利/现金】，覆盖面不完整，请尽快修复注册表。")

    # ── 健康矩阵与收盘判定（#138）──
    try:
        import data_source_health as dsh
        # load() 而非 HealthMatrix()：跨运行保留 readings（#138 B-4 两次读数都保留、不得覆盖）
        matrix = dsh.HealthMatrix.load()
        has_dsh = True
    except Exception as exc:
        print(f"[WARN] 健康矩阵模块不可用（{type(exc).__name__}: {exc}）——本次不落盘 data_source_health.json")
        dsh, matrix, has_dsh = None, None, False

    now = datetime.now()
    holdings = load_holdings()
    today = date.today().isoformat()
    results = []
    failed = []
    skipped = []

    print(f"=== 数据回填候选生成（{today} {now.strftime('%H:%M')}）===")
    print(f"持仓载入 {len(holdings)} 条（holdings_summary {sum(1 for h in holdings if h['segment']=='holdings_summary')}"
          f" ＋ stock_holdings {sum(1 for h in holdings if h['segment']=='stock_holdings')}）")
    print(f"{'标的':<10}{'查询涨跌':>10}{'现日盈亏':>11}{'估算日盈亏':>12}{'差值':>9}  {'收盘确认':<8}数据日期")

    for spec in specs:
        label = spec["label"]
        holding = match_holding(spec, holdings)
        is_held = bool(holding and holding["mv"] > 0)

        # when_held：无活跃持仓则不空跑（只登记，不烧 mx 配额）
        if spec.get("fetch") == "when_held" and not is_held:
            skipped.append(f"{label}（fetch=when_held，无活跃持仓）")
            if matrix:
                matrix.attempt(label, "skipped", "fetch=when_held 且无活跃持仓，未发起查询", ok=False)
                matrix.finalize(label, "real", extra={"skipped": "when_held_no_position"})
            print(f"{label:<10}{'⏭ 未持有':>10}{'--':>11}{'--':>12}{'--':>9}  {'--':<8}--")
            continue

        # cash：无行情可取（#137 注册表已登记，仅为覆盖度）
        if spec.get("target_kind") == "cash":
            if matrix:
                matrix.attempt(label, "n/a", "现金类无行情，金额由用户 App 提供", ok=False)
                matrix.finalize(label, "real", official_name=label, extra={"target_kind": "cash"})
            print(f"{label:<10}{'— 现金类':>10}{'--':>11}{'--':>12}{'--':>9}  {'n/a':<8}--")
            entry = {"key": spec["key"], "label": label, "matched_holding": holding["name"] if holding else "",
                     "base_mv": holding["mv"] if holding else 0, "target_kind": "cash",
                     "close_class": spec.get("close_class"), "close_confirmed": True,
                     "grade": "real", "note": "现金类无行情"}
            results.append(entry)
            continue

        # ── 复用当日【已收盘确认】的读数（2026-09-16 深夜补）──
        # 为什么：readings 是 append-only 且跨运行保留，但此前【从不被读取】——
        #   同一标的在同一晚被反复发问（实测 23:52 已取到创新药 −1.25%，23:54 又查一次
        #   → code=112），既烧 6-skill 共用池，又让后一次的失败把前一次取到的 grade
        #   覆盖成 unavailable。**已经知道的值不该再问一次，更不该被一次失败抹掉。**
        reused = None
        if has_dsh and matrix:
            _lr = matrix.latest_reading(label)
            if _lr and str(_lr.get("at", ""))[:10] == today and _lr.get("close_confirmed") is True:
                reused = _lr

        if reused is not None:
            r = {"pct": reused["value"], "date": today, "entity": "",
                 "query": reused.get("source") or "cache", "reused_at": reused["at"]}
            if matrix:
                matrix.attempt(label, "cache: 当日已收盘确认读数",
                               f"复用 {str(reused['at'])[:19]} 的读数 {reused['value']}%"
                               f"（未重复发问，省共用配额）", ok=True)
        else:
            r = fetch_latest_pct(spec, matrix=matrix, target=label)
        base_mv = holding["mv"] if holding else 0
        matched_name = holding["name"] if holding else ""

        # 收盘判定（#138 需求B-2）：拿到价 ≠ 拿到收盘价
        cc, cc_reason = (None, "")
        if has_dsh:
            cc, cc_reason = dsh.close_confirmed(spec.get("close_class"), now=now, data_date=r.get("date"))

        entry = {
            "key": spec["key"],
            "label": label,
            "pipeline_key": spec.get("pipeline_key"),
            "matched_holding": matched_name,
            "matched_segment": holding["segment"] if holding else None,
            "base_mv": base_mv,
            "target_kind": spec.get("target_kind"),
            "close_class": spec.get("close_class"),
            "close_confirmed": cc,
        }
        if holding is None:
            failed.append(f"{label}（持仓未匹配，关键词 {spec['match']}）")
        entry.update(r)

        cur_day_pnl = holding["day_pnl"] if holding else None
        est = round(base_mv * r["pct"] / 100, 2) if ("pct" in r and base_mv) else None
        if est is not None:
            entry["est_day_pnl"] = est
        if isinstance(cur_day_pnl, (int, float)):
            entry["current_day_pnl"] = cur_day_pnl
            if est is not None:
                entry["diff_vs_current"] = round(est - cur_day_pnl, 2)

        # 等级（#138 A-1/D-4）：拿到值 = real；拿不到 = unavailable
        # v3.1 补：**当日已有读数时不得降级**——否则后一轮的限频会把前一轮的 real 抹成
        #   unavailable，健康矩阵出现「grade=unavailable 但 readings 里有收盘值」的自相矛盾。
        have_value = "pct" in r
        resolved = "real" if have_value else "unavailable"
        if has_dsh and matrix and not have_value:
            _any = matrix.latest_reading(label)
            if _any and str(_any.get("at", ""))[:10] == today:
                resolved = "real"
                entry["grade_note"] = (f"本轮未取到（{r.get('error_kind')}），"
                                       f"沿用当日已有读数 @{str(_any['at'])[:19]} = {_any['value']}%")
                matrix.attempt(label, "finalize: 沿用当日已有读数",
                               f"本轮未取到，但当日已有读数 @{str(_any['at'])[:19]}，grade 保持 real", ok=True)
        if has_dsh and matrix:
            matrix.finalize(label, resolved)
            # 登记读数（#138 B-4：append-only）。标收盘确认状态——报告端据此判断
            # 该值能否作为触发线判据（F5：盘中读数不得作判据）。
            if have_value and reused is None:   # 复用来的读数已在矩阵里，不重复登记
                matrix.reading(label, r["pct"], close_confirmed=cc,
                               source=r.get("query"), close_class=spec.get("close_class"),
                               note=cc_reason)
        entry["grade"] = resolved
        # 序列天数：本脚本只取单日（D-3：不得据此断言「连续 N 日」）
        entry["series_days"] = 1 if "pct" in r else 0

        if "pct" in r:
            diff = entry.get("diff_vs_current")
            diff_s = f"{diff:+.1f}" if isinstance(diff, (int, float)) else "--"
            cur_s = f"{cur_day_pnl:+.1f}" if isinstance(cur_day_pnl, (int, float)) else "--"
            est_s = f"{est:+.1f}" if est is not None else "--"
            cc_s = ("✅已收盘" if cc else "🟡盘中") if cc is not None else "--"
            print(f"{label:<10}{r['pct']:>+9.2f}%{cur_s:>11}{est_s:>12}{diff_s:>9}  {cc_s:<8}{r.get('date','')}")
        else:
            failed.append(f"{label}（{r.get('error')}）")
            entry["error_kind"] = r.get("error_kind")
            tag = {"rate_limited": "限频", "quota_exhausted": "配额",
                   "network": "网络", "source_error": "源错"}.get(r.get("error_kind"), "无数据")
            print(f"{label:<10}{'❌ ' + tag:>10}{'--':>11}{'--':>12}{'--':>9}  {'--':<8}--")
        results.append(entry)

    out = {
        "generated": today,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "spec_source": REGISTRY_PATH if entries else "LEGACY_QUERY_SPECS(回退)",
        "note": "数据回填候选——仅供用户确认，未写入 portfolio_data.json（数据铁律：权威以用户确认为准）；"
                "diff_vs_current=新算估算日盈亏-组合现值，核对后再决定是否回填。"
                "close_confirmed=False 表示读到的是【盘中读数】，不得作为任何触发线判据（手册附录E·F5）。",
        "failed": failed,
        "skipped": skipped,
        "candidates": results,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{today}-数据回填候选.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n候选已生成（未写入 JSON）: {out_path}")

    if has_dsh:
        hp = matrix.write()
        print(f"源健康矩阵已更新: {hp}")

    if failed:
        kinds = sorted({e.get("error_kind") for e in results if e.get("error_kind")})
        print(f"\n[WARN] {len(failed)} 项未成功取数/匹配：")
        for msg in failed:
            print(f"  - {msg}")
        print(f"  原因分类：{', '.join(kinds) or '(未分类·见候选文件 error_kind)'}")
        if kinds and all(k in ("rate_limited", "quota_exhausted") for k in kinds):
            print("  ⚠️ 以上均为【源不可用】而非【无数据】——间隔后重跑即可，不要改查询词。")
        print("候选文件已含成功项；详见 data_source_health.json 的 attempted_sources。")
        return 1
    if skipped:
        print(f"\n[INFO] {len(skipped)} 项按设计跳过：")
        for msg in skipped:
            print(f"  - {msg}")
    print("\n全部标的取数成功。请对照 diff_vs_current 确认后再回填。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
