#!/usr/bin/env python3
"""
Anchor 每日 14:30 盘中建议推送（daily_advice.py）

流程：
  1. 读 portfolio_data.json + data_processor 规则引擎 → 持仓/状态/信号
  2. 妙想 API（东方财富）拉实时行情 → 指数/板块/ETF/溢价率（全部真实数据）
  3. 规则引擎生成「信号清单」（操作次数/时间止损/溢价率/回撤/板块异动）
  4. 组装「事实简报」——数字全部来自 API 与 JSON，AI 禁止编造
  5. 调 AstrBot cron API 创建 run_once 任务 → Agent 查知识库 → 推送到微信
  6. run_once 任务执行后 AstrBot 自动删除；脚本轮询确认执行结果

数据准确性铁律：
  - 行情数字 = 妙想 API 返回原样（标注数据日期）
  - 持仓数字 = portfolio_data.json（用户确认数据，标注日期）
  - LLM 只能引用简报中的数字，简报之外的一律不得编造
  - 行情/JSON 拉取失败 → 当天跳过，绝不用猜测数据顶替

用法: python daily_advice.py
日志: Anchor/05-scripts/daily_advice.log
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from data_processor import process_all  # noqa: E402

DESKTOP = Path.home() / "Desktop"
DATA_PATH = DESKTOP / "portfolio_data.json"
LOG_FILE = Path(__file__).parent / "daily_advice.log"

MX_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw/query"

# 禁用系统代理（Windows urllib 代理劫持坑）
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

ASTRBOT_BASE = "http://127.0.0.1:6185"
ASTRBOT_USER = "astrbot"
# 密码从环境变量读取（setx ASTRBOT_PASSWORD 已永久配置，不写死在源码）
ASTRBOT_PASSWORD = os.environ.get("ASTRBOT_PASSWORD", "")
# 用户微信会话（weixin_oc 管道；MessageType.value 是 FriendMessage 驼峰格式）
# ⚠️ 凭据安全（8/17 审计）：会话 ID 不得写死源码/公开文档，改从环境变量读取
# 设置：setx WECHAT_SESSION "weixin_personal_xxx:FriendMessage:xxx@im.wechat"（用户级永久）
WECHAT_SESSION = os.environ.get("WECHAT_SESSION", "")

# 妙想 API 查询清单（合并查询减少调用次数，每天共 5 次）
MX_QUERIES = [
    ("index", "上证指数 科创50指数 最新收盘价 涨跌幅"),
    ("sector", "半导体板块 创新药板块 证券板块 今日涨跌幅"),
    ("ddx", "半导体板块 今日 DDX 超大单净流入"),  # 8/17 审计：补仓窗口直接进推送
    ("premium", "纳指ETF 溢价率"),
    ("etf", "515180 中证红利ETF 国泰黄金ETF 最新价格 涨跌幅"),
]

SYSTEM_PROMPT = """你是 Anchor 投资系统的每日 14:30 盘中助手。以下「事实简报」是你唯一可用的数据来源：
- 行情数字来自东方财富 API 实时拉取
- 持仓数字来自 portfolio_data.json（用户确认的最新数据）
- 简报中每个数字都标注了数据日期

输出要求（将直接推送到用户微信）：
1. 先简短总结市场与持仓状态（只能引用简报中的数字）
2. 逐条检查「规则信号」，给出明确建议：买入/卖出/加仓/减仓/持有/等待，并说明依据
3. 没有触发规则的不要硬造建议，明确写「今日无操作」
4. 【硬性要求】禁止编造简报之外的任何数字（价格/涨跌幅/盈亏/日期）；简报中没有的就写「以 portfolio 数据为准」
5. 手机阅读排版，emoji 分节，总长控制在 300 字内"""


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------- 1. 数据加载与规则状态 ----------

def load_data() -> dict:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_state(data: dict) -> dict:
    """复用 data_processor 规则引擎（与看板同一套逻辑）"""
    out = process_all(data)
    for key in ("state", "ops_state", "risk_state", "drawdown_state", "freeze_state",
                "holding_counts", "layers"):
        if key not in out:
            out[key] = {}
    return out


# ---------- 2. 妙想 API 实时行情 ----------

def mx_query(text: str, timeout: int = 40) -> list[dict]:
    """查询妙想 API，返回 [{entity, name, value, date}] 最新一期数据"""
    key = os_environ_api_key()
    resp = requests.post(MX_URL, headers={
        "Content-Type": "application/json",
        "apikey": key,
    }, json={"toolQuery": text}, timeout=timeout)
    resp.raise_for_status()
    d = resp.json()
    if d.get("status") != 0:
        raise RuntimeError(f"妙想API错误: {d.get('status')} {d.get('message', '')[:60]}")
    inner = d.get("data", {}).get("data", {})
    sdr = inner.get("searchDataResultDTO", {})
    rows: list[dict] = []
    for t in (sdr.get("dataTableDTOList") or []):
        entity = (t.get("entityName") or "").strip()
        tbl = t.get("table") or {}
        nm = t.get("nameMap") or {}
        dates = tbl.get("headName") or []
        for k, vals in tbl.items():
            if k == "headName" or not vals:
                continue
            name = str(nm.get(k, k))
            date = str(dates[0]) if dates else ""
            # 过滤区间/基准类噪音（如 "2026-05-11至2026-08-07"、"业绩比较基准"）
            if any(w in name or w in date or w in str(vals[0])
                   for w in ("至", "区间", "业绩比较基准", "基准", "换手", "收益率", "合约")):
                continue
            # 板块类接口实体/指标名是反的：entityName 是指标，table key 是板块名
            if "(" in entity and any(w in name for w in ("板块", "指数", "ETF", "证券")):
                entity, name = name, entity
            rows.append({
                "entity": entity.split("(")[0].strip(),
                "name": name,
                "value": str(vals[0]),
                "date": date,
            })
    if not rows:
        raise RuntimeError(f"妙想API无数据: {text[:20]}")
    return rows


def os_environ_api_key() -> str:
    key = os.environ.get("MX_APIKEY")
    if not key:
        raise RuntimeError("MX_APIKEY 环境变量未设置")
    return key


def fetch_quotes() -> dict:
    """返回 {index:[..], sector:[..], premium:[..], etf:[..]} 全部真实行情"""
    out: dict[str, list] = {}
    for group, query in MX_QUERIES:
        out[group] = mx_query(query)
        log(f"行情[{group}]: {len(out[group])} 条")
        time.sleep(2)  # 温和节流，避免触发调用次数限制
    return out


# ---------- 3. 规则信号 ----------

def ddx_ledger_streak() -> tuple[int, str]:
    """读取噪声台账（noise/ddx_daily.json）最近连续为正的天数（8/17 审计新增）。
    台账由每日 21:30 复盘用 noise_audit.py --log-ddx 记录；此处用于 14:30 推送的补仓窗口提示。"""
    try:
        path = Path(__file__).parent.parent / "06-dashboard" / "noise" / "ddx_daily.json"
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0, ""
    data = sorted(data, key=lambda x: str(x.get("date", "")))
    streak, last_val = 0, ""
    for d in reversed(data):
        if d.get("direction") == "positive":
            streak += 1
            last_val = str(d.get("value", ""))
        else:
            break
    return streak, last_val


def build_signals(data: dict, state: dict, quotes: dict) -> list[str]:
    """从状态合同 + 实时行情生成信号清单（全部基于真实数据）"""
    sigs: list[str] = []
    ops = state.get("ops_state") or {}
    if ops:
        n, m = ops.get("count", 0), ops.get("max", 0)
        if ops.get("is_over_limit"):
            sigs.append(f"🔴 月操作 {n}/{m} 已超限，禁止任何买入/加仓")
        elif ops.get("is_at_limit"):
            sigs.append(f"🟡 月操作 {n}/{m} 到上限，本日不建议操作")
        else:
            sigs.append(f"🟢 月操作 {n}/{m}，余额 {m - n} 次")
    # 创新药时间止损（8/20）
    for a in data.get("pending_actions", []):
        text = (a.get("name") or "") + (a.get("action") or "")
        if "时间止损" in text or "8/20" in text:
            upd = (a.get("updated") or "").replace("|", "／")[:60]
            sigs.append(f"⏰ {a.get('name')}｜最新：{upd}")
    # 止损确认自动化（v3.5.2）：次日 14:30 板块方向确认 → 输出可执行指令
    # 规则（从 pending_actions 文案解析阈值，默认 0.5%）：板块跌>阈值 → 执行止损一半；否则延期一天
    for a in data.get("pending_actions", []):
        text = (a.get("name") or "") + (a.get("action") or "")
        if "止损确认" not in text and "止损执行" not in text:
            continue
        sector_kw = next((kw for kw in ("半导体", "创新药", "证券") if kw in text), None)
        m_th = re.search(r"跌\s*[>≥]\s*(\d+(?:\.\d+)?)\s*%", text)
        threshold = float(m_th.group(1)) if m_th else 0.5
        decision = None
        for r in quotes.get("sector", []):
            if "涨跌" not in r["name"]:
                continue
            if sector_kw and sector_kw not in (r.get("entity") or ""):
                continue
            try:
                pct = float(r["value"].rstrip("%"))
            except ValueError:
                continue
            if pct <= -threshold:
                decision = (f"🔴【执行】{sector_kw or '相关'}板块 {r['value']} 跌破 {threshold:.1f}% "
                            f"→ 按规则执行止损一半（{text[:36]}…）")
            else:
                decision = (f"🟢【延期】{sector_kw or '相关'}板块 {r['value']} 未跌破 {threshold:.1f}% "
                            f"→ 止损延期一天，明日 14:30 再确认")
            break
        if decision:
            sigs.append(decision)
        else:
            sigs.append(f"🟡 {a.get('action') or '止损确认'}：板块行情未取到，以人工确认为准")
    # 半导体 DDX 补仓窗口（8/17 审计：台账连击 + 今日实时 DDX 直接进推送，无需翻复盘）
    streak, last_val = ddx_ledger_streak()
    realtime_ddx = None
    for r in quotes.get("ddx", []):
        if "DDX" in r["name"] and "半导体" in (r.get("entity") or ""):
            try:
                realtime_ddx = float(r["value"])
            except ValueError:
                pass
            break
    ddx_txt = f"（今日实时 {realtime_ddx:+.3f}）" if realtime_ddx is not None else ""
    if streak >= 2:
        sigs.append(f"🔬 半导体 DDX 台账连续 {streak} 日为正{ddx_txt} → 补仓条件已满足，按规则执行并记录台账")
    elif streak == 1:
        sigs.append(f"🔬 半导体 DDX 台账第 {streak} 日为正{ddx_txt} → 明日再确认 1 日即满足补仓条件")
    else:
        sigs.append(f"🔬 半导体 DDX 未连正{ddx_txt} → 补仓继续等待（连 2 日为正才动手）")
    # 纳指溢价率（实时）
    for r in quotes.get("premium", []):
        if "折溢价率" in r["name"] or "溢价" in r["name"]:
            try:
                pct = float(str(r["value"]).rstrip("%").replace("+", ""))  # 8/17 审计：'1.5%' 不再抛异常
            except ValueError:
                continue
            tag = f"🔴 溢价率 {pct}% ≥3%，纳指建仓继续冻结" if pct > 3 else \
                  f"🟢 溢价率 {pct}% ≤3%，纳指建仓条件满足（¥500-1000）"
            sigs.append(f"🌐 纳指ETF（{r['entity']}）：{tag}（{r['date']}）")
    # 回撤状态
    dd = state.get("drawdown_state") or {}
    if dd.get("level") == "red":
        sigs.append(f"🔴 回撤 {dd.get('dd_pct')}% 触及红线：{dd.get('action')}")
    elif dd.get("level") == "amber":
        sigs.append(f"🟡 回撤 {dd.get('dd_pct')}% 预警：{dd.get('action')}")
    elif dd.get("safe_cushion") is not None:  # 8/17 审计：契约键为 safe_cushion（原 cushion 永不存在→信号静默丢失）
        sigs.append(f"🟢 回撤安全，距 -5% 线 {dd.get('safe_cushion'):,.0f} 元")
    # 板块异动（|涨跌| ≥2%）
    for r in quotes.get("sector", []):
        if "涨跌" not in r["name"]:
            continue
        try:
            pct = float(r["value"].rstrip("%"))
        except ValueError:
            continue
        if abs(pct) >= 2:
            sigs.append(f"📈 {r['entity']} 波动 {r['value']}（{r['date']}）——" +
                        ("注意止盈/回踩" if pct > 0 else "关注是否触发止损条件"))
    # 冻结状态
    fz = state.get("freeze_state") or {}
    if fz.get("frozen"):
        reasons = fz.get("reasons") or ["见知识库"]  # 8/17 审计：契约键为 reasons（list），原 reason 永不存在
        sigs.append(f"🧊 冻结状态：{reasons[0]}")
    return sigs


# ---------- 4. 简报组装 ----------

def build_brief(data: dict, state: dict, quotes: dict, signals: list[str]) -> str:
    lines = ["## 📊 14:30 盘中事实简报", "> 行情=东方财富API实时｜持仓=portfolio_data.json（用户确认）", ""]
    # 市场
    idx = quotes.get("index", [])
    if idx:
        pts = [r for r in idx if "收盘" in r["name"] or "点位" in r["name"] or "价格" in r["name"]]
        lines.append(f"**市场** " + "｜".join(
            f"{r['entity']} {r['value']}（{r['date']}）" for r in pts[:2]))
        chg = [r for r in idx if "涨跌幅" in r["name"]]
        if chg:
            lines.append("涨跌：" + "｜".join(f"{r['entity']} {r['value']}" for r in chg[:2]))
    # 板块
    sec = [r for r in quotes.get("sector", []) if "涨跌" in r["name"]]
    if sec:
        lines.append(f"**板块** " + "｜".join(
            f"{r['entity']} {r['value']}" for r in sec))
    # ETF 与溢价率
    etf = quotes.get("etf", [])
    if etf:
        lines.append("**ETF** " + "｜".join(
            f"{r['entity']} {r['value']}" for r in etf))
    prem = [r for r in quotes.get("premium", []) if "溢价" in r["name"]]
    if prem:
        lines.append(f"**纳指ETF溢价率** {prem[0]['value']}（{prem[0]['date']}，阈值3%）")
    # 持仓（JSON 确认数据）
    lines.append(f"**持仓**（数据日期 {data.get('update_date', '?')}）总资产 {data.get('total_assets', 0):,.0f}")
    holds = [h for h in data.get("holdings_summary", []) if (h.get("mv") or 0) > 0]
    for h in holds:
        lines.append(f"- {h['name']}：市值 {h.get('mv', 0):,.0f}，持有收益 {h.get('pnl', 0):+,.0f}")
    stocks = data.get("stock_holdings", [])
    for s in stocks:
        lines.append(f"- {s.get('name')}：市值 {s.get('mv', 0):,.0f}，盈亏 {s.get('pnl', 0):+,.0f}")
    # 规则信号
    lines += ["", "## 🚦 规则信号"]
    lines += [f"- {s}" for s in signals] or ["- （无触发）"]
    return "\n".join(lines)


# ---------- 5. AstrBot cron API 推送 ----------

def api_call(path: str, method: str = "GET", token: str | None = None,
             body: dict | None = None, timeout: int = 60):
    headers = {"User-Agent": "daily-advice/1.0", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(ASTRBOT_BASE + path, data=data, headers=headers, method=method)
    try:
        with _NO_PROXY.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}") from e


def push_advice(brief: str, signals: list[str]) -> str:
    """创建 AstrBot run_once cron 任务 → Agent 查知识库 → 推微信。返回 job_id"""
    note = f"{SYSTEM_PROMPT}\n\n---\n\n{brief}"
    body = {
        "name": f"daily_advice_{datetime.now().strftime('%H%M')}",
        "note": note,
        "session": WECHAT_SESSION,
        "run_once": True,
        "run_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "timezone": "Asia/Shanghai",
        "origin": "api",
    }
    token = api_call("/api/v1/auth/login", "POST",
                     body={"username": ASTRBOT_USER, "password": ASTRBOT_PASSWORD})["data"]["token"]
    r = api_call("/api/v1/cron/jobs", "POST", token=token, body=body, timeout=30)
    data = r.get("data", r)
    job_id = data.get("job_id") or data.get("id")
    if not job_id:
        raise RuntimeError(f"创建 cron 任务失败: {json.dumps(r, ensure_ascii=False)[:200]}")
    return str(job_id)


def wait_job_done(job_id: str, timeout: int = 300) -> bool:
    """轮询任务列表，run_once 任务执行后被 AstrBot 自动删除 → 视为完成"""
    token = api_call("/api/v1/auth/login", "POST",
                     body={"username": ASTRBOT_USER, "password": ASTRBOT_PASSWORD})["data"]["token"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(15)
        try:
            r = api_call("/api/v1/cron/jobs", "GET", token=token, timeout=15)
            jobs = r.get("data", r)
            items = jobs.get("jobs", jobs if isinstance(jobs, list) else [])
            ids = [str(j.get("job_id") or j.get("id")) for j in items]
            if job_id not in ids:
                return True  # 已删除 = 执行完成
        except Exception:
            pass  # 继续轮询
    return False


# ---------- 主流程 ----------

def main() -> int:
    if not ASTRBOT_PASSWORD:
        print("[❌] ASTRBOT_PASSWORD 环境变量未设置，无法推送（setx ASTRBOT_PASSWORD 永久配置）")
        return 1
    log("===== daily_advice 开始 =====")
    try:
        # 1. 数据 + 规则状态
        data = load_data()
        state = load_state(data)
        log(f"数据源 OK（update_date={data.get('update_date', '?')}）")
        # 2. 实时行情（失败则整体跳过，不发假数据）
        try:
            quotes = fetch_quotes()
        except Exception as e:
            log(f"行情拉取失败，今日跳过: {e}")
            return 1
        # 3. 信号 + 简报
        signals = build_signals(data, state, quotes)
        brief = build_brief(data, state, quotes, signals)
        log(f"简报已生成（{len(brief)} 字符，信号 {len(signals)} 条）")
        if "--dry-run" in sys.argv:
            print("\n" + "=" * 20 + " 简报预览 " + "=" * 20)
            print(brief)
            log("dry-run 模式，未推送")
            return 0
        # 4. 推送
        job_id = push_advice(brief, signals)
        log(f"cron 任务已创建: {job_id}，等待 Agent 执行并推送微信…")
        done = wait_job_done(job_id)
        log(f"Agent 执行完成" if done else "等待超时（任务可能仍在执行，详见 AstrBot 日志）")
        return 0
    except Exception as e:
        log(f"❌ 异常: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
