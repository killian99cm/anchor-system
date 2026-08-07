# 🔧 Troubleshooting

## Installation

### `python: command not found`

**Cause**: Python is not installed or not on the PATH.

**Fix**:
1. Download Python 3.8+ from [python.org](https://python.org)
2. During installation, **check "Add Python to PATH"**
3. Reopen the terminal and run `python --version` to verify

### `ModuleNotFoundError: No module named 'xxx'`

**Fix**:
```bash
pip install pandas   # needed for Excel export
pip install requests # needed if you fetch data manually (rebuild.py doesn't depend on this)
```

Most dependencies are bundled with Python, so no extra installs are needed.

## rebuild.py

### `FileNotFoundError: portfolio_data.json`

**Cause**: `portfolio_data.json` is not in the current directory.

**Fix**:
```bash
# Option 1: generate it with setup.py
python setup.py

# Option 2: copy the example
cp 06-dashboard/portfolio_data_example.json portfolio_data.json

# Option 3: run from the Anchor root directory
cd C:\Users\lenovo\Desktop\Anchor
python 05-scripts/rebuild.py
```

### `KeyError: 'xxx'`

**Cause**: `portfolio_data.json` is missing a required field.

**Fix**: Compare your JSON structure against `portfolio_data_example.json`. Or run `python setup.py --reset` to regenerate it.

### Garbled Chinese characters

**Cause**: Terminal encoding issue (common in Git Bash).

**Fix**: The file content is fine (UTF-8); only the terminal display is garbled. The generated HTML dashboard will render correctly. Or run it in PowerShell/CMD.

### `UnicodeDecodeError`

**Cause**: The config file is not UTF-8 encoded.

**Fix**: Open `portfolio_data.json` in VS Code / Notepad++ and save it as UTF-8.

## Dashboard

### Dashboard blank / data shows 0

**Checklist**:
1. Did you run `rebuild.py`? Check the terminal output to confirm success.
2. Are you opening `Desktop/portfolio_analysis.html` or an old copy?
3. Is `total_assets` > 0 in `portfolio_data.json`?
4. Any errors in the browser console (F12)?

### Charts not displaying

**Cause**: The `chart_data` array is empty or malformed.

**Fix**: Make sure the JSON has a `chart_data` field, formatted like:
```json
"chart_data": [
  {"d": "08-01", "sh": 3900, "star": 1700, "pnl": 100},
  {"d": "08-02", "sh": 3920, "star": 1715, "pnl": -50}
]
```

### Broken layout on mobile

**Cause**: The dashboard is designed for desktop.

**Fix**:
- The GitHub Pages version adapts to mobile automatically
- The local version looks better in landscape on a phone
- Or deploy to GitHub Pages and access it from your phone

## GitHub

### Push rejected

**Cause**: Cannot reach GitHub (common in mainland China).

**Fix**:
```bash
# Switch to SSH
git remote set-url origin git@github.com:killian99cm/anchor-system.git

# Or configure a proxy
git config --global http.proxy http://127.0.0.1:7890
```

### GitHub Pages not updating

**Check**:
1. Did the Actions workflow complete and turn green? (https://github.com/YOUR_USERNAME/anchor-system/actions)
2. In Settings → Pages, is "GitHub Actions" selected?
3. Wait 1-2 minutes; the CDN caches.

### How do I sync upstream updates after forking?

```bash
# Add the original repo as upstream
git remote add upstream https://github.com/killian99cm/anchor-system.git

# Fetch and merge
git fetch upstream
git merge upstream/main

# Push after resolving conflicts
git push origin main
```

## Data

### mx-data query fails

**Cause**: The API Key is not configured or has expired.

**Fix**:
1. Get an API Key from https://dl.dfcfs.com/m/itc4
2. Set the environment variable: `export MX_APIKEY=your_key`
3. Or manually fill the JSON using WebSearch / App data

### Fund NAV not updating

**Cause**: Off-exchange fund NAVs are usually published between 20:00 and 22:00.

**Fix**: Run rebuild again in the evening. Or use the day's estimated value first and correct it the next day.

---

If none of the above solved your problem, please open an Issue:
https://github.com/killian99cm/anchor-system/issues/new?template=bug_report.md
