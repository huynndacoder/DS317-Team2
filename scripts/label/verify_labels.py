#!/usr/bin/env python
"""Step 6.3 — verify the exported label table against the source parquet.

Independent of the builder: it re-reads the label parquet plus the raw
origination/performance parquet and asserts the invariants the exercise
requires. Exits non-zero if any check fails.

    ./venv/bin/python scripts/label/verify_labels.py
    ./venv/bin/python scripts/label/verify_labels.py --quarters 2020Q1 2005Q3
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import duckdb

import label_rules as R

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "parquet"
LABELS = ROOT / "output" / "labels"
TABLES = ROOT / "output" / "label_tables"
WORK = Path(os.environ.get("DQ_WORK_DIR", ROOT / ".label_tmp"))
MEMORY_LIMIT = os.environ.get("DQ_MEMORY_LIMIT", "3GB")
THREADS = int(os.environ.get("DQ_THREADS", "6"))

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, got, want) -> None:
    ok = got == want
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got!r} want={want!r}")


def connect() -> duckdb.DuckDBPyConnection:
    WORK.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    con.execute(f"SET threads = {THREADS}")
    con.execute(f"SET temp_directory = '{WORK}'")
    con.execute("SET preserve_insertion_order = false")
    con.execute("SET enable_progress_bar = false")
    return con


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarters", nargs="*")
    args = ap.parse_args()

    t0 = time.time()
    con = connect()
    have = {p.name.split("=", 1)[1] for p in LABELS.glob("cohort=*")}
    qs = sorted(args.quarters or have)
    missing = [q for q in qs if q not in have]
    if missing:
        print(f"missing label partitions: {missing}")
        return 1

    print(f"verifying {len(qs)} cohort(s), memory_limit={MEMORY_LIMIT}")

    lab = (f"read_parquet('{LABELS}/cohort=*/data.parquet', "
           f"hive_partitioning=false)")
    con.execute(f"CREATE VIEW labels AS SELECT * FROM {lab} "
                f"WHERE cohort IN ({','.join(repr(q) for q in qs)})")

    # ---- row identity -----------------------------------------------------
    con.execute(f"""CREATE VIEW orig_ids AS
        SELECT loan_id, quarter AS cohort FROM read_parquet(
          '{PARQUET}/orig/quarter=*/data.parquet', hive_partitioning=true)
        WHERE quarter IN ({','.join(repr(q) for q in qs)})""")

    total_orig = con.execute("SELECT count(*) FROM orig_ids").fetchone()[0]
    total_lab = con.execute("SELECT count(*) FROM labels").fetchone()[0]
    total_distinct = con.execute("SELECT count(DISTINCT loan_id) FROM labels").fetchone()[0]

    check("label rows equal origination rows", total_lab, total_orig)
    check("one label row per loan_id", total_lab, total_distinct)
    check("no loan_id outside origination",
          con.execute("SELECT count(*) FROM (SELECT loan_id FROM labels ANTI JOIN orig_ids USING (loan_id))").fetchone()[0], 0)
    check("no origination loan_id missing a label row",
          con.execute("SELECT count(*) FROM (SELECT loan_id FROM orig_ids ANTI JOIN labels USING (loan_id))").fetchone()[0], 0)
    check("cohort agrees with origination partition",
          con.execute("SELECT count(*) FROM labels l JOIN orig_ids o USING (loan_id) WHERE l.cohort <> o.cohort").fetchone()[0], 0)

    # ---- label value integrity -------------------------------------------
    check("label_12m only 0/1/NULL",
          con.execute("SELECT count(*) FROM labels WHERE label_12m IS NOT NULL AND label_12m NOT IN (0,1)").fetchone()[0], 0)
    check("label_status domain",
          con.execute("SELECT count(*) FROM labels WHERE label_status NOT IN ('positive','negative','unknown')").fetchone()[0], 0)
    check("positive <=> label_12m = 1",
          con.execute("SELECT count(*) FROM labels WHERE (label_status='positive') <> (label_12m=1)").fetchone()[0], 0)
    check("negative <=> label_12m = 0",
          con.execute("SELECT count(*) FROM labels WHERE (label_status='negative') <> (label_12m=0)").fetchone()[0], 0)
    check("unknown => label_12m IS NULL",
          con.execute("SELECT count(*) FROM labels WHERE label_status='unknown' AND label_12m IS NOT NULL").fetchone()[0], 0)

    # ---- eligibility ------------------------------------------------------
    check("eligible rows always carry 0/1",
          con.execute("SELECT count(*) FROM labels WHERE eligible_for_primary_study AND label_12m IS NULL").fetchone()[0], 0)
    check("no immature-cohort row is eligible",
          con.execute("SELECT count(*) FROM labels WHERE eligible_for_primary_study AND NOT cohort_mature").fetchone()[0], 0)
    check("no immature-window row is eligible",
          con.execute("SELECT count(*) FROM labels WHERE eligible_for_primary_study AND NOT window_mature").fetchone()[0], 0)
    check("eligible rows have no exclusion reason",
          con.execute("SELECT count(*) FROM labels WHERE eligible_for_primary_study AND primary_exclusion_reason IS NOT NULL").fetchone()[0], 0)
    check("ineligible rows name a reason",
          con.execute("SELECT count(*) FROM labels WHERE NOT eligible_for_primary_study AND primary_exclusion_reason IS NULL").fetchone()[0], 0)

    # ---- event placement --------------------------------------------------
    check("first_event_month inside the label window",
          con.execute("""SELECT count(*) FROM labels
                         WHERE first_event_month IS NOT NULL
                           AND (first_event_month < label_window_start
                                OR first_event_month > label_window_end)""").fetchone()[0], 0)
    check("label window is exactly 12 calendar months",
          con.execute(f"""SELECT count(*) FROM labels
                          WHERE {R.month_index('label_window_end')} - {R.month_index('label_window_start')} <> 11""").fetchone()[0], 0)
    check("window starts at original_first_payment_date",
          con.execute("SELECT count(*) FROM labels WHERE label_window_start <> original_first_payment_date").fetchone()[0], 0)
    check("positive loans have an event month",
          con.execute("SELECT count(*) FROM labels WHERE label_status='positive' AND first_event_month IS NULL").fetchone()[0], 0)
    check("no event month on non-positive loans",
          con.execute("SELECT count(*) FROM labels WHERE label_status<>'positive' AND first_event_month IS NOT NULL").fetchone()[0], 0)

    # ---- independent recomputation of the positive set --------------------
    # Recompute events straight from performance, ignoring the builder entirely.
    # Done one cohort at a time: a single 2.89-billion-row join against the whole
    # label set would spill far past the memory limit, and per-cohort is the same
    # decomposition the builder was validated with.
    # Compare the full (loan_id, first_event_month) SET, not just the count, so a
    # wrong loan being marked positive cannot hide behind a correct total.
    built_positive = con.execute(
        "SELECT count(*) FROM labels WHERE label_status='positive'").fetchone()[0]
    recomputed = 0
    mismatches = 0
    for q in qs:
        # label side: the event months the builder recorded for this cohort
        con.execute(f"""CREATE OR REPLACE TEMP VIEW lab_pos_{q} AS
            SELECT loan_id, first_event_month FROM labels
            WHERE cohort = {q!r} AND label_status='positive'""")
        # independent side: first month each loan crossed the threshold, recomputed
        con.execute(f"""CREATE OR REPLACE TEMP VIEW rec_pos_{q} AS
            WITH o AS (SELECT loan_id, {R.month_index('label_window_start')} AS a
                       FROM labels
                       WHERE cohort = {q!r} AND original_first_payment_date IS NOT NULL),
                 e AS (
                   SELECT o.loan_id,
                          min(p.monthly_reporting_period) AS first_event_month
                   FROM o JOIN read_parquet('{PARQUET}/perf/quarter={q}/data.parquet') p
                     USING (loan_id)
                   WHERE {R.month_index('p.monthly_reporting_period')}
                             BETWEEN o.a AND o.a + {R.WINDOW_MONTHS - 1}
                     AND coalesce({R.status_as_int('p.current_loan_delinquency_status')}
                                  >= {R.EVENT_MIN_STATUS}, FALSE)
                   GROUP BY o.loan_id)
            SELECT loan_id, first_event_month FROM e""")
        recomputed += con.execute(f"SELECT count(*) FROM rec_pos_{q}").fetchone()[0]
        mismatches += con.execute(f"""
            SELECT (SELECT count(*) FROM lab_pos_{q} l
                    LEFT JOIN rec_pos_{q} r USING (loan_id) WHERE r.loan_id IS NULL)
                 + (SELECT count(*) FROM rec_pos_{q} r
                    LEFT JOIN lab_pos_{q} l USING (loan_id) WHERE l.loan_id IS NULL)
                 + (SELECT count(*) FROM lab_pos_{q} l JOIN rec_pos_{q} r USING (loan_id)
                    WHERE l.first_event_month <> r.first_event_month)""").fetchone()[0]
    check("positive count matches independent recomputation", built_positive, recomputed)
    check("positive (loan_id, first_event_month) set matches independent recomputation",
          mismatches, 0)

    # no positive may be contradicted by a fully-observed clean window
    check("positive loans never have 12 clean observed months",
          con.execute("""SELECT count(*) FROM labels
                         WHERE label_status='positive' AND observed_month_count_in_window = 12
                           AND unknown_status_month_count = 0 AND has_event = FALSE""").fetchone()[0], 0)

    # ---- negatives must be justified by observed history -----------------
    check("negative loans have no unknown-status month",
          con.execute("SELECT count(*) FROM labels WHERE label_status='negative' AND unknown_status_month_count > 0").fetchone()[0], 0)
    check("negative loans observed at least as many months as expected",
          con.execute("""SELECT count(*) FROM labels
                         WHERE label_status='negative'
                           AND observed_month_count_in_window < expected_months""").fetchone()[0], 0)
    check("non-terminated negative loans observed all 12 months",
          con.execute("""SELECT count(*) FROM labels
                         WHERE label_status='negative' AND termination_code IS NULL
                           AND observed_month_count_in_window <> 12""").fetchone()[0], 0)
    check("unknown-month counter never exceeds observed months",
          con.execute("""SELECT count(*) FROM labels
                         WHERE unknown_status_month_count > observed_month_count_in_window""").fetchone()[0], 0)

    # a determined verdict must never be labelled "incomplete": an early payoff
    # that was proven negative is not an incomplete record.
    check("negative loans never carry an incompleteness reason",
          con.execute("""SELECT count(*) FROM labels
                         WHERE label_status='negative'
                           AND label_reason IN ('incomplete_window_gap',
                                                'incomplete_before_termination')""").fetchone()[0], 0)
    # a determined NEGATIVE always has label_reason NULL, matured window or not:
    # an early payoff is itself the evidence and must not read as a data gap.
    check("negative loans never carry a label_reason",
          con.execute("""SELECT count(*) FROM labels
                         WHERE label_status='negative'
                           AND label_reason IS NOT NULL""").fetchone()[0], 0)
    check("determined loans with a matured window have no label_reason",
          con.execute("""SELECT count(*) FROM labels
                         WHERE label_status IN ('positive','negative')
                           AND window_mature AND label_reason IS NOT NULL""").fetchone()[0], 0)
    check("every ineligible loan names a concrete exclusion reason",
          con.execute("""SELECT count(*) FROM labels
                         WHERE NOT eligible_for_primary_study
                           AND (primary_exclusion_reason IS NULL
                                OR primary_exclusion_reason='unknown_reason_unclassified')""").fetchone()[0], 0)

    # counters must be integers, not DOUBLE (sum() -> HUGEINT -> Parquet DOUBLE)
    check("all count columns are BIGINT",
          con.execute("""SELECT count(*) FROM (DESCRIBE SELECT * FROM read_parquet('{lab}'))
                         WHERE column_name IN ('observed_month_count_in_window',
                                               'unknown_status_month_count',
                                               'missing_month_count',
                                               'duplicate_row_count',
                                               'n_termination_events')
                           AND column_type <> 'BIGINT'""".format(lab=LABELS)).fetchone()[0], 0)

    # post-window termination must NOT force unknown: a clean, complete window
    # whose loan later terminated (any code) is still negative.
    check("post-window termination never turns a clean window unknown",
          con.execute("""SELECT count(*) FROM labels
                         WHERE label_status='unknown'
                           AND observed_month_count_in_window = 12
                           AND unknown_status_month_count = 0
                           AND has_event = FALSE
                           AND termination_code IS NOT NULL
                           AND ((termination_month//100)*12 + termination_month%100)
                               > ((label_window_end//100)*12 + label_window_end%100)""").fetchone()[0], 0)

    # termination anomalies are surfaced, not silently collapsed (report-only)
    mism = con.execute("""SELECT count(*) FROM labels WHERE termination_date_mismatch""").fetchone()[0]
    multi = con.execute("""SELECT count(*) FROM labels WHERE n_termination_events > 1""").fetchone()[0]
    print(f"  [INFO] termination_date_mismatch rows: {mism:,}   "
          f"multiple_termination_events rows: {multi:,}")

    # ---- unknown is never silently zeroed --------------------------------
    check("sum(pos+neg+unk) equals total",
          con.execute("""SELECT (SELECT count(*) FROM labels WHERE label_status='positive')
                              + (SELECT count(*) FROM labels WHERE label_status='negative')
                              + (SELECT count(*) FROM labels WHERE label_status='unknown')""").fetchone()[0],
          total_lab)
    check("column label_12m has NULLs preserved in parquet",
          con.execute("SELECT count(*) FROM labels WHERE label_12m IS NULL").fetchone()[0],
          con.execute("SELECT count(*) FROM labels WHERE label_status='unknown'").fetchone()[0])

    # ---- summary table consistency ---------------------------------------
    summary = TABLES / "cohort_summary.csv"
    if summary.exists():
        con.execute(f"CREATE VIEW summary AS SELECT * FROM read_csv_auto('{summary}')")
        mismatch = con.execute("""
            SELECT count(*) FROM summary s
            JOIN (SELECT cohort,
                         count(*) AS total_loans,
                         count(*) FILTER (WHERE cohort_mature) AS mature_loans,
                         count(*) FILTER (WHERE label_status='positive') AS positive_count,
                         count(*) FILTER (WHERE label_status='negative') AS negative_count,
                         count(*) FILTER (WHERE label_status='unknown') AS unknown_count,
                         count(*) FILTER (WHERE eligible_for_primary_study) AS eligible_count
                  FROM labels GROUP BY 1) a USING (cohort)
            WHERE s.total_loans <> a.total_loans OR s.positive_count <> a.positive_count
               OR s.negative_count <> a.negative_count OR s.unknown_count <> a.unknown_count
               OR s.eligible_count <> a.eligible_count""").fetchone()[0]
        check("cohort_summary.csv agrees with label table", mismatch, 0)
    else:
        print(f"  [SKIP] {summary} not found")

    # ---- headline numbers ------------------------------------------------
    h = con.execute("""
        SELECT count(*) FILTER (WHERE eligible_for_primary_study),
               count(*) FILTER (WHERE eligible_for_primary_study AND label_status='positive'),
               count(*) FILTER (WHERE label_status='unknown'),
               max(cohort) FILTER (WHERE eligible_for_primary_study AND label_status='positive')
        FROM labels""").fetchone()
    print(f"\neligible={h[0]:,}  eligible_positive={h[1]:,}  "
          f"eligible_rate={100.0 * h[1] / h[0]:.3f}%" if h[0] else "\neligible=0")
    print(f"unknown={h[2]:,}  last cohort with an eligible positive={h[3]}")

    out = {"quarters": qs, "checks_passed": len(PASS), "checks_failed": len(FAIL),
           "failed": FAIL, "eligible": h[0], "eligible_positive": h[1],
           "unknown": h[2], "last_positive_cohort": h[3],
           "elapsed_seconds": round(time.time() - t0, 1)}
    TABLES.mkdir(parents=True, exist_ok=True)
    (TABLES / "verification.json").write_text(json.dumps(out, indent=1))

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed  ({out['elapsed_seconds']}s)")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())