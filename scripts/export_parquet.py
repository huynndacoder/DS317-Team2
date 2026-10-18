"""
export_parquet.py — Xuất `warehouse.duckdb` ra Parquet (zstd), phân vùng theo quý.

Vì sao Parquet?
---------------
- Nhỏ hơn nhiều so với text gốc: đo trên 2020Q4 (70,4M dòng) = 0.63 GB
  (8,9 B/dòng) so với 8,0 GB text -> ~12,5x. Ước tính cả bộ ~4,7 GB.
- Cột: chỉ đọc cột cần -> `XX` count trên 533M dòng chỉ chạm 1/35 dữ liệu.
- Di động: DuckDB / pandas / Spark / BigQuery / Colab / Kaggle đều đọc trực tiếp,
  kể cả qua HTTP. `.duckdb` thì không (embedded, phải có file local).

Bố cục xuất ra (Hive partitioning -> prune theo quý):
    parquet/perf/quarter=2020Q1/data.parquet
    parquet/orig/quarter=2020Q1/data.parquet

Mỗi quý xuất riêng (KHÔNG một COPY khổng lồ) để giữ RAM thấp.

Cách dùng
---------
    venv/bin/python scripts/export_parquet.py              # xuất phần còn thiếu
    venv/bin/python scripts/export_parquet.py --verify     # chỉ kiểm tra
    venv/bin/python scripts/export_parquet.py --rebuild    # xuất lại từ đầu
    venv/bin/python scripts/export_parquet.py --only perf  # chỉ một nguồn
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
PQ_DIR = ROOT / "parquet"
TMP_DIR = dq.TMP_DIR

SOURCES = ('orig', 'perf')


def connect(read_only: bool = True):
    con = duckdb.connect(str(DB_PATH), read_only=read_only)
    con.execute(f"SET temp_directory='{TMP_DIR}';")
    con.execute("SET preserve_insertion_order=false;")
    con.execute("SET memory_limit='3GB';")
    con.execute("SET threads=2;")
    return con


def pq_path(source: str, quarter: str) -> Path:
    return PQ_DIR / source / f"quarter={quarter}" / "data.parquet"


def export_one(con, source: str, quarter: str) -> tuple[int, float]:
    """Xuất một (nguồn, quý) ra Parquet. Trả về (số dòng, dung lượng MB)."""
    out = pq_path(source, quarter)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out.with_suffix('.parquet.tmp')

    t0 = time.time()
    con.execute(f"""
        COPY (SELECT * FROM {source} WHERE quarter = '{quarter}')
        TO '{tmp_out}'
        (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 122880)
    """)
    elapsed = time.time() - t0
    tmp_out.replace(out)

    n = con.execute(
        f"SELECT count(*) FROM read_parquet('{out}')"
    ).fetchone()[0]
    mb = out.stat().st_size / 1e6
    print(f"  {quarter} {source:4s}: {n:>12,} dòng  {mb:8.1f} MB  {elapsed:6.1f}s")
    return n, mb


def export(rebuild: bool = False, only: str | None = None):
    if not DB_PATH.exists():
        print(f"Chưa có {DB_PATH} — chạy scripts/build_warehouse.py trước.")
        return 1

    sources = (only,) if only else SOURCES
    if rebuild:
        # Chỉ xoá đúng nguồn được chọn — tránh xoá nhầm nguồn còn lại.
        for s in sources:
            d = PQ_DIR / s
            if d.exists():
                shutil.rmtree(d)

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    con = connect()

    # Số dòng kỳ vọng lấy từ DB (nguồn chuẩn)
    print(f"\n=== Xuất {DB_PATH.name} -> {PQ_DIR} ===")
    for source in sources:
        todo = [q for q in dq.QUARTERS if not pq_path(source, q).exists()]
        if not todo:
            print(f"{source}: đã có đủ {len(dq.QUARTERS)} quý, bỏ qua")
            continue
        print(f"\n{source}: còn {len(todo)}/{len(dq.QUARTERS)} quý")
        for q in todo:
            export_one(con, source, q)

    con.close()
    return 0


def verify(only: str | None = None) -> int:
    if not PQ_DIR.exists():
        print(f"Chưa có {PQ_DIR} — chạy export trước.")
        return 1

    sources = (only,) if only else SOURCES
    con = connect()
    ok = True

    total_rows = 0
    total_bytes = 0

    print(f"\n=== Kiểm tra {PQ_DIR} ===")
    for source in sources:
        db_n = con.execute(f"SELECT count(*) FROM {source}").fetchone()[0]
        files = sorted((PQ_DIR / source).glob('quarter=*/data.parquet'))
        pq_n = 0
        size = 0
        for f in files:
            pq_n += con.execute(
                f"SELECT count(*) FROM read_parquet('{f}')"
            ).fetchone()[0]
            size += f.stat().st_size
        total_rows += pq_n
        total_bytes += size
        flag = 'OK' if db_n == pq_n else 'LỆCH'
        if db_n != pq_n:
            ok = False
        print(f"{source:5s}: DB {db_n:>12,} | Parquet {pq_n:>12,} | "
              f"{len(files)} file, {size / 1e9:.2f} GB  [{flag}]")

    # Truy vấn thử bằng glob — đúng cách đồng đội sẽ dùng
    print("\n-- Truy vấn thử qua glob (perf) --")
    t0 = time.time()
    r = con.execute(f"""
        SELECT count(*) FILTER (WHERE current_loan_delinquency_status = 'XX') AS n_xx,
               count(*) AS n
        FROM read_parquet('{PQ_DIR}/perf/quarter=*/data.parquet')
    """).fetchone()
    print(f"  XX: {r[0]:,} / {r[1]:,} dòng  ({time.time() - t0:.1f}s)")

    # Prune: chỉ một quý
    print("\n-- Truy vấn thử có partition pruning (2026Q1) --")
    t0 = time.time()
    r = con.execute(f"""
        SELECT count(*) FROM read_parquet('{PQ_DIR}/perf/quarter=2026Q1/data.parquet')
    """).fetchone()[0]
    print(f"  {r:,} dòng  ({time.time() - t0:.2f}s)")

    con.close()
    print(f"\nTổng: {total_rows:,} dòng, {total_bytes / 1e9:.2f} GB")
    print("KẾT QUẢ:", "OK" if ok else "CÓ LỆCH")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rebuild', action='store_true', help='xoá thư mục parquet và xuất lại')
    ap.add_argument('--verify', action='store_true', help='chỉ kiểm tra, không xuất')
    ap.add_argument('--only', choices=SOURCES, help='chỉ xuất/kiểm tra một nguồn')
    args = ap.parse_args()

    if args.verify:
        sys.exit(verify(only=args.only))

    t0 = time.time()
    rc = export(rebuild=args.rebuild, only=args.only)
    if rc:
        sys.exit(rc)
    print(f"\nXuất xong sau {time.time() - t0:.1f}s")
    rc = verify(only=args.only)
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    sys.exit(rc)


if __name__ == '__main__':
    main()
