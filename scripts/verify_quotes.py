"""Check every dashboard blockquote against the filing text it claims to quote.

A blockquote reads `FY2025: "…text…"`. The text (with <strong> tags removed and
split on ellipses) must appear verbatim, modulo whitespace and quote style, in
companies/<ticker>/sections/fy{YEAR}_full.txt for the labelled year.

Usage: python scripts/verify_quotes.py <ticker>
Exit status 1 if any quote fails.
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

def main(ticker):
    base = os.path.join("companies", ticker)
    cache, fails, total = {}, [], 0
    # (file, title, html) for every finding body, signal card and theme card.
    items = []
    for path in sorted(glob.glob(os.path.join(base, "dashboard", "fy*.json"))):
        with open(path, encoding="utf-8") as f:
            t = json.load(f)
        items += [(path, fd["title"], fd.get("body_html", "")) for g in t["groups"] for fd in g["findings"]]
    sig = os.path.join(base, "dashboard", "signals.json")
    if os.path.exists(sig):
        with open(sig, encoding="utf-8") as f:
            s = json.load(f)
        items += [(sig, c["title"], c["html"]) for x in s["signals"] for c in x["cards"]]
        items += [(sig, th["title"], th["html"]) for th in s.get("themes", [])]
    for path, title, html_ in items:
        for bq in re.findall(r"<blockquote>(.*?)</blockquote>", html_, re.S):
            total += 1
            m = re.match(r"\s*(?:<[^>]+>)*\s*FY\s?(\d{4})[^:]*:\s*(.*)", bq, re.S)
            if not m:
                fails.append((path, title, "no FY label", bq[:80]))
                continue
            year, text = m.group(1), norm(m.group(2)).strip('"').strip()
            if year not in cache:
                p = os.path.join(base, "sections", f"fy{year}_full.txt")
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
    sys.exit(main(sys.argv[1]))
