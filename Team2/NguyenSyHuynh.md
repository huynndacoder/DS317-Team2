# Tổng Quan Nghiên Cứu: Deep Learning và AI trong Phân Tích Kinh Doanh & Kinh Tế

## Giới Thiệu
Tài liệu này tóm tắt bảy bài nghiên cứu về ứng dụng deep learning, machine learning và trí tuệ nhân tạo trong phân tích kinh doanh, kinh tế và kỹ thuật phần mềm.

---

## 1. JEL: Ứng Dụng Neural Entity Linking End-to-End tại JPMorgan Chase
**Nguồn:** 00021-IAAI21.DingW-EM.pdf  
**Hội nghị:** AAAI-21 (Hội nghị Trí tuệ Nhân tạo AAAI lần thứ 35)  
**Tác giả:** Wanying Ding, Vinay K. Chaudhri, Naren Chittar, Krishna Konakanchi (JPMorgan Chase & Co.)

### Đóng Góp Chính
- **Vấn đề mới:** Phát triển JEL (JPMorgan Entity Linking), mô hình liên kết thực thể neural end-to-end để liên kết tên công ty trong tin tức tài chính với các thực thể trong knowledge graph nội bộ
- **Đổi mới:** Không phụ thuộc vào Wikipedia để tạo entity embeddings, sử dụng thông tin ngữ cảnh tối thiểu với hàm margin loss
- **Kiến trúc:** Sử dụng mô hình Wide & Deep Learning để khớp thông tin ký tự và ngữ nghĩa

### Thách Thức Chính
1. Wikipedia không bao phủ tất cả các thực thể tài chính quan trọng (ví dụ: startup chưa có trên Wikipedia)
2. Thiếu thông tin ngữ cảnh phong phú so với các dataset công khai như CoNLL, TAC KBP, DBpedia
3. Cần liên kết thực thể trong knowledge graph đặc thù doanh nghiệp

### Phương Pháp
- **Nhận dạng:** Sử dụng spaCy để nhận dạng mention
- **Liên kết:** Phân loại nhị phân với margin loss cho entity embeddings
- **Khớp chuỗi:** N-gram cosine similarity hoạt động tốt nhất trong các phương pháp (Jaccard, Levenshtein, Jaro Winkler)

### Ứng Dụng
- Quản lý rủi ro
- Phát hiện gian lận
- Tư vấn đầu tư
- Tạo cảnh báo cho các nhà phân tích tài chính dựa trên tin tức

---

## 2. Deep Learning trong Kinh Tế: Đánh Giá Hệ Thống và Phê Phán
**Nguồn:** 10462_2022_Article_10272.pdf  
**Tạp chí:** Artificial Intelligence Review  
**Tác giả:** Yuanhang Zheng, Zeshui Xu, Anran Xiao  
**Năm:** 2022

### Phát Hiện Chính
- **Xu hướng tăng trưởng:** Deep learning trong kinh tế bắt đầu năm 2014, số lượng bài báo tăng trung bình 222,4% mỗi năm
- **Số lượng xuất bản:** 631 bài báo được xuất bản chỉ riêng năm 2021
- **Cơ sở dữ liệu:** Phân tích các bài báo từ Web of Science, Scopus và DBLP (tổng 1.414 bài sau khi lọc)

### Tiến Hóa của Phương Pháp Kinh Tế
1. **Trước 1790:** Phân tích lịch sử và thống kê
2. **Giữa thế kỷ 17-19:** Kinh tế học cổ điển với lập luận suy diễn
3. **Cuối thế kỷ 19-đầu 20:** Trường phái tân cổ điển với phương pháp tĩnh và cân bằng tổng quát
4. **1930-1960:** Kinh tế học Keynes, chủ nghĩa thực chứng vs. chủ nghĩa phản chứng
5. **Sau 1960:** Kinh tế lượng thống trị với chủ nghĩa thực chứng
6. **Thời đại hiện đại:** Deep learning cho ra quyết định thông minh

### Các Mô Hình Deep Learning trong Kinh Tế
- **Deep Neural Networks (DNN)** - Mạng Neural Sâu
- **Restricted Boltzmann Machine (RBM)** - Máy Boltzmann Hạn Chế
- **Deep Belief Networks (DBN)** - Mạng Niềm Tin Sâu
- **Convolutional Neural Networks (CNN)** - Mạng Neural Tích Chập
- **Recurrent Neural Networks (RNN)** - Mạng Neural Hồi Quy
- **Autoencoders (AE)** - Bộ Tự Mã Hóa
- **Transformers** - Bộ Biến Đổi
- **Deep Reinforcement Learning (DRL)** - Học Tăng Cường Sâu

### Ứng Dụng theo Lĩnh Vực Kinh Tế
- Kinh tế tài chính
- Kinh tế vĩ mô và tiền tệ
- Kinh tế nông nghiệp và tài nguyên thiên nhiên
- Tổ chức công nghiệp
- Kinh tế đô thị, nông thôn, khu vực, bất động sản và vận tải
- Y tế, giáo dục và phúc lợi
- Quản trị kinh doanh và kinh tế vi mô

### Nhận Xét Phê Phán
- Deep learning xử lý dữ liệu lớn, nhiều chiều tốt hơn machine learning truyền thống
- Ngăn chặn overfitting tốt hơn các thuật toán truyền thống
- Có thể mô hình hóa các mối quan hệ phi tuyến phức tạp trong dữ liệu kinh tế
- Hiệu suất cải thiện khi lượng dữ liệu tăng

---

## 3. Deep Learning trong Phân Tích Kinh Doanh và Nghiên Cứu Vận Hành
**Nguồn:** 1-s2.0-S0377221719307581-main.pdf  
**Tạp chí:** European Journal of Operational Research  
**Tác giả:** Mathias Kraus, Stefan Feuerriegel, Asil Oztekin  
**Năm:** 2020

### Mục Tiêu Chính
1. Đánh giá nghiên cứu về deep learning cho phân tích kinh doanh từ góc độ vận hành
2. Thúc đẩy các nhà nghiên cứu sử dụng deep neural networks
3. Điều tra giá trị gia tăng trong các case study với dữ liệu doanh nghiệp thực
4. Cung cấp hướng dẫn cho các nhà nghiên cứu, quản lý và thực hành

### Lợi Thế Chính của Deep Learning
- **Khả năng mở rộng:** Có thể xử lý big data khi ML truyền thống không thể
- **Hiệu suất:** Cải thiện hiệu suất vận hành so với ML truyền thống
- **Tính linh hoạt:** Mô hình hóa các mối quan hệ phi tuyến rất phức tạp

### Ứng Dụng Đột Phá Nổi Bật
- **Nhận dạng giọng nói:** Hệ thống của Microsoft phiên âm chính xác như con người được đào tạo
- **Dịch thuật:** Hệ thống của Google tiếp cận hiệu suất con người
- **Thị giác máy tính:** Nhận dạng khuôn mặt để thanh toán (Alipay - 120 triệu người dùng ở Trung Quốc)
- **Hệ thống gợi ý:** Amazon và Netflix sử dụng DNN để cá nhân hóa

### Tại Sao Deep Learning Bây Giờ?
1. **Sức mạnh tính toán:** GPU tăng tốc làm cho việc huấn luyện khả thi (ví dụ: Google DeepMind sử dụng 176 GPU trong 40 ngày cho AlphaGo)
2. **Sẵn có dữ liệu:** Cần dataset lớn để ngăn overfitting và tinh chỉnh tham số
3. **Tối ưu hóa tốt hơn:** Các thủ tục tối ưu hiện đại mở rộng hiệu quả

### Ứng Dụng trong Vận Hành
- Quản lý chuỗi cung ứng
- Mô hình hóa rủi ro
- Thương mại điện tử
- Bảo trì phòng ngừa
- Sản xuất

### Phát Hiện Quan Trọng
- **Kiến trúc mặc định thường không tối ưu** - nhấn mạnh giá trị của kiến trúc tùy chỉnh
- Đề xuất kiến trúc "deep-embedded network" mới

---

## 4. Deep Learning trong Phân Tích Kinh Doanh: Xung Đột Giữa Kỳ Vọng và Thực Tế
**Nguồn:** 1-s2.0-S2667096822000891-main.pdf  
**Tạp chí:** International Journal of Information Management Data Insights  
**Tác giả:** Marc Schmitt  
**Năm:** 2023

### Luận Điểm Chính
Mặc dù phổ biến, deep learning gặp khó khăn trong việc được áp dụng rộng rãi trong ngành cho phân tích kinh doanh.

### Hạn Chế Chính Được Xác Định
1. **Độ phức tạp tính toán**
2. **Thiếu kiến trúc big data**
3. **Thiếu tính minh bạch (vấn đề black-box)**
4. **Thiếu kỹ năng**
5. **Vấn đề cam kết lãnh đạo**

### Phát Hiện Quan Trọng
**Deep learning KHÔNG vượt trội hơn các mô hình ML truyền thống đối với dataset có cấu trúc với vector đặc trưng có độ dài cố định**

### Khuyến Nghị Thực Tiễn
- **Gradient boosting là mô hình lựa chọn hàng đầu cho dự đoán trên dataset có cấu trúc** trong phân tích kinh doanh
- Deep learning nên được xem như một bổ sung mạnh mẽ cho các mô hình ML hiện có, không phải giải pháp "một kích cỡ phù hợp tất cả"

### Case Study Ngành
- Nghiên cứu dựa trên ba case study công nghiệp thực tế
- Bằng chứng thực nghiệm cho thấy ML truyền thống có thể bằng hoặc vượt hiệu suất DL trên dữ liệu có cấu trúc

### Hàm Ý
- Các tổ chức không nên áp dụng DL một cách mù quáng mà không hiểu đặc điểm dữ liệu
- Dữ liệu kinh doanh có cấu trúc (phổ biến nhất trong phân tích) có thể không hưởng lợi từ DL
- Phân bổ nguồn lực nên xem xét lợi ích hiệu suất thực tế so với chi phí triển khai

---

## 5. Đánh Giá Toàn Diện về Phương Pháp Deep Reinforcement Learning trong Kinh Tế
**Nguồn:** mathematics-08-01640.pdf  
**Tạp chí:** Mathematics  
**Tác giả:** Amirhosein Mosavi, Yaser Faghan, Pedram Ghamisi, Puhong Duan, Sina Faizollahzadeh Ardabili, Ely Salwana, Shahab S. Band  
**Năm:** 2020

### Trọng Tâm Chính
Ứng dụng Deep Reinforcement Learning (DRL) trong kinh tế - kết hợp Reinforcement Learning (RL) với Deep Learning (DL).

### Đặc Điểm Chính của DRL
- **Khả năng mở rộng:** Có thể áp dụng cho các vấn đề nhiều chiều
- **Khả năng thích nghi:** Xử lý các mẫu nhiễu và phi tuyến trong dữ liệu kinh tế
- **Học tự động:** Agent học thông qua thử-sai không cần dữ liệu được gán nhãn

### Ưu Điểm của DRL so với Phương Pháp Truyền Thống
1. Ngăn chặn hiệu suất không tối ưu do các ràng buộc thị trường
2. Tìm các chiến lược tối ưu cho phân tích và dự báo thị trường
3. Kết hợp xấp xỉ hàm với học biểu diễn
4. Xử lý các mẫu dữ liệu kinh tế phức tạp và phi tuyến

### Công Nghệ Cốt Lõi
- **Tìm kiếm chính sách:** Phương pháp dựa trên gradient và không dựa trên gradient cho các cài đặt trạng thái-hành động liên tục/rời rạc
- **Xấp xỉ hàm giá trị:** Ước tính lợi nhuận kỳ vọng để tìm chính sách tối ưu
- **Deep Neural Networks:** Cung cấp xấp xỉ hàm mạnh mẽ

### Phương Pháp Đánh Giá
- **Chuẩn Prisma:** Quy trình đánh giá hệ thống 4 bước
  1. Xác định: 400 bài báo từ Web of Science và Scopus
  2. Sàng lọc: 200 bài báo duy nhất
  3. Đủ điều kiện: 80 bài báo để xem xét
  4. Bao gồm: 57 bài báo cho đánh giá cuối cùng

### Ứng Dụng trong Kinh Tế
- Dự đoán xu hướng thị trường
- Tối ưu hóa chiến lược đầu tư
- Đánh giá rủi ro với các tham số không chắc chắn
- Dự báo kinh tế với dữ liệu ngẫu nhiên

### Đóng Góp Chính
1. Phân loại các phương pháp DL, RL và DRL hiện có trong kinh tế
2. Hiểu biết sâu rộng về độ chính xác và khả năng áp dụng
3. Thảo luận về công nghệ cốt lõi và kiến trúc
4. Xác định các vấn đề và thách thức mở

---

## 6. Dự Đoán Khách Hàng Rời Bỏ: Đánh Giá Machine Learning và Deep Learning
**Nguồn:** make-07-00105.pdf  
**Tạp chí:** Machine Learning and Knowledge Extraction  
**Tác giả:** Mehdi Imani, Majid Joudaki, Ali Beikmohammadi, Hamid Reza Arabnia  
**Năm:** 2025

### Bối Cảnh
- Khách hàng rời bỏ tác động đáng kể đến doanh thu doanh nghiệp
- Tỷ lệ rời bỏ hàng năm: 20-40% trong một số ngành
- Thu hút khách hàng mới **đắt gấp 5 đến 25 lần** so với giữ chân khách hàng hiện có

### Phạm Vi Đánh Giá
- **Hướng dẫn PRISMA 2020:** Phương pháp đánh giá hệ thống
- **Khoảng thời gian:** Tháng 1/2020 - Tháng 12/2024
- **Mẫu ban đầu:** 240 nghiên cứu cho phân tích bibliometric
- **Phân tích chi tiết:** 61 nghiên cứu cho tổng hợp định tính
- **Cơ sở dữ liệu:** Springer, IEEE, Elsevier, MDPI, ACM, Wiley qua Lens.org

### Phương Pháp ML
**Phương pháp chủ đạo:**
- **Ensemble Methods:** XGBoost, LightGBM, CatBoost
- **ML truyền thống:** Decision Trees, Random Forests, Support Vector Machines
- Khả năng dự đoán mạnh mẽ với dataset có cấu trúc

### Phương Pháp DL
**Ngày càng được áp dụng:**
- Artificial Neural Networks (ANNs) - Mạng Neural Nhân Tạo
- Convolutional Neural Networks (CNNs) - Mạng Neural Tích Chập
- Long Short-Term Memory networks (LSTMs) - Mạng Bộ Nhớ Dài-Ngắn Hạn
- Transformer-based models - Mô hình dựa trên Transformer
- Ưu điểm cho dữ liệu tuần tự và không có cấu trúc (lịch sử tương tác, phản hồi văn bản)

### Thách Thức Chính
1. **Mất cân bằng lớp:** Ít người rời bỏ hơn nhiều so với người không rời bỏ, làm thiên lệch dự đoán
2. **Khả năng diễn giải:** Mô hình DL hoạt động như mô hình "black-box"
3. **Concept drift:** Hành vi khách hàng phát triển theo thời gian, ảnh hưởng độ chính xác duy trì
4. **Số liệu định hướng lợi nhuận hạn chế:** Khoảng cách giữa hiệu suất mô hình và giá trị kinh doanh

### Đóng Góp Mới
1. Phân loại phân cấp các phương pháp ML/DL
2. Tích hợp các hiểu biết bibliometric và phương pháp luận
3. Ánh xạ dựa trên bằng chứng về xu hướng và thách thức mới nổi
4. Tập trung vào tiềm năng AI có thể giải thích và học thích ứng

### Các Ngành Được Phân Tích
- Viễn thông
- Bán lẻ
- Ngân hàng
- Chăm sóc sức khỏe
- Giáo dục
- Bảo hiểm
- Dịch vụ đăng ký

---

## 7. Dự Đoán Hoàn Nguyên Code với Graph Neural Networks: Case Study tại J.P. Morgan Chase
**Nguồn:** 3617572.3617879.pdf  
**Hội nghị:** SDD '23 (International Workshop on Software Defect Datasets)  
**Tác giả:** Yulong Pei, Salwa Alamir, Rares Dolga, Sameena Shah (J.P. Morgan AI Research)  
**Năm:** 2023

### Công Thức Vấn Đề Mới
**Dự đoán hoàn nguyên code:** Hình thức đặc biệt của phát hiện lỗi phần mềm dự đoán khả năng thay đổi code bị rollback.

### Tại Sao Quan Trọng
- Xác định chủ động các thay đổi code rủi ro
- Cải thiện chất lượng code
- Tối ưu hóa quy trình phát triển
- Quan trọng trong môi trường công nghiệp nơi các vấn đề hoàn nguyên nghiêm trọng hơn

### Thách Thức Công Nghiệp
1. **Codebase quy mô lớn:** Không thực tế để phân tích từng dòng
2. **Truy cập hạn chế:** Hạn chế thuộc tính và nội dung code trong môi trường được quản lý
3. **Chỉ phân tích tĩnh:** Không thể chạy phân tích động (AST, DFG) trên code production
4. **Mất cân bằng cực độ:** Ít hơn 4% commit dẫn đến hoàn nguyên

### Phương Pháp
**Graph Neural Networks (GNNs):**
- Xây dựng code graph sử dụng quan hệ import (phụ thuộc code)
- Đồ thị không có hướng đại diện quan hệ giữa các code script
- Tích hợp phụ thuộc code mà các phương pháp trước bỏ qua

### Đặc Trưng Được Sử Dụng (theo Tầm Quan Trọng)
1. **Tần suất hoàn nguyên 30 ngày qua** (IV: 0.570) - dự báo mạnh nhất
2. **Phiên bản file** (IV: 0.326)
3. **Số ngày trễ commit đến push** (IV: 0.188)
4. **Tổng số dòng code trong push set** (IV: 0.151)
5. **Tổng độ phức tạp Cyclomatic** (IV: 0.100)
6. **Số người đóng góp duy nhất** (IV: 0.082)
7. **Số module phụ thuộc** (IV: 0.063)
8. **Số file trong push set** (IV: 0.014)

### Hai Phương Pháp
1. **Phân loại mất cân bằng:** Xử lý tỷ lệ lớp dương <4%
2. **Phát hiện bất thường:** Coi hoàn nguyên như bất thường trong commit code bình thường

### Đóng Góp Chính
1. Nghiên cứu đầu tiên về dự đoán hoàn nguyên code trong môi trường công nghiệp
2. Nghiên cứu thực nghiệm có hệ thống tích hợp phụ thuộc code
3. Phương pháp dựa trên GNN từ cả góc độ phát hiện bất thường và phân loại mất cân bằng
4. Thảo luận chi tiết về hướng tương lai (khả năng giải thích, xử lý mất cân bằng)

### Tác Động Thực Tiễn
- Lợi ích cho chất lượng phần mềm trong các tổ chức tài chính
- Áp dụng cho các ngành được quản lý khác với các ràng buộc tương tự
- Dữ liệu lịch sử từ log commit loại bỏ nhu cầu gán nhãn thủ công

---

## Chủ Đề Chung Xuyên Suốt Các Nghiên Cứu

### 1. Thách Thức về Dữ Liệu
- **Dataset mất cân bằng** (dự đoán rời bỏ, dự đoán hoàn nguyên code)
- Yêu cầu **khả năng mở rộng big data**
- Ràng buộc về **chất lượng và sẵn có dữ liệu**

### 2. Đánh Đổi Lựa Chọn Mô Hình
- **Ưu điểm deep learning:** Mẫu phức tạp, dữ liệu không cấu trúc, khả năng mở rộng
- **Hạn chế deep learning:** Tính chất black-box, chi phí tính toán, hiệu suất dữ liệu có cấu trúc
- **ML truyền thống vẫn cạnh tranh:** Đặc biệt cho dataset có cấu trúc (gradient boosting)

### 3. Ứng Dụng Công Nghiệp
- **Dịch vụ Tài chính:** Liên kết thực thể, quản lý rủi ro, phát hiện gian lận
- **Phân tích Khách hàng:** Dự đoán rời bỏ, chiến lược giữ chân
- **Kỹ thuật Phần mềm:** Phát hiện lỗi, chất lượng code
- **Kinh tế:** Dự đoán thị trường, tối ưu hóa chính sách

### 4. Khả Năng Diễn Giải vs. Hiệu Suất
- Đánh đổi giữa độ phức tạp mô hình và khả năng giải thích
- Tập trung ngày càng tăng vào AI có thể giải thích (XAI)
- Nhu cầu kinh doanh về ra quyết định minh bạch

### 5. Ràng Buộc Thực Tế
- Nguồn lực tính toán
- Tuân thủ quy định
- Thiếu kỹ năng và thách thức triển khai
- Cần số liệu đánh giá phù hợp với kinh doanh

### 6. Hướng Tương Lai
- Học thích ứng cho concept drift
- Mô hình lai kết hợp DL và ML truyền thống
- Số liệu định hướng lợi nhuận và tập trung kinh doanh
- Phương pháp khả năng diễn giải nâng cao
- Xử lý tốt hơn dữ liệu mất cân bằng

---

## Hiểu Biết về Phương Pháp Luận

### Khi Nào Sử Dụng Deep Learning
✅ **Phù hợp cho:**
- Dữ liệu không có cấu trúc (văn bản, hình ảnh, giọng nói)
- Dữ liệu tuần tự/thời gian
- Dataset quy mô lớn
- Các mối quan hệ phi tuyến phức tạp
- Không gian đặc trưng nhiều chiều

❌ **Không được khuyến nghị cho:**
- Dữ liệu dạng bảng có cấu trúc với đặc trưng có độ dài cố định
- Sẵn có dữ liệu hạn chế
- Yêu cầu khả năng diễn giải cao
- Môi trường hạn chế nguồn lực
- Khi ML truyền thống hoạt động đầy đủ

### Thực Hành Tốt Nhất
1. **Xác thực thực nghiệm** trước khi áp dụng đầy đủ
2. **Kiến trúc tùy chỉnh** thay vì cấu hình mặc định
3. **Phương pháp ensemble** cho dữ liệu kinh doanh có cấu trúc
4. **Phương pháp dựa trên đồ thị** cho dữ liệu quan hệ
5. **Đánh giá hệ thống** theo PRISMA hoặc chuẩn tương tự
6. **Số liệu phù hợp với kinh doanh** ngoài chỉ độ chính xác

---

## Tóm Tắt Khoảng Trống Nghiên Cứu

1. **Nghiên cứu triển khai thực tế hạn chế** so với thí nghiệm học thuật
2. **Tập trung không đủ vào số liệu giá trị kinh doanh** (lợi nhuận, ROI, tiết kiệm chi phí)
3. **Cần benchmark chuẩn hóa** xuyên ngành
4. **Phương pháp khả năng giải thích** vẫn chưa phát triển
5. **Học thích ứng** cho môi trường thay đổi chưa được khám phá
6. **Thách thức tích hợp** giữa ML/DL và hệ thống kinh doanh hiện có

---

## Kết Luận

Nghiên cứu chứng minh rằng mặc dù deep learning mang lại những tiến bộ đáng kể trong việc xử lý dữ liệu phức tạp, không có cấu trúc, nó không phải là giải pháp phổ quát. Các tổ chức nên:

1. **Đánh giá đặc điểm dữ liệu** trước khi chọn giữa DL và ML truyền thống
2. **Xem xét ràng buộc vận hành** (tính toán, kỹ năng, khả năng diễn giải)
3. **Ưu tiên giá trị kinh doanh** hơn số liệu hiệu suất học thuật
4. **Đầu tư vào phương pháp lai** kết hợp điểm mạnh của nhiều phương pháp
5. **Tập trung vào xác thực thực tế** và thách thức triển khai
6. **Xây dựng năng lực** trong cả ML truyền thống và deep learning

Sự hội tụ của AI, machine learning và chuyên môn lĩnh vực trong kinh tế, phân tích kinh doanh và kỹ thuật phần mềm tiếp tục thúc đẩy đổi mới, nhưng thành công đòi hỏi ứng dụng chu đáo các phương pháp phù hợp cho các bối cảnh vấn đề cụ thể.
