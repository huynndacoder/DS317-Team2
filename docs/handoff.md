# Bàn giao cho teammate

## 1. Mục tiêu và điểm bắt đầu

Dự đoán serious delinquency (90+ ngày hoặc REO) trong 12 tháng từ first-payment
month, dùng thông tin origination. Population nghiên cứu là Purchase và eligible.
Câu hỏi chính tiếp theo: lịch sử training 3/5/10 năm hoặc expanding ảnh hưởng thế nào?

Clone GitHub main mới, cài requirements và chạy make test. Nhận data riêng từ Drive,
đặt theo layout dưới đây. GitHub không chứa loan-level data/models/predictions.
Không copy cả workspace của người khác hoặc git add . khi có dữ liệu local.

## 2. Nhận gói nào?

| Task | Gói | Dung lượng xấp xỉ |
| --- | --- | ---: |
| EDA/model | output/research/ | 319 MiB |
| Demo/đối chiếu baseline | output/baseline/ (run + report) | 40 MiB |
| DQ/kiểm tra nguồn | parquet/orig/ + output/labels/ + output/label_tables/ + output/schema/ | 724 MiB |
| Classwork clustering/outliers | output/classwork/ | 3 MiB |

Performance tháng chỉ cần khi task cần audit nhãn/lịch sử tháng cụ thể.
Nguồn đầy đủ có 110 cohorts, 49.348.308 origination loans và 2.892.202.475 performance rows.

## 3. Bốn file dữ liệu nghiên cứu

| File trong output/research/ | Vai trò |
| --- | --- |
| features.parquet | 16.641.482 dòng; 18 predictors + loan_id + number_of_borrowers_raw |
| target.parquet | loan_id + label_12m |
| split.parquet | loan_id + cohort + mốc thời gian; split là exclusive metadata lịch sử |
| membership.parquet | 7.012.771 cặp loan_id–role cho pilot; role có thể overlap |

Chỉ whitelist 18 predictors vào X. Hai cột loan_id/raw trace không vào model.
Chọn role từ membership trước rồi join 1:1 theo loan_id.
Membership pilot không phủ toàn bộ Gold; cửa sổ mới cần membership mới từ metadata/readiness.
Không loại mọi dòng split=embargoed khi làm nghiên cứu cửa sổ mới.

| Role pilot | Cohorts | Số khoản |
| --- | --- | ---: |
| train_tune | 2009–2013 | 1.863.476 |
| validation | 2016 | 710.554 |
| train_refit | 2012–2016 | 2.688.363 |
| development_test | 2019 | 933.708 |
| holdout | 2024 | Không chấm trong pilot |

Readiness: label_window_end + lag 3 tháng <= ngày fit.
Counts chính trong split_manifest.json dùng role membership; exclusive_split_counts được ghi riêng.
Config chỉ mô tả baseline pilot: một số mốc thời gian và XGB parameters còn trong trainer.
So nhiều cửa sổ cần runner riêng, không chỉ thay YAML.

## 4. Model và kết quả chuẩn

- output/baseline/run/: giữ 18 input artifacts gốc để kiểm chứng hash.
- output/baseline/report/REPORT.md: báo cáo hiện hành.
- output/baseline/report/metrics/: metrics, constant baseline, convergence.
- output/baseline/report/verification/: independent recount/inference evidence.
- output/baseline/report/COMPLETE.json: completion marker, kiểm bằng make verify-baseline.

Các metric/report bên trong run là input lịch sử; dùng report/ cho dashboard và báo cáo cuối.
Model/preprocessor/predictions giữ nguyên bytes khi chuẩn hóa tên; không có supervised retraining.
Historical LR convergence là unknown vì thiếu bằng chứng warning capture lịch sử.
Không suy ra iteration_limit từ 12/13 iterations dưới max_iter 1000.

## 5. Phân công và đầu ra

| Người | Công việc | Nộp |
| --- | --- | --- |
| Huy | EDA population/nhãn/features/drift theo cohort; phối hợp clusters/series | docs/eda_report.md + CSV/figures/manifest |
| Nhân | DQ contract theo 6 khía cạnh và can thiệp có căn cứ | Rule table, grain/cohort metrics, before/after cùng scope |
| Hiển | Runner windows và phối hợp Raw/Raw+ | Config/membership mới, models/predictions/metrics, resources |
| Ys | Paper và giả thuyết cải tiến | Paper comparison, method spec, ablation |
| Hiền | Demo và tổng hợp kết quả | App dùng saved preprocessing/model và report metrics |

Sy chốt protocol và review tích hợp. Primary metric đề xuất AP; nghiệp vụ là
capture@5% với ngân sách riêng từng quý. Giữ holdout 2024 ngoài model selection.

Giữ configs/baseline.yaml và code baseline đã kiểm chứng; thí nghiệm mới dùng config/runner
riêng. Package checker kiểm cả source hashes, nên sửa các file nguồn baseline sẽ làm
kiểm chứng lịch sử thất bại dù model files vẫn còn nguyên.

Mỗi task ghi rõ dataset/scope, IDs, ngày fit, yếu tố thay đổi, lệnh tái lập,
outputs và người review. Thí nghiệm mới không ghi đè output/research hoặc output/baseline.

## 6. Classwork

Đã có mẫu 8.000 train_refit + 4.000 development 2019: DQ, KMeans/GMM/DBSCAN,
outlier và PSI. Đây là kết quả mẫu, chưa phải full-data EDA hay bằng chứng Raw+ tốt hơn.
Accuracy/timeliness không có reference/timestamps ghi N/A.
Default outcome không phải nhãn nhóm thật; purity cao có thể do mất cân bằng.
Script: scripts/classwork/run_homework.py; dependencies: requirements-classwork.txt.
Để tái lập classwork, cần thêm research, baseline, origination và schema; performance
không dùng cho model mẫu, chỉ xuất hiện trong inventory khi có file trên máy.

Đọc tiếp [kế hoạch EDA/làm giàu](eda-plan.md) và [lệnh tái lập](reproducibility.md).
