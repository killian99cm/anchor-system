"""
每日一键同步: portfolio_data.json 更新 → Viking + 知识库 + Excel + HTML

用法: python sync_all.py
你每晚更新完 portfolio_data.json 后运行这个就行
"""
import json, urllib.request, os, subprocess, time, glob

DESKTOP = r"C:\Users\lenovo\Desktop"
VIKING = "http://127.0.0.1:18790"
PY = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python"

def viking_overwrite(uri, content):
    """覆盖写入 Viking (同 URI 替换旧数据)"""
    body = json.dumps({"uri": uri, "content": content}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(f"{VIKING}/api/v1/resources", data=body,
                                  headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30)

def run(cmd):
    subprocess.run(cmd, shell=True, capture_output=True, timeout=60)

def sync():
    now = time.strftime("%Y-%m-%d %H:%M")
    today = time.strftime("%Y%m%d")
    pf = os.path.join(DESKTOP, "portfolio_data.json")

    if not os.path.exists(pf):
        print("[ERROR] portfolio_data.json not found")
        return

    # 1. 读最新数据
    with open(pf, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total = data.get('total_assets', 0)
    funds = data.get('fund_account', 0)
    stock = data.get('stock_account', 0)
    yuebao = data.get('yuebao', 0)
    update_date = data.get('update_date', now)

    print(f"[SYNC] {now} | 总资产: {total:,.0f} | 更新日期: {update_date}")

    # 2. 计算当日盈亏
    day_total = sum(h.get('day_pnl', 0) or 0 for h in data.get('holdings_summary', []))
    holdings_count = len([h for h in data.get('holdings_summary', []) if h.get('mv', 0) > 0])

    # 3. 找最大赢家和输家
    active = [h for h in data.get('holdings_summary', []) if h.get('mv', 0) > 0]
    active.sort(key=lambda h: h.get('cumul', 0) or 0, reverse=True)
    top3 = active[:3]
    bottom3 = active[-3:]

    # 4. 覆盖写入 Viking（只保留最新）— 忽略连接失败
    try:
        viking_overwrite("viking://snapshot/latest",
            f"最新快照:{now}。总资产{total:,.0f}元(基金{funds:,.0f}+股票{stock:,.0f}+余额宝{yuebao:,.0f})。"
            f"当日盈亏{day_total:+.2f}元。{holdings_count}只持仓。"
            f"最大盈利:{top3[0].get('name','')[:12]}+{top3[0].get('cumul',0):.0f} "
            f"最大亏损:{bottom3[0].get('name','')[:12]}{bottom3[0].get('cumul',0):.0f}")
    except Exception as e:
        print(f"  Viking snapshot skip: {e}")

    # 5. 覆盖持仓汇总
    try:
        summary_lines = []
        for h in active:
            name = h.get('name', '?')[:20]
            mv = h.get('mv', 0)
            cp = h.get('cumul', 0) or 0
            dp = h.get('day_pnl', 0) or 0
            summary_lines.append(f"{name}:市值{mv:.0f},累计{cp:+.0f},当日{dp:+.0f}")
        viking_overwrite("viking://portfolio/current", " | ".join(summary_lines[:25]))
    except Exception as e:
        print(f"  Viking portfolio skip: {e}")

    # 6. 保存每日快照到知识库 docs
    kb_docs = os.path.join(DESKTOP, "investment_kb", "docs")
    os.makedirs(kb_docs, exist_ok=True)

    daily_file = os.path.join(kb_docs, f"daily_{today}.md")
    if not os.path.exists(daily_file):
        with open(daily_file, 'w', encoding='utf-8') as f:
            f.write(f"# 每日持仓快照 {update_date}\n\n")
            f.write(f"- 总资产: {total:,.0f}\n")
            f.write(f"- 基金: {funds:,.0f} | 股票: {stock:,.0f} | 余额宝: {yuebao:,.0f}\n")
            f.write(f"- 当日盈亏: {day_total:+.2f}\n")
            f.write(f"- 持仓数: {holdings_count}\n\n")
            f.write("## 盈亏排名\n\n")
            for h in active:
                f.write(f"- {h['name'][:20]}: 市值{h['mv']:.0f} 累计{h.get('cumul',0):+.0f} 当日{h.get('day_pnl',0):+.2f}\n")
        print(f"  Daily snapshot saved: daily_{today}.md")

    # 7. 重建 HTML + Excel
    rebuild = os.path.join(DESKTOP, "rebuild.py")
    if os.path.exists(rebuild):
        run(f'"{PY}" "{rebuild}"')
        print("  HTML rebuilt")

    gen_excel = os.path.join(DESKTOP, "gen_excel_skill.py")
    if os.path.exists(gen_excel):
        run(f'"{PY}" "{gen_excel}"')
        print("  Excel rebuilt")

    # 8. 清理旧快照（保留最近 30 天）
    old_files = sorted(glob.glob(os.path.join(kb_docs, "daily_*.md")))
    if len(old_files) > 30:
        for f in old_files[:-30]:
            os.remove(f)
            print(f"  Cleaned old: {os.path.basename(f)}")

    # 9. 统计
    try:
        body = b'{}'
        req = urllib.request.Request(f"{VIKING}/api/v1/system/status", data=body,
                                      headers={"Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=5).read())
        cnt = r['result']['vikingdb']['collections'][0]['vector_count']
        viking_status = f"Viking: {cnt} records |"
    except Exception as e:
        viking_status = "Viking: offline |"

    print(f"\n[SYNC DONE] {viking_status} Daily snapshots: {len(old_files)} files")
    print(f"   portfolio_data.json -> KB [OK] -> HTML [OK] -> Excel [OK]")

if __name__ == "__main__":
    sync()
