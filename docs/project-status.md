# Trạng thái nghiên cứu

## Đã chốt

- 110 cohorts, nhãn serious delinquency 12 tháng.
- Dữ liệu Purchase eligible: 16.641.482 khoản, 18 features.
- Baseline LR/XGBoost: refit 2012–2016, development 2019.
- Layout hiện hành: output/research, output/baseline, output/classwork.
- Model/preprocessor/predictions không đổi khi chuyển layout; report kiểm chứng được tạo mới.
- Historical LR convergence unknown; không đủ warning evidence để kết luận.
- Holdout 2024 chưa đánh giá mô hình.
- Classwork clustering/outlier/DQ có kết quả trên mẫu 8.000+4.000, chưa có Raw+ experiment.

## Việc tiếp theo

1. EDA/DQ mới theo current population/roles; xem eda-plan.md.
2. Chốt protocol training windows 3/5/10 năm và expanding.
3. Xây runner một development fold, sau đó mở rộng các OOT folds.
4. Kiểm chứng làm giàu Raw/Raw+ và một cải tiến có paper bằng ablation rõ yếu tố.
5. Đáp ứng yêu cầu tối thiểu ba phương pháp; Random Forest mới là đề xuất, chưa train.
6. Khóa phương pháp trước final holdout; hoàn thiện demo và báo cáo.

Dùng chung IDs/features/evaluator; không giao mỗi người một pipeline preprocessing khác nhau.
Trên máy chung mỗi lúc chỉ một heavy process.

## Giới hạn

Baseline chưa phải SOTA hoặc kết quả so windows; snapshot/backfill và lag 3 tháng là giả định.
Accuracy/timeliness DQ cần reference/timestamps hoặc ghi proxy/N/A; chưa tái lập AccTEMPO.
Freddie Mac là dữ liệu Mỹ; chưa kiểm chứng chuyển sang Việt Nam.
