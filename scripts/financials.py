"""Reported figures from SEC XBRL company facts, for headline metrics and reference tables.

  python scripts/financials.py TICKER [--years 3] [--quarters 6] [--json]

Values are exactly as tagged in the filings (USD, or NT$ for TSM's IFRS 20-F).
Quarterly flow metrics are three-month values. Use these numbers in transition
headers and financial reference tables rather than re-reading them from prose.
"""
import argparse, json, os, sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_new_filings import http_get, load_ledger  # noqa: E402

METRICS = [  # label, candidate concepts (first one with data wins), instant?
    ("Revenue", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenue",
                 "RevenuesNetOfInterestExpense"], False),
    ("Operating income", ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"], False),
    ("Net income", ["NetIncomeLoss", "ProfitLossAttributableToOwnersOfParent", "ProfitLoss"], False),
    ("Diluted EPS", ["EarningsPerShareDiluted", "DilutedEarningsLossPerShare"], False),
    ("Operating cash flow", ["NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities"], False),
    ("Capex", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
               "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"], False),
    ("Buybacks", ["PaymentsForRepurchaseOfCommonStock"], False),
    ("Cash & equivalents", ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents"], True),
    ("Long-term debt", ["LongTermDebtNoncurrent", "LongTermDebt", "NoncurrentPortionOfNoncurrentBondsIssued"], True),
]


def days(r):
    return (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days if "start" in r else 0


def series(facts, concepts, instant, quarterly):
    """{period end: (value, unit, note)} merged across concept variants in priority order.
    Quarterly cash-flow items are only reported year-to-date in 10-Qs; those carry note 'YTD'."""
    out, used = {}, []
    for taxonomy in ("us-gaap", "ifrs-full"):
        for c in concepts:
            node = facts.get(taxonomy, {}).get(c)
            if not node:
                continue
            got = {}
            for unit, rows in node["units"].items():
                for r in rows:
                    if not r.get("form", "").startswith(("10-K", "10-Q", "20-F")):
                        continue
                    annual_form = r["form"].startswith(("10-K", "20-F"))
                    if instant:
                        if "start" in r or (not quarterly and not annual_form):
                            continue
                        got.setdefault(r["end"], (r["val"], unit, ""))
                    elif not quarterly:
                        if annual_form and 350 <= days(r) <= 380:
                            got.setdefault(r["end"], (r["val"], unit, ""))
                    else:
                        d = days(r)
                        if 80 <= d <= 100:
                            got[r["end"]] = (r["val"], unit, "")
                        elif not annual_form and 100 < d < 300:
                            prev = got.get(r["end"])
                            if not prev or (prev[2] == "YTD" and d > prev[3]):
                                got[r["end"]] = (r["val"], unit, "YTD", d)
            for k, v in got.items():
                out.setdefault(k, v[:3])
            if got:
                used.append(c)
    return "/".join(used), out


def fmt(v, unit, note=""):
    if "/shares" in unit:
        txt = f"{v:.2f}"
    else:
        a = abs(v)
        txt = f"{v / 1e9:,.2f}B" if a >= 1e9 else f"{v / 1e6:,.1f}M" if a >= 1e6 else f"{v:,.0f}"
    return txt + (" ytd" if note else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--quarters", type=int, default=6)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    co = load_ledger()["companies"][a.ticker.upper()]
    facts = json.loads(http_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{co['cik']}.json"))["facts"]
    result = {}
    for view, n in (("annual", a.years), ("quarterly", a.quarters)):
        if not n:
            continue
        rows = {label: series(facts, concepts, instant, view == "quarterly") for label, concepts, instant in METRICS}
        flow_ends = sorted({e for label, (_, s_) in rows.items() for e, v in s_.items()
                            if label in ("Revenue", "Net income") and not v[2]})[-n:]
        result[view] = {"period_ends": flow_ends,
                        "rows": {label: {"concept": c, "values": {e: s_[e] for e in flow_ends if e in s_}}
                                 for label, (c, s_) in rows.items()}}
    if a.json:
        print(json.dumps(result, indent=2))
        return
    units = {u for v in result.values() for r in v["rows"].values() for (_, u, _) in r["values"].values()}
    print(f"{a.ticker.upper()} reported figures (units: {', '.join(sorted(units))}; 'ytd' = year-to-date, "
          f"the only basis the 10-Q reports)")
    for view, v in result.items():
        print(f"\n{view} (period end)")
        print(f"{'':<22}" + "".join(f"{e:>15}" for e in v["period_ends"]))
        for label, r in v["rows"].items():
            cells = [fmt(*r["values"][e]) if e in r["values"] else "-" for e in v["period_ends"]]
            print(f"{label:<22}" + "".join(f"{c:>15}" for c in cells) + f"   [{r['concept'] or 'not tagged'}]")


if __name__ == "__main__":
    main()
