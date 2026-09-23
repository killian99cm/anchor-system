#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指数注册表与代码—名称一致性校验测试（test_index_registry.py，inbox/135）

覆盖：
  A. 注册表结构完整性（secid + official_name 必备）
  B. 提取规则（表格行/单元格邻近；散文不提取；多代码格跳过）
  C. 判定三态（✅ 命中 / 🔴 张冠李戴 / 🟡 未登记或非注册名）
  D. 负向自测（验收 #4：构造 399811↔国证芯片 必须 🔴；还原后 ✅）
  E. 量级跳变护栏（验收 #5：980017 15895.17→7127.09 必须 🔴 −55.2%；分段 🟡/✅）
运行: python test_index_registry.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_pipeline as dp

REG = dp.load_index_registry()[0]


class RegistryIntegrityTests(unittest.TestCase):
    def test_每条的_secid_与_official_name_必备(self):
        self.assertIsNotNone(REG, "index_registry.json 缺失或损坏")
        for code, ent in REG["indices"].items():
            self.assertRegex(code, r"^\d{6}$")
            self.assertTrue(ent.get("official_name"), f"{code} 缺 official_name")
            self.assertTrue(ent.get("secid"), f"{code} 缺 secid")

    def test_secid_前缀与代码规则一致(self):
        # 0. = 深市/深证/国证，1. = 沪市/中证；同一串数字不同前缀指不同标的（135 附录坑 2）
        for code, ent in REG["indices"].items():
            p = str(ent["secid"]).split(".")[0]
            self.assertIn(p, ("0", "1"), f"{code} secid 前缀异常：{ent['secid']}")
            self.assertEqual(str(ent["secid"]).split(".")[1], code)


class ExtractionTests(unittest.TestCase):
    def test_同格括号写法_命中(self):
        text = "| **CSSW电子(399811)** | 7,192.88 | +1.18% |"
        f, _ = dp.verify_codes_in_text(text, REG["indices"])
        self.assertEqual([x["level"] for x in f], ["✅"])

    def test_相邻格写法_命中(self):
        text = "| **国证芯片**（真实）| **980017** | 15,860.01 |"
        f, _ = dp.verify_codes_in_text(text, REG["indices"])
        self.assertEqual([x["level"] for x in f], ["✅"])

    def test_代码后紧跟简称_命中_经alias(self):
        text = "| 399975 证券 | 728.25 | **728.52** |"
        f, _ = dp.verify_codes_in_text(text, REG["indices"])
        self.assertEqual([x["level"] for x in f], ["✅"])

    def test_散文行不提取(self):
        text = "今日以 399811 收盘价为准，约 7,206.28 点。"
        f, stat = dp.verify_codes_in_text(text, REG["indices"])
        self.assertEqual(f, [])
        self.assertEqual(stat["code_cells"], 0)

    def test_多代码单元格跳过并计数(self):
        text = "| 交易所 ETF 代理价（513120 / 518880 / 399975 等）| 用跟踪标的估算 |"
        f, stat = dp.verify_codes_in_text(text, REG["indices"])
        self.assertEqual(f, [])
        self.assertEqual(stat["multi_code_cells"], 1)

    def test_纯数字token不作名称候选(self):
        text = "| 399975 | 1,943 | 61.2 |"
        f, stat = dp.verify_codes_in_text(text, REG["indices"])
        # 相邻格只有数字 ⇒ 无名称候选 ⇒ 跳过（不得拿「943」当名称去判）
        self.assertEqual(f, [])
        self.assertEqual(stat["no_name"], 1)


class VerdictTests(unittest.TestCase):
    def test_未登记代码_黄灯而非红灯(self):
        text = "| 512990 某新指数 | 1,234.5 |"
        f, _ = dp.verify_codes_in_text(text, REG["indices"])
        self.assertEqual(f[0]["level"], "🟡")
        self.assertIn("未登记", f[0]["msg"])

    def test_相邻串非注册名_明说未校验(self):
        text = "| 今日 399811 微升 | 7,206.28 |"
        f, _ = dp.verify_codes_in_text(text, REG["indices"])
        self.assertEqual(f[0]["level"], "🟡")
        self.assertIn("未校验", f[0]["msg"])


class NegativeSelfTest(unittest.TestCase):
    """验收 #4：构造错误标签 → 必须 🔴 → 还原后 ✅（同一夹具，仅改标签）。"""

    WRONG = "| **国证芯片**（半导体）| sz399811 | 7,127.09 |"
    FIXED = "| **CSSW电子**（半导体）| sz399811 | 7,127.09 |"

    def test_构造错误必须红灯_还原后绿灯(self):
        fw, _ = dp.verify_codes_in_text(self.WRONG, REG["indices"])
        self.assertEqual(fw[0]["level"], "🔴")
        self.assertIn("代码-名称不符", fw[0]["msg"])
        self.assertIn("980017", fw[0]["msg"])          # 指出「国证芯片」归属 980017
        ff, _ = dp.verify_codes_in_text(self.FIXED, REG["indices"])
        self.assertEqual(ff[0]["level"], "✅")

    def test_rc_语义_单文件红灯回1(self):
        tmp = Path(tempfile.mkdtemp(prefix="anchor_135rc_")) / "rep.md"
        tmp.write_text(f"# 夹具报告\n\n{self.WRONG}\n", encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = dp.verify_codes(["--verify-codes", str(tmp)])
        self.assertEqual(rc, 1)
        self.assertIn("代码-名称不符", buf.getvalue())


class MagnitudeGuardTests(unittest.TestCase):
    def test_验收5_事故对_必须红灯_55_2(self):
        rows = dp.magnitude_guard({"980017": (15895.17, 7127.09)})
        self.assertEqual(rows[0]["level"], "🔴")
        self.assertAlmostEqual(rows[0]["pct"], -55.16, delta=0.1)
        # 还原：真实 9/14 → 9/15 收盘量级（15,574.65 → 15,860.01 ≈ +1.83%）
        rows2 = dp.magnitude_guard({"980017": (15574.65, 15860.01)})
        self.assertEqual(rows2[0]["level"], "✅")

    def test_分段阈值_8与15(self):
        self.assertEqual(dp.magnitude_guard({"X": (100.0, 110.0)})[0]["level"], "🟡")
        self.assertEqual(dp.magnitude_guard({"X": (100.0, 103.0)})[0]["level"], "✅")
        self.assertEqual(dp.magnitude_guard({"X": (100.0, 116.0)})[0]["level"], "🔴")
        self.assertEqual(dp.magnitude_guard({"X": (100.0, 84.0)})[0]["level"], "🔴")


if __name__ == "__main__":
    print("=" * 60)
    print("Anchor - Index Registry Test Suite")
    print("=" * 60)
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print()
    print("=" * 60)
    print("ALL TESTS PASSED" if result.wasSuccessful()
          else f"FAILURES: {len(result.failures)} | ERRORS: {len(result.errors)}")
    print(f"   Ran {result.testsRun} tests")
    print("=" * 60)
    sys.exit(0 if result.wasSuccessful() else 1)
