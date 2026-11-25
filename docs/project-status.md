# Trạng thái đồ án — 25/11/2026

## Đang ở đâu?

**Đã chuẩn bị dữ liệu và có baseline pilot được kiểm chứng.** Nhóm đang chuyển sang EDA, đo chất lượng dữ liệu và thiết kế thí nghiệm so cửa sổ huấn luyện. Chưa có kết quả nghiên cứu cuối.

## Đã hoàn thành

- Convert 110 cohort Freddie Mac 1999Q1–2026Q2 sang Parquet: 49.348.308 khoản origination và khoảng 2,89 tỷ dòng performance.
- Dựng và kiểm tra nhãn 12 tháng; xử lý coverage, maturity, termination. Dữ liệu nghiên cứu hiện kết thúc ở cohort đủ điều kiện 2024Q4.
- Bàn giao research: 16.641.482 khoản Purchase đủ điều kiện, 18 predictors, nhãn và metadata thời gian.
- Chạy LR và XGBoost pilot: Stage B train 2012–2016, development test 2019. Preprocessing được fit riêng theo train của mỗi stage.
- Lưu model, preprocessing, predictions và gói kiểm chứng. Kết quả hiện hành ở `output/baseline/report/`.
- Giữ holdout 2024 chưa đánh giá.

## Việc tiếp theo và người phụ trách

| Người | Việc trước mắt |
| --- | --- |
| Huy | EDA toàn bộ research: số lượng/nhãn theo quý, 18 biến, drift train–2019 |
| Nhân | Rule table và độ đo DQ; đề xuất can thiệp dựa trên vấn đề đã thấy |
| Hiển + Sy | Chốt protocol; triển khai runner so cửa sổ 3/5/10 năm và expanding |
| Ys | Chốt paper đủ tiêu chí nơi công bố và phù hợp bài toán; mô tả một cải tiến/ablation |
| Hiền | Demo dùng saved preprocessing + model và kết quả hiện hành |

Hướng dẫn đầu vào, việc đầu tiên và kết quả cần nộp: [handoff.md](handoff.md).

## Bài tập trên lớp

Đã có mẫu 8.000 train + 4.000 development 2019 cho DQ, clustering, outlier và drift. Còn cần chẩn đoán cụm KMeans 2 điểm, bổ sung thông tin hình PCA/DBSCAN, thực hiện Chương 10 và so classifier Raw/Raw+.

Chưa thể khẳng định dữ liệu làm giàu có ích. Chi tiết: [eda-plan.md](eda-plan.md).

## Giới hạn phải giữ khi báo cáo

- LR/XGBoost hiện là baseline kỹ thuật; chưa chốt hoặc tái lập paper baseline.
- Historical LR convergence là unknown vì thiếu bằng chứng warning capture đáng tin cậy.
- Lag nhãn 3 tháng là giả định; snapshot/backfill hạn chế mức khẳng định point-in-time.
- Accuracy/Timeliness DQ ghi N/A khi không có reference/timestamp; proxy phải có giải thích.
- Chưa triển khai AccTEMPO, nghiên cứu nhiều cửa sổ hoặc demo hoàn chỉnh.
- Dữ liệu Freddie Mac của Mỹ; chưa chứng minh mô hình áp dụng trực tiếp tại Việt Nam.
