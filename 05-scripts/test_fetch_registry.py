# -*- coding: utf-8 -*-
"""取数层回归测试（任务单 #137 / #138）· 2026-09-16 立

配套：test_sync_resilience.py（慢，跑全链路 sync_all）
本文件【不发任何网络请求】，秒级完成，可每次改动后跑。

覆盖：
  A. 注册表加载与按目标展开
  B. 持仓载入读两段（holdings_summary + stock_holdings）
  C. 逐条持仓匹配（含红利 515180 落在 stock_holdings 这一历史缺口）
  D. when_held 跳过逻辑（半导体已清仓）
  E. 收盘判定三态（#138 需求B）
  F. 健康矩阵约束（#138 A-1/A-3）：degraded 必带完整 substitute
  G. 单日资金字段自动降级（#138 D-3/D-4）
  H. A-2 双向断言：DATA_PIPELINE_MAP ↔ 注册表 pipeline_key
  I. 【负向】删掉债券条目 → --coverage 必须 🔴 且指名，还原后全绿
"""
import json, os, shutil, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_auto_fill as daf
import data_pipeline as dp
import data_source_health as dsh

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
fails = []


def ck(name, ok, detail=""):
    print(f"  {'✅' if ok else '❌'} {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        fails.append(name)


print("=== A. 注册表加载与按目标展开 ===")
entries, suffixes, warn = daf.load_registry()
ck("注册表可加载", bool(entries), f"{len(entries) if entries else 0} 条")
specs = daf.registry_to_specs(entries, suffixes)
ck("specs = 条目数+1（债券按目标展开 ×2）", len(specs) == len(entries) + 1, f"{len(entries)} 条目 → {len(specs)} specs")
bond = [s for s in specs if s["key"] == "债券"]
ck("债券展开为 2 条（两只债基各自取数）", len(bond) == 2, " / ".join(s["label"] for s in bond))
alias = [s for s in specs if s["key"] == "纳指A"]
ck("别名兜底未被拆开（纳指A 仍为 1 条，2 个 query）", len(alias) == 1 and len(alias[0]["queries"]) == 2)

print("\n=== B/C. 持仓载入（两段）与逐条匹配 ===")
holdings = daf.load_holdings()
sh = [h for h in holdings if h["segment"] == "stock_holdings"]
ck("stock_holdings 已载入", len(sh) > 0, f"{len(sh)} 条")
missing = []
for s in specs:
    if s["target_kind"] in ("cash",) or s["key"] == "半导体C":
        continue
    h = daf.match_holding(s, holdings)
    if not h:
        missing.append(s["label"])
ck("全部在持标的匹配到持仓", not missing, f"未匹配：{missing}" if missing else "")
red = [s for s in specs if s["key"] == "红利"][0]
red_h = daf.match_holding(red, holdings)
ck("红利 515180 匹配成功（曾因只读单段恒失败）",
   bool(red_h) and red_h["segment"] == "stock_holdings", red_h["name"] if red_h else "None")

print("\n=== D. when_held 跳过 ===")
semi = [s for s in specs if s["key"] == "半导体C"][0]
semi_h = daf.match_holding(semi, holdings)
ck("半导体 fetch=when_held 且 mv=0 → 按设计跳过",
   semi["fetch"] == "when_held" and not (semi_h and semi_h["mv"] > 0))

print("\n=== E. 收盘判定三态（#138 B）===")
# ⚠️ v4.4.11 修正：本段原调用 close_confirmed(cls) 不注入 now，
#    断言的真值随【运行钟点】漂移 —— 9/16 23:5x 跑为 True，
#    9/17 00:02 跑同一断言变 False（当日尚未开盘，False 才是正确答案）。
#    → 一个会按钟点翻脸的断言不是测试，是钟表。已改为注入固定时刻，
#      并对每个边界【两侧都断言】，避免只测「已收盘」单向。
_CLOSED = __import__("datetime").datetime(2026, 9, 16, 23, 50)  # 三类市场均已收盘
_OPEN = __import__("datetime").datetime(2026, 9, 16, 10, 00)    # 三类市场均在盘中
for cls in ("hk", "a_share", "cn_fund_nav", "cash"):
    ok, _ = dsh.close_confirmed(cls, now=_CLOSED)
    ck(f"已收盘时刻 close_confirmed({cls}) = True", ok is True)
for cls in ("hk", "a_share", "cn_fund_nav"):
    ok, _ = dsh.close_confirmed(cls, now=_OPEN)
    ck(f"盘中时刻 close_confirmed({cls}) = False", ok is False)
ok, _ = dsh.close_confirmed("us", now=_CLOSED)
ck("美股盘中 → close_confirmed=False", ok is False)
# ⚠️ 2026-09-17 全库「读挂钟」审计抓出的【漏网孪生】：本行原为
#      dsh.close_confirmed("us", data_date="2026-09-15")     ← 未注入 now
#    就紧挨着上面那段修复注释往下 9 行，却没被一起改到。
#    实跑证明它同样按钟点翻脸：now=2026-09-15 22:00 → False、now=2026-09-14 22:00 → False，
#    【只有挂钟走到 9/16 之后才 True】—— 断言名写「历史数据日期一律判为已结算」，
#    可它测到 data_date 分支纯属【跑得够晚】，不是设计。今天通过 ≠ 逻辑成立。
ok, _ = dsh.close_confirmed("us", now=_CLOSED, data_date="2026-09-15")
ck("历史数据日期一律判为已结算", ok)
# 同一分支的【反向】断言：数据日期就是当天、且当天未收盘时，必须判 False。
_OPEN_0916 = __import__("datetime").datetime(2026, 9, 16, 10, 0)
ok, _ = dsh.close_confirmed("cn_fund_nav", now=_OPEN_0916, data_date="2026-09-16")
ck("数据日期=当天且未收盘 → False（不得把盘中快照当收盘价）", ok is False)
ok, _ = dsh.close_confirmed("未识别类别")
ck("未知资产类别 → False（不得当地收盘价用）", ok is False)

print("\n=== F. 健康矩阵约束（#138 A-1/A-3）===")
m = dsh.HealthMatrix()
for bad_grade in ("degraded", "bogus"):
    try:
        m.finalize("X", bad_grade) if bad_grade == "bogus" else m.finalize("X", "degraded")
        ck(f"grade='{bad_grade}' 应被拒", False)
    except ValueError:
        ck(f"grade='{bad_grade}' 被拒", True)
try:
    m.finalize("X", "degraded", substitute={"used": "513120", "kind": "指数→ETF"})
    ck("substitute 缺 known_bias 应被拒", False)
except ValueError:
    ck("substitute 缺 known_bias 被拒", True)
m.finalize("X", "degraded", substitute={"used": "513120", "kind": "指数→ETF",
                                        "known_bias": "折溢价+跟踪误差，与指数点位不同量纲"})
ck("完整 substitute 通过", m.targets["X"]["grade"] == "degraded")

print("\n=== G. 单日资金字段自动降级（#138 D-3/D-4）===")
f = dsh.flow_field(series_days=1, grade="real", main_flow=-1.2e8)
ck("单日 real → 自动降级 degraded", f["grade"] == "degraded")
ck("单日不得断言「连续 N 日」", f["can_assert_consecutive"] is False)
f2 = dsh.flow_field(series_days=5, grade="real")
ck("5 日 real → 可断言连续", f2["can_assert_consecutive"] is True)
try:
    dsh.flow_field(series_days=None, grade="real")
    ck("series_days 缺失应被拒（D-4 不得只给布尔值）", False)
except ValueError:
    ck("series_days 缺失被拒", True)

print("\n=== H. A-2 双向断言 ===")
mk = set(dp.DATA_PIPELINE_MAP.keys())
rk = {s["pipeline_key"] for s in specs if s["pipeline_key"]}
ck("MAP-only 为空", not (mk - rk), f"{sorted(mk - rk)}")
ck("注册表-only 为空", not (rk - mk), f"{sorted(rk - mk)}")

print("\n=== J. 健康矩阵失败留痕（#138 A-2 / 验收第2条）===")
m2 = dsh.HealthMatrix()
m2.attempt("测试标的", "fake_source_A", "RemoteDisconnected", ok=False)
m2.attempt("测试标的", "fake_source_B", "HTTP 429", ok=False)
m2.attempt("测试标的", "fake_source_C", "OK price=1.23", ok=True)
m2.finalize("测试标的", "real")
tr = m2.targets["测试标的"]["attempted_sources"]
ck("失败尝试也留痕（不只记成功）", len(tr) == 3 and sum(1 for a in tr if not a["ok"]) == 2)
ck("每条留痕带源名/结果/时刻", all(a.get("source") and a.get("result") and a.get("at") for a in tr))
m2.finalize("测试标的", "unavailable")
ck("全败可置 unavailable", m2.targets["测试标的"]["grade"] == "unavailable")

print("\n=== K. 读数 append-only 与取值取自最新（#138 B-4 / 验收第4条）===")
m3 = dsh.HealthMatrix()
m3.reading("纳指", 27150.25, close_confirmed=False, at="2026-09-16T23:50:00+08:00")
m3.reading("纳指", 27188.40, close_confirmed=True, at="2026-09-17T06:30:00+08:00")
ck("两次读数共存不覆盖", len(m3.targets["纳指"]["readings"]) == 2)
ck("按时间取最新 = 次日清晨那条",
   m3.latest_reading("纳指")["value"] == 27188.40)
ck("按收盘确认取 = 只挑 close_confirmed=True",
   m3.latest_reading("纳指", confirmed_only=True)["close_confirmed"] is True)
# 反例：注入的时间戳早于已存在读数时，按【追加顺序】取末条会取错
m3.reading("纳指", 27000.00, close_confirmed=True, at="2026-09-16T06:30:00+08:00")
ck("乱序注入后 latest 仍按时间取（非追加顺序）",
   m3.latest_reading("纳指")["value"] == 27188.40)

print("\n=== L. 收盘确认与判据可用性（#138 B-3 · 手册附录E F5）===")
ok_intraday, _ = dsh.close_confirmed("us", now=__import__("datetime").datetime(2026, 9, 16, 23, 50))
ck("美股盘中 → close_confirmed=False", ok_intraday is False)
ok_close, _ = dsh.close_confirmed("us", now=__import__("datetime").datetime(2026, 9, 17, 6, 30))
ck("次日清晨 → close_confirmed=True", ok_close is True)

print("\n=== I. 【负向】删债券条目 → --coverage 必须拦下并指名 ===")
REG = os.path.join(HERE, "fetch_registry.json")
BAK = REG + ".bak_regtest"
orig = open(REG, "rb").read()
shutil.copyfile(REG, BAK)
same = False
try:
    reg = json.loads(orig.decode("utf-8"))
    reg["entries"] = [e for e in reg["entries"] if e.get("key") != "债券"]
    with open(REG, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
    p = subprocess.run([PY, os.path.join(HERE, "data_pipeline.py"), "--coverage"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ck("退出码为 1", p.returncode == 1)
    ck("输出含 🔴", "🔴" in p.stdout)
    ck("指名「债券」", "债券" in p.stdout)
    ck("点名债基", "鹏华畅享" in p.stdout or "中银稳健增利" in p.stdout)
    ck("A-2 报出「死定义」形态", "死定义" in p.stdout or "取数层无条目" in p.stdout)
finally:
    with open(REG, "wb") as fh:
        fh.write(orig)
    same = open(REG, "rb").read() == orig
    if same and os.path.exists(BAK):
        os.remove(BAK)
ck("还原字节级一致", same)
if same:
    p2 = subprocess.run([PY, os.path.join(HERE, "data_pipeline.py"), "--coverage"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    ck("还原后重新全绿", p2.returncode == 0)

print("\n=== M. index_secid 前缀护栏（v4.5.6 新增）===")
# ⚠️ 编号已查重（`grep '=== [A-Z]\.'`）：A–L 已用 ⇒ 本条取 **M**。
#    📌 顺带记录一处**既有编号失序**（非本次引入，未改）：`I.` 排在 `L.` **之后**
#       —— 同「编号是先占先得，凭记忆写必然撞」之理（v4.4.15 #C1-4 教训）。
#   缘起：注册表里 半导体/证券 的 index_secid 曾写作 **`2.980017` / `2.399975`**，
#   实测 `rc:100 data:null`（东财「无此证券」）⇒ **正确前缀是 `0.`**（深市）。
#   🔴 **为何必须由测试钉住**：错误 secid 的失败长相是
#      · `ulist.np`  → **静默少一条**（不报错，diff 里直接没有）
#      · `stock/get` → `rc:100 data:null`（同样不抛）
#   ⇒ 「取不到」与「该标的无数据」返回值完全一样，**人眼无从分辨**。
#   ⚠️ 本护栏**不联网**：只断言前缀落在**已实测可用**的白名单内。
#      （联网解析校验更彻底，但会把测试变成网络依赖 —— 取舍见 #138「不烧配额」原则）
_KNOWN_GOOD_PREFIX = {
    "0",    # 深市：指数 / ETF / 个股（980017 / 399975 / 159992）
    "1",    # 沪市：指数 / ETF / 个股 / 基金（000922 / 515180 / 513120）
    "90",   # 东财板块（BK1036）
    "100",  # 全球指数 / 美股（NDX100 / DJIA / SPX）
    "101",  # 外盘商品（GC00Y）
    "118",  # 上海黄金交易所（AU9999）
    "124",  # 港股指数（HSSCID）
}
_bad_fmt, _bad_pfx = [], []
for e in entries:
    sid = e.get("index_secid")
    if not sid:
        continue
    segs = str(sid).split(".")
    if len(segs) != 2 or not segs[1]:
        _bad_fmt.append(f"{e['key']}={sid}")
    elif segs[0] not in _KNOWN_GOOD_PREFIX:
        _bad_pfx.append(f"{e['key']}={sid}")
ck("index_secid 格式均为 <市场>.<代码>", not _bad_fmt, str(_bad_fmt) if _bad_fmt else "")
ck("index_secid 前缀均在已实测白名单内（拦住 `2.` 这类无效市场码）",
   not _bad_pfx, str(_bad_pfx) if _bad_pfx else "")
ck("纳指 index_secid 已填正确码（不再只记禁用项）",
   all(e.get("index_secid") == "100.NDX100"
       for e in entries if e.get("key", "").startswith("纳指")),
   "100.NDX100")

# 🔴 反向断言：证明本护栏**确实拦得住**旧值 —— 否则它可能在「压根没生效」下通过
_old = {"key": "__REV__", "index_secid": "2.980017"}
_pfx = str(_old["index_secid"]).split(".")[0]
ck("🔴 反向断言：旧值 `2.980017` 必须被判为非法前缀（否则本护栏是空转）",
   _pfx not in _KNOWN_GOOD_PREFIX)

print("\n" + "=" * 56)
if fails:
    print(f"❌ {len(fails)} 项未通过：")
    for f_ in fails:
        print(f"  - {f_}")
    sys.exit(1)
print("✅ 取数层回归测试全部通过（#137 / #138）")
