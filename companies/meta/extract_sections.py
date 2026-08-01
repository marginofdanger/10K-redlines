"""
Extract key sections from META 10-K HTML filings.
Sections: Business, Risk Factors, MD&A (incl. Results of Operations), Properties, Legal Proceedings
"""
import re
import os
import json
from bs4 import BeautifulSoup

RAW_DIR = "raw"
OUT_DIR = "sections"
os.makedirs(OUT_DIR, exist_ok=True)

YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

# 10-K Item patterns - we look for these headings in the text
SECTIONS = {
    "business": (r"item\s*1[\.\s]", r"item\s*1a[\.\s]", 500),
    "risk_factors": (r"item\s*1a[\.\s]", r"item\s*1b[\.\s]", 500),
    "properties": (r"item\s*2[\.\s]", r"item\s*3[\.\s]", 500),
    "legal_proceedings": (r"item\s*3[\.\s]", r"item\s*4[\.\s]", 100),
    "mda": (r"item\s*7[\.\s]", r"item\s*7a[\.\s]", 500),
    "market_risk": (r"item\s*7a[\.\s]", r"item\s*8[\.\s]", 500),
}

def clean_html(filepath):
    """Convert HTML to clean text, preserving structure."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    soup = BeautifulSoup(html, "lxml")
    # Remove scripts, styles
    for tag in soup(["script", "style", "img"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Clean up whitespace
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            lines.append(line)
    return "\n".join(lines)

def at_line_start(text, pos):
    """clean_html joins stripped non-empty lines with \\n, so a real item heading
    always begins a line. An "Item N" that does not is an inline cross-reference
    -- e.g. "Item 1A of Part I - \u201cRisk Factors\u201d" inside another Item.
    Selecting one as a boundary swallows every Item in between."""
    return pos == 0 or text[pos - 1] == "\n"

def find_section_boundaries(text, start_pat, end_pat, min_len=500):
    """
    Find the start and end of a section using item header patterns.
    We look for the LAST occurrence of the start pattern in the table of contents area
    vs the actual section. We use a heuristic: the actual section header is usually
    followed by substantial text, not just a page number.
    """
    # Find all matches of start pattern
    starts = list(re.finditer(start_pat, text, re.IGNORECASE))
    ends = list(re.finditer(end_pat, text, re.IGNORECASE))
    # Prefer headings; fall back to the unfiltered lists if a filing somehow
    # carries no line-anchored match.
    starts = [m for m in starts if at_line_start(text, m.start())] or starts
    anchored_ends = [m for m in ends if at_line_start(text, m.start())]

    if not starts:
        return None, None

    # The actual section (not TOC reference) is typically the one where the next 500 chars
    # contain substantial text, not just a number and another Item reference
    best_start = None
    for m in starts:
        after = text[m.start():m.start()+1000]
        # If the text after the heading has more than 200 chars before next "Item", it's the real section
        next_item = re.search(r'\bitem\s*\d', after[50:], re.IGNORECASE)
        if next_item and next_item.start() > min_len // 3:
            best_start = m.start()
            break
        elif not next_item:
            best_start = m.start()
            break

    if best_start is None:
        # Fallback: use the last occurrence (usually the actual section, after TOC)
        best_start = starts[-1].start()

    # Find the first end pattern that comes after our start
    best_end = None
    for candidates in (anchored_ends, ends):  # prefer a heading over any match
        for m in candidates:
            if m.start() > best_start + min_len:
                best_end = m.start()
                break
        if best_end is not None:
            break

    if best_end is None:
        best_end = best_start + 100000  # fallback: take a large chunk

    return best_start, best_end

def extract_sections(text, year):
    """Extract all key sections from the filing text."""
    results = {}
    for section_name, (start_pat, end_pat, min_len) in SECTIONS.items():
        start, end = find_section_boundaries(text, start_pat, end_pat, min_len)
        if start is not None:
            section_text = text[start:end].strip()
            # Trim to reasonable size and clean
            results[section_name] = section_text
            print(f"  {section_name}: {len(section_text):,} chars")
        else:
            print(f"  {section_name}: NOT FOUND")
            results[section_name] = ""
    return results

for year in YEARS:
    filepath = os.path.join(RAW_DIR, f"meta_10k_fy{year}.htm")
    print(f"\n=== Processing FY{year} ===")
    print(f"  File: {filepath}")

    text = clean_html(filepath)
    print(f"  Total clean text: {len(text):,} chars")

    # Save full clean text
    with open(os.path.join(OUT_DIR, f"fy{year}_full.txt"), "w", encoding="utf-8") as f:
        f.write(text)

    sections = extract_sections(text, year)

    # Save each section
    for section_name, section_text in sections.items():
        outpath = os.path.join(OUT_DIR, f"fy{year}_{section_name}.txt")
        with open(outpath, "w", encoding="utf-8") as f:
            f.write(section_text)

print("\n=== Done ===")
print(f"Sections saved to {OUT_DIR}/")
