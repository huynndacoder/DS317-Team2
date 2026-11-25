# Bắt đầu từ đây — hướng dẫn cho các thành viên

Cập nhật: 25/11/2026.

## Đồ án đang làm gì?

Khi một khoản vay mua nhà mới bắt đầu, ta chỉ biết hồ sơ lúc cấp vay. Ta muốn dự đoán: **trong 12 tháng từ tháng trả góp đầu tiên, khoản vay có quá hạn từ 90 ngày trở lên hoặc chuyển sang REO hay không?** REO là trạng thái bất động sản đã thuộc quyền sở hữu của bên cho vay sau xử lý.

Đồ án tập trung vào khoản vay **mua nhà (Purchase)**. Câu hỏi nghiên cứu chính là: **dùng lịch sử huấn luyện dài bao nhiêu năm thì dự đoán tốt hơn trên dữ liệu tương lai?**

Phần chuẩn bị dữ liệu đã xong và đã có hai mô hình chạy thử: Logistic Regression (LR) và XGBoost. Team bắt đầu từ dữ liệu đã bàn giao để phân tích, thiết kế thí nghiệm và xây dựng demo.

## Buổi đầu tiên: làm theo 4 bước

1. Đọc phần phân công bên dưới để biết mình cần trả lời câu hỏi nào.
2. Lấy code từ [GitHub](https://github.com/huynndacoder/DS317-Team2). Nếu đã clone, chạy `git status` rồi `git pull --ff-only` khi working tree sạch.
3. Tải đúng gói trong [Drive nhóm](https://drive.google.com/drive/folders/1xoLgyWRgFcv0Si5hqbS_7K6TfgPRG6rK), đặt vào vị trí trong bảng sau. GitHub chứa code và tài liệu; dữ liệu, model và predictions nhận qua Drive.
4. Mở một file, kiểm tra schema/số dòng bằng DuckDB hoặc đọc một mẫu nhỏ. Sau đó làm **việc đầu tiên** trong phân công của mình. Không cần dựng lại dữ liệu để bắt đầu.

Nếu chưa có môi trường Python, làm mục 1 trong [hướng dẫn chạy](reproducibility.md). Nếu thiếu dữ liệu hoặc thấy dữ liệu sai, gửi Sy đường dẫn file và ví dụ cụ thể.

## Tải gì từ Drive?

| Bạn đang làm | Tải trong Drive | Đặt tại repo | Dung lượng gần đúng |
| --- | --- | --- | ---: |
| EDA, mô hình, cửa sổ huấn luyện | `01_DU_LIEU_ML/research` — tải cả thư mục | `output/research/` | 319 MiB |
| Đọc kết quả baseline hoặc làm demo | `03_BASELINE_LR_XGBOOST/run` và `report` | `output/baseline/run/` và `output/baseline/report/` | 40 MiB |
| Kiểm tra chất lượng dữ liệu nguồn | `02_DU_LIEU_GOC_VA_NHAN`: orig, labels, label_tables, schema | `parquet/orig/`, `output/labels/`, `output/label_tables/`, `output/schema/` | 724 MiB |
| Đọc kết quả bài tập trên lớp | `05_BAI_TAP_TREN_LOP/classwork` | `output/classwork/` | 3 MiB |

**Phân chia trách nhiệm:** Sy giữ phần dữ liệu gốc, tạo nhãn và dựng dữ liệu bàn giao. Teammate làm trên các gói output. Nhân có thể đọc thêm origination để đo DQ; nếu cần thay đổi dữ liệu chuẩn, thống nhất với Sy trước.

Không cần tải 2,89 tỷ dòng performance cho công việc EDA/model thông thường. Nếu cần thống kê từ nguồn chưa có trong gói bàn giao, nhờ Sy xuất bảng tổng hợp.

## Bốn file trong research dùng để làm gì?

Đây là dữ liệu của **16.641.482 khoản vay đủ điều kiện**, mỗi khoản một dòng trong features, target và split.

| File | Hiểu đơn giản | Cách dùng |
| --- | --- | --- |
| `features.parquet` | Hồ sơ đầu vào của khoản vay | Chỉ lấy 18 biến dự đoán theo [data contract](data-contract.md); không đưa ID hoặc cột truy vết vào model |
| `target.parquet` | Đáp án đã xác định từ lịch sử trả nợ | `label_12m=1` là có sự kiện; `0` là không có theo quy tắc nhãn |
| `split.parquet` | Khoản vay thuộc quý nào, các mốc thời gian | Dùng để phân tích theo quý và kiểm tra thời điểm |
| `membership.parquet` | Danh sách khoản vay thuộc từng tập của pilot | Chọn role trước, rồi nối các file bằng `loan_id` |

Một khoản có thể xuất hiện ở nhiều role vì pilot có hai giai đoạn huấn luyện. Điều này đã được thiết kế; **không xóa các dòng overlap**. Nối dữ liệu phải giữ đúng một dòng cho mỗi khoản trong tập đang dùng.

Membership chỉ mô tả pilot hiện có, không bao phủ toàn bộ research. Khi tạo cửa sổ mới, phải tạo membership mới từ dữ liệu đầy đủ và điều kiện thời gian. Không dùng cột `split` để loại toàn bộ các dòng ghi `embargoed`.

## Baseline hiện có là gì?

Pilot là lần chạy thử để kiểm tra toàn bộ đường đi từ dữ liệu đến dự đoán và đo lường. Đây chưa phải kết quả cuối của đồ án, cũng chưa phải tái lập một paper.

| Giai đoạn | Dữ liệu học | Đánh giá |
| --- | --- | --- |
| A — chuẩn bị/chọn cấu hình | `train_tune`: 2009–2013, 1.863.476 khoản | `validation`: 2016, 710.554 khoản |
| B — huấn luyện lại để kiểm tra tương lai | `train_refit`: 2012–2016, 2.688.363 khoản | `development_test`: 2019, 933.708 khoản |

Như vậy, **model Stage B được học trên 5 năm 2012–2016**. Năm 2019 dùng để kiểm tra khả năng dự đoán sang tương lai; năm 2024 được giữ riêng, chưa chấm điểm.

Các bước điền thiếu, mã hóa và chuẩn hóa học từ tập train của từng giai đoạn. Khi chuyển sang Stage B, các bước này được fit mới. Một khoản chỉ được dùng để train khi cửa sổ nhãn đã kết thúc và cộng thêm độ trễ giả định 3 tháng.

Đọc kết quả hiện hành ở `output/baseline/report/REPORT.md`, hoặc bản tóm tắt [reports/baseline.md](../reports/baseline.md). Thư mục `run/` giữ model, preprocessing và predictions gốc; các báo cáo bên trong `run/` là bản lịch sử.

## Huy — hiểu dữ liệu trước khi so mô hình

**Cần nhận:** research. Đọc [kế hoạch EDA](eda-plan.md).

**Việc đầu tiên:** lập bảng theo từng quý gồm số khoản và tỷ lệ nhãn 1; kiểm tra các tập pilot có đúng số dòng trong bảng trên.

Sau đó:
1. Mô tả phân bố, giá trị thiếu và mã đặc biệt của 18 biến.
2. So sánh train 2012–2016 với development test 2019: biến nào thay đổi, thay đổi ở quý nào?
3. Ghi các phát hiện ảnh hưởng đến thí nghiệm. Nhờ Sy bổ sung số liệu tổng hợp nếu cần biết vì sao các khoản bị loại trước khi vào research.

**Nộp:** code/notebook chạy lại được, CSV thống kê, hình có nhãn rõ ràng và báo cáo ngắn nêu 3–5 phát hiện. Đạt khi số dòng khớp, phạm vi dữ liệu rõ và mọi hình có kết luận đi kèm.

## Nhân — đo chất lượng dữ liệu và đề xuất cách xử lý

**Cần nhận:** research; nhận thêm gói orig/labels/label_tables/schema khi cần đo nguồn.

**Việc đầu tiên:** viết bảng quy tắc cho 6 khía cạnh: đo trên cột nào, thế nào là đạt, mẫu số là gì, có đo trực tiếp được không.

Sau đó:
1. Tính cờ lỗi ở mức giá trị/dòng; tổng hợp theo cột, bảng và quý.
2. Ghi Accuracy và Timeliness là N/A nếu thiếu dữ liệu chuẩn hoặc timestamp cần thiết. Nếu dùng proxy, ghi rõ giới hạn.
3. Chọn 1–2 vấn đề thực sự có trong dữ liệu và đề xuất can thiệp. Cùng Sy chốt phần nào sửa ở dữ liệu nguồn, phần nào là preprocessing của model.
4. Đo trước/sau trên cùng phạm vi; ghi cả số dòng bị loại nếu có. Mọi thống kê học từ dữ liệu để phục vụ model chỉ được fit trên train.

**Nộp:** rule table, bảng độ đo trước/sau, biểu đồ theo quý và giải thích lựa chọn. Đạt khi truy được từ tỷ lệ tổng hợp về quy tắc và mẫu số; không hứa đo được cả 6 khi thiếu bằng chứng.

## Hiển — xây thí nghiệm so cửa sổ huấn luyện

**Cần nhận:** research và baseline.

**Việc đầu tiên:** đọc membership và xác nhận tập train 2012–2016 có 2.688.363 khoản, tập test 2019 có 933.708 khoản. Kiểm tra cách tính capture@5% theo từng quý từ kết quả đã lưu.

Sau đó:
1. Cùng Sy viết `docs/research_protocol.md` trước khi chạy batch: ngày fit, cửa sổ train, tập validation, cách chọn tham số, độ trễ nhãn và các độ đo.
2. Tạo runner/config mới cho cửa sổ 3 năm (2014–2016), 5 năm (2012–2016), 10 năm (2007–2016), expanding (1999–2016). Đây là khoảng quý ứng viên; vẫn phải lọc điều kiện nhãn đã sẵn sàng.
3. Giữ cùng tập test 2019 và cách đánh giá; fit preprocessing riêng trên train của mỗi cấu hình. Giữ mô hình, đặc trưng và ngân sách tuning nhất quán để so tác động của cửa sổ.
4. Khi quy trình đã ổn, mở rộng sang các mốc kiểm tra tương lai khác theo protocol.

**Nộp:** membership/config của từng thí nghiệm, model + preprocessing, predictions, metrics chung và theo quý, thời gian/RAM. Đạt khi truy được mỗi kết quả về đúng tập train và có lệnh chạy lại.

Trainer hiện tại là pilot cố định; chỉ đổi YAML chưa đủ để chạy nhiều cửa sổ. Giữ nguyên `configs/baseline.yaml` và source baseline đã đóng gói.

## Ys — chốt paper và đề xuất cải tiến

**Cần nhận:** data contract, báo cáo baseline; không cần tải dữ liệu gốc để bắt đầu.

**Việc đầu tiên:** lập bảng so sánh 2–3 paper: nơi công bố, bằng chứng uy tín/rank, đầu vào, định nghĩa nhãn, thời hạn dự đoán, cách chia thời gian, code và mức phù hợp.

Sau đó:
1. Chọn ứng viên có thể tái lập trong phạm vi hiện tại; ghi rõ khác biệt với đồ án. Bài về dữ liệu hoặc cửa sổ thời gian có thể làm tài liệu hỗ trợ, chưa chắc là baseline thuật toán.
2. Cùng Sy xác nhận tiêu chí nơi công bố của cô trước khi chốt.
3. Đề xuất một cải tiến cụ thể và ablation: giữ nguyên gì, thay đổi gì, so với mốc nào, đo lợi ích thế nào.

**Nộp:** bảng paper có link/DOI, đề xuất baseline và bản mô tả cải tiến đủ để Hiển triển khai. Đạt khi phân biệt rõ “tham khảo”, “tái lập phương pháp” và “đã chạy thực nghiệm”. Hiện nhóm chưa chốt paper baseline.

## Hiền — dựng demo từ model đã lưu

**Cần nhận:** baseline và research nếu cần lấy ví dụ minh họa.

**Việc đầu tiên:** đọc `report/REPORT.md`, tìm bundle Stage B của LR/XGBoost trong `run/models/`, xác định schema 18 biến đầu vào.

Sau đó:
1. Dùng preprocessing và model trong cùng bundle để dự đoán; không tự fit lại trên dữ liệu nhập của người dùng.
2. Hiển thị xác suất rủi ro, thông tin model và kết quả kiểm tra năm 2019. Kiểm tra đầu vào thiếu/sai miền.
3. Chạy thử với các ví dụ từ dữ liệu development, đối chiếu điểm dự đoán với predictions đã lưu.
4. Ghi rõ đây là demo trên dữ liệu Freddie Mac của Mỹ; xác suất chưa được khẳng định hiệu chuẩn cho người vay tại Việt Nam.

**Nộp:** app, hướng dẫn chạy, ví dụ đầu vào và kết quả đối chiếu. Đạt khi cùng một ví dụ cho điểm khớp với saved model và người xem hiểu giới hạn sử dụng.

## Thứ tự phối hợp

Huy, Nhân, Ys và Hiền có thể bắt đầu song song. Hiển bắt đầu kiểm tra membership/evaluator, rồi cùng Sy chốt protocol trước khi chạy thí nghiệm lớn. Huy và Nhân gửi phát hiện dữ liệu sớm để Hiển đưa vào thiết kế.

Thứ tự thực nghiệm: **Raw với các cửa sổ train → chọn thiết kế đã thống nhất → kiểm tra cải tiến/làm giàu**. Không đổi cửa sổ và thêm đặc trưng cùng lúc rồi quy toàn bộ chênh lệch cho một yếu tố.

Sy giữ dữ liệu chuẩn, review protocol, tích hợp kết quả và quyết định thời điểm mở holdout 2024. Không dùng holdout để chọn model hoặc tham số.

## Mỗi người bàn giao như thế nào?

Tạo nhánh riêng. Code/notebook và báo cáo tổng hợp đưa lên GitHub; dữ liệu mức khoản vay, predictions, model và file lớn đưa lên Drive nhóm.

Kết quả chạy mới đặt dưới `output/experiments/<ten-task>/<run_id>/`, ví dụ `output/experiments/eda/20261125_01/`. Đây là quy ước cho công việc tiếp theo; không phải các kết quả đã tồn tại. Giữ nguyên `output/research/` và `output/baseline/`.

Trong mỗi gói kết quả có một README ngắn:
- Câu hỏi đang trả lời và dữ liệu/tập/quý đã dùng.
- Lệnh chạy, phiên bản code và số dòng đầu vào/đầu ra.
- File nào là bảng kết quả chính, file nào là hình hoặc bằng chứng kiểm tra.
- 3–5 nhận xét, giới hạn còn lại và việc cần người khác review.

Không đưa loan_id, dữ liệu mức khoản vay hoặc model lên GitHub public. Tránh `git add .`; chọn rõ file cần commit.

## Bài tập trên lớp nằm ở đâu trong kế hoạch?

`output/classwork/` đang có kết quả mẫu: 8.000 khoản train và 4.000 khoản development 2019, gồm DQ, clustering, outlier và drift. Có kết quả mẫu không đồng nghĩa đã hoàn tất EDA toàn bộ dữ liệu.

Bài làm giàu Chương 8 + 10 còn cần sửa chẩn đoán clustering, bổ sung chuỗi thời gian/hồi quy và so classifier **Raw với Raw + đặc trưng làm giàu**. Chi tiết ở phần bài tập của [kế hoạch EDA](eda-plan.md). Không dùng kết quả mẫu để khẳng định làm giàu đã tăng chất lượng dự đoán.
