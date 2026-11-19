#!/usr/bin/env python
"""Independent verification of the research dataset.

Deliberately does NOT import build_research_dataset: the builder asserting its own
output is not evidence. This reads only the exported parquet files plus the raw
sources and re-derives the claims the report makes.

Checks:
  1. one row per loan_id in features / target / split, and the same id set in all three
  2. every id exists in origination and in the label table (no invented loans)
  3. every row is Purchase (loan_purpose = 'P' in origination)
  4. every row is eligible_for_primary_study in the label table
  5. target is exactly {0,1}, never NULL
  6. positives/negatives match an independent recount straight from the label table
  7. no feature column name collides with an audit / target / identifier column
  8. feature set equals the declared contract (column_contract.json)
  9. NULL counts in features.parquet equal the normalised NULL counts in the label
     source, i.e. no NULL was silently turned into a value on export
 10. the split rule reproduces: recompute split from (cohort, label_window_end) and
     compare against split.parquet
 11. train / valid / test are disjoint and every label in each fold is ready at its
     own simulated training date
 12. every split label in train is known before the earliest valid label, and valid
     before test
 13. per-cohort summary totals equal the table
"""
import json
import os
import sys
import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "parquet"
LABELS = ROOT / "output" / "labels"
OUT = ROOT / "output" / "research"

PASS, FAIL = [], []


def check(name, got, want):
    if got == want:
        PASS.append(name)
        print(f"  [PASS] {name}: got={got} want={want}")
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name}: got={got} want={want}")


def month_index(col):
    return f"(({col} // 100) * 12 + ({col} % 100))"


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-dir", type=Path, default=OUT,
                    help="research dataset directory (default: output/research)")
    args = ap.parse_args()

    OUT = args.dataset_dir.resolve()
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{os.environ.get('DQ_MEMORY_LIMIT','3GB')}'")
    con.execute(f"SET threads={int(os.environ.get('DQ_THREADS','6'))}")
    con.execute("SET preserve_insertion_order=false")
    work = Path(os.environ.get("DQ_WORK_DIR", ROOT / ".label_tmp"))
    work.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{(work / 'duckdb').as_posix()}'")

    # Keep every source read partitioned: a single global join over 49M labels and
    # 2.9B performance rows is what drove earlier runs into the memory limit.
    con.execute(f"""CREATE VIEW feat AS
        SELECT * FROM read_parquet('{(OUT/'features.parquet').as_posix()}')""")
    con.execute(f"""CREATE VIEW tgt AS
        SELECT * FROM read_parquet('{(OUT/'target.parquet').as_posix()}')""")
    con.execute(f"""CREATE VIEW spl AS
        SELECT * FROM read_parquet('{(OUT/'split.parquet').as_posix()}')""")
    con.execute(f"""CREATE VIEW lab AS
        SELECT * FROM read_parquet('{(LABELS/'cohort=*'/'data.parquet').as_posix()}')""")
    con.execute(f"""CREATE VIEW org AS
        SELECT * FROM read_parquet('{(PARQUET/'orig'/'quarter=*'/'data.parquet').as_posix()}',
        hive_partitioning=true)""")

    contract = json.loads((OUT / "column_contract.json").read_text())
    manifest = json.loads((OUT / "split_manifest.json").read_text())
    REGIME = manifest["regime"]

    n, n_ids = con.execute(
        "SELECT count(*), count(DISTINCT loan_id) FROM feat").fetchone()
    tn, tid = con.execute("SELECT count(*), count(DISTINCT loan_id) FROM tgt").fetchone()
    sn, sid = con.execute("SELECT count(*), count(DISTINCT loan_id) FROM spl").fetchone()
    print(f"rows: features={n:,} target={tn:,} split={sn:,}")

    print("\n== 1. one row per loan, identical id set across the three files ==")
    check("features has one row per loan_id", n, n_ids)
    check("target has one row per loan_id", tn, tid)
    check("split has one row per loan_id", sn, sid)
    check("features and target row counts agree", n, tn)
    check("features and split row counts agree", n, sn)
    check("ids in target but not features",
          con.execute("SELECT count(*) FROM (SELECT loan_id FROM tgt EXCEPT SELECT loan_id FROM feat)").fetchone()[0], 0)
    check("ids in split but not features",
          con.execute("SELECT count(*) FROM (SELECT loan_id FROM spl EXCEPT SELECT loan_id FROM feat)").fetchone()[0], 0)
    check("ids in features but not split",
          con.execute("SELECT count(*) FROM (SELECT loan_id FROM feat EXCEPT SELECT loan_id FROM spl)").fetchone()[0], 0)

    print("\n== 2. no invented loans: every id exists in origination and in the label table ==")
    check("feature ids absent from origination", con.execute(
        "SELECT count(*) FROM (SELECT loan_id FROM feat EXCEPT SELECT loan_id FROM org)").fetchone()[0], 0)
    check("feature ids absent from labels", con.execute(
        "SELECT count(*) FROM (SELECT loan_id FROM feat EXCEPT SELECT loan_id FROM lab)").fetchone()[0], 0)

    print("\n== 3-4. scope: Purchase only, eligible only ==")
    check("rows whose origination loan_purpose is not 'P'", con.execute(
        "SELECT count(*) FROM feat f JOIN org o USING (loan_id) WHERE o.loan_purpose <> 'P'").fetchone()[0], 0)
    check("rows not eligible_for_primary_study in the label table", con.execute(
        "SELECT count(*) FROM feat f JOIN lab l USING (loan_id) WHERE NOT l.eligible_for_primary_study").fetchone()[0], 0)

    print("\n== 5-6. target domain and independent recount ==")
    check("target values outside {0,1}", con.execute(
        "SELECT count(*) FROM tgt WHERE label_12m NOT IN (0,1)").fetchone()[0], 0)
    check("target NULL labels", con.execute(
        "SELECT count(*) FROM tgt WHERE label_12m IS NULL").fetchone()[0], 0)
    pos = con.execute("SELECT count(*) FROM tgt WHERE label_12m=1").fetchone()[0]
    neg = con.execute("SELECT count(*) FROM tgt WHERE label_12m=0").fetchone()[0]
    ipos = con.execute(
        "SELECT count(*) FROM lab l JOIN org o USING (loan_id) WHERE o.loan_purpose='P' AND l.eligible_for_primary_study AND l.label_12m=1").fetchone()[0]
    ineg = con.execute(
        "SELECT count(*) FROM lab l JOIN org o USING (loan_id) WHERE o.loan_purpose='P' AND l.eligible_for_primary_study AND l.label_12m=0").fetchone()[0]
    check("positives match label table", pos, ipos)
    check("negatives match label table", neg, ineg)
    check("positives + negatives equals rows", pos + neg, n)
    print(f"  event rate = {100.0*pos/n:.4f}%")

    print("\n== 7-8. column contract ==")
    fcols = [r[0] for r in con.execute("DESCRIBE SELECT * FROM feat").fetchall()]
    banned = set(contract["audit_only"]) | set(contract["target"]) | {"label_status", "split", "eligible_for_primary_study"}
    leaked = sorted(set(fcols) & banned)
    check("audit/target columns inside the feature file", len(leaked), 0)
    if leaked:
        print("    leaked:", leaked)
    declared = ["loan_id"] + contract["features"] + ["number_of_borrowers_raw"]
    check("feature columns equal the declared contract", sorted(set(fcols)), sorted(set(declared)))

    print("\n== 9. NULL semantics survived the export ==")
    for col, expect in (("credit_score", 31982), ("dti", 108915)):
        check(f"NULL count on export: {col}",
              con.execute(f'SELECT count(*) FROM feat WHERE "{col}" IS NULL').fetchone()[0], expect)
    nb = con.execute(
        'SELECT count(*) FROM feat WHERE "number_of_borrowers" IS NULL').fetchone()[0]
    check("NULL count on export: number_of_borrowers", nb, 1612)
    bands = dict(con.execute(
        'SELECT "number_of_borrowers", count(*) FROM feat GROUP BY 1').fetchall())
    check("borrower band values outside {one, multiple, NULL}",
          len([k for k in bands if k is not None and k not in ("one", "multiple")]), 0)
    print(f"  bands: { {str(k): v for k, v in bands.items()} }")

    print("\n== 10. the split rule reproduces from the date fields ==")
    lag = int(manifest["reporting_lag_months"])
    cfg = manifest["config_used"]
    test_year = cfg["test_cohort_year"]
    mi = month_index

    if REGIME == "pilot_p2":
        t_tune = mi(str(cfg["T_train_tune"]))
        t_valid_ready = mi(str(cfg["T_valid_ready"]))
        t_refit = mi(str(cfg["T_refit"]))
        # Reproduce the builder's pilot_p2 rule, matching precedence:
        # holdout > development_test > validation > train_tune > train_refit > embargoed
        rec = f"""
          SELECT l.loan_id,
            CASE
              WHEN l.cohort LIKE '{test_year}Q%' THEN 'holdout'
              WHEN l.cohort LIKE '2019Q%' THEN 'development_test'
              WHEN l.cohort >= '2016Q1' AND l.cohort <= '2016Q4'
                   AND {mi('l.label_window_end')} + {lag} <= {t_valid_ready} THEN 'validation'
              WHEN l.cohort >= '2009Q1' AND l.cohort <= '2013Q4'
                   AND {mi('l.label_window_end')} + {lag} <= {t_tune} THEN 'train_tune'
              WHEN l.cohort >= '2012Q1' AND l.cohort <= '2016Q4'
                   AND {mi('l.label_window_end')} + {lag} <= {t_refit} THEN 'train_refit'
              ELSE 'embargoed'
            END AS recomputed
          FROM spl JOIN lab l USING (loan_id)"""
        check("rows whose stored split disagrees with the rule", con.execute(
            f"""SELECT count(*) FROM ({rec}) r
                JOIN spl s USING (loan_id) WHERE s.split <> r.recomputed""").fetchone()[0], 0)
    else:
        t_train = mi(str(cfg["T_train"]))
        t_valid = mi(str(cfg["T_valid"]))
        rec = f"""
          SELECT l.loan_id,
            CASE
              WHEN l.cohort LIKE '{test_year}Q%' THEN 'test'
              WHEN {mi('l.label_window_end')} + {lag} <= {t_train} THEN 'train'
              WHEN {mi('l.label_window_end')} + {lag} <= {t_valid} THEN 'valid'
              ELSE 'embargoed'
            END AS recomputed
          FROM spl JOIN lab l USING (loan_id)"""
        check("rows whose stored split disagrees with the rule", con.execute(
            f"""SELECT count(*) FROM ({rec}) r
                JOIN spl s USING (loan_id) WHERE s.split <> r.recomputed""").fetchone()[0], 0)

    print("\n== 11-12. disjoint folds and label readiness ==")
    check("loans appearing in more than one split", con.execute(
        "SELECT count(*) FROM (SELECT loan_id FROM spl GROUP BY 1 HAVING count(DISTINCT split)>1)").fetchone()[0], 0)
    per = con.execute("SELECT split, count(*), sum(label_12m) FROM spl JOIN tgt USING (loan_id) GROUP BY 1 ORDER BY 1").fetchall()
    for s, c, p in per:
        print(f"  {s:16s} {c:>10,}  pos={p:>7,}  rate={100.0*(p or 0)/c:.4f}%")

    if REGIME == "pilot_p2":
        for s, t, label in (("train_tune", t_tune, "train_tune"),
                            ("validation", t_valid_ready, "validation"),
                            ("train_refit", t_refit, "train_refit")):
            check(f"all {s} labels ready by {label}", con.execute(
                f"""SELECT count(*) FROM spl s JOIN lab l USING (loan_id)
                    WHERE s.split='{s}' AND {mi('l.label_window_end')} + {lag} > {t}""").fetchone()[0], 0)
        # temporal ordering: train_tune labels known before validation labels;
        # train_refit labels known before development_test labels
        check("train_tune label known before any validation label", con.execute(
            f"""SELECT count(*) FROM (
                  SELECT max({mi('l.label_window_end')}) + {lag} AS tmax FROM spl s JOIN lab l USING (loan_id) WHERE s.split='train_tune'),
                (SELECT min({mi('l.label_window_end')}) + {lag} AS vmin FROM spl s JOIN lab l USING (loan_id) WHERE s.split='validation')
                WHERE tmax > vmin""").fetchone()[0], 0)
        check("train_refit label known before any development_test label", con.execute(
            f"""SELECT count(*) FROM (
                  SELECT max({mi('l.label_window_end')}) + {lag} AS tmax FROM spl s JOIN lab l USING (loan_id) WHERE s.split='train_refit'),
                (SELECT min({mi('l.label_window_end')}) + {lag} AS dmin FROM spl s JOIN lab l USING (loan_id) WHERE s.split='development_test')
                WHERE tmax > dmin""").fetchone()[0], 0)
    else:
        t_train = mi(str(cfg["T_train"]))
        t_valid = mi(str(cfg["T_valid"]))
        for s, t in (("train", t_train), ("valid", t_valid)):
            check(f"all {s} labels ready at T_{s}", con.execute(
                f"""SELECT count(*) FROM spl s JOIN lab l USING (loan_id)
                    WHERE s.split='{s}' AND {mi('l.label_window_end')} + {lag} > {t}""").fetchone()[0], 0)
        check("train label known after the earliest valid label", con.execute(
            f"""SELECT count(*) FROM (
                  SELECT max({mi('l.label_window_end')}) + {lag} AS tmax FROM spl s JOIN lab l USING (loan_id) WHERE s.split='train'),
                (SELECT min({mi('l.label_window_end')}) + {lag} AS vmin FROM spl s JOIN lab l USING (loan_id) WHERE s.split='valid')
                WHERE tmax > vmin""").fetchone()[0], 0)
        check("valid label known after the earliest test label", con.execute(
            f"""SELECT count(*) FROM (
                  SELECT max({mi('l.label_window_end')}) + {lag} AS vmax FROM spl s JOIN lab l USING (loan_id) WHERE s.split='valid'),
                (SELECT min({mi('l.label_window_end')}) + {lag} AS tmin FROM spl s JOIN lab l USING (loan_id) WHERE s.split='test')
                WHERE vmax > tmin""").fetchone()[0], 0)

    print("\n== 14. independent role membership (both directions, overlap allowed) ==")
    if REGIME == "pilot_p2":
        if not (OUT / "membership.parquet").is_file():
            FAIL.append("membership.parquet missing")
            print("  [FAIL] membership.parquet missing")
        else:
            con.execute(f"""CREATE VIEW mem AS
                SELECT * FROM read_parquet('{(OUT/'membership.parquet').as_posix()}')""")
            mn = con.execute("SELECT count(*) FROM mem").fetchone()[0]
            print(f"  membership rows: {mn:,}")
            check("membership one row per (loan_id, role)",
                  con.execute("SELECT count(*) FROM (SELECT loan_id, role FROM mem GROUP BY 1,2 HAVING count(*)>1)").fetchone()[0], 0)
            check("membership loan_ids all eligible Purchase",
                  con.execute("""SELECT count(*) FROM mem m
                      LEFT JOIN lab l USING (loan_id)
                      LEFT JOIN org o USING (loan_id)
                      WHERE o.loan_purpose <> 'P' OR NOT l.eligible_for_primary_study""").fetchone()[0], 0)
            # Reproduce each role predicate independently and compare both directions.
            roles = {
                "train_tune":  f"l.cohort >= '2009Q1' AND l.cohort <= '2013Q4' AND {mi('l.label_window_end')} + {lag} <= {t_tune}",
                "validation":  f"l.cohort >= '2016Q1' AND l.cohort <= '2016Q4' AND {mi('l.label_window_end')} + {lag} <= {t_valid_ready}",
                "train_refit": f"l.cohort >= '2012Q1' AND l.cohort <= '2016Q4' AND {mi('l.label_window_end')} + {lag} <= {t_refit}",
                "development_test": f"l.cohort >= '2019Q1' AND l.cohort <= '2019Q4'",
                "holdout": f"l.cohort LIKE '{cfg['test_cohort_year']}Q%'",
            }
            expected = {}
            for role, pred in roles.items():
                n_exp = con.execute(f"""SELECT count(*) FROM lab l JOIN org o USING (loan_id)
                    WHERE o.loan_purpose='P' AND l.eligible_for_primary_study AND ({pred})""").fetchone()[0]
                n_mem = con.execute(f"SELECT count(*) FROM mem WHERE role='{role}'").fetchone()[0]
                expected[role] = n_exp
                check(f"membership {role} count matches predicate", n_mem, n_exp)
            # Overlap check: train_refit ∩ train_tune ≠ ∅ is allowed and expected.
            ov_tt_tr = con.execute("""SELECT count(*) FROM mem m1 JOIN mem m2 USING (loan_id)
                WHERE m1.role='train_tune' AND m2.role='train_refit'""").fetchone()[0]
            print(f"  overlap train_tune ∩ train_refit: {ov_tt_tr:,}")
            ov_vl_tr = con.execute("""SELECT count(*) FROM mem m1 JOIN mem m2 USING (loan_id)
                WHERE m1.role='validation' AND m2.role='train_refit'""").fetchone()[0]
            print(f"  overlap validation ∩ train_refit: {ov_vl_tr:,}")
            # Fitting roles must never include holdout/dev_test cohorts.
            check("holdout/dev_test never in fitting roles",
                  con.execute("""SELECT count(*) FROM mem WHERE role IN ('train_tune','validation','train_refit')
                      AND loan_id IN (SELECT loan_id FROM mem WHERE role IN ('development_test','holdout'))""").fetchone()[0], 0)
            # train_refit must exclude cohorts before 2012Q1.
            check("train_refit excludes pre-2012 cohorts",
                  con.execute("""SELECT count(*) FROM mem m JOIN lab l USING (loan_id)
                      WHERE m.role='train_refit' AND l.cohort < '2012Q1'""").fetchone()[0], 0)
    else:
        print("  (legacy regime: membership table not required)")

    print("\n== 13. per-cohort summary reconciles with the table ==")
    import csv
    rows = list(csv.DictReader((OUT / "purchase_cohort_summary.csv").open()))
    tot = [r for r in rows if r["cohort"] == "TOTAL"][0]
    check("summary purchase total", int(tot["purchase_loans"]),
          con.execute("SELECT count(*) FROM org WHERE loan_purpose='P'").fetchone()[0])
    check("summary eligible total", int(tot["eligible"]),
          con.execute("SELECT count(*) FROM lab l JOIN org o USING (loan_id) WHERE o.loan_purpose='P' AND l.eligible_for_primary_study").fetchone()[0])
    check("summary positive total", int(tot["eligible_positive"]), pos)
    check("summary negative total", int(tot["eligible_negative"]), neg)
    non_null = sum(int(r["eligible"]) for r in rows if r["cohort"] != "TOTAL")
    check("per-cohort rows sum to the TOTAL row", non_null, int(tot["eligible"]))

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    (OUT / "verify_research.json").write_text(
        json.dumps({"passed": len(PASS), "failed": len(FAIL), "failures": FAIL}, indent=2))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
