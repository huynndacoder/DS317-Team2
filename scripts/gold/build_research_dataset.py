#!/usr/bin/env python3
"""Build the Purchase-only research dataset and the pilot temporal split.

Scope: `loan_purpose = 'P'` (Purchase), label determinate and
`eligible_for_primary_study`. Features come from origination only; performance
never enters the feature matrix.

Three things this script refuses to do:
  * it never writes to `output/labels/` or `output/gold/gold_v1/`;
  * it never turns an unknown label into 0;
  * it never splits by a fixed year alone and calls that leakage-free. The split
    is expressed as a per-row rule on `label_window_end + reporting_lag <= T`,
    because a cohort can contain loans whose windows close months apart (the
    first-payment date spread within a cohort is several quarters wide).

Normalisation is limited to what the feature dictionary (gold_spec.py) justifies
from documentation: sentinel decoding, era-aware domain validation, and derived
variables with a fixed formula. No imputation, scaling, vocabulary learning or
resampling happens here — those belong after the split, and doing them here
would silently leak test statistics into training.

Usage:
  build_research_dataset.py                    # full build + split
  build_research_dataset.py --stage summary    # cohort/quality tables only
"""
import argparse
import hashlib
import json
import os
import pathlib
import sys
import time

import duckdb
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from gold_spec import BASELINE  # noqa: E402  the single source of truth

ROOT = pathlib.Path(__file__).resolve().parents[2]
PARQUET = ROOT / "parquet"
CONFIG_PATH = ROOT / "configs" / "pilot_baseline.yaml"


def load_config(path: str | pathlib.Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def config_hash(path: str | pathlib.Path = CONFIG_PATH) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def month_index(col: str) -> str:
    """Calendar-month index. Shared with the label builder; never do YYYYMM + 11."""
    return f"(({col} // 100) * 12 + ({col} % 100))"
LABELS = ROOT / "output" / "labels"
GOLD = ROOT / "output" / "gold"
OUT = GOLD / "research_v1"
MEMORY_LIMIT = os.environ.get("DQ_MEMORY_LIMIT", "3GB")
THREADS = os.environ.get("DQ_THREADS", "6")
WORK = pathlib.Path(os.environ.get("DQ_WORK_DIR", ROOT / ".label_tmp"))

# ---------------------------------------------------------------------------
# Split configuration. Every number here is a stated assumption, not a fact.
# The single executable config lives in configs/pilot_baseline.yaml. This
# section loads it; env vars can still override individual numbers.
# ---------------------------------------------------------------------------
# Months between a label window closing and that label being usable for fitting.
# 3 months approximates the quarterly publication cadence of the dataset. The
# real pipeline latency is NOT documented (there is no "as of" manifest on the
# Freddie Mac site), so this is an ASSUMPTION and is recorded as one.
REPORTING_LAG_MONTHS = int(os.environ.get("DQ_REPORTING_LAG_MONTHS", "3"))

# Load config YAML as the single executable config for split parameters.
# --version defaults to research_v1; pilot_p2 output goes to research_v2.
# Never let a pilot build silently overwrite research_v1.
_cfg = load_config()
_split_cfg = _cfg["split"]
SPLIT_REGIME = os.environ.get("DQ_SPLIT_REGIME", _split_cfg["regime"])
REPORTING_LAG_MONTHS = int(os.environ.get("DQ_REPORTING_LAG_MONTHS", _split_cfg.get("reporting_lag_months", 3)))

REGIMES = {
    "pilot":  {"T_TRAIN": 201901, "T_VALID": 202001},
    "stress": {"T_TRAIN": 202301, "T_VALID": 202401},
    "pilot_p2": {
        "T_TRAIN_TUNE": 201601,
        "T_VALID_READY": 201901,
        "T_REFINIT": 201901,
        "DEVELOPMENT_TEST_YEAR": 2019,
        "HOLDOUT_YEAR": 2024,
    },
}
assert SPLIT_REGIME in REGIMES, f"DQ_SPLIT_REGIME must be one of {list(REGIMES)}"
REGIME_CFG = REGIMES[SPLIT_REGIME]

if SPLIT_REGIME == "pilot_p2":
    T_TRAIN_TUNE = int(os.environ.get("DQ_T_TRAIN_TUNE", REGIME_CFG["T_TRAIN_TUNE"]))
    T_VALID_READY = int(os.environ.get("DQ_T_VALID_READY", REGIME_CFG["T_VALID_READY"]))
    T_REFINIT = int(os.environ.get("DQ_T_REFINIT", REGIME_CFG["T_REFINIT"]))
    DEVELOPMENT_TEST_YEAR = int(os.environ.get("DQ_DEVELOPMENT_TEST_YEAR", REGIME_CFG["DEVELOPMENT_TEST_YEAR"]))
    TEST_COHORT_YEAR = int(os.environ.get("DQ_HOLDOUT_YEAR", REGIME_CFG["HOLDOUT_YEAR"]))  # holdout_year
else:
    T_TRAIN = int(os.environ.get("DQ_T_TRAIN", REGIME_CFG["T_TRAIN"]))
    T_VALID = int(os.environ.get("DQ_T_VALID", REGIME_CFG["T_VALID"]))
    TEST_COHORT_YEAR = int(os.environ.get("DQ_TEST_YEAR", REGIME_CFG.get("TEST_YEAR", 2024)))
    assert T_VALID > T_TRAIN, (
        f"T_VALID ({T_VALID}) must be after T_TRAIN ({T_TRAIN}): validation is the "
        "later period, so its labels can only be ready later")
    TEST_COHORT_YEAR = int(os.environ.get("DQ_TEST_YEAR", "2024"))

# ---------------------------------------------------------------------------
# Normalisation rules, keyed by column. Each entry is (sql_expression, note).
# `raw` keeps the untouched source value so a decoded NULL is still traceable.
# ---------------------------------------------------------------------------
def norm_sql() -> dict:
    """Return {column: SQL producing the cleaned value} for baseline features."""
    return {
        # no documented sentinel; only a single genuine NULL exists
        "original_upb": '"original_upb"',
        "original_loan_term": '"original_loan_term"',
        "original_interest_rate": '"original_interest_rate"',
        # 999 = Not Available, valid range depends on origination era
        "ltv": ("""CASE WHEN "ltv" = 999 THEN NULL
                    WHEN "quarter" <= '2018Q1' AND ("ltv" < 6 OR "ltv" > 105) THEN NULL
                    WHEN "quarter" >  '2018Q1' AND ("ltv" < 1 OR "ltv" > 998) THEN NULL
                    ELSE "ltv" END"""),
        "cltv": ("""CASE WHEN "cltv" = 999 THEN NULL
                     WHEN "quarter" <= '2018Q1' AND ("cltv" < 6 OR "cltv" > 200) THEN NULL
                     WHEN "quarter" >  '2018Q1' AND ("cltv" < 1 OR "cltv" > 998) THEN NULL
                     ELSE "cltv" END"""),
        # 999 = Not Available; every HARP loan is 999 by design
        "dti": ('CASE WHEN "dti" = 999 OR "dti" < 0 OR "dti" > 65 THEN NULL ELSE "dti" END'),
        # 999 = Not Available, 0 = No MI (a real value, not missing)
        "mi_percentage": ('CASE WHEN "mi_percentage" = 999 OR "mi_percentage" > 55 '
                          'THEN NULL ELSE "mi_percentage" END'),
        "number_of_units": ('CASE WHEN "number_of_units" = 99 OR "number_of_units" < 1 '
                            'OR "number_of_units" > 4 THEN NULL ELSE "number_of_units" END'),
        # definition changed at 2018Q2: pre-era "2" means ">1", post-era it is a count.
        # Collapse to an era-invariant band so the model does not learn a 2018Q2 step.
        "number_of_borrowers": ("""CASE WHEN "number_of_borrowers" = 99
                                          OR "number_of_borrowers" < 1 THEN NULL
                                     WHEN "number_of_borrowers" = 1 THEN 'one'
                                     ELSE 'multiple' END"""),
        # 9999 = Not Available; documented methodology break at Release 2 (2013)
        "credit_score": ('CASE WHEN "credit_score" = 9999 OR "credit_score" < 300 '
                         'OR "credit_score" > 850 THEN NULL ELSE "credit_score" END'),
        # 9 = Not Available on every categorical flag below
        "first_time_homebuyer_flag": ('CASE WHEN "first_time_homebuyer_flag" IN (\'Y\',\'N\') '
                                      'THEN "first_time_homebuyer_flag" ELSE NULL END'),
        "channel": ('CASE WHEN "channel" IN (\'R\',\'C\',\'T\',\'B\') THEN "channel" '
                    'ELSE NULL END'),
        "property_type": ('CASE WHEN "property_type" = \'99\' THEN NULL ELSE "property_type" END'),
        # no documented sentinel; the single blank is a genuine unknown
        "property_state": '"property_state"',
        "occupancy_status": ('CASE WHEN "occupancy_status" IN (\'P\',\'I\',\'S\') '
                             'THEN "occupancy_status" ELSE NULL END'),
        "prepayment_penalty_flag": ('CASE WHEN "prepayment_penalty_flag" IN (\'Y\',\'N\') '
                                    'THEN "prepayment_penalty_flag" ELSE NULL END'),
        "super_conforming_flag": ('CASE WHEN "super_conforming_flag" IN (\'Y\',\'N\') '
                                  'THEN "super_conforming_flag" ELSE NULL END'),
        "harp_indicator": ('CASE WHEN "harp_indicator" IN (\'Y\',\'N\') '
                           'THEN "harp_indicator" ELSE NULL END'),
    }


# Sentinel definitions used by the quality report. (code_predicate, label)
SENTINELS = {
    "credit_score": [("credit_score = 9999", "9999 Not Available")],
    "dti": [("dti = 999", "999 Not Available (incl. all HARP)")],
    "ltv": [("ltv = 999", "999 Not Available")],
    "cltv": [("cltv = 999", "999 Not Available")],
    "mi_percentage": [("mi_percentage = 999", "999 Not Available"),
                      ("mi_percentage = 0", "0 = No MI (valid, not missing)")],
    "number_of_borrowers": [("number_of_borrowers = 99", "99 Not Available")],
    "number_of_units": [("number_of_units = 99", "99 Not Available")],
    "first_time_homebuyer_flag": [("first_time_homebuyer_flag = '9'", "9 Not Available")],
    "channel": [("channel = '9'", "9 Not Available")],
    "property_type": [("property_type = '99'", "99 Not Available")],
    "occupancy_status": [("occupancy_status = '9'", "9 Not Available")],
    "vantage_score_4": [("vantage_score_4 = 9999", "9999 Not Available")],
    "valuation_method": [("valuation_method = '7'", "7 Not Available")],
}
NOT_APPLICABLE = [
    ("valuation_method", "valuation_method = '7' AND quarter < '2017Q1'",
     "trường chưa tồn tại trước 2017 ⇒ không áp dụng, không phải thiếu"),
    ("dti", "dti = 999 AND harp_indicator = 'Y'",
     "HARP: UG quy định DTI luôn Not Available ⇒ không áp dụng"),
    ("pre_harp_loan_id", "pre_harp_loan_id IS NULL", "chỉ áp dụng cho khoản HARP"),
]

# Documented valid domain per column, used only to detect values that are neither
# a sentinel nor not-applicable (``invalid_value_count``). Ranges come from the
# Release 48 guide; era-dependent limits are expressed against ``quarter`` so a
# row is judged by the definition in force when it was originated.
VALID = {
    "original_upb": '"original_upb" > 0',
    "original_loan_term": '"original_loan_term" BETWEEN 1 AND 600',
    "original_interest_rate": '"original_interest_rate" >= 0 AND "original_interest_rate" <= 25',
    "ltv": ("""("quarter" <= '2018Q1' AND "ltv" BETWEEN 6 AND 105)
               OR ("quarter" > '2018Q1' AND "ltv" BETWEEN 1 AND 998)"""),
    "cltv": ("""("quarter" <= '2018Q1' AND "cltv" BETWEEN 6 AND 200)
                OR ("quarter" > '2018Q1' AND "cltv" BETWEEN 1 AND 998)"""),
    "dti": '"dti" BETWEEN 0 AND 65',
    "mi_percentage": '"mi_percentage" BETWEEN 0 AND 55',
    "number_of_units": '"number_of_units" BETWEEN 1 AND 4',
    "number_of_borrowers": ("""("quarter" < '2018Q2' AND "number_of_borrowers" IN (1, 2))
                               OR ("quarter" >= '2018Q2'
                                   AND "number_of_borrowers" BETWEEN 1 AND 10)"""),
    "credit_score": '"credit_score" BETWEEN 300 AND 850',
    "vantage_score_4": '"vantage_score_4" BETWEEN 300 AND 850',
    "first_time_homebuyer_flag": "\"first_time_homebuyer_flag\" IN ('Y','N')",
    "channel": "\"channel\" IN ('R','C','T','B')",
    "property_type": "\"property_type\" IN ('SF','PU','CO','MH','CP')",
    "property_state": "regexp_full_match(\"property_state\", '[A-Z]{2}')",
    "occupancy_status": "\"occupancy_status\" IN ('P','I','S')",
    "prepayment_penalty_flag": "\"prepayment_penalty_flag\" IN ('Y','N')",
    "super_conforming_flag": "\"super_conforming_flag\" IN ('Y','N')",
    "harp_indicator": "\"harp_indicator\" IN ('Y','N')",
    "valuation_method": "\"valuation_method\" IN ('1','2','3','4')",
}


def connect():
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute(f"SET threads={int(THREADS)}")
    con.execute("SET preserve_insertion_order=false")
    WORK.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{(WORK / 'duckdb').as_posix()}'")
    return con


CHECKS = []   # (stage, name, got, want, passed)


def check(name, got, want):
    ok = got == want
    CHECKS.append(("build", name, str(got), str(want), ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got} want={want}")
    return ok


def write_checks(dest):
    import csv as _csv
    with (dest / "split_checks.csv").open("w", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["stage", "check", "got", "want", "passed"])
        w.writerows(CHECKS)


def views(con):
    con.execute(f"""CREATE OR REPLACE VIEW lab AS
        SELECT * FROM read_parquet('{(LABELS / 'cohort=*' / 'data.parquet').as_posix()}')""")
    con.execute(f"""CREATE OR REPLACE VIEW org AS
        SELECT * FROM read_parquet('{(PARQUET / 'orig' / 'quarter=*' / 'data.parquet').as_posix()}',
                                   hive_partitioning=true)""")
    # one row per loan, Purchase only; label side joined on the key
    con.execute("""CREATE OR REPLACE VIEW purchase AS
        SELECT o.*, l.cohort, l.label_12m, l.label_status, l.eligible_for_primary_study,
               l.label_window_start, l.label_window_end, l.first_event_month,
               l.primary_exclusion_reason, l.label_reason, l.window_mature,
               l.cohort_mature, l.termination_code, l.performance_cutoff
        FROM org o JOIN lab l USING (loan_id)
        WHERE o.loan_purpose = 'P'""")


# ---------------------------------------------------------------------------
# Stage 1: Purchase scope summary
# ---------------------------------------------------------------------------
def scope_summary(con):
    q = """
    SELECT cohort,
           count(*)                                                AS purchase_loans,
           count(*) FILTER (WHERE eligible_for_primary_study)      AS eligible,
           count(*) FILTER (WHERE eligible_for_primary_study
                              AND label_status = 'positive')       AS eligible_positive,
           count(*) FILTER (WHERE eligible_for_primary_study
                              AND label_status = 'negative')       AS eligible_negative,
           count(*) FILTER (WHERE NOT eligible_for_primary_study)  AS excluded,
           count(*) FILTER (WHERE label_status = 'unknown')        AS unknown_any
    FROM purchase GROUP BY cohort ORDER BY cohort"""
    rows = con.execute(q).fetchall()
    cols = ["cohort", "purchase_loans", "eligible", "eligible_positive",
            "eligible_negative", "excluded", "unknown_any"]
    import csv
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "purchase_cohort_summary.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols + ["eligible_event_rate", "eligible_event_rate_pct"])
        for r in rows:
            rate = (r[3] / r[2]) if r[2] else None
            w.writerow(list(r) + [f"{rate:.8f}" if rate is not None else "",
                                  f"{100*rate:.4f}" if rate is not None else ""])
        tot = [sum(r[i] for r in rows) for i in range(1, 7)]
        rate = (tot[2] / tot[1]) if tot[1] else None
        w.writerow(["TOTAL"] + tot + [f"{rate:.8f}" if rate else "",
                                      f"{100*rate:.4f}" if rate else ""])

    # exclusion reasons within the Purchase scope
    with (OUT / "purchase_exclusion_reasons.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cohort", "reason", "loans"])
        for r in con.execute("""
            SELECT cohort, coalesce(primary_exclusion_reason, '(eligible)') AS reason,
                   count(*) AS n
            FROM purchase GROUP BY 1,2 ORDER BY 1, 3 DESC""").fetchall():
            w.writerow(r)
    print(f"  purchase cohorts: {len(rows)} | "
          f"loans {sum(r[1] for r in rows):,} | eligible {sum(r[2] for r in rows):,}")
    return sum(r[2] for r in rows)


# ---------------------------------------------------------------------------
# Stage 2: sentinel-aware quality per feature per cohort
# ---------------------------------------------------------------------------
def quality(con):
    """Sentinel-aware missingness per feature per cohort.

    Four things are counted separately because they mean different things:

    * ``sql_null``     - the value is absent from the file at all
    * ``documented_missing_code_count`` - a real number/flag that the Freddie Mac
      guide defines as Not Available (``9999``, ``999``, ``99``, ``9``)
    * ``not_applicable_count`` - the field does not apply to this loan (valuation
      method before 2017, DTI on a HARP loan), so its absence is not a data
      quality problem
    * ``invalid_value_count`` - a non-null value outside the documented domain
      that is neither a sentinel nor not-applicable, i.e. the file disagrees with
      the guide

    A naive ``IS NULL`` rate conflates the first with the other three, which is
    why a 0.2% null rate can hide a 0.8% semantic gap. A code that is both a
    sentinel and not-applicable (``dti = 999`` on a HARP loan) is counted once,
    under not-applicable, never twice.
    """
    import csv
    cols = [c for c in BASELINE]
    extra = ["vantage_score_4", "valuation_method"]  # reported though not baseline
    out_rows = []
    cohorts = [r[0] for r in con.execute(
        "SELECT DISTINCT cohort FROM purchase ORDER BY 1").fetchall()]

    def expr_for(c, kind):
        """Build the SQL predicate for one quality dimension of one column."""
        if kind == "na":
            preds = [p for col_, p, _ in NOT_APPLICABLE if col_ == c]
        elif kind == "code":
            # a predicate labelled "valid" describes a real value, not a sentinel
            preds = [p for p, lbl in SENTINELS.get(c, []) if "valid" not in lbl]
        else:
            pred = VALID.get(c)
            preds = [pred] if pred else []
        return " OR ".join(f"({x})" for x in preds) if preds else "FALSE"

    for q in cohorts:
        n = con.execute("SELECT count(*) FROM purchase WHERE cohort = ?", [q]).fetchone()[0]
        for c in cols + extra:
            na = expr_for(c, "na")
            code = expr_for(c, "code")
            valid = expr_for(c, "valid")
            r = con.execute(f"""
                SELECT
                  count(*) FILTER (WHERE "{c}" IS NULL)                AS sql_null,
                  count(*) FILTER (WHERE {na})                          AS na,
                  count(*) FILTER (WHERE ({code}) AND NOT ({na}))       AS code_miss,
                  count(*) FILTER (WHERE "{c}" IS NOT NULL
                                     AND NOT ({na}) AND NOT ({code})
                                     AND NOT ({valid}))                 AS invalid
                FROM purchase WHERE cohort = ?""", [q]).fetchone()
            sql_null, na_n, code_miss, invalid = r
            observed = n - sql_null - na_n - code_miss - invalid
            rate = (sql_null + code_miss) / n if n else None
            out_rows.append([q, c, n, sql_null, code_miss, na_n, invalid, observed,
                             round(rate, 8) if rate is not None else None,
                             round(100.0 * rate, 4) if rate is not None else None])
    with (OUT / "feature_quality_by_cohort.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cohort", "feature", "total_rows", "sql_null_count",
                    "documented_missing_code_count", "not_applicable_count",
                    "invalid_value_count", "observed_valid_count",
                    "semantic_missing_rate", "semantic_missing_rate_pct"])
        w.writerows(out_rows)
    print(f"  feature_quality_by_cohort.csv: {len(out_rows)} rows "
          f"({len(cohorts)} cohorts x {len(cols)+len(extra)} columns)")

    # overall per-feature summary (all cohorts pooled)
    with (OUT / "feature_quality_overall.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["feature", "total_rows", "sql_null_count",
                    "documented_missing_code_count", "not_applicable_count",
                    "invalid_value_count", "observed_valid_count",
                    "semantic_missing_rate", "semantic_missing_rate_pct"])
        for c in cols + extra:
            r = [x for x in out_rows if x[1] == c]
            n = sum(x[2] for x in r)
            sn = sum(x[3] for x in r)
            cm = sum(x[4] for x in r)
            na = sum(x[5] for x in r)
            iv = sum(x[6] for x in r)
            ov = sum(x[7] for x in r)
            rate = (sn + cm) / n if n else None
            w.writerow([c, n, sn, cm, na, iv, ov,
                        round(rate, 8) if rate is not None else None,
                        round(100.0 * rate, 4) if rate is not None else None])
    return out_rows


# ---------------------------------------------------------------------------
# Stage 3: normalised research dataset + split assignment
# ---------------------------------------------------------------------------
def build(con):
    ns = norm_sql()
    assert set(ns) == set(BASELINE), (
        f"normalisation rules do not cover the baseline exactly: "
        f"missing={set(BASELINE)-set(ns)} extra={set(ns)-set(BASELINE)}")

    # month index helper, inline so the split rule is auditable in one place
    mi = lambda c: f"(({c}//100)*12 + {c}%100)"  # noqa: E731
    ready = f"{mi('label_window_end')} + {REPORTING_LAG_MONTHS}"

    feats = ",\n           ".join(f'{expr} AS "{c}"' for c, expr in ns.items())

    # Per-loan readiness: a loan is usable at T only when its own label window
    # had closed and been published by T (label_window_end + lag <= T).
    # Assigning per cohort instead would be over-conservative: a cohort's
    # first-payment dates span years (modified / converted loans), so one
    # late loan would drag every later cohort out of the training set.
    if SPLIT_REGIME == "pilot_p2":
        # P2.2: train_tune/validation/train_refit/development_test/holdout.
        # Precedence: holdout > development_test > validation > train_tune >
        # train_refit > embargoed. train_refit (2012Q1-2016Q4) nominally overlaps
        # train_tune (2009Q1-2013Q4) and validation (2016Q1-2016Q4); those loans
        # are counted in their first-matched role here and the overlap is
        # reported in the manifest so step B can add them back.
        split_case = f"""
          CASE
            WHEN cohort LIKE '{TEST_COHORT_YEAR}Q%' THEN 'holdout'
            WHEN cohort LIKE '2019Q%' THEN 'development_test'
            WHEN cohort >= '2016Q1' AND cohort <= '2016Q4'
                 AND {ready} <= {mi(str(T_VALID_READY))} THEN 'validation'
            WHEN cohort >= '2009Q1' AND cohort <= '2013Q4'
                 AND {ready} <= {mi(str(T_TRAIN_TUNE))} THEN 'train_tune'
            WHEN cohort >= '2012Q1' AND cohort <= '2016Q4'
                 AND {ready} <= {mi(str(T_REFINIT))} THEN 'train_refit'
            ELSE 'embargoed'
          END"""
    else:
        split_case = f"""
          CASE
            WHEN cohort LIKE '{TEST_COHORT_YEAR}Q%' THEN 'test'
            WHEN {ready} <= {mi(str(T_TRAIN))} THEN 'train'
            WHEN {ready} <= {mi(str(T_VALID))} THEN 'valid'
            ELSE 'embargoed'
          END"""

    select_sql = f"""
    SELECT loan_id,
           {feats},
           "number_of_borrowers"                      AS number_of_borrowers_raw,
           label_12m,
           cohort,
           first_payment_date,
           label_window_start,
           label_window_end,
           {split_case} AS split
    FROM purchase
    WHERE eligible_for_primary_study"""

    OUT.mkdir(parents=True, exist_ok=True)
    con.execute(f"""CREATE OR REPLACE TABLE research AS {select_sql}""")

    # ---------- checks ----------
    print("\n== checks ==")
    ok = True
    n = con.execute("SELECT count(*) FROM research").fetchone()[0]
    n_pos = con.execute("SELECT count(*) FROM research WHERE label_12m = 1").fetchone()[0]
    ids = con.execute("SELECT count(DISTINCT loan_id) FROM research").fetchone()[0]
    ok &= check("one row per loan_id", n - ids, 0)
    ok &= check("label is only 0 or 1",
                con.execute("SELECT count(*) FROM research WHERE label_12m NOT IN (0,1)"
                            ).fetchone()[0], 0)
    ok &= check("no NULL label", con.execute(
        "SELECT count(*) FROM research WHERE label_12m IS NULL").fetchone()[0], 0)
    ok &= check("every row is Purchase", con.execute(
        "SELECT count(*) FROM purchase WHERE eligible_for_primary_study "
        "AND loan_purpose <> 'P'").fetchone()[0], 0)
    ok &= check("research equals eligible Purchase",
                n, con.execute("SELECT count(*) FROM purchase "
                               "WHERE eligible_for_primary_study").fetchone()[0])
    # no audit column leaked into the feature list
    leaked = [c for c in ("label_status", "primary_exclusion_reason", "label_reason",
                          "observed_month_count_in_window", "first_event_month",
                          "termination_code", "performance_cutoff", "window_mature",
                          "cohort_mature")
              if c in con.execute("DESCRIBE SELECT * FROM research").fetchall() and False]
    fcols = [r[0] for r in con.execute("DESCRIBE SELECT * FROM research").fetchall()]
    leaked = [c for c in ("label_status", "primary_exclusion_reason", "label_reason",
                          "observed_month_count_in_window", "first_event_month",
                          "termination_code", "performance_cutoff", "window_mature",
                          "cohort_mature", "eligible_for_primary_study") if c in fcols]
    ok &= check("no audit column in the research table", len(leaked), 0)
    if leaked:
        print("     leaked:", leaked)

    # ---------- split checks ----------
    print("\n== split ==")
    sp = con.execute("""
        SELECT split, count(*) AS n, sum(label_12m) AS pos,
               min(cohort) AS first_cohort, max(cohort) AS last_cohort,
               min(label_window_end) AS min_wend, max(label_window_end) AS max_wend
        FROM research GROUP BY 1 ORDER BY 1""").fetchdf()
    print(sp.to_string(index=False))

    if SPLIT_REGIME == "pilot_p2":
        # P2.2: per-role readiness checks.
        # train_tune labels ready at T_TRAIN_TUNE (fit_date step A).
        late_tt = con.execute(f"""
            SELECT count(*) FROM research
            WHERE split='train_tune' AND {ready} > {mi(str(T_TRAIN_TUNE))}""").fetchone()[0]
        ok &= check("all train_tune labels ready at fit_date (2016-01)", late_tt, 0)
        # validation labels ready at T_VALID_READY (refit date step B).
        late_val = con.execute(f"""
            SELECT count(*) FROM research
            WHERE split='validation' AND {ready} > {mi(str(T_VALID_READY))}""").fetchone()[0]
        ok &= check("all validation labels ready by refit_date (2019-01)", late_val, 0)
        # train_refit labels ready at T_REFINIT (refit date step B).
        late_tr = con.execute(f"""
            SELECT count(*) FROM research
            WHERE split='train_refit' AND {ready} > {mi(str(T_REFINIT))}""").fetchone()[0]
        ok &= check("all train_refit labels ready by refit_date (2019-01)", late_tr, 0)

        # Validation loans dropped due to readiness (2016Q1-2016Q4 but label not
        # ready by 2019-01). Reported, not silently dropped.
        val_dropped = con.execute(f"""
            SELECT count(*) FROM research
            WHERE cohort >= '2016Q1' AND cohort <= '2016Q4'
              AND split <> 'validation'""").fetchone()[0]
        print(f"  [INFO] 2016Q1-2016Q4 loans not assigned to validation (not label-ready "
              f"by 2019-01): {val_dropped:,}")

        # Temporal ordering: train_tune labels known before validation labels;
        # train_refit labels known before development_test labels.
        bad_tt_val = con.execute(f"""
            WITH s AS (SELECT split,
                           max({mi('label_window_end')}+{REPORTING_LAG_MONTHS}) AS ready_hi,
                           min({mi('label_window_end')}+{REPORTING_LAG_MONTHS}) AS ready_lo
                    FROM research GROUP BY 1)
            SELECT count(*) FROM s a, s b
            WHERE a.split='train_tune' AND b.split='validation' AND a.ready_hi > b.ready_lo""").fetchone()[0]
        ok &= check("every train_tune label known before any validation label", bad_tt_val, 0)
        bad_tr_dt = con.execute(f"""
            WITH s AS (SELECT split,
                           max({mi('label_window_end')}+{REPORTING_LAG_MONTHS}) AS ready_hi,
                           min({mi('label_window_end')}+{REPORTING_LAG_MONTHS}) AS ready_lo
                    FROM research GROUP BY 1)
            SELECT count(*) FROM s a, s b
            WHERE a.split='train_refit' AND b.split='development_test' AND a.ready_hi > b.ready_lo""").fetchone()[0]
        ok &= check("every train_refit label known before any development_test label", bad_tr_dt, 0)
    else:
        # Legacy regimes: train/valid/test readiness.
        late_train = con.execute(f"""
            SELECT count(*) FROM research
            WHERE split='train' AND {ready} > {mi(str(T_TRAIN))}""").fetchone()[0]
        late_valid = con.execute(f"""
            SELECT count(*) FROM research
            WHERE split='valid' AND {ready} > {mi(str(T_VALID))}""").fetchone()[0]
        ok &= check("all train labels ready at T_train", late_train, 0)
        ok &= check("all valid labels ready at T_valid", late_valid, 0)

        bad = con.execute(f"""
            WITH s AS (SELECT split, max({mi('label_window_end')}+{REPORTING_LAG_MONTHS}) AS ready_hi,
                          min({mi('label_window_end')}+{REPORTING_LAG_MONTHS}) AS ready_lo
                     FROM research GROUP BY 1)
            SELECT count(*) FROM s a, s b
            WHERE a.split='train' AND b.split='valid' AND a.ready_hi > b.ready_lo""").fetchone()[0]
        ok &= check("every train label known before any valid label", bad, 0)
        bad2 = con.execute(f"""
            WITH s AS (SELECT split, max({mi('label_window_end')}+{REPORTING_LAG_MONTHS}) AS ready_hi,
                          min({mi('label_window_end')}+{REPORTING_LAG_MONTHS}) AS ready_lo
                     FROM research GROUP BY 1)
            SELECT count(*) FROM s a, s b
            WHERE a.split='valid' AND b.split='test' AND a.ready_hi > b.ready_lo""").fetchone()[0]
        ok &= check("every valid label known before any test label", bad2, 0)

    # cohorts must not be split across sets (informational; per-loan readiness can
    # put two loans of the same cohort in two folds — that's not leakage).
    straddle = con.execute("""
        SELECT count(*) FROM (
          SELECT cohort FROM research GROUP BY cohort HAVING count(DISTINCT split) > 1
        )""").fetchone()[0]
    straddle_rows = con.execute("""
        SELECT count(*) FROM research r
        JOIN (SELECT cohort FROM research GROUP BY cohort HAVING count(DISTINCT split)>1) s
          USING (cohort)""").fetchone()[0]
    print(f"  [INFO] cohorts contributing to more than one split: {straddle} "
          f"({straddle_rows:,} loans). Expected with a per-loan readiness rule; "
          f"reported in the manifest.")

    empty = con.execute("""SELECT count(*) FROM (
        SELECT split FROM research GROUP BY split HAVING count(*) = 0)""").fetchone()[0]
    if empty:
        print("     WARNING: an empty split exists")

    # every loan must land in exactly one set.
    multi = con.execute("""
        SELECT count(*) FROM (
          SELECT loan_id FROM research GROUP BY 1 HAVING count(DISTINCT split) > 1)""").fetchone()[0]
    ok &= check("no loan appears in more than one split", multi, 0)

    # ---------- independent membership table (F1/F5 fix) ----------
    # Roles train_tune/validation/train_refit legitimately overlap (a 2012-2013 loan
    # can be in both train_tune and train_refit; a 2016 loan can be in both validation
    # and train_refit). They are NOT mutually exclusive partitions. We export an
    # independent (loan_id, role) table so each role can be verified against its
    # own predicate, and step B can add overlapping loans back.
    if SPLIT_REGIME == "pilot_p2":
        con.execute(f"""
        CREATE OR REPLACE TABLE membership AS
        SELECT loan_id, 'train_tune' AS role FROM purchase
        WHERE eligible_for_primary_study
          AND cohort >= '2009Q1' AND cohort <= '2013Q4'
          AND {ready} <= {mi(str(T_TRAIN_TUNE))}
        UNION ALL
        SELECT loan_id, 'validation' FROM purchase
        WHERE eligible_for_primary_study
          AND cohort >= '2016Q1' AND cohort <= '2016Q4'
          AND {ready} <= {mi(str(T_VALID_READY))}
        UNION ALL
        SELECT loan_id, 'train_refit' FROM purchase
        WHERE eligible_for_primary_study
          AND cohort >= '2012Q1' AND cohort <= '2016Q4'
          AND {ready} <= {mi(str(T_REFINIT))}
        UNION ALL
        SELECT loan_id, 'development_test' FROM purchase
        WHERE eligible_for_primary_study
          AND cohort LIKE '2019Q%'
        UNION ALL
        SELECT loan_id, 'holdout' FROM purchase
        WHERE eligible_for_primary_study
          AND cohort LIKE '{TEST_COHORT_YEAR}Q%'""")
        membership_counts = con.execute("""
            SELECT role, count(*) FROM membership GROUP BY 1 ORDER BY 1""").fetchall()
        print("  [INFO] independent membership counts:")
        for role, cnt in membership_counts:
            print(f"    {role}: {cnt:,}")

    if not ok:
        print("\nchecks failed; nothing written")
        return 1

    # ---------- export ----------
    # features / target / metadata in separate files so training code physically
    # cannot read a metadata column into X.
    feat_cols = ', '.join(f'"{c}"' for c in BASELINE)
    con.execute(f"""COPY (SELECT loan_id, {feat_cols},
                          number_of_borrowers_raw FROM research)
        TO '{(OUT / 'features.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION zstd)""")
    con.execute(f"""COPY (SELECT loan_id, label_12m FROM research)
        TO '{(OUT / 'target.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION zstd)""")
    con.execute(f"""COPY (SELECT loan_id, cohort, first_payment_date,
                          label_window_start, label_window_end, split FROM research)
        TO '{(OUT / 'split.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION zstd)""")

    # independent membership table (allows role overlap: train_tune & train_refit,
    # validation & train_refit). Verifier cross-checks each role against its own
    # predicate in both directions.
    if SPLIT_REGIME == "pilot_p2":
        con.execute(f"""COPY (SELECT loan_id, role FROM membership)
            TO '{(OUT / 'membership.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION zstd)""")

    # split manifest with the reproducible rule
    split_manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "version": OUT.name,
        "label_version": "v3",
        "label_source": "output/labels/cohort=*/data.parquet",
        "normalization_source": "scripts/gold/gold_spec.py",
        "scope": {"loan_purpose": "P (Purchase)", "eligible_only": True},
        "output_version": OUT.name,
        "reporting_lag_months": REPORTING_LAG_MONTHS,
        "regime": SPLIT_REGIME,
        "config_used": (
            {"fit_date": T_TRAIN_TUNE, "T_train_tune": T_TRAIN_TUNE,
             "validation_cohorts": "2009Q1-2013Q4",
             "validation_ready_by": T_VALID_READY, "T_valid_ready": T_VALID_READY,
             "refit_date": T_REFINIT, "T_refit": T_REFINIT,
             "development_test_cohorts": "2019Q1-2019Q4",
             "holdout_cohorts": f"{TEST_COHORT_YEAR}Q1-{TEST_COHORT_YEAR}Q4",
             "holdout_year": TEST_COHORT_YEAR, "test_cohort_year": TEST_COHORT_YEAR,
             "reporting_lag_months": REPORTING_LAG_MONTHS,
             "config_hash": config_hash(CONFIG_PATH)}
            if SPLIT_REGIME == "pilot_p2"
            else {"T_train": T_TRAIN, "T_valid": T_VALID,
                  "test_cohort_year": TEST_COHORT_YEAR,
                  "reporting_lag_months": REPORTING_LAG_MONTHS}),
        "resource_config": {"memory_limit": MEMORY_LIMIT, "threads": int(THREADS),
                            "spill_dir": str(WORK)},
        "reporting_lag_status": (
            "ASSUMPTION. Freddie Mac does not publish an 'as of' date or a manifest "
            "for the dataset; the 3-month figure approximates the quarterly release "
            "cadence and has NOT been verified against a publication timestamp."),
        "rule": (
            {
                "holdout": f"cohort LIKE '{TEST_COHORT_YEAR}Q%'",
                "development_test": "cohort LIKE '2019Q%'",
                "validation": (f"cohort >= '2016Q1' AND cohort <= '2016Q4' "
                               f"AND month_index(label_window_end) + "
                               f"{REPORTING_LAG_MONTHS} <= month_index({T_VALID_READY})"),
                "train_tune": (f"cohort >= '2009Q1' AND cohort <= '2013Q4' "
                               f"AND month_index(label_window_end) + "
                               f"{REPORTING_LAG_MONTHS} <= month_index({T_TRAIN_TUNE})"),
                "train_refit": (f"cohort >= '2012Q1' AND cohort <= '2016Q4' "
                                f"AND month_index(label_window_end) + "
                                f"{REPORTING_LAG_MONTHS} <= month_index({T_REFINIT})"),
                "else": "embargoed (excluded from all sets)",
                "month_index": "((m//100)*12 + m%100)",
                "precedence": "holdout > development_test > validation > train_tune > "
                              "train_refit > embargoed",
            }
            if SPLIT_REGIME == "pilot_p2"
            else {
                "test": f"cohort LIKE '{TEST_COHORT_YEAR}Q%'",
                "train": f"month_index(label_window_end) + {REPORTING_LAG_MONTHS} <= month_index({T_TRAIN})",
                "valid": f"month_index(label_window_end) + {REPORTING_LAG_MONTHS} <= month_index({T_VALID})",
                "else": "embargoed (excluded from all three sets)",
                "month_index": "((m//100)*12 + m%100)",
            }),
        "dates": (
            {"fit_date": T_TRAIN_TUNE, "refit_date": T_REFINIT,
             "validation_ready_by": T_VALID_READY,
             "development_test_year": 2019,
             "holdout_year": TEST_COHORT_YEAR}
            if SPLIT_REGIME == "pilot_p2"
            else {"T_train": T_TRAIN, "T_valid": T_VALID,
                  "test_cohort_year": TEST_COHORT_YEAR}),
        "counts": {r[0]: {"rows": int(r[1]), "positives": int(r[2])}
                   for r in con.execute(
                       "SELECT split, count(*), sum(label_12m) FROM research "
                       "GROUP BY 1").fetchall()},
        # Readiness, not vintage, is what licenses a training run: a label may be
        # used at T only once label_window_end + lag <= T. These bounds are recorded
        # so a reviewer can see that each fold is closed before the next one starts,
        # without having to re-derive it from 16 million rows.
        "readiness": {r[0]: {"label_window_end_min": int(r[1]),
                             "label_window_end_max": int(r[2]),
                             "label_known_from": int(r[3]),
                             "label_known_until": int(r[4])}
                      for r in con.execute(f"""
                          SELECT split,
                                 min(label_window_end),
                                 max(label_window_end),
                                 min({month_index('label_window_end')}) + {REPORTING_LAG_MONTHS},
                                 max({month_index('label_window_end')}) + {REPORTING_LAG_MONTHS}
                          FROM research GROUP BY 1""").fetchall()},
        "features": BASELINE,
        "files": {"features": "features.parquet", "target": "target.parquet",
                  "split": "split.parquet"},
        "known_limitations": [
            "Backfilled labels: the label table was built from one current snapshot, "
            "so a 2005 loan's label may differ from what was observable in 2005. "
            "This does not invalidate the split, but it does mean historical folds "
            "are not true point-in-time backtests.",
            "No publication timestamp exists for individual fields, so "
            "'available_at_scoring_time' is argued from field semantics, not verified "
            "from metadata.",
            "The 2024 test year is held out but its labels are derived from a snapshot "
            "that also contains later data; treat test metrics as an upper bound on "
            "real forward performance.",
        ],
        "cohort_straddle": {
            "cohorts_in_more_than_one_split": straddle,
            "loans_affected": straddle_rows,
            "why": ("The rule is per-loan readiness (label_window_end + lag <= T), not "
                    "vintage assignment. A cohort whose first-payment dates span years "
                    "can therefore contribute loans to two folds. This is not leakage: "
                    "each loan is assigned by when its own label became knowable. It is "
                    "recorded so a reviewer can see the magnitude."),
        },
        "checks_passed": True,
    }
    (OUT / "split_manifest.json").write_text(json.dumps(split_manifest, indent=2))

    # feature / target / metadata lists as a machine-readable contract
    contract = {
        "features": BASELINE,
        "target": ["label_12m"],
        "identifier": ["loan_id"],
        "split_metadata": ["cohort", "first_payment_date", "label_window_start",
                           "label_window_end", "split"],
        "audit_only": ["label_status", "eligible_for_primary_study",
                       "primary_exclusion_reason", "label_reason",
                       "observed_month_count_in_window", "first_event_month",
                       "termination_code", "termination_month", "performance_cutoff",
                       "window_mature", "cohort_mature", "quality_flags"],
        "excluded_from_baseline": ["vantage_score_4", "valuation_method", "seller_name",
                                   "product_type", "interest_only_indicator",
                                   "maturity_date", "postal_code", "msa",
                                   "pre_harp_loan_id", "program_indicator", "quarter",
                                   "loan_purpose"],
    }
    (OUT / "column_contract.json").write_text(json.dumps(contract, indent=2))

    write_checks(OUT)
    sizes = {f.name: f.stat().st_size for f in OUT.glob("*.parquet")}
    print("\n== written ==")
    for k, v in sorted(sizes.items()):
        print(f"  {k:22s} {v/1e6:8.1f} MB")
    # ---------- verify the written files ----------
    # A successful COPY is not evidence the export is usable. Reopen the parquet
    # and re-check the contract against what actually landed on disk, including
    # that semantic NULLs were not silently coerced.
    print("\n== verify written files ==")
    f_rows, f_ids, t_rows, s_rows, t_pos, t_neg, t_null = con.execute(f"""
        SELECT
          (SELECT count(*) FROM read_parquet('{OUT}/features.parquet')),
          (SELECT count(DISTINCT loan_id) FROM read_parquet('{OUT}/features.parquet')),
          (SELECT count(*) FROM read_parquet('{OUT}/target.parquet')),
          (SELECT count(*) FROM read_parquet('{OUT}/split.parquet')),
          (SELECT count(*) FROM read_parquet('{OUT}/target.parquet') WHERE label_12m = 1),
          (SELECT count(*) FROM read_parquet('{OUT}/target.parquet') WHERE label_12m = 0),
          (SELECT count(*) FROM read_parquet('{OUT}/target.parquet') WHERE label_12m IS NULL)
    """).fetchone()
    ok2 = True
    ok2 &= check("features rows equal research rows", f_rows, n)
    ok2 &= check("features unique on loan_id", f_rows - f_ids, 0)
    ok2 &= check("target rows equal research rows", t_rows, n)
    ok2 &= check("split rows equal research rows", s_rows, n)
    ok2 &= check("target positives equal positives in table", t_pos, int(n_pos))
    ok2 &= check("target negatives equal negatives in table", t_neg, n - int(n_pos))
    ok2 &= check("target exports no NULL label", t_null, 0)
    for c in ("credit_score", "dti", "number_of_borrowers"):
        a = con.execute(f'SELECT count(*) FILTER (WHERE "{c}" IS NULL) FROM research').fetchone()[0]
        b = con.execute(f"""SELECT count(*) FILTER (WHERE "{c}" IS NULL)
                            FROM read_parquet('{OUT}/features.parquet')""").fetchone()[0]
        ok2 &= check(f"NULL count preserved on export: {c}", b, a)

    if not ok2:
        print("\nexported files failed verification")
        return 1

    print(f"\nwrote {OUT}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["all", "summary"], default="all")
    ap.add_argument("--version", default="research_v1",
                    help="output version directory under output/gold/ (default: research_v1)")
    args = ap.parse_args()

    global OUT
    OUT = GOLD / args.version
    if args.version == "research_v1" and SPLIT_REGIME == "pilot_p2":
        print("WARNING: pilot_p2 regime writing to research_v1 — use --version research_v2 "
              "for pilot output to avoid clobbering the v1 baseline.")

    t0 = time.time()
    con = connect()
    views(con)
    OUT.mkdir(parents=True, exist_ok=True)

    print("== purchase scope ==")
    scope_summary(con)
    if args.stage == "summary":
        print(f"\ndone ({time.time()-t0:.1f}s)")
        return 0

    print("\n== feature quality (sentinel-aware) ==")
    quality(con)

    print("\n== research dataset + split ==")
    rc = build(con)
    print(f"\ndone ({time.time()-t0:.1f}s)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
