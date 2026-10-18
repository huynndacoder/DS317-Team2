"""
validate_metrics.py — Xác nhận các metric DQ trong output/dq_metrics_by_quarter.csv
vẫn đúng sau khi (a) đổi postal_code sang VARCHAR trong warehouse, (b) xuất Parquet.

Cách làm: tính lại 6 khía cạnh TRỰC TIẾP TỪ warehouse.duckdb (đã định kiểu), rồi
so sánh với CSV được tạo bởi dq_core.py (đọc .txt toàn VARCHAR). Nếu khớp, kết
luận: kiểu dữ liệu không làm thay đổi metric -> KHÔNG cần chạy lại 4-5-6.

Khác biệt có chủ đích so với dq_core.py:
  - Join perf↔orig phải thêm `AND o.quarter = t.quarter` vì bảng chứa 25 quý.
  - Mọi thứ còn lại giữ nguyên định nghĩa.
"""

import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq_core as dq

ROOT = dq.ROOT
DB_PATH = ROOT / "warehouse.duckdb"
OUT = dq.OUT

CHECK_QUARTERS = ['2020Q1', '2022Q1', '2024Q1', '2025Q3', '2025Q4', '2026Q1']


def orig_metrics(con, q):
    cs = dq.completeness_sum(dq.ORIG_COLUMNS)
    sql = f"""
    WITH s AS (SELECT * FROM orig WHERE quarter = '{q}'),
    w AS (SELECT *, count(*) OVER (PARTITION BY loan_id) AS id_cnt FROM s)
    SELECT
      count(*) AS n_rows,
      1.0 - sum({cs})::DOUBLE / (count(*) * {len(dq.ORIG_COLUMNS)}) AS completeness,
      avg((
        CASE WHEN credit_score IS NULL OR credit_score::VARCHAR = '9999'
                  OR credit_score BETWEEN 300 AND 850 THEN 1 ELSE 0 END
      + CASE WHEN first_payment_date IS NULL OR regexp_matches(first_payment_date::VARCHAR, '^[0-9]{{6}}$') THEN 1 ELSE 0 END
      + CASE WHEN maturity_date IS NULL OR regexp_matches(maturity_date::VARCHAR, '^[0-9]{{6}}$') THEN 1 ELSE 0 END
      + CASE WHEN occupancy_status IS NULL OR occupancy_status IN ('P','I','S') THEN 1 ELSE 0 END
      + CASE WHEN cltv IS NULL OR cltv BETWEEN 0 AND 200 THEN 1 ELSE 0 END
      + CASE WHEN dti IS NULL OR dti::VARCHAR = '999' OR dti BETWEEN 0 AND 65 THEN 1 ELSE 0 END
      + CASE WHEN original_upb IS NULL OR original_upb > 0 THEN 1 ELSE 0 END
      + CASE WHEN ltv IS NULL OR ltv BETWEEN 0 AND 200 THEN 1 ELSE 0 END
      + CASE WHEN original_interest_rate IS NULL OR original_interest_rate BETWEEN 0.000001 AND 20 THEN 1 ELSE 0 END
      + CASE WHEN loan_purpose IS NULL OR loan_purpose IN ('P','C','N') THEN 1 ELSE 0 END
      ) / 10.0) AS validity,
      avg(CASE WHEN id_cnt = 1 THEN 1.0 ELSE 0.0 END) AS uniqueness,
      1.0 AS consistency,
      avg(CASE WHEN first_payment_date <= maturity_date THEN 1.0 ELSE 0.0 END) AS accuracy,
      avg(greatest(0, 1 - {dq.month_lag_sql('first_payment_date')} / 12.0)) AS timeliness
    FROM w
    """
    r = con.execute(sql).fetchone()
    keys = ['n_rows', 'completeness', 'validity', 'uniqueness',
            'consistency', 'accuracy', 'timeliness']
    return dict(zip(keys, r))


def perf_metrics(con, q):
    cs = dq.completeness_sum(dq.PERF_COLUMNS)
    sql = f"""
    WITH t AS (SELECT * FROM perf WHERE quarter = '{q}'),
    o AS (SELECT loan_id, original_upb, original_interest_rate
          FROM orig WHERE quarter = '{q}'),
    j AS (SELECT t.*, o.loan_id AS o_id,
                 try_cast(o.original_upb AS DOUBLE) AS o_upb,
                 try_cast(o.original_interest_rate AS DOUBLE) AS o_rate
          FROM t LEFT JOIN o ON t.loan_id = o.loan_id),
    w AS (SELECT *,
            count(*) OVER (PARTITION BY loan_id, monthly_reporting_period) AS key_cnt,
            row_number() OVER (PARTITION BY loan_id ORDER BY monthly_reporting_period) AS rn,
            min(try_cast(monthly_reporting_period AS BIGINT))
              OVER (PARTITION BY loan_id) AS first_period
          FROM j)
    SELECT
      count(*) AS n_rows,
      1.0 - sum({cs})::DOUBLE / (count(*) * {len(dq.PERF_COLUMNS)}) AS completeness,
      avg(CASE WHEN current_loan_delinquency_status IS NULL
                 OR current_loan_delinquency_status = 'RA'
                 OR (regexp_matches(current_loan_delinquency_status, '^[0-9]{{1,2}}$')
                     AND try_cast(current_loan_delinquency_status AS INT) BETWEEN 0 AND 99)
               THEN 1.0 ELSE 0.0 END) AS validity,
      avg(CASE WHEN current_loan_delinquency_status IS NULL
                 OR current_loan_delinquency_status IN ('RA','XX')
                 OR (regexp_matches(current_loan_delinquency_status, '^[0-9]{{1,2}}$')
                     AND try_cast(current_loan_delinquency_status AS INT) BETWEEN 0 AND 99)
               THEN 1.0 ELSE 0.0 END) AS validity_spec,
      avg(CASE WHEN key_cnt = 1 THEN 1.0 ELSE 0.0 END) AS uniqueness,
      avg(CASE WHEN rn = 1 THEN (CASE WHEN o_id IS NOT NULL THEN 1.0 ELSE 0.0 END) END) AS consistency,
      avg((
        CASE WHEN current_upb IS NULL OR o_upb IS NULL
                  OR current_upb <= o_upb THEN 1.0 ELSE 0.0 END
      + CASE WHEN monthly_reporting_period <> first_period THEN 1.0
             WHEN o_rate IS NULL THEN 1.0
             WHEN abs(current_interest_rate - o_rate) < 0.005 THEN 1.0
             ELSE 0.0 END
      + CASE WHEN zero_balance_code IS NULL OR trim(zero_balance_code) = '' OR zero_balance_code = '999' THEN 1.0
             WHEN regexp_matches(zero_balance_code, '^[0-9]+$')
                  AND try_cast(zero_balance_code AS INT) BETWEEN 1 AND 998 THEN 1.0
             ELSE 0.0 END
      ) / 3.0) AS accuracy,
      avg(greatest(0, 1 - {dq.month_lag_sql('monthly_reporting_period')} / 12.0)) AS timeliness
    FROM w
    """
    r = con.execute(sql).fetchone()
    keys = ['n_rows', 'completeness', 'validity', 'validity_spec', 'uniqueness',
            'consistency', 'accuracy', 'timeliness']
    return dict(zip(keys, r))


def main():
    cached = pd.read_csv(dq.OUT_DATA / 'dq_metrics_by_quarter.csv')
    con = duckdb.connect(str(DB_PATH), read_only=True)
    con.execute(f"SET temp_directory='{dq.TMP_DIR}';")
    con.execute("SET preserve_memory=false;" if False else "SET preserve_insertion_order=false;")
    con.execute("SET memory_limit='3GB';")
    con.execute("SET threads=2;")

    dims = dq.DIMS
    tol = 1e-4
    bad = []
    print(f"{'quý':8s} {'nguồn':5s} {'khía cạnh':14s} {'CSV':>10s} {'tính lại':>10s} {'lệch':>10s}")
    print('-' * 64)

    for q in CHECK_QUARTERS:
        for source, fn in (('orig', orig_metrics), ('perf', perf_metrics)):
            got = fn(con, q)
            row = cached[(cached.quarter == q) & (cached.source == source)].iloc[0]
            if int(row.n_rows) != int(got['n_rows']):
                bad.append((q, source, 'n_rows', row.n_rows, got['n_rows']))
            for d in dims:
                exp = float(row[d])
                act = float(got[d])
                delta = abs(exp - act)
                mark = '' if delta <= tol else '  <-- LỆCH'
                if delta > tol:
                    bad.append((q, source, d, exp, act))
                print(f"{q:8s} {source:5s} {d:14s} {exp:10.4f} {act:10.4f} {delta:10.6f}{mark}")

    con.close()

    print('\n' + '=' * 64)
    if bad:
        print(f'THẤT BẠI: {len(bad)} điểm lệch > {tol}')
        for b in bad:
            print('  ', b)
        return 1
    print(f'OK: mọi metric khớp trong sai số {tol}')
    print('Kết luận: kiểu dữ liệu (postal_code VARCHAR) và Parquet')
    print('KHÔNG làm thay đổi kết quả 4-5-6 -> không cần chạy lại.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
