"""Check a dashboard before it is published. Exit status 1 if anything fails.

  python scripts/verify_dashboard.py companies/<t>/index.html [--since REF] [--no-render]

  structure  every non-void tag closed in order; every href="#id" has a target;
             no duplicate ids; every table row as wide as its header (colspan-aware)
  quotes     every quoted fragment in a <blockquote> (split at ellipses, 6+ words)
             appears in the filing text under <folder>/sections/*_full.txt
             (10-Q scanners also search ../sections). With --since REF only the
             blockquotes added since that git ref are checked, since older periods'
             filings may not be downloaded.
  render     loads the page in headless Chromium: no console or page errors, and
             clicking a finding header toggles it open
"""
import argparse, glob, html, os, re, subprocess, sys, tempfile
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
OPTIONAL_END = {"p", "li", "td", "th", "tr", "thead", "tbody", "option"}


class Structure(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.ids, self.hrefs = [], [], {}, []
        self.tables, self.quotes, self._q = [], [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            if a["id"] in self.ids:
                self.errors.append(f"duplicate id '{a['id']}' (lines {self.ids[a['id']]} and {self.getpos()[0]})")
            self.ids[a["id"]] = self.getpos()[0]
        if tag == "a" and (a.get("href") or "").startswith("#") and len(a["href"]) > 1:
            self.hrefs.append((a["href"][1:], self.getpos()[0]))
        if tag == "table":
            self.tables.append({"line": self.getpos()[0], "rows": []})
        if tag == "tr" and self.tables:
            self.tables[-1]["rows"].append([0, False])
        if tag in ("td", "th") and self.tables and self.tables[-1]["rows"]:
            row = self.tables[-1]["rows"][-1]
            row[0] += int(a.get("colspan") or 1)
            row[1] = row[1] or tag == "th"
        if tag == "blockquote":
            self._q = []
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag == "blockquote" and self._q is not None:
            self.quotes.append(("".join(self._q), self.getpos()[0]))
            self._q = None
        while self.stack and self.stack[-1][0] != tag and self.stack[-1][0] in OPTIONAL_END:
            self.stack.pop()
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            open_tag = self.stack[-1] if self.stack else ("nothing", 0)
            self.errors.append(f"line {self.getpos()[0]}: </{tag}> closes <{open_tag[0]}> opened on line {open_tag[1]}")

    def handle_data(self, data):
        if self._q is not None:
            self._q.append(data)


def norm(s):
    s = html.unescape(s).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def fragments(quote):
    """Quoted text inside a blockquote, split at ellipses and brackets (editorial insertions)."""
    q = norm(quote)
    spans = re.findall(r'"([^"]{20,})"', q) or [re.sub(r"^[a-z0-9 \-]{0,24}:\s*", "", q)]
    out = []
    for span in spans:
        for frag in re.split(r"\.\.\.|…|\[[^\]]*\]", span):
            frag = frag.strip(" .,;:")
            if len(frag.split()) >= 6:
                out.append(frag)
    return out


def added_lines(path, ref):
    diff = subprocess.run(["git", "diff", "-U0", ref, "--", path], capture_output=True, text=True).stdout
    lines, cur = set(), 0
    for l in diff.splitlines():
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", l)
        if m:
            cur = int(m.group(1))
            continue
        if l.startswith("+") and not l.startswith("+++"):
            lines.add(cur)
            cur += 1
    return lines


RENDER_JS = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
  const page = await browser.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  await page.goto('file://' + process.argv[2]);
  await page.waitForTimeout(300);
  const header = await page.$('.finding-header');
  if (header) {
    await header.click();
    const open = await page.evaluate(() => !!document.querySelector('.finding.open'));
    if (!open) errors.push('clicking .finding-header did not open the finding');
  }
  console.log(JSON.stringify(errors));
  await browser.close();
})();
"""


def render(path):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(RENDER_JS)
    env = dict(os.environ)
    npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    env["NODE_PATH"] = npm_root
    exe = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    if exe:
        env["CHROMIUM"] = exe[-1]
    r = subprocess.run(["node", f.name, os.path.abspath(path)], capture_output=True, text=True, env=env, timeout=120)
    os.unlink(f.name)
    if r.returncode != 0:
        return [f"render failed: {r.stderr.strip()[-400:]}"]
    return __import__("json").loads(r.stdout.strip().splitlines()[-1])


SIDES = {"bull", "bear"}


def card_fields(src, new_lines):
    """Bull/bear pages: each new evidence card needs data-pillar, data-side (bull|bear) and
    data-basis (stated|inferred), plus a .magnitude and a .next line inside it."""
    fails = []
    lines = src.split("\n")
    for ln in sorted(new_lines):
        line = lines[ln - 1] if ln - 1 < len(lines) else ""
        if '<div class="bb-card"' not in line:
            continue
        m = re.search(r'<div class="bb-card"([^>]*)>', "\n".join(lines[ln - 1:ln + 5]))
        attrs = dict(re.findall(r'data-(\w+)="([^"]*)"', m.group(1))) if m else {}
        if not attrs.get("pillar"):
            fails.append(f"line {ln}: card has no data-pillar")
        if attrs.get("side") not in SIDES:
            fails.append(f"line {ln}: card data-side must be bull or bear")
        if attrs.get("basis") not in ("stated", "inferred"):
            fails.append(f"line {ln}: card data-basis must be stated or inferred")
        block = "\n".join(lines[ln - 1:ln + 60])
        end = block.find('<div class="bb-card"', 10)
        block = block if end < 0 else block[:end]
        for cls in ("magnitude", "next"):
            if f'class="{cls}"' not in block:
                fails.append(f"line {ln}: card has no element with class=\"{cls}\"")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("--since")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()
    with open(a.page, encoding="utf-8") as f:
        src = f.read()
    p = Structure()
    p.feed(src)
    p.close()
    fails = list(p.errors)
    fails += [f"line {t[1]}: <{t[0]}> never closed" for t in p.stack if t[0] not in OPTIONAL_END | {"html", "body", "head"}]
    fails += [f"line {ln}: link to missing #{h}" for h, ln in p.hrefs if h not in p.ids]
    for t in p.tables:
        rows = [r for r in t["rows"] if r[0]]
        if not rows:
            continue
        width = next((r[0] for r in rows if r[1]), rows[0][0])
        bad = [r[0] for r in rows if r[0] != width]
        if bad:
            fails.append(f"table at line {t['line']}: header has {width} columns, {len(bad)} row(s) have {sorted(set(bad))}")

    folder = os.path.dirname(os.path.abspath(a.page))
    corpus_files = glob.glob(os.path.join(folder, "sections", "*_full.txt"))
    if os.path.basename(folder) == "10q":
        corpus_files += glob.glob(os.path.join(folder, "..", "sections", "*_full.txt"))
    if os.path.basename(folder) == "bullbear":  # quotes come from the company's 10-K and 10-Q text
        corpus_files += glob.glob(os.path.join(folder, "..", "sections", "*_full.txt"))
        corpus_files += glob.glob(os.path.join(folder, "..", "10q", "sections", "*_full.txt"))
    quotes = p.quotes
    if a.since:
        new = added_lines(a.page, a.since)
        quotes = [q for q in quotes if q[1] in new or any(l in new for l in range(q[1] - 3, q[1] + 1))]
        fails += card_fields(src, new)
    checked = unmatched = 0
    if corpus_files:
        # drop page furniture so a paragraph split across a page break reads continuously
        furniture = re.compile(r"(\d{1,3}|[ivxl]{1,5}|-\s*\d{1,3}\s*-|table of contents|page|index)", re.I)
        corpus = norm(" ".join(l for f in corpus_files for l in open(f, encoding="utf-8").read().split("\n")
                               if not furniture.fullmatch(l.strip())))
        for q, ln in quotes:
            for frag in fragments(q):
                checked += 1
                if frag not in corpus:
                    unmatched += 1
                    fails.append(f"line {ln}: quote not found in filing text: \"{frag[:110]}\"")
    if not a.no_render:
        fails += render(a.page)

    print(f"{a.page}: {len(p.ids)} ids, {len(p.hrefs)} anchors, {len(p.tables)} tables, "
          f"{len(quotes)} blockquotes checked ({checked} fragments, {unmatched} unmatched"
          f"{'' if corpus_files else '; no sections/*_full.txt found, quotes NOT checked'})")
    for f in fails:
        print("FAIL", f)
    print("OK" if not fails else f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
