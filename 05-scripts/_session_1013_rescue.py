# -*- coding: utf-8 -*-
"""10/13 板块历史抢救：push2his 板块日K → 关键板块 10/8-10/13 日涨幅（close 序列自算）

口径验证（写前必读）：
  - kline 行格式: date,open,close,high,low,volume,amount,chg_field
  - 🔴 chg_field ≠ f3：实测 黄金 10/9 chg_field=6.04，而 close 自算 (6267.88/5914.23-1)=5.98
    = 已入库 days_push2_partial[10/9].BK1617 (f3 口径) 逐位吻合；
    贵金属 10/9 chg_field=5.90，close 自算 =5.42 = 入库值逐位吻合。
  => 采用 close 序列自算，禁止使用 chg_field。
"""
import sys, json, time, datetime
sys.path.insert(0, r"C:\Users\lenovo\Desktop\Anchor\05-scripts")
sys.stdout.reconfigure(encoding="utf-8")

import fetch_public as fp

BOARDS = [
    # (code, name, board_type)
    ("BK1617", "黄金", "行业板块"),
    ("BK0732", "贵金属", "行业板块"),
    ("BK0473", "证券Ⅱ", "行业板块"),
    ("BK1106", "创新药", "概念板块"),
    ("BK0968", "固态电池", "概念板块"),
    ("BK1184", "人形机器人", "概念板块"),
    ("BK0802", "智能驾驶", "概念板块"),
    ("BK0478", "有色金属", "行业板块"),
    ("BK1036", "半导体", "行业板块"),
    ("BK1641", "红利股", "概念板块"),
    ("BK1216", "医药生物", "行业板块"),
    ("BK1044", "生物制品", "行业板块"),
    ("BK1137", "存储芯片", "概念板块"),
    ("BK0475", "银行Ⅱ", "行业板块"),
]

out = {}
log = []
for code, name, btype in BOARDS:
    try:
        r = fp.board_prev_day_chg(code)
        if not r.get("available"):
            log.append(f"🔴 {name}({code}) 取数失败: {r.get('tried')}")
            time.sleep(0.8)
            continue
        closes = []
        for row in r["closes"]:
            parts = row.split(",")
            closes.append((parts[0], float(parts[2])))
        daily = {}
        for i in range(1, len(closes)):
            d, c = closes[i]
            d0, c0 = closes[i - 1]
            daily[d] = round((c / c0 - 1) * 100, 2)
        out[code] = {"name": name, "board_type": btype,
                     "closes": {d: c for d, c in closes}, "chg": daily}
        log.append(f"✅ {name}({code}): " + " | ".join(
            f"{k[5:]}={v:+.2f}" for k, v in daily.items()))
    except Exception as e:
        log.append(f"🔴 {name}({code}) 异常: {type(e).__name__} {e}")
    time.sleep(0.7)  # 温和取数

print("=" * 78)
for line in log:
    print(line)
print("=" * 78)
print("共", len(out), "/", len(BOARDS), "个板块")

# 落盘候选（非生产缓存；供本会话复用与留痕）
dest = r"C:\Users\lenovo\Desktop\Anchor\04-reviews\daily\2026-10-13-板块抢救候选.json"
with open(dest, "w", encoding="utf-8") as f:
    json.dump({"generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "source": "push2his kline close 序列自算（口径=f3 族，已验证逐位吻合）",
               "boards": out}, f, ensure_ascii=False, indent=1)
print("候选已落盘:", dest)
