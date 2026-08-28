# Anchor

**[English](README.md) | [中文](README.zh-CN.md)**

> ⚠️ **Disclaimer** — Anchor is for **educational purposes only**, **not financial advice**.
> Markets carry risk; you may lose money. Use at your own risk.

[![CI](https://github.com/killian99cm/anchor-system/actions/workflows/ci.yml/badge.svg)](https://github.com/killian99cm/anchor-system/actions/workflows/ci.yml)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-GitHub%20Pages-blue)](https://killian99cm.github.io/anchor-system)
[![Version](https://img.shields.io/badge/version-v4.3.3-blueviolet)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](SETUP.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> ⭐ If Anchor helps you, **star this repo** so others can find it.
> ⭐ 如果这套体系对你有帮助，欢迎点击 **Star**，让更多人看到它。

| 109 live trades | 80% decision accuracy | 0% chase violations | 13 mo track record |
|:---:|:---:|:---:|:---:|
| 实操交易笔数 | 决策判定准确率 | 追高违规次数 | 持续运行记录 |

<!-- 数据来源：05-scripts/transaction_ledger.md（2026-06~07 台账）/ 06-dashboard/decision_log.json（16/20 correct）/ 月度归因_2026年7月 -->

Anchor is a rules-driven personal investment management system for individual investors.

It turns a personal portfolio process into a repeatable workflow:

- maintain a four-layer allocation model
- encode investment discipline into executable checks
- generate a private local dashboard from a single portfolio data file
- publish sanitized public demo pages without exposing private holdings

---

## System at a glance

**Four-layer pyramid** (weight = role):

| Layer | Weight | Role | Rule |
|---|---|---|---|
| 🛡️ Bedrock | 45% | low-volatility ballast, portfolio foundation | hold long-term · 0-1 ops/year |
| 🚀 Core Growth | 20% | broad-index core assets | DCA + valuation gate |
| 🔥 Satellite Attack | 20% | high-beta offense, capped per position | -8% stop · ≤4 trades/month |
| 💰 Cash Reserve | 15% | safety buffer, waiting for extreme opportunities | deploy on crashes |

**Six iron rules:**

- [ ] 🛑 Never add to a losing position — no averaging down while underwater
- [ ] 🔒 72-hour freeze after selling — proceeds cool in cash before re-entry
- [ ] 📉 -8% stop-loss (1-day buffer + next-day 14:30 sector confirm)
- [ ] 📊 Portfolio drawdown lines — -5% / -10% / -15% trigger escalating cuts
- [ ] ⏱ 30-day time stop — satellite held >30 days and underperforming ≥5% → exit
- [ ] 🌐 Entry premium ≤3% — no chasing QDII at high premium, wait for NAV reversion

**Permanently banned:** ❌ averaging down · ❌ switching targets same day · ❌ buying without a plan

> "No predictions. Discipline only." — 不靠预测，靠纪律

---

## What Anchor does

Anchor combines three things into one system:

1. **Portfolio structure** — Bedrock / Core / Satellite / Cash layers
2. **Rule execution** — drawdown lines, operation limits, freeze state, dynamic holdings
3. **Output surfaces** — private dashboard, public demo pages, snapshots, and smoke checks

It is **not**:

- a stock-picking engine
- an auto-trading bot
- a public repository for your real portfolio data

---

## Documentation

- [Docs index](docs/index.md) — entry point for all guides
- [Setup](SETUP.md) · [FAQ](FAQ.md) · [Troubleshooting](TROUBLESHOOTING.md)
- [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)
- [Live demo](https://killian99cm.github.io/anchor-system) · [Track record (simulated backtest)](08-website/track-record.html)

---

## Screenshots

![Anchor overview](docs/screenshots/overview.png)

![Anchor structure — four-layer pyramid and rule boundaries](docs/screenshots/structure.png)

---

## Public vs private

Anchor is intentionally split into two worlds.

### Private, local-only

These stay on your machine and should not be pushed to GitHub:

- your real `portfolio_data.json`
- local reviews, rules, strategy notes, and memory backups
- private dashboard outputs built from real holdings

### Public, shareable

These are safe to publish:

- code under `05-scripts/` that does not embed private data
- sanitized example input: `06-dashboard/portfolio_data_example.json`
- public overview page: `08-website/anchor-pro.html`
- GitHub Pages example homepage: `06-dashboard/portfolio_analysis_example.html`

The repository is configured so the private workspace stays local while public assets remain shareable.

---

## Core pages

### Private dashboard

Generated locally from your real portfolio data.

Main output:

- `portfolio_analysis.html` on your Desktop

Use it for:

- daily decision-making
- risk review
- allocation checks
- weekly and monthly review support

### Public system overview

- `08-website/anchor-pro.html`

Use it for:

- explaining the Anchor method
- showing the structure and rule model
- sharing a sanitized version publicly

### GitHub Pages example homepage

- `06-dashboard/portfolio_analysis_example.html`

Use it for:

- public-facing landing page
- example dashboard preview
- safe online demo

---

## Quick start

### Step 1 — clone the repo

```bash
git clone https://github.com/killian99cm/anchor-system.git
cd anchor-system
```

### Step 2 — create your local private data file

Use the example file as the base:

```bash
cp 06-dashboard/portfolio_data_example.json portfolio_data.json
```

Then replace the example values with your own holdings **locally**.

### Step 3 — build your private dashboard

```bash
python "05-scripts/rebuild.py"
```

This generates your private outputs from local data.

### Step 4 — open the dashboard

Open:

- `portfolio_analysis.html`

That is your main daily cockpit.

---

## Daily usage flow

### Update local data

Refresh your local `portfolio_data.json` with the latest close, holdings, and notes.

### Rebuild outputs

Run:

```bash
python "05-scripts/rebuild.py"
```

### Read the private dashboard

Focus on:

- decision strip
- KPI matrix
- allocation drift
- risk board
- action queue
- trend cards

### Only trade after rules pass

Use the dashboard to check:

- current state
- freeze conditions
- drawdown lines
- operation count
- signal-specific rules such as DDX / premium-rate / time-stop

---

## Weekly usage flow

Once per week:

- review the four-layer allocation
- scan pending actions and red lights
- check whether any layer drift requires attention
- generate and read the weekly summary from your local workflow

---

## Monthly usage flow

Once per month:

- review monthly attribution
- inspect which rules protected you
- inspect which rules triggered too late or too often
- update the system only if a change is justified by real behavior and repeatable evidence

---

## Public page generation

To refresh the sanitized public pages:

```bash
python "05-scripts/gen_anchor_pro.py"
```

This updates both:

- `08-website/anchor-pro.html`
- `06-dashboard/portfolio_analysis_example.html`

The public generator uses only sanitized example data and checks for private token leakage.

---

## Validation

Run the smoke test before publishing or after larger changes:

```bash
python "05-scripts/smoke_test.py"
```

It verifies:

- rebuild output exists
- snapshots are consistent
- public pages stay sanitized
- dynamic holding contracts are present
- inline scripts still parse correctly
- GitHub Pages example page remains valid

---

## Key scripts

- `05-scripts/data_processor.py` — computes portfolio state, drawdown, risk, freeze, and layer contracts
- `05-scripts/rebuild.py` — builds the private dashboard from local portfolio data
- `05-scripts/gen_anchor_pro.py` — injects sanitized example data into public pages
- `05-scripts/smoke_test.py` — validates output integrity and privacy boundaries
- `05-scripts/gen_monthly_attribution.py` — supports monthly attribution workflow
- `05-scripts/test_calculations.py` — verifies core calculation behavior

---

## Typical end-to-end user journey

1. Discover the repo on GitHub
2. Read the public README and public demo page
3. Clone the repo
4. Create a local private `portfolio_data.json`
5. Run `rebuild.py`
6. Open the private dashboard
7. Use the dashboard daily after market close
8. Run weekly checks and monthly attribution locally
9. Use the public pages only for sharing the framework, never for exposing real holdings

---

## Privacy note

This repository is built around a strict rule:

> **Real portfolio data stays local. Public GitHub pages use sanitized examples only.**

If you use Anchor, keep your real holdings out of GitHub and only publish the public example assets.
