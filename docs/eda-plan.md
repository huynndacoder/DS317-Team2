# EDA/DQ và làm giàu dữ liệu

Code EDA/DQ legacy đã xóa. Triển khai mới theo contract hiện hành; dùng nhãn có sẵn.
Classwork mẫu đã có ở output/classwork/, chưa thay thế EDA toàn population.

## P0 — Quy tắc trước khi viết biểu đồ

- Population/role khai báo một chỗ; mọi query dùng cùng view.
- Dùng label_12m và eligibility hiện hành; không tự xây nhãn theo loan_age.
- DTI 0 và MI 0 hợp lệ; sentinel/domain theo scripts/gold/gold_spec.py.
- LTV/CLTV đổi miền từ 2018Q2; borrowers dùng one/multiple/NULL.
- ID, raw trace và ngày/period không tự coi là biến số/model predictors.
- Đếm tổng duplicates riêng với LIMIT dùng lấy ví dụ.
- IQR/outlier là cờ chẩn đoán; ngưỡng xử lý học từ training, có căn cứ trước khi xóa.
- Sampling bằng seed/hash ID độc lập nhãn; cache gắn snapshot/scope/rules.
- Aggregate bằng SQL, đưa summaries/sample vào pandas. EDA chính không scan toàn performance.

## E0 — Population và schema

Huy xuất flow: all origination → Purchase → eligible → development/role.
Nêu n/n_pos, unknown/exclusions ở scope được phép. Schema/ID uniqueness và join cardinality
phải đúng. Không cộng lại dòng TOTAL trong cohort summary.
Manifest: nguồn, filters, cohorts/role, ID counts, seed, rules, tài nguyên.

## E1 — Nhãn theo thời gian

Vẽ n, n_pos, prevalence theo cohort/role; unknown không thành negative.
Training prevalence khoảng 0,1%; development 2019 là 24.100/933.708 = 2,5811%.
Kiểm tra mẫu số, window, maturity, thành phần và event timing trước giả thuyết kinh tế.
Không suy luận nhân quả chỉ từ đồ thị. Holdout 2024 không dùng để chọn phương pháp.

## E2 — Features và DQ

18 predictors: numeric summaries/quantiles; categorical shares; physical NULL,
semantic missing, invalid, cardinality theo cohort/role.
Feature–target bins dùng training/validation lịch sử; ghi n/n_pos, missing và nhóm ít mẫu.
Nhân lập rule ở mức hạt: Completeness, Validity, Uniqueness, Consistency, Accuracy,
Timeliness; mỗi rule có nguồn, unit, tử/mẫu số, scope và limitation.
Accuracy/timeliness thiếu reference/timestamps ghi proxy hoặc N/A.
Chọn can thiệp theo bằng chứng; học imputation từ training; giữ evaluation IDs trước/sau.

## E3 — Drift

Phân phối/missing/category share theo origination cohort; chú thích đổi quy ước.
Bin/PSI reference học từ training. Phân biệt feature drift, label prevalence shift,
data errors và thay đổi thành phần danh mục. PSI không chứng minh nguyên nhân.

## E4 — Nhóm/ngoại lai (Chương 8)

Dùng classwork 8.000 reference + 4.000 monitor làm điểm xuất phát.
Chọn thuật toán theo thời gian/chi phí, loại mô hình, ý tưởng, ưu/nhược.
Fit imputer/scaler/cluster/outlier detector trên training, transform các tập sau.
Báo internal metrics, noise coverage, hồ sơ cụm, ổn định seed/cohort, PCA và ý nghĩa nghiệp vụ.
Default không phải ground-truth cluster; outcome theo cụm chỉ phân tích hậu nghiệm.
DBSCAN không có predict chuẩn, cần định nghĩa assignment nếu dùng làm feature.
Candidate: one-hot cluster ID, khoảng cách tâm, anomaly score. Không xóa anomaly mặc định.

## E5 — Chuỗi thời gian/hồi quy (Chương 10)

Candidate: mean original_interest_rate của Purchase origination theo quý, kèm n/n_valid/missing.
Dùng origination trước lọc eligible để tránh selection dựa khả năng biết nhãn tương lai.
Chốt target liên tục, grain, horizon, gaps/trend/seasonality và ngày thông tin có thể biết.
Chương 10 tr.64 yêu cầu baseline + ít nhất hai model và backtesting:
đề xuất naive, trend/lag regression, ETS sau khi EDA xác nhận phù hợp.
Báo MAE, WAPE/MASE, Bias và residual diagnostics; metric có mẫu số hợp lệ.

Availability aggregate khác label-readiness +3 tháng. Nếu giả định aggregate chậm ba tháng,
tại 2019-01 chỉ có đến 2018Q3: dự báo 2019Q1 là h=2 quý.
Candidate forecast_rate/rate_gap phải được sinh walk-forward chỉ từ quá khứ cho cả training.
Không gắn fitted values từ toàn 1999–2026 hoặc actual mean của quý đang dự đoán.
Ghi origin/latest-input/target-period/horizon; giữ ID khi cold-start, thêm missing flag.

## E6 — Raw so với Raw+

Raw là 18 predictors sau chuẩn hóa cố định. Raw+ thêm cluster/outlier/forecast features.
Lượt đầu giữ training 2012–2016, development 2019, model/tuning budget và evaluation IDs.
Nếu training sample thì cả hai nhánh dùng cùng sample, không so mẫu 8.000 với full 2,69M.
Chọn phương pháp trên validation lịch sử; test chỉ chấm sau khi khóa.
So AP, quarterly capture@5%, AUC/losses và chi phí; optional ablations Raw+C, Raw+R.
Forecast tốt hơn naive hoặc silhouette cao chưa chứng minh classifier tốt hơn.
Training-window study và enrichment là hai yếu tố riêng; không đổi cả hai rồi quy kết nguyên nhân.

## Gói nộp

docs/eda_report.md; output/eda/<run_id>/ gồm scope_manifest.json, population_flow.csv,
label_by_cohort_role.csv, feature_profile.csv, missing_by_cohort.csv, drift_by_cohort.csv,
cluster_profiles.csv, regression_series.csv khi có, và figures.
Mỗi hình có scope/thời gian/mẫu số/sampling/nhận xét. Code tái lập có một entrypoint chính.
