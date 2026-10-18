"""
build_warehouse.py — Dựng kho dữ liệu DuckDB (persistent) cho bộ dữ liệu
Freddie Mac SFLLD trong `data/`.

Thiết kế
--------
- `warehouse.duckdb` là MỘT file, không cần server.
- Lớp **silver** = bảng ĐÃ ĐỊNH KIỂU (INTEGER/DOUBLE/VARCHAR). Đo thực tế trên
  quý 2020Q1 (22,2M dòng): 0.54 GB thay vì 0.74 GB nếu để toàn VARCHAR
  (nén 4,71x so với text gốc) và nạp NHANH hơn (19,3s vs 38,4s) vì không phải
  parse chuỗi lúc truy vấn.
- Lớp **bronze** không lưu trong DB: file `.txt` gốc trên đĩa CHÍNH LÀ bronze
  (giữ nguyên độ trung thực, không nhân đôi ~18 GB). Muốn dựng lại silver chỉ
  cần chạy lại script này, không cần suy đoán lại quy tắc.
- Mỗi quý là MỘT partition của bảng (`quarter` + `source`), nên truy vấn có
  `WHERE quarter = '2026Q1'` sẽ prune thay vì quét 533M dòng.
- Resumable: mỗi (quarter, source) ghi xong được đánh dấu trong bảng
  `_load_log`; chạy lại sẽ bỏ qua phần đã nạp.

Bộ nhớ
------
Máy 15 GB RAM, `/tmp` là tmpfs (RAM-backed) nên TUYỆT ĐỐI không cho DuckDB
spill vào `/tmp` — dùng `.duckdb_tmp/` trên đĩa thật.

Cách dùng
---------
    venv/bin/python scripts/build_warehouse.py            # nạp phần còn thiếu
    venv/bin/python scripts/build_warehouse.py --rebuild   # xoá và nạp lại
    venv/bin/python scripts/build_warehouse.py --verify    # chỉ kiểm tra
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq_core as dq

ROOT = dq.ROOT
DB_PATH = ROOT / "warehouse.duckdb"
TMP_DIR = dq.TMP_DIR

# ---------------------------------------------------------------------------
# Kiểu dữ liệu cho từng cột.
#
# Nguyên tắc: cột nào THỰC SỰ là số thì khai báo số. Những cột mã/định danh giữ
# VARCHAR để bảo toàn số 0 đứng đầu ('01', '02'...) và các sentinel ('XX',
# '9999', 'RA') — nếu cast sang INT sẽ mất thông tin và sai ngữ nghĩa.
# ---------------------------------------------------------------------------
ORIG_INT = {
    'first_payment_date', 'maturity_date', 'msa', 'mi_percentage',
    'number_of_units', 'cltv', 'dti', 'original_upb', 'ltv',
    'original_loan_term', 'number_of_borrowers', 'credit_score',
    'vantage_score_4',
}
# postal_code PHẢI là VARCHAR: dữ liệu gốc là mã 3 ký tự có số 0 đứng đầu
# ('006' = Puerto Rico, '010'...). Cast sang INTEGER sẽ thành 6, 10 -> mất
# thông tin và sai ngữ nghĩa. Đo trên 2020Q1: 37.840 dòng bị ảnh hưởng.
ORIG_TEXT_FORCE = {'postal_code'}
ORIG_DBL = {'original_interest_rate'}
ORIG_TYPES_TYPED = {
    c: ('VARCHAR' if c in ORIG_TEXT_FORCE
        else 'INTEGER' if c in ORIG_INT
        else 'DOUBLE' if c in ORIG_DBL
        else 'VARCHAR')
    for c in dq.ORIG_COLUMNS
}

PERF_INT = {
    'monthly_reporting_period', 'loan_age', 'remaining_months_to_legal_maturity',
    'defect_settlement_date', 'zero_balance_effective_date',
    'due_date_of_last_paid_installment', 'estimated_loan_to_value',
}
PERF_DBL = {
    'current_upb', 'current_interest_rate', 'current_deferred_upb',
    'mi_recoveries', 'net_sales_proceeds', 'non_mi_recoveries', 'expenses',
    'legal_costs', 'maintenance_and_preservation_costs', 'taxes_and_insurance',
    'miscellaneous_expenses', 'actual_loss_calculation', 'modification_cost',
    'zero_balance_removal_upb', 'delinquent_accrued_interest',
    'current_month_modification_cost', 'interest_bearing_upb',
    'bankruptcy_cramdown_costs',
}
PERF_TYPES_TYPED = {
    c: ('INTEGER' if c in PERF_INT else 'DOUBLE' if c in PERF_DBL else 'VARCHAR')
    for c in dq.PERF_COLUMNS
}

# Bảng nhỏ tra cứu tên cột → kiểu, phục vụ introspection
SPECS = {
    'perf': (dq.PERF_COLUMNS, PERF_TYPES_TYPED),
    'orig': (dq.ORIG_COLUMNS, ORIG_TYPES_TYPED),
}


def connect(db_path: Path = DB_PATH, read_only: bool = False):
    con = duckdb.connect(str(db_path), read_only=read_only)
    if not read_only:
        con.execute(f"SET temp_directory='{TMP_DIR}';")
        con.execute("SET preserve_insertion_order=false;")
        con.execute("SET memory_limit='3GB';")
        # Window/join trên 70M dòng tốn RAM theo số luồng; máy chỉ 15GB.
        con.execute("SET threads=2;")
    return con


def ensure_log(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS _load_log (
            quarter   VARCHAR,
            source    VARCHAR,
            n_rows    BIGINT,
            loaded_at TIMESTAMP,
            seconds   DOUBLE,
            PRIMARY KEY (quarter, source)
        )
    """)


def already_loaded(con, quarter: str, source: str) -> bool:
    r = con.execute(
        "SELECT n_rows FROM _load_log WHERE quarter = ? AND source = ?",
        [quarter, source],
    ).fetchone()
    return r is not None


def columns_ddl(cols, types) -> str:
    return ", ".join(f'"{c}" {types[c]}' for c in cols)


def load_one(con, quarter: str, source: str) -> int:
    """Nạp một (quý, nguồn) vào bảng <source>. Trả về số dòng."""
    cols, types = SPECS[source]
    path = dq.quarter_dir(quarter) / f"{source}_{quarter}.txt"
    if not path.exists():
        raise FileNotFoundError(path)

    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {source} (
            {columns_ddl(cols, types)},
            quarter VARCHAR
        )
    """)

    col_spec = ", ".join(f"'{c}': '{types[c]}'" for c in cols)
    t0 = time.time()
    # Ghi thẳng từ CSV vào bảng, có partition `quarter` để prune về sau.
    con.execute(f"""
        INSERT INTO {source}
        SELECT *, '{quarter}' AS quarter
        FROM read_csv('{path}', delim='|', header=false,
                      columns={{{col_spec}}})
    """)
    elapsed = time.time() - t0
    n = con.execute(
        f"SELECT count(*) FROM {source} WHERE quarter = ?", [quarter]
    ).fetchone()[0]
    con.execute(
        "INSERT INTO _load_log VALUES (?, ?, ?, now(), ?)",
        [quarter, source, n, round(elapsed, 2)],
    )
    print(f"  {quarter} {source:4s}: {n:>12,} dòng  {elapsed:6.1f}s")
    return n


def build(rebuild: bool = False):
    if rebuild and DB_PATH.exists():
        print(f"Xoá DB cũ: {DB_PATH}")
        DB_PATH.unlink()

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    con = connect()
    ensure_log(con)

    # ---- orig trước (nhỏ, 12,8M dòng) rồi mới tới perf ----
    for source in ('orig', 'perf'):
        todo = [q for q in dq.QUARTERS if not already_loaded(con, q, source)]
        if not todo:
            print(f"{source}: đã nạp đủ {len(dq.QUARTERS)} quý, bỏ qua")
            continue
        print(f"\n{source}: còn {len(todo)}/{len(dq.QUARTERS)} quý")
        for q in todo:
            load_one(con, q, source)

    con.execute("CHECKPOINT")
    con.close()


def verify():
    if not DB_PATH.exists():
        print(f"Chưa có {DB_PATH} — chạy build trước.")
        return 1
    con = connect(read_only=True)
    ok = True
    print(f"=== {DB_PATH} ({DB_PATH.stat().st_size / 1e9:.2f} GB) ===")

    print("\n-- Số dòng theo nguồn --")
    for source in ('orig', 'perf'):
        n = con.execute(f"SELECT count(*) FROM {source}").fetchone()[0]
        nq = con.execute(f"SELECT count(DISTINCT quarter) FROM {source}").fetchone()[0]
        print(f"{source:5s}: {n:>12,} dòng, {nq} quý")

    print("\n-- Đối chiếu với output/dq_metrics_by_quarter.csv --")
    import pandas as pd
    m = pd.read_csv(dq.OUT_DATA / 'dq_metrics_by_quarter.csv')
    for source in ('orig', 'perf'):
        expect = int(m[m.source == source].n_rows.sum())
        got = con.execute(f"SELECT count(*) FROM {source}").fetchone()[0]
        flag = 'OK' if expect == got else 'LỆCH'
        if expect != got:
            ok = False
        print(f"{source:5s}: kỳ vọng {expect:>12,} | DB {got:>12,}  [{flag}]")

    print("\n-- Kiểu cột đã áp (mẫu perf) --")
    rows = con.execute("""
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_name = 'perf' ORDER BY ordinal_position LIMIT 8
    """).fetchall()
    for c, t in rows:
        print(f"  {c:38s} {t}")

    print("\n-- Kiểm tra nhanh giá trị đặc biệt --")
    xx = con.execute("""
        SELECT count(*) FROM perf WHERE current_loan_delinquency_status = 'XX'
    """).fetchone()[0]
    print(f"  perf XX: {xx:,} dòng")
    zb = con.execute("""
        SELECT count(DISTINCT zero_balance_code) FROM perf
        WHERE zero_balance_code IS NOT NULL AND trim(zero_balance_code) <> ''
    """).fetchone()[0]
    print(f"  zero_balance_code: {zb} giá trị khác rỗng")

    con.close()
    print("\nKẾT QUẢ:", "OK" if ok else "CÓ LỆCH")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rebuild', action='store_true', help='xoá DB và nạp lại từ đầu')
    ap.add_argument('--verify', action='store_true', help='chỉ kiểm tra, không nạp')
    args = ap.parse_args()

    if args.verify:
        sys.exit(verify())

    t0 = time.time()
    build(rebuild=args.rebuild)
    print(f"\nNạp xong sau {time.time() - t0:.1f}s")
    verify()
    shutil.rmtree(TMP_DIR, ignore_errors=True)


if __name__ == '__main__':
    main()
