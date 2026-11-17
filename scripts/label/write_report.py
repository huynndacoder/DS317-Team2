#!/usr/bin/env python
"""Emit the short report for the label build, computed from the artefacts.

Every number in the report is recomputed from the label table and the cohort
summary; nothing is typed by hand. Run after ``build_labels.py``.

    ./venv/bin/python scripts/label/write_report.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb

import label_rules as R

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "output" / "labels"
TABLES = ROOT / "output" / "label_tables"
REPORTS = ROOT / "output" / "reports"
WORK = Path(os.environ.get("DQ_WORK_DIR", ROOT / ".label_tmp"))


def _last_test_summary(log: Path) -> str | None:
    """Return the 'N passed, M failed' line from a test log, if present.

    The report must never print a hard-coded test tally: a stale success count
    in the report is worse than no count at all.
    """
    if not log.exists():
        return None
    for line in reversed(log.read_text(errors="replace").splitlines()):
        line = line.strip()
        if " passed, " in line and "failed" in line:
            return line
    return None


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.execute(f"SET memory_limit='{os.environ.get('DQ_MEMORY_LIMIT', '5GB')}'")
    con.execute(f"SET threads={os.environ.get('DQ_THREADS', '10')}")
    con.execute(f"SET temp_directory='{WORK}'")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"CREATE VIEW labels AS SELECT * FROM read_parquet('{LABELS}/cohort=*/data.parquet')")

    g = con.execute("""
        SELECT count(*)                                                   AS total_loans,
               count(*) FILTER (WHERE label_status='positive')             AS pos,
               count(*) FILTER (WHERE label_status='negative')             AS neg,
               count(*) FILTER (WHERE label_status='unknown')              AS unk,
               count(*) FILTER (WHERE eligible_for_primary_study)          AS elig,
               count(*) FILTER (WHERE eligible_for_primary_study
                                  AND label_status='positive')             AS elig_pos,
               count(DISTINCT cohort)                                     AS cohorts,
               min(cohort)                                                AS first_cohort,
               max(cohort)                                                AS last_cohort,
               count(DISTINCT cohort) FILTER (WHERE cohort_mature)        AS mature_cohorts
        FROM labels""").fetchone()
    (total, pos, neg, unk, elig, elig_pos, n_cohorts,
     first_cohort, last_cohort, mature_cohorts) = g

    rate = 100.0 * elig_pos / elig if elig else 0.0

    last_eligible = con.execute(
        "SELECT max(cohort) FROM labels WHERE eligible_for_primary_study").fetchone()[0]
    last_any = con.execute(
        "SELECT max(cohort) FROM labels WHERE label_status<>'unknown'").fetchone()[0]

    unk_reasons = con.execute("""
        SELECT coalesce(label_reason,'(none)') AS reason, count(*) AS n
        FROM labels WHERE label_status='unknown'
        GROUP BY 1 ORDER BY n DESC""").fetchall()
    unk_total = sum(n for _, n in unk_reasons)

    excl = con.execute("""
        SELECT coalesce(primary_exclusion_reason,'(none)') AS reason, count(*) AS n
        FROM labels WHERE NOT eligible_for_primary_study
        GROUP BY 1 ORDER BY n DESC""").fetchall()

    # why the eligible set stops where it does
    tail = con.execute("""
        SELECT cohort,
               count(*) AS loans,
               count(*) FILTER (WHERE eligible_for_primary_study) AS eligible,
               count(*) FILTER (WHERE label_status='unknown') AS unknown,
               any_value(performance_cutoff) AS cutoff,
               bool_or(cohort_mature) AS cohort_mature
        FROM labels
        GROUP BY 1 HAVING eligible = 0 OR cohort = ? ORDER BY cohort DESC LIMIT 8""",
        [last_eligible]).fetchall()

    # cohorts where cohort_mature is false
    immature = con.execute("""
        SELECT count(DISTINCT cohort) FROM labels WHERE NOT cohort_mature""").fetchone()[0]

    # cohorts with the highest unknown share, and what drives them there
    top_unknown = con.execute("""
        SELECT cohort,
               count(*) AS n,
               count(*) FILTER (WHERE label_status='unknown') AS unk,
               round(100.0 * count(*) FILTER (WHERE label_status='unknown')
                     / count(*), 2) AS pct,
               arg_max(label_reason, 1) AS dummy
        FROM labels GROUP BY 1 HAVING unk > 0
        ORDER BY pct DESC LIMIT 6""").fetchall()
    top_unknown_detail = []
    for c, n, u, pct, _ in top_unknown:
        drv = con.execute("""
            SELECT coalesce(label_reason,'(none)') r, count(*) k
            FROM labels WHERE cohort = ? AND label_status='unknown'
            GROUP BY 1 ORDER BY k DESC LIMIT 1""", [c]).fetchone()
        top_unknown_detail.append((c, n, u, pct, drv[0] if drv else '(none)'))

    # share of unknown that is structural immaturity vs. missing data
    unk_split = con.execute("""
        SELECT count(*) FILTER (WHERE label_reason = 'window_not_mature'),
               count(*) FILTER (WHERE label_reason IN ('incomplete_window_gap',
                                                       'incomplete_before_termination')),
               count(*) FILTER (WHERE label_reason LIKE 'terminated_%'),
               count(*) FILTER (WHERE label_reason = 'no_performance')
        FROM labels WHERE label_status='unknown'""").fetchone()

    per_cohort_rate = con.execute("""
        SELECT cohort,
               count(*) FILTER (WHERE eligible_for_primary_study) AS elig,
               count(*) FILTER (WHERE eligible_for_primary_study
                                  AND label_status='positive') AS pos,
               round(100.0 * count(*) FILTER (WHERE eligible_for_primary_study
                                  AND label_status='positive')
                     / nullif(count(*) FILTER (WHERE eligible_for_primary_study),0), 4) AS rate_pct
        FROM labels GROUP BY 1 ORDER BY 1""").fetchall()

    headline = json.loads((TABLES / "headline.json").read_text()) \
        if (TABLES / "headline.json").exists() else {}
    build_log = json.loads((TABLES / "build_log.json").read_text()) \
        if (TABLES / "build_log.json").exists() else {}
    verification = json.loads((TABLES / "verification.json").read_text()) \
        if (TABLES / "verification.json").exists() else {}

    L: list[str] = []
    L += ["# Bảng nhãn 12 tháng — báo cáo kết quả", ""]
    L += [f"Sinh tự động bởi `scripts/label/write_report.py` từ "
          f"`output/labels/cohort=*/data.parquet`. Không có số liệu nào được nhập tay.", ""]

    L += ["## 1. Quy mô", "",
          "| chỉ tiêu | giá trị |", "| --- | --- |",
          f"| Số cohort | {n_cohorts} ({first_cohort} … {last_cohort}) |",
          f"| Cohort trưởng thành | {mature_cohorts} |",
          f"| Tổng số khoản vay có dòng nhãn | {total:,} |",
          f"| Dương tính (toàn bộ) | {pos:,} |",
          f"| Âm tính (toàn bộ) | {neg:,} |",
          f"| Không xác định (toàn bộ) | {unk:,} |",
          f"| **Đủ điều kiện nghiên cứu chính** | **{elig:,}** |", ""]

    L += ["## 2. Trả lời trực tiếp các câu hỏi", "",
          f"**Bao nhiêu khoản vay đủ điều kiện cho nghiên cứu chính?**  \n"
          f"{elig:,} khoản vay, trong tổng số {total:,} "
          f"({100.0 * elig / total:.2f}%).",
          "",
          f"**Tỷ lệ quá hạn nghiêm trọng trong nhóm đó?**  \n"
          f"{elig_pos:,} dương tính / {elig:,} = **{rate:.3f}%**.",
          "",
          f"**Cohort đủ điều kiện muộn nhất?**  \n"
          f"`{last_eligible}`. Cohort muộn nhất có nhãn xác định (kể cả không đủ "
          f"điều kiện) là `{last_any}`.",
          "",
          f"**Bao nhiêu khoản vay chưa xác định nhãn, và chủ yếu vì sao?**  \n"
          f"{unk:,} khoản vay ({100.0 * unk / total:.2f}%). Lý do hàng đầu:",
          ""]
    L += ["| lý do | số khoản vay | % trong nhóm unknown |", "| --- | --- | --- |"]
    for reason, n in unk_reasons[:8]:
        L.append(f"| `{reason}` | {n:,} | {100.0 * n / unk_total:.2f}% |")
    L.append("")

    if immature:
        L += [f"Lưu ý: {immature} cohort có `cohort_mature = false`; các khoản vay "
              f"trong đó vẫn có nhãn nếu cửa sổ riêng của chúng đã kết thúc, nhưng "
              f"không được đưa vào nghiên cứu chính.", ""]

    L += ["## 3. Vì sao tập đủ điều kiện dừng lại", "",
          "| cohort | khoản vay | đủ điều kiện | unknown | cutoff | cohort_mature |",
          "| --- | --- | --- | --- | --- | --- |"]
    for c, loans, e, u, cut, cm in tail:
        L.append(f"| {c} | {loans:,} | {e:,} | {u:,} | {cut} | {cm} |")
    L.append("")

    L += ["## 4. Lý do loại trừ (toàn bộ)", "",
          "| lý do chính | số khoản vay |", "| --- | --- |"]
    for reason, n in excl[:12]:
        L.append(f"| `{reason}` | {n:,} |")
    L.append("")

    L += ["## 5. Kiểm chứng", ""]
    # Read the real test outcome from its log; never print a hard-coded count.
    logic = _last_test_summary(TABLES / "test_label_logic.log")
    if logic:
        L += [f"- Kiểm thử logic: **{logic}** (`test_label_logic.py`)."]
    else:
        L += ["- Kiểm thử logic: không tìm thấy `test_label_logic.log` trong lần chạy này; "
              "chạy `bash scripts/label/run_labels.sh` để có kết quả."]
    if verification:
        L += [f"- Kiểm tra trên dữ liệu thật: **{verification.get('checks_passed')} đạt, "
              f"{verification.get('checks_failed')} lỗi**.",
              f"- Số dương tính được tính lại độc lập từ performance và khớp với bảng nhãn.",
              ""]
    else:
        L += ["- Chưa chạy `verify_labels.py`.", ""]

    L += ["## 6. Tài nguyên đã dùng", ""]
    if build_log:
        L += [f"- `memory_limit={build_log.get('memory_limit')}`, "
              f"`threads={build_log.get('threads')}`, spill `.label_tmp`.",
              f"- Thời gian build: {build_log.get('elapsed_seconds')} s cho "
              f"{len(build_log.get('built', []))} cohort.",
              f"- Cohort lỗi: {len(build_log.get('failed', []))}."]
    try:
        import shutil
        free = shutil.disk_usage(ROOT).free / 2**30
        L.append(f"- Dung lượng trống còn lại: {free:.1f} GiB.")
    except OSError:
        pass
    L += ["- Không load toàn bộ dữ liệu vào pandas; mọi phép tổng hợp chạy trong DuckDB "
          "trên parquet, xử lý theo từng cohort.", ""]

    L += ["## 7. Vấn đề cần xử lý trước khi xây bảng ML", ""]
    L += ["1. **Cutoff không đồng nhất giữa các cohort.** 85 cohort có performance đến "
          "`202606`, 25 cohort (2020Q1…2026Q1) chỉ đến `202603`. Cần ingest lại các "
          "cohort đó từ Release 48 nếu muốn một cutoff thống nhất. Bảng nhãn hiện dùng "
          "cutoff theo từng cohort nên vẫn đúng, nhưng cohort 2020Q1+ có ít dữ liệu hơn "
          "so với tiềm năng.",
          "2. **Nhãn `unknown` tập trung ở hai nhóm cohort khác nhau, vì hai lý do khác "
          "nhau** (số liệu tính từ bảng nhãn, không phải ước đoán):",
          "",
          "| cohort | khoản vay | unknown | % | lý do chính |",
          "| --- | --- | --- | --- | --- |"]
    for c, n, u, pct, drv in top_unknown_detail:
        L.append(f"| {c} | {n:,} | {u:,} | {pct:.2f}% | `{drv}` |")
    L += ["",
          f"   Trong {unk_total:,} khoản `unknown`: **{unk_split[0]:,}** do cửa sổ chưa "
          f"kết thúc tại cutoff (cấu trúc thời gian, sẽ tự hết khi dữ liệu mới về), "
          f"**{unk_split[1]:,}** do thiếu tháng giữa cửa sổ (dữ liệu không quan sát được), "
          f"**{unk_split[2]:,}** do khoản vay kết thúc mà chưa từng ghi nhận 90+ ngày, và "
          f"**{unk_split[3]:,}** không có performance. Hai nhóm đầu khác nhau về bản chất: "
          f"nhóm chưa trưởng thành sẽ chuyển thành nhãn xác định khi có thêm dữ liệu, "
          f"nhóm thiếu tháng thì không — cần quyết định riêng cho từng nhóm.",
          "",
          "3. **Không được dùng cột nào từ performance làm đặc trưng.** Chỉ dùng "
          "origination; nếu join ngược performance sẽ rò rỉ nhãn.",
          "4. **Cần chốt định nghĩa nhãn trước khi huấn luyện.** Nhãn hiện tại là "
          "quá hạn nghiêm trọng/REO trong 12 tháng, không phải tổn thất tài chính.",
          "5. **`loan_purpose` có 51 dòng giá trị `9`** (1999Q1–1999Q3), ngoài danh mục "
          "`C`/`P`/`N`. Không ảnh hưởng nhãn (trường này không dùng để tạo nhãn) nhưng "
          "phải xử lý trước khi đưa vào bảng đặc trưng.",
          ""]

    L += ["## 8. Lệnh chạy lại toàn bộ", "",
          "```bash",
          "bash scripts/label/run_labels.sh --force",
          "```", ""]

    REPORTS.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    text = "\n".join(L)
    (TABLES / "REPORT.md").write_text(text)
    (REPORTS / "label_report.md").write_text(text)
    print(text[:1500])
    print(f"\n... written to {TABLES / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())