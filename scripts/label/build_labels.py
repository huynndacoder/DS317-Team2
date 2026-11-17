#!/usr/bin/env python
"""Build the 12-month serious-delinquency label table from Freddie Mac parquet.

Reads parquet directly with DuckDB, one origination cohort at a time, so peak
memory stays bounded regardless of the 2.9 billion performance rows in the
full store. Writes one label partition per cohort plus cohort-level summaries.

Usage
-----
    ./venv/bin/python scripts/label/build_labels.py                # all cohorts
    ./venv/bin/python scripts/label/build_labels.py --quarters 2020Q1 2020Q2
    ./venv/bin/python scripts/label/build_labels.py --force        # rebuild

Environment
-----------
    DQ_MEMORY_LIMIT   DuckDB memory limit            (default 3GB)
    DQ_THREADS        DuckDB threads                 (default 6)
    DQ_WORK_DIR       spill directory                (default <repo>/.label_tmp)

See docs/labeling_rules.md for the label definition and exclusion rules.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import label_rules as R  # noqa: E402

PARQUET = ROOT / "parquet"
OUT = ROOT / "output" / "labels"
TABLES = ROOT / "output" / "label_tables"
WORK = Path(os.environ.get("DQ_WORK_DIR", ROOT / ".label_tmp"))
MEMORY_LIMIT = os.environ.get("DQ_MEMORY_LIMIT", "3GB")
THREADS = int(os.environ.get("DQ_THREADS", "6"))
COMPRESSION = "zstd"

#: Final column order of the exported label table, plus audit columns.
COLUMNS = [
    "loan_id", "cohort", "original_first_payment_date",
    "label_window_start", "label_window_end",
    "performance_cutoff",
    "first_observed_month", "last_observed_month",
    "observed_month_count_in_window", "unknown_status_month_count",
    "missing_month_count", "first_event_month",
    "termination_code", "termination_month",
    "window_mature", "cohort_mature",
    "label_status", "label_12m", "eligible_for_primary_study",
    "primary_exclusion_reason", "label_reason", "quality_flags",
    # audit columns
    "expected_months", "has_event", "duplicate_row_count",
    "conflict_flag", "event_conflict_flag", "duplicate_flag",
    "termination_effective_month", "termination_date_mismatch",
    "n_termination_events", "cohort_anchor_first_payment_month",
]


def connect() -> duckdb.DuckDBPyConnection:
    WORK.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute(f"SET threads={THREADS}")
    con.execute(f"SET temp_directory='{WORK}'")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET enable_progress_bar=false")
    return con


def quarters() -> list[str]:
    qs = sorted(p.name.split("=", 1)[1] for p in (PARQUET / "orig").glob("quarter=*"))
    return [q for q in qs if (PARQUET / "perf" / f"quarter={q}" / "data.parquet").exists()]


def cohort_facts(con, q: str) -> dict:
    """Data-derived facts for one cohort: loan count and performance frontier."""
    row = con.execute(f"""
        SELECT (SELECT count(*) FROM read_parquet('{PARQUET}/orig/quarter={q}/data.parquet')) AS n_loans,
               (SELECT max(monthly_reporting_period)
                FROM read_parquet('{PARQUET}/perf/quarter={q}/data.parquet')) AS cutoff,
               (SELECT count(*) FROM read_parquet('{PARQUET}/perf/quarter={q}/data.parquet')) AS n_perf,
               (SELECT max(first_payment_date)
                FROM read_parquet('{PARQUET}/orig/quarter={q}/data.parquet')) AS max_fpd
    """).fetchone()
    n_loans, cutoff, n_perf, max_fpd = row
    # source-version inference is documented: Release 48 carries performance to
    # 202606; the 25 cohorts that stop at 202603 were ingested from an earlier
    # release (47). This is a per-partition fact, recorded in the manifest.
    if cutoff == 202606:
        source = "release_48"
    elif cutoff == 202603:
        source = "release_47_inferred"
    else:
        source = "unknown"
    return {"cohort": q, "n_loans": n_loans, "performance_cutoff": cutoff,
            "n_perf_rows": n_perf, "max_first_payment_date": max_fpd,
            "source_version": source}


def build_cohort(con, q: str, facts: dict) -> dict:
    """Compute and export the label partition for one cohort. Returns summary."""
    cutoff = facts["performance_cutoff"]
    if cutoff is None:
        raise RuntimeError(f"{q}: no performance rows, cannot determine cutoff")

    orig = f"read_parquet('{PARQUET}/orig/quarter={q}/data.parquet')"
    perf = f"read_parquet('{PARQUET}/perf/quarter={q}/data.parquet')"
    core = R.core_sql(orig, perf, cutoff_expr=f"{cutoff}::INTEGER")

    # cohort_mature is anchored on the cohort's ACTUAL first-payment month, not
    # the origination quarter end. The cohort's window range ends at its 99th
    # percentile first-payment month + 11 months (inclusive). p99 is used rather
    # than max(first_payment_date) because ~0.3-0.5% of a cohort are modified /
    # converted loans whose first_payment_date reflects a modification date years
    # later (Freddie Mac FAQ Q37) -- using max would keep even 1999Q1 immature
    # forever. quantile_disc is exact and deterministic, so the anchor is
    # reproducible; it is recorded per row as cohort_anchor_first_payment_month.
    anchor = con.execute(f"""
        SELECT CAST(quantile_disc(first_payment_date, 0.99) AS INTEGER)
        FROM {orig}
    """).fetchone()[0]
    cohort_mature = con.execute(f"""
        SELECT {R.month_index(str(anchor))} + {R.WINDOW_MONTHS - 1}
               <= {R.month_index(f'{cutoff}::INTEGER')}
    """).fetchone()[0]

    con.execute(f"""
        CREATE OR REPLACE TABLE core_t AS
        SELECT c.*, '{q}' AS cohort, {bool_sql(cohort_mature)} AS cohort_mature,
               {anchor} AS cohort_anchor_first_payment_month
        FROM ({core}) c
    """)
    con.execute(f"CREATE OR REPLACE TABLE dec_t AS {R.decide_sql('core_t')}")

    # window_mature is per loan: the loan's own label window ended by the cutoff
    con.execute(f"""
        CREATE OR REPLACE TABLE fin_t AS
        WITH base AS (
          SELECT *,
            '{q}'                 AS cohort,
            win_end_idx <= cut_idx AS window_mature,
            (termination_effective_month IS NOT NULL
             AND termination_effective_month <> termination_month) AS termination_date_mismatch
          FROM ({R.finish_sql('SELECT * FROM dec_t')})
        )
        SELECT *,
          array_to_string(list_filter([
            CASE WHEN conflict_any = 1 THEN 'conflict' ELSE NULL END,
            CASE WHEN conflict_event_month = 1 THEN 'event_conflict' ELSE NULL END,
            CASE WHEN has_dup_rows = 1 THEN 'dup' ELSE NULL END,
            CASE WHEN termination_date_mismatch THEN 'termination_date_mismatch' ELSE NULL END,
            CASE WHEN n_termination_events > 1 THEN 'multiple_termination_events' ELSE NULL END
          ], x -> x IS NOT NULL), ';')        AS quality_flags,
          expected_months,
          has_ev                              AS has_event,
          dup_row_count                       AS duplicate_row_count,
          conflict_any = 1                    AS conflict_flag,
          conflict_event_month = 1            AS event_conflict_flag,
          has_dup_rows = 1                    AS duplicate_flag
        FROM base
    """)

    outdir = OUT / f"cohort={q}"
    outdir.mkdir(parents=True, exist_ok=True)
    target = outdir / "data.parquet"
    tmp = outdir / "data.parquet.tmp"
    sel = ", ".join(COLUMNS)
    con.execute(f"""
        COPY (SELECT {sel} FROM fin_t ORDER BY loan_id)
        TO '{tmp}' (FORMAT PARQUET, COMPRESSION '{COMPRESSION}', ROW_GROUP_SIZE 122880)
    """)
    os.replace(tmp, target)

    n_out = con.execute("SELECT count(*) FROM fin_t").fetchone()[0]
    if n_out != facts["n_loans"]:
        raise RuntimeError(f"{q}: wrote {n_out} label rows but cohort has "
                           f"{facts['n_loans']} origination loans")

    s = con.execute("""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE label_status='positive') AS pos,
               count(*) FILTER (WHERE label_status='negative') AS neg,
               count(*) FILTER (WHERE label_status='unknown')  AS unk,
               count(*) FILTER (WHERE eligible_for_primary_study) AS eligible,
               count(*) FILTER (WHERE eligible_for_primary_study AND label_status='positive') AS e_pos,
               count(*) FILTER (WHERE eligible_for_primary_study AND label_status='negative') AS e_neg,
               count(*) FILTER (WHERE window_mature)           AS mature
        FROM fin_t
    """).fetchone()
    con.execute("DROP TABLE IF EXISTS core_t")
    con.execute("DROP TABLE IF EXISTS dec_t")
    con.execute("DROP TABLE IF EXISTS fin_t")
    out = dict(zip(["total_loans", "positive", "negative", "unknown", "eligible",
                    "eligible_positive", "eligible_negative", "mature_loans"], s))
    out["cohort_anchor_first_payment_month"] = anchor
    out["cohort_mature"] = cohort_mature
    out["source_version"] = facts["source_version"]
    return out


def bool_sql(v: bool) -> str:
    return "TRUE" if v else "FALSE"


def write_reports(con, summaries: list[dict]) -> None:
    TABLES.mkdir(parents=True, exist_ok=True)

    # cohort summary, per the required schema
    con.execute("""
        CREATE OR REPLACE TABLE cohort_summary AS
        SELECT cohort,
               count(*)                                                   AS total_loans,
               count(*) FILTER (WHERE window_mature)                       AS mature_loans,
               count(*) FILTER (WHERE label_status='positive')             AS positive_count,
               count(*) FILTER (WHERE label_status='negative')             AS negative_count,
               count(*) FILTER (WHERE label_status='unknown')              AS unknown_count,
               count(*) FILTER (WHERE eligible_for_primary_study)          AS eligible_count,
               count(*) FILTER (WHERE eligible_for_primary_study
                                  AND label_status='positive')             AS eligible_positive_count,
               count(*) FILTER (WHERE eligible_for_primary_study
                                  AND label_status='negative')             AS eligible_negative_count,
               round(100.0 * count(*) FILTER (WHERE eligible_for_primary_study
                                  AND label_status='positive')
                     / nullif(count(*) FILTER (WHERE eligible_for_primary_study), 0), 4)
                                                                           AS eligible_event_rate_pct,
               -- spec column `eligible_event_rate`: same ratio as a proportion (0-1)
               round(1.0 * count(*) FILTER (WHERE eligible_for_primary_study
                                  AND label_status='positive')
                     / nullif(count(*) FILTER (WHERE eligible_for_primary_study), 0), 8)
                                                                            AS eligible_event_rate,
               bool_or(cohort_mature)                                      AS cohort_mature
        FROM read_parquet('{out}/*/data.parquet')
        GROUP BY cohort ORDER BY cohort
    """.replace("{out}", str(OUT)))
    con.execute(f"COPY cohort_summary TO '{TABLES}/cohort_summary.csv' (HEADER)")
    con.execute(f"COPY cohort_summary TO '{TABLES}/cohort_summary.parquet' (FORMAT PARQUET)")

    # reason breakdown per cohort
    con.execute("""
        CREATE OR REPLACE TABLE reason_summary AS
        SELECT cohort,
               coalesce(label_reason, 'none_' || label_status) AS reason,
               label_status,
               count(*) AS loans,
               round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY cohort), 4) AS pct_of_cohort
        FROM read_parquet('{out}/*/data.parquet')
        GROUP BY cohort, reason, label_status
        ORDER BY cohort, loans DESC
    """.replace("{out}", str(OUT)))
    con.execute(f"COPY reason_summary TO '{TABLES}/reason_summary.csv' (HEADER)")

    # global headline numbers
    g = con.execute("""
        SELECT count(*)                                              AS total_loans,
               count(*) FILTER (WHERE eligible_for_primary_study)     AS eligible,
               count(*) FILTER (WHERE eligible_for_primary_study
                                  AND label_status='positive')        AS eligible_pos,
               count(*) FILTER (WHERE label_status='positive')        AS pos_all,
               count(*) FILTER (WHERE label_status='negative')        AS neg_all,
               count(*) FILTER (WHERE label_status='unknown')         AS unk_all,
               count(*) FILTER (WHERE cohort_mature)                  AS in_mature_cohorts,
               count(DISTINCT cohort)                                 AS n_cohorts
        FROM read_parquet('{out}/*/data.parquet')
    """.replace("{out}", str(OUT))).fetchone()
    # last eligible cohort
    last = con.execute("""
        SELECT max(cohort) FROM read_parquet('{out}/*/data.parquet')
        WHERE eligible_for_primary_study
    """.replace("{out}", str(OUT))).fetchone()[0]
    unk = con.execute("""
        SELECT coalesce(label_reason,'none') r, count(*) n
        FROM read_parquet('{out}/*/data.parquet')
        WHERE label_status='unknown' GROUP BY 1 ORDER BY n DESC
    """.replace("{out}", str(OUT))).fetchall()

    (TABLES / "headline.json").write_text(json.dumps({
        "total_loans": g[0], "eligible": g[1], "eligible_positive": g[2],
        "positive_all": g[3], "negative_all": g[4], "unknown_all": g[5],
        "loans_in_mature_cohorts": g[6], "n_cohorts": g[7],
        "last_cohort_with_eligible_loans": last,
        "unknown_reasons": [{"reason": r, "loans": n} for r, n in unk],
    }, indent=2))
    print(f"\n  last cohort with eligible loans: {last}")
    print("  unknown reasons:")
    for r, n in unk[:8]:
        print(f"    {r:<36} {n:>12,}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quarters", nargs="*", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--skip-summary", action="store_true")
    ap.add_argument("--summary-only", action="store_true",
                    help="rebuild summary tables from existing label partitions")
    args = ap.parse_args()

    qs = args.quarters or quarters()
    OUT.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)

    print(f"label build: {len(qs)} cohort(s), memory_limit={MEMORY_LIMIT}, "
          f"threads={THREADS}, spill={WORK}")
    con = connect()
    print(f"  disk free: {shutil.disk_usage(ROOT).free / 2**30:.1f} GiB")

    t0 = time.time()
    summaries, skipped, failed = [], [], []
    existing = sorted(p.name.split("=", 1)[1] for p in OUT.glob("cohort=*"))
    for i, q in enumerate(qs if not args.summary_only else [], 1):
        target = OUT / f"cohort={q}" / "data.parquet"
        if target.exists() and not args.force:
            skipped.append(q)
            continue
        try:
            facts = cohort_facts(con, q)
            s = build_cohort(con, q, facts)
            s.update(cohort=q, cutoff=facts["performance_cutoff"])
            summaries.append(s)
            rate = 100.0 * s["eligible_positive"] / s["eligible"] if s["eligible"] else 0.0
            print(f"  [{i}/{len(qs)}] {q} n={s['total_loans']:>9,} "
                  f"pos={s['positive']:>7,} neg={s['negative']:>9,} "
                  f"unk={s['unknown']:>7,} elig={s['eligible']:>9,} "
                  f"rate={rate:5.2f}%  cut={facts['performance_cutoff']} "
                  f"mature_cohort={s['cohort_mature']} "
                  f"anchor={s['cohort_anchor_first_payment_month']}", flush=True)
        except Exception as exc:  # keep going, report at the end
            failed.append((q, str(exc)))
            print(f"  [{i}/{len(qs)}] {q} FAILED: {exc}", flush=True)

    if not args.skip_summary and existing:
        print("\nbuilding summary tables ...")
        write_reports(con, summaries)
        # real-loan evidence is produced by label_examples.py so there is exactly
        # one producer of output/label_tables/label_examples.csv

    ok = len(summaries) + len(skipped)
    print(f"\ndone in {time.time()-t0:.0f}s: {ok} cohort(s) present, "
          f"{len(skipped)} skipped, {len(failed)} failed")
    (TABLES / "build_log.json").write_text(json.dumps({
        "quarters": qs, "built": [s["cohort"] for s in summaries],
        "skipped": skipped, "failed": failed,
        "memory_limit": MEMORY_LIMIT, "threads": THREADS,
        "elapsed_seconds": round(time.time() - t0, 1),
    }, indent=2))
    # The manifest describes EVERY partition on disk, not just the ones this
    # invocation rebuilt. A subset/--resume run must never erase the record of
    # partitions it did not touch, so the file is merged rather than overwritten.
    MANIFEST = OUT / "manifest.json"
    previous = {}
    if MANIFEST.exists():
        try:
            previous = {e["cohort"]: e for e in
                        json.loads(MANIFEST.read_text()).get("partitions", [])}
        except (json.JSONDecodeError, KeyError, TypeError):
            previous = {}
    fresh = {}
    for s in summaries:
        fresh[s["cohort"]] = {
            "cohort": s["cohort"],
            "performance_cutoff": s["cutoff"],
            "source_version": s["source_version"],
            "cohort_anchor_first_payment_month": s["cohort_anchor_first_payment_month"],
            "cohort_mature": bool(s["cohort_mature"]),
            "total_loans": s["total_loans"],
        }
    merged = dict(previous)
    merged.update(fresh)
    # only partitions that still exist on disk belong in the manifest
    on_disk = {p.name.split("=", 1)[1] for p in OUT.glob("cohort=*")}
    parts = [merged[q] for q in sorted(merged) if q in on_disk]
    stale = sorted(set(previous) - on_disk)
    MANIFEST.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "run_cohorts": qs,
        "source_version_rule": (
            "performance_cutoff 202606 => release_48 (Release 48, 2026-10-28). "
            "202603 => release_47_inferred: the cohort stops one quarter early, "
            "consistent with an ingestion from Release 47; inferred from the "
            "performance frontier, not read from release metadata."
        ),
        "partitions": parts,
    }, indent=2))
    if stale:
        print(f"manifest: dropped {len(stale)} partition(s) no longer on disk: "
              f"{', '.join(stale[:5])}{' ...' if len(stale) > 5 else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())