"""Generate 10-K redline dashboard HTML from analysis.json files -- matching META/PGR style."""
import json
import sys
import html

def esc(s):
    return html.escape(str(s))

# Color mapping for finding group sections
SECTION_COLORS = {
    'Business': 'var(--accent)',
    'Business Overview': 'var(--accent)',
    'Risk Factors': 'var(--red)',
    'MD&A': 'var(--orange)',
    'Legal': 'var(--pink)',
    'Legal Proceedings': 'var(--pink)',
    'Forward Guidance': 'var(--cyan)',
    'Key Forward Guidance': 'var(--cyan)',
}

def build_dashboard(json_path, out_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    co = esc(data['company'])
    co_name = esc(data['company_name'])
    fy_end = esc(data['fiscal_year_end'])
    transitions = data['transitions']
    deep_signals = data.get('deep_signals', [])
    themes = data.get('themes', [])

    total_findings = sum(len(t.get('findings', [])) for t in transitions)
    first_fy = transitions[0]['from_year']
    last_fy = transitions[-1]['to_year']

    # Sidebar nav items
    sidebar_yoy = []
    for t in transitions:
        to_id = t['to_year'].lower()
        sidebar_yoy.append(f'  <a class="nav-item" href="#yoy-{to_id}">{esc(t["from_year"])} &rarr; {esc(t["to_year"])}</a>')

    sidebar_signals = []
    for i, s in enumerate(deep_signals, 1):
        sig_id = f"sig-{i}"
        sidebar_signals.append(f'  <a class="nav-item" href="#{sig_id}">{esc(s["title"])}</a>')

    # Era cards
    era_cards = []
    for t in transitions:
        era_cards.append(f'''  <div class="era-card">
    <div class="years">{esc(t["from_year"])} &rarr; {esc(t["to_year"])}</div>
    <h3>{esc(t["to_year"])}</h3>
    <p>{esc(t["summary"])}</p>
  </div>''')

    # Transitions
    trans_parts = []
    for t in transitions:
        to_id = t['to_year'].lower()
        metrics = t.get('headline_metrics', {})
        metric_strs = []
        for k, v in metrics.items():
            label = k.replace('_', ' ').title()
            metric_strs.append(f'{label}: {esc(v)}')
        sub_line = ' | '.join(metric_strs)

        # Group findings by section
        sections = {}
        for f in t.get('findings', []):
            sec = f.get('section', 'Other')
            if sec not in sections:
                sections[sec] = []
            sections[sec].append(f)

        groups_html = []
        for sec_name, findings in sections.items():
            dot_color = SECTION_COLORS.get(sec_name, 'var(--text-dim)')
            findings_html = []
            for f in findings:
                ftype = f.get('type', 'Signal')
                tag_class = f'tag-{ftype.lower()}'
                findings_html.append(f'''  <div class="finding"><div class="finding-header" onclick="toggle(this)"><span class="arrow">&#9654;</span><span class="title">{esc(f.get("title",""))}</span><span class="tag {tag_class}">{esc(ftype)}</span></div><div class="finding-body">{esc(f.get("detail",""))}</div></div>''')
            groups_html.append(f'''<div class="finding-group">
  <h3><span class="dot" style="background:{dot_color}"></span> {esc(sec_name)}</h3>
{''.join(findings_html)}
</div>''')

        trans_parts.append(f'''<div class="transition-header" id="yoy-{to_id}">
  <h2>{esc(t["from_year"])} &rarr; {esc(t["to_year"])}</h2>
  <div class="sub">{sub_line}</div>
</div>

{''.join(groups_html)}''')

    # Deep signals
    signal_parts = []
    for i, s in enumerate(deep_signals, 1):
        sig_id = f"sig-{i}"
        signal_parts.append(f'''<div class="signal-card full" id="{sig_id}">
  <h3><span class="num">{i}</span> {esc(s["title"])}</h3>
  <p>{esc(s["detail"])}</p>
</div>''')

    # Themes
    theme_parts = []
    for th in themes:
        theme_parts.append(f'''<div class="signal-card">
  <h3>{esc(th["title"])}</h3>
  <p>{esc(th["detail"])}</p>
</div>''')

    page = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{co} 10-K Redline Analysis | {first_fy}-{last_fy}</title>
<style>
:root {{
  --bg: #ffffff;
  --surface: #f6f8fa;
  --surface2: #eef1f5;
  --border: #d1d9e0;
  --text: #1f2328;
  --text-dim: #59636e;
  --accent: #0969da;
  --accent2: #1a7f37;
  --red: #cf222e;
  --orange: #9a6700;
  --purple: #8250df;
  --pink: #bf3989;
  --cyan: #0e7c6b;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.7;
  overflow-x: hidden;
}}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

/* Sidebar Nav */
.sidebar {{
  position: fixed;
  left: 0; top: 0; bottom: 0;
  width: 250px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  z-index: 100;
  padding: 20px 0;
  scrollbar-width: thin;
  scrollbar-color: var(--border) var(--surface);
}}
.sidebar-header {{
  padding: 0 20px 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
}}
.sidebar-header h1 {{ font-size: 15px; font-weight: 700; color: var(--accent); letter-spacing: 0.5px; }}
.sidebar-header .sub {{ font-size: 11px; color: var(--text-dim); margin-top: 4px; }}
.nav-section {{
  padding: 8px 20px 4px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-dim);
  font-weight: 600;
}}
.nav-item {{
  display: block;
  padding: 5px 20px 5px 28px;
  font-size: 13px;
  color: var(--text-dim);
  transition: all 0.15s;
  border-left: 2px solid transparent;
}}
.nav-item:hover {{
  color: var(--text);
  background: rgba(9,105,218,0.08);
  border-left-color: var(--accent);
  text-decoration: none;
}}

/* Main */
.main {{
  margin-left: 250px;
  padding: 32px 48px 80px;
  max-width: 1000px;
}}

/* Hero */
.hero {{ margin-bottom: 40px; padding-bottom: 28px; border-bottom: 1px solid var(--border); }}
.hero h1 {{
  font-size: 30px; font-weight: 800;
  color: var(--text);
  margin-bottom: 8px;
}}
.hero .tagline {{ font-size: 15px; color: var(--text-dim); max-width: 700px; }}
.hero .source {{ font-size: 12px; color: var(--text-dim); margin-top: 12px; opacity: 0.7; }}

/* Era Cards */
.eras {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin: 28px 0; }}
.era-card {{
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: 18px; position: relative; overflow: hidden;
}}
.era-card::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--border); }}
.era-card .years {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; color: var(--text-dim); }}
.era-card h3 {{ font-size: 15px; font-weight: 700; margin-bottom: 6px; }}
.era-card p {{ font-size: 12px; color: var(--text-dim); line-height: 1.5; }}

/* Transition header */
.transition-header {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 24px;
  margin: 48px 0 24px;
  scroll-margin-top: 20px;
}}
.transition-header:first-of-type {{ margin-top: 0; }}
.transition-header h2 {{ font-size: 20px; font-weight: 700; }}
.transition-header .sub {{ font-size: 13px; color: var(--text-dim); margin-top: 4px; }}
.expand-btn {{
  background: none;
  border: 1px solid var(--border);
  color: var(--text-dim);
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}}
.expand-btn:hover {{
  color: var(--text);
  border-color: var(--text-dim);
}}

/* Finding groups */
.finding-group {{ margin-bottom: 28px; }}
.finding-group h3 {{
  font-size: 15px; font-weight: 600; margin-bottom: 14px;
  display: flex; align-items: center; gap: 8px;
}}
.finding-group h3 .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}

/* Findings */
.finding {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; margin-bottom: 10px; overflow: hidden;
}}
.finding-header {{
  padding: 12px 18px; cursor: pointer;
  display: flex; align-items: flex-start; gap: 10px; user-select: none;
}}
.finding-header:hover {{ background: rgba(0,0,0,0.02); }}
.finding-header .arrow {{
  color: var(--text-dim); font-size: 11px; margin-top: 3px;
  transition: transform 0.2s; flex-shrink: 0;
}}
.finding.open .finding-header .arrow {{ transform: rotate(90deg); }}
.finding-header .title {{ font-size: 14px; font-weight: 600; }}
.finding-header .tag {{
  font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.5px; flex-shrink: 0; margin-left: auto;
}}
.tag-new {{ background: rgba(26,127,55,0.1); color: var(--accent2); }}
.tag-removed {{ background: rgba(207,34,46,0.1); color: var(--red); }}
.tag-changed {{ background: rgba(154,103,0,0.1); color: var(--orange); }}
.tag-signal {{ background: rgba(130,80,223,0.1); color: var(--purple); }}
.finding-body {{
  display: none; padding: 0 18px 14px 40px;
  font-size: 13px; color: var(--text-dim); line-height: 1.7;
}}
.finding.open .finding-body {{ display: block; }}
.finding-body blockquote {{
  border-left: 3px solid var(--accent); padding: 8px 14px; margin: 10px 0;
  background: rgba(9,105,218,0.06); border-radius: 0 6px 6px 0;
  font-style: italic; color: var(--text);
}}
.finding-body strong {{ color: var(--text); }}

/* Section headings */
.section {{ margin-bottom: 56px; padding-top: 32px; border-top: 2px solid var(--border); scroll-margin-top: 20px; }}
.section:first-of-type {{ border-top: none; padding-top: 0; }}
.section-header {{
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 20px; padding-bottom: 10px; border-bottom: 1px solid var(--border);
}}
.section-header h2 {{ font-size: 22px; font-weight: 700; }}

/* Signal Cards */
.signal-grid {{ display: grid; grid-template-columns: 1fr; gap: 16px; margin-bottom: 24px; }}
.signal-card {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 20px;
}}
.signal-card.full {{ grid-column: 1 / -1; }}
.signal-card h3 {{
  font-size: 15px; font-weight: 700; margin-bottom: 10px;
  display: flex; align-items: center; gap: 8px;
}}
.signal-card h3 .num {{
  background: var(--accent); color: var(--bg); font-size: 11px;
  width: 22px; height: 22px; display: inline-flex; align-items: center;
  justify-content: center; border-radius: 50%; font-weight: 700;
}}
.signal-card p, .signal-card li {{ font-size: 13px; color: var(--text-dim); line-height: 1.6; }}
.signal-card ul {{ padding-left: 18px; margin-top: 8px; }}
.signal-card li {{ margin-bottom: 5px; }}

/* Responsive */
@media (max-width: 1100px) {{
  .eras {{ grid-template-columns: 1fr 1fr; }}
}}
@media (max-width: 768px) {{
  .sidebar {{ display: none; }}
  .main {{ margin-left: 0; padding: 20px; }}
  .eras {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>

<nav class="sidebar">
  <div class="sidebar-header">
    <h1>{co} 10-K REDLINES</h1>
    <div class="sub">{first_fy} - {last_fy} | SEC EDGAR</div>
  </div>
  <div class="nav-section">Overview</div>
  <a class="nav-item" href="#hero-section">Executive Summary</a>

  <div class="nav-section">Year-Over-Year</div>
{chr(10).join(sidebar_yoy)}

  <div class="nav-section">Deep Signals</div>
{chr(10).join(sidebar_signals)}

  <div class="nav-section">Synthesis</div>
  <a class="nav-item" href="#themes">Themes</a>
</nav>

<div class="main">

<!-- Hero -->
<div class="hero" id="hero-section">
  <h1>{co_name} 10-K Redline Analysis</h1>
  <div class="tagline">Year-over-year textual analysis of SEC filings reveals strategic pivots, risk signals, and forward guidance tells invisible to surface-level reading. {total_findings} findings across {len(transitions)} transitions, {len(deep_signals)} deep signals, {len(themes)} themes.</div>
  <div class="source">Source: SEC EDGAR | Fiscal Year End: {fy_end} | {first_fy}&ndash;{last_fy} | Analysis: March 2026</div>
</div>

<!-- Strategic Eras -->
<div class="eras">
{chr(10).join(era_cards)}
</div>

<!-- Year-Over-Year Redlines -->
<div style="display:flex;justify-content:flex-end;margin-bottom:8px">
  <button class="expand-btn" onclick="toggleAll()" id="global-expand">Expand all</button>
</div>

{chr(10).join(trans_parts)}

<!-- Deep Signals -->
<div class="section" id="signals-section">
  <div class="section-header">
    <h2>Deep Signals</h2>
  </div>
  <div class="signal-grid">
{chr(10).join(signal_parts)}
  </div>
</div>

<!-- Themes -->
<div class="section" id="themes">
  <div class="section-header">
    <h2>Themes</h2>
  </div>
  <div class="signal-grid">
{chr(10).join(theme_parts)}
  </div>
</div>

</div>

<script>
function toggle(el) {{ el.closest('.finding').classList.toggle('open'); }}
let allOpen = false;
function toggleAll() {{
  allOpen = !allOpen;
  document.querySelectorAll('.finding').forEach(f => {{
    if (allOpen) f.classList.add('open');
    else f.classList.remove('open');
  }});
  document.getElementById('global-expand').textContent = allOpen ? 'Collapse all' : 'Expand all';
}}
</script>
</body>
</html>'''

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(page)
    print(f"Built {out_path} ({len(page):,} bytes, {total_findings} findings)")

if __name__ == '__main__':
    json_path = sys.argv[1]
    out_path = sys.argv[2]
    build_dashboard(json_path, out_path)
