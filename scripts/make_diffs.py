"""Word-level redlines between consecutive filings, for analysis.

  python scripts/make_diffs.py companies/<t>        # annual: fy2024 -> fy2025 ...
  python scripts/make_diffs.py companies/<t>/10q    # quarterly, with the 10-K interleaved
                                                    # after each fiscal Q3
  options: --last N   only the last N transitions (default: all)

Reads  <folder>/sections/<period>_<section>.txt  (10-Q chains also read ../sections/)
Writes <folder>/diffs/<from>_to_<to>_<section>.diff         unified line diff
       <folder>/diffs/<from>_to_<to>_<section>.redline.txt  paragraph-aligned, word-level

Each paragraph is one line in the section files, so a line diff marks a whole
paragraph as changed when one word moved. The redline pairs changed paragraphs
and marks words: [-deleted-] {+inserted+}. Moved paragraphs are reported as
MOVED instead of a delete plus an add. The header carries the counts the
analysis cares about: paragraphs added / removed / changed / moved, and modal
and hedging words gained or lost.
"""
import argparse, difflib, glob, os, re

MODALS = ["may", "might", "could", "would", "will", "should", "must", "expect", "expects",
          "anticipate", "anticipates", "believe", "believes", "intend", "intends", "plan", "plans",
          "likely", "unlikely", "possible", "potential", "significant", "material", "materially",
          "substantial", "substantially", "uncertain", "uncertainty", "risk", "risks"]
WORD = re.compile(r"\S+")
NUM = re.compile(r"[\d][\d,.]*")


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return [l for l in f.read().splitlines() if l.strip()]


def norm(s):
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()


def word_redline(a, b):
    aw, bw = WORD.findall(a), WORD.findall(b)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, aw, bw, autojunk=False).get_opcodes():
        if op == "equal":
            seg = aw[i1:i2]
            out.append(" ".join(seg) if len(seg) <= 24 else " ".join(seg[:10] + ["..."] + seg[-10:]))
        if op in ("delete", "replace"):
            out.append("[-" + " ".join(aw[i1:i2]) + "-]")
        if op in ("insert", "replace"):
            out.append("{+" + " ".join(bw[j1:j2]) + "+}")
    return " ".join(out)


def counts(lines):
    c = {}
    words = WORD.findall(" ".join(lines))
    for k, raw in enumerate(words):
        w = raw.strip(".,;:()\"'").lower()
        nxt = words[k + 1] if k + 1 < len(words) else ""
        if raw[:1] == "M" and w == "may" and re.match(r"\d", nxt):
            continue  # the month
        if w in MODALS:
            c[w] = c.get(w, 0) + 1
    return c


def redline(a, b, label_a, label_b, section):
    """Pair removed and added paragraphs by similarity; report the rest as added/removed/moved."""
    sm = difflib.SequenceMatcher(None, [norm(x) for x in a], [norm(x) for x in b], autojunk=False)
    removed, added = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("delete", "replace"):
            removed += list(range(i1, i2))
        if op in ("insert", "replace"):
            added += list(range(j1, j2))

    entries, used = [], set()
    na, nb = {i: norm(a[i]) for i in removed}, {j: norm(b[j]) for j in added}
    exact = {}
    for j in added:
        exact.setdefault(nb[j], []).append(j)
    for i in removed:
        best, best_r = None, 0.0
        for j in exact.get(na[i], []):
            if j not in used:
                best, best_r = j, 1.0
                break
        for j in ([] if best is not None else added):
            if j in used or not (0.4 < (len(nb[j]) + 1) / (len(na[i]) + 1) < 2.5):
                continue
            sm2 = difflib.SequenceMatcher(None, na[i], nb[j], autojunk=False)
            if sm2.real_quick_ratio() <= best_r or sm2.quick_ratio() <= best_r:
                continue
            r = sm2.ratio()
            if r > best_r:
                best, best_r = j, r
        if best is not None and best_r >= 0.999:
            used.add(best)
            entries.append((best, "MOVED", f"paragraph {i + 1} -> {best + 1}: {a[i][:160]}"))
        elif best is not None and best_r >= 0.45:
            used.add(best)
            kind = "ROLLED" if NUM.sub("#", a[i]) == NUM.sub("#", b[best]) else "CHANGED"
            entries.append((best, kind, word_redline(a[i], b[best])))
        else:
            entries.append((i, "REMOVED", a[i]))
    for j in added:
        if j not in used:
            entries.append((j, "ADDED", b[j]))

    tally = {k: sum(1 for e in entries if e[1] == k) for k in ("ADDED", "REMOVED", "CHANGED", "MOVED", "ROLLED")}
    ca, cb = counts(a), counts(b)
    shifts = {w: cb.get(w, 0) - ca.get(w, 0) for w in set(ca) | set(cb) if cb.get(w, 0) != ca.get(w, 0)}
    head = [f"REDLINE {section}: {label_a} -> {label_b}",
            f"paragraphs {len(a)} -> {len(b)}; words {len(WORD.findall(' '.join(a))):,} -> "
            f"{len(WORD.findall(' '.join(b))):,}",
            "added {ADDED}, removed {REMOVED}, changed {CHANGED}, moved {MOVED}, "
            "numbers-only {ROLLED} (listed last)".format(**tally),
            ""]
    ordered = sorted(entries, key=lambda e: e[0])
    body = [f"## {kind}\n{text}\n" for _, kind, text in ordered if kind != "ROLLED"]
    rolled = [text for _, kind, text in ordered if kind == "ROLLED"]
    if rolled:
        # same words, new figures: usually a roll-forward, but a figure that moved a lot is still a finding
        body.append("## NUMBERS ONLY (wording unchanged)\n" + "\n".join(f"- {t}" for t in rolled) + "\n")
    return "\n".join(head + body), tally


def sequence(folder):
    sec = os.path.join(folder, "sections")
    if os.path.basename(os.path.normpath(folder)) != "10q":
        years = sorted({re.match(r"(fy\d{4})_", os.path.basename(p)).group(1)
                        for p in glob.glob(os.path.join(sec, "fy*_*.txt"))
                        if re.match(r"fy\d{4}_", os.path.basename(p))})
        return [(y, sec, y) for y in years]
    kdir = os.path.join(os.path.dirname(os.path.normpath(folder)), "sections")
    quarters = sorted({re.match(r"(fy\d{4}q\d)_", os.path.basename(p)).group(1)
                       for p in glob.glob(os.path.join(sec, "fy*q*_*.txt"))})
    seq = []
    for q in quarters:
        seq.append((q, sec, q))
        year = int(q[2:6])
        if q.endswith("q3") and glob.glob(os.path.join(kdir, f"fy{year}_*.txt")):
            seq.append((f"fy{year}", kdir, f"fy{year}-10K"))
    return seq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--last", type=int, default=0)
    a = ap.parse_args()
    seq = sequence(a.folder)
    pairs = list(zip(seq, seq[1:]))[-a.last:] if a.last else list(zip(seq, seq[1:]))
    out_dir = os.path.join(a.folder, "diffs")
    os.makedirs(out_dir, exist_ok=True)
    for (p1, d1, l1), (p2, d2, l2) in pairs:
        names = {os.path.basename(p)[len(p2) + 1:-4] for p in glob.glob(os.path.join(d2, f"{p2}_*.txt"))}
        for sn in sorted(names - {"full"}):
            x, y = load(os.path.join(d1, f"{p1}_{sn}.txt")), load(os.path.join(d2, f"{p2}_{sn}.txt"))
            if x is None or y is None:
                continue
            stem = os.path.join(out_dir, f"{l1}_to_{l2}_{sn}")
            with open(stem + ".diff", "w", encoding="utf-8") as f:
                f.write("\n".join(difflib.unified_diff(x, y, fromfile=l1, tofile=l2, n=2, lineterm="")))
            text, t = redline(x, y, l1, l2, sn)
            with open(stem + ".redline.txt", "w", encoding="utf-8") as f:
                f.write(text)
            print(f"{l1} -> {l2} {sn:<22} +{t['ADDED']} -{t['REMOVED']} ~{t['CHANGED']} moved {t['MOVED']} "
                  f"numbers-only {t['ROLLED']}")


if __name__ == "__main__":
    main()
