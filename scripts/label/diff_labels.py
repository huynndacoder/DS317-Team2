#!/usr/bin/env python3
"""Before/after comparison of the two label rule versions, cohort by cohort.

Why this re-derives the old labels instead of diffing a saved copy: a saved copy
of the previous run is only trustworthy for partitions that were never rebuilt.
During development some cohorts are rebuilt before the snapshot is taken, so a
file diff silently reports "no change" for exactly the cohorts most likely to
have changed. The old definition is a pure function of columns that the label
table already carries, so it can be recomputed and cross-checked.

  v2 (previous): a termination counts as inside the window when its
    monthly_reporting_period is at or before the window end; the number of
    months that must be observed is measured up to that reporting month; a
    termination before the window is not special-cased.
  v3 (current): the window-boundary test uses zero_balance_effective_date (the
    date the loan really left surveillance); the coverage test still counts the
    reporting month; a termination before the window cannot licence a negative.

Usage:
  diff_labels.py --validate     # re-derived v2 vs on-disk labels (must match)
  diff_labels.py                # re-derived v2 vs current v3 labels
Both write output/label_tables/label_changes_summary.csv.
"""
import argparse
import os
import pathlib
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[2]
LABELS = ROOT / "output" / "labels"
TABLES = ROOT / "output" / "label_tables"
MEMORY_LIMIT = os.environ.get("DQ_MEMORY_LIMIT", "5GB")
THREADS = os.environ.get("DQ_THREADS", "10")
WORK = pathlib.Path(os.environ.get("DQ_WORK_DIR", ROOT / ".label_tmp"))

WSTART = "((label_window_start//100)*12 + label_window_start%100)"
WEND = "((label_window_end//100)*12 + label_window_end%100)"
TRM = "((termination_month//100)*12 + termination_month%100)"
EFF = "((termination_effective_month//100)*12 + termination_effective_month%100)"


def legacy_status_sql() -> str:
    """The v2 label definition, rebuilt from columns the label table carries."""
    return f"""
    CASE
      WHEN has_event = 1 AND conflict_flag THEN 'unknown'
      WHEN has_event = 1 THEN 'positive'
      WHEN first_observed_month IS NULL THEN 'unknown'
      WHEN conflict_flag THEN 'unknown'
      WHEN termination_code = '01' AND {TRM} <= {WEND} THEN
           CASE WHEN observed_month_count_in_window >=
                     least({WEND}, {TRM}) - {WSTART} + 1
                 AND unknown_status_month_count = 0
                THEN 'negative' ELSE 'unknown' END
      WHEN termination_code IN ('02','03','09','15','16','96')
           AND {TRM} <= {WEND} THEN 'unknown'
      WHEN termination_code IS NOT NULL AND {TRM} <= {WEND} THEN 'unknown'
      WHEN {WEND} <= ((performance_cutoff//100)*12 + performance_cutoff%100)
           AND observed_month_count_in_window = 12
           AND unknown_status_month_count = 0 THEN 'negative'
      ELSE 'unknown'
    END"""


def connect():
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute(f"SET threads={int(THREADS)}")
    con.execute("SET preserve_insertion_order=false")
    WORK.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{(WORK / 'duckdb').as_posix()}'")
    con.execute(f"""CREATE OR REPLACE VIEW lab AS
        SELECT *, {legacy_status_sql()} AS legacy_status
        FROM read_parquet('{(LABELS / 'cohort=*' / 'data.parquet').as_posix()}')""")
    return con


def rebuilt_before_snapshot() -> list[str]:
    """Cohorts already carrying v3 logic, recorded when the snapshot was taken."""
    import json
    f = ROOT / "output" / "labels_v2" / "_rebuilt_before_snapshot.json"
    if not f.exists():
        return []
    return json.loads(f.read_text()).get("rebuilt_before_snapshot", [])


def validate(con):
    """On un-rebuilt partitions the re-derived v2 must reproduce the stored label.

    Cohorts rebuilt with v3 during development are excluded: their stored label is
    v3 by construction, so a difference there is the fix, not a derivation error.
    """
    skip = rebuilt_before_snapshot()
    where = ("WHERE cohort NOT IN (" + ",".join(f"'{q}'" for q in skip) + ")") if skip else ""
    rows = con.execute(f"""
        SELECT count(*) AS n,
               count(*) FILTER (WHERE legacy_status <> label_status) AS mismatch
        FROM lab {where}""").fetchone()
    n, bad = rows
    print(f"re-derived v2 vs stored labels: {n:,} rows on {len(skip)} excluded "
          f"cohort(s), {bad:,} mismatches")
    if skip:
        print("   excluded (already v3):", ", ".join(skip))
    if bad:
        detail = con.execute("""
            SELECT label_status AS stored, legacy_status AS derived, count(*) n
            FROM lab WHERE legacy_status <> label_status GROUP BY 1,2 ORDER BY n DESC
            LIMIT 8""").fetchall()
        for r in detail:
            print("   ", r)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true",
                    help="check the re-derived v2 against the labels already stored")
    ap.add_argument("--quarters", nargs="*")
    args = ap.parse_args()

    con = connect()
    if args.quarters:
        con.execute("CREATE OR REPLACE VIEW scoped AS SELECT * FROM lab WHERE cohort IN "
                    "(" + ",".join(f"'{q}'" for q in args.quarters) + ")")
        base = "scoped"
    else:
        base = "lab"

    if args.validate:
        bad = validate(con)
        return 1 if bad else 0

    ch = con.execute(f"""
        SELECT cohort,
               count(*) AS total_loans,
               count(*) FILTER (WHERE legacy_status = 'positive') AS pos_before,
               count(*) FILTER (WHERE label_status = 'positive') AS pos_after,
               count(*) FILTER (WHERE legacy_status = 'negative') AS neg_before,
               count(*) FILTER (WHERE label_status = 'negative') AS neg_after,
               count(*) FILTER (WHERE legacy_status = 'unknown') AS unk_before,
               count(*) FILTER (WHERE label_status = 'unknown') AS unk_after,
               count(*) FILTER (WHERE legacy_status <> label_status) AS changed_label,
               count(*) FILTER (WHERE legacy_status = 'unknown' AND label_status = 'negative') AS unk_to_neg,
               count(*) FILTER (WHERE legacy_status = 'negative' AND label_status = 'unknown') AS neg_to_unk,
               count(*) FILTER (WHERE legacy_status = 'positive' AND label_status <> 'positive') AS pos_to_other
        FROM {base} GROUP BY 1 ORDER BY 1""").fetchdf()

    # eligibility follows the label, so it is reported alongside rather than
    # recomputed: an eligible loan is still mature + determinate + cohort mature.
    elig = con.execute(f"""
        SELECT cohort,
               count(*) FILTER (WHERE legacy_status <> 'unknown'
                                  AND window_mature AND cohort_mature) AS elig_before,
               count(*) FILTER (WHERE eligible_for_primary_study)       AS elig_after,
               count(*) FILTER (WHERE (legacy_status <> 'unknown'
                                  AND window_mature AND cohort_mature)
                                 <> eligible_for_primary_study)         AS changed_elig
        FROM {base} GROUP BY 1 ORDER BY 1""").fetchdf()
    out = ch.merge(elig, on="cohort")

    out["eligible_event_rate_before_pct"] = (
        100.0 * out["pos_before"].where(out["elig_before"] == 0, out["pos_before"])
        / out["elig_before"].replace(0, float("nan"))).round(4)
    out["eligible_event_rate_after_pct"] = (
        100.0 * out["pos_after"] / out["elig_after"].replace(0, float("nan"))).round(4)

    TABLES.mkdir(parents=True, exist_ok=True)
    dest = TABLES / "label_changes_summary.csv"
    out.to_csv(dest, index=False)

    tot = out[["total_loans", "changed_label", "changed_elig", "unk_to_neg",
               "neg_to_unk", "pos_to_other"]].sum()
    print(out.to_string(index=False))
    print(f"\ntotal loans {tot['total_loans']:,.0f}")
    print(f"changed label {tot['changed_label']:,.0f} | changed eligibility "
          f"{tot['changed_elig']:,.0f}")
    print(f"unknown->negative {tot['unk_to_neg']:,.0f} | negative->unknown "
          f"{tot['neg_to_unk']:,.0f} | positive leaving positive "
          f"{tot['pos_to_other']:,.0f}")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
