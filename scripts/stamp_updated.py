"""Fill index.html's UPDATED map with each company's latest covered 10-Q filing date.

Reads automation/tracked.json (quarterly_filed, recorded by check_new_filings.py mark). Run at deploy:
  python scripts/stamp_updated.py
"""
import json, re

with open("automation/tracked.json", encoding="utf-8") as f:
    ledger = json.load(f)["companies"]
dates = {t: c["quarterly_filed"] for t, c in ledger.items() if c.get("quarterly_filed")}

with open("index.html", encoding="utf-8") as f:
    page = f.read()
page, n = re.subn(r"const UPDATED = \{.*?\};", "const UPDATED = " + json.dumps(dates) + ";", page)
if n != 1:
    raise SystemExit("index.html has no `const UPDATED = {...};` line to fill")
with open("index.html", "w", encoding="utf-8") as f:
    f.write(page)
print(json.dumps(dates, indent=1))
