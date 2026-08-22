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
from pathlib import Path

import paths

DESKTOP = paths.DESKTOP
ANCHOR = paths.ANCHOR
SCRIPTS = paths.SCRIPTS
PY = sys.executable
PUBLIC_DATA_PATH = paths.DASHBOARD_DIR / "portfolio_data_example.json"
PUBLIC_HTML_PATH = ANCHOR / "08-website" / "anchor-pro.html"
EXAMPLE_HTML_PATH = paths.DASHBOARD_DIR / "portfolio_analysis_example.html"

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


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


def private_tokens_from_data(data, embed):
    tokens = set()
    for h in data.get('holdings_summary', []):
        name = str(h.get('name', '')).strip()
        if name:
            tokens.add(name)
        code = str(h.get('code', '')).strip()
        if code:
            tokens.add(code)
    for s in data.get('stock_holdings', []):
        name = str(s.get('name', '')).strip()
        if name:
            tokens.add(name)
        code = str(s.get('code', '')).strip()
        if code:
            tokens.add(code)
    for key in ('total_assets', 'fund_mv', 'stock_mv', 'cash_mv'):
        val = embed.get(key, data.get(key))
        if isinstance(val, (int, float)):
            tokens.add(str(int(round(val))))
    for key in ('bedrock_mv', 'core_mv', 'sat_mv', 'cash_mv'):
        val = embed.get(key)
        if isinstance(val, (int, float)):
            tokens.add(str(int(round(val))))
    hc = embed.get('holding_counts', {}) if isinstance(embed, dict) else {}
    active_label = str(hc.get('active_label', '')).strip()
    if active_label:
        tokens.add(active_label)
    for key, suffix in (('fund', '只基金'), ('stock', '只股票')):
        val = hc.get(key)
        if isinstance(val, int) and val:
            tokens.add(f'{val}{suffix}')
    return sorted(tokens, key=len, reverse=True)


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
        private_tokens = private_tokens_from_data(data, embed)
        check("公开页无私有标记", not any(contains_token(public_html, token) for token in private_tokens), "检测到私有持仓或基准标记")
        check("公开页现金名称脱敏", '余额宝' not in public_html, "现金名称仍暴露为余额宝")
        check("公开页使用示例资产", public_embed.get('total_assets', -1) == public_data.get('total_assets', -2),
              f"(page={public_embed.get('total_assets')} vs example={public_data.get('total_assets')})")
        check("公开页示例标签可见", public_embed.get('hero', [{}])[0].get('l') == '示例总资产 ¥',
              f"(label={public_embed.get('hero', [{}])[0].get('l')})")
        check("公开页含动态持仓合同", '"holding_counts"' in public_html and '"layers"' in public_html)
        check("公开页使用动态持仓标签", 'D.holding_counts' in public_html and 'active_label' in public_html)
        check("公开页遍历动态层级", 'D.layers' in public_html and 'layers.forEach' in public_html)
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
        # v3.10.0 演进时间线横向 Pin
        check("公开页演进时间线横向 pin（GSAP 招牌技法）", 'pin-shell' in public_html and 'pin-stage' in public_html and 'evo-track' in public_html and 'getBoundingClientRect().top' in public_html)
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
        check("示例首页无私有标记", not any(contains_token(example_html, token) for token in private_tokens), "检测到私有持仓或基准标记")

    # 7. 运行核心测试
    print("\n[7] 核心计算测试 test_calculations.py")
    r2 = subprocess.run(
        f'"{PY}" "{SCRIPTS / "test_calculations.py"}"',
        shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=60
    )
    check("核心测试通过", "ALL TESTS PASSED" in r2.stdout, f"(rc={r2.returncode})")

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
    print(f"结果: {PASS} 通过 / {FAIL} 失败")
    if FAIL == 0:
        print("SMOKE TEST PASSED — 产物完整，数据一致")
    else:
        print(f"SMOKE TEST FAILED — {FAIL} 项异常，请检查")
        sys.exit(1)
    print("=" * 60)


if __name__ == '__main__':
    main()
