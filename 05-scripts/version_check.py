# -*- coding: utf-8 -*-
"""Anchor 版本一致性校验（v4.3.2 版本冻结协议核心工具）

检查三处版本号是否一致：
  1. CHANGELOG.md 最新版本条目（## vX.Y.Z）
  2. portfolio_data.json 的 system_version（桌面 + 06-dashboard 两副本）
  3. 用户主目录主版本文件版本行

冻结规则（8/27 用户确立）：bump 必须三处一致，否则不进规则手册。
A1 复盘自动化每日自检；手动运行：python version_check.py

用法:
  python version_check.py          # 校验三处一致性
  python version_check.py --sync   # 不一致时把 JSON/主版本文件同步到 CHANGELOG 最新版本（谨慎，仅已知一致时用）
"""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # C1：统一路径真源，禁止硬编码用户目录

DESKTOP = str(paths.DESKTOP)
ANCHOR = str(paths.ANCHOR)
CHANGELOG = os.path.join(ANCHOR, "CHANGELOG.md")
# 09-01 修复：原默认读 ~/.anchor_version.md（不存在）→ 主版本文件恒缺失 → 8/31 审计"三处一致"
# 依赖不可追溯的 ANCHOR_VERSION_FILE 环境变量兜底。现默认指向家目录 CLAUDE.md（版本行恒存在，
# 变更管理铁律强制维护），仍保留环境变量覆盖。
MASTER_VERSION_FILE = os.environ.get(
    "ANCHOR_VERSION_FILE", os.path.join(os.path.expanduser("~"), "CLAUDE.md")
)
JSON_PATHS = [
    os.path.join(DESKTOP, "portfolio_data.json"),
    os.path.join(ANCHOR, "06-dashboard", "portfolio_data.json"),
]

VERSION_RE = re.compile(r"v\d+\.\d+\.\d+[a-z-]*\d*")


def get_changelog_version():
    with io.open(CHANGELOG, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^## (v\d+\.\d+\.\d+[a-z-]*)", line.strip())
            if m:
                return m.group(1)
    return None


def get_json_versions():
    out = {}
    for p in JSON_PATHS:
        try:
            d = json.load(io.open(p, encoding="utf-8"))
            out[p] = d.get("system_version")
        except Exception:
            out[p] = None
    return out


def get_master_version():
    try:
        with io.open(MASTER_VERSION_FILE, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("| 版本 |"):
                    m = VERSION_RE.search(line)
                    if m:
                        return m.group(0).rstrip("-")
    except Exception:
        pass
    return None


def main():
    cl = get_changelog_version()
    js = get_json_versions()
    cm = get_master_version()

    print(f"CHANGELOG 最新: {cl}")
    for p, v in js.items():
        print(f"JSON {os.path.basename(os.path.dirname(p)) or '桌面'}: {v}")
    print(f"主版本文件: {cm}")

    refs = [cl] + list(js.values()) + [cm]
    # 8/31 审计修复：主版本文件缺失时按失败处理（原逻辑过滤 None → 仅比 2 处即宣称「三处一致」假阳性）
    if cm is None:
        print(f"\n❌ 主版本文件缺失: {MASTER_VERSION_FILE}")
        print("   原逻辑将 None 过滤后仅比对 2 处，造成「三处一致」假阳性（8/31 审计修复）")
        return 1
    refs = [r for r in refs if r]
    ok = len(set(refs)) == 1 and refs

    if ok:
        print(f"\n✅ 三处版本一致: {refs[0]}")
        return 0

    print("\n❌ 版本不一致，需统一。来源清单：")
    print(f"  CHANGELOG: {cl}")
    for p, v in js.items():
        print(f"  {p}: {v}")
    print(f"  主版本文件: {cm}")
    print("\n统一方法：以 CHANGELOG 最新条目为准（或先补 CHANGELOG 条目），"
          "再改 JSON system_version 与主版本文件版本行。")
    return 1


if __name__ == "__main__":
    if "--sync" in sys.argv:
        print("⚠️ --sync 模式未启用（避免误写），请手动按清单统一。")
    sys.exit(main())
