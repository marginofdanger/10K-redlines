"""Assemble a 10-K redline dashboard from per-transition JSON fragments.

The page reuses the <style> block and toggle script of the canonical template
(companies/meta/index.html) so every dashboard shares one look. Content comes
from companies/<ticker>/dashboard/:

  page.json         {ticker, name, title, tagline, source, footer}
  fy{YEAR}.json     one per transition, named for the later year:
                    {from, to, title, sub, era_summary,
                     groups: [{section, findings: [{title, tag, body_html}]}]}
  signals.json      {signals: [{id, title, cards: [{title, html}]}],
                     themes: [{title, html}],
                     ref_table: {headers: [...], rows: [[cell_html, ...], ...]}}

body_html / html / cell values are trusted HTML written by the analysis agents
(blockquotes for verbatim filing text); every other field is escaped.

Usage: python scripts/build_redline_page.py <ticker>
Writes companies/<ticker>/index.html

Quarterly scanner: python scripts/build_redline_page.py <ticker> --10q
Reads companies/<ticker>/10q/dashboard/, writes companies/<ticker>/10q/index.html.
Transitions are t{NN}.json, ordered by filename, each with an `id` (anchor) and
no era_summary; page.json adds `range` (sidebar label) and optional `method`
({title, html}, the "Reading This Filer" card). The sidebar links back to the
10-K dashboard and the front page.
"""
import glob, html, json, os, re, sys

TEMPLATE = os.path.join("companies", "meta", "index.html")

SECTION_COLORS = {
    "Business": "var(--accent)",
    "Risk Factors": "var(--red)",
    "MD&A": "var(--orange)",
    "Capital & Liquidity": "var(--purple)",
    "Credit": "var(--cyan)",
    "Market & Operational Risk": "var(--red)",
    "Accounting & FLS": "var(--text-dim)",
    "Legal": "var(--pink)",
    "Forward Guidance": "var(--accent2)",
}
TAG_CLASS = {"new": "tag-new", "changed": "tag-changed", "removed": "tag-removed"}

def esc(s):
    return html.escape(str(s), quote=False)

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def template_parts():
    with open(TEMPLATE, encoding="utf-8") as f:
        t = f.read()
    style = re.search(r"<style>.*?</style>", t, re.S).group(0)
    # The template only styles blockquotes inside findings; signal and theme
    # cards here carry year-labelled filing quotes too, so give them the same look.
    style = style.replace(".finding-body blockquote {", ".finding-body blockquote, .signal-card blockquote {", 1)
    script = re.search(r"<script>.*?</script>", t, re.S).group(0)
    return style, script

def finding_html(f):
    tag = f.get("tag", "Signal")
    cls = TAG_CLASS.get(tag.lower(), "tag-signal")
    return ('  <div class="finding"><div class="finding-header" onclick="toggle(this)">'
            '<span class="arrow">&#9654;</span>'
            f'<span class="title">{esc(f["title"])}</span>'
            f'<span class="tag {cls}">{esc(tag)}</span></div>'
            f'<div class="finding-body">{f.get("body_html", "")}</div></div>')

def main(ticker, quarterly=False):
    base = os.path.join("companies", ticker, *(["10q"] if quarterly else []))
    ddir = os.path.join(base, "dashboard")
    page = load(os.path.join(ddir, "page.json"))
    if quarterly:
        trans = [load(p) for p in sorted(glob.glob(os.path.join(ddir, "t*.json")))]
    else:
        trans = sorted((load(p) for p in glob.glob(os.path.join(ddir, "fy*.json"))),
                       key=lambda t: t["to"])
    sig_path = os.path.join(ddir, "signals.json")
    sig = load(sig_path) if os.path.exists(sig_path) else {"signals": [], "themes": []}
    style, script = template_parts()

    def yid(t):
        return t["id"] if quarterly else "yoy-" + re.sub(r"\D", "", t["to"])

    span = page.get("range") or f'{trans[0]["from"]} - {trans[-1]["to"]}'
    nav = [f'  <div class="sidebar-header">\n    <h1>{esc(page["ticker"])} {"10-Q SCANNER" if quarterly else "10-K REDLINES"}</h1>\n'
           f'    <div class="sub">{esc(span)} | SEC EDGAR</div>\n  </div>',
           '  <div class="nav-section">Overview</div>',
           '  <a class="nav-item" href="#hero-section">Executive Summary</a>']
    if page.get("method"):
        nav.append('  <a class="nav-item" href="#method">Reading This Filer</a>')
    nav.append(f'  <div class="nav-section">{"Quarter-over-Quarter" if quarterly else "Year-Over-Year"}</div>')
    nav += [f'  <a class="nav-item" href="#{yid(t)}">{esc(t["from"])} &rarr; {esc(t["to"])}</a>' for t in trans]
    if sig["signals"]:
        nav.append('  <div class="nav-section">Deep Signals</div>')
        nav += [f'  <a class="nav-item" href="#{esc(s["id"])}">{esc(s["title"])}</a>' for s in sig["signals"]]
    nav.append('  <div class="nav-section">Synthesis</div>')
    if sig.get("themes"):
        nav.append('  <a class="nav-item" href="#themes">Themes</a>')
    if sig.get("ref_table"):
        nav.append('  <a class="nav-item" href="#ref-table">Financial Reference</a>')
    if quarterly:
        nav += ['  <div class="nav-section">Links</div>',
                f'  <a class="nav-item" href="../index.html">{esc(page["ticker"])} 10-K dashboard</a>',
                '  <a class="nav-item" href="../../../index.html">All companies</a>']

    body = [f'<div class="hero" id="hero-section">\n  <h1>{esc(page["title"])}</h1>\n'
            f'  <div class="tagline">{esc(page["tagline"])}</div>\n'
            f'  <div class="source">{esc(page["source"])}</div>\n</div>']
    if not quarterly:
        body.append('<div class="eras">')
        for t in trans:
            body.append(f'  <div class="era-card">\n    <div class="years">{esc(t["from"])} &rarr; {esc(t["to"])}</div>\n'
                        f'    <h3>{esc(t["title"])}</h3>\n    <p>{esc(t["era_summary"])}</p>\n  </div>')
        body.append('</div>')
    m = page.get("method")
    if m:
        body.append('<div class="section" id="method">\n  <div class="section-header"><h2>Reading This Filer</h2></div>\n'
                    f'  <div class="signal-card full">\n    <h3>{esc(m["title"])}</h3>\n    {m["html"]}\n  </div>\n</div>')
    body.append('<div style="display:flex;justify-content:flex-end;margin-bottom:8px">\n'
                '  <button class="expand-btn" onclick="toggleAll()" id="global-expand">Expand all</button>\n</div>')

    for t in trans:
        body.append(f'<div class="transition-header" id="{yid(t)}">\n'
                    f'  <h2>{esc(t["from"])} &rarr; {esc(t["to"])}: {esc(t["title"])}</h2>\n'
                    f'  <div class="sub">{esc(t["sub"])}</div>\n</div>')
        for g in t["groups"]:
            color = SECTION_COLORS.get(g["section"], "var(--text-dim)")
            body.append(f'<div class="finding-group">\n  <h3><span class="dot" style="background:{color}"></span> {esc(g["section"])}</h3>')
            body += [finding_html(f) for f in g["findings"]]
            body.append('</div>')

    for i, s in enumerate(sig["signals"], 1):
        body.append(f'<div class="section" id="{esc(s["id"])}" style="margin-top:56px">\n'
                    f'  <div class="section-header"><h2>{esc(s["title"])}</h2></div>')
        for c in s["cards"]:
            body.append(f'  <div class="signal-card full" style="margin-bottom:20px">\n'
                        f'    <h3><span class="num">{i}</span> {esc(c["title"])}</h3>\n    {c["html"]}\n  </div>')
        body.append('</div>')

    if sig.get("themes"):
        body.append('<div class="section" id="themes">\n  <div class="section-header"><h2>Themes</h2></div>\n  <div class="signal-grid">')
        body += [f'    <div class="signal-card">\n      <h3>{esc(th["title"])}</h3>\n      {th["html"]}\n    </div>' for th in sig["themes"]]
        body.append('  </div>\n</div>')

    rt = sig.get("ref_table")
    if rt:
        head = "".join(f"<th>{esc(h)}</th>" for h in rt["headers"])
        rows = "\n".join("      <tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rt["rows"])
        body.append(f'<div class="section" id="ref-table">\n  <div class="section-header"><h2>Financial Reference</h2></div>\n'
                    f'  <table class="data-table">\n    <thead><tr>{head}</tr></thead>\n    <tbody>\n{rows}\n    </tbody>\n  </table>\n</div>')

    body.append('<div style="text-align:center;padding:40px 0;color:var(--text-dim);font-size:12px;'
                f'border-top:1px solid var(--border);margin-top:40px">\n  {esc(page["footer"])}\n</div>')

    out = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
           f'<title>{esc(page["ticker"])} {"10-Q Quarterly Scanner" if quarterly else "10-K Redline Analysis"} | '
           f'{esc(page.get("range") or trans[0]["from"] + "-" + trans[-1]["to"])}</title>\n'
           f'{style}\n</head>\n<body>\n\n<nav class="sidebar">\n' + "\n".join(nav) + '\n</nav>\n\n'
           '<div class="main">\n\n' + "\n\n".join(body) + '\n\n</div><!-- end .main -->\n\n'
           f'{script}\n</body>\n</html>\n')
    with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)
    n = sum(len(g["findings"]) for t in trans for g in t["groups"])
    print(f"{base}/index.html: {len(trans)} transitions, {n} findings, {len(sig['signals'])} signal sections")

if __name__ == "__main__":
    main(sys.argv[1], quarterly="--10q" in sys.argv[2:])
