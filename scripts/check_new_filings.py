"""Find SEC filings that the dashboards don't cover yet, and record them once they do.

  python scripts/check_new_filings.py pending              # human-readable work list
  python scripts/check_new_filings.py pending --json       # same, machine-readable
  python scripts/check_new_filings.py fetch URL DEST       # download a filing document
  python scripts/check_new_filings.py mark TICKER annual|quarterly REPORT_DATE [--dashboard PATH]

State lives in automation/tracked.json. SEC_USER_AGENT must be set to "<name> <contact email>"
(SEC fair-access policy; www.sec.gov refuses requests without it).
"""
import argparse, json, os, sys, time, urllib.error, urllib.request
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "automation", "tracked.json")
# www.sec.gov rejects agents without a contact email; both hosts reject agents containing a URL.
# The email comes from the environment so it stays out of this public repo.
UA = os.environ.get("SEC_USER_AGENT", "")
if "@" not in UA:
    sys.exit('Set SEC_USER_AGENT to "<name> <contact email>"; SEC refuses downloads without one.')
SCANNER_QUARTERS = 8

_last_request = 0.0

def http_get(url):
    global _last_request
    wait = 0.2 - (time.time() - _last_request)  # stay far under SEC's 10 req/s limit
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                _last_request = time.time()
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503) or attempt == 3:
                raise
        except urllib.error.URLError:
            if attempt == 3:
                raise
        time.sleep(2 ** (attempt + 1))

def load_ledger():
    with open(LEDGER, encoding="utf-8") as f:
        return json.load(f)

def save_ledger(data):
    with open(LEDGER, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

def rows(block):
    keys = ["accessionNumber", "filingDate", "reportDate", "acceptanceDateTime", "form", "primaryDocument"]
    return [dict(zip(keys, vals)) for vals in zip(*(block[k] for k in keys))]

def filings(cik, forms, need_older=0):
    """Original (non-amended) filings of the given forms, newest first."""
    sub = json.loads(http_get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    out = [r for r in rows(sub["filings"]["recent"]) if r["form"] in forms]
    for page in sub["filings"].get("files", []):
        if len(out) >= need_older:
            break
        older = json.loads(http_get(f"https://data.sec.gov/submissions/{page['name']}"))
        out += [r for r in rows(older) if r["form"] in forms]
    for r in out:
        r["url"] = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{r['accessionNumber'].replace('-', '')}/{r['primaryDocument']}")
    return sorted(out, key=lambda r: r["acceptanceDateTime"], reverse=True)

def item(kind, ticker, co, f, dashboard):
    return {"kind": kind, "ticker": ticker, "form": f["form"], "accession": f["accessionNumber"],
            "filing_date": f["filingDate"], "report_date": f["reportDate"], "url": f["url"],
            "dashboard": dashboard, "cik": co["cik"]}

def pending():
    work, errors = [], []
    for ticker, co in load_ledger()["companies"].items():
        try:
            forms = {co["annual_form"]} | ({"10-Q"} if co["quarterly"] else set())
            build = co["quarterly"] and not co["quarterly_dashboard"]
            fs = filings(co["cik"], forms, need_older=SCANNER_QUARTERS + 3 if build else 0)
        except Exception as e:
            errors.append(f"{ticker}: {e}")
            continue
        for f in fs:
            if f["form"] == co["annual_form"] and f["reportDate"] > co["annual_covered_through"]:
                work.append(item("annual", ticker, co, f, co["annual_dashboard"]))
            elif (f["form"] == "10-Q" and co["quarterly_dashboard"]
                  and f["reportDate"] > co["quarterly_covered_through"]):
                work.append(item("quarterly", ticker, co, f, co["quarterly_dashboard"]))
        if build:
            qs = [f for f in fs if f["form"] == "10-Q"][:SCANNER_QUARTERS]
            if qs:
                w = item("build_scanner", ticker, co, qs[0], co["annual_dashboard"] + "10q/")
                w["filings"] = [item("quarterly", ticker, co, f, None) for f in reversed(qs)]
                oldest = date.fromisoformat(qs[-1]["reportDate"]) - timedelta(days=366)
                w["annual_baselines"] = [item("annual", ticker, co, f, None)
                                         for f in reversed(fs) if f["form"] == co["annual_form"]
                                         and date.fromisoformat(f["reportDate"]) > oldest]
                work.append(w)
    # Updates before scanner builds; within each, oldest filing first so transitions chain in order.
    work.sort(key=lambda w: (w["kind"] == "build_scanner", w["filing_date"], w["ticker"]))
    return work, errors

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("pending"); p.add_argument("--json", action="store_true")
    p = sp.add_parser("fetch"); p.add_argument("url"); p.add_argument("dest")
    p = sp.add_parser("mark"); p.add_argument("ticker"); p.add_argument("which", choices=["annual", "quarterly"])
    p.add_argument("report_date"); p.add_argument("--dashboard")
    a = ap.parse_args()

    if a.cmd == "pending":
        work, errors = pending()
        if a.json:
            print(json.dumps({"pending": work, "errors": errors}, indent=2))
        else:
            for w in work:
                extra = f" ({len(w['filings'])} 10-Qs)" if w["kind"] == "build_scanner" else ""
                print(f"{w['kind']:<14}{w['ticker']:<6}{w['form']:<6}period {w['report_date']}  "
                      f"filed {w['filing_date']}  {w['accession']}{extra}")
            for e in errors:
                print(f"ERROR {e}", file=sys.stderr)
            if not work and not errors:
                print("Nothing pending.")
        sys.exit(1 if errors and not work else 0)

    if a.cmd == "fetch":
        os.makedirs(os.path.dirname(os.path.abspath(a.dest)), exist_ok=True)
        data = http_get(a.url)
        with open(a.dest, "wb") as f:
            f.write(data)
        print(f"{a.dest}: {len(data):,} bytes")

    if a.cmd == "mark":
        data = load_ledger()
        co = data["companies"][a.ticker]
        co[f"{a.which}_covered_through"] = a.report_date
        if a.dashboard:
            co[f"{a.which}_dashboard"] = a.dashboard
        save_ledger(data)
        print(f"{a.ticker} {a.which} covered through {a.report_date}")

if __name__ == "__main__":
    main()
