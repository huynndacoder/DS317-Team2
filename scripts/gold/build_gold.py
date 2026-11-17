#!/usr/bin/env python3
"""Build the Gold table: origination features + the 12-month label, one row per loan.

Design decisions, all deliberate:

* **Allow-list, not deny-list.** Features are named explicitly in FEATURES below.
  Anything not on the list does not reach Gold, so a column added to the raw data
  (or a performance column that happens to be joined nearby) can never leak into
  the feature matrix by default. Deny-lists fail open; allow-lists fail closed.

* **Performance columns are never features.** The label is built from monthly
  delinquency history; any post-origination column is future information. The
  synthetic dataset carries a `performance_columns_used_for_label` audit record so
  the exclusion is documented rather than implied.

* **Audit is a separate row set.** `gold_<version>/features/` holds loan_id + the
  permitted features only. `gold_<version>/audit/` holds the label, the exclusion
  reason, the quality flags and the join diagnostics. Training code joins only the
  features; the audit stays out of the feature matrix by construction, not by
  remembering to drop columns.

* **The join must be 1:1.** Checked, not assumed: both sides are asserted unique on
  loan_id and the join is asserted not to change the row count.

* **Immature cohorts are excluded from Gold, not labelled.** A row whose label is
  not determinate, or whose window has not closed, is written to the audit set with
  a reason and left out of the feature set. Silently including them with label NULL
  is how NULL-as-zero bugs reach training.

Usage:
  build_gold.py --version v1              # all mature cohorts
  build_gold.py --version v1 --dry-run    # checks only, writes nothing
"""
import argparse
import json
import os
import pathlib
import sys
import time

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[2]
PARQUET = ROOT / "parquet"
LABELS = ROOT / "output" / "labels"
OUT = ROOT / "output" / "gold"
MEMORY_LIMIT = os.environ.get("DQ_MEMORY_LIMIT", "5GB")
THREADS = os.environ.get("DQ_THREADS", "10")
WORK = pathlib.Path(os.environ.get("DQ_WORK_DIR", ROOT / ".label_tmp"))

# ---------------------------------------------------------------------------
# The feature allow-list. Origination-only, and every entry is usable at the
# moment of origination (no post-application information).
# ---------------------------------------------------------------------------
FEATURES = [
    # loan terms
    "original_upb",
    "original_loan_term",
    "original_interest_rate",
    "ltv",
    "cltv",
    "dti",
    "mi_percentage",
    "number_of_units",
    "number_of_borrowers",
    # borrower and credit
    "credit_score",
    "vantage_score_4",
    "first_time_homebuyer_flag",
    # product and property
    "channel",
    "product_type",
    "loan_purpose",
    "property_type",
    "property_state",
    "occupancy_status",
    "prepayment_penalty_flag",
    "interest_only_indicator",
    "super_conforming_flag",
    "harp_indicator",
    "valuation_method",
    "seller_name",
    # calendar placement, expressed as the origination quarter so the model never
    # sees the label window itself
    "cohort",
]

# Deliberately excluded, with the reason recorded in the manifest.
EXCLUDED = {
    "loan_id": "identifier, kept as a key not a feature",
    "first_payment_date": "determines the label window start; leaks timing",
    "maturity_date": "collinear with first_payment_date and term",
    "postal_code": "high-cardinality identifier-like field; property_state covers geography",
    "msa": "23% null, and identifier-like; decide separately before using",
    "pre_harp_loan_id": "94% null, identifier",
    "program_indicator": "97% null",
    "quarter": "physical partition column; duplicate of cohort",
}

# Audit columns: never in the feature matrix.
AUDIT = [
    "cohort",
    "label_status",
    "label_12m",
    "eligible_for_primary_study",
    "original_first_payment_date",
    "label_window_start",
    "label_window_end",
    "performance_cutoff",
    "window_mature",
    "cohort_mature",
    "first_event_month",
    "termination_code",
    "termination_month",
    "observed_month_count_in_window",
    "missing_month_count",
    "primary_exclusion_reason",
    "label_reason",
    "quality_flags",
]


def connect():
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute(f"SET threads={int(THREADS)}")
    con.execute("SET preserve_insertion_order=false")
    WORK.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{(WORK / 'duckdb').as_posix()}'")
    return con


def check(con, name, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got} want={want}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    con = connect()
    dest = OUT / f"gold_{args.version}"
    print(f"gold {args.version} -> {dest}")

    con.execute(f"""CREATE OR REPLACE VIEW labels AS
        SELECT * FROM read_parquet('{(LABELS / 'cohort=*' / 'data.parquet').as_posix()}')""")
    con.execute(f"""CREATE OR REPLACE VIEW orig AS
        SELECT * FROM read_parquet('{(PARQUET / 'orig' / 'quarter=*' / 'data.parquet').as_posix()}',
                                   hive_partitioning=true)""")

    # ---- schema guards -------------------------------------------------
    have_orig = {r[0] for r in con.execute("DESCRIBE SELECT * FROM orig").fetchall()}
    have_lab = {r[0] for r in con.execute("DESCRIBE SELECT * FROM labels").fetchall()}
    missing = [f for f in FEATURES if f not in have_orig and f != "cohort"]
    print("\n== schema ==")
    ok = True
    ok &= check(con, "every allow-listed feature exists in origination",
                len(missing), 0)
    if missing:
        print("     missing:", missing)
    # `cohort` is legitimately present on both sides: it is the physical quarter
    # partition in origination, aliased into the label table. Any *other* name
    # shared between the label table and the feature list would be a leak.
    shared = [f for f in FEATURES if f in have_lab and f not in have_orig and f != "cohort"]
    ok &= check(con, "no feature is a performance column", len(shared), 0)
    if shared:
        print("     leaked:", shared)
    ok &= check(con, "label_12m present in the label table",
                int("label_12m" in have_lab), 1)

    # ---- join cardinality ----------------------------------------------
    print("\n== join cardinality ==")
    n_lab = con.execute("SELECT count(*) FROM labels").fetchone()[0]
    n_lab_ids = con.execute("SELECT count(DISTINCT loan_id) FROM labels").fetchone()[0]
    n_orig = con.execute("SELECT count(*) FROM orig").fetchone()[0]
    n_orig_ids = con.execute("SELECT count(DISTINCT loan_id) FROM orig").fetchone()[0]
    ok &= check(con, "label side is unique on loan_id", n_lab - n_lab_ids, 0)
    ok &= check(con, "origination side is unique on loan_id", n_orig - n_orig_ids, 0)
    ok &= check(con, "label rows equal origination rows", n_lab, n_orig)
    orphan_lab = con.execute(
        "SELECT count(*) FROM labels l ANTI JOIN orig o USING (loan_id)").fetchone()[0]
    orphan_orig = con.execute(
        "SELECT count(*) FROM orig o ANTI JOIN labels l USING (loan_id)").fetchone()[0]
    ok &= check(con, "labels with no origination row", orphan_lab, 0)
    ok &= check(con, "origination rows with no label", orphan_orig, 0)

    # ---- label domain ---------------------------------------------------
    print("\n== label domain ==")
    bad_domain = con.execute("""
        SELECT count(*) FROM labels
        WHERE label_status NOT IN ('positive','negative','unknown')
           OR (label_status = 'positive' AND label_12m <> 1)
           OR (label_status = 'negative' AND label_12m <> 0)
           OR (label_status = 'unknown'  AND label_12m IS NOT NULL)""").fetchone()[0]
    ok &= check(con, "label_status and label_12m agree", bad_domain, 0)
    unnamed = con.execute("""
        SELECT count(*) FROM labels
        WHERE NOT eligible_for_primary_study AND primary_exclusion_reason IS NULL""").fetchone()[0]
    ok &= check(con, "every excluded loan names a reason", unnamed, 0)

    # ---- split the sets -------------------------------------------------
    print("\n== row split ==")
    split = con.execute("""
        SELECT count(*) FILTER (WHERE eligible_for_primary_study) AS gold,
               count(*) FILTER (WHERE NOT eligible_for_primary_study) AS audit_only,
               count(*) FILTER (WHERE cohort_mature AND label_status <> 'unknown'
                                  AND NOT eligible_for_primary_study) AS decidable_but_excluded
        FROM labels""").fetchone()
    n_gold, n_audit_only, n_decidable_excluded = split
    print(f"     feature-set rows {n_gold:,} | audit-only {n_audit_only:,} | "
          f"decidable but excluded {n_decidable_excluded:,}")

    if not ok:
        print("\nchecks failed; nothing written")
        return 1

    # ---- feature set ----------------------------------------------------
    # Only determinate, mature, non-conflicted rows enter the feature set.
    feat_sql = f"""
        SELECT o.loan_id,
               {', '.join('o.quarter AS cohort' if f == 'cohort' else f'o."{f}"' for f in FEATURES)}
        FROM orig o
        JOIN labels l USING (loan_id)
        WHERE l.eligible_for_primary_study"""
    # ---- audit set ------------------------------------------------------
    audit_cols = [c for c in AUDIT if c != "cohort"]
    audit_sql = f"""
        SELECT l.loan_id, o.quarter AS cohort, {', '.join(f'l."{c}"' for c in audit_cols)}
        FROM labels l
        JOIN orig o USING (loan_id)"""

    print("\n== build ==")
    feat = con.execute(f"SELECT count(*) FROM ({feat_sql})").fetchone()[0]
    print(f"     feature rows {feat:,}")
    ok &= check(con, "feature rows equal eligible loans", feat, n_gold)
    nulls = con.execute(f"""
        SELECT count(*) FROM ({feat_sql}) WHERE loan_id IS NULL""").fetchone()[0]
    ok &= check(con, "no null loan_id in the feature set", nulls, 0)

    if args.dry_run:
        print("\ndry run: checks done, nothing written")
        return 0 if ok else 1

    (dest / "features").mkdir(parents=True, exist_ok=True)
    (dest / "audit").mkdir(parents=True, exist_ok=True)
    con.execute(f"""COPY ({feat_sql})
        TO '{(dest / 'features' / 'data.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION zstd)""")
    con.execute(f"""COPY ({audit_sql})
        TO '{(dest / 'audit' / 'data.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION zstd)""")

    # ---- verify what actually landed ------------------------------------
    print("\n== written ==")
    con.execute(f"""CREATE OR REPLACE VIEW gf AS
        SELECT * FROM read_parquet('{(dest / 'features' / 'data.parquet').as_posix()}')""")
    con.execute(f"""CREATE OR REPLACE VIEW ga AS
        SELECT * FROM read_parquet('{(dest / 'audit' / 'data.parquet').as_posix()}')""")
    f_rows = con.execute("SELECT count(*) FROM gf").fetchone()[0]
    f_ids = con.execute("SELECT count(DISTINCT loan_id) FROM gf").fetchone()[0]
    a_rows = con.execute("SELECT count(*) FROM ga").fetchone()[0]
    a_ids = con.execute("SELECT count(DISTINCT loan_id) FROM ga").fetchone()[0]
    ok &= check(con, "feature rows survived the write", f_rows, feat)
    ok &= check(con, "feature set unique on loan_id", f_rows - f_ids, 0)
    ok &= check(con, "audit rows cover every origination loan", a_rows, n_orig)
    ok &= check(con, "audit unique on loan_id", a_rows - a_ids, 0)
    overlap = con.execute(
        "SELECT count(*) FROM gf f SEMI JOIN ga a USING (loan_id)").fetchone()[0]
    ok &= check(con, "feature ids are a subset of audit ids", overlap, f_rows)
    leak = con.execute("""
        SELECT count(*) FROM gf f JOIN ga a USING (loan_id)
        WHERE a.label_12m IS NULL""").fetchone()[0]
    ok &= check(con, "no feature row has an indeterminate label", leak, 0)
    fcols = [r[0] for r in con.execute("DESCRIBE SELECT * FROM gf").fetchall()]
    leak_cols = [c for c in fcols if c in AUDIT and c != "cohort"]
    ok &= check(con, "no audit column inside the feature set", len(leak_cols), 0)
    if leak_cols:
        print("     leaked:", leak_cols)

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "version": args.version,
        "source": {
            "origination": "parquet/orig/quarter=*/data.parquet",
            "labels": "output/labels/cohort=*/data.parquet",
        },
        "rows": {"features": f_rows, "audit": a_rows,
                 "eligible": n_gold, "audit_only": n_audit_only},
        "features": FEATURES,
        "excluded_columns": EXCLUDED,
        "audit_columns": AUDIT,
        "rules": [
            "features are an allow-list; anything unlisted cannot reach the matrix",
            "no performance column is ever a feature: they are post-origination",
            "audit is a separate dataset, so the label cannot leak into features",
            "only eligible_for_primary_study rows enter the feature set",
            "the join is asserted 1:1 on loan_id, not assumed",
        ],
        "checks_passed": bool(ok),
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nwrote {dest}  ({time.time()-t0:.1f}s)")
    print("checks:", "all passed" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
