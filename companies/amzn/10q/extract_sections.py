"""Extract key sections from 10-Q HTML filings.
10-Q structure: Part I (financial + MD&A), Part II (risk factors, legal).
Generic: auto-detects ticker and quarters from raw/{ticker}_10q_{quarter}.htm filenames.
"""
import re, os, glob
from bs4 import BeautifulSoup
import warnings
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

RAW_DIR = "raw"
OUT_DIR = "sections"
os.makedirs(OUT_DIR, exist_ok=True)

# 10-Q sections: MD&A is Part I Item 2; Risk Factors is Part II Item 1A;
# Legal Proceedings is Part II Item 1 (appears after Item 4 of Part I).
# Third tuple element: minimum section length (legal proceedings can be a
# one-paragraph pointer to the notes, well under the default 500).
SECTIONS = {
    "mda": (r"item\s*2[\.\s]", r"item\s*3[\.\s]", 500),
    "risk_factors": (r"item\s*1a[\.\s]", r"item\s*2[\.\s]", 500),
    "legal_proceedings": (r"item\s*1\.?\s*\n?\s*legal\s+proceedings", r"item\s*1a[\.\s]", 100),
}

def clean_html(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "img"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return "\n".join([l.strip() for l in text.split("\n") if l.strip()])

def find_section_boundaries(text, start_pat, end_pat, min_len=500, search_from=0):
    """Find a section's boundaries, skipping table-of-contents references.
    search_from lets Part II sections search after the MD&A (Part I)."""
    start_offsets = [m.start() + search_from
                     for m in re.finditer(start_pat, text[search_from:], re.IGNORECASE)]
    if not start_offsets:
        return None, None
    best_start = None
    for off in start_offsets:
        after = text[off:off + 1000]
        next_item = re.search(r"\bitem\s*\d", after[50:], re.IGNORECASE)
        if next_item is None or next_item.start() > min_len // 3:
            best_start = off; break
    if best_start is None:
        best_start = start_offsets[-1]
    ends = list(re.finditer(end_pat, text, re.IGNORECASE))
    best_end = None
    # Headings sit on their own line (clean_html joins stripped lines with \n),
    # so an "Item N" that is not at a line start is an inline cross-reference --
    # e.g. AMZN's risk-factor intro says "the factors discussed in Item 2 of
    # Part I", which would otherwise truncate the section at ~800 chars.
    for require_line_start in (True, False):
        for m in ends:
            if m.start() <= best_start + min_len:
                continue
            if require_line_start and m.start() > 0 and text[m.start() - 1] != "\n":
                continue
            best_end = m.start(); break
        if best_end is not None:
            break
    if best_end is None:
        best_end = best_start + 100000
    return best_start, best_end


# AMZN's Part II Item 1 is a one-line pointer to the contingencies note, so the
# quarterly legal signal lives in Note 4 inside the financial statements.
NOTE_HEADING = re.compile(r"^[A-Z][A-Z &',\-]{8,}$", re.MULTILINE)

def find_note(text, heading):
    m = re.search(rf"^{heading}$", text, re.MULTILINE)
    if not m:
        return None, None
    nxt = NOTE_HEADING.search(text, m.end())
    return m.start(), (nxt.start() if nxt else len(text))

raw_files = sorted(glob.glob(os.path.join(RAW_DIR, "*_10q_*.htm")))
for filepath in raw_files:
    q = re.search(r"_10q_(.+)\.htm$", os.path.basename(filepath)).group(1)
    print(f"\n=== {q.upper()} ===")
    text = clean_html(filepath)
    print(f"  total: {len(text):,}")
    with open(os.path.join(OUT_DIR, f"{q}_full.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    # Extract MD&A first (Part I Item 2); Part II sections must come after it
    mda_s, mda_e = find_section_boundaries(text, *SECTIONS["mda"])
    results = {"mda": (mda_s, mda_e)}
    part2_from = mda_e if mda_e else 0
    for sn in ("risk_factors", "legal_proceedings"):
        sp, ep, ml = SECTIONS[sn]
        results[sn] = find_section_boundaries(text, sp, ep, min_len=ml, search_from=part2_from)
    results["contingencies"] = find_note(text, "COMMITMENTS AND CONTINGENCIES")
    for sn, (s, e) in results.items():
        st = text[s:e].strip() if s is not None else ""
        print(f"  {sn}: {len(st):,}" if st else f"  {sn}: NOT FOUND")
        with open(os.path.join(OUT_DIR, f"{q}_{sn}.txt"), "w", encoding="utf-8") as f:
            f.write(st)
print("\n=== Done ===")
