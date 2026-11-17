"""Shared label rules for the 12-month serious-delinquency label.

Single source of truth for the label definition used by:
  - scripts/label/build_labels.py     (production build)
  - scripts/label/test_label_logic.py (synthetic known-answer tests)

Both callers execute the SAME SQL produced here, so the tested logic and the
production logic cannot diverge.

Label definition (frozen, documented in docs/labeling_rules.md):
  Window  = original first payment month .. +11 calendar months (12 months,
            inclusive of both ends). Calendar months, NOT loan_age.
  Event   = any month in the window whose current_loan_delinquency_status is a
            numeric code >= 3 ('03'..'99') or is 'RA' (REO acquisition).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Rule constants
# ---------------------------------------------------------------------------

#: minimum numeric delinquency status that counts as "serious" (90+ days).
#: '00' current, '01' 30-59, '02' 60-89, '03' 90-119 ... '99' is saturation.
EVENT_MIN_STATUS = 3

#: status code that means REO acquisition (a real state, not a missing marker).
EVENT_STATUS_RA = "RA"

#: sentinel meaning "Not Available". Never treated as 0, never inside a window.
UNKNOWN_STATUS = "XX"

#: zero balance codes.
#:   01 Prepaid or Matured (voluntary payoff)  -> allows a NEGATIVE label
#:   96 Confirmed Underwriting / Servicing Defect prior to credit event
#:   02 Third Party Sale                       -> surveillance stops, UNKNOWN
#:   03 Short Sale or Charge Off               -> surveillance stops, UNKNOWN
#:   09 REO Disposition                        -> surveillance stops, UNKNOWN
#:   15 Whole Loan Sales                       -> surveillance stops, UNKNOWN
#:   16 Reperforming Loan Securitizations      -> surveillance stops, UNKNOWN
ZBC_VOLUNTARY = "01"
ZBC_DISTRESS = ("02", "03", "09")
ZBC_SALE = ("15", "16")
ZBC_DEFECT = "96"

WINDOW_MONTHS = 12



# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def month_index(col: str) -> str:
    """SQL expression turning a YYYYMM integer into a linear month index."""
    return f"(({col} // 100) * 12 + ({col} % 100))"


def month_from_index(expr: str) -> str:
    """SQL expression turning a linear month index back into YYYYMM."""
    return f"((({expr}) - 1) // 12 * 100 + ((({expr}) - 1) % 12 + 1))"


def status_as_int(col: str = "status") -> str:
    """Numeric delinquency value of a status string; NULL when not interpretable."""
    return f"""
    CASE
      WHEN {col} = '{EVENT_STATUS_RA}' THEN 99
      WHEN regexp_full_match({col}, '[0-9]{{2}}') THEN CAST({col} AS INTEGER)
      ELSE NULL
    END
    """


# kept for callers that used the earlier private name
_status_as_int = status_as_int


def core_sql(orig_rel: str, perf_rel: str, *, cutoff_expr: str = "NULL::INTEGER") -> str:
    """Per-loan window aggregate: one row per origination loan_id.

    ``orig_rel`` / ``perf_rel`` are DuckDB relations (parquet glob, parquet
    file, or table name). ``cutoff_expr`` must evaluate to a YYYYMM integer.

    Duplicate handling is explicit: perf rows are collapsed to one row per
    (loan_id, calendar month) before any decision. Identical duplicates only
    raise ``has_dup_rows``; duplicates that disagree on the month's status
    (including one NULL vs one value) raise ``conflict_any`` (and, when the
    month carries the event, ``conflict_event_month``), which force the label to
    unknown rather than picking an arbitrary row.
    """
    mi_mrp = month_index("monthly_reporting_period")
    mi_fpd = month_index("fpd")
    last = WINDOW_MONTHS - 1

    return f"""
WITH src AS (
    SELECT loan_id,
           monthly_reporting_period AS mrp,
           {mi_mrp} AS mi,
           current_loan_delinquency_status AS status,
           zero_balance_code AS zbc,
           zero_balance_effective_date AS zbed,
           {_status_as_int()} AS d
    FROM {perf_rel}
),
pm AS (
    SELECT loan_id, mi,
           min(mrp)              AS mrp,
           count(*)              AS n_rows,
           max(d)                AS mx_d,
           min(d)                AS mn_d,
           count(DISTINCT coalesce(status, '~')) AS n_status,
           max(zbc)              AS mx_zbc,
           max(zbed)             AS mx_zbed
    FROM src
    GROUP BY loan_id, mi
),
obs AS (
    SELECT loan_id,
           min(mrp) AS first_observed_month,
           max(mrp) AS last_observed_month
    FROM pm GROUP BY loan_id
),
term AS (
    -- code, reporting month and effective date all come from the single
    -- termination event; a loan with >1 zero-balance event is flagged, not
    -- silently collapsed to one arbitrary row.
    SELECT loan_id,
           min(mrp)    FILTER (WHERE mx_zbc IS NOT NULL) AS termination_month,
           max(mx_zbc) FILTER (WHERE mx_zbc IS NOT NULL) AS termination_code,
           max(mx_zbed) FILTER (WHERE mx_zbc IS NOT NULL) AS termination_effective_month,
           count(*)    FILTER (WHERE mx_zbc IS NOT NULL) AS n_termination_events
    FROM pm GROUP BY loan_id
),
o AS (
    SELECT loan_id, fpd, {mi_fpd} AS a FROM (
        SELECT loan_id, first_payment_date AS fpd FROM {orig_rel}
    )
),
win AS (
    SELECT o.loan_id,
           o.fpd                       AS fpd,
           o.a                         AS win_start,
           o.a + {last}                AS win_end,
           count(pm.mi)                AS n_obs,
           -- only months that were actually OBSERVED can be "unknown status";
           -- the LEFT JOIN emits one all-NULL row when the window has no rows
           CAST(sum(CASE WHEN pm.mi IS NOT NULL AND pm.mx_d IS NULL THEN 1 ELSE 0 END) AS BIGINT) AS n_unk,
           coalesce(max(CASE WHEN pm.mx_d >= {EVENT_MIN_STATUS} THEN 1 ELSE 0 END), 0) AS has_ev,
           min(CASE WHEN pm.mx_d >= {EVENT_MIN_STATUS} THEN pm.mrp END) AS first_event_month,
           -- conflict_any: some window month has contradicting duplicate rows
           coalesce(max(CASE WHEN pm.n_status > 1 THEN 1 ELSE 0 END), 0) AS conflict_any,
           -- conflict_event_month: the month that carried the event itself also
           -- has contradicting duplicates, so the event is not certain.
           coalesce(max(CASE WHEN pm.mx_d >= {EVENT_MIN_STATUS}
                             AND pm.n_status > 1 THEN 1 ELSE 0 END), 0) AS conflict_event_month,
           coalesce(max(CASE WHEN pm.n_rows > 1 THEN 1 ELSE 0 END), 0) AS has_dup_rows,
           CAST(coalesce(sum(pm.n_rows - 1), 0) AS BIGINT) AS dup_row_count
    FROM o
    LEFT JOIN pm
           ON pm.loan_id = o.loan_id
          AND pm.mi BETWEEN o.a AND o.a + {last}
    GROUP BY o.loan_id, o.fpd, o.a
)
SELECT w.loan_id,
       w.fpd                              AS original_first_payment_date,
       {month_from_index("w.win_start")}  AS label_window_start,
       {month_from_index("w.win_end")}    AS label_window_end,
       w.win_start                        AS win_start_idx,
       w.win_end                          AS win_end_idx,
       {cutoff_expr}                      AS performance_cutoff,
       o2.first_observed_month,
       o2.last_observed_month,
       w.n_obs                            AS observed_month_count_in_window,
       w.n_unk                            AS unknown_status_month_count,
       CAST({WINDOW_MONTHS} - w.n_obs AS BIGINT) AS missing_month_count,
       w.first_event_month,
       t.termination_code,
       t.termination_month,
       t.termination_effective_month,
       t.n_termination_events,
       w.has_ev,
       w.conflict_any,
       w.conflict_event_month,
       w.has_dup_rows,
       w.dup_row_count,
       (o2.first_observed_month IS NOT NULL) AS has_performance
FROM win w
LEFT JOIN obs  o2 ON o2.loan_id = w.loan_id
LEFT JOIN term t  ON t.loan_id  = w.loan_id
"""


def decide_sql(core_rel: str) -> str:
    """Turn the core aggregate into label_status / label_12m / reasons.

    ``core_rel`` must expose the core columns plus ``cohort_mature`` (BOOLEAN).
    """
    cut = "performance_cutoff"
    cut_idx = month_index(cut)
    zbc_v = f"'{ZBC_VOLUNTARY}'"
    zbc_sale = ", ".join(f"'{c}'" for c in ZBC_SALE)
    zbc_dis = ", ".join(f"'{c}'" for c in ZBC_DISTRESS)

    return f"""
WITH c AS (SELECT * FROM {core_rel}),
flagged AS (
    SELECT *,
        {cut_idx} AS cut_idx,
        -- The termination event is dated by zero_balance_effective_date, which is
        -- when the loan actually left surveillance; monthly_reporting_period is
        -- only the cycle the servicer reported it in (they differ in 58,034 rows).
        -- Falls back to the reporting month on the 1 row with no effective date.
        -- term_idx anchors the COVERAGE test and must stay on the reporting
        -- month: that month is the last cycle the servicer actually reported, so
        -- it is what "observed" counts up to. (Anchoring coverage on the
        -- effective date would demand a month that by construction is never
        -- reported, turning 2,555 sound negatives into unknown.)
        {month_index('termination_month')} AS term_idx,
        -- term_eff_idx anchors the WINDOW-BOUNDARY test: the effective date is
        -- when the loan really left surveillance, and the two differ in 58,034
        -- rows. Falls back to the reporting month on the 1 row with no date.
        coalesce({month_index('termination_effective_month')},
                 {month_index('termination_month')}) AS term_eff_idx,
        CASE WHEN {cut} IS NOT NULL AND win_end_idx <= {cut_idx} THEN 1 ELSE 0 END AS mature,
        CASE WHEN coalesce({month_index('termination_effective_month')},
                           {month_index('termination_month')}) <= win_end_idx
             THEN 1 ELSE 0 END AS term_in_window,
        -- surveillance ended BEFORE the window opened: there is no in-window
        -- evidence at all, so nothing can licence a negative.
        CASE WHEN termination_code IS NOT NULL
              AND coalesce({month_index('termination_effective_month')},
                           {month_index('termination_month')}) < win_start_idx
             THEN 1 ELSE 0 END AS term_before_window,
        CASE WHEN termination_code = {zbc_v} THEN 1 ELSE 0 END AS term_voluntary,
        CASE WHEN termination_code IN ({zbc_sale}) THEN 1 ELSE 0 END AS term_sale,
        CASE WHEN termination_code = '{ZBC_DEFECT}' THEN 1 ELSE 0 END AS term_defect,
        CASE WHEN termination_code IN ({zbc_dis}) THEN 1 ELSE 0 END AS term_distress
    FROM c
),
cov AS (
    SELECT *,
        -- months that must be observed to conclude anything, given an early exit.
        -- Clamped at 0: a termination before the window would otherwise yield a
        -- negative expected-months value and make "observed >= expected" trivially
        -- true, producing a negative label from zero observations.
        greatest(least(win_end_idx, coalesce(term_idx, win_end_idx))
                 - win_start_idx + 1, 0) AS expected_months
    FROM flagged
),
verdict AS (
    SELECT *,
        CASE
          -- 1. a verified event is decisive UNLESS the event month itself is
          --    contradicted by duplicate rows. A conflict in a DIFFERENT month
          --    does not undo an event that is itself clean.
          WHEN has_ev = 1 AND conflict_event_month = 1 THEN 'unknown'
          WHEN has_ev = 1 THEN 'positive'
          -- 2. no event, but no evidence at all
          WHEN has_performance IS NOT TRUE THEN 'unknown'
          --    a conflicting month could be hiding an event, so undetermined
          WHEN conflict_any = 1 THEN 'unknown'
          -- 3. termination that stops surveillance INSIDE the window, without a
          --    D90 on record. A termination code occurring AFTER the window is
          --    irrelevant: the window is already decided on its own history.
          WHEN term_sale = 1 AND term_in_window = 1 THEN 'unknown'
          WHEN term_defect = 1 AND term_in_window = 1 THEN 'unknown'
          WHEN term_distress = 1 AND term_in_window = 1 THEN 'unknown'
          WHEN termination_code IS NOT NULL AND term_in_window = 1
               AND term_voluntary = 0 THEN 'unknown'
          -- 4. voluntary payoff inside the window is definitive
          WHEN term_voluntary = 1 AND term_in_window = 1
               AND term_before_window = 0 THEN
               CASE WHEN expected_months >= 1
                     AND observed_month_count_in_window >= expected_months
                     AND unknown_status_month_count = 0
                    THEN 'negative' ELSE 'unknown' END
          -- 5. a mature, fully-observed, clean window is negative regardless of
          --    what happened before OR after it: the window is decided on its own
          --    history, which is exactly the claim being made.
          WHEN mature = 1 AND observed_month_count_in_window = {WINDOW_MONTHS}
               AND unknown_status_month_count = 0 THEN 'negative'
          -- 6. surveillance ended before the window opened and the window is not
          --    fully observed: nothing licences a conclusion either way.
          WHEN term_before_window = 1 THEN 'unknown'
          ELSE 'unknown'
        END AS label_status
    FROM cov
),
reasoned AS (
    SELECT *,
        CASE
          -- determined verdicts carry their own justification (NULL), whether or
          -- not the window has closed: an early voluntary payoff is proven
          -- negative by the payoff itself, and a clean mature window is negative
          -- by inspection -- neither is a "gap".
          WHEN label_status = 'positive' AND mature = 1 THEN NULL
          WHEN label_status = 'positive' THEN 'window_not_mature'
          WHEN label_status = 'negative' THEN NULL
          -- undetermined below: pick the reason in priority order
          WHEN original_first_payment_date IS NULL THEN 'missing_fpd'
          WHEN has_performance IS NOT TRUE THEN 'no_performance'
          WHEN conflict_any = 1 THEN 'conflicting_duplicate_rows'
          WHEN term_before_window = 1 THEN 'terminated_before_window'
          WHEN term_sale = 1 AND term_in_window = 1 THEN 'terminated_sale'
          WHEN term_defect = 1 AND term_in_window = 1 THEN 'terminated_defect'
          WHEN term_distress = 1 AND term_in_window = 1 THEN 'terminated_credit_event_without_d90'
          WHEN termination_code IS NOT NULL AND term_in_window = 1
               AND term_voluntary = 0 THEN 'terminated_other'
          WHEN term_voluntary = 1 AND term_in_window = 1 THEN 'incomplete_before_termination'
          WHEN mature = 0 THEN 'window_not_mature'
          WHEN cohort_mature = FALSE THEN 'cohort_not_mature'
          WHEN unknown_status_month_count > 0 THEN 'unknown_status_in_window'
          WHEN observed_month_count_in_window <> {WINDOW_MONTHS} THEN 'incomplete_window_gap'
          ELSE NULL
        END AS label_reason
    FROM verdict
)
SELECT *,
       CASE label_status WHEN 'positive' THEN 1 WHEN 'negative' THEN 0 END AS label_12m,
       (CASE WHEN label_status <> 'unknown'
              AND cohort_mature
              AND mature = 1
             THEN TRUE ELSE FALSE END) AS eligible_for_primary_study
FROM reasoned
"""


def finish_sql(decided_rel: str) -> str:
    """Add the single documented primary exclusion reason."""
    return f"""
SELECT *,
       CASE
         WHEN eligible_for_primary_study THEN NULL
         WHEN label_status = 'unknown' THEN label_reason
         WHEN cohort_mature = FALSE THEN 'cohort_not_mature'
         WHEN win_end_idx > cut_idx THEN 'window_not_mature'
         ELSE 'unknown_reason_unclassified'
       END AS primary_exclusion_reason
FROM ({decided_rel})
"""
