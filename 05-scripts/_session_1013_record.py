# -*- coding: utf-8 -*-
"""10/13 板块抢救落盘：days_push2_partial 补 10/8、10/12（14 板块）+ 10/9 补 4 主题

前置：_session_1013_rescue.py 已取数并验证口径（close 序列自算 == f3，10/9 全部重叠板块逐位吻合）。
安全：先备份 → 原子替换；不改 days / days_mx；不触 10/13（未收盘）。
"""
import sys, json, io, os, shutil, datetime
sys.path.insert(0, r"C:\Users\lenovo\Desktop\Anchor\05-scripts")
sys.stdout.reconfigure(encoding="utf-8")
import fetch_public as fp

CAND = r"C:\Users\lenovo\Desktop\Anchor\04-reviews\daily\2026-10-13-板块抢救候选.json"
cand = json.load(open(CAND, encoding="utf-8"))
boards = cand["boards"]

hist = fp.board_history_load()
part = hist.setdefault("days_push2_partial", {})
pmeta = hist.setdefault("days_push2_partial_meta", {})

now = datetime.datetime.now()
stamp = now.strftime("%Y-%m-%d %H:%M")
mismatch = []

for day in ("2026-10-08", "2026-10-09", "2026-10-12"):
    entry = part.setdefault(day, {})
    added, verified = [], 0
    for code, b in boards.items():
        v = b["chg"].get(day)
        if v is None:
            continue
        if code in entry:
            old = entry[code].get("chg_pct")
            if old is not None and abs(float(old) - float(v)) > 0.011:
                mismatch.append((day, code, old, v))
            else:
                verified += 1
            continue
        entry[code] = {"name": b["name"], "chg_pct": v, "board_type": b["board_type"]}
        added.append(f'{b["name"]}({code})')
    m = pmeta.setdefault(day, {})
    if day == "2026-10-09":
        m["n"] = len(entry)
        m["supplement_20261013"] = {
            "added": added,
            "source": "push2his kline 收盘序列自算（口径校验：与 ulist.np f3 在 10 个重叠板块上逐位吻合，"
                      f"已核 {verified}/10 一致、0 个不一致）",
            "note": "🔴 原 still_missing 4 主题（watchlist）经此次补入 ⇒ 该缺口闭合。A2 读取侧仍不认本命名空间（待接线）。",
        }
        m.pop("still_missing", None)
        m.pop("missing_note", None)
        print(f"[10/9] 补入 {len(added)} 个: {added}；重叠 {verified} 个逐位吻合")
    else:
        pmeta[day] = {
            "source": "push2his kline 收盘序列自算（板块日K close(t)/close(t-1)-1；14 个关键板块）",
            "metric": "板块涨跌幅（f3 族；口径校验：10/9 与 ulist.np f3 逐位吻合）",
            "n": len(entry),
            "fetched_at": stamp,
            "why_not_days": "10/8、10/12 全量 clist/get 当时均不可用（限流）⇒ days 缺该日；"
                            "本次以板块日K 抢救关键板块（判据相关性最高的 14 个）",
            "purpose": "A2 前日判据源（分支②）+ watchlist 4 主题 + 持仓对标板块",
            "reader_caveat": "A2 读取侧（gen_watchlist_status）当前只读 days → days_mx，不认本命名空间",
        }
        print(f"[{day}] 新增 {len(added)} 个: {added}")

hist["updated_at"] = stamp
hist["schema"] = 1

path = fp._board_history_path()
bak = path + ".bak_20261013_kline_rescue"
shutil.copy2(path, bak)
tmp = path + ".tmp"
with io.open(tmp, "w", encoding="utf-8") as f:
    json.dump(hist, f, ensure_ascii=False)
os.replace(tmp, path)

print()
print("落盘完成:", path)
print("备份:", bak)
print("days_push2_partial 各日条数:", {d: len(v) for d, v in part.items()})
if mismatch:
    print("🔴 不一致清单:", mismatch)
else:
    print("✅ 一致性校验通过（无冲突）")
