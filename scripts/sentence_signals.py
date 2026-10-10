"""Sentence-level wording signals for one transition, ranked by salience.

  python3 scripts/sentence_signals.py companies/meta/10q fy2026q1 fy2026q2 [--section mda] [--top 25]
  python3 scripts/sentence_signals.py companies/meta fy2024 fy2025

Pairs paragraphs the way make_diffs does, then splits changed paragraphs into sentences,
aligns sentences, and labels each changed/added/removed sentence with wording signals:
  certainty   modal ladder moved (may < could < likely/should < expect/intend/plan < will/have)
  realized    hypothetical -> actual ("could pressure" -> "have pressured")
  quant       numbers added / removed / changed (de-quantification is the bearish-ish one)
  hedge       hedge phrase added / removed ("currently", "at this time", "if at all"...)
  scope       quantifier drift ("all" -> "substantially all" -> "most" -> "certain")
  degree      intensity drift ("significant" -> "substantial", "modest" -> "meaningful")
  condition   conditional / caveat clause added or dropped ("if", "unless", "subject to")
  named       proper noun added or removed (laws, counterparties, products)
  denamed     a named party becomes "a customer" / "a third party" / "certain"
  persistence how many prior periods the before-sentence stood unchanged
Each signal carries a direction about the WORDING: + firmer/more disclosure, - softer/less.
"""
import argparse, difflib, glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_diffs as md  # noqa: E402
import phrase_history as ph  # noqa: E402

SENT_SPLIT = re.compile(r"(?<=[.!?;])\s+(?=[A-Z“\"(•])")
WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*|\$?\d[\d,.]*%?")

# certainty ladder: higher = firmer commitment / more actual
LADDER = {"might": 1, "possible": 1, "possibly": 1, "may": 2, "could": 2, "potentially": 2, "would": 2,
          "likely": 3, "should": 3, "believe": 3, "believes": 3, "anticipate": 3, "anticipates": 3,
          "expect": 4, "expects": 4, "intend": 4, "intends": 4, "plan": 4, "plans": 4, "committed": 4,
          "will": 5, "are": 5, "is": 5, "have": 5, "has": 5, "had": 5, "did": 5, "were": 5, "was": 5,
          "continue": 4, "continues": 4}
REALIZED_FROM = {"could", "may", "might", "would", "can"}
REALIZED_TO = {"have", "has", "had", "did", "were", "was", "are", "is", "experienced", "resulted", "pressured",
               "impacted", "affected", "incurred", "recorded", "occurred"}
HEDGES = ["currently", "at this time", "in the near term", "near-term", "if at all", "from time to time",
          "there can be no assurance", "no assurance", "cannot guarantee", "we cannot predict", "approximately",
          "generally", "primarily", "in part", "to some extent", "to the extent", "among other things",
          "we believe", "in our judgment", "for the foreseeable future", "at least", "up to", "or more"]
SCOPE = {"all": 5, "substantially all": 4, "most": 3, "the majority of": 3, "many": 2, "a number of": 2,
         "several": 2, "some": 2, "certain": 1, "a portion of": 1, "a few": 1, "limited": 1}
DEGREE = {"immaterial": 0, "modest": 1, "limited": 1, "minor": 1, "meaningful": 2, "significant": 3,
          "significantly": 3, "material": 3, "materially": 3, "substantial": 4, "substantially": 4,
          "severe": 5, "severely": 5}
CONDITION = ["if ", "unless", "subject to", "to the extent", "provided that", "depending on", "assuming",
             "in the event", "there can be no assurance", "however"]
DENAME = re.compile(r"\b(a|an|one|certain|some|other)\s+(customer|customers|supplier|suppliers|third part(y|ies)|"
                    r"counterpart(y|ies)|partner|partners|vendor|vendors|lender|lenders|governmental|regulator)",
                    re.I)
NOISE = re.compile(r"\b(three|six|nine|twelve) months ended|\bfiscal (year|quarter)s?\b|\bas of (january|february|"
                   r"march|april|may|june|july|august|september|october|november|december)\b|\bnote \d+\b|"
                   r"\bitem \d+[a-c]?\b|\bpart [iv]+\b|see\b", re.I)
ROLL_WORDS = {"three", "six", "nine", "twelve", "months", "ended", "respectively", "period", "periods", "same",
              "and", "year", "quarter", "fiscal", "compared", "the", "of", "in", "for", "as", "to", "or",
              "primarily", "mostly", "mainly", "largely", "due", "increase", "increases", "an", "a"}
CAP_STOP = {"january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
            "november", "december", "our", "the", "total", "notes", "note", "item", "part", "company", "we",
            "these", "this", "there", "such", "during", "cash", "net", "revenue", "income", "fiscal", "year",
            "quarterly", "report", "form", "table", "consolidated", "condensed", "statements", "financial"}
PERIOD_TOKEN = re.compile(r"\b(20\d\d|january|february|march|april|may|june|july|august|september|october|"
                          r"november|december|first|second|third|fourth|three|six|nine|q[1-4])\b", re.I)


ABBR = re.compile(r"\b(U\.S\.|U\.K\.|E\.U\.|Inc\.|Co\.|Corp\.|Ltd\.|No\.|vs\.|e\.g\.|i\.e\.|Mr\.|Ms\.|Dr\.|St\.)")


def is_table_row(s):
    letters = sum(c.isalpha() for c in s)
    numeric = len(re.findall(r"\(?\$?\s?\d[\d,.]*\)?%?", s))
    return "|" in s or letters < 0.45 * max(len(s), 1) or (numeric >= 2 and not re.search(r"[.;:]\s*$", s)
                                                           and re.search(r"[\d%)]\s*$", s) is not None)


def sentences(para):
    if is_table_row(para):
        return []
    protected = ABBR.sub(lambda m: m.group(0).replace(".", "\x00"), para)
    return [s.replace("\x00", ".") for s in SENT_SPLIT.split(protected) if len(s) > 15]


def toks(s):
    return [t.lower() for t in WORD.findall(s)]


def month_safe(s):
    """Tokens, with the month 'May' (capital M, followed by a day or year) kept out of the modal lexicon."""
    s = re.sub(r"\bMay(?=\s+\d)", "MAYMONTH", s)
    return toks(s)


def diff_words(a, b):
    """(deleted words, inserted words) as lists, from a word-level diff."""
    aw, bw = month_safe(a), month_safe(b)
    dl, ins = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, aw, bw, autojunk=False).get_opcodes():
        if op in ("delete", "replace"):
            dl += aw[i1:i2]
        if op in ("insert", "replace"):
            ins += bw[j1:j2]
    return dl, ins


def nums(s):
    """Quantities only: money, percentages, scaled numbers, and large counts; years and dates excluded."""
    found = re.findall(r"\$\s?\d[\d,.]*(?:\s?(?:billion|million|thousand))?|\d[\d,.]*\s?%|"
                       r"\b\d[\d,.]*\s?(?:billion|million|thousand|basis points|bps)\b|\b\d{1,3}(?:,\d{3})+\b|"
                       r"\b\d+\.\d+\b", s)
    return [f for f in found if not re.fullmatch(r"(19|20)\d\d", f.strip("$ "))]


def phrase_hits(s, phrases):
    sl = " " + ph.norm(s) + " "
    return {p for p in phrases if " " + p + " " in sl or (" " + p) in sl and p.endswith(" ")}


def classify(a, b):
    """Signals for a changed sentence pair (a may be None = added, b None = removed)."""
    sig, score = [], 0.0
    if a is None or b is None:
        s = b if a is None else a
        kind = "ADDED" if a is None else "REMOVED"
        n = nums(s)
        score += 2.0 + (1.5 if n else 0) + (0.5 if re.search(r"\b(expect|anticipate|will|plan)\b", s, re.I) else 0)
        if NOISE.search(s) and not n:
            score -= 1.0
        if DENAME.search(s):
            sig.append("unnamed party")
        if a is not None:
            score += 1.0  # deletions are under-read
            if n:
                sig.append(f"quant: {len(n)} figure(s) no longer stated (-)")
        return kind, sig, score
    dl, ins = diff_words(a, b)
    dset, iset = set(dl), set(ins)
    forward = bool(re.search(r"\b(expect|expects|anticipate|anticipates|guidance|outlook|will|plan|plans|"
                             r"intend|intends|estimate|estimates|target|targets)\b", a + " " + b, re.I))
    # roll-forward: once period words, figures and synonyms are removed nothing changed
    residual = [t for t in dl + ins if not (PERIOD_TOKEN.match(t) or re.match(r"\$?\d", t) or t in ROLL_WORDS)]
    if not residual and dl + ins:
        na, nb = nums(a), nums(b)
        if set(na) != set(nb) and forward:
            return "CHANGED", [f"guidance figures: {', '.join(na[:3])} -> {', '.join(nb[:3])}"], 4.0
        if set(na) != set(nb):
            return "ROLLED", [f"figures: {', '.join(na[:3])} -> {', '.join(nb[:3])}"], 0.5
        return "ROLLED", [], 0.0
    # certainty ladder
    da = [t for t in dl if t in LADDER]
    ib = [t for t in ins if t in LADDER]
    if da and ib:
        lo, hi = max(da, key=LADDER.get), max(ib, key=LADDER.get)
        d = LADDER[hi] - LADDER[lo]
        if d:
            sig.append(f"certainty: {lo} -> {hi} ({'firmer +' if d > 0 else 'weaker -'})")
            score += 3.0
    if (dset & REALIZED_FROM) and (iset & REALIZED_TO):
        sig.append("realized: hypothetical -> actual (risk has happened)")
        score += 3.0
    elif (iset & REALIZED_FROM) and (dset & REALIZED_TO):
        sig.append("de-realized: actual -> hypothetical")
        score += 2.5
    # quantification
    na, nb = nums(a), nums(b)
    if na and not nb:
        sig.append(f"quant: removed ({', '.join(na[:3])}) (-)")
        score += 3.0
    elif nb and not na:
        sig.append(f"quant: added ({', '.join(nb[:3])}) (+)")
        score += 2.5
    elif set(na) != set(nb):
        sig.append(f"{'guidance ' if forward else ''}figures: {', '.join(x for x in na if x not in nb)[:60]} -> "
                   f"{', '.join(x for x in nb if x not in na)[:60]}")
        score += 3.0 if forward else 0.3
    # hedges
    ha, hb = phrase_hits(a, HEDGES), phrase_hits(b, HEDGES)
    if hb - ha:
        sig.append(f"hedge added: {', '.join(sorted(hb - ha))} (-)")
        score += 2.0
    if ha - hb:
        sig.append(f"hedge dropped: {', '.join(sorted(ha - hb))} (+)")
        score += 2.0
    # scope quantifiers
    sa, sb = phrase_hits(a, SCOPE), phrase_hits(b, SCOPE)
    if sa != sb and (sa - sb) and (sb - sa):
        x, y = max(sa - sb, key=SCOPE.get), max(sb - sa, key=SCOPE.get)
        if SCOPE[x] != SCOPE[y]:
            sig.append(f"scope: {x} -> {y} ({'narrower -' if SCOPE[y] < SCOPE[x] else 'wider +'})")
            score += 2.5
    ga, gb = {t for t in dl if t in DEGREE}, {t for t in ins if t in DEGREE}
    if ga and gb:
        x, y = max(ga, key=DEGREE.get), max(gb, key=DEGREE.get)
        if DEGREE[x] != DEGREE[y]:
            sig.append(f"degree: {x} -> {y} ({'stronger' if DEGREE[y] > DEGREE[x] else 'milder'})")
            score += 2.0
    ca, cb = phrase_hits(a, CONDITION), phrase_hits(b, CONDITION)
    if cb - ca:
        sig.append(f"condition added: {', '.join(sorted(cb - ca))} (-)")
        score += 1.5
    if ca - cb:
        sig.append(f"condition dropped: {', '.join(sorted(ca - cb))} (+)")
        score += 1.5
    # names
    capa = {w for w in re.findall(r"(?<![.!?]\s)(?<!^)\b[A-Z][A-Za-z]{2,}\b", a) if w.lower() not in CAP_STOP}
    capb = {w for w in re.findall(r"(?<![.!?]\s)(?<!^)\b[A-Z][A-Za-z]{2,}\b", b) if w.lower() not in CAP_STOP}
    newn = {w for w in capb - capa if w.lower() in iset and w.lower() not in LADDER}
    gone = {w for w in capa - capb if w.lower() in dset}
    if newn:
        sig.append(f"named: +{', '.join(sorted(newn))[:80]}")
        score += 1.5
    if gone and DENAME.search(b) and not DENAME.search(a):
        sig.append(f"de-named: {', '.join(sorted(gone))[:60]} -> generic party (-)")
        score += 3.0
    elif gone:
        sig.append(f"name dropped: {', '.join(sorted(gone))[:60]}")
        score += 1.5
    # tense: future/intent words replaced by past
    if {"will", "expect", "expects", "plan", "plans", "intend", "intends"} & dset and \
            {"have", "has", "had", "completed", "began", "launched", "commenced"} & iset:
        sig.append("tense: intent -> done (+)")
        score += 2.0
    # weighting: guidance sentences and long edits matter more; cross-reference edits less
    if re.search(r"\b(expect|anticipate|guidance|outlook)\b", b, re.I) and nums(b):
        score += 1.0
    if NOISE.search(" ".join(dl + ins)):
        score -= 1.0
    score += min(len(dl) + len(ins), 20) / 10.0
    return "CHANGED", sig, score


def align_sentences(pa, pb):
    sa, sb = sentences(pa), sentences(pb)
    na, nb = [ph.norm(s) for s in sa], [ph.norm(s) for s in sb]
    sm = difflib.SequenceMatcher(None, na, nb, autojunk=False)
    pairs = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        rem, add = list(range(i1, i2)), list(range(j1, j2))
        used = set()
        for i in rem:
            best, br = None, 0.0
            for j in add:
                if j in used:
                    continue
                r = difflib.SequenceMatcher(None, na[i], nb[j], autojunk=False).ratio()
                if r > br:
                    best, br = j, r
            if best is not None and br >= 0.5:
                used.add(best)
                pairs.append((sa[i], sb[best]))
            else:
                pairs.append((sa[i], None))
        pairs += [(None, sb[j]) for j in add if j not in used]
    return pairs


def elsewhere(s, pool):
    """Is this sentence (or a >=0.9 variant) present anywhere in the other period's section?"""
    n = ph.norm(s)
    if n in pool:
        return True
    words = set(re.findall(r"[a-z]{5,}", n))
    for p in pool:
        if abs(len(p) - len(n)) < 0.3 * len(n) and words and len(words & set(re.findall(r"[a-z]{5,}", p))) >= 0.8 * len(words):
            if difflib.SequenceMatcher(None, n, p, autojunk=False).ratio() >= 0.9:
                return True
    return False


def persistence(company, sentence, section):
    """Periods in which the sentence stood identical before the 'to' period (uses phrase_history index)."""
    run, first = 0, None
    for label, d in ph.periods(company):
        secs = ph.load_sections(d, label, section)
        found = any(ph.norm(sentence) == ph.norm(s) for lines in secs.values() for s in ph.sentences(lines))
        if found:
            run += 1
            first = first or label
        else:
            run, first = 0, None
    return run, first


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("p1")
    ap.add_argument("p2")
    ap.add_argument("--section")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--no-persistence", action="store_true")
    a = ap.parse_args()
    seq = {lab: d for lab, d, _ in md.sequence(a.folder)} if False else None
    company = a.folder[:-4] if a.folder.rstrip("/").endswith("10q") else a.folder
    dirs = {lab: d for lab, d in ph.periods(company)}
    d1, d2 = dirs[a.p1], dirs[a.p2]
    names = {os.path.basename(p)[len(a.p2) + 1:-4] for p in glob.glob(os.path.join(d2, f"{a.p2}_*.txt"))}
    rows = []
    for sn in sorted(names - {"full"}):
        if a.section and sn != a.section:
            continue
        x, y = md.load(os.path.join(d1, f"{a.p1}_{sn}.txt")), md.load(os.path.join(d2, f"{a.p2}_{sn}.txt"))
        if x is None or y is None:
            continue
        x_sents = {ph.norm(s) for p in x for s in sentences(p)}
        y_sents = {ph.norm(s) for p in y for s in sentences(p)}
        # recover paragraph pairs from make_diffs pairing by re-running its matcher
        sm = difflib.SequenceMatcher(None, [md.norm(s) for s in x], [md.norm(s) for s in y], autojunk=False)
        removed, added = [], []
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op in ("delete", "replace"):
                removed += list(range(i1, i2))
            if op in ("insert", "replace"):
                added += list(range(j1, j2))
        used = set()
        for i in removed:
            best, br = None, 0.0
            for j in added:
                if j in used or not (0.4 < (len(y[j]) + 1) / (len(x[i]) + 1) < 2.5):
                    continue
                s2 = difflib.SequenceMatcher(None, md.norm(x[i]), md.norm(y[j]), autojunk=False)
                if s2.quick_ratio() <= br:
                    continue
                r = s2.ratio()
                if r > br:
                    best, br = j, r
            if best is not None and br >= 0.45:
                used.add(best)
                if br < 0.999:
                    for pa, pb in align_sentences(x[i], y[best]):
                        kind, sig, sc = classify(pa, pb)
                        if pb is None and elsewhere(pa, y_sents):
                            kind, sc = "MOVED", 0.2
                        if pa is None and elsewhere(pb, x_sents):
                            kind, sc = "MOVED", 0.2
                        rows.append((sc, sn, kind, sig, pa, pb))
            else:
                for s in sentences(x[i]):
                    kind, sig, sc = classify(s, None)
                    if elsewhere(s, y_sents):
                        kind, sc = "MOVED", 0.2  # still in the new section: not a deletion
                    rows.append((sc, sn, kind, sig, s, None))
        for j in added:
            if j not in used:
                for s in sentences(y[j]):
                    kind, sig, sc = classify(None, s)
                    if elsewhere(s, x_sents):
                        kind, sc = "MOVED", 0.2  # was already in the old section: not new
                    rows.append((sc, sn, kind, sig, None, s))
    seen, deduped = {}, []
    for r in rows:
        key = (ph.norm(r[4] or ""), ph.norm(r[5] or ""))
        if key in seen:
            seen[key][1].append(r[1])
            continue
        seen[key] = (r, [])
        deduped.append(r)
    rows = [(sc, sn + ("" if not seen[(ph.norm(pa or ""), ph.norm(pb or ""))][1] else
                       " (+" + ",".join(seen[(ph.norm(pa or ""), ph.norm(pb or ""))][1]) + ")"), k, sg, pa, pb)
            for sc, sn, k, sg, pa, pb in deduped]
    rows.sort(key=lambda r: -r[0])
    n_rolled = sum(1 for r in rows if r[2] in ("ROLLED", "MOVED"))
    print(f"{a.folder} {a.p1} -> {a.p2}: {len(rows)} sentence-level changes, {n_rolled} roll-forwards or within-section moves hidden")
    shown = 0
    for sc, sn, kind, sig, pa, pb in rows:
        if kind in ("ROLLED", "MOVED") or shown >= a.top:
            continue
        shown += 1
        pers = ""
        if pa and not a.no_persistence and kind != "ADDED":
            run, first = persistence(company, pa, sn)
            if run >= 2:
                pers = f" | before-sentence unchanged for {run} periods (since {first})"
        print(f"\n[{sc:4.1f}] {sn} {kind}  {'; '.join(sig) or '(wording edit)'}{pers}")
        if pa:
            print(f"   - {pa[:400]}")
        if pb:
            print(f"   + {pb[:400]}")


if __name__ == "__main__":
    main()
