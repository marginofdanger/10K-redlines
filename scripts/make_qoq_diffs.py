"""Generate quarter-over-quarter unified diffs for 10-Q section files.

For each section, diffs consecutive periods in the quarterly sequence. The
annual 10-K is interleaved at fiscal-year boundaries (after Q3) so the diff
chain shows what the annual filing changed before the next Q1 picks it up.

Usage: python scripts/make_qoq_diffs.py <ticker>
Reads  companies/<ticker>/10q/sections/{period}_{section}.txt
       companies/<ticker>/sections/fy{year}_{section}.txt   (10-K baselines)
Writes companies/<ticker>/10q/diffs/{prev}_to_{curr}_{section}.diff
"""
import difflib, os, re, sys, glob

def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()

def main(ticker):
    base = os.path.join("companies", ticker)
    qdir = os.path.join(base, "10q", "sections")
    kdir = os.path.join(base, "sections")
    out_dir = os.path.join(base, "10q", "diffs")
    os.makedirs(out_dir, exist_ok=True)

    quarters = sorted({re.match(r"(fy\d{4}q\d)_", os.path.basename(p)).group(1)
                       for p in glob.glob(os.path.join(qdir, "fy*q*_mda.txt"))})
    # Interleave the 10-K after each fiscal year's Q3
    sequence = []
    for q in quarters:
        year = int(q[2:6])
        sequence.append((q, qdir))
        if q.endswith("q3") and os.path.exists(os.path.join(kdir, f"fy{year}_mda.txt")):
            sequence.append((f"fy{year}", kdir))  # 10-K for that fiscal year

    # "contingencies" covers filers (e.g. AMZN) whose Part II Item 1 is only a
    # pointer to the commitments-and-contingencies note; tickers without those
    # section files simply produce no diffs for it.
    sections = ["mda", "risk_factors", "legal_proceedings", "contingencies"]
    for sn in sections:
        for (p1, d1), (p2, d2) in zip(sequence, sequence[1:]):
            a = load(os.path.join(d1, f"{p1}_{sn}.txt"))
            b = load(os.path.join(d2, f"{p2}_{sn}.txt"))
            if a is None or b is None:
                continue
            label1 = p1 if d1 == qdir else f"{p1}-10K"
            label2 = p2 if d2 == qdir else f"{p2}-10K"
            diff = list(difflib.unified_diff(a, b, fromfile=label1, tofile=label2, n=2, lineterm=""))
            out = os.path.join(out_dir, f"{label1}_to_{label2}_{sn}.diff")
            with open(out, "w", encoding="utf-8") as f:
                f.write("\n".join(diff))
            print(f"{out}: {len(diff):,} lines")

if __name__ == "__main__":
    main(sys.argv[1])
