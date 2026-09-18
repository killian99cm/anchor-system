# -*- coding: utf-8 -*-
"""#137 验收第5条：注入一次确定性取数失败 → 跑 sync_all → 证明取数失败【不中断】每日链路。

设计要点：注入的假条目必须让 0.6 步失败，但【不能】让 0.5 覆盖度失败——
否则分不清是哪一层拦下的。故假条目 pipeline_key 用已有的「通利」（不产生孤儿键），
holdings_match 用不存在的持仓名（不干扰活跃持仓的覆盖判定），query 故意查不到。
安全（v4.5.1 重做）：
  🔴 **不再碰生产文件** —— 本测试改为在**临时副本**上注入，生产 `fetch_registry.json`
     通过 `ANCHOR_FETCH_REGISTRY` 环境变量被子进程绕开。
     旧版直接改生产文件、靠 `try/finally` 还原；**硬杀（超时/SIGKILL）下 finally 不执行**
     ⇒ 2026-09-17 23:08 那次运行把假条目 `__TEST_FAIL__` 永久留在了生产注册表里，
     还连带让 `test_fetch_registry` 长期失败、卡住 smoke_test。
     **教训：「靠 finally 保证不污染」在进程被硬杀时不成立 —— 不碰生产文件才是真隔离。**
  另：启动时**自愈**——若发现历史遗留的哨兵条目或 `.bak_syncfail_test`，先清掉再跑。
"""
import json, os, shutil, subprocess, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(HERE, "fetch_registry.json")
BAK = REG + ".bak_syncfail_test"
PY = sys.executable

# ── 自愈：清理历史遗留污染（旧版硬杀所致）────────────────────────────
_healed = []
try:
    _r = json.load(open(REG, encoding="utf-8"))
    _n = len(_r.get("entries", []))
    _r["entries"] = [e for e in _r.get("entries", []) if e.get("key") != "__TEST_FAIL__"]
    if len(_r["entries"]) != _n:
        json.dump(_r, open(REG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        _healed.append(f"清除遗留哨兵 {_n - len(_r['entries'])} 条")
except Exception as _e:
    print(f"[自愈][WARN] 注册表检查失败：{_e}")
if os.path.exists(BAK):
    os.remove(BAK)
    _healed.append("删除遗留 .bak_syncfail_test")
print("[自愈] " + ("；".join(_healed) if _healed else "无历史遗留污染") + "\n")

# ── 隔离：在临时副本上注入，生产文件全程只读 ──────────────────────
_TMP = tempfile.mkdtemp(prefix="anchor_sync_resilience_")
WORK_REG = os.path.join(_TMP, "fetch_registry.json")
shutil.copyfile(REG, WORK_REG)
os.environ["ANCHOR_FETCH_REGISTRY"] = WORK_REG   # 子进程经环境变量继承 → 绕开生产文件
orig = open(WORK_REG, "rb").read()
_PROD_ORIG = open(REG, "rb").read()   # 生产文件起始字节，收尾时断言其未被改动
same = False

try:
    reg = json.loads(orig.decode("utf-8"))
    reg["entries"].append({
        "key": "__TEST_FAIL__",
        "label": "【测试】故意取不到数的假标的",
        "pipeline_key": "通利",                  # 用已有键 → 不制造 A-2 孤儿
        "holdings_match": ["__不存在的持仓XYZ__"],  # 不干扰活跃持仓覆盖判定
        "target_kind": "nav",
        "close_class": "cn_fund_nav",
        "underlying_market": "cn",
        "queries": [{"q": "__不存在的基金XYZ__", "match": ["__不存在的持仓XYZ__"]}],
        "fetch": "always",
        "note": "测试注入，跑完即删",
    })
    with open(WORK_REG, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    print(f"[注入] 已加假条目 __TEST_FAIL__（pipeline_key=通利，持仓/查询均不存在）")
    print(f"[隔离] 注入目标 = 临时副本 {WORK_REG}\n       生产注册表 {REG} 全程只读\n")

    # 先单独跑 0.5，确认【不是】覆盖度拦下的
    p05 = subprocess.run([PY, os.path.join(HERE, "data_pipeline.py"), "--coverage"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(f"[预检] --coverage rc={p05.returncode}（期望 0：假条目不破坏覆盖度判定）")
    print(f"       {p05.stdout.strip().splitlines()[-1]}\n")

    # 再单独跑取数，确认它会失败
    p06 = subprocess.run([PY, os.path.join(HERE, "data_auto_fill.py")],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=900)
    print(f"[预检] data_auto_fill rc={p06.returncode}（期望 1：确实失败）")
    tail = [l for l in p06.stdout.splitlines() if "__TEST_FAIL__" in l or "未成功取数" in l]
    for l in tail[:4]:
        print("       ", l)
    print()

    # 全链路 sync_all —— 关键断言：0.6 失败但 sync 不中断
    p = subprocess.run([PY, os.path.join(HERE, "sync_all.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=1800)
    out = p.stdout + p.stderr
    print("=== sync_all 关键行 ===")
    for l in out.splitlines():
        if any(k in l for k in ("0.5", "0.6", "取数", "Sync", "同步完成", "失败步",
                                "❌", "🔴", "[FAIL]", "SUCCESS", "FAILED")):
            print("  ", l)
    print(f"\n[sync_all] rc={p.returncode}")

    # 判据说明：不能以 rc==0 断言「未中止」——步骤 7 版本一致性自检是【既有】致命项
    # （JSON 停在 v4.4.7，随 #134 入库才升 v4.4.10），与本次改动无关。
    # 真正要证的是：0.6 失败后【链路仍在推进】，即 0.6 之后的步骤确实执行了。
    after_06 = out.split("0.6.取数候选 [FAILED", 1)
    progressed = (len(after_06) > 1 and "7.版本一致性自检" in after_06[1])
    checks = [
        ("0.5 覆盖度仍通过（假条目未污染该层）", p05.returncode == 0),
        ("0.6 取数确实失败（rc=1）", p06.returncode == 1),
        ("0.6 判为【非致命·继续】", "非致命，继续" in out),
        ("0.6 之后链路仍在推进（步骤7已执行）", progressed),
        ("结尾回执已生成（跑到最后一步）", "回执 |" in out),
    ]
    print("\n— 验收断言 —")
    bad = 0
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
        if not ok:
            bad += 1
finally:
    # 还原副本（副本即使没还原成功也无所谓 —— 它随临时目录一起删）
    with open(WORK_REG, "wb") as f:
        f.write(orig)
    same = open(WORK_REG, "rb").read() == orig
    print(f"\n[还原] 副本字节级一致：{'✅' if same else '❌ 不一致！'}")
    # 🔴 关键断言换成**生产文件从未被改动** —— 这才是本测试真正要保证的事
    prod_untouched = open(REG, "rb").read() == _PROD_ORIG
    print(f"[隔离] 生产注册表全程未被改动：{'✅' if prod_untouched else '❌ 被改动了！'}")
    shutil.rmtree(_TMP, ignore_errors=True)
    os.environ.pop("ANCHOR_FETCH_REGISTRY", None)
    same = same and prod_untouched

print("\n" + "=" * 50)
print("✅ 验收第5条通过：取数失败不中断每日链路" if (bad == 0 and same) else "❌ 验收第5条未通过")
sys.exit(0 if (bad == 0 and same) else 1)
