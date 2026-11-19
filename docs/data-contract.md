# Data contract

## Population và hạt dữ liệu

- Nguồn: Freddie Mac SFLLD, lịch sử origination cohorts 1999Q1–2026Q2.
- Nhãn được xây từ performance monthly; Gold phục vụ ML có một dòng/khoản vay.
- Nghiên cứu chỉ dùng `loan_purpose=P` và nhãn eligible.
- Không ép unknown label thành negative.
- Kết quả toàn dữ liệu và Purchase-only có population khác nhau.

## Nhãn

`label_12m=1` khi khoản vay đạt delinquency status 03+ hoặc REO trong
12 tháng lịch bắt đầu tại original first-payment month.
`0` là negative đủ điều kiện; `NULL` là unknown.

Nguồn thực thi: `scripts/label/label_rules.py`.
Giải thích termination/maturity/coverage/exclusions:
[label_rules.md](label_rules.md).
Cohort maturity là giả định nghiên cứu, không phải quy tắc Freddie Mac.

## Features

18 features theo `configs/baseline.yaml` và
`scripts/gold/gold_spec.py`; gồm 9 numeric và 9 categorical.
`number_of_borrowers` là categorical one/multiple/NULL.
Identifier, label, first-event month và performance/audit columns không vào X.

Giải mã sentinel theo quy tắc cố định.
Imputation, scaling và vocabulary phải fit trên training của từng stage/window.
LR có scaling; XGBoost không scale numeric.

## Chia tập pilot

Nguồn ID: `membership.parquet` theo (loan_id, role).
Các roles có thể overlap hợp lệ; exclusive-role counts cũ trong split metadata
không phải nguồn đúng để chọn train_refit.

| Role | Cohorts | Rows |
|---|---|---:|
| train_tune | 2009–2013 | 1.863.476 |
| validation | 2016 | 710.554 |
| train_refit | 2012–2016 | 2.688.363 |
| development_test | 2019 | 933.708 |
| holdout | 2024 | Không đánh giá trong pilot |

Còn điều kiện per-loan readiness: label-window end + lag <= decision date.
Lag 3 tháng là giả định về khả năng biết nhãn; lịch sử không phải point-in-time
backtest hoàn hảo do nguồn snapshot/backfill.

## Metrics

AP khác trapezoidal PR-AUC.
Ngân sách nghiệp vụ: k=ceil(0.05*N) mỗi cohort-quý,
sort score descending rồi loan_id ascending.
Báo riêng quarterly-capacity, macro-quarter và global-ranking.
Constant predictor dùng training prevalence nhưng tính loss trên evaluation labels.
