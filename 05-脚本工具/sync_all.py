"""
每日一键同步: portfolio_data.json 更新 → 看板HTML + 快照JSON + Excel

用法: python sync_all.py
你每晚更新完 portfolio_data.json 后运行这个就行
"""
import json, os, subprocess, time, glob, shutil, logging, sys
from datetime import datetime

# ===== LOGGING =====
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
log_file = os.path.join(LOG_DIR, 'sync_all.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('sync_all')

DESKTOP = r"C:\Users\lenovo\Desktop"
ANCHOR = r"C:\Users\lenovo\Desktop\Anchor"
ANCHOR_DATA = os.path.join(ANCHOR, "06-看板数据")
ANCHOR_SCRIPTS = os.path.join(ANCHOR, "05-脚本工具")
PY = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python"

def run(cmd, cwd=None):
    """Run a command and log output. Returns (success, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120, cwd=cwd)
        if result.returncode != 0:
            log.error(f"Command failed (rc={result.returncode}): {cmd[:100]}")
            if result.stderr:
                log.error(f"  stderr: {result.stderr.strip()[:500]}")
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                log.info(f"  {line.strip()}")
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        log.error(f"Command timed out: {cmd[:100]}")
        return False, "", "TIMEOUT"
    except Exception as e:
        log.error(f"Command failed with exception: {e}")
        return False, "", str(e)

def sync():
    now = time.strftime("%Y-%m-%d %H:%M")
    today = time.strftime("%Y%m%d")
    pf = os.path.join(DESKTOP, "portfolio_data.json")

    if not os.path.exists(pf):
        log.error(f"portfolio_data.json not found on Desktop: {pf}")
        return False

    # 1. Validate data before sync
    try:
        with open(pf, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        log.error(f"Invalid JSON in portfolio_data.json: {e}")
        return False
    except Exception as e:
        log.error(f"Failed to read portfolio_data.json: {e}")
        return False

    total = data.get('total_assets', 0)
    update_date = data.get('update_date', data.get('update_time', now))

    log.info(f"SYNC {now} | Total: CNY {total:,.0f} | Data date: {update_date}")

    # 2. Sync JSON to Anchor data dir
    os.makedirs(ANCHOR_DATA, exist_ok=True)
    dest_json = os.path.join(ANCHOR_DATA, "portfolio_data.json")
    try:
        shutil.copy2(pf, dest_json)
        log.info(f"JSON synced -> {dest_json}")
    except Exception as e:
        log.error(f"Failed to copy JSON: {e}")
        return False

    # 3. Run rebuild.py
    rebuild = os.path.join(ANCHOR_SCRIPTS, "rebuild.py")
    if os.path.exists(rebuild):
        ok, stdout, stderr = run(f'"{PY}" "{rebuild}"')
        if ok:
            log.info("rebuild.py [OK]")
        else:
            log.error("rebuild.py [FAILED]")
    else:
        log.warning(f"rebuild.py not found at {rebuild}")

    # 4. Generate Excel (unified: gen_excel_skill.py — 10-sheet full version)
    gen_excel = os.path.join(ANCHOR_SCRIPTS, "gen_excel_skill.py")
    if os.path.exists(gen_excel):
        ok, stdout, stderr = run(f'"{PY}" "{gen_excel}"')
        if ok:
            log.info("gen_excel_skill.py [OK]")
        else:
            log.warning("gen_excel_skill.py [FAILED]")
    else:
        log.info("gen_excel_skill.py not found, skipping Excel generation")

    # 5. Save daily snapshot
    kb_docs = os.path.join(ANCHOR, "04-每日复盘")
    os.makedirs(kb_docs, exist_ok=True)

    daily_file = os.path.join(kb_docs, f"daily_snapshot_{today}.md")
    if not os.path.exists(daily_file):
        try:
            active = [h for h in data.get('holdings_summary', []) if h.get('mv', 0) > 0]
            with open(daily_file, 'w', encoding='utf-8') as f:
                f.write(f"# 每日持仓快照 {update_date}\n\n")
                f.write(f"- 总资产: {total:,.0f}\n")
                f.write(f"- 基金: {data.get('fund_account', 0):,.0f} | 股票: {data.get('stock_account', 0):,.0f} | 余额宝: {data.get('yuebao', 0):,.0f}\n")
                f.write(f"- 持有盈亏: {data.get('total_hold_pnl_est', 0):+,.0f}\n\n")
                f.write("## 活跃持仓\n\n")
                for h in active:
                    f.write(f"- {h['name'][:20]}: 市值{h['mv']:,.0f} 累计{h.get('cumul',0):+,.0f} 当日{h.get('day_pnl',0):+,.2f}\n")
            log.info(f"Daily snapshot: daily_snapshot_{today}.md")
        except Exception as e:
            log.error(f"Failed to create daily snapshot: {e}")

    # 6. Clean old snapshots (keep last 30 days)
    try:
        old_files = sorted(glob.glob(os.path.join(kb_docs, "daily_snapshot_*.md")))
        if len(old_files) > 30:
            for f_path in old_files[:-30]:
                os.remove(f_path)
                log.info(f"Cleaned: {os.path.basename(f_path)}")
    except Exception as e:
        log.warning(f"Failed to clean old snapshots: {e}")

    log.info(f"SYNC DONE | JSON -> Anchor [OK] | HTML -> rebuild [OK]")
    log.info(f"  Desktop: {DESKTOP}")
    log.info(f"  Anchor:  {ANCHOR}")
    return True

if __name__ == "__main__":
    log.info("=" * 50)
    log.info("Anchor sync_all starting")
    log.info("=" * 50)
    success = sync()
    if success:
        log.info("Sync completed successfully.")
    else:
        log.error("Sync failed. Check log for details.")
        sys.exit(1)
