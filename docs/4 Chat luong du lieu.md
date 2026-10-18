# CHƯƠNG 4 — Chất lượng dữ liệu

> **Học phần:** DS317 – Khai phá dữ liệu trong doanh nghiệp
> **Biên soạn:** ThS. Nguyễn Thị Anh Thư
> **Nguồn:** `docs/4 Chat luong du lieu.pdf` (68 slide)
> **Ghi chú chuyển đổi:** Văn bản trích xuất tự động từ PDF. Các bảng/biểu đồ được
> thiết kế dưới dạng hình ảnh trong slide gốc không trích xuất được nội dung ô —
> những chỗ đó được đánh dấu *(hình/bảng trong slide gốc)*.

---

## Chuẩn đầu ra (Learning Outcomes)

CĐRMH của Buổi 4 – Chương 4 (Đề cương DS317, Bảng 1):

- **G1.1:** Tóm tắt và giải thích được các khái niệm, thuật ngữ cơ bản thuộc lĩnh vực
  dữ liệu lớn và khoa học dữ liệu; (…) tóm tắt và phân tích được các vấn đề trong quá
  trình quản lý và khai phá dữ liệu lớn trong doanh nghiệp.
- **G2.1:** Trình bày và tóm tắt đầy đủ những phương pháp tìm hiểu, phân tích, tiền xử
  lý và khai phá dữ liệu lớn trong doanh nghiệp; (…) mô phỏng và áp dụng các phương
  pháp này vào thực tiễn trong doanh nghiệp.
- **Trong chương này:** G1.1 → khái niệm, khía cạnh, độ đo, khuôn khổ và vấn đề CLDL;
  G2.1 → đo lường, giám sát, lựa chọn phương pháp quản lý CLDL, áp dụng vào đồ án (A4).

## Nội dung Chương 4

1. Giới thiệu về chất lượng dữ liệu
2. Khuôn khổ và độ đo đánh giá chất lượng dữ liệu
3. Phân tích đánh giá và lựa chọn phương pháp quản lý CLDL phù hợp
4. Quản lý vòng đời dữ liệu
5. Phân tích các vấn đề tồn tại và xu hướng tiềm năng
6. Tổng kết và định hướng đồ án

---

# PHẦN 1 — Giới thiệu về chất lượng dữ liệu

- Khái niệm chất lượng dữ liệu – mức độ phù hợp mục đích sử dụng.
- Vì sao chất lượng dữ liệu quan trọng với doanh nghiệp và AI.
- Bài học từ các sự cố dữ liệu thực tế.
- Vị trí của CLDL trong quy trình khám phá tri thức; bối cảnh dữ liệu dị thể và dự đoán sớm.

> **Câu hỏi trọng tâm:** Vì sao doanh nghiệp phải quan tâm đến chất lượng dữ liệu trước khi khai phá?

## Chất lượng dữ liệu là gì?

- **Chất lượng dữ liệu (Data Quality – DQ):** mức độ dữ liệu phù hợp cho mục đích sử
  dụng (*fitness for use*).
- Là khái niệm **đa khía cạnh** (multi-dimensional): đầy đủ, chính xác, nhất quán, kịp
  thời, hợp lệ, duy nhất…
- Mang tính **tương đối theo ngữ cảnh**: cùng dữ liệu có thể đủ tốt cho báo cáo nhưng
  chưa đủ tốt cho mô hình AI.
- Mỗi khía cạnh được lượng hoá bằng **độ đo (metric)** để giám sát và cải thiện liên tục.

> **Ví dụ:** Bảng khách hàng thiếu 5% số điện thoại vẫn đủ cho báo cáo doanh thu, nhưng
> chưa đạt yêu cầu cho chiến dịch gọi điện chăm sóc khách hàng.

## Vì sao chất lượng dữ liệu quan trọng?

- CLDL quyết định độ tin cậy của báo cáo, phân tích và mô hình AI – *"garbage in, garbage out"*.
- Chi phí của dữ liệu kém tăng theo thời gian: lỗi càng phát hiện muộn càng tốn kém.
- Doanh nghiệp cần đo lường – giám sát – cải thiện CLDL liên tục, không làm một lần rồi thôi.

## Bài học từ sự cố dữ liệu thực tế

- Lỗi ở đầu vào lan truyền đến mô hình, báo cáo và quyết định kinh doanh.
- Nhiều sự cố bắt nguồn từ lỗi rất đơn giản: sai đơn vị, vượt giới hạn định dạng, nhập nhầm.
- Thiếu kiểm tra tự động – giám sát – cảnh báo khiến lỗi bị phát hiện quá muộn.

## Vị trí của chất lượng dữ liệu

Quy trình khám phá tri thức cho dự đoán gồm 4 thành phần:

- **(R1)** thu thập dữ liệu
- **(R2)** chuẩn bị dữ liệu
- **(R3)** mô hình dự đoán
- **(R4)** khung CLDL (DQF)

R4 là **lớp điều phối (orchestration layer)**: biến R2 từ "làm theo kinh nghiệm" thành
quy trình dựa trên tiêu chí. DQF định nghĩa khía cạnh, hướng dẫn can thiệp và liên kết
định lượng cải thiện CLDL với hiệu quả của R3.

## Dữ liệu dị thể & dự đoán sớm

- Dữ liệu doanh nghiệp **dị thể** (heterogeneous): có cấu trúc (hồ sơ, giao dịch), bán
  cấu trúc (log JSON, clickstream), phi cấu trúc (văn bản, bình luận).
- Dữ liệu tích luỹ theo thời gian; quyết định phải đưa ra trước khi quá trình kết thúc –
  **dự đoán sớm** (early prediction).
- Giá trị dự đoán giảm dần theo thời điểm → CLDL đầu vào trở thành **yêu cầu vận hành**,
  không chỉ là bước tiền xử lý.

> **Ví dụ:** Cảnh báo sớm học viên MOOC có nguy cơ bỏ học tại mốc 25% khoá học – khi dữ
> liệu hành vi còn ít và liên tục thay đổi.

---

# PHẦN 2 — Khuôn khổ và độ đo đánh giá chất lượng dữ liệu

- Khuôn khổ – khía cạnh – độ đo; chuẩn tham chiếu DAMA, ISO/IEC 25012.
- Đánh giá chủ quan, khách quan và các dạng hàm độ đo.
- Độ đo truyền thống ở mức hạt dữ liệu và hạn chế của chúng.
- Khung TEMPO-DQ, độ đo AccTEMPO và mặt phẳng chẩn đoán lỗi AI.

> **Câu hỏi trọng tâm:** Đo bằng gì để kết luận dữ liệu thực sự phù hợp cho mô hình AI?

## Khuôn khổ – Khía cạnh – Độ đo

- **Khuôn khổ CLDL (DQ Framework – DQF):** cách tiếp cận có cấu trúc gồm định nghĩa,
  tiêu chuẩn, quy trình, công cụ và quản trị CLDL.
- **Khía cạnh (dimension):** một thuộc tính đo được của CLDL, ví dụ tính đầy đủ, tính
  nhất quán.
- **Độ đo (metric):** hàm ánh xạ khía cạnh thành giá trị số, thường chuẩn hoá về đoạn
  `[0; 1]`.
- Độ đo được tính ở nhiều mức tổng hợp: giá trị → thuộc tính → bản ghi → bảng → CSDL.

## Sáu khía cạnh chất lượng cốt lõi

- Bộ 6 khía cạnh cốt lõi được dùng phổ biến (DAMA UK, 2013; UK Government, 2020).
- Mỗi khía cạnh ứng với một câu hỏi kiểm tra cụ thể trên dữ liệu.

*(hình/bảng trong slide gốc — 6 khía cạnh: chính xác, đầy đủ, nhất quán, kịp thời, hợp
lệ, duy nhất)*

> **Ví dụ:** Email `"binh.tran@"` sai định dạng → vi phạm tính **hợp lệ**; một khách hàng
> có hai bản ghi cùng mã → vi phạm tính **duy nhất**.

## Mô hình ISO/IEC 25012 (15 đặc tính)

- Chuẩn quốc tế về mô hình CLDL thuộc họ SQuaRE (ISO/IEC 25000).
- **Nội tại (inherent):** chất lượng tự thân của dữ liệu – 5 đặc tính.
- **Phụ thuộc hệ thống (system-dependent):** chất lượng đạt được và duy trì nhờ hệ thống
  – 3 đặc tính.
- 7 đặc tính mang cả hai góc nhìn; ISO/IEC 25024 hướng dẫn cách đo các đặc tính.

*(hình/bảng trong slide gốc)*

## So sánh các bộ khía cạnh CLDL

- Chưa có đồng thuận về một danh sách khía cạnh chuẩn (Sebastian-Coleman, 2012).
- Bốn khía cạnh phổ biến nhất: **chính xác, đầy đủ, nhất quán, kịp thời**
  (Ehrlinger & Wöß, 2022).
- Luật Dữ liệu 2024 (Điều 12): bảo đảm tính chính xác, hợp lệ, toàn vẹn, đầy đủ, cập
  nhật kịp thời, thống nhất.

## Đánh giá chủ quan & khách quan

- **Chủ quan (subjective):** khảo sát người dùng dữ liệu theo thang điểm, ví dụ bảng hỏi AIMQ.
- **Khách quan (objective):** tính độ đo trực tiếp từ dữ liệu bằng quy tắc kiểm tra – tự
  động hoá được.
- Khía cạnh "cứng" đo khách quan được; khía cạnh "mềm" cần đánh giá chủ quan (Piro, 2014).
- Xu hướng: ưu tiên đo khách quan, tự động, tái lập; bổ sung chủ quan khi cần diễn giải nghiệp vụ.

## Ba dạng hàm độ đo khách quan

- **Tỷ lệ đơn giản (simple ratio):** `1 − số đơn vị lỗi / tổng số đơn vị`; dùng cho đầy
  đủ, không lỗi, nhất quán.
- **Min/Max:** gộp nhiều chỉ báo; `min` cho đánh giá thận trọng, `max` cho đánh giá dễ dãi.
- **Trung bình có trọng số (weighted average):** khi biết mức quan trọng của từng thành
  phần, với `Σwi = 1`.

> **Ví dụ:** Tỷ giá cập nhật cách đây 2 giờ (currency), thường biến động sau 8 giờ
> (volatility) → `Timeliness = max(0; 1 − 2/8) = 0,75`.

## Độ đo truyền thống ở mức hạt dữ liệu

- **Hạt dữ liệu (data grain):** đơn vị nhỏ nhất để đo CLDL, ví dụ một bản ghi học viên – khoá học.
- Đo tại mức hạt giúp phát hiện lỗi cục bộ sớm; tổng hợp lên tập dữ liệu, pha, pipeline
  bằng trung bình cộng.
- Đầy đủ, Nhất quán: dễ tự động nhất; Kịp thời: khi cần dữ liệu tươi; Chính xác: khi có
  nguồn tham chiếu tin cậy.

## Ví dụ: đo CLDL bảng khách hàng

- **Quy tắc:** email đúng định dạng; tuổi ∈ `[18; 100]`; mã KH duy nhất; cập nhật trong
  12 tháng (tính đến 30/9/2026).
- Đầy đủ `= 28/30 = 0,93`; Hợp lệ `= 8/10 = 0,80`; Duy nhất `= 5/6 = 0,83`;
  Kịp thời `= 4/6 = 0,67`.
- Trung bình `≈ 0,81` → ưu tiên cập nhật bản ghi cũ và hợp nhất khách hàng trùng mã.

## Hạn chế của độ đo truyền thống

- Sau tiền xử lý, Completeness và Consistency **bão hoà = 1,000** ở cả 6 phiên bản
  V1–V6 → không phân biệt được.
- Trên cùng dữ liệu, `AccTEMPO_M1` vẫn tách biệt các phiên bản với biên độ `0,1081` và `0,3370`.
- Độ đo tĩnh (snapshot) không phản ánh mức phù hợp cho quyết định AI theo thời gian.

## Khung TEMPO-DQ cho dự đoán sớm

- TEMPO-DQ: khung CLDL vận hành (operational DQF) cho dự đoán sớm đa lớp trên dữ liệu
  lớn dị thể.
- Chuẩn hoá chuẩn bị – quản trị – đo lường – can thiệp cho dữ liệu có cấu trúc, bán cấu
  trúc, phi cấu trúc trong một pipeline.
- Kết hợp độ đo truyền thống với độ đo nâng cao AccTEMPO; đóng góp cốt lõi là nguyên lý
  **Temporal–Ensemble**.

## Pipeline 6 bước của TEMPO-DQ

- Mỗi lượt chạy trả lời: phiên bản dữ liệu này có phù hợp cho quyết định tại thời điểm
  này không, vì sao, và cần sửa gì.
- **Ràng buộc cốt lõi:** tại mỗi mốc quyết định chỉ dùng dữ liệu đã tồn tại – không "nhìn
  trước" (*no look-ahead*).
- **Vòng lặp khép kín:** chẩn đoán → can thiệp → đo lại trên cùng một thang đo.

## Nguyên lý Temporal–Ensemble

- **Temporal:** đánh giá qua các pha quan sát P1–P4 (25%, 50%, 75%, 90% tiến trình); dữ
  liệu pha trước là tiền tố của pha sau.
- **Ensemble:** gộp bằng chứng qua hội đồng mô hình RNN, LSTM, GRU, BiLSTM → giảm thiên
  lệch do một mô hình.
- Chỉ gộp theo mô hình giảm độ phân tán kết luận `54,6% / 65,8%`; chỉ gộp theo pha giảm
  `45,2% / 27,5%`; kết hợp cả hai → một kết luận duy nhất.

## AccTEMPO: chẩn đoán ba cấp

- **M1 – Chỉ báo toàn cục:** gộp theo mô hình và pha → giám sát xu hướng, xếp hạng phiên
  bản dữ liệu.
- **M2 – Tóm tắt theo pha:** cố định pha, gộp theo mô hình → so sánh trước/sau can thiệp.
- **M3 – Đánh giá chi tiết:** theo từng bộ (phiên bản V, mô hình m, pha p) → truy nguyên
  nguyên nhân.
- Trọng số mặc định: `wp = (0,4; 0,3; 0,2; 0,1)` ưu tiên pha sớm; `wm = 1/|M|`.

## Thành phần hiệu năng & sức khoẻ

- **Sperf** (từ ma trận nhầm lẫn): trung bình nhân của MacroF1, BalancedAcc, `(MCC+1)/2`,
  `(κ+1)/2`.
- **Ssan+** (từ ma trận xác suất): trung bình nhân 6 chỉ số sức khoẻ `snan`, `smaj/jsd`,
  `sent`, `sdrift`, `seff`, `sleak`.
- `M3 = Sperf^α · Ssan+^β`, mặc định `α = 0,6`; `β = 0,4` – như **cổng AND**: một thành
  phần yếu kéo điểm xuống mạnh.
- Không dùng Accuracy thô vì bị lớp đa số chi phối khi mất cân bằng.

## Ví dụ tính AccTEMPO

- Cấu hình: bài toán chất lượng khoá học, mô hình LSTM, phiên bản V1-Median, pha P4.
- `Sperf = (0,8704 · 0,8603 · 0,9059 · 0,9051)^(1/4) = 0,8852`
- `Ssan+ = (1 · 0,9651 · 0,5968 · 0,9650 · 1 · 0,3241)^(1/6) = 0,7515`
- `M3 = 0,8852^0,6 · 0,7515^0,4 = 0,8291` → `M2(V1 | P4) = 0,7641` → `M1(V1) = 0,7047`

## Mặt phẳng chẩn đoán (x, y)

- Trục `x = Ssan+` (sức khoẻ), `y = Sperf` (hiệu năng); ngưỡng `x0 = 0,75` và `y0 = 0,70`.
- Q1 phù hợp mục đích; Q2 hiệu năng cao – sức khoẻ thấp; Q3 cả hai thấp; Q4 khoẻ nhưng
  hiệu năng thấp.
- Bài toán chất lượng khoá học (112 cấu hình): Q1 `17,86%` – Q2 `20,54%` – Q3 `37,50%`
  – Q4 `24,11%`.
- Ngưỡng lỏng `(0,70; 0,65)` đẩy Q1 lên 50%; ngưỡng chặt `(0,80; 0,75)` làm Q1 = 0 →
  chọn cặp `(0,75; 0,70)`.

## Bốn chế độ lỗi AI & can thiệp

- Mỗi chế độ lỗi để lại dấu vết riêng trên Sperf và Ssan+ → khoanh vùng nguyên nhân trước
  khi can thiệp.
- Mục tiêu không chỉ biết "điểm thấp" mà biết vì sao chưa phù hợp và ưu tiên sửa gì.

*(hình/bảng trong slide gốc)*

## Kiểm tra nhanh – Phần 2

1. Cột Email có 1.000 bản ghi, trong đó 50 ô trống. Completeness của cột bằng bao nhiêu?
2. Vì sao Completeness = Consistency = 1,000 nhưng dữ liệu vẫn có thể chưa "phù hợp mục đích"?
3. Cho `Sperf = 0,64`; `Ssan+ = 0,81`; `α = 0,6`; `β = 0,4`. Tính `AccTEMPO_M3`.
4. Cấu hình có `Sperf = 0,82` và `Ssan+ = 0,40` nằm ở vùng nào? Nghi ngờ chế độ lỗi gì?

---

# PHẦN 3 — Phân tích đánh giá và lựa chọn phương pháp quản lý CLDL phù hợp

- Quản lý chất lượng dữ liệu (DQM) và các khung tiêu biểu 1998–2027.
- Phân tích năng lực và khoảng trống của các khung hiện có.
- Tiêu chí, cây quyết định lựa chọn phương pháp phù hợp.
- Công cụ, ví dụ thực tế và đánh giá hiệu quả can thiệp.

> **Câu hỏi trọng tâm:** Chọn phương pháp quản lý CLDL nào cho bối cảnh doanh nghiệp cụ thể?

## Quản lý chất lượng dữ liệu (DQM)

- **DQM (Data Quality Management):** phân tích, cải thiện và bảo đảm CLDL (DAMA) – một
  chu trình liên tục.
- **Bốn hoạt động cốt lõi:** hồ sơ hoá hiện trạng → đo lường, đánh giá → làm sạch, cải
  thiện → giám sát liên tục.
- **Giám sát dữ liệu** (kiểm tra quy tắc liên tục) khác **giám sát CLDL** (đo CLDL liên
  tục theo thời gian).
- TDQM (Wang, 1998) vận hành theo vòng **Define – Measure – Analyze – Improve**.

## Tiến hoá các khung CLDL (1998–2027)

- **Định hướng lý thuyết:** hướng dẫn khái niệm, quản trị; thiên về đánh giá chủ quan
  (TDQM, TIQM, AIMQ, OODA DQ…).
- **Định hướng thực tiễn:** chỉ báo khách quan, triển khai được (DQA, DQAF, TBDQ,
  EHR-DQF, Vase…).
- **Nhóm lai** kết hợp chủ quan – khách quan: HIQM, CDQ, HDQM, METRIC.

## Khoảng trống của các khung hiện có

- **Chủ quan chi phối:** 7/19 khung chỉ đánh giá chủ quan, 4/19 kết hợp → khó tự động
  hoá, khó tái lập.
- **Thiếu cơ chế cải thiện:** trong 12 khung có đo khách quan, chỉ 3 khung hướng dẫn can
  thiệp nâng cao CLDL.
- **Hỗ trợ loại dữ liệu không đều:** 8/19 hỗ trợ bán cấu trúc, 9/19 hỗ trợ phi cấu trúc.
- Đa số **tĩnh (snapshot)**, chưa liên kết CLDL với hành vi mô hình ở hạ nguồn.

## Lựa chọn khung CLDL phù hợp

- Căn cứ bối cảnh dữ liệu (loại, nguồn, tốc độ), hệ thống thông tin và loại hình kinh doanh.
- **Tiêu chí:** chức năng, tính linh hoạt, khía cạnh đề xuất, khả năng định lượng – tự
  động hoá, loại dữ liệu hỗ trợ, hướng dẫn triển khai.
- TEMPO-DQ phù hợp khi dữ liệu đa nguồn (**C1**), tích luỹ theo thời gian (**C2**), nhãn
  đa lớp cố định (**C3**), có mốc quyết định sớm (**C4**).

## Công cụ đo lường & giám sát CLDL

- Khảo sát hệ thống: **667 công cụ** "data quality"; **13 công cụ** được đánh giá chi
  tiết (Ehrlinger & Wöß, 2022).
- Đa số hỗ trợ hồ sơ hoá (profiling); không công cụ nào cài đặt đủ các độ đo khoa học;
  giám sát thường là tính năng trả phí.
- Chọn công cụ theo quy mô dữ liệu, nền tảng (Python, Spark, Lakehouse) và nhu cầu giám
  sát liên tục.

## Ví dụ: kiểm tra CLDL bằng Python

- Biến quy tắc nghiệp vụ thành kiểm tra tự động, chạy mỗi lần nạp dữ liệu mới.
- Kết quả là bảng độ đo theo thời gian → đầu vào cho dashboard giám sát (đồ án Cơ bản).
- Đặt ngưỡng cảnh báo (ví dụ `< 0,95`) để kích hoạt can thiệp; lưu log để truy vết.

## Ví dụ: DQM cho dự đoán tốt nghiệp

- Dữ liệu thực của một trường đại học: **8 bảng** (điểm học phần 674.273 dòng…);
  **6.637 sinh viên tốt nghiệp** (2006–2019).
- Quy trình 4 giai đoạn: **Hồ sơ hoá → Triển khai → Giám sát → Cải thiện**
  (Profile – Implement – Monitor – Improve).
- **5 khía cạnh:** chính xác, đầy đủ, nhất quán, duy nhất, kịp thời; kiểm tra ở mức dòng
  và mức bảng.
- Hạ tầng Azure: Data Factory → Data Lake (Bronze, Silver, Gold) → Databricks → Synapse
  Analytics.

## Kết quả trước & sau cải thiện CLDL

- Bảng Student: chính xác `45,99 → 87,53`; nhất quán `35,67 → 90,00`. WaiverTuition:
  đầy đủ `7,59 → 65,00`.
- LightGBM: Accuracy `80,65% → 85,05%`, F1 `68,80% → 77,50%`; CatBoost: Accuracy
  `79,32% → 85,16%`.
- **Bài học:** luôn đo lại sau can thiệp để chứng minh hiệu quả bằng số liệu.

## Chẩn đoán → Can thiệp → Đo lại

- **Chẩn đoán V0** (kết quả học tập): `seff = 0,5832` (mất thông tin); `sleak = 0,1291`
  – chỉ từ mẫu thiếu đã đoán được nhãn (AUC ≈ 0,87).
- **Can thiệp đúng – điền khuyết:** `seff = 1,0`; `sleak = 0,5`; M1: `0,2788 → 0,4864`.
- **Can thiệp phản tác dụng – CDSMOTE:** Sperf vẫn `0,5632` nhưng sdrift giảm
  `0,9990 → 0,5603`; `M1 = 0,1495` (thấp hơn dữ liệu thô).

## Thảo luận nhóm (10 phút)

1. Mô tả dữ liệu đề tài: nguồn, loại (có cấu trúc, bán cấu trúc, phi cấu trúc), hạt dữ liệu.
2. Chọn 4–6 khía cạnh CLDL phù hợp mục đích; đề xuất độ đo và ngưỡng chấp nhận.
3. Đề xuất khung/phương pháp quản lý CLDL và công cụ; giải thích lý do lựa chọn.
4. Dự kiến một can thiệp cải thiện và cách đo lại hiệu quả (trước/sau).

---

# PHẦN 4 — Quản lý vòng đời dữ liệu

- Vòng đời dữ liệu và nguyên tắc đánh giá chất lượng ở mọi giai đoạn.
- Chất lượng trong vòng đời dữ liệu lớn và pipeline Lakehouse.
- Chuẩn bị dữ liệu chống rò rỉ thời gian.
- Giám sát liên tục và chi phí chất lượng (quy tắc 1-10-100).

> **Câu hỏi trọng tâm:** Đặt kiểm soát chất lượng ở đâu, khi nào trong vòng đời dữ liệu?

## Vòng đời dữ liệu (Data Lifecycle)

- **6 giai đoạn:** Lập kế hoạch → Thu thập, nạp → Chuẩn bị, lưu trữ → Sử dụng, xử lý →
  Chia sẻ, công bố → Lưu trữ lâu dài, huỷ.
- Đánh giá, bảo đảm chất lượng diễn ra ở **từng giai đoạn**; biện pháp đo thay đổi theo
  giai đoạn.
- CLDL mỗi giai đoạn được ghi nhận, truyền đạt rõ; có thể phải quay lại giai đoạn trước
  để khắc phục.
- **5 nguyên tắc:** cam kết CLDL; hiểu người dùng; đánh giá suốt vòng đời; truyền đạt rõ;
  lường trước thay đổi.

## Kiểm soát chất lượng theo giai đoạn

- Mỗi giai đoạn có rủi ro CLDL và biện pháp kiểm soát riêng; độ đo phù hợp cũng khác nhau.
- **Phát hiện càng sớm, chi phí càng thấp** → đặt kiểm tra ngay tại điểm nạp dữ liệu.

*(hình/bảng trong slide gốc)*

## Chất lượng trong vòng đời dữ liệu lớn

- Quản lý chất lượng ở cả **7 pha:** sinh dữ liệu → truyền → thu thập → tiền xử lý → lưu
  trữ → xử lý, phân tích → trực quan hoá.
- **Hồ sơ chất lượng (Data Quality Profile – DQP):** lưu yêu cầu, thuộc tính, khía cạnh,
  điểm số và quy tắc chất lượng.
- Đánh giá **trước (pre)** và **sau (post)** tiền xử lý trên mẫu dữ liệu để giảm chi phí
  tính toán (Taleb et al., 2021).

## TEMPO-DQ trong pipeline dữ liệu lớn

- Luồng: Nguồn dữ liệu → Nạp → Lưu trữ → Xử lý → Phân tích → Khai thác (Consumption).
- TEMPO-DQ là **lớp CLDL liên tục** bên dưới Lakehouse, vừa "hiểu dữ liệu" vừa "hiểu mô hình".
- Thực tế là **vòng phản hồi** Lưu trữ – Xử lý – Phân tích: phát hiện lỗi → tái tạo, chạy
  lại, kiểm định lại đến khi đạt ngưỡng.

## Lakehouse: Bronze – Silver – Gold

- **Bronze:** dữ liệu thô từ mọi nguồn;
- **Silver:** đã làm sạch, kiểm tra;
- **Gold:** dữ liệu tuyển chọn phục vụ BI/AI.
- Kiểm tra chất lượng tăng dần ở tầng cao; Delta Lake hỗ trợ ràng buộc `NOT NULL`, `CHECK`.
- **Delta Live Tables Expectations:** khi vi phạm thì ghi nhận, `DROP ROW` hoặc
  `FAIL UPDATE`; nhật ký sự kiện → dashboard CLDL.

## Chia tập chống rò rỉ thời gian

- **B1:** chia Train/Val/Test **một lần** theo tỷ lệ `8:1:1`, phân tầng (stratified),
  **trước mọi can thiệp**.
- **B2–B3:** chỉ mô phỏng pha P1–P4 trên Val/Test; mốc pha tính theo tiến trình của từng
  thực thể.
- **B4:** đặc trưng tại pha `p` chỉ tính từ sự kiện có thời điểm `≤` mốc cắt (as-of) →
  pha trước là tiền tố pha sau.
- **B5:** nhãn cố định ở cuối cửa sổ, không tính lại theo pha; CDSMOTE chỉ áp dụng trên Train.

## Giám sát CLDL liên tục & cảnh báo

- Theo dõi chuỗi thời gian độ đo sau mỗi lần nạp (Completeness, Validity, Timeliness) và
  sau mỗi lần huấn luyện (`AccTEMPO_M1`).
- Đặt ngưỡng và mức cảnh báo; gắn với hành động: chặn nạp, xử lý lại, huấn luyện lại.
- TEMPO-DQ tái sử dụng ma trận nhầm lẫn và ma trận xác suất có sẵn → không tăng độ trễ
  suy luận.

## Kiểm soát sớm: quy tắc 1-10-100

- **1 USD** để phòng ngừa lỗi tại nguồn: kiểm tra khi nhập, ràng buộc, quy tắc nghiệp vụ.
- **10 USD** để khắc phục khi lỗi đã vào hệ thống: làm sạch, ETL, đối soát.
- **100 USD** là chi phí thất bại nếu không xử lý: quyết định sai, mất khách hàng, vi
  phạm quy định.
- **Hàm ý:** dịch chuyển kiểm soát CLDL về đầu vòng đời (*shift-left*) (Labovitz & Chang, 1992).

## Kiểm tra nhanh – Phần 3 & 4

1. Nêu 4 hoạt động cốt lõi của quản lý CLDL. "Giám sát dữ liệu" khác "giám sát CLDL" thế nào?
2. Đề tài dự báo doanh thu (hồi quy) từ một bảng giao dịch tĩnh có thuộc vùng áp dụng của
   TEMPO-DQ không? Vì sao?
3. Trong Lakehouse, quy tắc "tuổi ∈ `[18; 100]`" nên đặt ở tầng nào? Chọn `DROP ROW` hay
   `FAIL UPDATE`?
4. Vì sao chỉ được áp dụng CDSMOTE (hoặc SMOTE) trên tập Train?

---

# PHẦN 5 — Phân tích các vấn đề tồn tại và xu hướng tiềm năng

- Vấn đề tồn tại về đo lường, công cụ và dữ liệu lớn cho AI.
- Rò rỉ lối tắt, mất cân bằng, trôi phân phối trong thực tế.
- Bốn xu hướng: data-centric AI, data observability, LLM và dữ liệu tổng hợp, quản trị – tuân thủ.

> **Câu hỏi trọng tâm:** CLDL còn những thách thức nào và đang phát triển theo hướng nào?

## Vấn đề tồn tại: đo lường & công cụ

- Chưa đồng thuận về danh sách khía cạnh và công thức độ đo chuẩn.
- Độ đo cục bộ theo từng cấu hình thiếu ổn định: Acc-DQ dao động trung bình `0,2121` trên
  cùng một phiên bản dữ liệu.
- Công cụ chưa cài đặt đủ độ đo khoa học; nhiều độ đo cần "chuẩn vàng" không có sẵn; giám
  sát thường trả phí.
- **66% doanh nghiệp** (khảo sát tại Đức) vẫn kiểm tra CLDL bằng Excel/Access
  (Schäffer & Beckmann, 2014).

## Vấn đề tồn tại: dữ liệu lớn & AI

- 18 nghiên cứu dự đoán sớm (2020–2025): **94,4%** có thu thập dữ liệu (R1) nhưng chỉ
  **44,4%** có khung CLDL (R4); **33,3%** đo CLDL tự động.
- Dữ liệu phi cấu trúc chỉ có ở **38,9%** nghiên cứu → nút thắt của tự động hoá.
- "Đứt gãy" giữa nhóm mạnh về mô hình (giáo dục) và nhóm mạnh về quản trị CLDL (y tế).
- Mất cân bằng cực đoan (99,64% một lớp), nhiễu nhãn, trôi phân phối theo pha và theo nhóm.

## Ví dụ: rò rỉ lối tắt từ dữ liệu thiếu

- `sleak = 1 − AUCprobe`: huấn luyện hồi quy logistic chỉ trên chỉ báo thiếu;
  `sleak = 0,5` là không có lối tắt.
- **Kết quả học tập:** dữ liệu thô AUC ≈ `0,87` → sau điền khuyết AUC = `0,50` → lối tắt
  bị loại bỏ.
- **Chất lượng khoá học:** AUC ≈ `0,68` vẫn còn sau điền khuyết → bản thân mẫu thiếu mang
  thông tin nhãn.
- **Hành động:** không đưa chỉ báo thiếu vào tập đặc trưng; kiểm toán rò rỉ ở mức cấu hình.

## Xu hướng 1: Data-Centric AI

- Chuyển trọng tâm từ cải tiến mô hình sang cải thiện dữ liệu có hệ thống
  (Zha et al., 2023; Whang et al., 2023).
- CLDL gắn với mục đích và mô hình (*fit-for-purpose, model-aware*) thay cho kiểm tra bề mặt.
- Tự động hoá vòng **đo lường → can thiệp → đo lại** trong MLOps; CLDL là **cổng chất
  lượng** (quality gate) trước triển khai.

## Xu hướng 2: Data Observability

- **Khả năng quan sát dữ liệu** (data observability): 5 trụ cột – độ tươi, phân phối, khối
  lượng, lược đồ, dòng dõi (Moses, 2020).
- **Hợp đồng dữ liệu** (data contract): thoả thuận lược đồ, ngữ nghĩa và ngưỡng CLDL giữa
  bên tạo và bên dùng dữ liệu.
- **DataOps:** kiểm tra CLDL viết như mã (expectations, dbt tests), chạy trong CI/CD của
  pipeline.

## Xu hướng 3: LLM & dữ liệu tổng hợp

- Mô hình nền tảng/LLM hỗ trợ phát hiện lỗi, điền khuyết, đối sánh thực thể
  (Narayan et al., 2022).
- LLM làm bộ trích xuất đặc trưng phụ trợ cho dữ liệu phi cấu trúc (embedding văn bản) rồi
  hợp nhất với đặc trưng có cấu trúc.
- Dữ liệu tổng hợp và tăng cường (GAN, CTGAN, tăng cường chuỗi thời gian) cho lớp thiểu số.
- **Cần kiểm soát:** rò rỉ thông tin, chi phí, "ảo giác", khả năng so sánh giữa các pha.

## Xu hướng 4: Quản trị & tuân thủ

- **EU AI Act – Điều 10:** dữ liệu huấn luyện, kiểm định, kiểm thử của AI rủi ro cao phải
  phù hợp, đủ đại diện, không lỗi và đầy đủ ở mức tốt nhất có thể.
- **Luật Dữ liệu 2024** (số 60/2024/QH15, hiệu lực 01/7/2025) quy định bảo đảm chất lượng
  dữ liệu (Điều 12).
- **Gartner (2025):** 63% tổ chức chưa có hoặc không chắc có thực hành quản lý dữ liệu phù
  hợp cho AI.
- CLDL trở thành **yêu cầu pháp lý và năng lực cạnh tranh**, không chỉ là vấn đề kỹ thuật.

---

# PHẦN 6 — Tổng kết và định hướng đồ án

- Tóm tắt kiến thức trọng tâm của chương 4.
- Phân loại đồ án môn học: Cơ bản và Nâng cao.
- Gợi ý phương pháp, đăng ký đề tài và bài tập về nhà.

> **Câu hỏi trọng tâm:** Vận dụng kiến thức chương 4 vào đồ án môn học như thế nào?

## Tổng kết Chương 4

- CLDL = mức độ phù hợp mục đích; đo bằng **khía cạnh → độ đo** ở nhiều mức tổng hợp.
- Độ đo truyền thống cần nhưng chưa đủ; AccTEMPO bổ sung góc nhìn **thời gian – hội đồng
  mô hình – chẩn đoán 3 cấp**.
- Chọn khung, phương pháp theo bối cảnh dữ liệu, hệ thống, nghiệp vụ; **luôn đo lại sau
  can thiệp**.
- Quản lý chất lượng **suốt vòng đời**: kiểm soát sớm, giám sát liên tục, tuân thủ quy định.

## Vận dụng: phân loại đồ án môn học

- Mỗi nhóm chọn **1 trong 2 loại** đồ án khi đăng ký đề tài.
- **Cơ bản:** xây dựng ứng dụng BI giám sát và cải thiện CLDL đầu vào cho bài toán của đề tài.
- **Nâng cao:** đáp ứng toàn bộ yêu cầu Cơ bản và phát triển cải tiến mới theo 1 trong 3
  hướng.
- **Đánh giá A4 (50%):** báo cáo 30% – thuyết trình 20% – demo chương trình 50%.

## Đồ án Cơ bản: ứng dụng BI về CLDL

- Tập trung giám sát dữ liệu **đầu vào (input)** của bài toán.
- Đo lường và giám sát độ đo CLDL: **6 khía cạnh cốt lõi**, khuyến khích bổ sung AccTEMPO.
- Áp dụng phương pháp cải thiện CLDL cơ bản: điền khuyết, tăng cường, làm giàu dữ liệu.
- Áp dụng các phương pháp **SOTA** trong tài liệu tham khảo.

## Gợi ý phương pháp cho đồ án

- Ưu tiên phương pháp có trích dẫn trong tài liệu tham khảo; **luôn so sánh với baseline
  đơn giản**.
- Mọi phương pháp cải thiện phải được **đo lại (trước/sau)** bằng cùng bộ độ đo; fit bộ
  điền khuyết, tăng cường **chỉ trên Train**.

## Đồ án Nâng cao: 3 hướng cải tiến

- **Hướng 1 – CLDL nâng cao:** đề xuất phương pháp cải thiện CLDL mới và triển khai chức
  năng demo cho output bài toán.
- **Hướng 2 – ML/DL:** nghiên cứu cải tiến phương pháp học máy, học sâu và triển khai chức
  năng demo cho output.
- **Hướng 3 – Dữ liệu lớn:** triển khai thực nghiệm trên kiến trúc dữ liệu lớn, đáp ứng
  yêu cầu nghiệp vụ doanh nghiệp.

## Đăng ký đề tài & bài tập về nhà

**Đăng ký đề tài** (post "Đăng ký đề tài" trên Teams):

- I. Tên nhóm; II. Tên đề tài; III. Lĩnh vực ứng dụng; IV. Tài sản dữ liệu (dataset,
  nguồn cung cấp, link); V. Phân loại đồ án.

**Bài tập về nhà – Đo lường và giám sát độ đo CLDL:**

- Lập **từ điển dữ liệu** và **quy tắc kiểm tra**;
- Tính **6 khía cạnh ở mức hạt**;
- **Trực quan hoá theo thời gian**;
- Áp dụng **ít nhất 1 phương pháp cải thiện** và so sánh trước/sau;
- Đọc trước **Chương 5:** Phân tích dữ liệu cho doanh nghiệp (kiến trúc BI).

---

## Tài liệu tham khảo

1. Nguyen, T., Nguyen, H.-T., & Nguyen-Hoang, T.-A. (2027). *TEMPO-DQ framework: A
   Temporal-Ensemble, multi-phase operational data quality approach for early multi-class
   prediction under heterogeneous big data.* Information Processing & Management, 64,
   105175. **(Tài liệu chính)**
2. Nguyen, T., Nguyen, H.-T., & Nguyen-Hoang, T.-A. (2025). *Data quality management in
   big data: Strategies, tools, and educational implications.* Journal of Parallel and
   Distributed Computing, 200, 105067.
3. Nguyen-Pham, H.-D., Vo, K. T., Nguyen, T., et al. (2024). *Data quality management for
   real-world graduation prediction.*
4. L'Esteve, R. (2022). *The Azure Data Lakehouse Toolkit.* Apress.
5. Ehrlinger, L., & Wöß, W. (2022). *A survey of data quality measurement and monitoring
   tools.* Frontiers in Big Data, 5, 850611.
6. Taleb, I., Serhani, M. A., Bouhaddioui, C., & Dssouli, R. (2021). *Big data quality
   framework: A holistic approach to continuous quality management.* Journal of Big Data, 8, 76.
7. Schwabe, D., Becker, K., Seyferth, M., Klaß, A., & Schaeffter, T. (2024). *The
   METRIC-framework for assessing data quality for trustworthy AI in medicine.* npj
   Digital Medicine, 7, 203.
8. Wang, R. Y., & Strong, D. M. (1996). *Beyond accuracy: What data quality means to data
   consumers.* Journal of Management Information Systems, 12(4), 5–33.
9. Pipino, L. L., Lee, Y. W., & Wang, R. Y. (2002). *Data quality assessment.*
   Communications of the ACM, 45(4), 211–218.
10. ISO/IEC 25012:2008. *Software engineering – SQuaRE – Data quality model*; UK Government
    Data Quality Hub (2020). *The Government Data Quality Framework.*
11. Quốc hội (2024). *Luật Dữ liệu số 60/2024/QH15*; Regulation (EU) 2024/1689 (AI Act),
    Article 10.
12. Narayan, A., Chami, I., Orr, L., Arora, S., & Ré, C. (2022). *Can foundation models
    wrangle your data?* PVLDB, 16(4), 738–746; Whang, S. E., et al. (2023). The VLDB
    Journal, 32(4), 791–813.
13. Gartner (2020, 2025). *Data quality*; *Lack of AI-ready data puts AI projects at
    risk.* Moses, B. (2020). *The five pillars of data observability.*
14. Elyan, E., et al. (2021). *CDSMOTE: Class decomposition and synthetic minority class
    oversampling technique for imbalanced-data classification.* Neural Computing and
    Applications, 33(7), 2839–2851.
15. Geirhos, R., et al. (2020). *Shortcut learning in deep neural networks.* Nat. Mach.
    Intell., 2(11), 665–673.
16. Zha, D., et al. (2023). *Data-centric AI: Perspectives and challenges.* Proc. SIAM
    International Conference on Data Mining (SDM), 945–948.
17. Rubin, D. B. (1976). *Inference and missing data.* Biometrika, 63(3), 581–592.
18. Solís-Martín, D., et al. (2026). *D3A-TS: Denoising-driven data augmentation in time
    series.* Int. J. of Data Science and Analytics, 22(1), 48.
19. Makarov, A., & Namiot, D. (2023). *Overview of data cleaning methods for machine
    learning.* Int. J. of Open Information Technologies, 11(10), 70–78.
20. DAMA UK (2013). *The six primary dimensions for data quality assessment.* Schäffer, T.,
    & Beckmann, H. (2014). *Trendstudie Stammdatenqualität 2013.* Labovitz, G., & Chang, Y.
    S. (1992): quy tắc 1-10-100.

---

## Câu hỏi & Thảo luận

**Câu hỏi gợi mở:**

- Dữ liệu trong đồ án của nhóm đang gặp vấn đề chất lượng nào nghiêm trọng nhất? Đo bằng
  độ đo gì?
- Khi các độ đo truyền thống đều đạt 1,0, nhóm dùng bằng chứng nào để chứng minh dữ liệu
  "phù hợp mục đích"?
- Doanh nghiệp nên ưu tiên đầu tư phòng ngừa hay khắc phục lỗi dữ liệu? Vì sao?

**Nhắc việc sau buổi học:**

- Đăng ký đề tài và loại đồ án (Cơ bản / Nâng cao) trên Teams.
- Làm bài tập "Đo lường và giám sát độ đo CLDL"; đọc trước Chương 5.

**Liên hệ:** ThS. Nguyễn Thị Anh Thư – thunta@uit.edu.vn
