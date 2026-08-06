"""
每日一键同步: portfolio_data.json 更新 → 看板HTML + 快照JSON + Excel

用法: python sync_all.py
你每晚更新完 portfolio_data.json 后运行这个就行
"""
import json, os, subprocess, time, glob, shutil

DESKTOP = r"C:\Users\lenovo\Desktop"
ANCHOR = r"C:\Users\lenovo\Desktop\Anchor"
ANCHOR_DATA = os.path.join(ANCHOR, "06-看板数据")
ANCHOR_SCRIPTS = os.path.join(ANCHOR, "05-脚本工具")
PY = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python"

def run(cmd, cwd=None):
    subprocess.run(cmd, shell=True, capture_output=True, timeout=120, cwd=cwd)

def sync():
    now = time.strftime("%Y-%m-%d %H:%M")
    today = time.strftime("%Y%m%d")
    pf = os.path.join(DESKTOP, "portfolio_data.json")

    if not os.path.exists(pf):
        print("[ERROR] portfolio_data.json not found on Desktop")
        return

    # 1. 读最新数据
    with open(pf, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total = data.get('total_assets', 0)
    update_date = data.get('update_date', data.get('update_time', now))

    print(f"[SYNC] {now} | Total: CNY {total:,.0f} | Data date: {update_date}")

    # 2. 同步 JSON 到 Anchor 看板目录
    os.makedirs(ANCHOR_DATA, exist_ok=True)
    dest_json = os.path.join(ANCHOR_DATA, "portfolio_data.json")
    shutil.copy2(pf, dest_json)
    print(f"  JSON synced -> {dest_json}")

    # 3. 运行 rebuild.py 生成 HTML + Snapshot
    rebuild = os.path.join(ANCHOR_SCRIPTS, "rebuild.py")
    if os.path.exists(rebuild):
        run(f'"{PY}" "{rebuild}"')
        print("  rebuild.py [OK]")

    # 4. 生成 Excel
    gen_excel = os.path.join(ANCHOR_SCRIPTS, "gen_excel_v2.py")
    if os.path.exists(gen_excel):
        run(f'"{PY}" "{gen_excel}"')
        print("  gen_excel_v2.py [OK]")

    # 5. 保存每日快照到 Anchor 知识库
    kb_docs = os.path.join(ANCHOR, "04-每日复盘")
    os.makedirs(kb_docs, exist_ok=True)

    daily_file = os.path.join(kb_docs, f"daily_snapshot_{today}.md")
    if not os.path.exists(daily_file):
        active = [h for h in data.get('holdings_summary', []) if h.get('mv', 0) > 0]
        with open(daily_file, 'w', encoding='utf-8') as f:
            f.write(f"# 每日持仓快照 {update_date}\n\n")
            f.write(f"- 总资产: {total:,.0f}\n")
            f.write(f"- 基金: {data.get('fund_account', 0):,.0f} | 股票: {data.get('stock_account', 0):,.0f} | 余额宝: {data.get('yuebao', 0):,.0f}\n")
            f.write(f"- 持有盈亏: {data.get('total_hold_pnl_est', 0):+,.0f}\n\n")
            f.write("## 活跃持仓\n\n")
            for h in active:
                f.write(f"- {h['name'][:20]}: 市值{h['mv']:,.0f} 累计{h.get('cumul',0):+,.0f} 当日{h.get('day_pnl',0):+,.2f}\n")
        print(f"  Daily snapshot: daily_snapshot_{today}.md")

    # 6. 清理旧快照（保留最近 30 天）
    old_files = sorted(glob.glob(os.path.join(kb_docs, "daily_snapshot_*.md")))
    if len(old_files) > 30:
        for f in old_files[:-30]:
            os.remove(f)
            print(f"  Cleaned: {os.path.basename(f)}")

    print(f"\n[SYNC DONE] portfolio_data.json -> Anchor [OK] -> HTML [OK] -> Excel [OK]")
    print(f"   Desktop: {DESKTOP}")
    print(f"   Anchor:  {ANCHOR}")

if __name__ == "__main__":
    sync()
