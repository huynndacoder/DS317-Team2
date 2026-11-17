#!/usr/bin/env python
"""Extract real-loan evidence for each label outcome (step 6.2).

For a handful of loans per outcome this prints the origination fields and the
actual performance history inside the label window, so a human can check the
assigned label against the raw monthly rows. The point is to inspect edge
cases, not to sample randomly.

    ./venv/bin/python scripts/label/label_examples.py
    ./venv/bin/python scripts/label/label_examples.py --cohorts 2020Q1 2005Q3 --per-group 3
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb

import label_rules as R

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "parquet"
LABELS = ROOT / "output" / "labels"
TABLES = ROOT / "output" / "label_tables"
WORK = Path(os.environ.get("DQ_WORK_DIR", ROOT / ".label_tmp"))

# outcome groups to illustrate; each is (label_status, extra predicate, note)
GROUPS = [
    ("positive", "TRUE", "event inside the window (any window)"),
    ("positive", "observed_month_count_in_window = 12", "event with a full window"),
    ("positive", "observed_month_count_in_window < 12", "event with a partial window"),
    ("negative", "termination_code IS NULL", "full window, never delinquent"),
    ("negative", "termination_code = '01'", "early voluntary payoff, clean history"),
    ("unknown", "label_reason = 'terminated_sale'", "terminated by loan sale"),
    ("unknown", "label_reason = 'no_performance'", "no performance rows at all"),
    ("unknown", "label_reason = 'incomplete_window_gap'", "gap inside the window"),
    ("unknown", "label_reason = 'incomplete_before_termination'",
     "payoff with an incomplete history"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohorts", nargs="*", help="restrict to these cohorts")
    ap.add_argument("--per-group", type=int, default=1)
    args = ap.parse_args()

    WORK.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.execute(f"SET memory_limit='{os.environ.get('DQ_MEMORY_LIMIT', '3GB')}'")
    con.execute(f"SET threads={os.environ.get('DQ_THREADS', '6')}")
    con.execute(f"SET temp_directory='{WORK}'")
    con.execute("SET preserve_insertion_order=false")

    lab_glob = f"'{LABELS}/cohort=*/data.parquet'"
    con.execute(f"CREATE VIEW labels AS SELECT * FROM read_parquet({lab_glob})")

    TABLES.mkdir(parents=True, exist_ok=True)
    out = TABLES / "label_evidence.txt"
    lines: list[str] = []
    csv_rows: list[tuple] = []   # one row per (group, loan); written to CSV too

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    used: set[str] = set()   # keep the groups from all showing the same loan
    for status, pred, note in GROUPS:
        cohort_filter = ""
        if args.cohorts:
            cohort_filter = "AND cohort IN (" + ",".join(repr(c) for c in args.cohorts) + ")"
        skip = ""
        if used:
            skip = "AND loan_id NOT IN (" + ",".join(repr(x) for x in sorted(used)) + ")"
        picks = con.execute(f"""
            SELECT loan_id, cohort, cohort_mature, window_mature FROM labels
            WHERE label_status = '{status}' AND ({pred}) {cohort_filter} {skip}
            -- prefer fully-matured cohorts (long observed history, verifiable
            -- against the raw monthly rows) over the newest, partially
            -- observed vintages
            ORDER BY cohort_mature DESC, window_mature DESC, cohort DESC, loan_id
            LIMIT {args.per_group}
        """).fetchall()
        if not picks:
            emit(f"\n### {status} — {note}\n  (no such loan in the selected cohorts)")
            continue
        for loan_id, cohort, _cm, _wm in picks:
            used.add(loan_id)
            emit(f"\n{'=' * 78}")
            emit(f"### {status.upper()} — {note}")
            emit(f"loan_id={loan_id}  cohort={cohort}")

            row = con.execute("""
                SELECT original_first_payment_date, label_window_start, label_window_end,
                       performance_cutoff, label_status, label_12m, label_reason,
                       first_event_month, termination_code, termination_month,
                       observed_month_count_in_window, unknown_status_month_count,
                       missing_month_count, window_mature, cohort_mature,
                       eligible_for_primary_study, primary_exclusion_reason,
                       first_observed_month, last_observed_month
                FROM labels WHERE loan_id = ?
            """, [loan_id]).fetchone()
            keys = ["original_first_payment_date", "label_window_start", "label_window_end",
                    "performance_cutoff", "label_status", "label_12m", "label_reason",
                    "first_event_month", "termination_code", "termination_month",
                    "observed_month_count_in_window", "unknown_status_month_count",
                    "missing_month_count", "window_mature", "cohort_mature",
                    "eligible_for_primary_study", "primary_exclusion_reason",
                    "first_observed_month", "last_observed_month"]
            emit("  label: " + "  ".join(f"{k}={v}" for k, v in zip(keys, row)))
            # row starts at original_first_payment_date, so loan_id/cohort must be
            # prepended explicitly or every column after it shifts
            csv_rows.append((loan_id, cohort, f"{status}: {note}") + tuple(row))

            orig = con.execute(f"""
                SELECT loan_purpose, original_loan_term, original_upb, ltv, cltv,
                       original_interest_rate, credit_score, property_state
                FROM read_parquet('{PARQUET}/orig/quarter={cohort}/data.parquet')
                WHERE loan_id = ?
            """, [loan_id]).fetchone()
            emit("  origination: " + "  ".join(
                f"{k}={v}" for k, v in
                zip(["loan_purpose", "term", "upb", "ltv", "cltv", "rate", "fico", "state"],
                    orig)))

            fpd, wstart = row[0], row[1]
            hist = con.execute(f"""
                SELECT monthly_reporting_period, current_loan_delinquency_status, loan_age,
                       modification_flag, zero_balance_code
                FROM read_parquet('{PARQUET}/perf/quarter={cohort}/data.parquet')
                WHERE loan_id = ?
                  AND {R.month_index('monthly_reporting_period')}
                      BETWEEN {R.month_index(str(wstart))}
                          AND {R.month_index(str(wstart))} + {R.WINDOW_MONTHS - 1}
                ORDER BY monthly_reporting_period
            """, [loan_id]).fetchall()
            emit(f"  performance inside the window ({len(hist)} month(s) present):")
            for mrp, st, age, mod, zb in hist:
                mark = " <- EVENT" if _is_event(st) else ""
                emit(f"    {mrp}  status={st!s:<4} loan_age={age!s:<4} "
                     f"mod={mod!s:<4} zbc={zb!s:<4}{mark}")
            tail = con.execute(f"""
                SELECT monthly_reporting_period, current_loan_delinquency_status, zero_balance_code
                FROM read_parquet('{PARQUET}/perf/quarter={cohort}/data.parquet')
                WHERE loan_id = ?
                  AND {R.month_index('monthly_reporting_period')}
                      > {R.month_index(str(wstart))} + {R.WINDOW_MONTHS - 1}
                ORDER BY monthly_reporting_period LIMIT 6
            """, [loan_id]).fetchall()
            if tail:
                emit("  first rows AFTER the window (must not affect the label):")
                for mrp, st, zb in tail:
                    emit(f"    {mrp}  status={st!s:<4} zbc={zb!s:<4}")

    out.write_text("\n".join(lines) + "\n")

    # the CSV is the same evidence in tabular form, produced here so the two
    # artefacts can never disagree about which loan illustrates which outcome
    import csv
    cols = ["group", "original_first_payment_date", "label_window_start", "label_window_end",
            "performance_cutoff", "label_status", "label_12m", "label_reason",
            "first_event_month", "termination_code", "termination_month",
            "observed_month_count_in_window", "unknown_status_month_count",
            "missing_month_count", "window_mature", "cohort_mature",
            "eligible_for_primary_study", "primary_exclusion_reason",
            "first_observed_month", "last_observed_month"]
    csv_path = TABLES / "label_examples.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["loan_id", "cohort"] + cols)
        for r in csv_rows:
            w.writerow(list(r))

    print(f"written: {out}")
    print(f"written: {csv_path}  ({len(csv_rows)} rows)")
    return 0


def _is_event(status) -> bool:
    if status == R.EVENT_STATUS_RA:
        return True
    try:
        return int(status) >= R.EVENT_MIN_STATUS
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())