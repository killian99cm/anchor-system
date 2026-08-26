# DESIGN.md — Anchor 设计系统规范 v4.3.0

> 生成：2026-08-26 · 设计师：Diana（DesignMdArchitect） · 参考品牌：Linear（排版/信息架构） + Stripe（色彩层次/品质光效） + Tesla（未来科技感）
> 适用范围：anchor-pro.html（公开页）、portfolio_analysis.html（主看板）、daily_hub.html（指挥中心）、decision_dashboard.html（决策仪表盘）、diagrams/*.html（图集）、09-backtest/output/index.html（回测仪表盘）
> 数据合同：私有页面由 rebuild.py/gen_intraday_signal.py 等生成，本规范仅定义视觉层 tokens 与组件样式，不改变任何数据字段

---

## 1. Visual Theme & Atmosphere（视觉主题与氛围）

- **设计哲学**：「纪律可见化」——把投资纪律的严肃性转化为一种冷静、精密、有光感的数字仪表美学
- **视觉基调**：深空科技风（Deep-Space Technical）——深色底 + 玻璃拟态 + 渐变光带
- **核心特征关键词**（5 个）：`冷静` `精密` `光感` `层次` `纪律`
- **光影质感**：毛玻璃（backdrop-filter 12-32px）+ 上缘内高光 + 渐变描边 + 低频氛围光晕（5 团径向光）
- **叙事逻辑**：信息按「结论 → 依据 → 数据」三层递进；每屏一个焦点；滚动驱动镜头推进

---

## 2. Color Palette & Roles（调色板与角色）

### 基础色板（保持 Anchor 基因，微调增强）

| 角色 | HEX | CSS 变量 | 场景 |
|------|-----|---------|------|
| 背景基底 | `#02070f` | `--bg` | 页面底色（接近纯黑的海军蓝） |
| 表面 1 | `#071120` | `--surface` | 默认卡片/面板 |
| 表面 2 | `#0b1729` | `--surface-2` | 次级卡片/悬浮面板 |
| 表面 3 | `#0f1e34` | `--surface-3` | 强调卡片/输入框 |
| 分隔线 | `#18304d` | `--line` | 边框/分隔 |
| 主文字 | `#edf4ff` | `--text` | 标题/正文 |
| 次要文字 | `#91a4bd` | `--muted` | 说明/注释 |
| 弱化文字 | `#536a85` | `--dim` | 页脚/水印 |

### 品牌与语义色

| 角色 | HEX | CSS 变量 | 场景 |
|------|-----|---------|------|
| 主蓝 | `#3987e5` | `--blue` | 主操作/强调/链接（Stripe 式可信蓝） |
| 蓝软底 | `rgba(57,135,229,.14)` | `--blue-soft` | 蓝色标签/选中底 |
| 成功绿 | `#36d39c` | `--green` | 盈利/安全/达标（A股惯例：涨） |
| 警示琥珀 | `#fab219` | `--amber` | 警告/观察/待定 |
| 危险红 | `#e66767` | `--red` | 亏损/止损/禁止（A股惯例：跌） |
| 科技紫 | `#9085e9` | `--purple` | 现金层/特殊标记 |
| 青蓝 | `#55c9d6` | `--cyan` | 数据流/连接线/次级强调 |

### 玻璃与光效 tokens（v4.3.0 新增）

```css
:root{
  --glass-1:rgba(13,26,46,.60);  /* L1 高透玻璃：命令卡 */
  --glass-2:rgba(10,20,36,.74);  /* L2 中透玻璃：数据卡 */
  --glass-3:rgba(7,17,32,.88);   /* L3 低透玻璃：悬浮面板 */
  --blur-s:blur(12px); --blur-m:blur(20px); --blur-l:blur(32px);
  --edge:0 0 0 1px rgba(57,135,229,.20);        /* 光效环边框 */
  --hi:inset 0 1px 0 rgba(255,255,255,.06);      /* 上缘内高光 */
  --grad-edge:linear-gradient(120deg,rgba(57,135,229,.55),rgba(85,201,214,.30),transparent);
  --glow-blue:0 0 70px rgba(57,135,229,.08);     /* 蓝色氛围光 */
  --glow-hover:0 18px 44px rgba(0,0,0,.30),0 0 28px -6px rgba(57,135,229,.38);
}
```

### 阴影色

| 层 | box-shadow |
|----|-----------|
| shadow-xs（卡片默认） | `0 2px 8px rgba(0,0,0,.22)` |
| shadow-sm（悬浮） | `0 8px 24px rgba(0,0,0,.28)` |
| shadow-md（浮层） | `0 18px 55px rgba(0,0,0,.25)` |
| shadow-lg（模态/高亮） | `0 24px 80px rgba(0,0,0,.35)` |
| glow（品牌光晕） | `0 0 70px rgba(57,135,229,.08)` |

---

## 3. Typography Rules（排版规则）

- **字体栈**：`--font: "Inter","SF Pro Text","Segoe UI","PingFang SC","Microsoft YaHei",sans-serif`（UI）；`--mono: "JetBrains Mono","Cascadia Code",Consolas,monospace`（数据）
- **中文渲染**：数字与代码一律用 mono；正文用 UI 栈；标题字重 800-920（数字优先）

### Type Scale（完整层级）

| 层级 | Size | Weight | Line-Height | Letter-Spacing | 用途 |
|------|------|--------|-------------|----------------|------|
| Display Hero | `clamp(2.6rem,6vw,4.2rem)` | 920 | 1.02 | `-0.03em` | 公开页 Hero 主标 |
| H1 页面大标 | `clamp(1.7rem,3.4vw,2.4rem)` | 850 | 1.12 | `-0.02em` | 页面主标题 |
| H2 章节标题 | `clamp(1.25rem,2.2vw,1.6rem)` | 800 | 1.2 | `-0.015em` | 章节标题 |
| H3 区块标题 | `1.06rem` | 750 | 1.3 | `-0.01em` | 卡片组标题 |
| Body 正文 | `0.92rem` | 400 | 1.65 | `0` | 段落说明 |
| Kicker 眉题 | `0.6875rem` | 600 | 1.3 | `0.15em` | 章节前置小标（大写） |
| Data Mono | `0.875rem` | 500 | 1.4 | `0` | KPI/表格数字 |
| Nano 注释 | `0.75rem` | 400 | 1.5 | `0` | 页脚/水印 |

**设计哲学**：标题超粗 + 紧字距制造「锚定感」；正文行高 1.65 保证长文可读；数字 mono 增强「仪表感」——层级之间用字重差而非字号差区分，保持深色下的锐利。

---

## 4. Component Stylings（组件样式）

### Buttons（4 变体）

```css
.btn-primary{background:linear-gradient(135deg,#3987e5,#2a6cc0);color:#fff;border:0;border-radius:10px;padding:.68rem 1.4rem;font-weight:650;box-shadow:0 4px 18px rgba(57,135,229,.35),var(--hi)}
.btn-primary:hover{filter:brightness(1.1);transform:translateY(-1px)}
.btn-secondary{background:rgba(57,135,229,.12);color:#bcd7f5;border:1px solid rgba(57,135,229,.35);border-radius:10px;padding:.66rem 1.3rem}
.btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--line);border-radius:10px;padding:.64rem 1.2rem}
.btn-ghost:hover{color:var(--text);border-color:var(--blue)}
.btn-danger{background:rgba(230,103,103,.14);color:#f2b8b8;border:1px solid rgba(230,103,103,.4);border-radius:10px}
```

### Cards（3 档玻璃）

```css
.card-L1{background:linear-gradient(145deg,var(--glass-1),var(--glass-3));backdrop-filter:var(--blur-m);border-radius:16px;box-shadow:var(--shadow),var(--glow-blue),var(--edge),var(--hi)}
.card-L2{background:var(--glass-2);backdrop-filter:var(--blur-s);border-radius:13px;box-shadow:var(--hi);border:1px solid rgba(255,255,255,.03)}
.card-L3{background:var(--glass-3);border-radius:10px;border:1px solid var(--line)}
```

### 其他核心组件

- **KPI 卡**：L2 玻璃 + 数字 `Data Mono` 大字号（1.5rem 起）+ 涨跌色（A股惯例红涨绿跌）+ 环比小标 muted
- **Badge/Tag**：`border-radius:6px;padding:.18rem .5rem;font-size:.72rem;font-weight:600`——蓝/绿/琥珀/红/紫五色，浅底深字
- **表格**：表头 `--dim` 小字 + 行分隔 `--line-soft` + hover 行 `--blue-soft`；首列固定；数字右对齐 mono
- **Nav 导航条**：`position:sticky;top:0;backdrop-filter:var(--blur-l);background:rgba(2,7,15,.72)` + 下缘渐变描边
- **模态**：遮罩 `rgba(2,7,15,.72)` + 内容卡 `card-L1` + 入场 `scale(.96)→1, opacity 0→1, .25s`

---

## 5. Layout Principles（布局原则）

- **间距系统**：基数 `8px`，节奏 `4/8/12/16/24/32/48/64/96`；卡片内边距 `16-20px`；区块间距 `64px`（移动端 `40px`）
- **网格**：12 列；桌面 gap 24px；KPI 区 4 列（≥1100px）→ 2 列（640-1100px）→ 1 列（<640px）
- **容器**：`max-width:1240px;padding:0 24px`（公开页）；看板 `max-width:1400px;padding:0 20px`
- **留白哲学**：结论区少留白（数据密度高）、叙事区大留白（呼吸感）；每屏焦点唯一
- **信息逻辑**：顶栏（身份+状态）→ 导航（跳转）→ KPI 总览（结论）→ 分区块（依据）→ 表格/图表（数据）→ 页脚（版本+免责）

---

## 6. Depth & Elevation（深度与层级）

```css
/* 表面层级：bg → surface → elevated → overlay */
--z-bg:0; --z-surface:1; --z-elevated:10; --z-nav:100; --z-modal:1000; --z-toast:1100;

/* backdrop 参数 */
.backdrop{backdrop-filter:var(--blur-l) saturate(1.4)}
/* 深度辅助：卡片 hover 上浮 + 蓝光 */
.card:hover{transform:translateY(-3px);box-shadow:var(--glow-hover)}
```

---

## 7. Do's and Don'ts（设计规范与禁忌）

**Do's**
1. 数字一律 mono 字体 + 右对齐（仪表感）
2. 涨跌色遵循 A 股惯例：红涨绿跌（不可反）
3. 每屏/每区块只保留一个视觉焦点（焦点唯一）
4. 玻璃层按 L1→L3 递减透明度，越浮层越实
5. 标题用字重+字距区分层级，避免字号跳变过碎
6. 导航条 sticky + 毛玻璃，保证长页可随时跳转
7. 动效遵循 `prefers-reduced-motion` 停用 + 降级路径
8. 表格数据密度优先，hover 才显示行高亮

**Don'ts**
1. 不使用刺眼纯白大面积背景（保持深色基底）
2. 不使用模糊色值描述（一切色值精确 HEX/rgba）
3. 不在深色上使用低对比文字（`--dim` 仅限注释）
4. 不堆砌 3 种以上强调色在同一卡片
5. 不为动效而动效（叙事滚动不超过 8 项/页）
6. 不破坏数据合同：视觉层不得改动 rebuild.py 的数据字段
7. 不用 emoji 代替语义图标（状态用 ✓/△/✗ + 文字）

---

## 8. Responsive Behavior（响应式行为）

| 断点 | 宽度 | 策略 |
|------|------|------|
| mobile | `<640px` | 1 列；表格横向滚动容器；KPI 折叠为堆叠；导航收汉堡 |
| tablet | `640-1100px` | 2 列；导航文字收图标 |
| desktop | `1100-1400px` | 4 列 KPI；标准布局 |
| wide | `>1400px` | 容器 1400px；图表放大 |

- **Touch Targets**：交互元素最小 `40×40px`；按钮 padding 保证点击区
- **字体缩放**：正文 `clamp(.875rem,1.6vw,.95rem)`；KPI 数字 `clamp(1.2rem,2.6vw,1.8rem)`
- **表格折叠**：`overflow-x:auto` + `-webkit-overflow-scrolling:touch`；表头 `position:sticky;top:0`
- **打印样式**：`@media print` 白底黑字，隐藏 nav/动效/背景光

---

## 9. Agent Prompt Guide（AI 代理提示指南）

**Quick Reference**（供 AI 快速套用）
> 深色科技风（bg #02070f）；玻璃拟态卡片（blur 12-32px + 上缘高光 + 渐变描边）；主蓝 #3987e5 + 语义红涨绿跌；Inter + JetBrains Mono；8px 间距节奏；标题 850-920 字重紧字距；sticky 毛玻璃导航；动效 GSAP + reduced-motion 停用；所有色值精确到 HEX。

**Component Prompts**（可直接复用）
```
1. "生成一个 KPI 卡：标题 + mono 大数字（红涨绿跌）+ 环比小标 + 玻璃 L2 样式"
2. "生成一个 Badge：蓝/绿/琥珀/红/紫五色，圆角6px，浅底深字"
3. "生成一个表格：表头 dim 小字、行分隔线、hover 蓝色底、数字右对齐 mono、横向滚动"
4. "生成 sticky 毛玻璃导航条：下缘渐变描边、当前项蓝色高亮"
5. "生成模态框：遮罩 rgba(2,7,15,.72) + L1 玻璃卡 + scale/opacity 入场"
6. "为段落加 Kicker 眉题：11px、字距 0.15em、蓝色"
```

**Iteration Guide**（AI 迭代建议）
1. 先套 tokens 再看组件——任何页面先注入 `:root` 变量层
2. 改颜色只改变量，不硬编码（保持单源）
3. 数据卡结构优先，视觉是第二层——先验证数据再美化
4. 动效必须带 `prefers-reduced-motion` 降级
5. 数字展示一律 mono，禁止 UI 字体显示长数字
6. 用 `clamp()` 做响应式字号，禁止固定 px 大字号
7. 每页检查一次"焦点唯一"原则，删掉抢焦点的装饰
8. 版本标注统一格式：`vX.Y.Z` + 数据截止日期，双处（title + footer）
9. 修改私有看板后必须同步桌面副本（portfolio_analysis.html）
10. 修改公开页后必须跑 smoke_test.py 校验数据合同

---

*本规范由 DesignMdArchitect 生成，供 WorkBuddy 与 Claude 双 AI 消费。改动规范须同步本文件与各页 tokens 覆盖层。*
