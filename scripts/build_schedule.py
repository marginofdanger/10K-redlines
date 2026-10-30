"""Record each tracked company's recent SEC filings and its next expected one, for the landing page.

  python scripts/build_schedule.py            # writes automation/schedule.json

The landing page compares these filings with the ledger (automation/tracked.json, stamped in at
deploy) to show which filings are on EDGAR but not on the site yet, and when the next one is due.
The expected date is the filing date of the same period a year earlier, 364 days on (same weekday).
SEC_USER_AGENT must be set, as for check_new_filings.py; it is never written to the file.
"""
import json, os, sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_new_filings as cnf  # noqa: E402

OUT = os.path.join(cnf.ROOT, "automation", "schedule.json")
KEEP = 8  # recent filings per company: enough to find the latest covered 10-K and 10-Q


def next_filing(fs, label):
    """The filing that followed the same period last year, moved forward a year."""
    chron = fs[::-1]
    latest = date.fromisoformat(fs[0]["reportDate"])
    ly = next((i for i, f in enumerate(chron)
               if abs((date.fromisoformat(f["reportDate"]) - (latest - timedelta(days=365))).days) <= 20), None)
    if ly is None or ly + 1 >= len(chron):
        return None
    nxt = chron[ly + 1]
    last = date.fromisoformat(nxt["reportDate"])
    if last.day >= 28:  # month-end period: the same month end a year on
        period = date(last.year + 1 + (last.month == 12), last.month % 12 + 1, 1) - timedelta(days=1)
    else:  # 52/53-week filer: same weekday a year on
        period = last + timedelta(days=364)
    expected = date.fromisoformat(nxt["filingDate"]) + timedelta(days=364)
    return {"form": nxt["form"], "label": label(nxt["form"], period.isoformat()),
            "period": period.isoformat(), "expected": expected.isoformat()}


def main():
    out, errors = {}, []
    ledger = cnf.load_ledger()["companies"]
    for t, co in ledger.items():
        forms = {co["annual_form"]} | ({"10-Q"} if co.get("quarterly") else set())
        try:
            fs = cnf.filings(co["cik"], forms)
        except Exception as e:  # keep the last known entry for this company
            errors.append(f"{t}: {e}")
            continue
        annual = [f for f in fs if f["form"] == co["annual_form"]]
        if not annual:
            errors.append(f"{t}: no {co['annual_form']} in recent filings")
            continue

        def label(form, period):
            if form == "10-Q":
                fye = next((x["reportDate"] for x in annual if x["reportDate"] < period), annual[-1]["reportDate"])
                return cnf.fiscal_label(period, fye, False)
            return cnf.fiscal_label(period, None, True)

        out[t] = {
            "fye_month": cnf.month_end(annual[0]["reportDate"])[1],
            "filings": [{"form": f["form"], "label": label(f["form"], f["reportDate"]), "period": f["reportDate"],
                         "filed": f["filingDate"],
                         "index": (f"https://www.sec.gov/Archives/edgar/data/{int(co['cik'])}/"
                                   f"{f['accessionNumber'].replace('-', '')}/{f['accessionNumber']}-index.htm")}
                        for f in fs[:KEEP]],
            "next": next_filing(fs, label),
        }
    old = json.load(open(OUT)).get("companies", {}) if os.path.exists(OUT) else {}
    for t in ledger:  # a company SEC didn't answer for keeps its last entry
        if t not in out and t in old:
            out[t] = old[t]
    json.dump({"checked": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "companies": out},
              open(OUT, "w"), indent=1)
    for t, c in out.items():
        n = c["next"]
        print(f"{t:<5} latest {c['filings'][0]['form']} {c['filings'][0]['label']} filed {c['filings'][0]['filed']}"
              + (f"; next {n['form']} {n['label']} ~{n['expected']}" if n else ""))
    for e in errors:
        print("error:", e)


if __name__ == "__main__":
    main()
