<div align="center" id="anchor">

<a href="https://github.com/killian99cm/anchor-system" title="Anchor">
  <img src="https://img.shields.io/badge/⚓_Anchor-v3.3-4d8af0?style=for-the-badge" alt="Anchor v3.3" height="36">
</a>

🚀 A Rule-Driven Personal Investment Management System — **Discipline Over Emotion, Data Over Instinct**

[![GitHub Stars](https://img.shields.io/github/stars/killian99cm/anchor-system?style=flat-square&logo=github&color=yellow)](https://github.com/killian99cm/anchor-system/stargazers)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
[![Version](https://img.shields.io/badge/version-v3.3-blue.svg)](https://github.com/killian99cm/anchor-system)
[![Trades](https://img.shields.io/badge/Live_Trades-109-00d69e?style=flat-square)](https://github.com/killian99cm/anchor-system)

[![Data-mxdata](https://img.shields.io/badge/Data-mx_data_API-4d8af0?style=flat-square)](https://data.eastmoney.com/)
[![Dashboard-ZeroDep](https://img.shields.io/badge/Dashboard-Pure_HTML/Zero_JS_Deps-00d69e?style=flat-square)](https://killian99cm.github.io/anchor-system)
[![分析-自动](https://img.shields.io/badge/分析-自动-f04668?style=flat-square)](https://github.com/killian99cm/anchor-system)
[![CI-GitHub Actions](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?style=flat-square&logo=github-actions)](https://github.com/killian99cm/anchor-system/actions)
[![Demo-Pages](https://img.shields.io/badge/Demo-GitHub_Pages-4285F4?style=flat-square&logo=github)](https://killian99cm.github.io/anchor-system)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat-square&logo=python)](https://www.python.org/)

</div>

<div align="center">

**[中文](README.md)** | **English**

</div>

> 💡 **What is this?** A personal system that turns investment discipline into executable code. Not a stock-picking strategy. Not AI auto-trading. Does NOT recommend specific products.

<br>

## 📑 Quick Navigation

<div align="center">

| [🧠 Philosophy](#-core-philosophy) | [📜 Rules](#-rule-system) | [⚡ Quick Start](#-quick-start) | [📂 Structure](#-directory-structure) | [📊 Data Flow](#-data-flow) |
|:---:|:---:|:---:|:---:|:---:|
| [🏗️ Architecture](#️-system-architecture) | [📈 Versions](#-version-history) | [🤖 AI System](#-ai-analysis-system) | [🌐 Live Demo](#-live-demo) | [📝 Changelog](#-changelog) |

</div>

<br>

## ✨ Core Features

### 🏗️ Four-Layer Pyramid

```
       ┌──────────────────────────────────┐
 20%   │  🔥 Satellite       -8% Stop Loss│  Swing Trading
       │  Sector ETFs+Stocks  No Averaging│  High Risk/Reward
       ├──────────────────────────────────┤
 20%   │  🚀 Core Growth     DCA+Dip Buy  │  Long-term Growth
       │  Broad Index+QDII   Build Slowly │  Compound Engine
       ├──────────────────────────────────┤
 45%   │  🛡️ Bedrock         Never Sell   │  Portfolio Anchor
       │  Bonds+Fixed Income  Qtrly Rebal │  Stable Returns
       ├──────────────────────────────────┤
 15%   │  💰 Cash Reserve    Crash Ammo    │  Opportunity Fund
       │  Money Market       Stay Liquid  │  Wait & Strike
       └──────────────────────────────────┘
```

### 📜 Rule Engine

**Four Iron Rules**: Never Average Down · -8% Hard Stop · 72h Cooldown · Tiered Take-Profit (+15%/+30%/+50%)

**Six Permanent Bans**: No Converting · No Averaging · No Same-Day Swaps · No Overcapacity · No DCA on Satellite · No FOMO

**v3.3 Filters**: DDX Filter (semiconductor) · Nasdaq Premium Rate ≤3% · 30-Day Time Stop · Monthly Trade Cap ≤4

### 📊 Data Pipeline

```
portfolio_data.json (single source of truth) → rebuild.py → Dual Output (Desktop + Repo Copy)
                                                              ├── HTML Dashboard
                                                              ├── JSON Snapshot
                                                              └── Excel Report
```

### 🤖 AI Analysis (Claude)

Natural language interaction for: Daily Reviews · Position Checks · Weekly Reports · Monthly Attribution · Rule Optimization

### 🌐 Live Demo

> 📋 **[View Demo →](https://killian99cm.github.io/anchor-system)** Sanitized example dashboard

<br>

## ⚡ Quick Start

```bash
git clone https://github.com/killian99cm/anchor-system.git
cd anchor-system

# Option A: Interactive setup (recommended)
python setup.py

# Option B: Manual setup
cp 06-dashboard/portfolio_data_example.json portfolio_data.json
# Edit portfolio_data.json with your holdings
python 05-scripts/rebuild.py
# Open portfolio_analysis.html
```

<br>

## 📈 Version History

| Version | Date | Milestone |
|:--|:--|:--|
| v0.1 | 2025.06 | Manual Excel tracking |
| v1.0 | 2025.08 | 3-layer structure + basic rules |
| v2.0 | 2025.11 | 4-layer pyramid + dual-track strategy |
| v3.0 | 2026.05 | Full restructure: forbidden list + evolution |
| v3.2 | 2026.07 | DDX filter + monthly attribution |
| **v3.3** | **2026.08** | **Dual output + session continuity + data protocol** |

<br>

## ⚠️ Disclaimer

**This is NOT investment advice.** This is a personal learning project documenting one investor's framework evolution. Past performance does not guarantee future results. Never blindly follow anyone's trades.

## 📄 License

MIT © [killian99cm](https://github.com/killian99cm) — Use the framework freely. Fill in your own holdings data.
