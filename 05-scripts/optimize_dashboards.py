#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""optimize_dashboards.py — Anchor 可视化页面统一优化（2026-08-26）
1. 版本号统一 v4.2.0（精确位置，不动规则引用）
2. 注入 meta description + favicon（data-URI ⚓）
3. decision_dashboard：判定符号（✓/△/✗）+ 响应式 + 页脚版本
"""
import io
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FAVICON = ("<link rel=\"icon\" href=\"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
           "<text y='.9em' font-size='90'>⚓</text></svg>\">")

JOBS = [
    # (path, version_subs, meta_desc)
    (r"C:\Users\lenovo\Desktop\Anchor\06-dashboard\portfolio_analysis.html",
     [("<title>Anchor v3.5 · 私有投资驾驶舱</title>", "<title>Anchor v4.2.0 · 私有投资驾驶舱</title>"),
      ('<span class="badge">v3.5 PRIVATE</span>', '<span class="badge">v4.2.0 PRIVATE</span>'),
      ("Anchor v3.7 · 四层占比由统一数据合同生成", "Anchor v4.2.0 · 四层占比由统一数据合同生成")],
     "Anchor 私有投资驾驶舱 · 四层金字塔实时看板（真实数据仅存本地）"),
    (r"C:\Users\lenovo\Desktop\Anchor\06-dashboard\daily_hub.html",
     [('<span class="badge">v4.1</span>', '<span class="badge">v4.2.0</span>'),
      ("Anchor v4.1.0 · 当日指挥中心", "Anchor v4.2.0 · 当日指挥中心")],
     "Anchor 当日指挥中心 · 聚合全部入口一页直达（KPI/四层/信号/仪表盘/事件/报告/工具）"),
    (r"C:\Users\lenovo\Desktop\Anchor\06-dashboard\decision_dashboard.html",
     [('<span style="color:#36d39c;font-family:Cascadia Mono,monospace">● 正确</span>',
       '<span style="color:#36d39c;font-family:Cascadia Mono,monospace">✓ 正确</span>'),
      ('<span style="color:#91a4bd;font-family:Cascadia Mono,monospace">● 中性</span>',
       '<span style="color:#91a4bd;font-family:Cascadia Mono,monospace">△ 中性</span>'),
      ('<span style="color:#e66767;font-family:Cascadia Mono,monospace">● 错误</span>',
       '<span style="color:#e66767;font-family:Cascadia Mono,monospace">✗ 错误</span>'),
      ('<p class="foot">决策日志 v3.4 · T+3 到期日 = 记录日 + 3 自然日 · 盈亏比目标 ≥1.5:1 · 数据生成时间见文件生成时刻</p>',
       '<p class="foot">决策日志 v3.4 · T+3 到期日 = 记录日 + 3 自然日 · 盈亏比目标 ≥1.5:1 · Anchor v4.2.0 · 数据生成时间见文件生成时刻</p>')],
     "Anchor 决策日志胜率仪表盘 · T+3 复盘闭环 · 准确率/盈亏比/追高占比"),
    (r"C:\Users\lenovo\Desktop\Anchor\08-website\anchor-pro.html",
     [("<title>⚓ Anchor · 投资纪律操作系统 v4.0.2</title>", "<title>⚓ Anchor · 投资纪律操作系统 v4.2.0</title>"),
      ('<span class="version">v4.0.0</span>', '<span class="version">v4.2.0</span>'),
      ("⚓ Anchor Investment System v4.0.2 · 公开页面仅使用脱敏示例数据",
       "⚓ Anchor Investment System v4.2.0 · 公开页面仅使用脱敏示例数据")],
     None),  # anchor-pro 元信息已齐全
]

# decision_dashboard 响应式补丁（插入 </style> 前）
RESPONSIVE_PATCH = """
/* v4.2.0 响应式增强 */
@media (max-width:760px){
  .table-wrap{overflow-x:auto}
  table{min-width:640px}
  .kpis{grid-template-columns:repeat(2,1fr)}
  body{padding:14px}
}
"""


def inject_head(html, meta_desc):
    """对内存中的 html 字符串注入 meta + favicon（不再重新读文件，避免覆盖替换结果）"""
    head_parts = []
    if meta_desc:
        head_parts.append(f'<meta name="description" content="{meta_desc}">')
    head_parts.append(FAVICON)
    inject = "\n".join(head_parts) + "\n"
    return html.replace("</title>", "</title>\n" + inject, 1)


def main():
    for path, subs, meta in JOBS:
        with io.open(path, encoding="utf-8") as f:
            html = f.read()
        for old, new in subs:
            n = html.count(old)
            html = html.replace(old, new)
            print(f"{path.split(chr(92))[-1]}: 替换 {n} 处 | {old[:40]}...")
        html = inject_head(html, meta)
        if "decision_dashboard" in path:
            if "</style>" in html:
                html = html.replace("</style>", RESPONSIVE_PATCH + "\n</style>", 1)
                print("decision_dashboard: 响应式补丁已注入")
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ 完成: {path.split(chr(92))[-1]}\n")


if __name__ == "__main__":
    main()
