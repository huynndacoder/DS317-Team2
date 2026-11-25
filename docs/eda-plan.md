# EDA: cần trả lời gì và làm theo thứ tự nào?

Cập nhật: 25/11/2026. Người phụ trách chính: Huy; phối hợp Nhân và Sy.

EDA là bước hiểu dữ liệu để thiết kế thí nghiệm. Đầu ra cần giúp nhóm trả lời: đang dự đoán cho ai, nhãn hiếm đến đâu, dữ liệu có vấn đề gì và train khác dữ liệu tương lai như thế nào?

Dùng `output/research/` làm điểm bắt đầu. Các bảng tổng hợp nguồn do Sy cung cấp khi cần. Không dựng lại nhãn hoặc đọc toàn bộ performance cho công việc này.

## 1. Xác nhận đang nhìn đúng tập dữ liệu

Lập bảng số khoản và phạm vi quý cho research. Với các tập train, validation và development test, thêm số nhãn 1 và tỷ lệ nhãn 1. Holdout 2024 chỉ kiểm tra metadata; chưa thống kê nhãn hoặc đánh giá kết quả để chọn phương án.

- Research: 16.641.482 khoản Purchase đủ điều kiện.
- Train tune 2009–2013: 1.863.476 khoản.
- Validation 2016: 710.554 khoản.
- Train refit 2012–2016: 2.688.363 khoản.
- Development test 2019: 933.708 khoản; 24.100 nhãn 1, khoảng 2,5811%.

Chọn role từ membership, sau đó join theo loan_id. Kiểm tra không nhân dòng khi join. Membership có overlap giữa các role là có chủ đích. Chưa phân tích kết quả model/nhãn của holdout 2024 để chọn phương án.

**Nộp:** `population_by_role.csv`, `population_by_cohort.csv`. Nếu muốn trình bày luồng origination → Purchase → đủ điều kiện → các role, xin Sy số liệu nguồn và lý do loại. Không gộp mẫu số của các phạm vi khác nhau.

## 2. Hiểu nhãn và mất cân bằng

Vẽ số khoản và tỷ lệ nhãn 1 theo quý, ưu tiên các giai đoạn dùng trong pilot. Hiển thị cả mẫu số để tránh hiểu nhầm một quý ít mẫu.

So train với validation/development. Tỷ lệ rủi ro của năm 2019 cao hơn nhiều tỷ lệ khoảng 0,1% của train pilot; cần mô tả thay đổi này trước khi giải thích metrics.

**Nộp:** một biểu đồ theo quý và nhận xét về thay đổi tỷ lệ nhãn. Chỉ mô tả; chưa dùng test 2019 để tự chọn tham số tốt nhất.

## 3. Hiểu 18 biến đầu vào

Với mỗi biến, ghi loại dữ liệu, ý nghĩa, tỷ lệ thiếu, số giá trị khác nhau và phân bố. Dùng median/quantiles cho biến số, bảng tần suất cho biến phân loại.

Đọc quy tắc tại [data contract](data-contract.md) và `scripts/gold/gold_spec.py` trước khi gắn cờ:
- Mã đặc biệt của Freddie Mac không tự động là một giá trị số hợp lệ.
- DTI = 0 và mortgage insurance = 0 có thể hợp lệ.
- Miền LTV/CLTV thay đổi theo giai đoạn; không áp một ngưỡng tự nghĩ cho mọi năm.
- `number_of_borrowers` là biến phân loại one/multiple/NULL.
- `loan_id` và `number_of_borrowers_raw` không phải predictors.

**Nộp:** `feature_summary.csv`, biểu đồ phân bố và danh sách điểm cần Nhân/Sy kiểm tra. Mẫu để vẽ phải có quy tắc lấy mẫu và số lượng rõ ràng; không tải toàn bộ research vào pandas chỉ để vẽ vài biểu đồ.

## 4. Phối hợp đo chất lượng dữ liệu

Nhân chốt rule table trước khi tính tỷ lệ. Mỗi quy tắc cần: bảng/cột, phạm vi, điều kiện đạt, hạt dữ liệu, tử số, mẫu số và cách tổng hợp theo quý.

| Khía cạnh | Câu hỏi cần trả lời |
| --- | --- |
| Completeness | Những giá trị cần thiết có bị thiếu không? |
| Validity | Giá trị có đúng miền và định dạng theo tài liệu không? |
| Consistency | Các trường có mâu thuẫn với nhau hoặc thay đổi quy tắc theo thời gian không? |
| Uniqueness | Có lặp khóa/dòng trong phạm vi yêu cầu duy nhất không? |
| Accuracy | Có nguồn chuẩn độc lập để biết giá trị có đúng thực tế không? |
| Timeliness | Có timestamp/tiêu chuẩn độ trễ để biết dữ liệu đến đúng hạn không? |

Hai khía cạnh cuối ghi N/A khi thiếu bằng chứng. Đúng miền không chứng minh đúng thực tế. Nếu dùng độ đo thay thế, ghi “proxy” và giải thích nó đo được phần nào.

**Nộp:** độ đo ở mức hạt, tổng hợp theo bảng/quý và biểu đồ. Khi đo trước/sau can thiệp, dùng cùng phạm vi hoặc giải thích rõ thay đổi số dòng.

## 5. Kiểm tra train khác năm 2019 thế nào

So phân bố, tỷ lệ thiếu và các nhóm giá trị giữa train refit 2012–2016 với năm 2019. Nếu tính PSI, dùng các bin/ngưỡng xác định từ train; trình bày cùng biểu đồ và số mẫu.

Tách hai việc: biến đầu vào thay đổi và tỷ lệ nhãn thay đổi. PSI cao là dấu hiệu cần điều tra, chưa chứng minh model hỏng hoặc dữ liệu sai.

**Nộp:** bảng drift theo biến/quý và 3–5 biến cần theo dõi. Ghi nguyên nhân đã có bằng chứng; các nguyên nhân còn lại ghi là giả thuyết.

## 6. Kết thúc EDA bằng quyết định cho thí nghiệm

Báo cáo ngắn cần nêu:
1. Phạm vi dữ liệu và những kiểm tra đã khớp.
2. Các vấn đề cần xử lý trước khi so model.
3. Các biến/giai đoạn cần giám sát.
4. Những giới hạn chưa giải quyết được.

Kết quả mới đặt ở `output/experiments/eda/<run_id>/`; báo cáo có thể đặt ở `docs/eda_report.md`. Ghi lệnh tái lập và đường dẫn các CSV/hình chính. Đây là đầu ra cần làm tiếp; chưa phải EDA full-data đã hoàn thành.

---

## Bài tập Chương 8 + 10: công việc riêng liên quan đến EDA

Cô yêu cầu dùng clustering/outlier và chuỗi thời gian/hồi quy để tạo thêm thông tin, rồi kiểm tra thông tin đó có giúp dự đoán tốt hơn không.

**Ví dụ:** từ hồ sơ khoản vay, tạo nhãn nhóm/độ xa tâm nhóm; từ dữ liệu quá khứ theo quý, tạo một giá trị dự báo bối cảnh. Sau đó so cùng một classifier:
- **Raw:** 18 biến đầu vào hiện có, đã qua chuẩn hóa ngữ nghĩa của dữ liệu.
- **Raw + làm giàu:** giữ các biến đó và thêm đặc trưng mới.

“Raw” ở đây không có nghĩa dùng thẳng mã thiếu trong file Freddie Mac. Hai bản raw/normalized trong bài DQ cũng không phải bằng chứng đã chạy so sánh classifier Raw/Raw+.

### A. Đã có gì?

`output/classwork/` chứa kết quả trên mẫu 8.000 khoản từ train refit và 4.000 khoản năm 2019: DQ, KMeans, GMM, DBSCAN, Isolation Forest/IQR và drift.

Đây là bài chạy trên mẫu. Chưa có bước Chương 10 đầy đủ và chưa có so sánh classifier Raw/Raw+.

### B. Clustering cần kiểm tra lại gì?

1. **KMeans có một cụm chỉ 2 khoản.** Cả hai có cờ thiếu `number_of_units`; khi StandardScaler chuẩn hóa cờ hiếm này, giá trị dương lên khoảng 63,24. Cần thử bỏ/đổi trọng số cờ và so lại. Chưa được kết luận đã tìm thấy 4 phân khúc nghiệp vụ tự nhiên.
2. **DBSCAN hiện có 2 cụm và 3,425% noise trên mẫu train.** Cụm lớn có 7.678 khoản; cách nhìn trong hình 2D chưa đủ để kết luận eps sai. Vẽ k-distance, thử một lưới nhỏ eps/min_samples và báo cả số cụm, noise, cụm lớn nhất, độ đo nội bộ.
3. **Hình PCA thiếu thông tin.** Bổ sung legend, đánh dấu noise = -1, ghi PC1 = 29,02%, PC2 = 14,28%; hai trục giữ khoảng 43,30% phương sai. Các dải chéo có thể liên quan biến rời rạc/tương quan; cần kiểm tra, không kết luận chỉ từ hình.
4. So KMeans/GMM ở cùng một số cụm để dễ đối chiếu, đồng thời có thể báo cấu hình tốt riêng của mỗi phương pháp. Không ép DBSCAN phải có đúng số cụm đó.

Các điểm trên là **việc cần sửa/kiểm tra**, chưa phải bản kết quả mới đã chạy.

### C. Cần giải thích kết quả clustering/outlier thế nào?

Mô tả từng thuật toán theo 5 tiêu chí cô giao: thời gian chạy, loại mô hình, ý tưởng, ưu điểm và nhược điểm.

Đánh giá kết hợp:
- Nội bộ: silhouette, Davies–Bouldin, kích thước cụm; ghi rõ có loại noise khỏi phép tính hay không.
- Bên ngoài: có thể xem liên hệ với nhãn quá hạn sau khi fit, nhưng nhãn quá hạn không phải “đáp án cụm”.
- Trực quan: PCA cùng legend, phương sai, cùng mẫu so sánh.
- Nghiệp vụ: mô tả mỗi nhóm bằng phân bố các biến có ý nghĩa.

Tỷ lệ purity cao có thể do nhãn rất hiếm; không gọi đó là accuracy phân cụm. Outlier là điểm khác thường, chưa chắc là dữ liệu sai. Không tự xóa outlier. Ngưỡng Isolation Forest theo contamination là lựa chọn cấu hình, không phải tỷ lệ lỗi thực đã được xác nhận.

### D. Bổ sung chuỗi thời gian/hồi quy thế nào?

Một phương án cần chốt với Sy: dự báo lãi suất gốc trung bình theo quý của khoản Purchase. Chuỗi này lấy từ origination Purchase trước khi lọc eligible, để tránh dùng khả năng quan sát nhãn tương lai khi tạo đặc trưng. Sy xuất bảng tổng hợp và quy tắc thời điểm dữ liệu sẵn sàng.

So ít nhất một mốc đơn giản (naive) với hồi quy dùng các độ trễ; có thể bổ sung ETS. Backtest theo thời gian và đo MAE, MASE hoặc WAPE, kèm bias. Ghi công thức, mẫu số và cách xử lý trường hợp không tính được.

Mỗi dự báo phải được tạo từ dữ liệu có thể biết trước ngày cấp vay. Không nối giá trị thực tương lai vào feature. Độ trễ có dữ liệu chuỗi là giả định riêng, không tự đồng nhất với lag nhãn 3 tháng.

Ví dụ: nếu tại đầu 2019 chỉ có chuỗi đến 2018Q3 do giả định trễ 3 tháng, dự báo bối cảnh 2019Q1 là bài toán dự báo 2 quý. Không dùng mô hình fit trên cả chuỗi đến năm 2024 để tạo feature cho năm 2019.

### E. Chứng minh làm giàu có ích hay không

1. Fit imputer/scaler, mô hình nhóm/outlier trên train. GMM/KMeans có thể áp lên tập sau bằng predict/transform; DBSCAN không có predict chuẩn cho điểm mới, nên không tùy tiện gán cụm cho test.
2. Tạo feature train bằng quy trình đúng thời gian; các giá trị dự báo chuỗi dùng backtest hoặc out-of-fold theo thời gian. Không lấy fitted value đã dùng dữ liệu tương lai.
3. So Raw, Raw + nhóm, Raw + dự báo và Raw + cả hai trên cùng khoản vay, cửa sổ train, classifier và ngân sách tuning.
4. Đo AP, ROC-AUC, Brier/log-loss và capture@5% theo quý; báo cả chi phí tính toán. Dùng validation để chọn phương án, giữ holdout 2024.
5. Kết luận dựa trên chênh lệch thực nghiệm, kể cả trường hợp không cải thiện. Chưa có kết quả thì ghi “chưa đánh giá”.

Trước mắt hoàn thành phần clustering trên mẫu và bảng chuỗi thời gian. Khi quy trình đã kiểm tra được, mới đưa feature làm giàu vào runner chung. Cửa sổ huấn luyện và đặc trưng làm giàu là hai yếu tố thí nghiệm khác nhau.
