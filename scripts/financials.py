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
    ("Dividends paid", ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"], False),
    ("Stock-based comp", ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"], False),
    ("Pre-tax income", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
                        "ProfitLossBeforeTax"], False),
    ("Income tax", ["IncomeTaxExpenseBenefit", "IncomeTaxExpenseContinuingOperations"], False),
    ("Interest expense", ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"], False),
    ("Goodwill impairment", ["GoodwillImpairmentLoss"], False),
    ("Diluted shares", ["WeightedAverageNumberOfDilutedSharesOutstanding"], False),
    ("Cash & equivalents", ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents"], True),
    ("Receivables", ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent", "TradeAndOtherCurrentReceivables"], True),
    ("Inventory", ["InventoryNet", "Inventories"], True),
    ("Deferred revenue", ["ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"], True),
    ("Long-term debt", ["LongTermDebtNoncurrent", "LongTermDebt", "NoncurrentPortionOfNoncurrentBondsIssued"], True),
    ("Tax valuation allowance", ["DeferredTaxAssetsValuationAllowance"], True),
    # filers tag different things here (META: leases not yet commenced); confirm against the commitments note
    ("Purchase obligations (as tagged)", ["PurchaseObligation", "UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount"], True),
    ("Guarantees (max exposure)", ["GuaranteeObligationsMaximumExposure"], True),
]


def derived(rows, ends, quarterly):
    """Ratios an analyst checks first. Each is computed only when its inputs share a basis
    (a year-to-date 10-Q cash flow is never divided by a three-month figure)."""
    def v(label, e):
        x = rows[label][1].get(e)
        return (x[0], x[2]) if x else (None, None)

    out = {}
    def put(name, e, val):
        if val is not None:
            out.setdefault(name, {})[e] = val
    for e in ends:
        ocf, n1 = v("Operating cash flow", e); capex, n2 = v("Capex", e)
        ni, n3 = v("Net income", e); sbc, n4 = v("Stock-based comp", e)
        rev, n5 = v("Revenue", e); ar, _ = v("Receivables", e)
        pre, n6 = v("Pre-tax income", e); tax, n7 = v("Income tax", e)
        if ocf is not None and capex is not None and n1 == n2:
            fcf = ocf - capex
            put("Free cash flow" + (" (ytd)" if n1 else ""), e, ("money", fcf))
            if ni and n1 == n3:
                put("FCF / net income", e, ("ratio", fcf / ni))
        if sbc is not None and ocf and n4 == n1:
            put("SBC / operating cash flow", e, ("ratio", sbc / ocf))
        if ar is not None and rev and not n5:
            put("Days sales outstanding", e, ("days", ar / rev * (91 if quarterly else 365)))
        if tax is not None and pre and n6 == n7:
            put("Effective tax rate", e, ("ratio", tax / pre))
    sh = rows["Diluted shares"][1]
    for p, e in zip(ends, ends[1:]):
        if p in sh and e in sh and sh[p][0]:
            put("Diluted shares change", e, ("ratio", sh[e][0] / sh[p][0] - 1))
    return out


def fmt_derived(kind, x):
    return {"money": lambda: fmt(x, "USD"), "ratio": lambda: f"{x * 100:.1f}%", "days": lambda: f"{x:.0f}d"}[kind]()


def days(r):
    return (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days if "start" in r else 0


def series(facts, concepts, instant, quarterly):
    """{period end: (value, unit, note)} merged across concept variants in priority order.
    10-Qs report cash-flow items year-to-date only; a three-month figure is derived as this
    year-to-date minus the prior quarter's year-to-date (same fiscal-year start). A figure that
    can't be derived keeps the year-to-date value with note 'YTD'."""
    out, used = {}, []
    for taxonomy in ("us-gaap", "ifrs-full"):
        for c in concepts:
            node = facts.get(taxonomy, {}).get(c)
            if not node:
                continue
            got, spans = {}, {}
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
                        if 80 <= d < 300 and not annual_form:
                            spans[(r["start"], r["end"])] = r["val"]
                        if 80 <= d <= 100:
                            got[r["end"]] = (r["val"], unit, "")
                        elif not annual_form and 100 < d < 300:
                            prev = got.get(r["end"])
                            if not prev or (prev[2] == "YTD" and d > prev[3]):
                                got[r["end"]] = (r["val"], unit, "YTD", d, r["start"])
            for end, v in list(got.items()):
                if v[2] == "YTD":
                    start = v[4]
                    earlier = [e for (st, e) in spans if st == start and e < end]
                    if earlier:
                        got[end] = (v[0] - spans[(start, max(earlier))], v[1], "")
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
        result[view] = {"period_ends": flow_ends, "derived": derived(rows, flow_ends, view == "quarterly"),
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
        print(f"{'':<26}" + "".join(f"{e:>15}" for e in v["period_ends"]))
        for label, r in v["rows"].items():
            cells = [fmt(*r["values"][e]) if e in r["values"] else "-" for e in v["period_ends"]]
            print(f"{label:<26}" + "".join(f"{c:>15}" for c in cells) + f"   [{r['concept'] or 'not tagged'}]")
        print(f"\n{view} derived (! = moved more than 20% vs the prior column: find the sentence that explains it)")
        for name, vals in v["derived"].items():
            cells, prev = [], None
            for e in v["period_ends"]:
                if e not in vals:
                    cells.append("-"); continue
                kind, x = vals[e]
                flag = "" if "(ytd)" in name else "!" if prev is not None and prev != 0 and abs(x / prev - 1) > 0.2 and kind != "ratio" or \
                    (kind == "ratio" and prev is not None and abs(x - prev) > 0.05 and name != "Diluted shares change") else ""
                cells.append(fmt_derived(kind, x) + flag)
                prev = x
            print(f"{name:<26}" + "".join(f"{c:>15}" for c in cells))


if __name__ == "__main__":
    main()
