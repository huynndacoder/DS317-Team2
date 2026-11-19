# Kiểm chứng chuẩn hóa layout — 20/11/2026

Layout hiện hành: output/research, output/baseline/run, output/baseline/report,
output/classwork, output/labels, output/label_tables và output/schema.

Đã kiểm tra trước khi xóa các bản thay thế:

- Dataset independent verifier: 44 passed, 0 failed.
- Label fixtures: 55 passed, 0 failed; không đổi logic nhãn.
- Model/package fixtures: 140 passed, 0 failed.
- Real saved-run verifier: 51 checks pass, đủ 50 required checks, không missing.
- Independent package checker: 218/218 tại repo hiện hành.
- Relocation check: cùng 218 checks pass sau khi đặt package, data và source tại một repo root khác.
- SHA256 bốn Parquet nghiên cứu và 18 original run artifacts giữ nguyên.
- Corrected pooled metrics giữ nguyên bytes; không thay kết quả baseline.
- Classwork trên mẫu tái lập metrics/profile/PSI/outlier; bỏ so runtime do phụ thuộc máy.

Đã xóa 508 file kết quả cũ/trung gian và warehouse DuckDB dẫn xuất, giải phóng khoảng
13,46 GiB. Raw ZIP, 110 origination/performance partitions và nhãn hiện hành được giữ.
Các thay đổi local trước đồng bộ được lưu bằng nhánh Git local, không publish.

Không supervised retraining, không rebuild labels/Parquet nghiên cứu và không đánh giá holdout.
Điều chỉnh metadata: validation cohort đúng 2016; role counts tách khỏi exclusive split counts.
Command evidence ghi lại execution root gốc; checker ánh xạ đường dẫn khi kiểm ở repo root mới,
không sửa lịch sử lệnh để giả rằng chúng đã chạy ở máy khác.

Các kiểm tra này nghiệm thu kỹ thuật việc chuyển layout; nghiên cứu windows/enrichment vẫn cần làm.
