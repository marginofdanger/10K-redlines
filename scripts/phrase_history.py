"""Phrase / sentence history across every downloaded period of one company.

  python3 scripts/phrase_history.py companies/meta "third-party AI token costs"
  python3 scripts/phrase_history.py companies/meta --sentence "We may not be successful in our AI initiatives ..."
  python3 scripts/phrase_history.py companies/meta --sentence "..." --section risk_factors

Answers: in which periods (10-K and 10-Q, in filing order) does the phrase occur, in which
sections, how many times; for a sentence, the nearest sentence in every period with a
similarity ratio, so "first time", "new" and "unchanged since" claims can be checked.
"""
import argparse, difflib, glob, os, re, sys

SENT_SPLIT = re.compile(r"(?<=[.!?;])\s+(?=[A-Z“\"(•])")
NUM = re.compile(r"\$?\d[\d,.]*%?")


def periods(company):
    """[(label, dir)] in filing order: fyYYYYqN before fyYYYY (10-K) before fy(YYYY+1)q1."""
    out = []
    for d in (os.path.join(company, "sections"), os.path.join(company, "10q", "sections")):
        for p in glob.glob(os.path.join(d, "fy*_*.txt")):
            m = re.match(r"(fy(\d{4})(?:q(\d))?)_", os.path.basename(p))
            if m:
                out.append((m.group(1), d, int(m.group(2)), int(m.group(3) or 4)))
    seen, seq = set(), []
    for lab, d, y, q in sorted(out, key=lambda t: (t[2], t[3])):
        if lab not in seen:
            seen.add(lab)
            seq.append((lab, d))
    return seq


def norm(s):
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()


def load_sections(d, label, only=None):
    secs = {}
    for p in sorted(glob.glob(os.path.join(d, f"{label}_*.txt"))):
        name = os.path.basename(p)[len(label) + 1:-4]
        if name == "full" or (only and name != only):
            continue
        with open(p, encoding="utf-8") as f:
            secs[name] = [l for l in f.read().splitlines() if l.strip()]
    return secs


def sentences(lines):
    for para in lines:
        for s in SENT_SPLIT.split(para):
            if len(s) > 20:
                yield s


def phrase_timeline(company, phrase, only=None):
    q = norm(phrase)
    rows = []
    for label, d in periods(company):
        hits = {}
        for name, lines in load_sections(d, label, only).items():
            n = sum(norm(l).count(q) for l in lines)
            if n:
                hits[name] = n
        rows.append((label, hits))
    first = next((lab for lab, h in rows if h), None)
    print(f'PHRASE "{phrase}"')
    for lab, h in rows:
        print(f"  {lab:<10} {'  '.join(f'{k}x{v}' for k, v in h.items()) or '-'}")
    print("  first appears:", first or "never", "| present in",
          f"{sum(1 for _, h in rows if h)}/{len(rows)} periods")


def best_match(target, cands):
    tn = norm(target)
    tw = set(re.findall(r"[a-z]{4,}", tn))
    best, best_r = None, 0.0
    for s in cands:
        sn = norm(s)
        if sn == tn:
            return s, 1.0
        sw = set(re.findall(r"[a-z]{4,}", sn))
        if not tw or len(tw & sw) / len(tw) < 0.4:
            continue
        sm = difflib.SequenceMatcher(None, tn, sn, autojunk=False)
        if sm.quick_ratio() <= best_r:
            continue
        r = sm.ratio()
        if r > best_r:
            best, best_r = s, r
    return best, best_r


def sentence_timeline(company, sentence, only=None, thresh=0.6):
    print(f'SENTENCE "{sentence[:100]}..."' if len(sentence) > 100 else f'SENTENCE "{sentence}"')
    prev = None
    first = None
    for label, d in periods(company):
        cands = []
        for name, lines in load_sections(d, label, only).items():
            cands += [(name, s) for s in sentences(lines)]
        m, r = best_match(sentence, [s for _, s in cands])
        sec = next((n for n, s in cands if s is m), "")
        if r >= 0.999:
            status = "identical"
        elif r >= thresh:
            status = f"variant r={r:.2f}"
        else:
            status = "absent"
        if r >= thresh and first is None:
            first = label
        changed = ""
        if r >= thresh and prev is not None and norm(prev) != norm(m):
            changed = "  <- wording changed from prior period"
        print(f"  {label:<10} {status:<14} {sec:<22}{changed}")
        if r >= thresh and (prev is None or norm(prev) != norm(m)):
            print(f"             {m[:300]}")
        prev = m if r >= thresh else prev
    print("  first appears:", first or "never")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company")
    ap.add_argument("phrase", nargs="?")
    ap.add_argument("--sentence")
    ap.add_argument("--section")
    a = ap.parse_args()
    if a.sentence:
        sentence_timeline(a.company, a.sentence, a.section)
    elif a.phrase:
        phrase_timeline(a.company, a.phrase, a.section)


if __name__ == "__main__":
    main()
