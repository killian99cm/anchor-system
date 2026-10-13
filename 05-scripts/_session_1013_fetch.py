# -*- coding: utf-8 -*-
"""10/13 盘中数据采集（一次性会话脚本，非持久工具）"""
import sys, json, datetime
sys.path.insert(0, r"C:\Users\lenovo\Desktop\Anchor\05-scripts")
sys.stdout.reconfigure(encoding="utf-8")

import fetch_public as fp

now = datetime.datetime.now()
print("=" * 70)
print(f"10/13 盘中采集 @ {now.strftime('%Y-%m-%d %H:%M:%S')} 星期{['一','二','三','四','五','六','日'][now.weekday()]}")
print("=" * 70)

# ---- 1. 指数（东财 index_quotes）----
print("\n[1] 指数实时")
try:
    idx = fp.index_quotes(["1.000001", "1.000300", "1.000688", "0.399975",
                           "1.000922", "100.HSI"])
    for k, v in idx.items():
        print(" ", k, json.dumps(v, ensure_ascii=False))
except Exception as e:
    print("  [FAIL]", e)

# ---- 2. 板块全量（push2，测可用性）----
print("\n[2] 板块全量 board_movers_all()")
try:
    b = fp.board_movers_all()
    print("  total:", b.get("total"), "fetched:", b.get("fetched"), "complete:", b.get("complete"))
    # 关键板块抽取
    want = ["BK1617", "BK0732", "BK0473", "BK1106", "BK1184", "BK1036"]
    rows = b.get("rows") or []
    for r in rows:
        code = str(r.get("code", ""))
        if any(w in code for w in want) or r.get("name") in (
                "黄金", "贵金属", "证券Ⅱ", "创新药", "人形机器人", "半导体"):
            print("  ", r.get("name"), code, r.get("chg"))
except Exception as e:
    print("  [FAIL]", type(e).__name__, e)

# ---- 3. ETF 日K（腾讯）----
print("\n[3] ETF 日K（末根=盘中价如含今日）")
for code, label in [("sh513120", "创新药ETF"), ("sh515180", "红利ETF"),
                    ("sh512880", "证券ETF"), ("sh518800", "国泰黄金ETF"),
                    ("sh518880", "华安黄金ETF"), ("sh588000", "科创50ETF"),
                    ("usNDX", "纳指100(腾讯usNDX)")]:
    try:
        k = fp.daily_kline(code, 45)
        if not k:
            print(f"  {label}({code}): 空")
            continue
        cl = [r["close"] for r in k]
        ma5, ma10, ma20 = fp.ma(cl, 5), fp.ma(cl, 10), fp.ma(cl, 20)
        last = k[-1]
        prev = k[-2] if len(k) > 1 else None
        chg = None
        if prev:
            chg = (last["close"] - prev["close"]) / prev["close"] * 100
        print(f"  {label}({code}): 末根 {last['date']} close={last['close']}"
              f" 日涨跌={chg:.2f}%" if chg is not None else
              f"  {label}({code}): 末根 {last['date']} close={last['close']}")
        print(f"      MA5={ma5:.4f} MA10={ma10:.4f} MA20={ma20:.4f}")
    except Exception as e:
        print(f"  {label}({code}): [FAIL] {type(e).__name__} {e}")

# ---- 4. 交易日确认（上一交易日）----
print("\n[4] 交易日")
try:
    ref = fp.ref_last_trading_day()
    print("  ref_last_trading_day:", ref)
except Exception as e:
    print("  [FAIL]", e)

print("\n采集结束", datetime.datetime.now().strftime("%H:%M:%S"))
