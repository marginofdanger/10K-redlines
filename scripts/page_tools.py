"""Add (or refresh) the page tools on every 10-K and 10-Q dashboard: newest filing first, and
Expand all / Collapse all buttons.

  python scripts/page_tools.py                  # all companies/*/index.html and companies/*/10q/index.html
  python scripts/page_tools.py companies/hca/10q/index.html

The block sits just before </body> between <!-- page-tools --> markers, so running this again
replaces it. Pages keep their transitions oldest-first in the source (the runbook appends each new
one at the end); the script shows them newest-first, in the page and in the sidebar.
"""
import glob, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BLOCK = """<!-- page-tools: newest filing first, expand / collapse all (scripts/page_tools.py) -->
<style>
.page-tools { position: fixed; right: 16px; bottom: 16px; z-index: 50; display: flex; gap: 6px; padding: 6px;
  background: #fff; border: 1px solid #d6dbe1; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.12);
  font: 600 12px/1 -apple-system, 'Segoe UI', Roboto, sans-serif; }
.page-tools button { font: inherit; padding: 7px 11px; border-radius: 5px; border: 1px solid #1B365D;
  background: #fff; color: #1B365D; cursor: pointer; }
.page-tools button:hover, .page-tools button:focus-visible { background: #1B365D; color: #fff; outline: none; }
@media print { .page-tools { display: none; } }
</style>
<div class="page-tools" role="toolbar" aria-label="Page tools">
  <button type="button" data-tools="expand">Expand all</button>
  <button type="button" data-tools="collapse">Collapse all</button>
</div>
<script>
(function () {
  // Newest filing first: each transition (its header and everything up to the next transition
  // or section) moves above the one before it.
  var headers = Array.prototype.slice.call(document.querySelectorAll('.transition-header'));
  if (headers.length > 1) {
    var parent = headers[0].parentNode;
    var spot = document.createComment('transitions');
    parent.insertBefore(spot, headers[0]);
    var blocks = headers.map(function (h) {
      var nodes = [h], n = h.nextSibling;
      while (n && !(n.nodeType === 1 && (n.classList.contains('transition-header') || n.classList.contains('section')))) {
        nodes.push(n);
        n = n.nextSibling;
      }
      return nodes;
    });
    var frag = document.createDocumentFragment();
    for (var i = blocks.length - 1; i >= 0; i--) blocks[i].forEach(function (n) { frag.appendChild(n); });
    parent.insertBefore(frag, spot);
    parent.removeChild(spot);

    // Same order in the sidebar
    var ids = headers.map(function (h) { return '#' + h.id; });
    var links = Array.prototype.slice.call(document.querySelectorAll('nav.sidebar a.nav-item')).filter(function (a) {
      return ids.indexOf(a.getAttribute('href')) >= 0;
    });
    if (links.length > 1) {
      var nav = links[0].parentNode, mark = document.createComment('links');
      nav.insertBefore(mark, links[0]);
      links.reverse().forEach(function (a) { nav.insertBefore(a, mark); });
      nav.removeChild(mark);
    }
    if (location.hash) {
      var target = document.getElementById(location.hash.slice(1));
      if (target) target.scrollIntoView();
    }
  }

  // Expand all / Collapse all (replaces the single toggle some pages had)
  var old = document.getElementById('global-expand');
  if (old) old.parentNode.style.display = 'none';
  Array.prototype.forEach.call(document.querySelectorAll('.page-tools button'), function (b) {
    b.addEventListener('click', function () {
      var open = b.getAttribute('data-tools') === 'expand';
      Array.prototype.forEach.call(document.querySelectorAll('.finding'), function (f) {
        f.classList.toggle('open', open);
      });
    });
  });
})();
</script>
<!-- /page-tools -->
"""


def main():
    pages = sys.argv[1:] or sorted(glob.glob(os.path.join(ROOT, "companies", "*", "index.html"))
                                   + glob.glob(os.path.join(ROOT, "companies", "*", "10q", "index.html")))
    for p in pages:
        s = open(p, encoding="utf-8").read()
        s = re.sub(r"<!-- page-tools:.*?<!-- /page-tools -->\n", "", s, flags=re.S)
        if "</body>" not in s:
            raise SystemExit(f"{p}: no </body>")
        i = s.rindex("</body>")
        s = s[:i] + BLOCK + s[i:]
        open(p, "w", encoding="utf-8").write(s)
        print("page tools:", os.path.relpath(p, ROOT))


if __name__ == "__main__":
    main()
