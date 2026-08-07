# Contributing Guide

Thank you for your interest in the Anchor investment management system!

## Before You Submit

### ⚠️ Never Commit Real Holdings Data
- Never commit `portfolio_data.json`
- Never commit `portfolio_snapshot.json`
- Never commit `portfolio_analysis.html` (contains embedded data)
- Never commit `portfolio_holdings.xlsx`
- Use `portfolio_data_example.json` for testing

### What You Can Contribute
- 🐛 Bug fixes (code, scripts, HTML)
- 📖 Documentation improvements (rule manual, README, comments)
- 🎨 Visualization improvements (dashboard HTML/CSS)
- 🔧 New features (data collection, analysis tools, backtesting)
- 🌐 Translations

## Submission Process

```bash
# 1. Fork the repository
# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/anchor-system.git
cd anchor-system

# 3. Create a feature branch
git checkout -b feature/my-improvement

# 4. Test with example data
cp 06-dashboard/portfolio_data_example.json portfolio_data.json
python 05-scripts/rebuild.py

# 5. Commit (do not include sensitive files)
# .gitignore is configured and will automatically exclude them on git add

# 6. Push and open a PR
```

## Code Style

- **Python**: Keep it simple; don't add new dependencies unless necessary
- **HTML/CSS**: Dark terminal style, zero external dependencies
- **Markdown**: Chinese documentation, clarity first

## Issue Guidelines

- 🐛 Bug reports: describe reproduction steps + expected behavior
- 💡 Feature suggestions: describe the use case + why it's needed

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Please stay kind and constructive.
