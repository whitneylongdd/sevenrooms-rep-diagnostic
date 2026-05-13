"""
Sevenrooms Pre-Sales Dash — Data Refresh Script
================================================
Run this to update embedded rep data in team.html.

Sources:
  - "Raw Data - Opps CW"      (Sheet: 1RGwcqbWrYk1WUVphvPJ7EnDw4TxBLpV1lwoa-EqbHbU)
  - "Raw Data - Opps Created" (same sheet)
  - "2025 - YTD" ramp tab     (Sheet: 1N5_gpIXPsQVrHB529OhlIqqmSdTQif9-mDcKvYrNbvs)

T90 CVR — matches spreadsheet formula on 'rep productivity'!row 27 exactly:
  Denominator = COUNTUNIQUEIFS(OppID, rep=X, SQO_date >= EOMONTH-90, SQO_date <= EOMONTH)
  Numerator   = same filters + Won? = "1"
  Both come from Raw Data - Opps Created only (col B=OppID, K=SQO date, L=rep, AE=Won?)
  This guarantees numerator is always a strict subset of denominator (no >100% possible).

EOMONTH is computed dynamically as the last day of the current month.
To run: python3 scripts/refresh_data.py  (from repo root, requires gws on PATH)
"""

import sys, json, re, subprocess, os
from collections import defaultdict
from datetime import datetime, date
import calendar

CW_SHEET_ID   = '1RGwcqbWrYk1WUVphvPJ7EnDw4TxBLpV1lwoa-EqbHbU'
RAMP_SHEET_ID = '1N5_gpIXPsQVrHB529OhlIqqmSdTQif9-mDcKvYrNbvs'
HTML_PATH     = os.path.join(os.path.dirname(__file__), '..', 'team.html')

# T90 window: EOMONTH of the last COMPLETED month (matches spreadsheet which uses
# a fixed monthly column — current month is incomplete so we anchor to prior EOMONTH)
today = date.today()
if today.month == 1:
    prev_year, prev_month = today.year - 1, 12
else:
    prev_year, prev_month = today.year, today.month - 1
eom = date(prev_year, prev_month, calendar.monthrange(prev_year, prev_month)[1])
t90_start = eom - __import__('datetime').timedelta(days=90)
print(f"T90 window: {t90_start} → {eom}  (EOMONTH={eom}, EOMONTH-90={t90_start})")

MONTHS_2026 = {'1','2','3','4','5'}
MO_KEY = {'1':'jan','2':'feb','3':'mar','4':'apr','5':'may'}

def fetch_sheet(sheet_id, range_name):
    result = subprocess.run(
        ['gws','sheets','spreadsheets','values','get',
         '--params', json.dumps({'spreadsheetId': sheet_id, 'range': range_name})],
        capture_output=True, text=True)
    out = result.stdout.strip()
    if os.path.exists(out):
        with open(out) as f: return json.load(f)
    return json.loads(out)

def parse_date(s):
    """Parse M/D/YYYY date string, return date or None."""
    try:
        return datetime.strptime(s.strip(), '%m/%d/%Y').date()
    except:
        return None

# ── Pull CW data (for cw2026, cwNN, cwExp, mrr, facecard, monthly) ───────────
print("Pulling Raw Data - Opps CW...")
cw_rows = fetch_sheet(CW_SHEET_ID, 'Raw Data - Opps CW').get('values', [])
print(f"  {len(cw_rows)-1} rows")

# Use sets of venue IDs to count unique venues per rep (matches spreadsheet COUNTUNIQUEIFS)
rep_venues = defaultdict(lambda: {
    'all':set(),'nn':set(),'exp':set(),
    'jan':set(),'feb':set(),'mar':set(),'apr':set(),'may':set()
})
rep = defaultdict(lambda: {
    'cw2026':0,'cwNN':0,'cwExp':0,'mrr2026':0.0,
    'ace':0,'jack':0,'king':0,
    'jan':0,'feb':0,'mar':0,'apr':0,'may':0
})

for row in cw_rows[1:]:
    if len(row) < 16: continue
    close_date = row[5].strip()
    rep_name   = row[15].strip()
    opp_type   = row[13].strip() if len(row) > 13 else ''
    facecard   = row[42].strip() if len(row) > 42 else ''
    mrr_raw    = row[46].strip() if len(row) > 46 else ''

    if not close_date or not rep_name: continue
    parts = close_date.split('/')
    if len(parts) != 3 or parts[2] != '2026': continue
    mo = parts[0]
    if mo not in MONTHS_2026: continue

    venue_id = row[9].strip() if len(row) > 9 else ''
    v = rep_venues[rep_name]
    v['all'].add(venue_id)
    v[MO_KEY[mo]].add(venue_id)

    ot = opp_type.lower()
    if 'net new' in ot: v['nn'].add(venue_id)
    elif 'expansion' in ot or 'upsell' in ot: v['exp'].add(venue_id)

    d = rep[rep_name]
    fc = facecard.lower()
    if fc == 'ace': d['ace'] += 1
    elif fc == 'jack': d['jack'] += 1
    elif fc == 'king': d['king'] += 1

    mrr_clean = mrr_raw.replace('$','').replace(',','').strip()
    try: d['mrr2026'] += float(mrr_clean)
    except: pass

# Collapse venue sets to counts
for name, v in rep_venues.items():
    d = rep[name]
    d['cw2026'] = len(v['all'])
    d['cwNN']   = len(v['nn'])
    d['cwExp']  = len(v['exp'])
    d['jan']    = len(v['jan'])
    d['feb']    = len(v['feb'])
    d['mar']    = len(v['mar'])
    d['apr']    = len(v['apr'])
    d['may']    = len(v['may'])
print(f"  Reps with CW: {len(rep)},  total cw2026: {sum(v['cw2026'] for v in rep.values()):,}")

# ── Team-level unique venue counts per month (for TEAM_MONTHLY constant) ──────
# Uses col J (venue ID) + col AJ (Opp CW Month) — matches spreadsheet COUNTUNIQUEIFS
team_venues = defaultdict(set)
CW_MONTH_KEY = {'1/1/2026':'jan','2/1/2026':'feb','3/1/2026':'mar','4/1/2026':'apr','5/1/2026':'may'}
for row in cw_rows[1:]:
    venue_id = row[9].strip()  if len(row) > 9  else ''
    cw_month = row[35].strip() if len(row) > 35 else ''
    if venue_id and cw_month in CW_MONTH_KEY:
        team_venues[CW_MONTH_KEY[cw_month]].add(venue_id)
team_monthly = {mo: len(team_venues.get(mo, set())) for mo in ['jan','feb','mar','apr','may']}
print(f"  Team monthly unique venues: {team_monthly}")

# ── Pull Opps Created (for sqo2026, sqoT90, cwT90 — all from same tab) ───────
# Col B (idx 1)  = Opportunity ID
# Col K (idx 10) = SQO Date (M/D/YYYY exact date)
# Col L (idx 11) = Sales Rep Name
# Col X (idx 23) = Month of Opp SQO (M/1/YYYY — used for sqo2026 YTD count)
# Col AE (idx 30) = Won? ("1" = closed-won)
print("Pulling Raw Data - Opps Created...")
sqo_rows = fetch_sheet(CW_SHEET_ID, 'Raw Data - Opps Created').get('values', [])
print(f"  {len(sqo_rows)-1} rows")

rep_sqo    = defaultdict(int)          # sqo2026: YTD SQO count
rep_sqoT90 = defaultdict(set)          # unique opp IDs in T90 window (denominator)
rep_cwT90  = defaultdict(set)          # unique won opp IDs in T90 window (numerator)

VALID_SQO_MONTHS = {f'{m}/1/2026' for m in MONTHS_2026}

for row in sqo_rows[1:]:
    if len(row) < 24: continue
    opp_id   = row[1].strip()  if len(row) > 1  else ''
    sqo_date = row[10].strip() if len(row) > 10 else ''
    rep_name = row[11].strip() if len(row) > 11 else ''
    sqo_mo   = row[23].strip() if len(row) > 23 else ''
    won      = row[30].strip() if len(row) > 30 else '0'

    if not rep_name or not opp_id: continue

    # sqo2026: YTD count by month bucket (same as before)
    if sqo_mo in VALID_SQO_MONTHS:
        rep_sqo[rep_name] += 1

    # T90 CVR: use exact SQO date vs. T90 window (matches spreadsheet EOMONTH logic)
    d = parse_date(sqo_date)
    if d and t90_start <= d <= eom:
        rep_sqoT90[rep_name].add(opp_id)        # denominator
        if won == '1':
            rep_cwT90[rep_name].add(opp_id)     # numerator (always subset of denom)

print(f"  Total sqo2026:  {sum(rep_sqo.values()):,}")
print(f"  Total sqoT90:   {sum(len(v) for v in rep_sqoT90.values()):,}")
print(f"  Total cwT90:    {sum(len(v) for v in rep_cwT90.values()):,}")

# ── Pull Ramp data ────────────────────────────────────────────────────────────
print("Pulling 2025-YTD ramp tab...")
ramp_rows = fetch_sheet(RAMP_SHEET_ID, '2025 - YTD').get('values', [])
rep_ramp = {}
for row in ramp_rows[1:]:
    if len(row) < 22: continue
    name = row[0].strip(); val = row[21].strip()
    if not name or not val: continue
    try: rep_ramp[name] = float(val)
    except: pass
print(f"  Reps with ramp: {len(rep_ramp)}")

# ── Patch HTML ────────────────────────────────────────────────────────────────
print(f"Patching {HTML_PATH}...")
with open(HTML_PATH, 'r') as f:
    html = f.read()

def patch_rep(m):
    entry = m.group(0)
    name_match = re.search(r'name:"([^"]+)"', entry)
    if not name_match: return entry
    name = name_match.group(1)

    cw = rep.get(name, {})
    fields = {
        'cw2026':  cw.get('cw2026', 0),
        'cwNN':    cw.get('cwNN', 0),
        'cwExp':   cw.get('cwExp', 0),
        'mrr2026': int(round(cw.get('mrr2026', 0))),
        'sqo2026': rep_sqo.get(name, 0),
        'sqoT90':  len(rep_sqoT90.get(name, set())),
        'cwT90':   len(rep_cwT90.get(name, set())),
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
        entry = re.sub(rf'\b{field}:\d+', f'{field}:{val}', entry)

    ramp_val = rep_ramp.get(name)
    if ramp_val is not None:
        entry = re.sub(r'ramp:[0-9.]+', f'ramp:{ramp_val}', entry)

    return entry

count = [0]
def counted_patch(m):
    count[0] += 1
    return patch_rep(m)

html = re.sub(r'\{id:"[^"]+",name:"[^"]+"[^{}]*\}', counted_patch, html)
print(f"  Patched {count[0]} rep objects")

# Patch TEAM_MONTHLY constant
import json as _json
tm_new = 'const TEAM_MONTHLY=' + _json.dumps(team_monthly).replace(' ','') + ';'
html = re.sub(r'const TEAM_MONTHLY=\{[^}]+\};', tm_new, html)
print(f'  TEAM_MONTHLY: {team_monthly}')

with open(HTML_PATH, 'w') as f:
    f.write(html)

# Remove the Math.min(100,...) cap since numerator is now always ≤ denominator
print("Done. Removing 100% cap from CVR formula (no longer needed)...")
with open(HTML_PATH, 'r') as f:
    html = f.read()
old = 'r.cvr=r.sqoT90>0?Math.min(100,parseFloat((r.cwT90/r.sqoT90*100).toFixed(1))):null;'
new = 'r.cvr=r.sqoT90>0?parseFloat((r.cwT90/r.sqoT90*100).toFixed(1)):null;'
html = html.replace(old, new)
with open(HTML_PATH, 'w') as f:
    f.write(html)

# Write last-updated timestamp into the dash
from datetime import datetime, timezone
ts = datetime.now(timezone.utc).strftime('%-m/%-d/%Y at %-I:%M %p UTC')
with open(HTML_PATH) as f:
    html = f.read()
html = re.sub(r'Last updated: [^<"]+', f'Last updated: {ts}', html)
with open(HTML_PATH, 'w') as f:
    f.write(html)
print(f"Timestamp written: {ts}")
print("Done. Commit: git add team.html scripts/refresh_data.py && git commit -m 'Data refresh YYYY-MM-DD'")
