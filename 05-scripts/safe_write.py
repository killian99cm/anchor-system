#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
safe_write.py — portfolio_data.json 的唯一安全写入通道（Anchor v4.5）

【为什么存在】
2026-10-31 一天内发现四处账本错误。复盘它们的共同点，不是算错，而是：
    **任何一次写入都没有被任何东西拦下。**
- 在途金额写成申报额 2,658 → 直接落库
- 台账 15 行累计字段为空 → 直接落库
- chart_data 的 star 存了创业板指 → 直接落库，而且 note 里写明了却没人改
- chart_data 缺 10 天 → 直接落库，图表曲线悄悄断掉
没有一处是「写的时候被拒绝」，全是「事后才发现」。本模块把这个顺序倒过来。

【用法】
    from safe_write import commit

    def mutate(data):
        data['total_assets'] = 47114.14
        ...

    commit(mutate, reason="#C1-53 更新 10/22 在途")

或者命令行：
    python safe_write.py --check              # 只审计现有文件
    python safe_write.py --check --strict     # 有 WARN 也算失败

【保证】
  1. 写入前备份到 portfolio_data.json.bak_safewrite_<时间戳>
  2. 变更先落临时文件，再跑 ledger_audit 全量不变量
  3. 有 FAIL ⇒ 删除临时文件、原文件不动、抛 AuditRejected
  4. 通过 ⇒ 原子替换（os.replace），并写一条变更记录到 _meta.write_log
  5. --force 可越过 FAIL，但会强制在 _meta.write_log 留一条「违规写入」痕迹

⛔ 例外：修数据本身就是为了让审计从 FAIL 变 PASS（例如修一个已知错误字段），
   此时该字段往往正是 FAIL 的来源。这种情形用 allow_fail=True + 明确 reason，
   让它变成一条可追责的「已知破窗」，而不是无痕放行。
"""
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import paths
from ledger_audit import run_audit

DATA_PATH = paths.DATA_PATH


class AuditRejected(Exception):
    """写入会破坏账本不变量，已拒绝并回滚。"""

    def __init__(self, fails):
        self.fails = fails
        lines = [f"{f.cid} {f.title}" + (f" —— {f.detail}" if f.detail else "") for f in fails]
        super().__init__("审计未通过，写入已拒绝：\n  " + "\n  ".join(lines))


def _backup(path, tag):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = Path(f"{path}.bak_{tag}_{ts}")
    shutil.copy2(path, dst)
    return dst


def commit(mutate, reason="", allow_fail=False, tag="safewrite", verbose=True, data_path=None):
    """对 portfolio_data.json 做一次受审计的修改。

    mutate: callable(data) -> None（原地修改）；也可返回新 dict
    reason: 变更原因，会写进 _meta.write_log，必填（空则拒绝）
    allow_fail: 已知本次修改会先造成 FAIL（如修的就是审计报错字段）时置 True
    data_path: 仅测试时指定，生产一律走全局 DATA_PATH
    """
    if not reason or not str(reason).strip():
        raise ValueError("commit() 必须给出 reason —— 无理由的写入不允许发生")

    target = Path(data_path or DATA_PATH)
    with open(target, encoding="utf-8") as f:
        original = json.load(f)

    data = json.loads(json.dumps(original))          # 深拷贝，原对象不被污染
    out = mutate(data)
    if isinstance(out, dict):
        data = out

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log = data.setdefault("_meta", {}).setdefault("write_log", [])
    log.append({"at": ts, "reason": str(reason), "via": tag,
                "allow_fail": bool(allow_fail)})
    data["_meta"]["write_log"] = log[-200:]          # 只留最近 200 条

    aud = run_audit(data)
    fails = aud.failed
    if fails and not allow_fail:
        raise AuditRejected(fails)

    tmp = Path(str(target) + ".tmp_safewrite")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    bak = _backup(target, tag)
    os.replace(tmp, target)

    if verbose:
        c = aud.counts()
        state = "🟢 审计通过" if not fails else f"🔴 强制写入（{len(fails)} 项 FAIL 被越过）"
        print(f"[safe_write] {state}｜{ts}")
        print(f"[safe_write] 原因：{reason}")
        print(f"[safe_write] 备份：{bak.name}")
        print(f"[safe_write] 通过 {c['PASS']} 失败 {c['FAIL']} 警告 {c['WARN']} 跳过 {c['SKIP']}")
        for x in fails:
            print(f"[safe_write]   ❌ {x.cid} {x.title}｜{x.detail[:90]}")

    return aud


def check(strict=False, data_path=None):
    p = data_path or DATA_PATH
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    aud = run_audit(data)
    c = aud.counts()
    bad = c["FAIL"] + (c["WARN"] if strict else 0)
    print(f"[safe_write --check] {p}")
    print(f"  通过 {c['PASS']} ｜ 失败 {c['FAIL']} ｜ 警告 {c['WARN']} ｜ 跳过 {c['SKIP']}")
    for x in aud.failed:
        print(f"  ❌ {x.cid} {x.title}")
        if x.detail:
            print(f"     {x.detail}")
        if x.fix:
            print(f"     → {x.fix}")
    if strict:
        for x in aud.checks:
            if x.status == "WARN":
                print(f"  ⚠️  {x.cid} {x.title}｜{x.detail}")
    print("  " + ("🔴 不可写入/不可引用" if bad else "🟢 可安全写入"))
    return 0 if not bad else 1


def main():
    argv = sys.argv[1:]
    if "--check" in argv:
        dp = None
        for i, a in enumerate(argv):
            if a == "--data" and i + 1 < len(argv):
                dp = argv[i + 1]
        sys.exit(check(strict="--strict" in argv, data_path=dp))
    print(__doc__)


if __name__ == "__main__":
    main()
