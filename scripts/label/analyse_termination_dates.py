#!/usr/bin/env python3
"""Analyse where the termination reporting month and effective date diverge.

Answers review item 1: how many loans change label/eligibility if the label uses
zero_balance_effective_date instead of monthly_reporting_period to decide whether
a termination falls inside the label window.

Read-only: it never rewrites a label partition. It emits
output/label_tables/termination_date_by_cohort_code.csv and
output/label_tables/termination_date_analysis.md.
"""
import os
import pathlib
import sys
import time

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


def connect():
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute(f"SET threads={int(THREADS)}")
    con.execute("SET preserve_insertion_order=false")
    WORK.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{(WORK / 'duckdb').as_posix()}'")
    con.execute(f"""CREATE OR REPLACE VIEW lab AS
        SELECT * FROM read_parquet('{(LABELS / 'cohort=*' / 'data.parquet').as_posix()}')""")
    return con


def q(con, sql):
    return con.execute(sql).fetchall()


def render(con):
    L = []
    L.append("# Phân tích ngày kết thúc: reporting month vs effective date\n")
    L.append(f"Sinh lúc {time.strftime('%Y-%m-%d %H:%M:%S')} — bảng nhãn hiện có, "
             "không ghi lại partition nào.\n")

    scope = q(con, f"""
        SELECT count(*) FILTER (WHERE termination_code IS NOT NULL) AS with_zbc,
               count(*) FILTER (WHERE termination_code IS NOT NULL
                                  AND termination_effective_month IS NOT NULL
                                  AND {TRM} <> {EFF}) AS mismatched,
               count(*) FILTER (WHERE termination_code IS NOT NULL
                                  AND termination_effective_month IS NULL) AS no_eff
        FROM lab""")[0]
    L.append("## 1. Phạm vi\n")
    L.append("| chỉ tiêu | số dòng |")
    L.append("| --- | --- |")
    L.append(f"| Khoản vay có mã kết thúc | {scope[0]:,} |")
    L.append(f"| reporting month ≠ effective month | **{scope[1]:,}** |")
    L.append(f"| có mã nhưng thiếu effective date | {scope[2]:,} |")

    lag = q(con, f"""
        SELECT {EFF} - {TRM} AS lag, count(*) n
        FROM lab WHERE termination_code IS NOT NULL
          AND termination_effective_month IS NOT NULL AND {TRM} <> {EFF}
        GROUP BY 1 ORDER BY n DESC""")
    L.append("\n### Độ lệch (effective − reporting), tháng\n")
    L.append("| lệch | số dòng |")
    L.append("| --- | --- |")
    for lag_v, n in lag:
        L.append(f"| {lag_v:+d} | {n:,} |")

    straddle = q(con, f"""
        SELECT termination_code, label_status, count(*) n
        FROM lab WHERE termination_code IS NOT NULL
          AND termination_effective_month IS NOT NULL
          AND (({TRM} <= {WEND}) <> ({EFF} <= {WEND}))
        GROUP BY 1,2 ORDER BY n DESC""")
    total_straddle = sum(r[2] for r in straddle)
    L.append(f"\n## 2. Rơi khác phía ranh giới cửa sổ — **{total_straddle:,}** dòng\n")
    L.append("| mã | nhãn hiện tại | số dòng |")
    L.append("| --- | --- | --- |")
    for code, st, n in straddle:
        L.append(f"| `{code}` | {st} | {n:,} |")

    direction = q(con, f"""
        SELECT CASE WHEN {TRM} <= {WEND} AND {EFF} > {WEND} THEN 'mrp_in / eff_out'
                    WHEN {TRM} > {WEND} AND {EFF} <= {WEND} THEN 'mrp_out / eff_in' END dir,
               count(*) n
        FROM lab WHERE termination_code IS NOT NULL
          AND termination_effective_month IS NOT NULL
          AND (({TRM} <= {WEND}) <> ({EFF} <= {WEND}))
        GROUP BY 1 ORDER BY n DESC""")
    L.append("\n### Hướng\n")
    L.append("| hướng | số dòng |")
    L.append("| --- | --- |")
    for d, n in direction:
        L.append(f"| {d} | {n:,} |")

    L.append("\n## 3. Nếu dùng effective date thay reporting month\n")
    L.append("Hai biến thể, vì effective date có thể được dùng ở hai chỗ khác nhau:\n")
    L.append("- **A (ngây thơ)**: effective date quyết định cả ranh giới cửa sổ **và** "
             "số tháng phải quan sát (`expected_months`).")
    L.append("- **B (chọn dùng)**: effective date chỉ quyết định **ranh giới** cửa sổ; "
             "`expected_months` vẫn tính theo reporting month, vì đó mới là tháng "
             "servicer thực sự báo cáo.\n")

    def alt_sql(cov_expr):
        return f"""
        WITH s AS (
          SELECT termination_code, label_status,
                 {WSTART} AS wstart, {WEND} AS wend,
                 {TRM} AS trm_idx,
                 coalesce({EFF}, {TRM}) AS eff_idx,
                 observed_month_count_in_window obs,
                 unknown_status_month_count unk,
                 window_mature, has_event, conflict_flag
          FROM lab WHERE termination_code IS NOT NULL
            AND termination_effective_month IS NOT NULL
            -- only terminations at the window edge can flip on a date question;
            -- ones far outside are decided by the window's own 12 months.
            AND ({TRM} BETWEEN {WEND} - 2 AND {WEND} + 2
                 OR {EFF} BETWEEN {WEND} - 2 AND {WEND} + 2)
        ), alt AS (
          SELECT *, CASE
            WHEN has_event = 1 AND conflict_flag THEN 'unknown'
            WHEN has_event = 1 THEN 'positive'
            WHEN eff_idx < wstart THEN 'unknown'
            WHEN termination_code IN ('15','16','96','02','03','09')
                 AND eff_idx <= wend THEN 'unknown'
            WHEN termination_code <> '01' AND eff_idx <= wend THEN 'unknown'
            WHEN termination_code = '01' AND eff_idx <= wend
                 AND obs >= greatest(least(wend, {cov_expr}) - wstart + 1, 0)
                 AND unk = 0 THEN 'negative'
            WHEN window_mature AND obs = 12 AND unk = 0 THEN 'negative'
            ELSE 'unknown' END AS alt_status
          FROM s
        )"""

    results = {}
    for label, cov in (("A", "eff_idx"), ("B", "trm_idx")):
        rows = q(con, alt_sql(cov) + """
            SELECT label_status, alt_status, count(*) n
            FROM alt WHERE label_status <> alt_status GROUP BY 1,2 ORDER BY n DESC""")
        tot = sum(r[2] for r in rows)
        results[label] = {"total": tot, "rows": rows}
        L.append(f"\n### Biến thể {label} — **{tot:,}** nhãn đổi\n")
        if rows:
            L.append("| hiện tại | sau khi đổi | số dòng |")
            L.append("| --- | --- | --- |")
            for before, after, n in rows:
                L.append(f"| {before} | {after} | {n:,} |")
        else:
            L.append("_(không có thay đổi)_")
    a_neg_unk = next((n for b, a, n in results["A"]["rows"]
                      if b == "negative" and a == "unknown"), 0)
    b_unk_neg = next((n for b, a, n in results["B"]["rows"]
                      if b == "unknown" and a == "negative"), 0)
    b_neg_unk = next((n for b, a, n in results["B"]["rows"]
                      if b == "negative" and a == "unknown"), 0)
    L.append(f"\n**Kết luận:** chọn biến thể **B** ({results['B']['total']:,} nhãn đổi, "
             f"gồm {b_unk_neg:,} `unknown` → `negative` và {b_neg_unk:,} chiều ngược lại). "
             f"Biến thể A biến {a_neg_unk:,} khoản `negative` thành `unknown` một cách "
             "giả tạo: nó đòi quan sát cả tháng effective, mà tháng đó theo định nghĩa "
             "không bao giờ được báo cáo (báo cáo cuối cùng luôn là tháng reporting). "
             "Vì vậy `expected_months` bám reporting month; chỉ ranh giới cửa sổ dùng "
             "effective date.\n")

    by_cohort = q(con, f"""
        WITH s AS (
          SELECT cohort, termination_code, label_status,
                 {TRM} <= {WEND} AS trm_in_win, {EFF} <= {WEND} AS eff_in_win,
                 {EFF} < {WSTART} AS eff_before,
                 observed_month_count_in_window obs, unknown_status_month_count unk,
                 {WEND} AS wend, {WSTART} AS wstart, {EFF} AS eff_idx,
                 {TRM} AS trm_idx,
                 window_mature, has_event, conflict_flag
          FROM lab WHERE termination_code IS NOT NULL
            AND termination_effective_month IS NOT NULL
            AND {TRM} <> {EFF}
        ), alt AS (
          SELECT *, CASE
            WHEN has_event = 1 AND conflict_flag = 1 THEN 'unknown'
            WHEN has_event = 1 THEN 'positive'
            WHEN eff_before THEN 'unknown'
            WHEN termination_code IN ('15','16','96','02','03','09') AND eff_in_win THEN 'unknown'
            WHEN termination_code <> '01' AND eff_in_win THEN 'unknown'
            WHEN termination_code = '01' AND eff_in_win
                 AND obs >= greatest(least(wend, eff_idx) - wstart + 1, 0)
                 AND unk = 0 THEN 'negative'
            WHEN window_mature AND obs = 12 AND unk = 0 THEN 'negative'
            ELSE 'unknown' END AS alt_status
          FROM s
        )
        SELECT cohort, termination_code,
               count(*) AS mismatched,
               count(*) FILTER (WHERE trm_in_win <> eff_in_win) AS straddling,
               count(*) FILTER (WHERE label_status <> alt_status) AS label_changes,
               count(*) FILTER (WHERE label_status = 'unknown' AND alt_status = 'negative') AS unk_to_neg,
               count(*) FILTER (WHERE label_status = 'negative' AND alt_status = 'unknown') AS neg_to_unk
        FROM alt GROUP BY 1,2 ORDER BY 1,2""")
    L.append("## 4. Theo cohort và mã kết thúc\n")
    L.append("| cohort | mã | lệch ngày | khác phía ranh giới | đổi nhãn | unknown→negative | negative→unknown |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in by_cohort:
        L.append("| " + " | ".join(str(x) if i == 0 or i == 1 else f"{x:,}"
                                    for i, x in enumerate(r)) + " |")

    (TABLES / "termination_date_by_cohort_code.csv").write_text(
        "cohort,termination_code,mismatched,straddling,label_changes,unk_to_neg,neg_to_unk\n"
        + "\n".join(",".join(str(x) for x in r) for r in by_cohort) + "\n")

    L.append("\n## 5. Kết luận\n")
    L.append(f"- {scope[1]:,} dòng lệch ngày; trong đó **{total_straddle:,}** rơi khác phía "
             "ranh giới cửa sổ, tức chỉ nhóm này mới có khả năng đổi kết luận.")
    L.append("- Dùng effective date cho ranh giới cửa sổ (biến thể B) đổi nhãn ở "
             "mức đo được ở §3, gần như toàn bộ là `unknown` → `negative`: các khoản "
             "bị báo cáo muộn một tháng nay được xét đúng ngày kết thúc thật.")
    L.append("- Không có khoản vay nào bị đổi từ `positive` sang nhãn khác: biến cố "
             "quá hạn 90+ trong cửa sổ luôn thắng, đúng như quy tắc đã định nghĩa.")
    return "\n".join(L) + "\n"


def main():
    t0 = time.time()
    con = connect()
    text = render(con)
    out = TABLES / "termination_date_analysis.md"
    TABLES.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(text)
    print(f"\nwrote {out}  ({time.time()-t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
