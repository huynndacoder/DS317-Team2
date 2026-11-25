# DS317 — Nhóm 2

Dự đoán khoản vay mua nhà có quá hạn từ 90 ngày trở lên hoặc chuyển sang REO trong 12 tháng từ tháng trả góp đầu tiên, dùng thông tin lúc cấp vay.

Câu hỏi nghiên cứu: **dùng lịch sử huấn luyện 3, 5, 10 năm hay toàn bộ quá khứ thì dự đoán tốt hơn trên dữ liệu tương lai?**

## Thành viên bắt đầu ở đâu?

**Đọc [hướng dẫn bàn giao](docs/handoff.md)**. Trong đó có: gói cần tải, ý nghĩa bốn file research, việc đầu tiên của từng người và kết quả cần nộp.

- Code/tài liệu: repo này.
- Dữ liệu, saved models và predictions: [Drive nhóm](https://drive.google.com/drive/folders/1xoLgyWRgFcv0Si5hqbS_7K6TfgPRG6rK).
- Chuẩn bị dữ liệu: Sy phụ trách. Team bắt đầu từ output đã bàn giao.

## Hiện đã có gì?

Research gồm **16.641.482 khoản Purchase đủ điều kiện**, 18 predictors và nhãn. Pilot LR/XGBoost đã chạy: Stage B học trên 2012–2016 và kiểm tra trên năm 2019. Holdout 2024 chưa đánh giá.

| Model | AP năm 2019 | ROC-AUC | Capture trong nhóm top 5% mỗi quý |
| --- | ---: | ---: | ---: |
| Logistic Regression | 0,055705 | 0,704997 | 15,15% |
| XGBoost | 0,054566 | 0,689814 | 15,82% |

Đây là pilot kỹ thuật, chưa phải kết quả cuối hoặc tái lập paper baseline. EDA đầy đủ, nghiên cứu cửa sổ, cải tiến model và demo là việc tiếp theo.

## Các thư mục cần biết

| Đường dẫn | Chứa gì |
| --- | --- |
| `scripts/` | Code chuẩn bị dữ liệu, kiểm tra và chạy baseline/classwork |
| `configs/baseline.yaml` | Cấu hình pilot đã kiểm chứng; giữ nguyên cho tái lập |
| `docs/` | Hướng dẫn, data contract, quy tắc nhãn, kế hoạch |
| `reports/baseline.md` | Tóm tắt baseline có thể đọc trên GitHub |
| `output/research/` | Dữ liệu nghiên cứu; nhận từ Drive |
| `output/baseline/run/` | Model, preprocessing và predictions gốc; nhận từ Drive |
| `output/baseline/report/` | Báo cáo/metrics/bằng chứng hiện hành; nhận từ Drive |
| `output/classwork/` | Kết quả bài tập trên mẫu; nhận từ Drive |

Các đường dẫn output trong bảng không có dữ liệu trên GitHub. Đầu ra thí nghiệm mới đặt dưới `output/experiments/<ten-task>/<run_id>/`.

## Đọc tiếp theo việc cần làm

- [Việc từng thành viên và cách bàn giao](docs/handoff.md).
- [EDA và phần bài tập làm giàu dữ liệu](docs/eda-plan.md).
- [Cài môi trường, kiểm chứng, chạy lại](docs/reproducibility.md).
- [Trạng thái hiện tại và phần chưa làm](docs/project-status.md).
- [Data contract](docs/data-contract.md), [quy tắc nhãn](docs/label_rules.md), [bản đồ repo](docs/repository-layout.md).

Không đưa dữ liệu mức khoản vay, loan_id, predictions hoặc model lên GitHub public.
