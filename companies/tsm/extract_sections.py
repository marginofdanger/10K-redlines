"""Extract key sections from TSM 20-F HTML filings.
20-F structure differs from 10-K:
- Item 3: Key Information (includes Risk Factors at 3D)
- Item 4: Information on the Company (≈ Business)
- Item 5: Operating and Financial Review (≈ MD&A)
- Item 8: Financial Information (includes Legal Proceedings at 8A)
"""
import re, os
from bs4 import BeautifulSoup
import warnings
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

RAW_DIR = "raw"
OUT_DIR = "sections"
os.makedirs(OUT_DIR, exist_ok=True)
TICKER = "tsm"
YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

# 20-F sections - adapted patterns
SECTIONS = {
    "business": (r"item\s*4[\.\s]", r"item\s*4a[\.\s]|item\s*5[\.\s]", 500),
    "risk_factors": (r"item\s*3[\.\s]", r"item\s*4[\.\s]", 500),
    "mda": (r"item\s*5[\.\s]", r"item\s*6[\.\s]", 500),
    "legal_proceedings": (r"item\s*8[\.\s]", r"item\s*9[\.\s]", 100),
}

def clean_html(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "img"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return "\n".join([l.strip() for l in text.split("\n") if l.strip()])

def at_line_start(text, pos):
    """clean_html joins stripped non-empty lines with \\n, so a real item heading
    always begins a line. An "Item N" that does not is an inline cross-reference
    -- e.g. "Item 1A of Part I - \u201cRisk Factors\u201d" inside another Item.
    Selecting one as a boundary swallows every Item in between."""
    return pos == 0 or text[pos - 1] == "\n"

def find_section_boundaries(text, start_pat, end_pat, min_len=500):
    starts = list(re.finditer(start_pat, text, re.IGNORECASE))
    ends = list(re.finditer(end_pat, text, re.IGNORECASE))
    # Prefer headings; fall back to the unfiltered lists if a filing somehow
    # carries no line-anchored match.
    starts = [m for m in starts if at_line_start(text, m.start())] or starts
    anchored_ends = [m for m in ends if at_line_start(text, m.start())]
    if not starts: return None, None
    best_start = None
    for m in starts:
        after = text[m.start():m.start()+1000]
        next_item = re.search(r'\bitem\s*\d', after[50:], re.IGNORECASE)
        if next_item and next_item.start() > min_len // 3:
            best_start = m.start(); break
        elif not next_item:
            best_start = m.start(); break
    if best_start is None: best_start = starts[-1].start()
    best_end = None
    for candidates in (anchored_ends, ends):
        for m in candidates:
            if m.start() > best_start + min_len:
                best_end = m.start()
                break
        if best_end is not None:
            break
    if best_end is None: best_end = best_start + 150000
    return best_start, best_end

for year in YEARS:
    filepath = os.path.join(RAW_DIR, f"{TICKER}_20f_fy{year}.htm")
    if not os.path.exists(filepath): continue
    print(f"\n=== FY{year} ===")
    text = clean_html(filepath)
    print(f"  total: {len(text):,}")
    with open(os.path.join(OUT_DIR, f"fy{year}_full.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    for sn, (sp, ep, min_len) in SECTIONS.items():
        s, e = find_section_boundaries(text, sp, ep, min_len)
        st = text[s:e].strip() if s is not None else ""
        if st: print(f"  {sn}: {len(st):,}")
        else: print(f"  {sn}: NOT FOUND")
        with open(os.path.join(OUT_DIR, f"fy{year}_{sn}.txt"), "w", encoding="utf-8") as f:
            f.write(st)
print("\n=== Done ===")
