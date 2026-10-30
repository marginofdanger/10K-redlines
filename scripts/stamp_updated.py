"""Fill index.html's LEDGER and SCHEDULE data at deploy.

LEDGER comes from automation/tracked.json (what the dashboards cover, recorded by
check_new_filings.py mark); SCHEDULE from automation/schedule.json (recent EDGAR filings and the
next expected one, written by build_schedule.py). The landing page compares the two. Run at deploy:
  python scripts/stamp_updated.py
"""
import json, os, re

KEYS = ["annual_form", "annual_covered_through", "annual_filed",
        "quarterly", "quarterly_covered_through", "quarterly_filed"]

with open("automation/tracked.json", encoding="utf-8") as f:
    ledger = {t: {k: c.get(k) for k in KEYS} for t, c in json.load(f)["companies"].items()}
schedule = {}
if os.path.exists("automation/schedule.json"):
    with open("automation/schedule.json", encoding="utf-8") as f:
        schedule = json.load(f)

with open("index.html", encoding="utf-8") as f:
    page = f.read()
for name, value in (("LEDGER", ledger), ("SCHEDULE", schedule)):
    page, n = re.subn(r"const %s = \{.*?\};" % name, lambda m: f"const {name} = {json.dumps(value)};", page, flags=re.S)
    if n != 1:
        raise SystemExit(f"index.html has no `const {name} = {{...}};` line to fill")
with open("index.html", "w", encoding="utf-8") as f:
    f.write(page)
print(f"stamped {len(ledger)} companies; EDGAR checked {schedule.get('checked', 'never')}")
