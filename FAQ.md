# ❓ Frequently Asked Questions (FAQ)

## Getting Started

### Q: I don't know Python at all. Can I use this?

Yes. You only need to:
1. Install Python on your computer (download from [python.org](https://python.org), check "Add to PATH")
2. Edit `portfolio_data.json` to fill in your holdings (open with Notepad)
3. Double-click to run (or type `python 05-scripts/rebuild.py` in a terminal)
4. Double-click `portfolio_analysis.html` to view

No coding required. If you have any problems, run `python setup.py` for an interactive guided setup.

### Q: I'm not a programmer. What's this useful for me?

Anchor isn't a tech product — it's an **investment discipline tool**. It helps you:
- Record all your holdings at a glance
- Automatically check the rules (stop-loss / take-profit / time expiry)
- Generate a visual dashboard without opening N apps
- Get automated review reports that save manual calculation

### Q: Does it cost money?

Completely free. The code is open source (MIT), data comes from free APIs, and the dashboard is pure HTML with zero dependencies.

## Data

### Q: Will my holdings data be uploaded to the internet?

**No.** `.gitignore` already excludes all sensitive files. If you don't use Git, the data stays on your machine only. If you upload to GitHub, sensitive files are automatically ignored.

### Q: How do I write portfolio_data.json?

Refer to `06-dashboard/portfolio_data_example.json`. Core fields:
- `holdings_summary`: fund list (name/mv/pnl/group)
- `stock_holdings`: stock list (name/shares/cost/price)
- `yuebao`: Yu'ebao balance
- `market`: market data

For details, run `python setup.py` for interactive configuration.

### Q: Where does the data come from?

Priority: `mx-data API (Eastmoney) → AKShare → WebSearch → App screenshots`

For daily updates, just say "update today's data" and the pipeline fetches it automatically.

### Q: How often should I update?

| Frequency | Action |
|:--|:--|
| Daily | Update JSON after market close → rebuild |
| Weekly | Position check + generate weekly report |
| Monthly | Monthly attribution + rule review |

## Dashboard

### Q: The dashboard opens blank?

Check:
1. Did `rebuild.py` run successfully (no errors in the terminal)?
2. Are you opening `Desktop/portfolio_analysis.html` (not the copy in `06-dashboard/`)?
3. Does `portfolio_data.json` contain data?

### Q: How can I view the dashboard on my phone?

Once you deploy GitHub Pages, it adapts to mobile automatically. Or just send the HTML file to your phone's browser.

### Q: Can I customize the colors/layout?

Yes. The HTML template in `rebuild.py` uses pure CSS variables — edit the `:root` block to switch themes.

## Rules

### Q: Why so many rules? Isn't this too rigid?

Rules exist to **keep emotions in check**. Backtested validation: across 109 real trades, every maximum loss happened when a rule was violated. Rules don't guarantee profit, but they guarantee survival.

### Q: Can I change the rules?

Of course. The rules are yours; the framework just helps you enforce them. Edit the files under `01-rules/`, then adjust the corresponding check logic in rebuild.py.

### Q: Why not add to a losing position?

The data proves it: the biggest losses for individual investors come from "buying more as the price falls." An unrealized loss means your call was wrong, and averaging down amplifies the mistake. Better to miss a rebound than to add to a losing position.

## Technical

### Q: What dependencies do I need to install?

- Python 3.8+
- Standard library: json, os, shutil (bundled with Python)
- Optional: pandas (for Excel export)

```bash
pip install pandas  # only needed for Excel export
```

### Q: How do I deploy to a server?

```bash
# Docker (coming soon)
docker run -v ./your_data:/data killian99cm/anchor-system

# Manual
crontab -e
# Add: 0 20 * * * cd /path/to/anchor && python 05-scripts/rebuild.py
```

### Q: Can I integrate other data sources?

Yes. Modify the data-loading logic in `rebuild.py` to adapt to any JSON format, or extend the data-source module to integrate the XXX data source.

### Q: How do I contribute code?

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs are welcome!
