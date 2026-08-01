"""Extract key sections from Apollo 10-Q HTML filings.

APO-specific: the generic regex extractor fails on Apollo because the MD&A
contains mixed-case cross-references ("See Part I—Item 3...") that match the
generic end patterns. Apollo's real item headings are UPPERCASE and
line-anchored (e.g. "ITEM 2.    MANAGEMENT'S DISCUSSION..."), so this version
parses line-by-line, case-sensitively. Part II Item 1A is located after the
"ITEM 1.    LEGAL PROCEEDINGS" heading to avoid Apollo's quirky Part I
"ITEM 1A. UNAUDITED SUPPLEMENTAL PRESENTATION..." heading.
"""
import re, os, glob
from bs4 import BeautifulSoup
import warnings
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

RAW_DIR = "raw"
OUT_DIR = "sections"
os.makedirs(OUT_DIR, exist_ok=True)

def clean_html(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "img"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return [l.strip() for l in text.split("\n") if l.strip()]

def find_line(lines, pattern, start=0):
    rx = re.compile(pattern)
    for i in range(start, len(lines)):
        if rx.match(lines[i]):
            return i
    return None

raw_files = sorted(glob.glob(os.path.join(RAW_DIR, "*_10q_*.htm")))
for filepath in raw_files:
    q = re.search(r"_10q_(.+)\.htm$", os.path.basename(filepath)).group(1)
    print(f"\n=== {q.upper()} ===")
    lines = clean_html(filepath)
    text = "\n".join(lines)
    print(f"  total: {len(text):,}")
    with open(os.path.join(OUT_DIR, f"{q}_full.txt"), "w", encoding="utf-8") as f:
        f.write(text)

    # MD&A: "ITEM 2.    MANAGEMENT'S DISCUSSION..." to "ITEM 3." (both uppercase,
    # line-anchored; search beyond the table of contents)
    mda_s = find_line(lines, r"ITEM\s+2\.\s+MANAGEMENT", start=200)
    mda_e = find_line(lines, r"ITEM\s+3\.\s+QUANTITATIVE", start=(mda_s or 0) + 1)
    # Legal proceedings: Part II "ITEM 1.    LEGAL PROCEEDINGS" to "ITEM 1A"
    leg_s = find_line(lines, r"ITEM\s+1\.\s+LEGAL PROCEEDINGS", start=(mda_e or 0))
    leg_e = find_line(lines, r"ITEM\s+1A\.?", start=(leg_s or 0) + 1)
    # Risk factors: Part II "ITEM 1A." (after legal proceedings) to "ITEM 2."
    rf_s = leg_e
    rf_e = find_line(lines, r"ITEM\s+2\.\s+UNREGISTERED", start=(rf_s or 0) + 1)

    for sn, (s, e) in {"mda": (mda_s, mda_e),
                       "legal_proceedings": (leg_s, leg_e),
                       "risk_factors": (rf_s, rf_e)}.items():
        st = "\n".join(lines[s:e]).strip() if s is not None and e is not None else ""
        print(f"  {sn}: {len(st):,}" if st else f"  {sn}: NOT FOUND")
        with open(os.path.join(OUT_DIR, f"{q}_{sn}.txt"), "w", encoding="utf-8") as f:
            f.write(st)
print("\n=== Done ===")
