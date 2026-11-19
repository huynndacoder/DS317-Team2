# DS317 — Nhóm 2: nguy cơ quá hạn khoản vay mua nhà

Dùng thông tin lúc khởi tạo khoản vay **Purchase** trong Freddie Mac Single-Family
Loan-Level Dataset để dự đoán **90+ ngày quá hạn hoặc REO trong 12 tháng đầu**,
tính từ tháng thanh toán đầu tiên.

Câu hỏi nghiên cứu tiếp theo: ảnh hưởng của cửa sổ dữ liệu huấn luyện
(3/5/10 năm hoặc expanding) đến kết quả dự đoán ngoài thời gian.

## Trạng thái

- Đã xây và kiểm chứng nhãn, Gold và pilot Logistic Regression / XGBoost.
- Gold nghiên cứu: **16.641.482 khoản eligible**, 18 baseline features.
- Development test: cohort 2019; **holdout 2024 chưa được đánh giá**.
- Chưa có kết quả nghiên cứu so sánh training windows hoặc tuyên bố đạt SOTA.
- Source nhãn/Gold/model được giữ nguyên từ baseline đã audit.
- Đây là repo source và kết quả tổng hợp; dữ liệu khoản vay, weights và predictions
  không được phân phối trong Git.

| Model | AP (2019) | ROC-AUC (2019) | Capture: top 5% từng quý |
|---|---:|---:|---:|
| Logistic Regression | 0,055705 | 0,704997 | 15,15% |
| XGBoost | 0,054566 | 0,689814 | 15,82% |

Đọc [phương pháp và giới hạn](reports/pilot-baseline.md) trước khi diễn giải kết quả.
Global-ranking khác với ngân sách 5% theo quý.

## Bắt đầu mà không cần dữ liệu Freddie Mac

Môi trường baseline được kiểm chứng trên Python **3.14.8**; dependencies hiện tại
yêu cầu Python **>=3.12**.

```bash
python3.14 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
make test
```

`make test` chỉ chạy label logic và model/package tests bằng fixtures synthetic.
Không tải dữ liệu, không train trên dữ liệu thật và không mở holdout.
Có thể dùng interpreter khác bằng `make test PYTHON=python`.

## Cấu trúc

```text
configs/                 Cấu hình pilot
scripts/ingest_stream.py  Zip → Parquet, không ghi toàn bộ TXT ra đĩa
scripts/label/           Profiling, nhãn 12 tháng và kiểm chứng
scripts/gold/            Feature contract, Purchase Gold và membership
scripts/model/           Training pilot, evaluator, verifier và package checker
docs/                    Data contract, tái lập và trạng thái nghiên cứu
reports/                 Chỉ kết quả tổng hợp, không có loan-level rows
```

## Tài liệu

- [Data contract](docs/data-contract.md)
- [Quy tắc nhãn chi tiết](docs/label_rules.md)
- [Chạy pipeline và kiểm chứng](docs/reproducibility.md)
- [Trạng thái và công việc tiếp theo](docs/project-status.md)
- [Chính sách repo public/local](docs/repository-layout.md)

## Dữ liệu và tài nguyên local

Đăng ký/tải dữ liệu trực tiếp tại
[Freddie Mac SFLLD](https://claritydownload.fmapps.freddiemac.com/CRT/#/sflld)
theo điều kiện của nhà cung cấp. Không có tài khoản, token hoặc dữ liệu thô trong repo.

Pipeline thật cần `parquet/` và `output/` local. Xem tài liệu tái lập trước khi chạy:
build nhãn/Gold và training là tác vụ nặng, khác với synthetic tests.
Trên máy dùng chung chỉ chạy một heavy training process tại một thời điểm.

## EDA và chất lượng dữ liệu

Sáu chiều CLDL: **Completeness, Validity, Uniqueness, Consistency, Accuracy,
Timeliness**. Các chỉ số delinquency/prepayment/UPB là chỉ số tín dụng.

Code EDA/DQ legacy và các notebook/SQL khám phá cũ đã được xóa.
Repo hiện chưa có entrypoint EDA/DQ thay thế được nghiệm thu cho Purchase Gold.
Triển khai mới trên Gold một dòng/khoản vay, dùng nhãn `label_12m` đã kiểm chứng,
chọn role qua `membership.parquet` và giữ holdout 2024 ngoài việc chọn phương pháp.
Xem [công việc tiếp theo](docs/project-status.md).

Pipeline được hỗ trợ: streaming ingest → labels → Purchase Gold →
`train_pilot_corrected.py` → verifier/package checker. Không cần dựng warehouse
hoặc giải nén toàn bộ TXT để chạy pipeline này.
