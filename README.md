# DS317 — Nhóm 2: dự đoán nguy cơ quá hạn vay mua nhà

Dùng thông tin lúc khởi tạo khoản vay **Purchase** để dự đoán **90+ ngày quá hạn
hoặc REO trong 12 tháng**, tính từ tháng thanh toán đầu tiên.

**Bắt đầu bàn giao tại [docs/handoff.md](docs/handoff.md).**

## Trạng thái

- Đã có nhãn kiểm chứng, dữ liệu nghiên cứu 16.641.482 khoản eligible và 18 features.
- Đã có pilot Logistic Regression/XGBoost: training refit 2012–2016, development 2019.
- Holdout 2024 chưa được đánh giá mô hình.
- EDA/DQ toàn population, so sánh training windows và Raw/Raw+ còn cần làm.
- Classwork đã có clustering/outlier/DQ trên mẫu; chưa chứng minh enrichment cải thiện classifier.

| Model | AP (2019) | ROC-AUC | Capture: top 5% từng quý |
| --- | ---: | ---: | ---: |
| Logistic Regression | 0,055705 | 0,704997 | 15,15% |
| XGBoost | 0,054566 | 0,689814 | 15,82% |

Đọc [kết quả và giới hạn](reports/baseline.md); quarterly khác global ranking.
Baseline hiện tại chưa phải bản tái lập SOTA hoặc kết quả nghiên cứu training windows.

## Một bộ tên dùng chung cho GitHub và local

```text
configs/baseline.yaml           Cấu hình baseline
scripts/ingest_stream.py        ZIP → Parquet
scripts/label/                 Nhãn 12 tháng và kiểm chứng
scripts/gold/                  Feature contract, build/verify dataset
scripts/model/train_baseline.py
scripts/model/verify_baseline.py
scripts/classwork/run_homework.py
docs/                          Hướng dẫn hiện hành
reports/                       Số liệu tổng hợp public

# Chỉ có ở local/Drive, không nằm trong Git:
parquet/orig/                  Origination gốc
parquet/perf/                  Performance tháng
output/labels/                 Nhãn hiện hành
output/label_tables/           Profiling/bằng chứng nhãn
output/research/               Features, target, metadata, membership
output/baseline/run/           Model/preprocessor/predictions gốc
output/baseline/report/        Metrics và kiểm chứng hiện hành
output/classwork/              Bài tập mẫu
output/schema/                 Schema và inventory tổng hợp
references/                    Giáo trình và ghi chú local
```

Tên thư mục mô tả mục đích. Snapshot/rule/config hashes nằm trong manifest.
Thí nghiệm mới dùng run directory riêng dưới output/experiments/.

## Cài và kiểm tra code

Python >=3.12; baseline đã kiểm chứng trên Python 3.14.8.

```bash
python3.14 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
make test
```

Tests dùng synthetic fixtures, không train dữ liệu thật hoặc mở holdout.
Khi đã nhận data/artifacts đúng layout:

```bash
make verify-dataset
make verify-baseline
```

Xem [tái lập pipeline](docs/reproducibility.md) trước khi chạy tác vụ nặng.
Không cần dựng warehouse hoặc giải nén toàn bộ TXT.
Dữ liệu SFLLD lấy từ [nguồn chính thức](https://claritydownload.fmapps.freddiemac.com/CRT/#/sflld)
theo điều kiện nhà cung cấp; GitHub chỉ chứa code và aggregates.

## Tài liệu theo việc cần làm

- [Bàn giao: nhận gì, chạy gì, ai làm gì](docs/handoff.md)
- [Bài toán/data contract](docs/data-contract.md)
- [Quy tắc nhãn](docs/label_rules.md)
- [EDA/DQ và làm giàu tiếp theo](docs/eda-plan.md)
- [Tái lập/kiểm chứng](docs/reproducibility.md)
- [Trạng thái nghiên cứu](docs/project-status.md)
- [Quy tắc public/local](docs/repository-layout.md)
