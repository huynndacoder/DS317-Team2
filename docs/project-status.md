# Trạng thái nghiên cứu và công việc tiếp theo

## Đã chốt

- Ingest 110 cohorts, nhãn serious delinquency 12 tháng.
- Purchase Gold: 16.641.482 khoản eligible, 18 features.
- Logistic Regression và XGBoost pilot trên development cohorts2019.
- Baseline package: 140 synthetic checks và 51 real verifier checks được ghi nhận;
  independent package checker có 218 checks.
- Original model/prediction artifacts được giữ nguyên.
- Historical LR status unknown do warning capture lịch sử không đầy đủ.
- Holdout2024 chưa đánh giá.

Các con số checks là trạng thái tại mốc baseline, không phải mục tiêu cố định của mọi run.

## Còn làm

1. Chốt protocol so training windows3/5/10 năm và expanding.
2. Kiểm runner một development fold rồi mở rộng nhiều OOT folds.
3. Hoàn thiện DQ theo chương4 trên scope Purchase/current split.
4. Chọn một cải tiến có paper support, ví dụ recency weighting; kiểm chứng bằng ablation.
5. Khóa phương pháp trước final holdout, làm demo và báo cáo tổng hợp.

Không cần năm pipelines cho năm teammate. Dùng chung features/IDs/evaluator;
phân công theo EDA, DQ, runner, literature/improvement và demo.
Trên máy chung chỉ chạy một heavy training process.

## Những giới hạn cần trình bày

- Baseline hiện tại chưa phải SOTA hoặc kết quả so training windows.
- DQ scripts cũ có proxy cho accuracy/timeliness và scope chưa đồng bộ.
- Diagnostic plane cũ không phải AccTEMPO nguyên bản.
- Lag3 và availability của dữ liệu là giả định có giới hạn.
- Nguồn Freddie Mac thuộc thị trường Mỹ; chưa kiểm chứng khả năng chuyển sang Việt Nam.
