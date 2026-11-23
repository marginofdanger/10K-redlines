"""Check every dashboard blockquote against the filing text it claims to quote.

A blockquote reads `FY2025: "…text…"`. The text (with <strong> tags removed and
split on ellipses) must appear verbatim, modulo whitespace and quote style, in
companies/<ticker>/sections/fy{YEAR}_full.txt for the labelled year.

Usage: python scripts/verify_quotes.py <ticker>
Exit status 1 if any quote fails.

Quarterly scanner: python scripts/verify_quotes.py <ticker> --10q
Checks companies/<ticker>/10q/dashboard/t*.json. A quarter label (`Q2 2025:`,
`FY2026 Q1:` or `FY2026Q1:`, always the FISCAL year) resolves to
10q/sections/fy{YEAR}q{N}_full.txt; a year label (`FY2025:` or `FY2025 10-K:`)
resolves to the 10-K text in sections/fy{YEAR}_full.txt.
"""
import glob, json, os, re, sys

def norm(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = s.replace(" ", " ")
    s = re.sub(r"\s+", " ", s)
    # Inline-XBRL tags split numbers/names onto their own lines, so the
    # extracted text has spaces before punctuation and after "$" or "(".
    s = re.sub(r" ([,.;:)%])", r"\1", s)
    s = re.sub(r"([$(]) ", r"\1", s)
    return s.strip()

LABEL = re.compile(r"\s*(?:<[^>]+>)*\s*(?:Q(?P<qa>\d)\s+(?P<ya>\d{4})|FY\s?(?P<yb>\d{4})\s?Q(?P<qb>\d)|FY\s?(?P<yc>\d{4}))[^:]*:\s*(?P<text>.*)", re.S)

def main(ticker, quarterly=False):
    base = os.path.join("companies", ticker)
    ddir = os.path.join(base, "10q", "dashboard") if quarterly else os.path.join(base, "dashboard")
    cache, fails, total = {}, [], 0
    # (file, title, html) for every finding body, signal card and theme card.
    items = []
    for path in sorted(glob.glob(os.path.join(ddir, "t*.json" if quarterly else "fy*.json"))):
        with open(path, encoding="utf-8") as f:
            t = json.load(f)
        items += [(path, fd["title"], fd.get("body_html", "")) for g in t["groups"] for fd in g["findings"]]
    sig = os.path.join(ddir, "signals.json")
    if os.path.exists(sig):
        with open(sig, encoding="utf-8") as f:
            s = json.load(f)
        items += [(sig, c["title"], c["html"]) for x in s["signals"] for c in x["cards"]]
        items += [(sig, th["title"], th["html"]) for th in s.get("themes", [])]
    for path, title, html_ in items:
        for bq in re.findall(r"<blockquote>(.*?)</blockquote>", html_, re.S):
            total += 1
            m = LABEL.match(bq)
            if not m:
                fails.append((path, title, "no FY/quarter label", bq[:80]))
                continue
            text = norm(m.group("text")).strip('"').strip()
            if m.group("yc"):
                year = m.group("yc")
                p = os.path.join(base, "sections", f"fy{year}_full.txt")
            else:
                year = f'{m.group("ya") or m.group("yb")}q{m.group("qa") or m.group("qb")}'
                p = os.path.join(base, "10q", "sections", f"fy{year}_full.txt")
            if year not in cache:
                # Two views of the text: as extracted, and with bare-number lines
                # dropped. The second rejoins sentences split by a page number at a
                # page break; the first keeps inline-XBRL values that sit on their own
                # line (e.g. "$\n541\nmillion"). A quote may match either.
                if os.path.exists(p):
                    raw = open(p, encoding="utf-8").read()
                    cache[year] = (norm(raw), norm(re.sub(r"^\d{1,3}$\n?", "", raw, flags=re.M)))
                else:
                    cache[year] = None
            hay = cache[year]
            if hay is None:
                fails.append((path, title, f"no fy{year} text", text[:80]))
                continue
            pieces = [p.strip(' "') for p in re.split(r"…|\.\.\.", text) if len(p.strip(' "')) > 12]
            missing = [p for p in pieces if p not in hay[0] and p not in hay[1]]
            if missing:
                fails.append((path, title, f"FY{year} not found", missing[0][:100]))
    for p, title, why, frag in fails:
        print(f"FAIL {os.path.basename(p)} | {title[:60]} | {why} | {frag}")
    print(f"{ticker}: {total - len(fails)}/{total} blockquotes verified")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], quarterly="--10q" in sys.argv[2:]))
