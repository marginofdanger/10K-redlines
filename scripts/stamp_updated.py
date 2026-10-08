"""Fill index.html's UPDATED map with each company's last dashboard change, from git history.

Run at deploy (needs full history: actions/checkout with fetch-depth: 0):
  python scripts/stamp_updated.py
"""
import json, re, subprocess

with open("index.html", encoding="utf-8") as f:
    page = f.read()

updated = {}
for ticker, url in re.findall(r"\{ticker:'(\w+)'.*?url:'([^']+)'", page):
    date = subprocess.run(["git", "log", "-1", "--format=%cs", "--", url + "index.html", url + "10q/index.html"],
                          capture_output=True, text=True, check=True).stdout.strip()
    if date:
        updated[ticker] = date

page, n = re.subn(r"const UPDATED = \{.*?\};", "const UPDATED = " + json.dumps(updated) + ";", page)
if n != 1:
    raise SystemExit("index.html has no `const UPDATED = {...};` line to fill")
with open("index.html", "w", encoding="utf-8") as f:
    f.write(page)
print(json.dumps(updated, indent=1))
