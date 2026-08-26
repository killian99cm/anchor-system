# -*- coding: utf-8 -*-
"""
Anchor v4.3.0 设计系统统一升级脚本
按 08-website/design-system/DESIGN.md 规范，对 4 个核心可视化页面幂等注入：
  - 设计 tokens 覆盖层（玻璃/光效/排版/滚动条/打印/响应式增强）
  - 便捷性：返回顶部按钮 + 键盘快捷键
  - 逻辑性：渐变眉题工具类 + KPI 数字增强
  - 版本修复：title/badge 统一 v4.2.0
可重复执行（幂等：检查标记，已注入则跳过）。
"""
import io
import sys

sys.stdout.reconfigure(encoding="utf-8")

MARK = "v4.3.0 design-layer"  # 幂等标记

# ============ 覆盖层 CSS（注入 </style> 前） ============
CSS_LAYER = """
/* ===== v4.3.0 design-layer · Anchor 设计系统统一层（DESIGN.md） ===== */
:root{
  --font-ui:"Inter","SF Pro Text","Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  --mono:"JetBrains Mono","Cascadia Code",Consolas,monospace;
  --glass-1:rgba(13,26,46,.60);--glass-2:rgba(10,20,36,.74);--glass-3:rgba(7,17,32,.88);
  --blur-s:blur(12px);--blur-m:blur(20px);--blur-l:blur(32px);
  --edge:0 0 0 1px rgba(57,135,229,.20);
  --hi:inset 0 1px 0 rgba(255,255,255,.06);
  --grad-edge:linear-gradient(120deg,rgba(57,135,229,.55),rgba(85,201,214,.30),transparent);
  --glow-blue:0 0 70px rgba(57,135,229,.08);
  --glow-hover:0 18px 44px rgba(0,0,0,.30),0 0 28px -6px rgba(57,135,229,.38);
}
/* 顶栏毛玻璃（sticky 导航，长页随时跳转） */
.topbar,.hub-top,.nav{position:sticky!important;top:0!important;z-index:100!important;
  backdrop-filter:var(--blur-l) saturate(1.3);-webkit-backdrop-filter:var(--blur-l) saturate(1.3);
  background:rgba(2,7,15,.78)!important;border-bottom:1px solid rgba(57,135,229,.18)!important}
/* KPI 数字增强：mono + 字重 + 字距 */
.kpi b,.kpi strong,.stat b,.stat strong,.metric b,.metric strong,.num,td:not(:first-child),.amt{
  font-family:var(--mono)!important;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
/* 渐变眉题工具类（章节逻辑标号） */
.grad-kicker{display:inline-flex;align-items:center;gap:.4rem;font-size:.6875rem;font-weight:600;
  letter-spacing:.15em;text-transform:uppercase;color:var(--blue,#3987e5)}
.grad-kicker::before{content:"";width:1.4rem;height:1px;background:linear-gradient(90deg,var(--blue,#3987e5),transparent)}
/* 卡片 hover 上浮 + 蓝光（深度层级） */
.card,.panel,.kpi,.hold,.block,.grid-card{transition:transform .25s ease,box-shadow .25s ease}
.card:hover,.panel:hover,.kpi:hover,.hold:hover,.block:hover,.grid-card:hover{
  transform:translateY(-2px);box-shadow:var(--glow-hover)}
/* 滚动条美化（Windows 深色） */
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-track{background:#060d18}
::-webkit-scrollbar-thumb{background:#1b3352;border-radius:5px;border:2px solid #060d18}
::-webkit-scrollbar-thumb:hover{background:#2a6cc0}
/* 返回顶部按钮 */
#wb2top{position:fixed;right:20px;bottom:24px;width:42px;height:42px;border-radius:12px;border:1px solid rgba(57,135,229,.4);
  background:linear-gradient(135deg,var(--glass-2),var(--glass-3));backdrop-filter:var(--blur-m);
  color:#bcd7f5;font-size:1.05rem;cursor:pointer;z-index:900;opacity:0;pointer-events:none;
  transition:opacity .3s,transform .3s;box-shadow:0 8px 24px rgba(0,0,0,.35),var(--hi)}
#wb2top.show{opacity:1;pointer-events:auto}
#wb2top:hover{transform:translateY(-3px);color:#fff;box-shadow:var(--glow-hover)}
/* 打印样式 */
@media print{ .topbar,.hub-top,.nav,#wb2top{display:none!important}
  body{background:#fff!important;color:#111!important}
  .card,.panel,.kpi{box-shadow:none!important;border:1px solid #ddd!important;background:#fff!important} }
/* 深色阅读焦点：选中文本 */
::selection{background:rgba(57,135,229,.32);color:#fff}
/* 移动端触控目标增强 */
@media(max-width:640px){ .btn-primary,.btn-secondary,.btn-ghost,.btn-danger{min-height:44px;display:inline-flex;align-items:center;justify-content:center} }
"""

# ============ 返回顶部 HTML+JS（注入 </body> 前） ============
BACK2TOP = """
<!-- v4.3.0 back-to-top -->
<button id="wb2top" aria-label="返回顶部" title="返回顶部">↑</button>
<script>
(function(){var b=document.getElementById('wb2top');
if(!b||document.documentElement.scrollHeight<=window.innerHeight*1.2){return}
window.addEventListener('scroll',function(){b.classList.toggle('show',window.scrollY>420)},{passive:true});
b.addEventListener('click',function(){window.scrollTo({top:0,behavior:'smooth'})});})();
</script>
"""

# ============ 任务定义 ============
JOBS = [
    {
        "path": "06-dashboard/portfolio_analysis.html",
        "title_fix": [
            ("Anchor v3.5 · 私有投资驾驶舱", "Anchor v4.2.0 · 私有投资驾驶舱"),
            ("v3.5 PRIVATE", "v4.2.0 PRIVATE"),
            ("v3.5 PRIVATE", "v4.2.0 PRIVATE"),
        ],
        "dash_enhance": True,
    },
    {
        "path": "06-dashboard/daily_hub.html",
        "title_fix": [],
        "dash_enhance": True,
    },
    {
        "path": "06-dashboard/decision_dashboard.html",
        "title_fix": [],
        "dash_enhance": True,
    },
    {
        "path": "08-website/anchor-pro.html",
        "title_fix": [],
        "skip_back2top": False,
    },
]

# ============ 看板增强层（v4.3.1，仅 3 个私有看板页） ============
# 章节自动编号（逻辑感）+ 表格/卡片 hover 交互提示
MARK_DASH = "v4.3.1-dash-enhance"
CSS_DASH = """
/* ===== v4.3.1-dash-enhance · 看板章节逻辑编号 ===== */
body{counter-reset:sec 0}
h2{counter-increment:sec}
h2::before{content:"0" counter(sec) " · ";font-family:var(--mono);font-weight:700;
  color:var(--blue,#3987e5);letter-spacing:-.02em;margin-right:.15rem}
h2{display:flex;align-items:baseline;gap:.2rem;flex-wrap:wrap}
/* 章节分隔光带（逻辑分块） */
h2:not(:first-of-type){margin-top:1.2em}
h2::after{content:"";flex:1;height:1px;margin-left:.6rem;
  background:linear-gradient(90deg,rgba(57,135,229,.35),transparent);align-self:center}
/* 数据行 hover 聚焦 */
tr:hover td{background:rgba(57,135,229,.07)!important}
@media print{h2::before,h2::after{display:none}}
"""


def process(job):
    path = job["path"]
    html = io.open(path, encoding="utf-8").read()
    name = path.split("/")[-1]
    changed = []

    # 1) title/badge 版本修复
    for old, new in job.get("title_fix", []):
        if old in html:
            html = html.replace(old, new)
            changed.append(f"版本: {old} → {new}")

    # 2) 注入 CSS 覆盖层（幂等）
    if MARK not in html:
        if "</style>" in html:
            html = html.replace("</style>", CSS_LAYER + "\n</style>", 1)
            changed.append("CSS 覆盖层注入")
        else:
            print(f"  ⚠️ {name}: 无 </style>，跳过 CSS")

    # 3) 注入返回顶部（幂等）
    if "wb2top" not in html and "</body>" in html:
        html = html.replace("</body>", BACK2TOP + "\n</body>", 1)
        changed.append("返回顶部注入")

    # 4) 看板增强层（仅私有看板 3 页，幂等）
    if job.get("dash_enhance") and MARK_DASH not in html and "</style>" in html:
        html = html.replace("</style>", CSS_DASH + "\n</style>", 1)
        changed.append("看板章节编号层注入")

    io.open(path, "w", encoding="utf-8").write(html)
    if changed:
        print(f"✅ {name}: " + "；".join(changed))
    else:
        print(f"⏭️  {name}: 已是最新（幂等跳过）")


def main():
    for job in JOBS:
        process(job)
    print("\n全部完成")


if __name__ == "__main__":
    main()
