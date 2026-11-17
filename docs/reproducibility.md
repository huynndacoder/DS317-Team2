# Tái lập và kiểm chứng

## 1. Synthetic tests — không cần dữ liệu

Từ repo root, Python >=3.12; baseline được kiểm chứng với Python3.14.8:

```bash
python3.14 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
make test
```

Label tests dùng DuckDB fixtures; model/package tests dùng synthetic data và
mocked child runners. Các test này không gọi full-data pipeline.

## 2. Dữ liệu local — tác vụ nặng

Tự lấy dữ liệu Freddie Mac từ nguồn chính thức. Không có downloader tự đăng nhập.
Kiểm tra zip members trước; ingest streaming tránh landing TXT đầy đủ:

```bash
./venv/bin/python scripts/ingest_stream.py list --src data
./venv/bin/python scripts/ingest_stream.py ingest --src data
```

Kết quả cần layout `parquet/{orig,perf}/quarter=YYYYQn/data.parquet`.
Sau đó mới build/verify labels và Gold:

```bash
DQ_MEMORY_LIMIT=3GB DQ_THREADS=2 bash scripts/label/run_labels.sh
DQ_MEMORY_LIMIT=3GB DQ_THREADS=2 ./venv/bin/python scripts/gold/build_research_dataset.py --version research_v2
DQ_MEMORY_LIMIT=3GB DQ_THREADS=2 ./venv/bin/python scripts/gold/verify_research_dataset.py --version research_v2
```

Các lệnh trên đọc dữ liệu thật và có thể chạy lâu.
Không dùng `--force` hay rebuild trên thư mục đã freeze mà chưa chủ ý tạo phiên bản mới.
Giữ config/rules của baseline; thí nghiệm mới dùng config và output version riêng.

## 3. Training — không phải verify-only

Chỉ chạy khi đã có Gold và đã chốt protocol:

```bash
./venv/bin/python scripts/model/train_pilot_corrected.py --config configs/pilot_baseline.yaml --version research_v2
```

Trainer tạo run mới có models/preprocessing/predictions/metrics.
Không trỏ output-dir vào original run hoặc package đã hoàn tất.
Giới hạn DuckDB không giới hạn toàn bộ RAM của pandas/model.

## 4. Kiểm saved artifacts

Với run và Gold local tương ứng:

```bash
./venv/bin/python scripts/model/verify_pilot_run.py --run-dir output/experiments/<run-id> --gold-dir output/gold/research_v2 --output-dir output/audits/<new-id>/verification
```

Để tạo package, `generate_handoff_package.py` yêu cầu
`--before-provenance`: một thư mục snapshot **tạo trước khi sửa/chạy** gồm
`input_hashes_before.json`, `source_hashes_before.json`,
`git_status_before.txt` và `dependency_versions.json`.
Input inventory phải là 18 files của saved pilot run theo contract generator.
Không tạo provenance giả bằng cách ghi số đã biết; xem
`generate_handoff_package.generate` và fixture trong `tests_handoff_package.py`.

Generator orchestrates tests + một real verifier, cần output-dir mới rỗng.
Nó không train models. Package không nằm trong Git vì chứa paths và artifacts local.
Với package đã hoàn tất, chỉ cần checker:

```bash
./venv/bin/python scripts/model/check_handoff_package.py --package-dir output/audits/<package-id>
```

Không cần lặp full verifier để kiểm package. Gate kiểm schema/content, baseline bằng
saved evaluation labels, command evidence, source/input hashes và completion marker.

## 5. Notebooks

```bash
./venv/bin/python -m pip install -r requirements-notebooks.txt
```

Notebooks public không có outputs hoặc row-level samples.
EDA cũ dùng population/horizon khám phá riêng; DQ notebook cần TXT layout local cũ.
Xem ghi chú đầu notebook và README. Không chạy toàn performance để thử môi trường.
