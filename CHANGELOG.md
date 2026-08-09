# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/).

---

## [Unreleased]

### Added

- GitHub Actions CI quality gate: on every push/PR to `main`, runs Python syntax check, 34 core calculation tests, public page regeneration with example-data contract + privacy scan, and a no-drift check that committed public pages match generator output.
- MIT LICENSE added.

### Changed

- CI verifies public pages stay sanitized on a fresh checkout with no local private data present.

---

## [v3.3.1] — 2026-08-08

### Added

- Unified state contract in generated dashboard/snapshot: `state`, `drawdown_state`, `ops_state`, `risk_state`, `freeze_state`, `clock_state`, `factor_clusters`, and `opportunity_scores`.
- Public homepage example now shares the sanitized `var D` contract with `anchor-pro.html` and is covered by smoke checks.
- Inline JavaScript syntax checks in `smoke_test.py` catch blank-page regressions before release.
- Dynamic holding contract in generated dashboard/snapshot/public example data: `holding_counts`, `layers`, `layer_order`, and `layer_meta`.
- Public publishing boundary smoke checks for `08-website/anchor-pro.html`: verifies sanitized example data, zero private asset total, visible example label, whitespace-tolerant private-token absence, dynamic layer rendering, and forbidden-card schema consistency.
- Hash-based Desktop vs `06-dashboard/` copy consistency validation in `smoke_test.py`.
- Holding-row take-profit/profile display in generated dashboard output.

### Changed

- Operation-count rendering is fully data-driven from `ops_state.label` instead of hard-coded "August Ops".
- Operation discipline text now distinguishes clean, at-limit, over-limit, and actual violation states.
- `smoke_test.py` now runs end-to-end checks covering rebuild output, state contracts, dynamic holding contracts, snapshot, Excel, public page, public static-copy sanitization, and core calculation tests.
- GitHub Pages deploy workflow now triggers on `main`.

### Fixed

- Public `anchor-pro.html` embed parser/checks now tolerate both `var D = {...}` and `var D={...}` formats.
- Copy consistency checks now compare content hashes and avoid unsafe `.stat()` calls when files are missing.
- Public example cash display is no longer tied to a fixed `余额宝` label in generated content.
- Public page generation now maps all example holding/stock names to generic labels, scans the final HTML for whitespace-spaced private tokens, and aligns forbidden-card data keys with the renderer.

---

## [v3.3] — 2026-08-06

### Added

- Data update protocol: a four-tier update system (real-time / daily / weekly / monthly)
- Session checkpoints: cross-conversation state recovery mechanism
- GitHub Pages auto-deployment workflow
- `portfolio_analysis_example.html` sanitized example dashboard
- `portfolio_data_example.json` sanitized example data
- `.gitignore` sensitive-data exclusion rules
- Data freshness report (rebuild.py output includes market-data age + rule alerts)

### Changed

- rebuild.py dual-path output: writes to both Desktop and Anchor/06-dashboard/
- sync_all.py fully rewritten; all path references fixed
- README.md comprehensive upgrade (badges + architecture diagram + quick start)
- anchor-pro.html rewritten to be data-driven (27.8KB → 31.5KB)
- CLAUDE.md rewritten as the system entry point

### Fixed

- `06-dashboard/portfolio_analysis.html` data disconnection → dual-path output
- `06-dashboard/portfolio_data.json` stale data off by ¥5,240 → auto-sync
- GitHub Actions CI three blocking errors (checkout@v5→v4, setup-python@v6→v5, path)
- anchor_calculator.html undefined CSS variable `--text3`

### Removed

- `rebuild_anchor.py` (dead code)
- `portfolio_reference.csv` (dead code)
- `anchor-dark.html`, `anchor-glass.html`, `anchor-light.html` (outdated visualizations)
- Old README (leftover on the main branch)

### Security

- GitHub sanitization: git rm --cached 5 sensitive files
- .gitignore prevents re-committing

---

## [v3.2] — 2026-07

### Added

- DDX filter: adding to semiconductor positions requires DDX positive for 2 consecutive days
- Nasdaq ETF premium-rate rule: only open positions when the premium rate is ≤3%
- Monthly attribution system
- GitHub Actions daily CI

### Changed

- Investment rule manual v3.1 → v3.2

---

## [v3.1] — 2026-06

### Added

- AI investment management system architecture
- Claude Memory persistence system
- 07-memory/ directory

---

## [v3.0] — 2026-05

### Added

- Four-layer pyramid structure
- Negative-list mechanism
- Rule evolution mechanism
- Official investment rule manual

---

## [v2.x] — 2025.11 ~ 2026.03

### v2.5 (2026.03)

- FDIS framework introduced
- First edition of the official rule manual

### v2.0 (2025.11)

- Four-layer structure took shape
- Dual-track strategy

---

## [v1.0] — 2025.08

### Added

- Three-layer structure
- Basic buy/sell rules

---

## [v0.1] — 2025.06

### Added

- Initial holdings records (manual Excel)
