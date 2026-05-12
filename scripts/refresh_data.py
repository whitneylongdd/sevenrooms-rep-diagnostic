"""
Sevenrooms Pre-Sales Dash — Data Refresh Script
================================================
Run this whenever you want to update the embedded rep data in team.html.

Reads from two Google Sheet tabs:
  - "Raw Data - Opps CW"      (Sheet: 1RGwcqbWrYk1WUVphvPJ7EnDw4TxBLpV1lwoa-EqbHbU)
  - "Raw Data - Opps Created" (same sheet)
  - "2025 - YTD" ramp tab     (Sheet: 1N5_gpIXPsQVrHB529OhlIqqmSdTQif9-mDcKvYrNbvs, col V)

What each field means:
  cw2026   = # deals closed in 2026 (all types), from Close Date col
  cw26sqo  = # 2026 closes whose SQO was also in 2026 (full-year cohort)
  cwT90    = # 2026 closes whose SQO was in the T90 window (numerator for T90 CVR)
  cwNN     = # Net New closes in 2026
  cwExp    = # Expansion closes in 2026
  mrr2026  = sum of MRR Final for 2026 closes
  sqo2026  = # SQOs created in 2026 YTD (shown as "SQOs" in sort)
  sqoT90   = # SQOs created in the T90 window (denominator for T90 CVR)
  ace/jack/king = facecard counts for 2026 closes
  janCW..mayCW  = monthly close counts by Close Date

T90 CVR definition (Brittany Brodlie):
  Denominator = SQOs created in the 90-day window ending at EOM
  Numerator   = CW deals that came FROM those same SQOs (cohort must match)
  Example: April → Feb 1–Apr 30. Current (May) → Mar 1–May 31.
  T90_MONTHS below = months in the current T90 window. Update each month.

Usage (from repo root, requires gws CLI on PATH):
  python3 scripts/refresh_data.py

It will patch team.html in place. Commit the result.
"""

import sys, json, re, subprocess, os
from collections import defaultdict

CW_SHEET_ID   = '1RGwcqbWrYk1WUVphvPJ7EnDw4TxBLpV1lwoa-EqbHbU'
RAMP_SHEET_ID = '1N5_gpIXPsQVrHB529OhlIqqmSdTQif9-mDcKvYrNbvs'
HTML_PATH     = os.path.join(os.path.dirname(__file__), '..', 'team.html')

# ── Update these sets as new months open/close ────────────────
MONTHS_2026 = {'1', '2', '3', '4', '5'}   # Jan=1 … May=5
MO_KEY = {'1':'jan','2':'feb','3':'mar','4':'apr','5':'may'}

# T90 window: SQO months in the ~90 days ending at current EOM
# May 2026 EOM = May 31 → 90 days back = ~Mar 1 → T90 months = Mar, Apr, May
# Update this each month: Jun→ {4,5,6}, Jul→ {5,6,7}, etc.
T90_MONTHS = {'3', '4', '5'}   # Mar, Apr, May 2026

VALID_SQO_2026 = {f'{m}/1/2026' for m in MONTHS_2026}
VALID_SQO_T90  = {f'{m}/1/2026' for m in T90_MONTHS}

def fetch_sheet(sheet_id, range_name):
    result = subprocess.run(
        ['gws', 'sheets', 'spreadsheets', 'values', 'get',
         '--params', json.dumps({'spreadsheetId': sheet_id, 'range': range_name})],
        capture_output=True, text=True
    )
    out = result.stdout.strip()
    if os.path.exists(out):
        with open(out) as f:
            return json.load(f)
    return json.loads(out)

# ── Pull CW data ──────────────────────────────────────────────
print("Pulling Raw Data - Opps CW...")
cw_rows = fetch_sheet(CW_SHEET_ID, 'Raw Data - Opps CW').get('values', [])
print(f"  {len(cw_rows)-1} rows")

rep = defaultdict(lambda: {
    'cw2026':0,'cw26sqo':0,'cwT90':0,'cwNN':0,'cwExp':0,
    'mrr2026':0.0,'ace':0,'jack':0,'king':0,
    'jan':0,'feb':0,'mar':0,'apr':0,'may':0
})

for row in cw_rows[1:]:
    if len(row) < 16: continue
    close_date = row[5].strip()   # col 5:  Close Date M/D/YYYY
    rep_name   = row[15].strip()  # col 15: Sales Rep Name
    opp_type   = row[13].strip() if len(row) > 13 else ''
    sqo_mo_raw = row[34].strip() if len(row) > 34 else ''
    facecard   = row[42].strip() if len(row) > 42 else ''
    mrr_raw    = row[46].strip() if len(row) > 46 else ''

    if not close_date or not rep_name: continue
    parts = close_date.split('/')
    if len(parts) != 3 or parts[2] != '2026': continue
    mo = parts[0]
    if mo not in MONTHS_2026: continue

    d = rep[rep_name]
    d['cw2026'] += 1
    d[MO_KEY[mo]] += 1

    # Full-year cohort CVR numerator
    sqo_parts = sqo_mo_raw.split('/')
    if len(sqo_parts) == 3 and sqo_parts[2] == '2026':
        d['cw26sqo'] += 1
        # T90 CVR numerator: CW whose SQO is in the T90 window
        sqo_month_num = sqo_parts[0]
        if sqo_month_num in T90_MONTHS:
            d['cwT90'] += 1

    ot = opp_type.lower()
    if 'net new' in ot: d['cwNN'] += 1
    elif 'expansion' in ot or 'upsell' in ot: d['cwExp'] += 1

    fc = facecard.lower()
    if fc == 'ace': d['ace'] += 1
    elif fc == 'jack': d['jack'] += 1
    elif fc == 'king': d['king'] += 1

    mrr_clean = mrr_raw.replace('$','').replace(',','').strip()
    try: d['mrr2026'] += float(mrr_clean)
    except: pass

print(f"  Reps with CW: {len(rep)}")
print(f"  Total cw2026:  {sum(v['cw2026']  for v in rep.values()):,}")
print(f"  Total cwT90:   {sum(v['cwT90']   for v in rep.values()):,}")

# ── Pull SQO data ─────────────────────────────────────────────
print("Pulling Raw Data - Opps Created...")
sqo_rows = fetch_sheet(CW_SHEET_ID, 'Raw Data - Opps Created').get('values', [])
print(f"  {len(sqo_rows)-1} rows")

rep_sqo    = defaultdict(int)   # full-year 2026
rep_sqoT90 = defaultdict(int)   # T90 window

for row in sqo_rows[1:]:
    if len(row) < 24: continue
    rep_name = row[11].strip()   # col 11: Sales Rep Name
    sqo_mo   = row[23].strip()   # col 23: Month of Opp SQO
    if not rep_name: continue
    if sqo_mo in VALID_SQO_2026:
        rep_sqo[rep_name] += 1
    if sqo_mo in VALID_SQO_T90:
        rep_sqoT90[rep_name] += 1

print(f"  Reps with SQOs: {len(rep_sqo)}")
print(f"  Total sqo2026: {sum(rep_sqo.values()):,}")
print(f"  Total sqoT90:  {sum(rep_sqoT90.values()):,}")

# ── Pull Ramp data ────────────────────────────────────────────
print("Pulling 2025-YTD ramp tab (col V)...")
ramp_rows = fetch_sheet(RAMP_SHEET_ID, '2025 - YTD').get('values', [])
print(f"  {len(ramp_rows)-1} rows")

rep_ramp = {}
for row in ramp_rows[1:]:
    if len(row) < 22: continue
    name = row[0].strip()
    val  = row[21].strip()
    if not name or not val: continue
    try:
        rep_ramp[name] = float(val)
    except: pass

print(f"  Reps with ramp: {len(rep_ramp)}")

# ── Patch HTML ────────────────────────────────────────────────
print(f"Patching {HTML_PATH}...")
with open(HTML_PATH, 'r') as f:
    html = f.read()

def patch_rep(m):
    entry = m.group(0)
    name_match = re.search(r'name:"([^"]+)"', entry)
    if not name_match: return entry
    name = name_match.group(1)

    cw     = rep.get(name, {})
    sqo    = rep_sqo.get(name, 0)
    sqoT90 = rep_sqoT90.get(name, 0)

    fields = {
        'cw2026':  cw.get('cw2026', 0),
        'cw26sqo': cw.get('cw26sqo', 0),
        'cwT90':   cw.get('cwT90', 0),
        'cwNN':    cw.get('cwNN', 0),
        'cwExp':   cw.get('cwExp', 0),
        'mrr2026': int(round(cw.get('mrr2026', 0))),
        'sqo2026': sqo,
        'sqoT90':  sqoT90,
        'ace':     cw.get('ace', 0),
        'jack':    cw.get('jack', 0),
        'king':    cw.get('king', 0),
        'janCW':   cw.get('jan', 0),
        'febCW':   cw.get('feb', 0),
        'marCW':   cw.get('mar', 0),
        'aprCW':   cw.get('apr', 0),
        'mayCW':   cw.get('may', 0),
    }
    for field, val in fields.items():
        entry = re.sub(rf'{field}:\d+', f'{field}:{val}', entry)

    ramp_val = rep_ramp.get(name)
    if ramp_val is not None:
        entry = re.sub(r'ramp:[0-9.]+', f'ramp:{ramp_val}', entry)

    return entry

html = re.sub(r'\{id:"[^"]+",name:"[^"]+",.*?(?:sqoT90:\d+)\}', patch_rep, html, flags=re.DOTALL)

with open(HTML_PATH, 'w') as f:
    f.write(html)

print("Done. Review: git diff team.html")
print("Then: git add team.html scripts/refresh_data.py && git commit -m 'Data refresh YYYY-MM-DD'")
