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


# 🔴 已核实的**合法跳号**（⛔ 不是「容许缺失」；每条须写明核实依据与日期）
KNOWN_SKIPS = {
    # v4.4.15：2026-10-09 核实 —— 该标题在**现行文件**与**近 25 个 commit 的历史版本**中
    #          均搜不到（grep -c "^## v4.4.15" 全为 0）⇒ 系**从未启用该号**，非被吃掉。
    "v4.4": [15],
}


def get_changelog_version_numbers():
    """CHANGELOG 中所有 `## vX.Y.Z` 标题的版本号，按 (major, minor) 分组返回 patch 列表。

    🔴 存在的理由（2026-10-09 建立 · 三次同类失误的机械防线）：
       用 `Edit` 插入新版本条目时，若 `old_string` **含上一版标题前缀**
       而 `new_string` 末尾**未补回**，就会**吃掉上一版标题**，只在文件里留下
       标题的尾巴（以 `：` 或 ` ＋` 开头的一行）⇒ **该版本在 CHANGELOG 中彻底消失**，
       而本器原有的「三处字符串比对」**完全看不出**（三处都不引用那个旧版本号）。
       实测三次：**写 v4.5.47 吃掉 46／写 v4.5.48 吃掉 47／写 v4.5.50 吃掉 49**
       （写 v4.5.49 那次吃掉的是 48，当场发现并补回）。
       ⇒ 本条把「**同 major.minor 下的 patch 编号必须连续**」变成机械可验的硬门禁。
    """
    if not os.path.exists(CHANGELOG):
        return {}
    groups = {}
    with open(CHANGELOG, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^## v(\d+)\.(\d+)\.(\d+)", line)
            if m:
                groups.setdefault((int(m.group(1)), int(m.group(2))), set()).add(int(m.group(3)))
    return groups


def main():
    cl = get_changelog_version()
    js = get_json_versions()
    cm = get_master_version()

    # 🔴 编号连续性硬门禁（2026-10-09 新增）：同 major.minor 下 patch 不得跳号
    gaps = {}
    for (MAJ, MIN), patches in get_changelog_version_numbers().items():
        lo, hi = min(patches), max(patches)
        skip = set(KNOWN_SKIPS.get(f"v{MAJ}.{MIN}", []))
        miss = [n for n in range(lo, hi + 1)
                if n not in patches and n not in skip]
        if miss:
            gaps[f"v{MAJ}.{MIN}"] = miss

    print(f"CHANGELOG 最新: {cl}")
    for p, v in js.items():
        print(f"JSON {os.path.basename(os.path.dirname(p)) or '桌面'}: {v}")
    print(f"主版本文件: {cm}")
    if gaps:
        print("\n❌ CHANGELOG 版本编号**有缺口**（疑似标题被 Edit 吃掉）：")
        for k, v in gaps.items():
            print(f"  {k}: 缺 {v}")
        print("  ⇒ 检查对应位置的**孤儿行**（以 '：' 或 ' ＋' 开头、脱离标题的残留），"
              "把 '## vX.Y.Z — <日期>（<标题前言>' 前缀补回。")
        print("  📌 成因与修法见 version_check.get_changelog_version_numbers 的 docstring。")
        return 1

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
