"""Extract key sections from JPM 10-Q HTML filings.

JPM's 10-Q follows the integrated layout of its 10-K: MD&A comes first under
all-caps body headings, then the financial statements and notes, then Part II.
Part II Item 1A is a one-paragraph pointer to the 10-K risk factors, so it is not
extracted; the quarterly risk-factor list lives in Forward-Looking Statements
(inside mda_accounting_fls). Section names match companies/jpm/sections/ so
scripts/make_qoq_diffs.py can chain each quarter through the annual 10-K.

Auto-detects quarters from raw/jpm_10q_{quarter}.htm filenames.
"""
import re, os, glob
from bs4 import BeautifulSoup
import warnings
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

RAW_DIR = "raw"
OUT_DIR = "sections"
os.makedirs(OUT_DIR, exist_ok=True)

# (start heading regex, end heading regex), matched as whole lines.
MDA_SECTIONS = {
    "mda_overview": (r"EXECUTIVE OVERVIEW", r"BUSINESS SEGMENT (?:RESULTS|& CORPORATE RESULTS)"),
    "mda_segments": (r"BUSINESS SEGMENT (?:RESULTS|& CORPORATE RESULTS)", r"(?:ENTERPRISE-WIDE|FIRMWIDE) RISK MANAGEMENT"),
    "mda_capital_liquidity": (r"(?:ENTERPRISE-WIDE|FIRMWIDE) RISK MANAGEMENT", r"CREDIT AND INVESTMENT RISK MANAGEMENT"),
    "mda_credit": (r"CREDIT AND INVESTMENT RISK MANAGEMENT", r"MARKET RISK MANAGEMENT"),
    "mda_other_risk": (r"MARKET RISK MANAGEMENT", r"CRITICAL ACCOUNTING ESTIMATES USED BY THE FIRM"),
    "mda_accounting_fls": (r"CRITICAL ACCOUNTING ESTIMATES USED BY THE FIRM", r"Consolidated statements of income \(unaudited\)"),
}

def clean_html(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "img"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return "\n".join([l.strip() for l in text.split("\n") if l.strip()])

def line_span(text, start_re, end_re, after=0):
    """First whole-line match of start_re at/after `after`, to the next whole-line end_re."""
    m = re.compile(r"^" + start_re + r"$", re.M).search(text, after)
    if not m:
        return None, None
    e = re.compile(r"^" + end_re + r"$", re.M).search(text, m.end())
    return m.start(), (e.start() if e else None)

def extract(text):
    results = {}
    # Body headings start after the table of contents, at INTRODUCTION.
    anchor = re.search(r"^INTRODUCTION$", text, re.M)
    pos = anchor.end() if anchor else 0
    for name, (sre, ere) in MDA_SECTIONS.items():
        s, e = line_span(text, sre, ere, pos)
        results[name] = text[s:e].strip() if s is not None and e else ""
    # Litigation note: "Note NN –" line followed by "Litigation", to the next note.
    m = re.search(r"^Note\s+\d+\s+–\nLitigation$", text, re.M)
    results["legal_proceedings"] = ""
    if m:
        nxt = re.compile(r"^Note\s+\d+\s+–$", re.M).search(text, m.end())
        results["legal_proceedings"] = text[m.start():nxt.start() if nxt else m.start() + 150000].strip()
    return results

for filepath in sorted(glob.glob(os.path.join(RAW_DIR, "*_10q_*.htm"))):
    q = re.search(r"_10q_(.+)\.htm$", os.path.basename(filepath)).group(1)
    print(f"\n=== {q.upper()} ===")
    text = clean_html(filepath)
    print(f"  total: {len(text):,}")
    with open(os.path.join(OUT_DIR, f"{q}_full.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    for sn, st in extract(text).items():
        print(f"  {sn}: {len(st):,}" if st else f"  {sn}: NOT FOUND")
        with open(os.path.join(OUT_DIR, f"{q}_{sn}.txt"), "w", encoding="utf-8") as f:
            f.write(st)
print("\n=== Done ===")
