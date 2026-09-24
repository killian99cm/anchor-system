#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单 151 回归：`pre_trade_check` 买入维满额时**必须打印 F7 例外出口**（裁决 #C1-21 方案 A-2 · 手册 v3.18 §1.3 ⑥）

背景
----
**F7**（触发条件性质判据）：「**状态信号**（…／**额度用尽**／…）属**枷锁** ⇒ **必须自带一条可核验的
例外出口**（写明出口的判据与判据源），**否则不得单独作为最终拦截**」；违反形态 ＝
「**无出口的状态信号每日复现、永不消解** ＝ 事实上的永久禁止」。

出口**早已存在**于 §2.4（全局豁免），但 §1.3 未引用、**工具未打印** ⇒ 命中 F7 违反形态
（#C1-21 实测：2026-09-24 三条候选全部只印「不可买入」，读者看不到任何出口）。

本测试的断言
------------
① **正向**：买入维满额 ⇒ 输出含「F7 例外出口」＋ **三项判据** ＋ 判据源（§1.3 ⑥）。
② **判定不变**：满额时结论**仍为**「⛔ 拦截」（出口只**披露**、不**放行**）。
③ 🔴 **反向 A（负向）**：买入维**未满额** ⇒ 输出**不得**含「F7 例外出口」（防无差别刷屏致读者脱敏）。
④ 🔴 **反向 B（承重）**：把披露行**删掉**（＝改回旧写法）跑 ⇒ 输出**不含**出口文案
   ⇒ 证明该打印是**承重的**（即：若有人改回旧写法，① 必红）。

隔离：夹具用 `ANCHOR_DESKTOP=<tmp>` 覆盖数据路径（⛔ 不碰生产 `portfolio_data.json`）；
     反向 B 的副本放在本脚本同目录（⛔ 不用 try/finally 清生产文件：硬杀时 finally 不执行），
     运行后**显式删除**并断言零残留。

运行：python test_pre_trade_f7_exit.py
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import paths  # noqa: E402

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PRE_TRADE = os.path.join(SCRIPTS, "pre_trade_check.py")
PY = sys.executable
EXIT_TAG = "F7 例外出口"


def _fixture(n_buys: int) -> str:
    """造一份 `portfolio_data.json` 夹具（借真实文件的结构，只替换 transactions）。

    `n_buys=2` ⇒ 买入维恰好**满额**（限额 2）；`n_buys=0` ⇒ 未满。
    ⛔ `transactions` 只含当月**买入**（`定投` 等记账腿不计额度）。
    """
    tmp = tempfile.mkdtemp(prefix="anchor_151_")
    src = json.load(io.open(paths.DATA_PATH, encoding="utf-8"))   # 只借结构，不借数据
    ym = date.today().strftime("%Y-%m")
    src["transactions"] = [
        {"date": f"{ym}-01", "op": "买入", "name": "创新药C", "amount": 100.0}
        for _ in range(n_buys)
    ]
    io.open(os.path.join(tmp, "portfolio_data.json"), "w", encoding="utf-8",
            newline="\n").write(json.dumps(src, ensure_ascii=False))
    return tmp


def _run(script: str, desktop: str) -> str:
    env = dict(os.environ, ANCHOR_DESKTOP=desktop)
    r = subprocess.run([PY, script, "创新药", "300", "--sector-chg", "-2.69",
                        "--sector-prev-chg", "0.30"],
                       capture_output=True, env=env)
    return (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")


class TestF7Exit(unittest.TestCase):
    def test_full_quota_prints_exit(self):
        """① 正向：满额 ⇒ 打印出口（含三项判据与判据源）。"""
        out = _run(PRE_TRADE, _fixture(2))
        self.assertIn(EXIT_TAG, out, f"❌ 满额时未打印 F7 出口：\n{out[-600:]}")
        for token in ("用户书面", "decision_log", "T+3", "§1.3 ⑥", "接受违规标记"):
            self.assertIn(token, out, f"❌ 出口文案缺「{token}」")

    def test_full_quota_still_blocks(self):
        """② 判定不变：满额 ⇒ 结论仍为「⛔ 拦截」（出口只披露、不放行）。"""
        out = _run(PRE_TRADE, _fixture(2))
        self.assertIn("⛔ 结论: 拦截", out, f"❌ 出口披露改变了判定：\n{out[-400:]}")

    def test_reverse_not_full_does_not_print_exit(self):
        """🔴 ③ 反向（负向）：**未满额** ⇒ 不得打印出口（防脱敏）。"""
        out = _run(PRE_TRADE, _fixture(0))
        self.assertNotIn(EXIT_TAG, out, "❌ 未满额也打印了出口 ⇒ 无差别刷屏会致读者脱敏")

    def test_reverse_removing_print_makes_positive_fail(self):
        """🔴 ④ 反向（承重）：**删掉披露行**（＝改回旧写法）⇒ 出口文案消失 ⇒ ① 必红。"""
        src = io.open(PRE_TRADE, encoding="utf-8").read()
        # 删掉从「↳ 🔴 F7 例外出口」那条 checks.append 起的整个语句块
        m = re.search(r'\n\s*# 🔴 F7 例外出口披露.*?checks\.append\(\("  ↳ 🔴 F7 例外出口",.*?\)\)\n',
                      src, re.S)
        self.assertIsNotNone(m, "❌ 反向夹具无法定位披露块（源码结构已变 ⇒ 请更新本测试）")
        broken = src[:m.start()] + "\n" + src[m.end():]
        self.assertNotIn(EXIT_TAG, broken, "❌ 删除后仍残留出口文案 ⇒ 删除不完整")
        probe = os.path.join(SCRIPTS, "_f7_reverse_probe.py")   # 必须同目录（imports 兄弟模块）
        io.open(probe, "w", encoding="utf-8", newline="\n").write(broken)
        try:
            out = _run(probe, _fixture(2))
            self.assertNotIn(EXIT_TAG, out,
                             "❌ 删掉披露行后仍打印出口 ⇒ 该打印不是承重的（本测试无鉴别力）")
        finally:
            os.remove(probe)
        self.assertFalse(os.path.exists(probe), "❌ 反向探针未清理（零残留断言）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
