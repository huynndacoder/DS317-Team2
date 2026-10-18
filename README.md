# DS317 — Team 2

Đồ án môn học DS317: phân tích chất lượng dữ liệu và khai phá dữ liệu tín dụng
(Freddie Mac Single-Family Loan-Level Dataset).

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `scripts/` | Pipeline Python: trích xuất dữ liệu, dựng warehouse DuckDB, tính 6 khía cạnh chất lượng dữ liệu, xuất Parquet |
| `notebooks/` | Notebook bài tập chất lượng dữ liệu |
| `ThucHanh/` | Notebook thực hành trên lớp |
| `Team2/` | Khảo sát tài liệu, lựa chọn dataset, phân công thành viên |
| `docs/` | Tài liệu môn học (markdown; PDF không đưa vào git) |

## Pipeline

```bash
# 1. Giải nén dữ liệu gốc vào data/historical_data_<YEAR>/
python scripts/extract_historical_data.py
python scripts/verify_extraction.py

# 2. Dựng warehouse DuckDB (silver layer, đã định kiểu)
python scripts/build_warehouse.py

# 3. Tính 6 khía cạnh chất lượng dữ liệu
bash scripts/run_6_dimensions.sh

# 4. Xuất Parquet phân vùng theo quý
python scripts/export_parquet.py
```

## Yêu cầu

Python 3.11+, `duckdb`, `pandas`, `matplotlib`, `openpyxl`.

## Dữ liệu

`data/`, `parquet/`, `output/` và `warehouse.duckdb` **không** được commit
(xem `.gitignore`) — tổng dung lượng ~80 GB. Liên hệ nhóm để lấy dữ liệu gốc.
