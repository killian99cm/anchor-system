#!/usr/bin/env python3
"""Anchor Excel Generator v2 — reads portfolio_data.json, outputs portfolio_holdings.xlsx"""

import json
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

DATA = Path(r"C:\Users\lenovo\Desktop\portfolio_data.json")
OUT = Path(r"C:\Users\lenovo\Desktop\portfolio_holdings.xlsx")

with open(DATA, encoding="utf-8") as f:
    D = json.load(f)

# Theme
T = {'primary': '1F4E79', 'light': 'D6E3F0'}
SRF = 'Georgia'
SNS = 'Calibri'
SEM = {'pos': '2E7D32', 'neg': 'C62828', 'warn': 'F57C00'}

# Borders
O = Side(style='thin', color='C0C0C0')
HB = Side(style='medium', color=T['primary'])
I = Side(style='thin', color='E0E0E0')
N = Side(style=None)

def frame(ws, r1, r2, c1, c2):
    for r in range(r1, r2+1):
        for c in range(c1, c2+1):
            cl = ws.cell(row=r, column=c)
            cl.border = Border(left=O if c==c1 else N, right=O if c==c2 else N,
                              top=O if r==r1 else I, bottom=HB if r==r1 else (O if r==r2 else I))

def hdr(ws, r, sc, labels):
    for j, v in enumerate(labels, sc):
        c = ws.cell(row=r, column=j, value=v)
        c.font = Font(name=SRF, size=10, bold=True, color='FFFFFF')
        c.fill = PatternFill(start_color=T['primary'], end_color=T['primary'], fill_type='solid')
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[r].height = 26

def wc(ws, r, c, value, font=None, align='center', fmt=None):
    cell = ws.cell(row=r, column=c)
    cell.value = value if value is not None else ''
    cell.font = font or Font(name=SNS, size=11)
    if align == 'L': cell.alignment = Alignment(horizontal='left', vertical='center', indent=1)
    elif align == 'R': cell.alignment = Alignment(horizontal='right', vertical='center')
    else: cell.alignment = Alignment(horizontal='center', vertical='center')
    if fmt: cell.number_format = fmt
    return cell

MNY = '#,##0.00'
PCT = '0.00%'
INT = '#,##0'

# ===== Data =====
holdings = [h for h in D.get('holdings_summary', []) if h.get('mv', 0) > 1]
stocks = D.get('stock_holdings', [])
yuebao = D.get('yuebao', 0)
mkt = D.get('market', {})
update_date = D.get('update_date', '')

# Classify
bedrock, core_gr, satellite, pending = [], [], [], []
for h in holdings:
    n, g = h.get('name', ''), h.get('group', '')
    mv = h.get('mv', 0)
    if g == '待结算':
        pending.append(h)
    elif '余额宝' in n:
        pass
    elif g == '全局固收' or '黄金' in n or '债券' in n:
        bedrock.append(h)
    elif '纳斯达克' in n or '纳指' in n or '示例指数基金通利' in n:
        core_gr.append(h)
    else:
        satellite.append(h)

for s in stocks:
    bedrock.append({'name': s.get('name', '红利ETF'), 'mv': s.get('mv', 0),
                    'pnl': s.get('pnl', 0), 'day_pnl': s.get('day_pnl', 0),
                    'cumul': 0, 'note': f"{s.get('shares',0)}股×{s.get('cost',0):.3f}"})

total_assets = D.get('total_assets', 0)
total_pnl = D.get('total_hold_pnl_est', 0)
pending_total = D.get('pending_clearance_total', 0)

wb = Workbook()

# ===== Sheet 1: 总览 =====
ws = wb.active
ws.title = "Anchor总览"
ws.sheet_view.showGridLines = False
for c, wd in [(1, 3), (2, 24), (3, 14), (4, 14), (5, 14), (6, 14), (7, 14)]:
    ws.column_dimensions[get_column_letter(c)].width = wd

ws.merge_cells('B2:G2')
ws['B2'] = "⚓ Anchor 投资体系"
ws['B2'].font = Font(name=SRF, size=22, bold=True, color=T['primary'])
ws.row_dimensions[2].height = 36

ws.merge_cells('B3:G3')
sh_close = mkt.get('sh', {}).get('close', '')
sh_chg = mkt.get('sh', {}).get('change', '')
ws['B3'] = f"净值日期 {update_date} | 上证 {sh_close}({sh_chg}) | 总资产 ¥{total_assets:,.2f}"
ws['B3'].font = Font(name=SNS, size=10, italic=True, color='666666')

# KPI
r = 5
kpi_data = [
    ("总资产", f"¥{total_assets:,.0f}", ""),
    ("持有盈亏", f"{total_pnl:+,.0f}", ""),
    ("待结算", f"¥{pending_total:,.0f}", "冻结至7/25"),
    ("余额宝", f"¥{yuebao:,.0f}", ""),
]
for i, (lbl, val, sub) in enumerate(kpi_data):
    wc(ws, r, 2+i*2, lbl, Font(name=SNS, size=10, color='666666'), 'L')
    wc(ws, r+1, 2+i*2, val, Font(name=SRF, size=16, bold=True, color=T['primary']), 'L')
    if sub:
        wc(ws, r+2, 2+i*2, sub, Font(name=SNS, size=9, color='999999'), 'L')

# Layer summary
r = 10
layers = [
    ("🛡️ 压舱石层", bedrock),
    ("🚀 核心增长层", core_gr),
    ("🔥 卫星进攻层", satellite),
    ("⏳ 待结算", pending),
    ("💰 现金预备", [{'name': '余额宝', 'mv': yuebao, 'pnl': 0, 'day_pnl': 0}]),
]
for lname, lfunds in layers:
    lmv = sum(f.get('mv', 0) for f in lfunds)
    lpct = lmv / (total_assets or 1) * 100
    ws.merge_cells(f'B{r}:G{r}')
    ws[f'B{r}'] = f"{lname}  —  ¥{lmv:,.0f} ({lpct:.1f}%)"
    ws[f'B{r}'].font = Font(name=SRF, size=12, bold=True, color=T['primary'])
    ws.row_dimensions[r].height = 22
    r += 1
    if lfunds:
        hdr(ws, r, 2, ["名称", "市值", "持有盈亏", "累计盈亏", "日收益", "备注"])
        r += 1
        for f in lfunds:
            wc(ws, r, 2, f.get('name', '?')[:30], Font(name=SNS, size=11), 'L')
            wc(ws, r, 3, f.get('mv', 0), None, 'R', MNY)
            pnl = f.get('pnl', 0) or 0
            wc(ws, r, 4, pnl, Font(name=SNS, size=11, color=SEM['pos'] if pnl >= 0 else SEM['neg']), 'R', MNY)
            cumul = f.get('cumul', 0) or 0
            wc(ws, r, 5, cumul, Font(name=SNS, size=11, color=SEM['pos'] if cumul >= 0 else SEM['neg']), 'R', MNY)
            dp = f.get('day_pnl', 0) or 0
            wc(ws, r, 6, dp, Font(name=SNS, size=11, color=SEM['pos'] if dp >= 0 else SEM['neg']), 'R', MNY)
            wc(ws, r, 7, f.get('note', '')[:30], Font(name=SNS, size=9, color='888888'), 'L')
            ws.row_dimensions[r].height = 20
            r += 1
        frame(ws, r-len(lfunds)-1, r-1, 2, 7)
    r += 1


# ===== Sheet 2: 持仓明细 =====
ws2 = wb.create_sheet("持仓明细")
ws2.sheet_view.showGridLines = False
for c, wd in [(1, 3), (2, 28), (3, 12), (4, 12), (5, 12), (6, 12), (7, 12), (8, 20)]:
    ws2.column_dimensions[get_column_letter(c)].width = wd

ws2.merge_cells('B2:H2')
ws2['B2'] = f"全部持仓明细 — {update_date}"
ws2['B2'].font = Font(name=SRF, size=18, bold=True, color=T['primary'])
ws2.row_dimensions[2].height = 32

r = 4
all_funds = bedrock + core_gr + satellite + pending
all_funds.sort(key=lambda x: x.get('mv', 0), reverse=True)
hdr(ws2, r, 2, ["基金名称", "市值", "持有盈亏", "收益率", "累计盈亏", "日收益", "备注"])
r += 1
for f in all_funds:
    mv = f.get('mv', 0)
    pnl = f.get('pnl', 0) or 0
    cumul = f.get('cumul', 0) or 0
    dp = f.get('day_pnl', 0) or 0
    rate = pnl / (mv - pnl) if mv != pnl and mv > 0 else 0
    wc(ws2, r, 2, f.get('name', '?')[:35], Font(name=SNS, size=11), 'L')
    wc(ws2, r, 3, mv, None, 'R', MNY)
    wc(ws2, r, 4, pnl, Font(name=SNS, size=11, color=SEM['pos'] if pnl >= 0 else SEM['neg']), 'R', MNY)
    wc(ws2, r, 5, rate, Font(name=SNS, size=11, color=SEM['pos'] if rate >= 0 else SEM['neg']), 'R', PCT)
    wc(ws2, r, 6, cumul, Font(name=SNS, size=11, color=SEM['pos'] if cumul >= 0 else SEM['neg']), 'R', MNY)
    wc(ws2, r, 7, dp, Font(name=SNS, size=11, color=SEM['pos'] if dp >= 0 else SEM['neg']), 'R', MNY)
    wc(ws2, r, 8, f.get('note', '')[:25], Font(name=SNS, size=9, color='888888'), 'L')
    ws2.row_dimensions[r].height = 20
    r += 1
frame(ws2, 4, r-1, 2, 8)

# ===== Sheet 3: 交易记录 =====
ws3 = wb.create_sheet("交易记录")
ws3.sheet_view.showGridLines = False
for c, wd in [(1, 3), (2, 14), (3, 28), (4, 14), (5, 12), (6, 30)]:
    ws3.column_dimensions[get_column_letter(c)].width = wd

txs = D.get('transactions', [])
ws3.merge_cells('B2:F2')
ws3['B2'] = f"交易记录 — 共{len(txs)}条"
ws3['B2'].font = Font(name=SRF, size=18, bold=True, color=T['primary'])
ws3.row_dimensions[2].height = 32

r = 4
hdr(ws3, r, 2, ["日期", "基金名称", "操作", "金额", "备注"])
r += 1
for tx in reversed(txs):
    wc(ws3, r, 2, tx.get('date', ''), Font(name=SNS, size=10), 'C')
    wc(ws3, r, 3, tx.get('name', '')[:35], Font(name=SNS, size=10), 'L')
    op = tx.get('op', '')
    c = SEM['neg'] if '清仓' in str(op) or '止损' in str(op) else SEM['pos']
    wc(ws3, r, 4, op, Font(name=SNS, size=10, color=c), 'C')
    wc(ws3, r, 5, tx.get('amount', 0), None, 'R', MNY)
    wc(ws3, r, 6, tx.get('note', '')[:40], Font(name=SNS, size=9, color='888888'), 'L')
    ws3.row_dimensions[r].height = 20
    r += 1
if txs:
    frame(ws3, 4, r-1, 2, 6)

# ===== Save =====
wb.save(OUT)
print(f"Anchor Excel saved — {len(all_funds)} funds, {len(txs)} transactions")
