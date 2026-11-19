# Baseline pilot — kết quả tổng hợp

Nguồn của bảng public: package pilot đã được review ngày17/11/2026.
Chỉ xuất số liệu tổng hợp; không có loan IDs hoặc predictions cá nhân.
[CSV](baseline.csv) chứa bốn model/stage rows.

Population: Purchase-only eligible; development cohorts2019 gồm933.708 khoản,
24.100 positives. Nhãn: serious delinquency90+ hoặc REO trong12 tháng đầu từ
first-payment month. Xem [data contract](../docs/data-contract.md).

## Ngân sách 5% theo từng cohort-quý

| Model | Selected | TP | Capture | Precision | Lift |
|---|---:|---:|---:|---:|---:|
| Logistic Regression | 46.688 | 3.650 | 0,151452 | 0,078179 | 3,028877 |
| XGBoost | 46.688 | 3.812 | 0,158174 | 0,081648 | 3,163309 |

## Discrimination và probability losses

| Model | AP | ROC-AUC | Brier | Log-loss |
|---|---:|---:|---:|---:|
| Logistic Regression | 0,055705 | 0,704997 | 0,025671 | 0,170606 |
| XGBoost | 0,054566 | 0,689814 | 0,025638 | 0,169971 |

Constant predictor stage B dùng training prevalence0,001117408624,
đánh giá trên cùng development labels:
Brier0,025754632855; log-loss0,176520366640.
Không thay baseline loss bằng entropy(training prevalence).

LR tốt hơn ở AP/AUC; XGB tốt hơn ở quarterly capture và losses trong pilot này.
Không có significance claim hoặc khẳng định model thắng mọi tiêu chí.
Global-ranking top5% có capture khác ngân sách theo quý; xem cột có suffix
`_global` trong CSV, không ghép chúng với quarterly precision/lift.

## Giới hạn

- Một development year, chưa so training windows.
- Phần lớn first events của cohort2019 ghi nhận trong2020; không diễn giải nhân quả.
- Historical LR A12/B13 iterations dưới max_iter1000; status unknown vì capture
  warning lịch sử chưa đủ bằng chứng, không phải iteration_limit.
- Snapshot/backfill và reporting-lag assumptions giới hạn point-in-time claims.
- Holdout2024 chưa được đánh giá.
