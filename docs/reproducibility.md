# Chạy và kiểm chứng

## Synthetic tests

Python >=3.12; baseline dùng Python 3.14.8.

```bash
./venv/bin/python -m pip install -r requirements.txt
make test
```

Tests dùng fixtures, không train dữ liệu thật/đọc holdout.
CLI tương thích duy nhất nằm trong README và tài liệu này.

## Dữ liệu đã bàn giao

Đặt bốn Parquet cùng metadata vào output/research/, baseline run/report vào output/baseline/.
Chạy:

```bash
make verify-dataset
make verify-baseline
```

verify-dataset đối chiếu origination/labels nên cần các nguồn này nếu muốn chạy full check.
Người chỉ dùng model/EDA có thể bắt đầu bằng make test và các counts/schema trong manifest.
verify-baseline cần target/membership và saved run; không train hoặc rebuild.
Gói report dùng đường dẫn tương đối repo, giữ command evidence lịch sử trong provenance.

## Chỉ khi cần dựng dữ liệu mới — tác vụ nặng

```bash
./venv/bin/python scripts/ingest_stream.py list --src data
./venv/bin/python scripts/ingest_stream.py ingest --src data
DQ_MEMORY_LIMIT=3GB DQ_THREADS=2 bash scripts/label/run_labels.sh
DQ_MEMORY_LIMIT=3GB DQ_THREADS=2 ./venv/bin/python scripts/gold/build_research_dataset.py --output-dir output/research
```

Builder từ chối thư mục có dữ liệu. Với snapshot mới, chọn một thư mục mới; không ghi đè
dataset đã bàn giao. Không cần rebuild vì clone repo hoặc đổi tên thư mục.
Nhãn và Parquet gốc đã có không cần chạy lại cho mỗi model.

## Training một run mới

Sau khi có Gold và protocol:

```bash
./venv/bin/python scripts/model/train_baseline.py --config configs/baseline.yaml --dataset-dir output/research
```

Trainer tự tạo output/experiments/baseline_<timestamp>, từ chối output nonempty.
Đây là trainer baseline pilot 2019; runner nhiều windows chưa được triển khai.
Median/scaler/vocabulary học riêng từ training mỗi stage. Holdout 2024 để riêng.
DuckDB memory_limit không giới hạn RAM pandas/model; mỗi lúc chỉ một heavy process.

## Kiểm saved run và tạo report

```bash
./venv/bin/python scripts/model/verify_baseline.py --run-dir output/baseline/run --gold-dir output/research --output-dir output/checks/baseline
./venv/bin/python scripts/model/check_handoff_package.py --package-dir output/baseline/report
```

Generator generate_handoff_package.py cần --run-dir, --gold-dir, --output-dir và
--before-provenance. Snapshot before-provenance tạo TRƯỚC thay đổi, gồm
input_hashes_before.json, source_hashes_before.json, git_status_before.txt, dependency_versions.json.
Generator chạy tests rồi verifier, không fit model; output phải mới/rỗng.
Report hiện hành đã có; không chạy generator chỉ để đọc kết quả.

## Chạy lại classwork trên mẫu

Cần output/research, output/baseline/report và run, parquet/orig, cùng output/schema/orig_schema.csv.
Nếu chưa có schema, nhận gói inventory hoặc chạy export_orig_schema.py trên origination.
Inventory trong evidence phản ánh các file có trên máy; performance không dùng để fit model mẫu.

```bash
./venv/bin/python -m pip install -r requirements-classwork.txt
./venv/bin/python scripts/classwork/run_homework.py --out-dir output/classwork
```

Script từ chối output đã có; dùng một thư mục experiment mới khi muốn chạy lại.
Không train classifier mới và không đánh giá holdout. Xem scope/limitations trong evidence.json.
