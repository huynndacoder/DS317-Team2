#!/usr/bin/env python3
"""Export the origination schema (column, type, null share) and Loan Purpose stats.

The Gold table can only be built against a schema read from the actual files, not
from a remembered column list: Release 47 renamed several origination fields and
moved two of them into the performance file. This script reads the parquet
metadata directly, checks that every column has ONE type across all partitions,
and reports the distribution of `loan_purpose` including undocumented values.

Read-only. Writes into output/schema/:
  orig_schema.csv, orig_schema.md, loan_purpose_stats.csv, loan_purpose_by_cohort.csv
"""
import os
import pathlib
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[2]
PARQUET = ROOT / "parquet"
OUT = ROOT / "output" / "schema"
MEMORY_LIMIT = os.environ.get("DQ_MEMORY_LIMIT", "5GB")
THREADS = os.environ.get("DQ_THREADS", "10")
WORK = pathlib.Path(os.environ.get("DQ_WORK_DIR", ROOT / ".label_tmp"))


def connect():
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute(f"SET threads={int(THREADS)}")
    con.execute("SET preserve_insertion_order=false")
    WORK.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{(WORK / 'duckdb').as_posix()}'")
    return con


def quarters():
    return sorted(p.name.split("=", 1)[1] for p in (PARQUET / "orig").glob("quarter=*"))


def rel(q):
    return (PARQUET / "orig" / f"quarter={q}" / "data.parquet").as_posix()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = connect()
    qs = quarters()
    print(f"origination partitions: {len(qs)}")

    con.execute(f"""CREATE OR REPLACE VIEW orig AS
        SELECT * FROM read_parquet('{(PARQUET / 'orig' / 'quarter=*' / 'data.parquet').as_posix()}',
                                   hive_partitioning=true)""")

    schema = [(c[0], c[1]) for c in
              con.execute("DESCRIBE SELECT * FROM orig").fetchall() if c[0] != "quarter"]
    n = con.execute("SELECT count(*) FROM orig").fetchone()[0]
    ids = con.execute("SELECT count(DISTINCT loan_id) FROM orig").fetchone()[0]
    print(f"rows {n:,} | distinct loan_id {ids:,} | columns {len(schema)}")

    # One type per column across all partitions. A column that changes type
    # between partitions is a feature change disguised as data.
    types = {}
    for q in qs:
        for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{rel(q)}')").fetchall():
            types.setdefault(row[0], {}).setdefault(row[1], []).append(q)
    drift = [(name, typ, len(v), v[0])
             for name, d in types.items() if len(d) > 1 for typ, v in d.items()]
    if drift:
        print("TYPE DRIFT DETECTED")
        for name, typ, k, sample in drift:
            print(f"   {name}: {typ} in {k} partition(s), e.g. {sample}")

    # Null share in a single pass over the store.
    counts = con.execute(
        "SELECT " + ", ".join(f'count(*) FILTER (WHERE "{c}" IS NULL)' for c, _ in schema)
        + " FROM orig").fetchone()
    nulls = dict(zip([c for c, _ in schema], counts))

    with (OUT / "orig_schema.csv").open("w") as f:
        f.write("column,type,null_rows,null_pct,type_stable\n")
        for name, typ in schema:
            pct = 100.0 * nulls[name] / n if n else 0.0
            f.write(f'"{name}","{typ}",{nulls[name]},{pct:.4f},'
                    f'{"yes" if len(types.get(name, {})) <= 1 else "NO"}\n')

    lp = con.execute("""
        SELECT coalesce(loan_purpose, '(null)') AS value,
               count(*) AS loans,
               round(100.0 * count(*) / sum(count(*)) OVER (), 4) AS pct
        FROM orig GROUP BY 1 ORDER BY loans DESC""").fetchdf()
    lp.to_csv(OUT / "loan_purpose_stats.csv", index=False)
    con.execute(f"""COPY (
        SELECT quarter AS cohort, coalesce(loan_purpose,'(null)') AS value, count(*) AS loans
        FROM orig GROUP BY 1,2 ORDER BY 1,2
      ) TO '{(OUT / 'loan_purpose_by_cohort.csv').as_posix()}' (HEADER, DELIMITER ',')""")
    odd = con.execute("""
        SELECT quarter AS cohort, loan_purpose, count(*) AS loans
        FROM orig WHERE loan_purpose IS NULL OR loan_purpose NOT IN ('C','P','N')
        GROUP BY 1,2 ORDER BY 1,2""").fetchdf()

    md = [f"# Origination schema ({len(schema)} cột)\n",
          f"Đọc trực tiếp từ `parquet/orig/quarter=*/data.parquet`: **{n:,}** dòng, "
          f"**{ids:,}** `loan_id` phân biệt, {len(qs)} partition "
          f"({qs[0]} … {qs[-1]}).\n",
          "\n## Cột, kiểu dữ liệu, tỷ lệ null\n",
          "| cột | kiểu | null | % null | kiểu ổn định |",
          "| --- | --- | --- | --- | --- |"]
    for name, typ in schema:
        pct = 100.0 * nulls[name] / n if n else 0.0
        md.append(f"| `{name}` | `{typ}` | {nulls[name]:,} | {pct:.4f}% | "
                  f"{'có' if len(types.get(name, {})) <= 1 else '**KHÔNG**'} |")

    md.append("\n## Loan Purpose\n")
    md.append("| giá trị | số khoản | % |")
    md.append("| --- | --- | --- |")
    for _, r in lp.iterrows():
        md.append(f"| `{r['value']}` | {int(r['loans']):,} | {r['pct']:.4f}% |")
    md.append(f"\nTổng: **{int(lp['loans'].sum()):,}** khoản vay. "
              "Nguồn: Freddie Mac General User Guide, Release 48 (2026-10-28). "
              "`P` = Purchase; `C` = Refinance - Cash Out; `N` = Refinance - No Cash Out; "
              "`R` = Refinance - Not Specified; `9` = Not Available.\n"
              "`R` không xuất hiện trong dữ liệu này; `9` là mã **được tài liệu định nghĩa**, "
              "không phải giá trị lạ. Khác biệt phiên bản: bảng trường của Release 19 (2018-03) "
              "chỉ liệt kê P/C/N/9 và chưa có `R`; Release 47/48 mới đổi nhãn `C` thành "
              "'Refinance - Cash Out'.\n")

    if len(odd):
        md.append("\n### Giá trị ngoài tập Purchase/Refinance (`C`/`N`/`P`/`R`)\n")
        md.append("| cohort | giá trị | số khoản |")
        md.append("| --- | --- | --- |")
        for _, r in odd.iterrows():
            md.append(f"| {r['cohort']} | `{r['loan_purpose']}` | {int(r['loans']):,} |")
        md.append("\n`loan_purpose` là trường mô tả, **không** tham gia tạo nhãn. "
                  "Mã `9` là **Not Available** theo General User Guide Release 48 — đây là "
                  "giá trị được tài liệu định nghĩa, không phải giá trị lạ; giữ nguyên, "
                  "không tự đổi thành `N`.\n")

    if drift:
        md.append("\n## Cảnh báo: kiểu dữ liệu thay đổi giữa các partition\n")
        for name, typ, k, sample in drift:
            md.append(f"- `{name}`: `{typ}` ở {k} partition (ví dụ {sample})")
    else:
        md.append("\n## Kiểu dữ liệu\n\nMọi cột có **một** kiểu duy nhất trên toàn bộ "
                  f"{len(qs)} partition — không phát hiện lệch kiểu.\n")

    (OUT / "orig_schema.md").write_text("\n".join(md) + "\n")
    print(f"wrote {OUT/'orig_schema.csv'}, orig_schema.md, loan_purpose_stats.csv, "
          "loan_purpose_by_cohort.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
