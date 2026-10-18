# ĐÁNH GIÁ LẠI CÁC HƯỚNG ĐI THEO PDF HƯỚNG DẪN ĐỒ ÁN DS317

Tài liệu đối chiếu: `DS317_Huong_dan_DO_AN_MON_HOC.pdf` (8 trang) — Đồ án cuối kỳ A4, 50% điểm, demo chiếm **50% điểm đồ án**, nhóm 4–6 SV, lộ trình **8 tuần**.

---

## 1. Các ràng buộc "chốt hạ" trích từ PDF

| # | Yêu cầu của DS317 | Điểm mấu chốt |
|---|---|---|
| R1 | **Tuần 1 phải xong thu thập dữ liệu** | Dữ liệu phải tải được ngay, không cần pipeline thu thập tự xây |
| R2 | Hạng mục 1: *"lập ground truth nếu nhãn chưa sẵn có"* | Có nhãn sẵn = giảm lớn khối lượng; tự gán nhãn = rủi ro lớn |
| R3 | Hạng mục 4: **≥ 3 phương pháp, bắt buộc 1 baseline**, tinh chỉnh siêu tham số | Bài toán phân loại có nhiều mô hình chuẩn là lợi thế |
| R4 | Hạng mục 5: *"quy đổi sang độ đo nghiệp vụ"* + ngưỡng chấp nhận | Cần ma trận chi phí/lợi nhuận rõ ràng |
| R5 | **Demo = 50% điểm**, *"khởi động + chạy 1 lượt ≤ 3 phút"*, dùng mô hình thật không phải kết quả cố định, diễn giải *"danh sách đối tượng cần ưu tiên xử lý kèm lý do"* | Dữ liệu demo phải nhỏ, suy luận nhanh, giải thích được bằng nghiệp vụ |
| R6 | Chương 6: kiến trúc triển khai + **thiên lệch & quyền riêng tư** | Đề tài có vấn đề fairness thực sự sẽ ghi điểm |
| R7 | *"Giảng viên có quyền hỏi bất kỳ thành viên nào về bất kỳ phần nào"* — nhóm phải giải thích được mọi dòng mã | Kỹ thuật quá mới/khó (GNN trên đồ thị code) là rủi ro bảo vệ |
| R8 | Công cụ được liệt kê: **Google Colab, Microsoft Azure** (cùng VS Code, PyCharm...) | Dataset phải chạy được trên Colab (~12GB RAM) |
| R9 | *"Không sử dụng lại đồ án của nhóm khác hoặc các khóa trước"* | Đề tài quá phổ biến phải có điểm khác biệt rõ |

---

## 2. Bảng chấm điểm lại 5 hướng (thang 1–5 mỗi tiêu chí, tối đa 45)

| Tiêu chí DS317 | 🏦 Credit Scoring (Gunnarsson 2021) | 💳 Fraud Detection (Chan 1999) | 🔗 Entity Linking (Ding 2021) | 📉 Stealthy Shorts (Goyal 2025) | 🔀 Code Revert GNN (Pei 2023) |
|---|---|---|---|---|---|
| R1. Dữ liệu xong tuần 1 | 5 (CSV tải ngay) | 5 (CSV 150MB) | 4 (nhiều nguồn phải ghép) | **2 (80GB, cần DuckDB/Polars)** | **2 (phải tự mine GitHub)** |
| R2. Ground truth sẵn có | 5 (nhãn default) | 5 (nhãn fraud) | 3 (201 bài gold NER — mỏng) | **2 (tự định nghĩa "informed")** | **2 (SZZ gán nhãn, nhiễu)** |
| R3. ≥3 model + baseline | 5 (LR/DT/RF/XGB/MLP/DBN — chính là bài báo) | 5 (baseline + ensemble + AdaCost) | 4 (NER + string-metrics + neural) | 4 (clustering + classifier) | 4 (GBDT + GNN) |
| R4. Độ đo nghiệp vụ | **5 (profit/cost matrix có sẵn trong tài liệu)** | 5 (tổn thất gian lận, recall@precision) | 3.5 (giờ phân tích tiết kiệm — suy diễn) | 3 (PnL — khó nói thành "doanh nghiệp") | **2.5 (giờ dev — mơ hồ)** |
| R5. Demo ≤3 phút + ưu tiên xử lý | **5 (nhập hồ sơ → duyệt/từ chối + lý do + thanh trượt ngưỡng)** | **5 (nhập giao dịch → cảnh báo + lý do)** | 4.5 (dán tin → gắn thực thể — rất demo được) | 3.5 (phải precompute) | 3.5 (dán commit → rủi ro) |
| R6. Triển khai + thiên lệch/riêng tư | **5 (fairness tuổi/dân tộc là vấn đề thật của credit)** | 4 | 4 | 3 | 3 |
| R7. Cả nhóm giải thích được | 5 | 5 | 3.5 (embedding/margin loss) | 3.5 (microstructure) | **2 (GNN + SZZ — nặng nhất)** |
| R8. Chạy được trên Colab/Azure | 5 | 5 | 4 | **2 (80GB)** | 3 |
| R9. Khác biệt hóa (tránh trùng đề tài cũ) | 3.5 | 3 | 4.5 | 5 | 5 |
| **TỔNG /45** | **43.5** | **42** | **35** | **28** | **27** |

---

## 3. Kết luận xếp hạng lại

### 🥇 Hạng 1: Credit Scoring — "Deep Learning for Credit Scoring: Do or Don't?" (Gunnarsson et al., 2021)
- Trúng **tất cả** tiêu chí rubric: nhãn sẵn, 6–7 mô hình so sánh đúng thiết kế bài báo (LR baseline → XGBoost → MLP/DBN), bài báo vốn đã là một "khung đánh giá mô hình" hoàn chỉnh chỉ cần tái hiện.
- Điểm ăn riêng so với mọi hướng khác: **Chương 6 yêu cầu phân tích thiên lệch — credit scoring là một trong số ít đề tài có vấn đề fairness được nghiên cứu bài bản** (đặc trưng tuổi, ràng buộc đơn điệu theo quy định, tài liệu NAM/MNAM đã khảo sát).
- Độ đo nghiệp vụ có chuẩn sẵn: profit-driven evaluation / expected cost (tài liệu Empulse ghi sẵn cost matrix cho GMSC).
- **Điểm cần khác biệt (R9):** thêm chiều mà các khóa trước ít làm — Bayesian hypothesis testing + profit curve + so sánh trên ≥3 dataset (GMSC + Home Credit + German).

### 🥈 Hạng 2: Fraud Detection — "Distributed Data Mining in Credit Card Fraud" (Chan et al., 1999)
- Nhị phân mất cân bằng cực đoan đúng chỗ rubric yêu cầu ("xử lý mất cân bằng lớp"), demo kịch tính cao (giao dịch → cảnh báo + lý do), cost-sensitive learning cho R4.
- **Điểm cần khác biệt (R9):** đề tài rất dễ trùng giữa các nhóm. Khác biệt bằng đúng góc nhìn của bài báo gốc: **metalearning/ensemble phân tán + cost-sensitive (AdaCost)** thay vì chỉ SMOTE + XGBoost như mọi người làm; so sánh trên 2–3 dataset (ULB + Interpretable-1M).
- Kèm dataset đồ sộ của Hào Húy (Interpretable 1M) cho SHAP → giải thích "lý do" trong demo rất mạnh.

### 🥉 Hạng 3 (nên cân nhắc thay thế): Customer Churn — từ bài #6 của Nguyễn Sĩ Huỳnh (Imani et al., 2025)
- Đánh giá ban đầu cho 7/10 vì là review paper, **nhưng khi đặt cạnh rubric DS317 thì đề tài churn lại khớp gần như từng chữ**: ví dụ diễn giải nghiệp vụ trong PDF là *"danh sách đối tượng cần ưu tiên xử lý kèm lý do"* — chính là danh sách khách hàng cần gọi giữ chân.
- Dataset Telco Customer Churn (7,043 × 21, Kaggle) tải trong 5 phút, 3+ mô hình chuẩn, mất cân bằng ~26%, business metric = giá trị giữ chân, demo Streamlit trực quan.
- Nếu nhóm muốn "an toàn tuyệt đối" theo rubric, đây là phương án dự phòng mạnh, dùng chính tài liệu khảo sát của thành viên làm Chương 2.

### ⏸️ Hạng 4–5: Nên dừng — không Chạy theo rubric dù tiềm năng nghiên cứu cao

**Stealthy Shorts (28/45)** — trước đây chấm 9/10 theo tiêu chí "tiềm năng khai phá dữ liệu", nhưng:
- 80GB dữ liệu vi phạm trực tiếp R8 (Colab) và nuốt trọn Tuần 1 (R1); 04_Data không thể nộp kèm.
- Không có nhãn sẵn → cả nhóm phải **tự phát minh ground truth** rồi bảo vệ nó (R2, R7) — rủi ro bị chất ván "làm sao biết nhãn đúng?".
- Câu chuyện "doanh nghiệp" yếu (prop-trading ≠ doanh nghiệp điển hình trong môn học).
- **Giữ lại làm** đề tài nghiên cứu cá nhân/hướng phát triển trong Chương 7, không làm đồ án chính.

**Code Revert GNN (27/45)** — trước đây chấm 9/10, nhưng:
- Phải tự xây pipeline thu thập (GitHub API + ast + PyDriller + SZZ) — đây là một đồ án khác, chưa kể đồ án chính.
- GNN + SZZ là cặp kỹ thuật khó giải thích nhất trong 5 hướng khi "giảng viên hỏi bất kỳ thành viên nào" (R7).
- Độ đo nghiệp vụ (giờ dev tiết kiệm) khó quy đổi thuyết phục (R4).

### 🔗 Entity Linking (35/45) — Hạng 3.5, giữ làm phương án dự phòng thứ hai
- Demo đẹp (dán tin tức → gắn công ty/ticker), doanh nghiệp frame tốt (JPMorgan), nhưng ground truth mỏng (201 bài NER) → phải tự gán nhãn thêm (R2), pipeline 3 tầng (NER → ứng viên → xếp hạng) = 3 đồ án con, phân tích lỗi xuyên tầng phức tạp trong 8 tuần.

---

## 4. Đối chiếu nhanh hướng hạng 1 với lộ trình 8 tuần

| Tuần | Yêu cầu DS317 | Việc cụ thể (Credit Scoring) |
|---|---|---|
| 1 | Chốt phạm vi + dữ liệu | Tải GMSC + Home Credit + German; từ điển dữ liệu 10 thuộc tính; đánh giá 6 chiều chất lượng |
| 2 | Tiền xử lý + đặc trưng | Xử lý giá trị thiếu (MonthlyIncome, #Dependents); ngoại lai; WOE/IV encoding; SMOTE/class-weights; tự động bằng script |
| 3 | Baseline + khung đánh giá | LR baseline; khung CV phân tầng + seed cố định; các độ đo cam kết (AUC, H-measure, profit) |
| 4 | Cài đặt + tinh chỉnh | DT, RF, XGBoost, LightGBM, MLP, DBN; Optuna/grid; nhật ký thực nghiệm |
| 5 | Phân tích lỗi + nghiệp vụ | Bayesian correlated t-test; SHAP; quy đổi profit theo cost matrix; đối chiếu ngưỡng |
| 6 | Demo + kiến trúc | Streamlit: nhập hồ sơ → xác suất → duyệt/từ chối + lý do; thanh ngưỡng Precision/Recall; sơ đồ Azure |
| 7 | Báo cáo + tổng duyệt | 30–50 trang theo cấu trúc Chương 1–7; slides; chạy thử demo ≤3 phút |
| 8 | Nộp + bảo vệ | Cấu trúc thư mục 01–08 đúng PDF |

---

## 5. Tóm tắt một dòng

> **Theo rubric DS317: chọn Credit Scoring (Gunnarsson et al.) làm đề tài chính, Fraud Detection (Chan et al.) làm phương án 2 — cả hai đều có dữ liệu tải-ngay, nhãn sẵn, demo ≤3 phút và độ đo nghiệp vụ rõ. Stealthy Shorts và Code Revert GNN tuy tiềm năng khai phá cao nhưng không phù hợp rubric (dữ liệu tự thu + nhãn tự gán + khó bảo vệ) — chuyển thành hướng phát triển trong Chương 7.**
