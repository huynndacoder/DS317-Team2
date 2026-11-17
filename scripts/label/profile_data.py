#!/usr/bin/env python
"""Step 1 profiling: survey the parquet store for the 12-month label build.

Read-only. Answers, per origination cohort: row/loan-id counts, keys and
duplicates, first-payment-date and reporting-period ranges, delinquency /
zero-balance / loan-purpose distributions, window coverage, and the observed
performance cutoff. Writes a machine-readable JSON plus a Markdown report.

    ./venv/bin/python scripts/label/profile_data.py                # all 110 cohorts
    ./venv/bin/python scripts/label/profile_data.py --quarters 2020Q1 2005Q3

Never loads full tables into pandas; every statistic is computed in DuckDB over
parquet and returned as a small aggregate.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

import label_rules as R

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "parquet"
OUT = ROOT / "output" / "label_tables"
WORK = Path(os.environ.get("DQ_WORK_DIR", ROOT / ".label_tmp"))
MEMORY_LIMIT = os.environ.get("DQ_MEMORY_LIMIT", "3GB")
THREADS = int(os.environ.get("DQ_THREADS", "6"))

# Freddie Mac Release 48 (release date 2026-10-28), from the official release
# notes: origination cutoff 2026-06-30, performance cutoff 2026-06-30.
DOCUMENTED_CUTOFF = {"release": 48, "origination": 202606, "performance": 202606}


def connect() -> duckdb.DuckDBPyConnection:
    WORK.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    con.execute(f"SET threads = {THREADS}")
    con.execute(f"SET temp_directory = '{WORK}'")
    con.execute("SET preserve_insertion_order = false")
    con.execute("SET enable_progress_bar = false")
    return con


def quarters() -> list[str]:
    return sorted(p.name.split("=", 1)[1] for p in PARQUET.joinpath("orig").glob("quarter=*"))


def rel(kind: str, q: str) -> str:
    return f"read_parquet('{PARQUET / kind / f'quarter={q}' / 'data.parquet'}')"


def scalar(con, sql, default=None):
    row = con.execute(sql).fetchone()
    return default if row is None or row[0] is None else row[0]


def profile_cohort(con, q: str) -> dict:
    orig, perf = rel("orig", q), rel("perf", q)
    d: dict = {"cohort": q}

    # --- 4.2 scope and keys -----------------------------------------------
    d["orig_row_count"] = scalar(con, f"SELECT count(*) FROM {orig}", 0)
    d["orig_loan_id_count"] = scalar(con, f"SELECT count(DISTINCT loan_id) FROM {orig}", 0)
    d["orig_duplicate_loan_ids"] = d["orig_row_count"] - d["orig_loan_id_count"]
    # a duplicate loan_id is "conflicting" when its rows are not byte-identical
    con.execute(f"CREATE OR REPLACE TEMP VIEW _o AS SELECT * FROM {orig}")
    d["orig_conflicting_dup_ids"] = scalar(con, """
        SELECT count(*) FROM (
          SELECT loan_id, count(*) AS n_rows,
                 (SELECT count(*) FROM (SELECT DISTINCT o2.* FROM _o o2
                                        WHERE o2.loan_id = _o.loan_id)) AS n_distinct
          FROM _o GROUP BY loan_id
        ) WHERE n_rows > n_distinct""", 0)

    d["perf_row_count"] = scalar(con, f"SELECT count(*) FROM {perf}", 0)
    d["perf_loan_id_count"] = scalar(con, f"SELECT count(DISTINCT loan_id) FROM {perf}", 0)
    d["perf_orphan_loan_ids"] = scalar(con, f"""
        SELECT count(*) FROM (
          SELECT DISTINCT p.loan_id FROM {perf} p
          ANTI JOIN (SELECT loan_id FROM {orig}) o USING (loan_id)
        )""", 0)
    d["orig_without_performance"] = scalar(con, f"""
        SELECT count(*) FROM (SELECT loan_id FROM {orig}) o
        ANTI JOIN (SELECT DISTINCT loan_id FROM {perf}) p USING (loan_id)""", 0)

    # (loan_id, reporting month) duplicates: identical vs conflicting
    con.execute(f"CREATE OR REPLACE TEMP VIEW _p AS SELECT * FROM {perf}")
    dup = con.execute("""
        SELECT coalesce(sum(n_rows - 1), 0)                        AS extra_rows,
               coalesce(sum(CASE WHEN n_rows > n_distinct THEN 1 ELSE 0 END), 0) AS conflicting
        FROM (
          SELECT loan_id, monthly_reporting_period, count(*) AS n_rows,
                 (SELECT count(*) FROM (SELECT DISTINCT p2.* FROM _p p2
                                        WHERE p2.loan_id = _p.loan_id
                                          AND p2.monthly_reporting_period
                                              = _p.monthly_reporting_period)) AS n_distinct
          FROM _p GROUP BY loan_id, monthly_reporting_period
          HAVING count(*) > 1
        )""").fetchone()
    d["perf_dup_key_extra_rows"] = int(dup[0])
    d["perf_conflicting_dup_keys"] = int(dup[1])

    # --- 4.3 time and status ----------------------------------------------
    t = con.execute(f"""
        SELECT min(first_payment_date), max(first_payment_date),
               count(*) FILTER (WHERE first_payment_date IS NULL) AS n_null_fpd,
               count(*) FILTER (WHERE first_payment_date IS NOT NULL
                                  AND (first_payment_date % 100 NOT BETWEEN 1 AND 12
                                       OR first_payment_date < 190001)) AS n_bad_fpd,
               count(*) FILTER (WHERE first_payment_date > {DOCUMENTED_CUTOFF['performance']}) AS n_fpd_after_cutoff
        FROM {orig}""").fetchone()
    (d["min_first_payment_date"], d["max_first_payment_date"], d["null_first_payment_date"],
     d["invalid_first_payment_date"], d["first_payment_date_after_cutoff"]) = t
    p = con.execute(f"""
        SELECT min(monthly_reporting_period), max(monthly_reporting_period)
        FROM {perf}""").fetchone()
    d["min_reporting_period"], d["max_reporting_period"] = p
    d["performance_cutoff"] = p[1]
    # first payment dates beyond THIS cohort's own observed frontier. Distinct from
    # first_payment_date_after_cutoff, which is measured against the documented
    # Release 48 cutoff (202606) and therefore understates cohorts whose ingest
    # still ends at 202603.
    d["first_payment_date_after_own_cutoff"] = scalar(con, f"""
        SELECT count(*) FROM {orig}
        WHERE first_payment_date > {p[1]}""", 0)

    d["loan_purpose"] = dict(con.execute(f"""
        SELECT coalesce(loan_purpose, '(null)'), count(*) FROM {orig}
        GROUP BY 1 ORDER BY 2 DESC""").fetchall())

    # delinquency domain: keep XX / RA / NULL / empty / everything else distinct
    d["delinquency_status"] = dict(con.execute(f"""
        SELECT coalesce(current_loan_delinquency_status, '(null)'), count(*) FROM {perf}
        GROUP BY 1 ORDER BY 2 DESC""").fetchall())
    d["zero_balance_code"] = dict(con.execute(f"""
        SELECT coalesce(zero_balance_code, '(null)'), count(*) FROM {perf}
        GROUP BY 1 ORDER BY 2 DESC""").fetchall())
    d["modification_flag"] = dict(con.execute(f"""
        SELECT coalesce(modification_flag, '(null)'), count(*) FROM {perf}
        GROUP BY 1 ORDER BY 2 DESC""").fetchall())

    # --- window coverage (labels are anchored on first_payment_date) --------
    # month index of first_payment_date, qualified per query below
    cov = con.execute(f"""
        WITH o AS (SELECT loan_id, first_payment_date FROM {orig}
                   WHERE first_payment_date IS NOT NULL),
             pm AS (SELECT loan_id, {R.month_index('monthly_reporting_period')} AS mi
                    FROM {perf}),
             w AS (
               SELECT o.loan_id,
                      count(pm.mi) AS n_obs
               FROM o LEFT JOIN pm
                 ON pm.loan_id = o.loan_id
                AND pm.mi BETWEEN {R.month_index('o.first_payment_date')}
                              AND {R.month_index('o.first_payment_date')} + {R.WINDOW_MONTHS - 1}
               GROUP BY 1)
        SELECT count(*) FILTER (WHERE n_obs = 0),
               count(*) FILTER (WHERE n_obs BETWEEN 1 AND {R.WINDOW_MONTHS - 1}),
               count(*) FILTER (WHERE n_obs >= {R.WINDOW_MONTHS}),
               avg(n_obs)
        FROM w""").fetchone()
    (d["loans_with_zero_window_months"], d["loans_with_partial_window"],
     d["loans_with_full_window"], d["avg_observed_months"]) = cov

    # performance series start relative to the window start
    st = con.execute(f"""
        WITH o AS (SELECT loan_id, {R.month_index('first_payment_date')} AS a
                   FROM {orig} WHERE first_payment_date IS NOT NULL),
             f AS (SELECT loan_id, min({R.month_index('monthly_reporting_period')}) AS fmi
                   FROM {perf} GROUP BY 1)
        SELECT count(*) FILTER (WHERE f.fmi IS NULL),
               count(*) FILTER (WHERE f.fmi < o.a),
               count(*) FILTER (WHERE f.fmi = o.a),
               count(*) FILTER (WHERE f.fmi > o.a)
        FROM o LEFT JOIN f USING (loan_id)""").fetchone()
    (d["loans_no_performance"], d["loans_perf_starts_before_window"],
     d["loans_perf_starts_at_window"], d["loans_perf_starts_after_window"]) = st

    # months present in the window whose status cannot be interpreted
    d["loans_with_unknown_status_in_window"] = scalar(con, f"""
        WITH o AS (SELECT loan_id, first_payment_date FROM {orig}
                   WHERE first_payment_date IS NOT NULL)
        SELECT count(DISTINCT p.loan_id) FROM {perf} p JOIN o USING (loan_id)
        WHERE {R.month_index('p.monthly_reporting_period')}
              BETWEEN {R.month_index('o.first_payment_date')}
                  AND {R.month_index('o.first_payment_date')} + {R.WINDOW_MONTHS - 1}
          AND {R.status_as_int('p.current_loan_delinquency_status')} IS NULL""", 0)

    # events, for a sanity cross-check against the label builder
    d["loans_with_event_in_window"] = scalar(con, f"""
        WITH o AS (SELECT loan_id, first_payment_date FROM {orig}
                   WHERE first_payment_date IS NOT NULL)
        SELECT count(DISTINCT p.loan_id) FROM {perf} p JOIN o USING (loan_id)
        WHERE {R.month_index('p.monthly_reporting_period')}
              BETWEEN {R.month_index('o.first_payment_date')}
                  AND {R.month_index('o.first_payment_date')} + {R.WINDOW_MONTHS - 1}
          AND {R.status_as_int('p.current_loan_delinquency_status')} >= {R.EVENT_MIN_STATUS}""", 0)

    d["xx_outside_window"] = scalar(con, f"""
        WITH o AS (SELECT loan_id, first_payment_date FROM {orig}
                   WHERE first_payment_date IS NOT NULL)
        SELECT count(*) FROM {perf} p JOIN o USING (loan_id)
        WHERE p.current_loan_delinquency_status = '{R.UNKNOWN_STATUS}'
          AND NOT ({R.month_index('p.monthly_reporting_period')}
                   BETWEEN {R.month_index('o.first_payment_date')}
                       AND {R.month_index('o.first_payment_date')} + {R.WINDOW_MONTHS - 1})""", 0)

    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarters", nargs="*", help="subset of cohorts (default: all)")
    args = ap.parse_args()

    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    con = connect()
    qs = args.quarters or quarters()

    usage = shutil.disk_usage(ROOT)
    print(f"profiling {len(qs)} cohort(s)  memory_limit={MEMORY_LIMIT} threads={THREADS} "
          f"spill={WORK}\n  disk free: {usage.free / 2**30:.1f} GiB")

    rows, failed = [], []
    for i, q in enumerate(qs, 1):
        try:
            d = profile_cohort(con, q)
        except Exception as exc:  # keep going: one bad cohort must not hide the rest
            failed.append({"cohort": q, "error": f"{type(exc).__name__}: {exc}"})
            print(f"  [{i}/{len(qs)}] {q}  FAILED  {type(exc).__name__}: {exc}")
            continue
        rows.append(d)
        print(f"  [{i}/{len(qs)}] {q} orig={d['orig_row_count']:,} "
              f"perf={d['perf_row_count']:,} cut={d['performance_cutoff']} "
              f"ev={d['loans_with_event_in_window']:,}")

    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documented_release": DOCUMENTED_CUTOFF,
        "settings": {"memory_limit": MEMORY_LIMIT, "threads": THREADS, "spill": str(WORK)},
        "cohorts": rows,
        "failed": failed,
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    (OUT / "profile.json").write_text(json.dumps(doc, indent=1, default=str))
    (OUT / "profile_summary.md").write_text(render_markdown(doc))

    print(f"\nprofile written: {OUT / 'profile.json'}  ({doc['elapsed_seconds']}s)")
    if failed:
        print(f"  {len(failed)} cohort(s) failed: {[f['cohort'] for f in failed]}")
    print(f"  totals: orig={sum(r['orig_row_count'] for r in rows):,} "
          f"perf={sum(r['perf_row_count'] for r in rows):,} "
          f"events={sum(r['loans_with_event_in_window'] for r in rows):,}")
    return 1 if failed else 0


def _merge(rows, key):
    """Sum a per-cohort {value: count} distribution across cohorts."""
    agg: dict[str, int] = {}
    for r in rows:
        for k, v in r[key].items():
            agg[k] = agg.get(k, 0) + v
    return agg


def render_markdown(doc: dict) -> str:
    rows = doc["cohorts"]
    L = ["# Data profiling for the 12-month label build", ""]
    L.append(f"Generated {doc['generated_at']} · {len(rows)} cohort(s) · "
             f"memory_limit={doc['settings']['memory_limit']} · threads={doc['settings']['threads']}")
    L.append("")

    tot_orig = sum(r["orig_row_count"] for r in rows)
    tot_perf = sum(r["perf_row_count"] for r in rows)
    tot_ev = sum(r["loans_with_event_in_window"] for r in rows)
    L += ["## Totals", "",
          f"- origination rows: **{tot_orig:,}**",
          f"- performance rows: **{tot_perf:,}**",
          f"- loans with an in-window event: **{tot_ev:,}**", ""]

    # key integrity
    L += ["## Key integrity", "", "| check | result |", "| --- | --- |"]
    L.append(f"| origination duplicate loan_ids | {sum(r['orig_duplicate_loan_ids'] for r in rows):,} |")
    L.append(f"| origination conflicting duplicate loan_ids | {sum(r['orig_conflicting_dup_ids'] for r in rows):,} |")
    L.append(f"| performance rows in duplicate (loan_id, month) groups | {sum(r['perf_dup_key_extra_rows'] for r in rows):,} |")
    L.append(f"| performance conflicting duplicate keys | {sum(r['perf_conflicting_dup_keys'] for r in rows):,} |")
    L.append(f"| performance orphans (not in origination) | {sum(r['perf_orphan_loan_ids'] for r in rows):,} |")
    L.append(f"| origination without performance | {sum(r['orig_without_performance'] for r in rows):,} |")
    L.append(f"| rows missing first_payment_date | {sum(r['null_first_payment_date'] for r in rows):,} |")
    L.append(f"| rows with invalid first_payment_date | {sum(r['invalid_first_payment_date'] for r in rows):,} |")
    L.append(f"| rows with first_payment_date after cutoff | {sum(r['first_payment_date_after_cutoff'] for r in rows):,} |")
    L.append(f"| `{R.UNKNOWN_STATUS}` rows outside a label window | {sum(r['xx_outside_window'] for r in rows):,} |")
    L.append(f"| loans with uninterpretable status inside the window | {sum(r['loans_with_unknown_status_in_window'] for r in rows):,} |")
    L.append("")

    # cutoffs
    L += ["## Performance cutoff by cohort", ""]
    by_cut: dict[str, list[str]] = {}
    for r in rows:
        by_cut.setdefault(str(r["performance_cutoff"]), []).append(r["cohort"])
    for cut, qs in sorted(by_cut.items()):
        shown = ", ".join(qs) if len(qs) <= 6 else f"{qs[0]} … {qs[-1]} ({len(qs)} cohorts)"
        L.append(f"- **{cut}** — {shown}")
    L.append("")

    L += ["## Window coverage", "",
          "| cohort | loans | full 12m | partial | 0 months | perf starts after window | cut | events |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        L.append(f"| {r['cohort']} | {r['orig_loan_id_count']:,} | {r['loans_with_full_window']:,} | "
                 f"{r['loans_with_partial_window']:,} | {r['loans_with_zero_window_months']:,} | "
                 f"{r['loans_perf_starts_after_window']:,} | {r['performance_cutoff']} | "
                 f"{r['loans_with_event_in_window']:,} |")
    L.append("")

    L += ["## Delinquency status domain (all cohorts merged)", ""]
    merged: dict[str, int] = {}
    for r in rows:
        for k, v in r["delinquency_status"].items():
            merged[k] = merged.get(k, 0) + v
    for k, v in sorted(merged.items(), reverse=True, key=lambda kv: kv[1]):
        L.append(f"- `{k}`: {v:,}")
    L.append("")

    # every category kept separate, including (null) — never folded into 00 / "not delinquent"
    for key, title, note in [
        ("loan_purpose", "Loan purpose distribution",
         "P=Purchase, C=Refinance cash-out, N=Refinance no cash-out, "
         "R=Refinance not specified, 9=Not Available (Release 48)"),
        ("zero_balance_code", "Zero balance code distribution",
         "`01` voluntary payoff, `02`/`03`/`09` credit event, `15`/`16` sale, `96` defect"),
        ("modification_flag", "Modification flag distribution", "Y=current period modification, P=prior"),
    ]:
        L += [f"## {title}", "", f"_{note}_", "",
              "| value | rows |", "| --- | --- |"]
        agg: dict[str, int] = {}
        for r in rows:
            for k, v in r[key].items():
                agg[k] = agg.get(k, 0) + v
        for k, v in sorted(agg.items(), reverse=True, key=lambda kv: kv[1]):
            L.append(f"| `{k}` | {v:,} |")
        L.append("")

    # per-cohort zero-balance split, so terminations are visible without merging the domain
    L += ["## Terminations by cohort (zero balance code)", "",
          "| cohort | loans | terminated | `01` | `02`/`03`/`09` | `15`/`16` | `96` | other |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        z = r["zero_balance_code"]
        get = lambda codes: sum(v for k, v in z.items() if k in codes)  # noqa: E731
        n_01 = get({"01"})
        n_dist = get({"02", "03", "09"})
        n_sale = get({"15", "16"})
        n_def = get({"96"})
        known = n_01 + n_dist + n_sale + n_def
        n_other = sum(v for k, v in z.items() if k not in {"01", "02", "03", "09", "15", "16", "96"})
        L.append(f"| {r['cohort']} | {r['orig_loan_id_count']:,} | {known + n_other:,} | "
                 f"{n_01:,} | {n_dist:,} | {n_sale:,} | {n_def:,} | {n_other:,} |")
    L.append("")

    # fpd / reporting period ranges, per cohort
    L += ["## Date ranges and invalid dates", "",
          "| cohort | fpd min | fpd max | mrp min | mrp max | null fpd | invalid fpd | fpd after cutoff |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        L.append(f"| {r['cohort']} | {r['min_first_payment_date']} | {r['max_first_payment_date']} | "
                 f"{r['min_reporting_period']} | {r['max_reporting_period']} | "
                 f"{r['null_first_payment_date']:,} | {r['invalid_first_payment_date']:,} | "
                 f"{r['first_payment_date_after_cutoff']:,} |")
    L.append("")
    L += ["> Lưu ý: kiểm tra độ trung thực khi chuyển đổi (parse/schema) được tách khỏi "
          "kiểm tra chất lượng dữ liệu nghiệp vụ. Parse thành công **không** đồng nghĩa "
          "dữ liệu đúng: một `first_payment_date` đọc được vẫn có thể mâu thuẫn với "
          "ngày giải ngân thực tế, và một trạng thái `00` đọc được vẫn có thể là tháng "
          "trước kỳ thanh toán đầu tiên.", ""]

    if doc["failed"]:
        L += ["## Failed cohorts", ""] + [f"- {f['cohort']}: `{f['error']}`" for f in doc["failed"]] + [""]

    # ---- points of attention: undocumented codes / structural oddities -------
    issues: list[str] = []

    purpose = _merge(rows, "loan_purpose")
    bad_purpose = {k: v for k, v in purpose.items() if k not in {"C", "P", "N", "(null)"}}
    if bad_purpose:
        detail = ", ".join(f"`{k}` ({v:,})" for k, v in sorted(bad_purpose.items()))
        cohorts = [r["cohort"] for r in rows if any(
            k in r["loan_purpose"] for k in bad_purpose)]
        issues.append(
            f"`loan_purpose` có giá trị ngoài tài liệu: {detail}, chỉ trong cohort "
            f"{', '.join(cohorts)}. Không ảnh hưởng nhãn (đây là trường đặc trưng, "
            f"không dùng để tạo nhãn), nhưng phải xử lý trước khi đưa vào bảng ML.")
    zbc = _merge(rows, "zero_balance_code")
    known_zbc = {"01", "02", "03", "09", "15", "16", "96", "(null)"}
    bad_zbc = {k: v for k, v in zbc.items() if k not in known_zbc}
    if bad_zbc:
        detail = ", ".join(f"`{k}` ({v:,})" for k, v in sorted(bad_zbc.items()))
        issues.append(f"`zero_balance_code` có giá trị ngoài danh mục Release 48: {detail}. "
                      f"Những khoản này rơi vào `terminated_other` và thành `unknown`.")
    status = _merge(rows, "delinquency_status")
    bad_status = {k: v for k, v in status.items()
                  if not (k == "RA" or k == "XX" or k == "(null)" or
                          (len(k) == 2 and k.isdigit()))}
    if bad_status:
        detail = ", ".join(f"`{k}` ({v:,})" for k, v in sorted(bad_status.items()))
        issues.append(f"`current_loan_delinquency_status` có giá trị ngoài miền "
                      f"`\\d{{2}}`/`RA`/`XX`: {detail}.")
    after_doc = sum(r["first_payment_date_after_cutoff"] for r in rows)
    after_own = sum(r["first_payment_date_after_own_cutoff"] for r in rows)
    if after_doc or after_own:
        issues.append(
            f"**{after_own:,}** khoản vay có `first_payment_date` sau performance "
            f"cutoff **của chính cohort đó** ({after_doc:,} khoản sau cutoff "
            f"toàn cục 202606 của Release 48). Với các cohort chỉ có dữ liệu tới "
            f"202603, con số theo cohort mới là con số đúng. Cửa sổ nhãn của những "
            f"khoản này nằm ngoài dữ liệu → `window_mature = false`, không đủ điều "
            f"kiện nghiên cứu chính.")
    no_perf = sum(r["orig_without_performance"] for r in rows)
    if no_perf:
        issues.append(f"{no_perf:,} khoản vay origination không có bản ghi performance "
                      f"→ `unknown` với lý do `no_performance`.")
    starts_late = sum(r["loans_perf_starts_after_window"] for r in rows)
    if starts_late:
        issues.append(f"{starts_late:,} khoản vay có lịch sử performance bắt đầu **sau** "
                      f"first payment date. Đây là nguồn `incomplete_window_gap` lớn nhất "
                      f"và là lý do chính khiến nhãn `unknown`. Không thể kết luận âm tính "
                      f"cho nhóm này nếu không có thêm giả định.")

    L += ["## Points of attention", ""]
    if issues:
        L += [f"{i}. {t}" for i, t in enumerate(issues, 1)]
    else:
        L.append("Không phát hiện điểm bất thường nào trong phạm vi đã khảo sát.")
    L.append("")
    L += ["## Ảnh hưởng trực tiếp tới việc tạo nhãn", ""]
    L += [
        "- Cửa sổ nhãn tính bằng tháng lịch từ `first_payment_date`; không dùng `loan_age` "
        "vì trường này bị reset sau modification.",
        f"- `XX` là sentinel, không phải `0`. Trong dữ liệu hiện tại `XX` chỉ xuất hiện ở "
        f"`loan_age = 0` (tháng trước kỳ thanh toán đầu tiên) nên không lọt vào cửa sổ; "
        f"quy tắc vẫn map `XX` → `unknown`.",
        "- Khoảng trống tháng giữa cửa sổ dẫn tới `unknown`, không được nén lại bằng cách "
        "lấy \"12 dòng performance đầu tiên\".",
        "- Cutoff lấy theo từng cohort từ `max(monthly_reporting_period)`; một cutoff toàn "
        "cục sẽ đánh dấu nhầm cửa sổ đã trưởng thành ở các cohort được ingest từ bản "
        "Release cũ.",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())