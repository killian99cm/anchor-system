# -*- coding: utf-8 -*-
"""10/13 会话档案写入：system_version v4.5.53→v4.5.54 + _meta 三键 + 护栏

纪律：CRLF / 2 空格缩进 / 无尾换行（二进制写）；两 JSON 副本同步；
      写前备份、写后自查（md5 + 解析 + 关键值回读）。
"""
import json
import io
import hashlib
import shutil
import datetime

DESKTOP = r"C:/Users/lenovo/Desktop/portfolio_data.json"
DASH = r"C:/Users/lenovo/Desktop/Anchor/06-dashboard/portfolio_data.json"

raw = open(DESKTOP, "rb").read()
prev_md5 = hashlib.md5(raw).hexdigest()
assert prev_md5 == hashlib.md5(open(DASH, "rb").read()).hexdigest(), "两副本写前应一致"
d = json.loads(raw.decode("utf-8"))
assert d["system_version"] == "v4.5.53", d["system_version"]
assert d["update_date"] == "2026-10-09", d["update_date"]

d["system_version"] = "v4.5.54"
m = d["_meta"]
now_s = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

m["ruling_513120_20261013"] = {
    "id": "E-RULING-513120-2026-10-13",
    "trigger_line": "513120 收盘跌破 MA20（9/24 复盘所立 · E 级 · 判据源=收盘价；次日 14:30 前评估减仓）",
    "triggered_at": "2026-10-12 收盘（1.304 < MA20含当日 1.3070）",
    "ruling_at": "2026-10-13（T+1，F3 义务；当日 14:30 前出具）",
    "verdict": "不减仓（三项 X 级均未触发 ＋ B3 母规则不满足 ＋ 裁量性减仓无规则授权）",
    "convergence": "F6：裁定「不做」⇒ 本线失效；监视移交 §2.2 −8% 止损（X 级）＋ B4 止损状态机",
    "decision_log": "#74",
    "proxy_estimate": "持有率 ≈ −5.97%（10/9 App −4.65% ＋ HSSCID 10/9→10/13 −1.32%）；距 −8% 线 ≈2.03pp；⛔ 代理估算，以 10/12-10/13 App 真值为准",
    "pending": "创新药C 登记入 stop_loss_watch（待今晚 App 真值后办理）",
}

m["board_rescue_20261013"] = {
    "what": "days_push2_partial 抢救落盘：10/8、10/12 各 14 个关键板块 ＋ 10/9 补齐 4 个 watchlist 主题（原缺口闭合）",
    "method": "push2his 板块日K close 序列自算（chg = close(t)/close(t-1)-1）",
    "caliber_check": "与 10/9 ulist.np f3 值在 10 个重叠板块上逐位吻合（|Δ|=0.00pp）⇒ 同口径族；⛔ kline 自带 chg 字段被弃用（与 f3 不一致：黄金 10/9 该字段 6.04 vs f3 5.98）",
    "wiring": "A2 读取侧接线：当日链 live→days→days_push2_partial→days_mx；前日链 days→days_push2_partial→days_mx（前两档同口径族不施容忍带）",
    "tests": "test_a2_partial_fallback.py 8 项（含 3 组反向）全过；test_rule_gates 179/179；test_a2_mx_fallback 13/13",
    "caveat": "days 全量档仍缺 9/24、9/29、10/8、10/9、10/12（缺口登记不变）；本次仅抢救判据相关性最高的 14 个板块",
}

m["t3_72_deferred_20261013"] = {
    "id": "#72（9/30 证券C「持有过节不执行止损」）",
    "due": "2026-10-12（T+3）",
    "status": "逾期未回填（按 --due 设计：判据数据仅至 10/9，早于到期日 ⇒ 不得凭估算硬填）",
    "plan": "今晚 10/12 数据入库后按 --review 72 correct +0.80（399975 715.39→721.09，price_move）回填",
}

m["integrity_hash_guard"] = {
    "purpose": "静默回退护栏：每次权威写入后记录规范 MD5，供后续会话/脚本比对",
    "asof": now_s,
    "algorithm": "md5( json.dumps(doc 且 _meta.integrity_hash_guard={} , ensure_ascii=False, indent=2) 换行→CRLF )",
    "canon_md5": None,
    "md5_prev_file": prev_md5,
    "system_version": "v4.5.54",
    "update_date": "2026-10-09",
    "total_assets": d.get("total_assets"),
    "how_to_use": "下次开工先按 algorithm 重算 canon_md5 与 canon_md5 比对；不符 ⇒ 疑似整档回退/外部改写，先查证再施工",
    "note": "本次为 v4.5.54 会话写入用途：E级裁定#74 + 板块抢救 + A2 接线；数据日仍为 10/09（10/12/10/13 App 真值待入库）",
}


def canon(doc):
    dd = json.loads(json.dumps(doc, ensure_ascii=False))
    dd["_meta"]["integrity_hash_guard"] = {}
    out = json.dumps(dd, ensure_ascii=False, indent=2).replace("\n", "\r\n").encode("utf-8")
    return hashlib.md5(out).hexdigest()


canon_md5 = canon(d)
m["integrity_hash_guard"]["canon_md5"] = canon_md5

out = json.dumps(d, ensure_ascii=False, indent=2).replace("\n", "\r\n").encode("utf-8")
assert not out.endswith(b"\n"), "不得有尾换行"

shutil.copy2(DESKTOP, DESKTOP + ".bak_20261013_v4554")
shutil.copy2(DASH, DASH + ".bak_20261013_v4554")
open(DESKTOP, "wb").write(out)
open(DASH, "wb").write(out)

# ---- 写后自查 ----
b1 = open(DESKTOP, "rb").read()
b2 = open(DASH, "rb").read()
d2 = json.loads(b1.decode("utf-8"))
assert b1 == b2, "两副本写后应一致"
assert d2["system_version"] == "v4.5.54"
assert d2["update_date"] == "2026-10-09"
assert d2["_meta"]["integrity_hash_guard"]["canon_md5"] == canon(d2), "canon 自洽校验失败"
print("✅ 写入完成")
print("   prev md5:", prev_md5)
print("   new  md5:", hashlib.md5(b1).hexdigest(), "(两副本一致:", b1 == b2, ")")
print("   canon md5:", canon_md5)
print("   system_version:", d2["system_version"], "| update_date:", d2["update_date"])
print("   total_assets:", d2["total_assets"])
for k in ("ruling_513120_20261013", "board_rescue_20261013", "t3_72_deferred_20261013"):
    assert k in d2["_meta"], k
print("   _meta 三键在位 ✓")
