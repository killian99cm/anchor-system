<div align="center" id="anchor">

<a href="https://github.com/killian99cm/anchor-system" title="Anchor">
  <img src="https://img.shields.io/badge/⚓_Anchor-v3.3-4d8af0?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0id2hpdGUiIGQ9Ik0xMiAyQzYuNDggMiAyIDYuNDggMiAxMnM0LjQ4IDEwIDEwIDEwIDEwLTQuNDggMTAtMTBTMTcuNTIgMiAxMiAyem0wIDNjNC40MSAwIDggMy41OSA4IDhzLTMuNTkgOC04IDgtOC0zLjU5LTgtOCAzLjU5LTggOC04em0wIDJjLTMuMzEgMC02IDIuNjktNiA2czIuNjkgNiA2IDYgNi0yLjY5IDYtNi0yLjY5LTYtNi02em0wIDFjMi43NiAwIDUgMi4yNCA1IDVzLTIuMjQgNS01IDUtNS0yLjI0LTUtNSAyLjI0LTUgNS01em0wIDJjLTEuNjYgMC0zIDEuMzQtMyAzczEuMzQgMyAzIDMgMy0xLjM0IDMtMy0xLjM0LTMtMy0zem0wIDJjLjU1IDAgMSAuNDUgMSAxcy0uNDUgMS0xIDEtMS0uNDUtMS0xIC40NS0xIDEtMXoiLz48L3N2Zz4=" alt="Anchor v3.3" height="36">
</a>

🚀 Rules-driven personal investment management system — **Discipline over impulse, data over intuition**

[![GitHub Stars](https://img.shields.io/github/stars/killian99cm/anchor-system?style=flat-square&logo=github&color=yellow)](https://github.com/killian99cm/anchor-system/stargazers)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
[![Version](https://img.shields.io/badge/version-v3.3-blue.svg)](https://github.com/killian99cm/anchor-system)
[![Trades](https://img.shields.io/badge/live_trades-109-00d69e?style=flat-square)](https://github.com/killian99cm/anchor-system)
[![Period](https://img.shields.io/badge/validated-13_months-f0a830?style=flat-square)](https://github.com/killian99cm/anchor-system)

[![Data-mxdata](https://img.shields.io/badge/data-mx_data_API-4d8af0?style=flat-square)](https://data.eastmoney.com/)
[![Dashboard-zero-dep](https://img.shields.io/badge/dashboard-HTML_zero_deps-00d69e?style=flat-square)](https://killian99cm.github.io/anchor-system)
[![Analysis-auto](https://img.shields.io/badge/analysis-automated-f04668?style=flat-square)](https://github.com/killian99cm/anchor-system)
[![CI-GitHub Actions](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?style=flat-square&logo=github-actions)](https://github.com/killian99cm/anchor-system/actions)
[![Demo-GitHub Pages](https://img.shields.io/badge/demo-GitHub_Pages-4285F4?style=flat-square&logo=github)](https://killian99cm.github.io/anchor-system)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat-square&logo=python)](https://www.python.org/)

</div>

<div align="center">

**[English](README.md)** | **[中文](README.zh-CN.md)**

</div>

> 💡 **What this is**: A personal system that turns investment discipline into executable code. Not a stock-picking strategy, not AI auto-trading, and does not recommend specific products.

<details>
<summary>🗺️ Click to expand: <strong>Project at a Glance</strong></summary>
<br>

| Dimension | Content |
|:--|:--|
| 🎯 **Goal** | Eliminate emotional trading with rules; replace gut-feel decisions with quantitative checklists |
| 🏗️ **Architecture** | Four-layer pyramid (Bedrock 45% / Core Growth 20% / Satellite 20% / Cash Reserve 15%) |
| 📜 **Rules** | 4 iron laws + 6 permanent bans + monthly trade cap + tiered take-profit |
| 📊 **Data** | mx-data API → rebuild.py → dual-output dashboard (Desktop + repo copy) |
| 🧠 **Analysis** | Daily review, position check, weekly report, monthly attribution |
| 🔄 **Cadence** | Real-time quotes / daily updates / weekly checks / monthly attribution |

</details>

<br>

## 📑 Quick Navigation

<div align="center">

| [🧠 Philosophy](#-core-philosophy) | [📜 Rules](#-rule-engine) | [⚡ Quick Start](#-quick-start) | [📂 Structure](#-directory-structure) | [📊 Data Flow](#-data-update-cadence) |
|:---:|:---:|:---:|:---:|:---:|
| [🏗️ Architecture](#️-system-architecture) | [📈 Evolution](#-version-history) | [🧠 Analysis](#-analysis-system) | [🌐 Demo](#-live-demo) | [📝 Changelog](#-changelog) |
| [❓ FAQ](FAQ.md) | [🔧 TROUBLESHOOTING](TROUBLESHOOTING.md) | [中文](README.zh-CN.md) | [🤝 Contributing](CONTRIBUTING.md) | [📄 License](LICENSE) |

</div>

<br>

## ✨ Core Features

### 🏗️ Four-Layer Pyramid

```
       ┌──────────────────────────────────┐
 20%   │  🔥 Satellite      -8% hard stop  │   Swing trading
       │  Sector ETFs       No averaging    │   High-conviction bets
       ├──────────────────────────────────┤
 20%   │  🚀 Core Growth     DCA + dip buy  │   Long-term growth
       │  Broad indices     Accumulate low  │   Through cycles
       ├──────────────────────────────────┤
 45%   │  🛡️ Bedrock         Never sell      │   Portfolio anchor
       │  Bonds + Fixed     Quarterly rebal │   Stable yield
       ├──────────────────────────────────┤
 15%   │  💰 Cash Reserve    Crash ammo      │   Tactical reserve
       │  Money market      Stay liquid     │   Wait for opportunity
       └──────────────────────────────────┘
```

| Layer | Goal | Target | Rules | Current Holdings |
|:--|:--|:--:|:--|:--|
| 🛡️ Bedrock | Stable return, drawdown defense | **45%** | Never sell, quarterly rebalance | Bonds×2 + Gold |
| 🚀 Core Growth | Long-term appreciation | **20%** | DCA primary, buy dips | Mixed fund + Nasdaq×2 |
| 🔥 Satellite | Swing enhancement | **20%** | -8% hard stop, no averaging down | Semi + Securities + Pharma |
| 💰 Cash Reserve | Liquidity + crash reserve | **15%** | Money market, deploy on crash | Yu'e Bao |

> 💡 Check layer weights monthly; trigger rebalancing when deviation exceeds 5%

### 📜 Quantified Rule Engine

**Four Iron Laws**:

1. **No averaging down on losers** — Close only, no adding, no converting. No throwing good money after bad.
2. **-8% hard stop** — Satellite layer: cut immediately on breach, no "bounce expectation" excuses.
3. **72h cooling-off** — Every buy idea frozen for 72 hours before execution.
4. **Tiered take-profit** — +15% sell 1/3 · +30% sell 1/2 · +50% close all

> ⚠️ **Note**: The above is the stock/ETF-side formula. Fund-side (Satellite layer) follows `01-rules/投资规则手册_v3.3_正式版.md`: **+10% sell 1/3 · +20% sell another 1/3 · keep 100-unit trail**. The two sets don't conflict — apply by holding type.

**Six Permanent Bans**:

```
🚫 No converting   🚫 No averaging losers  🚫 No same-day swap
🚫 No overcapacity  🚫 No DCA on satellite   🚫 No FOMO chasing
```

**v3.3 New Filters**:

| Filter | Condition | Effect |
|:--|:--|:--|
| 🔴 DDX Filter | Semiconductor DDX positive 2 consecutive days | Only then allow adding |
| 🔴 Nasdaq Premium | Premium rate ≤ 3% | Only then allow opening |
| 🟡 Time Stop | Held 30 days | Close if loss not improving |
| 🟡 Monthly Cap | ≤ 4 trades/month | Freeze until next month if exceeded |

> 💡 Run through the [Position Checklist](01-rules/持仓全面检查清单.md) before every trade — red light means no go.

### 📊 Dual-Output Data Dashboard

`rebuild.py` one-click generation, outputs to both Desktop and repo copy:

```
portfolio_data.json (single editable data source)
        │
        ▼
   rebuild.py ◀── Auto-injected market data
        │
   ┌────┴────┐
   ▼         ▼
 Desktop/   Anchor/06-dashboard/
 Dashboard   Dashboard (repo read-only copy)
 Snapshot    Snapshot
 Excel       portfolio_data.json
```

> 💡 **Data freshness report**: rebuild output includes market data age, rule alerts, time-stop countdown

### 🧠 Analysis System

Built-in analysis assistant, natural language interaction:

- **📋 Position Check**: Say "仓位点检", auto four-layer weight check + red-light scan
- **📝 Daily Review**: Say "更新今日数据", mx-data fetches close → updates JSON → rebuild
- **📈 Weekly Report**: Say "生成周报", auto-summarizes weekly trades + returns + rule triggers
- **🔍 Monthly Attribution**: Say "月度归因", full monthly P&L decomposition + rule review + version upgrade
- **🔄 Session Continuity**: Say "继续", reads session checkpoint, restores context in seconds

### 🌐 Live Demo Dashboard

GitHub Pages auto-deploy, pure HTML dark terminal style, zero external dependencies:

> 📋 **[Live Demo →](https://killian99cm.github.io/anchor-system)** View the anonymized sample dashboard

| Dashboard Feature | Description |
|:--|:--|
| 📊 KPI Cards | Four-layer weights, rule status, version score |
| 🏗️ Pyramid Viz | Graphical four-layer ratio display |
| 🚦 Rule Check Panel | Real-time rule trigger status |
| 📈 P&L Chart | Daily PnL + benchmark overlay |
| ⚠️ Todo Tracker | DDX / premium rate / time-stop countdown |

### 🔧 Zero-Friction Setup

```bash
git clone https://github.com/killian99cm/anchor-system.git
cd anchor-system

# Option A: Interactive setup (recommended for beginners!)
python setup.py
# → Enter your holdings as prompted → auto-generates data → auto-generates dashboard ✨

# Option B: Manual setup
cp 06-dashboard/portfolio_data_example.json portfolio_data.json
# Edit portfolio_data.json with your holdings
python 05-scripts/rebuild.py
# Open portfolio_analysis.html in your browser
```

> 💡 **Stuck?** → [FAQ](FAQ.md) | [TROUBLESHOOTING](TROUBLESHOOTING.md) | [中文文档](README.zh-CN.md)

**For**: Individual investors, fund DCA users, beginners building trading discipline

**Typical workflow**: Daily close update, weekly position check, monthly P&L attribution, new opportunity evaluation

<br>

## 📂 Directory Structure

```
Anchor/
├── 00-system/         Data update protocol + session checkpoint
├── 01-rules/          Investment rules v3.3 + position checklist + stock rules
├── 02-strategy/       Historical optimizations, feasibility analyses
├── 03-analysis/       Sector analysis, market assessment, performance comparison
├── 04-reviews/        Deep reviews + weekly reports + monthly attribution
├── 05-scripts/        rebuild.py · sync_all.py · position calculator
├── 06-dashboard/      HTML dashboard + JSON snapshots (data not uploaded)
├── 07-memory/         Claude Memory persistent backup
├── 08-website/        Anchor Pro system overview page
└── .github/workflows/ CI daily check + Pages deploy
```

<br>

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Data Collection Layer                 │
│  mx-data API (primary) │  AKShare (fallback) │ Web    │
└────────────────────────┬─────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────┐
│                  Data Processing Layer                 │
│  portfolio_data.json ──→ rebuild.py ──→ dual output  │
│  (single editable src)    (core engine)   Desktop+repo│
└────────────────────────┬─────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ HTML     │  │ JSON     │  │  Excel   │
    │ Dashboard│  │ Snapshot │  │  Desktop │
    │ Dark UI  │  │ Dual copy│  │          │
    └──────────┘  └──────────┘  └──────────┘
          │
          ▼
┌──────────────────────────────────────────────────────┐
│                  Analysis Layer (auto)                 │
│  Daily review │ Position check │ Weekly │ Monthly     │
└──────────────────────────────────────────────────────┘
```

<br>

## 📊 Data Update Cadence

| Frequency | Action | Trigger | Command |
|:--:|------|------|:--|
| ⚡ Real-time | Query quotes/DDX/premium | `mx-data` API | `用 mx-data 获取XXX` |
| 📅 Daily | Update close data → rebuild | Manual or CI | `更新今日数据` |
| 📋 Weekly | Position check + weekly report | Tell Claude | `仓位点检` / `生成周报` |
| 📈 Monthly | Attribution + rule review | Tell Claude | `月度归因` |

<br>

## 📈 Version History

| Version | Date | Milestone |
|:--|:--|:--|
| v0.1 | 2025.06 | Initial holdings record, manual Excel |
| v1.0 | 2025.08 | Three-layer structure + basic buy/sell rules |
| v2.0 | 2025.11 | Four-layer pyramid + dual-track strategy |
| v2.5 | 2026.03 | FDIS introduced + first formal rule manual |
| v3.0 | 2026.05 | Full rebuild: negative checklist + evolution mechanism |
| v3.1 | 2026.06 | AI management system + Claude Memory framework |
| v3.2 | 2026.07 | DDX filter + monthly attribution system |
| **v3.3** | **2026.08** | **Dual-output data + session continuity + 4-tier data protocol** |

> 💡 See [CHANGELOG.md](CHANGELOG.md) for detailed version history

<br>

## 📝 Changelog

### 2026/08/06 - v3.3

**🎉 Major System Upgrade**

1. **Data Pipeline**
   - rebuild.py dual output: Desktop + Anchor/06-dashboard/ simultaneous writes
   - portfolio_data.json auto-sync: Desktop (primary) → Anchor (read-only copy)
   - sync_all.py fully rewritten with all path references fixed

2. **Visualization Upgrade**
   - Dashboard HTML rewritten in Premium dark terminal style
   - anchor-pro.html rewritten as data-driven (27.8KB → 31.5KB)
   - Three-tier HTML navigation links all connected

3. **New System Files**
   - `数据更新协议.md`: Real-time/daily/weekly/monthly 4-tier update system
   - `会话检查点.md`: Cross-conversation state recovery, instant resume in new sessions
   - Data freshness report: rebuild output includes market data age + rule alerts

4. **GitHub Integration**
   - .gitignore excludes 5 sensitive data files
   - git rm --cached on previously tracked sensitive files
   - GitHub Actions Pages auto-deploy
   - Full open-source community files (CONTRIBUTING / CODE_OF_CONDUCT / SECURITY / CHANGELOG)

5. **Documentation Update**
   - ANCHOR_体系总览 v3.2 → v3.3
   - Position checklist / stock trading rules updated to 8/6

**🔧 Upgrade Guide** (existing local deployments):
- Must update: `rebuild.py`, `sync_all.py`, all files under `06-dashboard/`
- Optional: README.md, .gitignore

<details>
<summary>👉 Click to expand: <strong>History</strong></summary>

### 2026/07 - v3.2

- DDX Filter: Semiconductor addition requires DDX positive 2 consecutive days
- Nasdaq ETF premium rule: premium ≤ 3% to open position
- Monthly attribution system refined
- GitHub Actions daily CI

### 2026/06 - v3.1

- AI investment management system architecture
- Claude Memory persistence framework
- 07-memory/ directory established

### 2026/05 - v3.0

- Four-layer pyramid structure finalized
- Negative checklist mechanism
- Rule evolution mechanism
- Formal investment rule manual

### 2025.06~2026.03 - v0.1~v2.5

- v0.1: Initial holdings record (manual Excel)
- v1.0: Three-layer structure + basic buy/sell rules
- v2.0: Four-layer pyramid + dual-track strategy
- v2.5: FDIS introduced + first formal rule manual

</details>

<br>

## 🙏 Acknowledgments

Thanks to the following tools and services that make this project possible:

- **Data** — [East Money Miaoxiang AI](https://data.eastmoney.com/) provides the mx-data API with accurate real-time A-share market data
- **AI** — [Claude](https://claude.ai) provides intelligent assistance for review analysis, rule optimization, and report generation
- **Infrastructure** — [GitHub](https://github.com) provides free Actions automation and Pages deployment
- **Inspiration** — [TrendRadar](https://github.com/sansan0/TrendRadar) excellent multi-platform aggregation + AI analysis architecture

<br>

## 🤝 Contributing

Issues and PRs welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before contributing.

- 🐛 Found a bug? Open a [Bug Report](https://github.com/killian99cm/anchor-system/issues/new?template=bug_report.md)
- 💡 Have an idea? Open a [Feature Request](https://github.com/killian99cm/anchor-system/issues/new?template=feature_request.md)
- 🔧 Submitting code? Fork → Feature Branch → PR

> ⚠️ **Never submit real holdings data**. `.gitignore` is configured — use `portfolio_data_example.json` for testing.

<br>

## ⚠️ Disclaimer

**Not investment advice.** This is a personal learning project documenting a self-taught investor's framework iteration process. Past performance does not guarantee future results. Investing involves risk — invest with caution. Do not copy trades directly.

## 📄 License

MIT © [killian99cm](https://github.com/killian99cm) — Framework code is free to use. Fill in your own holdings data and you're good to go.
