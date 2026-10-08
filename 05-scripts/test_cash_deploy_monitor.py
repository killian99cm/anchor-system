#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_cash_deploy_monitor.py — §1.4 补仓监控防回归（2026-10-08 建立）

覆盖：数值解析 / 回撤算法 / **20 日窗口语义（含反向断言）** / 阈值边界 / **三态纪律** / 触发价 / 退出码。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cash_deploy_monitor as m  # noqa: E402

FAIL = []


def check(name, cond, detail=""):
    print(f"{'✅' if cond else '❌'} {name} {detail}")
    if not cond:
        FAIL.append(name)


def _ser(vals):
    """vals → [(date, close)]，日期用递增的 2026-09-DD 形式（仅作标识）。"""
    return [(f"d{i:02d}", float(v)) for i, v in enumerate(vals)]


def main() -> int:
    # ---- T1 数值解析：mx 带单位后缀 / 腾讯纯数字 / 非法值 ----
    check("T1 _num('31082.43点') = 31082.43", m._num("31082.43点") == 31082.43)
    check("T1b _num('1.4300') = 1.43", m._num("1.4300") == 1.43)
    check("T1c _num(4575.02) = 4575.02（已是数值）", m._num(4575.02) == 4575.02)
    check("T1d _num('—') is None（⛔ 不静默按 0）", m._num("—") is None)
    check("T1e _num(None) is None", m._num(None) is None)

    # ---- T2 回撤算法：高点在后、现价在前 ----
    d = m.drawdown(_ser([100, 110, 90]))
    check("T2 高点 110、现值 90 ⇒ 回撤 18.18%",
          d["ok"] and abs(d["dd_pct"] - 18.1818) < 0.01, f"实得 {d.get('dd_pct')}")
    check("T2b 高点日期与现值日期分别正确",
          d["high"] == 110 and d["last"] == 90 and d["high_date"] == "d01" and d["last_date"] == "d02")
    d2 = m.drawdown(_ser([100, 90, 110]))
    check("T2c 现价即最高点 ⇒ 回撤 0%", d2["ok"] and d2["dd_pct"] == 0.0, f"实得 {d2.get('dd_pct')}")
    check("T2d 序列仅 1 条 ⇒ ok=False（⛔ 不硬算）", m.drawdown(_ser([100]))["ok"] is False)

    # ---- T3 🔴 20 日窗口语义：**只数最近 20 条**，更早的高点不得计入 ----
    # 构造：第 1 条是极高点 200（窗口外），其余 20 条最高 100、现值 96
    #   · 正确口径（最近 20 条）⇒ 高点 100 ⇒ 回撤 **4.00%** ⇒ 对 5% 阈值 **未触发**
    #   · 全窗口口径         ⇒ 高点 200 ⇒ 回撤 **52.00%** ⇒ 对 5% 阈值 **触发**
    #   ⇒ 两口径**判定相反**，窗口语义是**载荷**（这正是 T4b 要钉的）。
    # ⚠️ 首版序列设计失误：[200]+[100]*19+[95] 两口径都 ≥5% ⇒ 不构成对照，T4b 恒假。
    old_spike = _ser([200] + [100] * 19 + [96])            # 共 21 条
    d3 = m.drawdown(old_spike, window=20)
    check("T3 窗口外的高点 200 **不计入**（高点应为 100）",
          d3["ok"] and d3["high"] == 100.0, f"实得 high={d3.get('high')}")
    check("T3b 且回撤按 100 算 = 4.00%（低于 5% 阈值）",
          abs(d3["dd_pct"] - 4.0) < 1e-6, f"实得 {d3['dd_pct']}")
    check("T3c n_used = 20（恰为窗口长）", d3["n"] == 20, f"实得 {d3['n']}")

    # ---- T4 🔴 反向断言：若窗口取「全部行」而非「最近 20 行」，**结论必须相反** ----
    d_all = m.drawdown(old_spike, window=len(old_spike))
    check("T4 🔴 反向：全窗口口径 high=200、回撤 52.00%",
          d_all["high"] == 200.0 and abs(d_all["dd_pct"] - 52.0) < 1e-6,
          f"实得 high={d_all['high']} dd={d_all['dd_pct']}")
    check("T4b 🔴 且两口径对 5% 阈值的判定必须相反（证明 T3 的窗口语义是**载荷**）",
          (d_all["dd_pct"] >= 5.0) != (d3["dd_pct"] >= 5.0),
          f"全窗口={d_all['dd_pct']}%({d_all['dd_pct']>=5}) 最近20={d3['dd_pct']}%({d3['dd_pct']>=5})")

    # ---- T5 阈值边界：恰在阈值上算「触发」（≥ 而非 >）----
    def _fx(ln):
        # 高 100、现价 95 ⇒ 回撤恰好 5.00%
        return _ser([100] * 19 + [95])
    ln5 = {"key": "x", "layer": "压舱石", "thr": 5.0, "src": "tencent", "code": "x", "label": "x"}
    r5 = m.evaluate(ln5, fetcher=_fx)
    check("T5 回撤**恰好 5.00%** ⇒ 判「触发」（§1.4 为 ≥）",
          r5["status"] == "触发", f"实得 {r5['status']} dd={r5.get('dd_pct')}")
    check("T5b gap_pp = 0.00（不多不少）", abs(r5["gap_pp"]) < 1e-9, f"实得 {r5['gap_pp']}")

    def _fx2(ln):
        return _ser([100] * 19 + [95.01])          # 回撤 4.99%
    r5b = m.evaluate(ln5, fetcher=_fx2)
    check("T5c 回撤 4.99% ⇒ 判「未触发」", r5b["status"] == "未触发", f"实得 {r5b['status']}")

    # ---- T6 🔴 三态纪律：源失败 ⇒ **不可判定**，⛔ 绝不是「未触发」 ----
    def _boom(ln):
        raise RuntimeError("模拟源不可达")
    r6 = m.evaluate(ln5, fetcher=_boom)
    check("T6 源抛异常 ⇒ status = **不可判定**（⛔ 不得落成「未触发」）",
          r6["status"] == "不可判定", f"实得 {r6['status']}")
    check("T6b 且必须带失败原因（fail-loud，⛔ 不静默）",
          "模拟源不可达" in str(r6.get("reason")), f"reason={r6.get('reason')}")
    check("T6c 不可判定时**不得**出现 dd_pct / trigger_price（⛔ 不伪造数字）",
          "dd_pct" not in r6 and "trigger_price" not in r6)

    # ---- T7 触发价 = 高点 × (1 − 阈值%) ----
    check("T7 trigger_price = 100 × 0.95 = 95.0（压舱石线）",
          r5["trigger_price"] == 95.0, f"实得 {r5.get('trigger_price')}")
    r7 = m.evaluate({**ln5, "thr": 10.0}, fetcher=_fx)
    check("T7b 核心线 10% ⇒ 100 × 0.90 = 90.0", r7["trigger_price"] == 90.0,
          f"实得 {r7.get('trigger_price')}")

    # ---- T8 退出码三态：2=有触发 / 1=有不可判定 / 0=全未触发 ----
    # ⚠️ 首版用 `code="x"`（不存在）⇒ 走了不可判定 ⇒ rc=1 而非 0。**是测试写错了**，
    #    不是 rc 逻辑错。现改为**注入 fetcher**，与真实网络彻底解耦（也更快）。
    _save = m.LINES
    try:
        m.LINES = ({**ln5},)
        _r0 = m.run(fetcher=lambda ln: _ser([100] * 19 + [99]))       # 回撤 1% ⇒ 未触发
        check("T8 全部未触发 ⇒ rc=0", _r0["rc"] == 0, f"实得 {_r0['rc']}")
        check("T8b 且 verdict 明写「现金层**不动**」", "不动" in _r0["verdict"], _r0["verdict"])
        _r1 = m.run(fetcher=_boom)
        check("T8c 源不可达 ⇒ rc=1 且 verdict 明写「⛔ 不得视为未触发」",
              _r1["rc"] == 1 and "不得视为" in _r1["verdict"], f"rc={_r1['rc']}")
        _r2 = m.run(fetcher=_fx)                                       # 回撤 5.00% ⇒ 触发
        check("T8d 有触发 ⇒ rc=2（优先级高于不可判定）", _r2["rc"] == 2, f"实得 {_r2['rc']}")
        _r3 = m.LINES
        m.LINES = ({"key": "a", "layer": "压舱石", "thr": 5.0, "src": "t", "code": "a", "label": "a"},
                   {"key": "b", "layer": "核心", "thr": 10.0, "src": "t", "code": "b", "label": "b"})
        _r4 = m.run(fetcher=lambda ln: (_fx(ln) if ln["key"] == "a" else _boom(ln)))
        check("T8e 同时有「触发」与「不可判定」⇒ rc=2（触发优先），但 both 标志都要为真",
              _r4["rc"] == 2 and _r4["any_triggered"] and _r4["any_unknown"],
              f"rc={_r4['rc']} trig={_r4['any_triggered']} unk={_r4['any_unknown']}")
        m.LINES = _r3
    finally:
        m.LINES = _save

    # ---- T9 🔴 mx 产物定位：**本次没产出 ⇒ 必须报错，⛔ 不得回退用旧产物** ----
    # 这是比「报错」危险得多的失效模式：若回退用别的 `_raw.json`，
    # 会把**上一次/别的问句的值当成今天的**报出来（静默错误值 > 显式缺口）。
    import tempfile
    from pathlib import Path as _P

    _save_mx = m.MX_DATA
    try:
        with tempfile.TemporaryDirectory() as td:
            tdp = _P(td)
            stale = tdp / "mx_data_中债_20200101_raw.json"
            stale.write_text('{"data":{"data":{"data":{"searchDataResultDTO":'
                             '{"dataTableDTOList":[{"table":{"k":["1"],"headName":["2000-01-01"]}}]}}}}}',
                             encoding="utf-8")
            # ① 假脚本「什么都不写」⇒ 本次无产物 ⇒ 必须抛错
            noop = tdp / "fake_noop.py"
            noop.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
            m.MX_DATA = noop
            try:
                m.mx_series("任意问句", out_dir=tdp)
                check("T9 🔴 本次未产出产物 ⇒ **必须抛错**（⛔ 不得回退别的产物）", False,
                      "未抛错 —— 存在把旧值/他值当今日值的风险")
            except RuntimeError as e:
                check("T9 🔴 本次未产出产物 ⇒ **必须抛错**（⛔ 不得回退别的产物）",
                      "未产出" in str(e), f"实得 {str(e)[:80]}")
            check("T9b 且旧产物**仍在**（证明上一步不是靠删文件通过的）", stale.exists())
            # ② 假脚本「真会写文件」⇒ 正常解析（且写进的是**独立子目录**，不会与旧产物混淆）
            fake = tdp / "fake_mx.py"
            fake.write_text(
                "import sys,json,pathlib\n"
                "d=pathlib.Path(sys.argv[2])\n"
                "j={'data':{'data':{'data':{'searchDataResultDTO':{'dataTableDTOList':[{'table':"
                "{'9':['102.5点','100.0点'],'headName':['2026-10-07','2026-10-08']},"
                "'nameMap':{'9':'收盘价'}}]}}}}}\n"
                "(d/'mx_data_fake_20261008_raw.json').write_text(json.dumps(j),encoding='utf-8')\n",
                encoding="utf-8")
            m.MX_DATA = fake
            s = m.mx_series("任意问句", out_dir=tdp)
            check("T9c 产出了新产物 ⇒ 正常解析出 [(date, close)] 序列",
                  s == [("2026-10-07", 102.5), ("2026-10-08", 100.0)], f"实得 {s}")
            check("T9d 🔴 产物落在**独立子目录**（`_run_*`），与旧产物物理隔离",
                  any(p.name.startswith("_run_") for p in tdp.iterdir() if p.is_dir()),
                  f"子目录={[p.name for p in tdp.iterdir() if p.is_dir()]}")
    finally:
        m.MX_DATA = _save_mx

    # ---- T10 🔴 反向断言：mx 返回**降序**（真实行为）⇒ 必须升序规范化，且窗口落在**最新**20条 ----
    # 病灶（2026-10-08 实测）：首版直接 `series[-20:]` ⇒ 取到**最旧**20条、`w[-1]` 成了最旧那条
    # ⇒ 纳指被算成高 30732.40(9/22)、现值 29224.52、回撤 **−4.91%**；
    #   真实应为高 **31224.47(10/6)**、现值 **31082.43(10/8)**、回撤 **−0.46%** ⇒ **错 4.45pp**。
    desc = [("2026-10-08", 100.0), ("2026-10-07", 110.0), ("2026-10-06", 90.0)]
    check("T10 🔴 降序输入 ⇒ `_asc` 升序输出",
          m._asc(desc) == [("2026-10-06", 90.0), ("2026-10-07", 110.0), ("2026-10-08", 100.0)],
          f"实得 {m._asc(desc)}")
    _d_ok = m.drawdown(m._asc(desc))
    check("T10b 升序后：高点 110(10-07)、现值 100(10-08)、回撤 9.09%",
          _d_ok["high"] == 110.0 and _d_ok["last"] == 100.0 and abs(_d_ok["dd_pct"] - 9.0909) < 1e-3,
          f"实得 high={_d_ok['high']} last={_d_ok['last']} dd={_d_ok['dd_pct']}")
    _d_bad = m.drawdown(desc)          # ⛔ 未规范化的降序输入
    check("T10c 🔴 不规范化则读数**不同**（证明规范化是载荷，不是装饰）",
          (_d_bad["high"], _d_bad["last"]) != (110.0, 100.0),
          f"降序直算 high={_d_bad['high']} last={_d_bad['last']}")
    # 端到端：假 mx 写**降序** payload ⇒ mx_series 必须返回**升序**
    import tempfile as _tf
    from pathlib import Path as _PP
    _save2 = m.MX_DATA
    try:
        with _tf.TemporaryDirectory() as td2:
            t2 = _PP(td2)
            fk = t2 / "fake_desc.py"
            fk.write_text(
                "import sys,json,pathlib\n"
                "d=pathlib.Path(sys.argv[2])\n"
                "j={'data':{'data':{'searchDataResultDTO':{'dataTableDTOList':[{'table':"
                "{'9':['96.0点','100.0点','105.0点'],"
                "'headName':['2026-10-08','2026-10-07','2026-10-06']},"
                "'nameMap':{'9':'收盘价'}}]}}}}\n"
                "(d/'mxdata_raw.json').write_text(json.dumps(j),encoding='utf-8')\n",
                encoding="utf-8")
            m.MX_DATA = fk
            got = m.mx_series("任意", out_dir=t2)
            check("T10d 🔴 端到端：mx 降序 payload ⇒ 返回升序序列",
                  got == [("2026-10-06", 105.0), ("2026-10-07", 100.0), ("2026-10-08", 96.0)],
                  f"实得 {got}")
            check("T10e 且 `drawdown` 用到的「现值」是最新那条（96.0），不是最旧的",
                  m.drawdown(got)["last"] == 96.0, f"实得 last={m.drawdown(got)['last']}")
    finally:
        m.MX_DATA = _save2

    print("\n" + "=" * 46)
    if FAIL:
        print(f"❌ {len(FAIL)} 项失败: {FAIL}")
        return 1
    print("✅ 全部通过 —— §1.4 补仓监控基线 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
