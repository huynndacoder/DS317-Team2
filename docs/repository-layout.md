# Phạm vi public và local

## Trong GitHub

Source ingest/label/research/model/classwork, config, synthetic tests/CI, hướng dẫn hiện hành
và aggregates không có loan IDs. Chỉ stage danh sách file đã kiểm tra; không git add . ở workspace data.

## Chỉ local/Drive

data/, parquet/, output/, model/pickles, loan-level labels/predictions/sample IDs,
references/ (giáo trình, papers, ghi chú), caches, environment và .slim/ (agent/recovery state).
Không upload dữ liệu hoặc checkpoint lên GitHub.

## Tên chuẩn

- output/research/: một bộ Purchase eligible hiện hành.
- output/baseline/run/: original accepted model/preprocessor/predictions, giữ nguyên hash.
- output/baseline/report/: report/metrics/verification đã tạo lại cho layout hiện hành.
- output/classwork/: một bộ kết quả mẫu hiện hành.
- output/labels/ và output/label_tables/: nhãn và bằng chứng nguồn.
- output/schema/: schema/inventory tổng hợp.
- output/experiments/: chỉ cho các thí nghiệm mới có run ID; không dùng để chọn baseline bằng timestamp.

Không giữ các bản dataset/run lỗi và report cũ dưới tên thư mục phiên bản.
Lịch sử code nằm trong Git; mã snapshot/rules/hash giữ trong manifest.
Raw ZIP và Parquet gốc được giữ để tái lập. Không cần warehouse DuckDB cũ.
