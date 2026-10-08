"""Extract the analyzed sections from 10-K, 20-F and 10-Q filings, for every company.

  python scripts/extract_sections.py companies/<t>        # raw/*_10k_fy<YYYY>.htm or *_20f_fy<YYYY>.htm
  python scripts/extract_sections.py companies/<t>/10q    # raw/*_10q_fy<YYYY>q<N>.htm

Writes sections/<period>_<section>.txt (and <period>_full.txt), then prints each
section's length with a WARN line when a section is missing or its length moved
more than 3x against the adjacent period: that is almost always a boundary bug,
and a redline built on it would report an extraction artifact as a disclosure change.

Headings are found structurally rather than by start/end regex pairs:
  - a heading is an "Item N" at the start of a line whose title (same or next
    line) matches the item; an "Item N" inside a sentence, or one followed by
    lowercase/punctuation continuation, is a cross-reference and is ignored
  - table-of-contents entries are skipped because their span to the next
    heading is tiny
  - items are resolved in filing order, each after the previous one, so a
    cross-reference that happens to start a line before its item can't win
"""
import glob, os, re, sys, warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

TITLES = {  # item -> title regex (matched case-insensitively at the start of the title text)
    "10-K": {"1": r"business", "1A": r"risk\s+factors", "1B": r"unresolved", "1C": r"cybersecurity",
             "2": r"properties", "3": r"legal\s+proceedings", "4": r"(mine\s+safety|submission|\(?removed|\[?reserved)",
             "5": r"market\s+for", "6": r"(selected|\[?reserved|reserved)", "7": r"management", "7A": r"quantitative",
             "8": r"financial\s+statements", "9": r"changes\s+in", "9A": r"controls", "9B": r"other\s+information"},
    "20-F": {"3": r"key\s+information", "4": r"information\s+on\s+the\s+company", "4A": r"unresolved",
             "5": r"operating\s+and\s+financial", "6": r"directors", "7": r"major\s+shareholders",
             "8": r"financial\s+information", "9": r"the\s+offer"},
    "10-Q": {"1": r"(financial\s+statements|legal\s+proceedings)", "1A": r"risk\s+factors",
             "2": r"(management|unregistered)", "3": r"(quantitative|defaults)", "4": r"(controls|mine\s+safety)",
             "5": r"other\s+information", "6": r"exhibits"},
}
# section -> (item, title override or None, minimum length); resolved in this order.
SECTIONS = {
    "10-K": [("business", "1", None, 500), ("risk_factors", "1A", None, 500), ("properties", "2", None, 1),
             ("legal_proceedings", "3", None, 1), ("mda", "7", None, 1), ("market_risk", "7A", None, 1)],
    "20-F": [("risk_factors", "3", None, 500), ("business", "4", None, 500), ("mda", "5", None, 500),
             ("legal_proceedings", "8", None, 1)],
    "10-Q": [("mda", "2", r"management", 500), ("legal_proceedings", "1", r"legal\s+proceedings", 1),
             ("risk_factors", "1A", r"risk\s+factors", 1)],
}
# Notes some 10-Q filers use instead of a substantive Part II Item 1.
CONTINGENCIES_NOTE = {"amzn": "COMMITMENTS AND CONTINGENCIES"}
# Sections a filer incorporates by reference from an exhibit (the main document holds a
# pointer). raw/<t>_10k_fy<YYYY>_ex13.htm is fetched by check_new_filings.py download.
EXHIBIT_SECTIONS = {
    "pgr": {"mda": (r"Management.s Discussion and Analysis of Financial Condition and Results of Operations",
                    r"Supplemental Information"),
            "market_risk": (r"Quantitative Market Risk Disclosures", r"Online Annual Report")},
}
MAX_SPAN = 400_000

ITEM_LINE = re.compile(r"^items?\s*(\d{1,2}[A-D]?)\b\s*[\.:\-—–,]?\s*(.*)$", re.I)


BLOCK = ["p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "hr",
         "section", "article", "header", "footer", "blockquote", "pre", "center", "body"]


def clean_lines(path):
    """One line per block element. Inline tags (inline-XBRL number wrappers, spans,
    links) stay inside their sentence, so a paragraph is one line."""
    with open(path, encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    for tag in soup(["script", "style", "img"]):
        tag.decompose()
    for t in soup.find_all(style=re.compile(r"display\s*:\s*none", re.I)):
        t.decompose()  # inline-XBRL hidden header
    for t in soup.find_all(BLOCK):
        t.insert_before("\n")
        t.insert_after("\n")
    for t in soup.find_all(["td", "th"]):
        t.insert_after(" ")
    lines = [re.sub(r"\s+", " ", l.replace("\xa0", " ")).strip() for l in soup.get_text("").split("\n")]
    return [l for l in lines if l]


def headings(lines, titles):
    """(line index, item, title text) for every line that reads as a real item heading.
    Table-of-contents entries (title followed by a page number) are dropped."""
    found = []
    for i, l in enumerate(lines):
        m = ITEM_LINE.match(l)
        if not m or len(l) > 220:
            continue
        item = m.group(1).upper()
        rest = [m.group(2).strip()] + lines[i + 1:i + 4]
        rest = [r for r in rest if r and not re.fullmatch(r"[\.\:\-\u2014\u2013]+", r)]
        if len(rest) < 2:
            continue
        title, after = rest[0], rest[1]
        if item not in titles or not re.search(titles[item], title[:120], re.I):
            continue
        if re.fullmatch(r"(page\s*)?[\divxl\-\u2013 ]{1,8}", after, re.I) or re.search(r"\s\d{1,3}$", title):
            continue  # table of contents: page number on the next line or ending the row
        if re.match(r"[a-z,;\)\u2019']", after) or re.match(r"(of|in|to|and)\b", after):
            continue  # cross-reference continuing a sentence
        prev = lines[i - 1] if i else ""
        if re.match(r"[\u201c\"]", title) or re.search(r"(\b(and|or|see|in|of|under|to|the|our)|,)$", prev, re.I):
            continue  # cross-reference: quoted title, or the sentence before it is unfinished
        found.append((i, item, title))
    return found


FURNITURE = re.compile(r"(\d{1,3}|[ivxl]{1,5}|-\s*\d{1,3}\s*-|table of contents|page|app\.-[a-z]-\d+|index)$", re.I)


def tidy(text, heading_line):
    """Drop page numbers, TOC links and running headers repeated inside the section."""
    head = key(heading_line)
    keep = [l for k, l in enumerate(text.split("\n"))
            if k == 0 or not (FURNITURE.fullmatch(l) or (key(l) == head and k > 0))]
    return "\n".join(keep).strip()


def offsets(lines):
    pos, out = 0, []
    for l in lines:
        out.append(pos)
        pos += len(l) + 1
    return out


def key(title):
    return re.sub(r"[^a-z]", "", title.lower())[:20]


def extract(lines, form):
    titles = TITLES[form]
    hs = headings(lines, titles)
    off = offsets(lines)
    total = off[-1] + len(lines[-1]) if lines else 0

    item_at = {j: (it, key(t)) for j, it, t in hs}

    def end_of(idx):
        for j, it, t in hs:
            # a repeat of the same heading is a running page header ("ITEM 2. ... (Continued)")
            if j > idx and item_at[j] != item_at[idx]:
                return off[j]
        return min(total, off[idx] + MAX_SPAN)

    results, cursor = {}, 0
    for name, item, title_rx, min_len in SECTIONS[form]:
        start = None
        for j, it, title in hs:
            if it != item or off[j] < cursor or (title_rx and not re.search(title_rx, title[:120], re.I)):
                continue
            if end_of(j) - off[j] >= min_len:
                start = j
                break
        if start is None:
            results[name] = ""
            continue
        s, e = off[start], end_of(start)
        results[name] = tidy("\n".join(lines)[s:e].strip(), lines[start])
        cursor = s + 1 if form != "10-Q" else e  # 10-Q Part II items follow the MD&A
    return results


NOTE_HEADING = re.compile(r"(Note \d+\s*[\u2014\u2013\-:.]\s*)?[A-Z][A-Z0-9 &',\-()]{3,}")


def find_note(lines, heading):
    """A financial-statement note, from its heading ("Note 4 \u2014 COMMITMENTS AND CONTINGENCIES")
    to the next note heading."""
    for i, l in enumerate(lines):
        if l.endswith(heading) and NOTE_HEADING.fullmatch(l):
            for j in range(i + 1, len(lines)):
                if NOTE_HEADING.fullmatch(lines[j]) and (lines[j].startswith("Note ") or not l.startswith("Note ")):
                    return "\n".join(lines[i:j])
            return "\n".join(lines[i:])
    return ""


def from_exhibit(lines, start_rx, end_rx):
    for i, l in enumerate(lines):
        if re.fullmatch(start_rx, l, re.I):
            for j in range(i + 1, len(lines)):
                if re.match(end_rx, lines[j], re.I) and len(lines[j]) < 120:
                    return "\n".join(lines[i:j])
    return ""


def main(folder):
    raw = sorted(glob.glob(os.path.join(folder, "raw", "*.htm")))
    out_dir = os.path.join(folder, "sections")
    os.makedirs(out_dir, exist_ok=True)
    sizes, warns = {}, []
    for path in raw:
        m = re.match(r"(\w+?)_(10k|20f|10q)_(fy\d{4}(?:q\d)?)\.htm$", os.path.basename(path), re.I)
        if not m:
            continue
        ticker, form, period = m.group(1).lower(), {"10k": "10-K", "20f": "20-F", "10q": "10-Q"}[m.group(2).lower()], m.group(3).lower()
        lines = clean_lines(path)
        with open(os.path.join(out_dir, f"{period}_full.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        secs = extract(lines, form)
        exhibit = path[:-4] + "_ex13.htm"
        if form == "10-K" and ticker in EXHIBIT_SECTIONS and os.path.exists(exhibit):
            ex_lines = clean_lines(exhibit)
            for name, (srx, erx) in EXHIBIT_SECTIONS[ticker].items():
                secs[name] = (secs[name] + "\n" if secs[name] else "") + from_exhibit(ex_lines, srx, erx)
        if form == "10-Q" and ticker in CONTINGENCIES_NOTE:
            secs["contingencies"] = find_note(lines, CONTINGENCIES_NOTE[ticker])
        for name, text in secs.items():
            with open(os.path.join(out_dir, f"{period}_{name}.txt"), "w", encoding="utf-8") as f:
                f.write(text)
            sizes.setdefault(name, []).append((period, len(text)))
        print(f"{period}: " + "  ".join(f"{n} {len(t):,}" for n, t in secs.items()))
    for name, series in sizes.items():
        for (p0, n0), (p1, n1) in zip(series, series[1:]):
            if n1 == 0 or n0 == 0:
                continue
            if n1 > 3 * n0 or n0 > 3 * n1:
                warns.append(f"WARN {name}: {p0} {n0:,} -> {p1} {n1:,} chars (>3x change; check boundaries)")
        for p, n in series:
            if n == 0:
                warns.append(f"WARN {name}: {p} NOT FOUND")
    for w in warns:
        print(w)
    return 1 if warns else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
