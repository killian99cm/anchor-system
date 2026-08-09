# Anchor

Anchor is a rules-driven personal investment management system built around a four-layer pyramid, a data-processing pipeline, and a zero-dependency HTML dashboard.

It is designed to help you:
- keep a stable allocation across bedrock / core / satellite / cash layers
- turn portfolio rules into executable checks
- generate a private dashboard from your local `portfolio_data.json`
- publish a sanitized public demo page to GitHub Pages

## Public vs private

- **Private workspace** stays on your machine only: `00-system/`, `01-rules/`, `02-strategy/`, `03-analysis/`, `04-reviews/`, `07-memory/`, and your local `portfolio_data.json`
- **Public repo** contains the code, public docs, and sanitized examples only
- **Public pages** use `06-dashboard/portfolio_data_example.json` and `08-website/anchor-pro.html`

## Quick start

1. Clone the repo
2. Copy `06-dashboard/portfolio_data_example.json` to your local `portfolio_data.json`
3. Edit the local file with your own holdings
4. Run:

```bash
python "05-scripts/rebuild.py"
```

5. Open `portfolio_analysis.html` on your Desktop

## Daily workflow

- **Update today’s data**: refresh local holdings data, then run `rebuild.py`
- **Position check**: review allocation, freeze state, drawdown, and rules before trading
- **Weekly report**: generate a weekly summary from your local data
- **Monthly attribution**: review monthly performance and rule outcomes

## Public pages

- **Demo homepage**: `06-dashboard/portfolio_analysis_example.html`
- **System overview**: `08-website/anchor-pro.html`

## What runs locally

- `05-scripts/data_processor.py` — calculates state, risk, drawdown, and layer contract
- `05-scripts/rebuild.py` — builds the private dashboard
- `05-scripts/gen_anchor_pro.py` — injects sanitized data into public pages
- `05-scripts/smoke_test.py` — checks output integrity and privacy boundaries

## Notes

- The repo intentionally avoids storing private portfolio files in GitHub.
- Keep your real holdings in the local `portfolio_data.json` only.
- The public sample data is safe to share and is not meant to reflect your real portfolio.
