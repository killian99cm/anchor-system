#!/usr/bin/env python3
"""
Anchor smoke 测试 — 端到端完整性验证 (短板1)
在 rebuild.py 运行后，验证生成产物是否完整、关键数据是否嵌入。

用法: python smoke_test.py
"""
import hashlib
import json
import re
import shutil
import sys
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import paths

# 🔴 必须最先重设 stdout 编码（2026-09-24 修复）：
#   本脚本的**失败路径**会打印含 emoji 的 `detail`（如 `validate_integrity` 的 🔴 硬项），
#   而 Windows 控制台默认 **cp936(GBK)** ⇒ `UnicodeEncodeError` **把「红」变成「崩」**：
#   真实症状＝一个断言失败时，套件在 `check()` 的 print 处中断，**读者拿到的是 traceback
#   而不是失败清单**（本次实测：4 项失败被截成 1 段崩溃）。
#   同族病史：v4.5.23 `sync_all` 9.5 步（JSON 值含 `⇒` 打到 cp936 而崩）—— 同一根因。
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DESKTOP = paths.DESKTOP
ANCHOR = paths.ANCHOR
SCRIPTS = paths.SCRIPTS
PY = sys.executable
PUBLIC_DATA_PATH = paths.DASHBOARD_DIR / "portfolio_data_example.json"
PUBLIC_HTML_PATH = ANCHOR / "08-website" / "anchor-pro.html"
EXAMPLE_HTML_PATH = paths.DASHBOARD_DIR / "portfolio_analysis_example.html"

PASS, FAIL, SKIP = 0, 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def skip(name, detail=""):
    """🔴 三态的第三态（inbox/144 R1/验收④）：**无法判定 ≠ 通过 ≠ 失败**。

    静默 skip 与静默通过同样危险（v4.5.4）：本态必须**显式、带原因、与 [FAIL] 可分**，
    且**不得计入 PASS**（「没测到」渲染成「测了且过了」正是 144 要治的病）。
    """
    global SKIP
    SKIP += 1
    print(f"  [SKIPPED] {name}" + (f" — {detail}" if detail else ""))


def file_hash(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def read_html_embed(path):
    html = path.read_text(encoding="utf-8")
    match = re.search(r"var\s+D\s*=\s*(\{.*?\});\s*\n", html, re.DOTALL)
    if not match:
        raise ValueError(f"未找到 {path.name} 中的 var D 数据块")
    return html, json.loads(match.group(1))


def check_inline_script_syntax(path):
    html = path.read_text(encoding="utf-8")
    match = re.search(r"<script>([\s\S]*)</script>", html)
    if not match:
        return False, "no inline script"
    script = match.group(1)
    node = shutil.which("node")
    if not node:
        return False, "node 不可用（未安装或不在 PATH），跳过 JS 语法检查"
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tmp:
        tmp.write("new Function(" + json.dumps(script) + ");\n")
        script_path = tmp.name
    try:
        result = subprocess.run(
            [node, script_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except FileNotFoundError:
        return False, "node 不可用（未安装或不在 PATH）"
    finally:
        try:
            Path(script_path).unlink()
        except OSError:
            pass
    if result.returncode == 0:
        return True, ""
    detail = (result.stderr or result.stdout).strip().splitlines()[-1] if (result.stderr or result.stdout) else "script syntax error"
    return False, detail


def contains_token(text, token):
    if not token:
        return False
    if token in text:
        return True
    compact_text = re.sub(r"\s+", "", text)
    compact_token = re.sub(r"\s+", "", token)
    return bool(compact_token and compact_token in compact_text)


def private_tokens_guard():
    """114/#C1-19：私有标记 token 集 —— **单一真源 ＝ gen_anchor_pro**（v4.5.4 修复版实现）。

    ⛔ 不得在本文件另建第二套 token 派生（历史缺陷 #C1-19：本文件旧内联实现有两个误报源——
    ① 用**页面 embed** 的金额派生 token，示例页金额为 0 ⇒ 产生退化 token `'0'` ⇒ 恒命中；
    ② 把 active_label 计入 token，示例页用示例数据渲染同名计数 ⇒ 必然误报。
    gen 侧实现只从**本地真实持仓**派生（数值仅取**非零**值、含名字/代码），且带
    CSS 长度单位豁免（v4.5.4）——升级为同一实现即为「单一真源」，两个误报源随之消失。）
    """
    import gen_anchor_pro as gap
    return gap.private_tokens_from_local_portfolio(), gap.contains_sensitive_token


def main():
    print("=" * 60)
    print("Anchor smoke 测试 — 端到端产物完整性")
    print("=" * 60)

    # 0. 确保最新产物（先跑 rebuild 与公开页生成）
    print("\n[0] 运行 rebuild.py / gen_anchor_pro.py ...")
    r = subprocess.run(
        f'"{PY}" "{SCRIPTS / "rebuild.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=120
    )
    check("rebuild.py 退出码 0", r.returncode == 0, f"(rc={r.returncode})")
    r_pub = subprocess.run(
        f'"{PY}" "{SCRIPTS / "gen_anchor_pro.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    check("gen_anchor_pro.py 退出码 0", r_pub.returncode == 0, f"(rc={r_pub.returncode})")

    # 1. 源 JSON
    print("\n[1] 源数据 portfolio_data.json")
    data_path = DESKTOP / "portfolio_data.json"
    check("portfolio_data.json 存在", data_path.exists())
    data = {}
    if data_path.exists():
        with open(data_path, encoding='utf-8') as f:
            data = json.load(f)
        check("total_assets 为正数", data.get('total_assets', 0) > 0,
              f"(total={data.get('total_assets')})")
        check("holdings_summary 非空", len(data.get('holdings_summary', [])) > 0)
        check("_meta.peak_assets 存在", data.get('_meta', {}).get('peak_assets') is not None,
              "回撤基准缺失!")
        check("update_date 存在", bool(data.get('update_date') or data.get('update_time')),
              "日期缺失!")

    # 1b. 结构化入库自检（v4.4.0 护栏镜像；对应 sync_all 步骤0 / data_pipeline --integrity）
    print("\n[1b] 结构化入库自检 validate_integrity")
    if data:
        ud = str(data.get('update_date', ''))
        chart = data.get('chart_data', [])
        sm = data.get('daily_summaries', [])
        check("chart_data 无重复 d", len({c.get('d') for c in chart if c.get('d')}) == len([c for c in chart if c.get('d')]))
        if chart and ud:
            check("chart 末条 == update_date", str(chart[-1].get('d', '')) == ud[-5:],
                  f"(chart={chart[-1].get('d')} vs update_date={ud})")
        if sm and ud:
            check("summaries 末条 == update_date", str(sm[-1].get('date', ''))[:10] == ud[:10],
                  f"({sm[-1].get('date')} vs {ud})")
        mdate = str((data.get('market') or {}).get('date', ''))
        if mdate and ud:
            check("market.date == update_date", mdate[:10] == ud[:10], f"({mdate} vs {ud})")
        ta, fa, sa = (data.get(k) for k in ('total_assets', 'fund_account', 'stock_account'))
        if isinstance(ta, (int, float)) and isinstance(fa, (int, float)) and isinstance(sa, (int, float)):
            check("total == fund + stock (±0.01)", abs(ta - (fa + sa)) <= 0.01, f"({ta} vs {fa}+{sa})")
        _wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        wbad = []
        for s in sm[-5:]:
            dt, dy = str(s.get('date', ''))[:10], str(s.get('day', ''))
            try:
                wd = datetime.strptime(dt, '%Y-%m-%d').weekday()
            except (ValueError, TypeError):
                continue
            if dy and _wd[wd] not in dy:
                wbad.append((dt, dy))
        check("末5条 summaries 星期正确", not wbad, f"({wbad})")
        from data_processor import validate_integrity
        hard = [p for p in validate_integrity(data) if p.startswith('🔴')]
        check("validate_integrity 无硬项", not hard, f"(共{len(hard)}项: {'; '.join(hard[:2])})")
        # 页面 freshness 证据（产物由 sync_all 生成；缺失文件即 FAIL，暴露链路断点）
        for label, path, token in (
            ("HTML 顶栏渲染数据日期", DESKTOP / 'portfolio_analysis.html', ud[:10]),
            ("daily_hub 含入库时刻", ANCHOR / '06-dashboard' / 'daily_hub.html', str(data.get('update_time', ''))[:16]),
            ("决策仪表盘含数据源时刻", ANCHOR / '06-dashboard' / 'decision_dashboard.html', '数据源更新'),
        ):
            if token and path.exists():
                txt = path.read_text(encoding='utf-8', errors='replace')
                check(label, token in txt, f"(缺 token={token!r})")
            elif token:
                check(label, False, f"(缺 {path.name})")
            else:
                check(label, True, "(无 token，跳过)")

    # 1c. 报告时间校验（v4.4.4 时间错标防御 L4）
    #     2026-09-11 事故：报告把 9/15 写成「周一」（实为周二）、9/13 写成「周六」（实为周日）。
    #     这里只断言「最新报告没有新增的星期错标」——注意不是「全库为零」：
    #     历史上仍有 28 处存量错标（归档未改写，见 00-system/2026-09-11-时间错标事故…）。
    print("\n[1c] 报告时间校验 report_time_check")
    rtc = SCRIPTS / "report_time_check.py"
    if not rtc.exists():
        check("report_time_check.py 存在", False, f"(缺 {rtc.name})")
    else:
        rep = [p for p in (ANCHOR / '04-reviews').rglob('*.md') if p.is_file()]
        if not rep:
            check("04-reviews 下存在报告", False)
        else:
            latest = max(rep, key=lambda p: p.stat().st_mtime)
            try:
                sys.path.insert(0, str(SCRIPTS))
                from report_time_check import check_text
                # 🔴 2026-09-17 修·年份炸弹：原传 `datetime.now().year` ——
                #    实跑同一份报告：--year 2026 → 🔴2；--year 2027 → 🔴15。
                #    今天不炸只因最新报告恰好无星期标注；下一位把含「M/D（周X）」的
                #    报告放到 04-reviews 最新位的人，会在跨年时收到一条与他改动无关的红灯。
                #    → 改由【文档自身】推年份（path=latest 优先读文件名里的日期）。
                _res = check_text(latest.read_text(encoding='utf-8', errors='replace'),
                                  path=latest)
                if _res.get('year') is None:
                    # 推不出年份 → 不校验星期。**显式说出来**，不当作通过。
                    print("      ⚠️ 该报告推不出年份（文件名/正文均无 20XX），"
                          "星期校验已跳过 —— 不判负，但也不冒充通过")
                bad = [f"行{h['line']}「{h['text']}」应为{h['expected']}" for h in _res['a']]
                check(f"最新报告无星期错标（{latest.name[:32]}，年份源 {_res.get('year_source')}）",
                      not bad, f"({'；'.join(bad[:2])})")
                # 🟡 只记录不判负：场外「收盘价」作触发线是待整改的表述习惯，非硬错误
                if _res['b']:
                    print(f"      ⚠️ 时点可执行性存疑 {len(_res['b'])} 处（提示级，不计失败）")
            except Exception as e:
                check("report_time_check 可导入并可运行", False, f"({e})")

    # 2. HTML 产物
    print("\n[2] portfolio_analysis.html")
    embed = {}
    html_path = DESKTOP / "portfolio_analysis.html"
    check("HTML 存在", html_path.exists())
    if html_path.exists() and data:
        try:
            html, embed = read_html_embed(html_path)
        except (ValueError, json.JSONDecodeError) as exc:
            html, embed = "", {}
            check("HTML var D 数据块解析", False, str(exc))
        check("HTML 大小 > 20KB", len(html) > 20000, f"({len(html)} bytes)")
        script_ok, script_detail = check_inline_script_syntax(html_path)
        check("HTML 内嵌脚本语法正确", script_ok, script_detail)
        check("HTML 含峰值数据", "peak_assets" in html)
        check("HTML 含今日结论", '"today"' in html)
        check("HTML 含操作计数", "aug_ops" in html)
        check("HTML 含四层数据", '"bedrock"' in html and '"sat"' in html)
        check("HTML 含 chart 数据", '"chart"' in html)
        check("HTML 含 state 合同", '"state"' in html and '"freeze_state"' in html)
        check("HTML 含动态持仓计数", '"holding_counts"' in html and '"layers"' in html)
        check("HTML 不含写死持仓数量", '10只基金 + 1只股票 + 余额宝' not in html and '10只活跃持仓' not in html)
        check("HTML 不含写死层级市值", '18626' not in html and '5875' not in html and '5428' not in html)
        check("embed.total ≈ total_assets", abs(embed.get('total', 0) - data.get('total_assets', 0)) < 100,
              f"(embed={embed.get('total')} vs json={data.get('total_assets')})")
        check("embed.dd_pct 合理范围", -50 < embed.get('dd_pct', 0) < 50,
              f"(dd_pct={embed.get('dd_pct')})")
        check("embed 包含 ops_state", 'ops_state' in embed and 'risk_state' in embed)
        check("embed 含动态持仓合同", 'holding_counts' in embed and 'layers' in embed and 'layer_order' in embed and 'layer_meta' in embed)
        check("embed source_update_date 一致", str(embed.get('source_update_date', ''))[:10] == str(data.get('update_date', data.get('update_time', '')))[:10],
              f"(embed={embed.get('source_update_date')} vs json={data.get('update_date')})")

    # 3. 快照
    print("\n[3] portfolio_snapshot.json")
    snap_path = DESKTOP / "portfolio_snapshot.json"
    check("快照存在", snap_path.exists())
    if snap_path.exists() and data:
        with open(snap_path, encoding='utf-8') as f:
            snap = json.load(f)
        check("快照 total_assets 一致", abs(snap.get('total_assets', 0) - data.get('total_assets', 0)) < 100,
              f"(snap={snap.get('total_assets')} vs json={data.get('total_assets')})")
        check("快照 layer_summary 四层完整", all(k in snap.get('layer_summary', {}) for k in ['bedrock', 'core', 'sat', 'cash']))
        check("快照 state 合同完整", all(k in snap for k in ['state', 'drawdown_state', 'ops_state', 'risk_state', 'freeze_state']))
        check("快照含动态持仓合同", 'holding_counts' in snap and 'layers' in snap and 'layer_order' in snap and 'layer_meta' in snap)
        check("快照 source_update_date 一致", str(snap.get('source_update_date', ''))[:10] == str(data.get('update_date', data.get('update_time', '')))[:10],
              f"(snap={snap.get('source_update_date')} vs json={data.get('update_date')})")

    # 4. Excel 产物
    print("\n[4] portfolio_holdings.xlsx")
    xlsx_path = DESKTOP / "portfolio_holdings.xlsx"
    xlsx_anchor = ANCHOR / "06-dashboard" / "portfolio_holdings.xlsx"
    check("Excel 存在(桌面)", xlsx_path.exists())
    check("Excel 存在(Anchor)", xlsx_anchor.exists())
    if xlsx_path.exists():
        check("Excel 大小 > 10KB", xlsx_path.stat().st_size > 10000, f"({xlsx_path.stat().st_size} bytes)")

    # 5. 副本一致性
    print("\n[5] 桌面 vs Anchor 副本")
    html_copy = ANCHOR / "06-dashboard" / "portfolio_analysis.html"
    snap_copy = ANCHOR / "06-dashboard" / "portfolio_snapshot.json"
    check("HTML 副本存在(桌面)", html_path.exists())
    check("HTML 副本存在(Anchor)", html_copy.exists())
    if html_path.exists() and html_copy.exists():
        check("HTML 副本内容一致", file_hash(html_path) == file_hash(html_copy), "HTML 内容不一致")
    check("快照副本存在(桌面)", snap_path.exists())
    check("快照副本存在(Anchor)", snap_copy.exists())
    if snap_path.exists() and snap_copy.exists():
        check("快照副本内容一致", file_hash(snap_path) == file_hash(snap_copy), "快照内容不一致")

    # 6. 公共发布边界
    print("\n[6] 公共 anchor-pro.html")
    check("公开页存在", PUBLIC_HTML_PATH.exists())
    check("示例数据存在", PUBLIC_DATA_PATH.exists())
    if PUBLIC_HTML_PATH.exists() and PUBLIC_DATA_PATH.exists():
        public_data = json.loads(PUBLIC_DATA_PATH.read_text(encoding='utf-8'))
        try:
            public_html, public_embed = read_html_embed(PUBLIC_HTML_PATH)
        except (ValueError, json.JSONDecodeError) as exc:
            public_html, public_embed = "", {}
            check("公开页 var D 数据块解析", False, str(exc))
        public_script_ok, public_script_detail = check_inline_script_syntax(PUBLIC_HTML_PATH)
        check("公开页内嵌脚本语法正确", public_script_ok, public_script_detail)
        private_tokens, contains = private_tokens_guard()
        check("公开页无私有标记", not any(contains(public_html, token) for token in private_tokens), "检测到私有持仓或基准标记")
        check("公开页现金名称脱敏", '余额宝' not in public_html, "现金名称仍暴露为余额宝")
        check("公开页使用示例资产", public_embed.get('total_assets', -1) == public_data.get('total_assets', -2),
              f"(page={public_embed.get('total_assets')} vs example={public_data.get('total_assets')})")
        check("公开页示例标签可见", public_embed.get('hero', [{}])[0].get('l') == '示例总资产 ¥',
              f"(label={public_embed.get('hero', [{}])[0].get('l')})")
        check("公开页含动态持仓合同", '"holding_counts"' in public_html and '"layers"' in public_html)
        check("公开页数据含动态层级标签", '"active_label"' in public_html)  # v4.3.1：持仓地图移除，数据键保留
        check("公开页金字塔消费动态层级", 'D.layers' in public_html and 'pyramidViz' in public_html)  # v4.3.1：改查金字塔渲染
        check("公开页禁令字段完整", '"act"' in public_html and '"cost"' in public_html)
        check("公开页禁令渲染字段", 'f.act' in public_html and 'f.cost' in public_html)
        check("公开页不写死持仓数量", '10只基金 + 1只股票 + 余额宝' not in public_html and '10只活跃持仓' not in public_html)
        check("公开页不写死层级市值", '18626' not in public_html and '5875' not in public_html and '5428' not in public_html)
        check("公开页无实盘历史文案", not any(contains_token(public_html, token) for token in ['109笔实盘交易', '109笔交易', '28只清仓基金', '13个月数据', '¥2,343', '实盘持仓']))
        # v3.9.0 Command Center 高冲击结构
        check("公开页含 Hero 粒子画布", '<canvas id="heroCanvas">' in public_html)
        check("公开页含打字机标题", 'class="typing"' in public_html and 't-seg' in public_html)
        check("公开页含 count-up 数字", 'count-up' in public_html and 'data-count' in public_html)
        check("公开页含 3D tilt", 'pointer: fine' in public_html and 'rotateX' in public_html)
        check("公开页含滚动进度条", 'id="scrollBar"' in public_html)
        check("公开页含光晕跟随", 'id="heroGlow"' in public_html)
        check("公开页含全页交互背景粒子场", 'id="bgCanvas"' in public_html and 'bgCanvas' in public_html and 'mx>-9000' in public_html)
        check("公开页含由浅入深 reveal 门控", '.js .reveal' in public_html and '.js .stagger>*' in public_html)
        check("公开页体系图简洁化（闭环总览 + 无 iframe 图）", 'system-loop' in public_html and 'loop-step' in public_html and 'iframe src="diagrams/' not in public_html and 'diagram-links' in public_html)
        check("公开页 copy 含打字机文案", '"hero_typed"' in public_html and '"hero_sub"' in public_html)
        # v4.0.1 进化叙事章节（v3.10.0 横向 pin 已由「简洁骨架+讲述」章节重构替代）
        check("公开页进化叙事章节（简洁骨架+讲述）", 'evo-chapter' in public_html and 'data-version' in public_html and 'evo-next' in public_html and 'evo-line' in public_html)
        # v4.0.0 GSAP 深度重构
        check("公开页 GSAP CDN 在 head 且内联脚本在后", 'gsap@3.13.0/dist/gsap.min.js' in public_html and public_html.index('gsap@3.13.0') < public_html.index('<script>'))
        check("公开页 ScrollSmoother 结构", 'id="smooth-wrapper"' in public_html and 'id="smooth-content"' in public_html)
        check("公开页 GSAP 插件齐全", all(k in public_html for k in ['ScrollSmoother','ScrollTrigger','SplitText','ScrambleTextPlugin','ScrollToPlugin']))
        check("公开页注册与门控", 'gsap.registerPlugin(' in public_html and 'gsap.matchMedia(' in public_html)
        check("公开页关键 GSAP API", 'gsap.quickTo(' in public_html and 'ScrollTrigger.batch(' in public_html and 'SplitText.create(' in public_html and 'scrambleText:' in public_html)
        check("公开页 gsap/no-gsap 降级", '.js.gsap' in public_html and ' no-gsap' in public_html)

    print("\n[6b] GitHub Pages 示例首页")
    check("示例首页存在", EXAMPLE_HTML_PATH.exists())
    if EXAMPLE_HTML_PATH.exists() and PUBLIC_DATA_PATH.exists():
        try:
            example_html, example_embed = read_html_embed(EXAMPLE_HTML_PATH)
        except (ValueError, json.JSONDecodeError) as exc:
            example_html, example_embed = "", {}
            check("示例首页 var D 数据块解析", False, str(exc))
        example_script_ok, example_script_detail = check_inline_script_syntax(EXAMPLE_HTML_PATH)
        check("示例首页内嵌脚本语法正确", example_script_ok, example_script_detail)
        check("示例首页使用示例资产", example_embed.get('total_assets', -1) == public_data.get('total_assets', -2))
        check("示例首页含动态合同", '"holding_counts"' in example_html and '"layers"' in example_html)
        check("示例首页含新视觉结构", 'ANCHOR COMMAND CENTER' in example_html and 'Portfolio map' in example_html and 'Sample performance' in example_html)
        check("示例首页无私有标记", not any(contains(example_html, token) for token in private_tokens), "检测到私有持仓或基准标记")

    # 7. 运行核心测试
    print("\n[7] 核心计算测试 test_calculations.py")
    r2 = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_calculations.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    check("核心测试通过", "ALL TESTS PASSED" in r2.stdout, f"(rc={r2.returncode})")

    # 7-c2a. 决策日志统计测试（C2：盈亏比/追高分母/backfilled 过滤/止损执行率）
    #   🔴 145 A7：**两路并取**（unittest 把 OK 写 stderr，本套件自定义 runner 把
    #      「ALL TESTS PASSED」写 stdout —— 两处都读过才不会再犯「套件绿而门禁红」）。
    print("\n[7-c2a] 决策日志测试 test_decision_log.py")
    r_dl = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_decision_log.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    _dl_out = (r_dl.stdout or "") + (r_dl.stderr or "")
    check("决策日志统计测试通过", "ALL TESTS PASSED" in _dl_out, f"(rc={r_dl.returncode}) {_dl_out[-200:]}")

    # 7-c2. 交易前校验测试（C2/C5：契约阈值/fallback/月操作口径）
    print("\n[7-c2b] 交易前校验测试 test_pre_trade_check.py")
    r_pt = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_pre_trade_check.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    check("交易前校验测试通过", "ALL TESTS PASSED" in r_pt.stdout, f"(rc={r_pt.returncode}) {r_pt.stderr[-200:]}")

    # 7-c2c. 取数层回归测试（#137/#138：注册表覆盖度 / 双向断言 / 收盘判定 / 健康矩阵约束）
    #         不发网络请求，秒级；含负向测试（删债券条目必须被 --coverage 拦下并指名）
    print("\n[7-c2c] 取数层回归测试 test_fetch_registry.py")
    r_fr = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_fetch_registry.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=120
    )
    check("取数层回归测试通过", "全部通过" in r_fr.stdout, f"(rc={r_fr.returncode}) {r_fr.stderr[-200:]}")

    # 7-c2d. 规则门禁回归测试（A2 追红日禁买 / watchlist 右侧确认 / 月额度二维口径）
    #   v4.5.0 建 test_rule_gates.py；v4.5.1 接入本处（§124 登记项 ③）。
    #   此前该测试**只能靠人记得手跑** —— 而「靠人记得」正是这一连串缺陷的成因本身。
    #   🔴 v4.5.20（inbox/144 验收④）：该套件含**全仓唯一**直连行情活源的断言（§I-b），
    #      活源限流时它不是回归而是「没测到」—— 本步必须**三态**分类：
    #      红(rc≠0/失败项) → [FAIL]；绿但含「无法判定 N」→ [SKIPPED]（⛔ 不计 PASS）；纯绿 → [PASS]。
    print("\n[7-c2d] 规则门禁回归测试 test_rule_gates.py")
    r_rg = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_rule_gates.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=180
    )
    _rg_out = (r_rg.stdout or "") + (r_rg.stderr or "")
    _rg_m = re.search(r"无法判定\D*(\d+)", _rg_out)   # 汇总行恒含「无法判定 N」（N=0 时为 0）
    _rg_last = _rg_out.strip().splitlines()[-1] if _rg_out.strip() else r_rg.stderr[-200:]
    if r_rg.returncode != 0:
        check("规则门禁回归测试通过", False, f"(rc={r_rg.returncode}) {_rg_last}")
    elif _rg_m is None:
        check("规则门禁回归测试通过", False,
              f"输出缺三态汇总行（无法判定计数）⇒ 未知态，⛔ 不得按通过处理。(rc=0) {_rg_last}")
    elif int(_rg_m.group(1)) > 0:
        skip(f"规则门禁回归测试（{int(_rg_m.group(1))} 项无法判定：直连活源不可达）",
             "见 test_rule_gates 输出『无法判定项』清单 —— ⛔ 不等于通过，本次未覆盖该节")
    else:
        check("规则门禁回归测试通过", "全绿" in _rg_out and r_rg.returncode == 0,
              f"(rc={r_rg.returncode}) {_rg_last}")

    # 7-c2e. 公开页隐私护栏回归测试（v4.5.4）
    #   缘起：total_hold_pnl_est 转派生后取值 1366.36，整数形态 `1366` 撞上 anchor-pro.html
    #   注释里的 `≥1366px` ⇒ sync_all 步骤 4 以「包含私有标记」**误报失败**。
    #   🔴 接入理由同 7-c2d：护栏的豁免面**只能靠测试钉住** —— 它既要拦真泄漏、
    #   又要放行 CSS 字面量，且这次**误报的表现形式与真泄漏完全一样**（都报「包含私有标记」），
    #   人眼无法区分 ⇒ 必须由测试而非人来判。
    print("\n[7-c2e] 公开页隐私护栏测试 test_anchor_pro_privacy.py")
    r_ap = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_anchor_pro_privacy.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    # ⚠️ unittest.TextTestRunner 默认把进度与 `OK` 写 **stderr** 而非 stdout
    #    （其余 7-c2x 套件自带自定义 runner 才打在 stdout）⇒ 判据必须两路并取，
    #    否则**套件全绿而本 check 报红**，造成「测试通过了但门禁说没过」的新假象。
    _ap_out = (r_ap.stdout or "") + (r_ap.stderr or "")
    check("公开页隐私护栏测试通过", "OK" in _ap_out and r_ap.returncode == 0,
          f"(rc={r_ap.returncode}) {_ap_out[-200:]}")

    # 7-c2f. DDX 取数回归测试（v4.5.6）
    #   缘起：DDX 被登记为「结构性无源」并据此删掉 B2' 的 DDX 条件，实为
    #   **端点选错**（`stock/get` 不供 f88 族）⇒ 与 v4.5.5 的 `100.NDX` 案同型。
    #   🔴 接入理由：这条致错路径**从外部看不见** —— 取不到 DDX 与「该标的没有 DDX」
    #   返回值完全一样（都长成「没有读数」），人眼无从分辨 ⇒ 只能靠测试钉住。
    print("\n[7-c2f] DDX 取数测试 test_fetch_public_ddx.py")
    r_ddx = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_fetch_public_ddx.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    # ⚠️ 同 7-c2e：unittest 把 `OK` 写 stderr ⇒ 两路并取，否则套件全绿而门禁报红
    _ddx_out = (r_ddx.stdout or "") + (r_ddx.stderr or "")
    check("DDX 取数测试通过", "OK" in _ddx_out and r_ddx.returncode == 0,
          f"(rc={r_ddx.returncode}) {_ddx_out[-200:]}")

    # 7-c2g. 交易日历测试（v4.5.10 · 登记表 §六 #C1-8）
    #   缘起：T+3 原口径「自然日 +3」跨周末时**只覆盖 1 个交易日**（周五记录 → 周一到期），
    #   使「准确率」混装 1 日与 3 日两种评价期（64 条中 14 条周五创建 ＝ 21.9%）。
    #   用户 2026-09-21 裁决：改用**交易日** ⇒ 交易日历是其前置条件。
    #   🔴 接入理由：本模块治的正是「**静默近似**」—— 若退回「按星期几猜」，
    #   2026-09-25（周五·中秋）会被当成交易日，而**近似版不报错、只是答案是错的**。
    #   故测试里 4 组反向断言钉住「不用本日历确实会出错」，防它退化成装饰。
    print("\n[7-c2g] 交易日历测试 test_trading_calendar.py")
    r_tc = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_trading_calendar.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    # ⚠️ 同 7-c2e/7-c2f：unittest 把 `OK` 写 stderr ⇒ 两路并取
    _tc_out = (r_tc.stdout or "") + (r_tc.stderr or "")
    check("交易日历测试通过", "OK" in _tc_out and r_tc.returncode == 0,
          f"(rc={r_tc.returncode}) {_tc_out[-200:]}")

    # 7-c2h. 板块双宇宙 + 主力资金回归测试（v4.5.10 · 登记表 §六 #C1-7 / G-3）
    #   缘起：「概念板块主力资金」被当作长期缺口写进多份报告的缺口声明表，
    #   实为 `board_movers_all()` **取了 f62 却在最后一跳丢掉**（v4.5.1 起的既存缺陷）。
    #   🔴 接入理由：这类「取了没人接」**从产物上看与「无源」完全一样** ——
    #   报告里两种成因都长成「无读数」，人眼无从分辨 ⇒ 只能靠测试钉住。
    #   ⚠️ 同时钉住「t:2 与 t:3 互不覆盖、同名不同物」，防日后有人为省事把两宇宙并成一个。
    print("\n[7-c2h] 板块双宇宙/主力资金测试 test_board_universe.py")
    r_bu = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_board_universe.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    _bu_out = (r_bu.stdout or "") + (r_bu.stderr or "")
    check("板块双宇宙测试通过", "OK" in _bu_out and r_bu.returncode == 0,
          f"(rc={r_bu.returncode}) {_bu_out[-200:]}")

    # 7-c2i. 南向资金合计可信性回归测试（v4.5.11）
    #   缘起：`southbound()` **自己把 002+004 相加**，而护栏只拦「两腿全挂」⇒
    #   单腿挂时 `set.intersection(*dates)` **对单个集合恒成功**，函数照旧返回 `ok=True`，
    #   `total` 只剩一条腿（实测 9/18 深腿若挂：报 0.17 亿，真值 11.93 亿，**偏低 98.6%**）。
    #   🔴 接入理由：该数字**直接喂报告**，且失败长相与正常完全一样（量级仍合理、无报错）。
    #   现已改为**直取官方合计行 `006`**（四项指标与 002+004 逐位相等，6 日 30/30 实测）。
    #   ⚠️ 同时钉住「无合计行时降级必须显式标注依据」与「合计行与分腿不符须报错」，防静默降级。
    print("\n[7-c2i] 南向资金合计测试 test_southbound.py")
    r_sb = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_southbound.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    # ⚠️ 同 7-c2e/7-c2f/7-c2g/7-c2h：unittest 把 `OK` 写 stderr ⇒ 两路并取
    _sb_out = (r_sb.stdout or "") + (r_sb.stderr or "")
    check("南向资金合计测试通过", "OK" in _sb_out and r_sb.returncode == 0,
          f"(rc={r_sb.returncode}) {_sb_out[-200:]}")

    # 7-c2j. 中国10Y 换源回归测试（v4.5.12）
    #   缘起：`cn10y()` 的 docstring 断言「**东财公开 API 不提供任何国债收益率**」并据此
    #   **预期返回 None**、每份报告照走替代口径 —— **该断言已被实测证伪**。
    #   真病根：旧写法只在 `push2/api/qt/stock/get` 试了 4 个码就断言「东财不提供」，
    #   而收益率在**另一套服务** `datacenter-web` 的 `RPTA_WEB_TREASURYYIELD` 里
    #   （实测 9/18 = 1.682）⇒ **试的是 A 服务，结论下在 B 服务**（病十四的服务级版本）。
    #   🔴 接入理由：这是「结构性无源」四字被证伪的**第二个**案例（首个＝DDX），
    #   且失败长相同样是「返回里就是没那个值」——**不报错**。同时钉住 `date`（数据日期）
    #   与 `ts`（取数时刻）必须分开暴露，防换源成功后把取数时刻误当数据时点。
    print("\n[7-c2j] 中国10Y 换源测试 test_cn10y.py")
    r_cn = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_cn10y.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    _cn_out = (r_cn.stdout or "") + (r_cn.stderr or "")
    check("中国10Y 换源测试通过", "OK" in _cn_out and r_cn.returncode == 0,
          f"(rc={r_cn.returncode}) {_cn_out[-200:]}")

    # 7-c2k. 南向 T+0 换源回归测试（v4.5.13）
    #   缘起：`#C1-7`「换源」在 G-2（南向仅 T-1）上的落地。源＝`push2delay kamt/get`，
    #   **T+0 当日实时**（实测 9/21 净买入 41.5 亿元、`netBuyAmt = buyAmt − sellAmt` 逐位相等）。
    #   🔴 真正的接入理由是**防住同一响应里那个恒定假值**：`dayNetAmtIn` 名字叫「当日净流入额」，
    #   实测却是**额度字段**（`≡420 亿`；`monthNetAmtIn`＝15×、`yearNetAmtIn`＝171×，
    #   与当月/当年已过交易日数**逐位吻合**）⇒ **按名字取数会往每份报告注入同一个 420 亿，
    #   不报错、量级正常**。另钉住「字段集依赖」（窄 `fields` 下**根本没有 `netBuyAmt`**，
    #   与 v4.5.6「`stock/get` 不供 `f88` 族」同形）与「内部一致性不符即不采纳」。
    print("\n[7-c2k] 南向 T+0 换源测试 test_southbound_intraday.py")
    r_si = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_southbound_intraday.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    _si_out = (r_si.stdout or "") + (r_si.stderr or "")
    check("南向 T+0 换源测试通过", "OK" in _si_out and r_si.returncode == 0,
          f"(rc={r_si.returncode}) {_si_out[-200:]}")

    # 7-c2l. A2 判据 mx 口径回落测试（裁决 #C1-20 · 2026-09-23）
    #   缘起：东财 push2 全族 IP 限流 ⇒ `days`（push2 全量）当日档会缺，此前只能落回
    #   「判不了」。裁决允许第三级回落读 mx 口径，但两口径不同指标族 ⇒ 必须①独立命名
    #   空间（⛔ 不混进 days）②逐日标源 ③**容忍带**（符号/阈值临界带内一律 fail-closed）。
    #   🔴 接入理由：这里新开的是一条**能影响 `X` 执行级禁买判定**的数据通路 ——
    #   命名空间混排或容忍带丢失都会**静默放宽**，而失败长相与正常完全一样。
    #   本测试含两条反向断言（「拿掉回落 ⇒ 回到判不了」「拿掉 _mx 标记 ⇒ 带消失」）。
    print("\n[7-c2l] A2 mx 口径回落测试 test_a2_mx_fallback.py")
    r_mx = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_a2_mx_fallback.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    _mx_out = (r_mx.stdout or "") + (r_mx.stderr or "")
    check("A2 mx 口径回落测试通过", "OK" in _mx_out and r_mx.returncode == 0,
          f"(rc={r_mx.returncode}) {_mx_out[-200:]}")

    # 7-c2m. 周报生成器命名/落盘目录回归（2026-09-25 · 单 33）
    #   🔴 接入理由：`gen_weekly_report.py` 原有**三处缺陷**且全部**静默**——
    #   ① 文件名基准日错（无论 `--week` 传什么都用「今天」⇒ 三周互相覆盖成 W4）；
    #   ② 落盘到 `04-reviews/` 根而非约定的 `weekly/`；
    #   ③ 周数公式用「周一在几月」分段 ⇒ **跨月周冲突**（8/31 周与 9/7 周都算 W1）。
    #   三者都**不报错**，只会让周报**悄悄写错地方/被覆盖**。
    #   本测试含**反向断言**（不同周产出同名 ⇒ 判红）与**契约测试**（ISO 惯例须逐一复现既有文件名）。
    print("\n[7-c2m] 周报命名与落盘目录回归 test_gen_weekly_report_naming.py")
    r_wk = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_gen_weekly_report_naming.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    _wk_out = (r_wk.stdout or "") + (r_wk.stderr or "")
    check("周报命名/目录回归测试通过", "OK" in _wk_out and r_wk.returncode == 0,
          f"(rc={r_wk.returncode}) {_wk_out[-200:]}")

    # 7-c2n. F7 例外出口披露回归（2026-09-25 · 单 151 · 裁决 #C1-21 方案 A-2）
    #   🔴 接入理由：F7 规定「**状态信号**（如**额度用尽**）须自带**可核验出口**，否则不得单独作最终
    #   拦截」。出口早存于 §2.4，但 §1.3 未引用、**工具未打印** ⇒ 命中 F7 违反形态（**每日复现**）。
    #   本项**只披露、不放行**（判定仍 ⛔）—— 而「只披露不拦截」的东西**最容易被顺手删掉**，
    #   故测试含**两条反向断言**（未满额不得打印；**删掉打印行 ⇒ 出口文案消失 ⇒ 证明承重**）。
    print("\n[7-c2n] F7 例外出口披露回归 test_pre_trade_f7_exit.py")
    r_f7 = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_pre_trade_f7_exit.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=120
    )
    _f7_out = (r_f7.stdout or "") + (r_f7.stderr or "")
    check("F7 例外出口披露回归通过", "OK" in _f7_out and r_f7.returncode == 0,
          f"(rc={r_f7.returncode}) {_f7_out[-200:]}")

    # 7-c2o. 月额度超限自动打标 + 月归因披露回归（2026-09-25 · 单 152 · 裁决 #C1-21 方案 A-3）
    #   🔴 接入理由：12 个月买入维**超限 11 个月**、9 月买入 5 笔，而违规留痕 **0 笔** ——
    #   病灶不是「上限太小」，是「**超了也没事**」（命中报告标准 v2.1 判例）。
    #   本项**只打标不拦截**（拦截仍在 pre_trade_check）—— 而「只留痕不拦截」的东西
    #   **最容易被顺手删掉**，故测试含**两条反向断言**（未满额/非买入不得打标；
    #   **删掉打标行 ⇒ tag 消失 ⇒ 证明承重**）＋**不溯及既往**双保险（生效日前＋补录）
    #   ＋只读扫描真实 decision_log 防追溯污染（A-3 红线）。
    print("\n[7-c2o] 月额度超限自动打标回归 test_monthly_quota_tag.py")
    r_qt = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_monthly_quota_tag.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=120
    )
    _qt_out = (r_qt.stdout or "") + (r_qt.stderr or "")
    check("月额度超限自动打标回归通过", "OK" in _qt_out and r_qt.returncode == 0,
          f"(rc={r_qt.returncode}) {_qt_out[-200:]}")

    # 7b. 本地全量编译检查（8/17 审计：CI compileall 只覆盖 git 跟踪脚本，
    #      gitignored 私有脚本需本地兜底——曾因 gen_excel_skill.py 语法错误漏网）
    print("\n[7b] 本地脚本全量编译 compileall（含 gitignored 私有脚本）")
    r3 = subprocess.run(
        f'"{PY}" -m compileall -q "{SCRIPTS}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    check("全部脚本编译通过", r3.returncode == 0, "(含 gitignored 私有脚本；修复后需重跑 smoke)")

    print("\n" + "=" * 60)
    # 🔴 144 验收④/⑤：SKIP **与 PASS 分列**（⛔ 不得把「无法判定」并进「通过」静默消化）。
    print(f"结果: {PASS} 通过 / {FAIL} 失败" + (f" / {SKIP} 跳过（无法判定：⛔ 不等于通过）" if SKIP else ""))
    if FAIL == 0:
        if SKIP:
            print(f"SMOKE TEST PASSED WITH SKIPS — 产物完整；但含 {SKIP} 项 SKIPPED（本次未测到，覆盖未达成，⛔ 不等于通过）")
        else:
            print("SMOKE TEST PASSED — 产物完整，数据一致")
    else:
        print(f"SMOKE TEST FAILED — {FAIL} 项异常，请检查")
        sys.exit(1)
    print("=" * 60)


if __name__ == '__main__':
    main()
