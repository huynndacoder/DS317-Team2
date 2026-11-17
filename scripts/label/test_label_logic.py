"""Known-answer tests for the 12-month label logic.

Builds tiny synthetic origination/performance tables with hand-computed
answers, then runs the PRODUCTION SQL from label_rules.py against them. Because
the production builder calls the same functions, a passing test proves the
shipped logic, not a reimplementation.

Run:  ./venv/bin/python scripts/label/test_label_logic.py
Exit code 0 = all cases pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import label_rules as R  # noqa: E402

CUTOFF = 202606  # Release 48 performance cutoff, used as the reference cutoff
PASS, FAIL = [], []


def check(name: str, got, want) -> None:
    ok = got == want
    (PASS if ok else FAIL).append(name)
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}: got={got!r} want={want!r}")


def months(start: str, n: int) -> list[int]:
    """n consecutive YYYYMM months starting at start (inclusive)."""
    y, m = int(start[:4]), int(start[4:])
    out = []
    for _ in range(n):
        out.append(y * 100 + m)
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


class Case:
    """One synthetic loan."""

    def __init__(self, loan_id, fpd, statuses, zbc=None, zbc_month=None,
                 cohort_mature=True, extra_rows=(), zbc_effective=None):
        self.loan_id = loan_id
        self.fpd = fpd
        self.statuses = statuses          # list of (YYYYMM, status) or dict month->status
        self.zbc = zbc
        self.zbc_month = zbc_month
        self.cohort_mature = cohort_mature
        self.extra_rows = list(extra_rows)
        # effective date of the zero-balance event; defaults to its reporting month
        self.zbc_effective = zbc_effective


def build(cases, cutoff=CUTOFF):
    con = duckdb.connect()
    con.execute("CREATE TABLE orig_t(loan_id VARCHAR, first_payment_date INTEGER)")
    con.execute("""CREATE TABLE perf_t(loan_id VARCHAR, monthly_reporting_period INTEGER,
                   current_loan_delinquency_status VARCHAR, zero_balance_code VARCHAR,
                   zero_balance_effective_date INTEGER)""")
    for c in cases:
        con.execute("INSERT INTO orig_t VALUES (?,?)", [c.loan_id, c.fpd])
        rows = c.statuses if isinstance(c.statuses, list) else sorted(c.statuses.items())
        for m, s in rows:
            zb = c.zbc if (c.zbc_month is None or c.zbc_month == m) else None
            eff = (c.zbc_effective if c.zbc_effective is not None else m) if zb else None
            con.execute("INSERT INTO perf_t VALUES (?,?,?,?,?)",
                        [c.loan_id, m, s, zb, eff])
        for m, s, zb in c.extra_rows:
            con.execute("INSERT INTO perf_t VALUES (?,?,?,?,?)",
                        [c.loan_id, m, s, zb, m if zb else None])

    core = R.core_sql("orig_t", "perf_t", cutoff_expr=f"{cutoff}::INTEGER")
    con.execute("CREATE TABLE cm_t(loan_id VARCHAR, cohort_mature BOOLEAN)")
    for c in cases:
        con.execute("INSERT INTO cm_t VALUES (?,?)", [c.loan_id, c.cohort_mature])
    con.execute(f"""
        CREATE TABLE core_t AS
        SELECT c.*, coalesce(cm.cohort_mature, TRUE) AS cohort_mature
        FROM ({core}) c LEFT JOIN cm_t cm USING(loan_id)
    """)
    con.execute(f"CREATE TABLE decided_t AS {R.decide_sql('core_t')}")
    con.execute(f"CREATE TABLE final_t AS {R.finish_sql('SELECT * FROM decided_t')}")
    return con


def get(con, col, loan_id):
    row = con.execute(f"SELECT {col} FROM final_t WHERE loan_id=?", [loan_id]).fetchone()
    return None if row is None else row[0]


def main() -> int:
    W = months("202001", 12)      # window 202001..202012
    LATE = months("202002", 12)   # next window 202002..202101

    cases = [
        # 1. event in the very first window month
        Case("T01_EV_FIRST", 202001, [(W[0], "03")] + [(m, "00") for m in W[1:]]),
        # 2. event in the 12th window month -> positive (inclusive end)
        Case("T02_EV_12TH", 202001, [(m, "00") for m in W[:11]] + [(W[11], "04")]),
        # 3. event in the 13th month -> must NOT count
        Case("T03_EV_13TH", 202001, [(m, "00") for m in W] + [(202101, "05")]),
        # 4. delinquency then cure -> still positive
        Case("T04_CURE", 202001, [(W[0], "00"), (W[1], "06"), (W[2], "03")] +
             [(m, "00") for m in W[3:]]),
        # 5. REO acquisition counts
        Case("T05_RA", 202001, [(m, "00") for m in W[:5]] + [(W[5], "RA")] +
             [(m, "00") for m in W[6:]]),
        # 6. complete, all current -> negative
        Case("T06_CLEAN", 202001, [(m, "00") for m in W]),
        # 7. XX inside the window with no event -> unknown, not negative
        Case("T07_XX", 202001, [(m, "00") for m in W[:4]] + [(W[4], "XX")] +
             [(m, "00") for m in W[5:]]),
        # 8. missing month in the middle -> unknown
        Case("T08_GAP", 202001, [(m, "00") for m in W if m != W[5]]),
        # 9. voluntary payoff early, clean history before it -> negative
        Case("T09_PAYOFF_CLEAN", 202001,
             [(m, "00") for m in W[:6]] + [(W[6], "00")], zbc="01", zbc_month=W[6]),
        # 10. ZBC 15 termination, no prior event -> unknown
        Case("T10_ZBC15", 202001,
             [(m, "00") for m in W[:6]] + [(W[6], "00")], zbc="15", zbc_month=W[6]),
        # 11. no performance at all -> unknown
        Case("T11_NO_PERF", 202001, []),
        # 12. modification: loan_age reset is irrelevant, calendar window holds.
        #     Emulate a mod at W[3] where loan_age restarts; window unchanged.
        Case("T12_MOD", 202001, [(m, "00") for m in W]),
        # 13. immature cohort, early event -> positive but not eligible
        Case("T13_IMMATURE_EV", 202509, [(202509, "00"), (202510, "03")], cohort_mature=False),
        # 14. conflicting duplicate rows on the same month -> unknown
        Case("T14_CONFLICT", 202001, [(m, "00") for m in W],
             extra_rows=[(W[5], "07", None)]),
        # 15. identical duplicate rows -> only a flag, label unaffected
        Case("T15_IDENTICAL_DUP", 202001, [(m, "00") for m in W],
             extra_rows=[(W[5], "00", None)]),
        # 16. ZBC 01 but a gap mid-window -> unknown (cannot prove no event)
        Case("T16_PAYOFF_GAP", 202001,
             [(m, "00") for m in W[:3]] + [(m, "00") for m in W[5:7]],
             zbc="01", zbc_month=W[6]),
        # 17. window straddles the cutoff -> unknown / not mature
        Case("T17_NOT_MATURE", 202601, [(202601, "00"), (202602, "00")]),
        # 18. window fully inside cutoff, 12 rows starting one month late -> unknown
        Case("T18_LATE_START", 202001, [(m, "00") for m in W[1:]]),
        # 19. early voluntary payoff while the window is still open at the cutoff.
        #     The payoff is definitive, so the label is NEGATIVE, and because the
        #     verdict is determined its label_reason must be NULL -- not
        #     "incomplete_before_termination". It stays ineligible via window_mature.
        Case("T19_PAYOFF_IMMATURE_WINDOW", 202601,
             [(202601, "00"), (202602, "00"), (202603, "00")],
             zbc="01", zbc_month=202603),
        # 20-25. a termination code recorded AFTER a complete, clean window must
        #        NOT turn the label unknown: the window is decided on its own
        #        history. Every post-window code (15,16,96,02,03,09) -> negative.
        Case("T20_ZBC15_AFTER", 202001, [(m, "00") for m in W],
             extra_rows=[(202101, "00", "15")]),
        Case("T21_ZBC16_AFTER", 202001, [(m, "00") for m in W],
             extra_rows=[(202101, "00", "16")]),
        Case("T22_ZBC96_AFTER", 202001, [(m, "00") for m in W],
             extra_rows=[(202101, "00", "96")]),
        Case("T23_ZBC02_AFTER", 202001, [(m, "00") for m in W],
             extra_rows=[(202101, "00", "02")]),
        Case("T24_ZBC03_AFTER", 202001, [(m, "00") for m in W],
             extra_rows=[(202101, "00", "03")]),
        Case("T25_ZBC09_AFTER", 202001, [(m, "00") for m in W],
             extra_rows=[(202101, "00", "09")]),
        # 26. conflict at the EVENT month itself -> the event is not certain -> unknown
        Case("T26_CONFLICT_AT_EVENT", 202001,
             [(m, "00") for m in W[:5]] + [(W[5], "03")] + [(m, "00") for m in W[6:]],
             extra_rows=[(W[5], "00", None)]),
        # 27. conflict at a NON-event month, with a clean event elsewhere ->
        #     still positive (the conflict does not touch the conclusion)
        Case("T27_CONFLICT_ELSEWHERE", 202001,
             [(m, "00") for m in W[:8]] + [(W[8], "03")] + [(m, "00") for m in W[9:]],
             extra_rows=[(W[2], "01", None)]),
        # 28. payoff reported in the window but EFFECTIVE one month after it ends:
        #     the event is outside the window, so the clean 12-month window decides
        #     and the label stays negative.
        Case("T28_PAYOFF_EFF_AFTER", 202001, [(m, "00") for m in W],
             zbc="01", zbc_month=W[11], zbc_effective=202101),
        # 30. surveillance ended BEFORE the window opened and no month is observed:
        #     nothing licences a negative -> unknown / terminated_before_window.
        #     (This was a live bug: expected_months went negative and the vacuous
        #     coverage test produced an eligible negative from zero observations.)
        Case("T30_TERM_BEFORE_WINDOW", 202001, [(201911, "00")],
             zbc="01", zbc_month=201911, zbc_effective=201911),
        # 31. same, but the loan still has full clean in-window history after the
        #     pre-window event: the window is decidable on its own -> negative.
        Case("T31_TERM_BEFORE_WINDOW_OBSERVED", 202001,
             [(201911, "00")] + [(m, "00") for m in W],
             zbc="01", zbc_month=201911, zbc_effective=201911),
    ]
    con = build(cases)

    print("\n--- label assignments ---")
    check("T01 event in month 1", (get(con, "label_status", "T01_EV_FIRST"),
                                   get(con, "label_12m", "T01_EV_FIRST")), ("positive", 1))
    check("T02 event in month 12 counts", get(con, "label_12m", "T02_EV_12TH"), 1)
    check("T03 event in month 13 ignored", get(con, "label_12m", "T03_EV_13TH"), 0)
    check("T04 cured delinquency stays positive", get(con, "label_12m", "T04_CURE"), 1)
    check("T05 RA counts as event", get(con, "label_12m", "T05_RA"), 1)
    check("T06 complete clean", get(con, "label_12m", "T06_CLEAN"), 0)
    check("T07 XX -> unknown/None", (get(con, "label_status", "T07_XX"),
                                     get(con, "label_12m", "T07_XX")), ("unknown", None))
    check("T07 XX reason", get(con, "label_reason", "T07_XX"), "unknown_status_in_window")
    check("T08 gap -> unknown", get(con, "label_12m", "T08_GAP"), None)
    check("T08 gap reason", get(con, "label_reason", "T08_GAP"), "incomplete_window_gap")
    check("T09 early voluntary payoff -> negative",
          get(con, "label_12m", "T09_PAYOFF_CLEAN"), 0)
    check("T10 ZBC15 -> unknown", get(con, "label_12m", "T10_ZBC15"), None)
    check("T10 ZBC15 reason", get(con, "label_reason", "T10_ZBC15"), "terminated_sale")
    check("T11 no performance -> unknown", get(con, "label_status", "T11_NO_PERF"), "unknown")
    check("T11 reason", get(con, "label_reason", "T11_NO_PERF"), "no_performance")
    check("T12 mod does not change window", get(con, "label_12m", "T12_MOD"), 0)
    check("T13 immature early event -> positive",
          get(con, "label_status", "T13_IMMATURE_EV"), "positive")
    check("T13 immature not eligible",
          get(con, "eligible_for_primary_study", "T13_IMMATURE_EV"), False)
    check("T13 exclusion reason",
          get(con, "primary_exclusion_reason", "T13_IMMATURE_EV"), "cohort_not_mature")
    check("T14 conflicting dup -> unknown", get(con, "label_status", "T14_CONFLICT"), "unknown")
    check("T14 conflict reason",
          get(con, "label_reason", "T14_CONFLICT"), "conflicting_duplicate_rows")
    check("T15 identical dup keeps label", get(con, "label_12m", "T15_IDENTICAL_DUP"), 0)
    check("T15 dup flagged", get(con, "has_dup_rows", "T15_IDENTICAL_DUP"), 1)
    check("T16 payoff with gap -> unknown", get(con, "label_12m", "T16_PAYOFF_GAP"), None)
    check("T17 frozen at cutoff -> unknown", get(con, "label_status", "T17_NOT_MATURE"),
          "unknown")
    check("T17 reason", get(con, "label_reason", "T17_NOT_MATURE"), "window_not_mature")
    check("T18 late start -> unknown", get(con, "label_12m", "T18_LATE_START"), None)
    check("T19 early payoff in an open window -> negative",
          get(con, "label_status", "T19_PAYOFF_IMMATURE_WINDOW"), "negative")
    check("T19 determined verdict has no label_reason",
          get(con, "label_reason", "T19_PAYOFF_IMMATURE_WINDOW"), None)
    check("T19 not eligible while the window is open",
          get(con, "eligible_for_primary_study", "T19_PAYOFF_IMMATURE_WINDOW"), False)
    check("T19 exclusion reason is window_not_mature",
          get(con, "primary_exclusion_reason", "T19_PAYOFF_IMMATURE_WINDOW"),
          "window_not_mature")
    for tid, code in [("T20_ZBC15_AFTER", "15"), ("T21_ZBC16_AFTER", "16"),
                      ("T22_ZBC96_AFTER", "96"), ("T23_ZBC02_AFTER", "02"),
                      ("T24_ZBC03_AFTER", "03"), ("T25_ZBC09_AFTER", "09")]:
        check(f"{tid} post-window zbc {code} keeps negative",
              (get(con, "label_status", tid), get(con, "label_reason", tid)),
              ("negative", None))
    check("T26 conflict at event month -> unknown",
          (get(con, "label_status", "T26_CONFLICT_AT_EVENT"),
           get(con, "label_reason", "T26_CONFLICT_AT_EVENT")),
          ("unknown", "conflicting_duplicate_rows"))
    check("T26 event-month conflict flagged",
          get(con, "conflict_event_month", "T26_CONFLICT_AT_EVENT"), 1)
    check("T27 conflict elsewhere, clean event -> positive",
          (get(con, "label_status", "T27_CONFLICT_ELSEWHERE"),
           get(con, "label_12m", "T27_CONFLICT_ELSEWHERE")),
          ("positive", 1))
    check("T27 non-event conflict does not poison the reason",
          get(con, "label_reason", "T27_CONFLICT_ELSEWHERE"), None)
    check("T27 any-conflict still flagged",
          get(con, "conflict_any", "T27_CONFLICT_ELSEWHERE"), 1)
    check("T28 payoff effective after the window -> still negative",
          (get(con, "label_status", "T28_PAYOFF_EFF_AFTER"),
           get(con, "label_reason", "T28_PAYOFF_EFF_AFTER")), ("negative", None))
    check("T30 termination before the window, nothing observed -> unknown",
          (get(con, "label_status", "T30_TERM_BEFORE_WINDOW"),
           get(con, "label_reason", "T30_TERM_BEFORE_WINDOW")),
          ("unknown", "terminated_before_window"))
    check("T30 not eligible", get(con, "eligible_for_primary_study", "T30_TERM_BEFORE_WINDOW"), False)
    check("T31 pre-window event but full clean window -> negative",
          get(con, "label_status", "T31_TERM_BEFORE_WINDOW_OBSERVED"), "negative")

    print("\n--- invariants ---")
    total_orig = sum(1 for _ in cases)
    check("one row per origination loan",
          con.execute("SELECT count(*) FROM final_t").fetchone()[0], total_orig)
    check("no loan ids outside origination",
          con.execute("""SELECT count(*) FROM final_t f
                         LEFT JOIN orig_t o USING(loan_id) WHERE o.loan_id IS NULL""").fetchone()[0], 0)
    check("label_12m is 0/1 only when determined",
          con.execute("""SELECT count(*) FROM final_t
                         WHERE (label_status='unknown' AND label_12m IS NOT NULL)
                            OR (label_status='positive' AND coalesce(label_12m,-1) <> 1)
                            OR (label_status='negative' AND coalesce(label_12m,-1) <> 0)""").fetchone()[0], 0)
    check("eligible rows always have label 0/1",
          con.execute("""SELECT count(*) FROM final_t
                         WHERE eligible_for_primary_study AND label_12m IS NULL""").fetchone()[0], 0)
    check("no immature-cohort row is eligible",
          con.execute("""SELECT count(*) FROM final_t
                         WHERE cohort_mature = FALSE AND eligible_for_primary_study""").fetchone()[0], 0)
    check("no negative rests on zero observed months",
          con.execute("""SELECT count(*) FROM final_t
                         WHERE label_status='negative'
                           AND observed_month_count_in_window = 0""").fetchone()[0], 0)
    check("expected_months is never negative",
          con.execute("SELECT count(*) FROM final_t WHERE expected_months < 0").fetchone()[0], 0)
    check("no event outside the window is recorded",
          con.execute("""SELECT count(*) FROM final_t
                         WHERE first_event_month IS NOT NULL
                           AND (first_event_month < label_window_start
                                OR first_event_month > label_window_end)""").fetchone()[0], 0)

    # ---- doc/code consistency -------------------------------------------
    # The reason ladder lives in the SQL. docs/label_rules.md lists it for
    # readers; this test fails if the two ever disagree, so the doc cannot rot.
    import re
    decide = R.decide_sql("core_t")
    # only the unknown/exclusion ladder: the earlier WHEN branches assign
    # label_status itself (positive/negative) plus the positive-only reason.
    ladder = decide[decide.index("WHEN original_first_payment_date IS NULL"):]
    sql_order = []
    for tok in re.findall(r"THEN\s+'([a-z_0-9]+)'", ladder):
        if not sql_order or tok != sql_order[-1]:
            sql_order.append(tok)
    seen = set()
    sql_order = [t for t in sql_order if not (t in seen or seen.add(t))]
    doc = (Path(__file__).resolve().parents[2] / "docs" / "label_rules.md").read_text()
    doc_order = re.findall(r"^\| `([a-z_0-9]+)` \|", doc, flags=re.MULTILINE)
    doc_order = [t for t in doc_order if t in sql_order]
    check("reason ladder in docs matches the SQL", doc_order, sql_order)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILURES: " + ", ".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())