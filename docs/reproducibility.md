# Cách chạy — chọn đúng việc mình cần

Nhận gói và đặt đúng thư mục theo [handoff.md](handoff.md). Không cần chạy ingestion, tạo nhãn hoặc train lại để đọc kết quả.

## 1. Chuẩn bị môi trường một lần

Dùng Python >=3.12; baseline đã lưu được tạo bằng Python 3.14.8. Với bundle pickle, ưu tiên môi trường khớp dependency versions trong gói report.

Ví dụ nếu máy có Python 3.14:

```bash
python3.14 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
make test
```

`make test` chạy kiểm tra logic trên dữ liệu giả lập, không train lại dữ liệu thật và không đánh giá holdout. Nếu lệnh thất bại, gửi log lỗi cùng phiên bản Python cho Sy; không sửa dữ liệu để làm test pass.

## 2. Muốn đọc hoặc kiểm tra baseline đã nhận

Đọc `output/baseline/report/REPORT.md` trước. Khi đã có gói report, run và research ở đúng vị trí, chạy:

```bash
make verify-baseline
```

Lệnh kiểm gói hiện có và bằng chứng kiểm chứng, không train lại model. Giữ source baseline/config nguyên bản vì checker đối chiếu source hash.

Nếu cần **tái chạy verifier trên saved predictions/model**, dùng thư mục output mới:

```bash
./venv/bin/python scripts/model/verify_baseline.py \
  --run-dir output/baseline/run \
  --gold-dir output/research \
  --output-dir output/checks/baseline_$(date +%Y%m%d_%H%M%S)
```

Verifier cần research và saved run; có đối chiếu dự đoán/inference, không fit model hay chấm holdout.

## 3. Muốn kiểm tra toàn bộ dữ liệu nghiên cứu

```bash
make verify-dataset
```

Đây là kiểm tra đầy đủ, cần thêm origination và labels tại `parquet/orig/`, `output/labels/`. Người chỉ nhận research có thể bắt đầu EDA từ schema, manifest và các counts trong guide; không cần tải nguồn chỉ để chạy lệnh này.

## 4. Muốn bắt đầu một thí nghiệm mới

Đọc [phân công](handoff.md) và chốt protocol trước khi chạy batch. Kết quả mới đặt ở `output/experiments/<ten-task>/<run_id>/`; giữ nguyên research và baseline.

Lệnh dưới đây **chạy lại pilot cố định**, không phải runner so nhiều cửa sổ:

```bash
./venv/bin/python scripts/model/train_baseline.py \
  --config configs/baseline.yaml \
  --dataset-dir output/research
```

Trainer tạo `output/experiments/baseline_<timestamp>/`, từ chối thư mục nonempty. Chỉ chạy khi cần tái lập pilot. Thí nghiệm cửa sổ mới cần runner/config riêng; thay mỗi YAML chưa đủ.

Mỗi lần chỉ chạy một tác vụ nặng trên máy chung. `DQ_MEMORY_LIMIT` giới hạn DuckDB, không giới hạn RAM của pandas hoặc thuật toán ML.

## 5. Muốn chạy lại bài tập trên mẫu

Chỉ đọc kết quả thì nhận `output/classwork/` là đủ. Chạy lại script cần research, baseline run/report, origination và `output/schema/orig_schema.csv`. Nhờ Sy bổ sung nguồn nếu máy chưa có.

```bash
./venv/bin/python -m pip install -r requirements-classwork.txt
./venv/bin/python scripts/classwork/run_homework.py \
  --out-dir output/experiments/classwork/$(date +%Y%m%d_%H%M%S)
```

Script từ chối thư mục output đã có. Kết quả bài này là DQ/clustering/outlier/drift trên mẫu; không train classifier mới, chưa thực hiện so sánh Raw/Raw+. Các điểm cần chỉnh ở [eda-plan.md](eda-plan.md).

## 6. Chỉ dành cho người phụ trách dữ liệu: dựng lại nguồn

Các bước dưới đây đọc dữ liệu lớn và không thuộc việc bắt đầu của teammate.

```bash
./venv/bin/python scripts/ingest_stream.py list --src data
./venv/bin/python scripts/ingest_stream.py ingest --src data
DQ_MEMORY_LIMIT=3GB DQ_THREADS=2 bash scripts/label/run_labels.sh
```

Khi cần dựng research từ snapshot mới, chọn một thư mục mới, không ghi đè dữ liệu bàn giao:

```bash
DQ_MEMORY_LIMIT=3GB DQ_THREADS=2 ./venv/bin/python scripts/gold/build_research_dataset.py \
  --output-dir output/experiments/research_build/$(date +%Y%m%d_%H%M%S)
```

Có sẵn Parquet và nhãn thì không cần dựng lại cho mỗi model.

## 7. Khi nào cần tạo lại gói báo cáo?

Gói hiện hành đã có. Không chạy generator chỉ để đọc kết quả.

`scripts/model/generate_handoff_package.py` cần `--run-dir`, `--gold-dir`, `--output-dir` và `--before-provenance`. Before-provenance phải được tạo trước thay đổi, gồm `input_hashes_before.json`, `source_hashes_before.json`, `git_status_before.txt` và `dependency_versions.json`.

Generator chạy tests và verifier, không fit model; output phải mới/rỗng. Giao Sy kiểm tra provenance trước khi tạo lại package.
