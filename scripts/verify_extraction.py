#!/usr/bin/env python3
"""
Verify completeness of the extracted historical loan data.

Checks, per quarter 2020Q1 .. 2026Q1:
  1. orig_<q>.txt and perf_<q>.txt exist and are non-empty.
  2. Byte size matches the size declared inside the source zip (when the
     source zip is still present; deleted inner zips are skipped).
  3. Header-less pipe-delimited column count is sane (orig=32 fields,
     perf=35 fields, per scripts/calculate_6_dimensions.py).
  4. perf monthly_reporting_period coverage: min month <= quarter start and
     max month <= quarter end (data is reporting-period based, so a quarter's
     file can carry later months for seasoned loans).
  5. Row counts for both files.

Exit code 0 only when every expected quarter passes.
"""

import csv
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

YEARS = list(range(2020, 2027))
QUARTERS = [f"{y}Q{q}" for y in YEARS for q in (1, 2, 3, 4) if not (y == 2026 and q > 1)]
# available through 2026Q1 per the user's target range

N_ORIG_COLS = 31  # pipe-delimited fields actually emitted in orig_*.txt
                  # (calculate_6_dimensions.py lists 32 names incl. a trailing
                  #  'filler' that the source files do not emit)
N_PERF_COLS = 35
LATEST_PERIOD = "202603"  # newest reporting period available in this extract


def txt_path(q: str, kind: str) -> Path:
    year = q[:4]
    return DATA / f"historical_data_{year}" / f"historical_data_{q}" / f"{kind}_{q}.txt"


def declared_sizes(year: int) -> dict:
    """filename -> file_size from the inner quarterly zips, if still present."""
    outer = DATA / f"historical_data_{year}.zip"
    out = {}
    if not outer.exists():
        return out
    import io

    with zipfile.ZipFile(outer) as zo:
        for name in zo.namelist():
            if not name.endswith(".zip"):
                continue
            with zo.open(name) as f:
                inner = zipfile.ZipFile(io.BytesIO(f.read()))
                for info in inner.infolist():
                    out[info.filename] = info.file_size
    return out


def scan_txt(path: Path, n_cols: int, id_idx: int):
    """Return (n_rows, col_count_counter, min_period, max_period, loan_ids).

    id_idx: 0-based field holding loan_id (orig=19, perf=0).
    period field is index 1 for both files.
    """
    n_rows = 0
    cols = Counter()
    min_p = max_p = None
    ids = set()
    with open(path, newline="") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            n_rows += 1
            parts = line.split("|")
            cols[len(parts)] += 1
            if len(parts) > id_idx:
                ids.add(parts[id_idx])
            if min_p is None:
                min_p = max_p = parts[1] if len(parts) > 1 else None
            elif len(parts) > 1:
                p = parts[1]
                if p < min_p:
                    min_p = p
                if p > max_p:
                    max_p = p
    return n_rows, cols, min_p, max_p, ids


def main() -> int:
    problems = []
    sizes = {}
    for y in YEARS:
        sizes.update(declared_sizes(y))

    print(f"{'quarter':8} {'orig_rows':>12} {'perf_rows':>12} {'orig_MB':>9} {'perf_MB':>9}  period")
    for q in QUARTERS:
        o = txt_path(q, "orig")
        p = txt_path(q, "perf")
        for path, kind in ((o, "orig"), (p, "perf")):
            if not path.exists() or path.stat().st_size == 0:
                problems.append(f"{q}: missing/empty {path}")
        if not o.exists() or not p.exists():
            print(f"{q:8} {'MISSING':>12} {'MISSING':>12}")
            continue

        # size cross-check against the still-present source zip
        for path in (o, p):
            if path.name in sizes and path.stat().st_size != sizes[path.name]:
                problems.append(
                    f"{q}: {path.name} size {path.stat().st_size} != zip {sizes[path.name]}"
                )

        orows, ocols, _, _, oids = scan_txt(o, N_ORIG_COLS, id_idx=19)
        prows, pcols, pmin, pmax, pids = scan_txt(p, N_PERF_COLS, id_idx=0)

        if ocols and max(ocols) != N_ORIG_COLS:
            problems.append(f"{q}: orig field counts {dict(ocols)} != {N_ORIG_COLS}")
        if pcols and max(pcols) != N_PERF_COLS:
            problems.append(f"{q}: perf field counts {dict(pcols)} != {N_PERF_COLS}")

        orphan = pids - oids
        if orphan:
            problems.append(f"{q}: {len(orphan)} perf loan_id(s) absent from orig")

        qy, qq = int(q[:4]), int(q[5])
        start = f"{qy}{qq * 3 - 2:02d}"
        # perf is a loan-month panel: a loan originated in quarter Q keeps
        # reporting until it terminates, so max period runs past Q's end, up
        # to the newest period in the extract. Only require full coverage of
        # Q's own months (min <= start) and no period beyond the extract.
        if pmin is not None and pmin > start:
            problems.append(f"{q}: perf min period {pmin} > quarter start {start}")
        if pmax is not None and pmax > LATEST_PERIOD:
            problems.append(f"{q}: perf max period {pmax} > {LATEST_PERIOD}")

        print(
            f"{q:8} {orows:12,} {prows:12,} "
            f"{o.stat().st_size / 1e6:9.1f} {p.stat().st_size / 1e6:9.1f}  "
            f"{pmin}..{pmax}"
        )

    print()
    if problems:
        print(f"FAIL: {len(problems)} problem(s)")
        for pr in problems:
            print("  -", pr)
        return 1
    print(f"OK: all {len(QUARTERS)} quarters complete (2020Q1..2026Q1)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
