"""Generate year-over-year unified diffs for 10-K section files.

Diffs every section file present for consecutive fiscal years (fy{year}_{section}.txt),
so company-specific sections (e.g. JPM's split MD&A, MSFT's contingencies note)
are picked up without configuration. The *_full.txt files are skipped.

Usage: python scripts/make_yoy_diffs.py <ticker>
Reads  companies/<ticker>/sections/fy{year}_{section}.txt
Writes companies/<ticker>/diffs/fy{prev}_to_fy{curr}_{section}.diff
"""
import difflib, glob, os, re, sys

def load(path):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()

def main(ticker):
    base = os.path.join("companies", ticker)
    sdir = os.path.join(base, "sections")
    out_dir = os.path.join(base, "diffs")
    os.makedirs(out_dir, exist_ok=True)

    files = {}
    for p in glob.glob(os.path.join(sdir, "fy*_*.txt")):
        m = re.match(r"fy(\d{4})_(.+)\.txt$", os.path.basename(p))
        if m and m.group(2) != "full":
            files.setdefault(m.group(2), {})[int(m.group(1))] = p

    for sn, by_year in sorted(files.items()):
        years = sorted(by_year)
        for y1, y2 in zip(years, years[1:]):
            diff = list(difflib.unified_diff(load(by_year[y1]), load(by_year[y2]),
                                             fromfile=f"fy{y1}", tofile=f"fy{y2}", n=2, lineterm=""))
            out = os.path.join(out_dir, f"fy{y1}_to_fy{y2}_{sn}.diff")
            with open(out, "w", encoding="utf-8") as f:
                f.write("\n".join(diff))
            print(f"{out}: {len(diff):,} lines, {sum(len(l) for l in diff):,} chars")

if __name__ == "__main__":
    main(sys.argv[1])
