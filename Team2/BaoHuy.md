# Tài liệu tham khảo: Fraud Detection

## 1. Philip K. Chan, Wei Fan, Andreas L. Prodromidis & Salvatore J. Stolfo (1999)
```bibtex
@article{chan1999distributed,
  title={Distributed data mining in credit card fraud detection},
  author={Chan, Philip K and Fan, Wei and Prodromidis, Andreas L and Stolfo, Salvatore J},
  journal={IEEE Intelligent Systems and Their Applications},
  volume={14},
  number={6},
  pages={67--74},
  year={1999},
  publisher={IEEE}
}
```
**Đóng góp**: Nghiên cứu giải quyết bài toán phát hiện gian lận thẻ tín dụng trên dữ liệu giao dịch quy mô lớn, đồng thời xử lý ba thách thức chính bao gồm khả năng mở rộng, phân bố lớp mất cân bằng và chi phí sai phân loại không đồng đều. Nghiên cứu đề xuất một kiến trúc distributed data mining trong đó dữ liệu được chia thành các tập con để huấn luyện nhiều bộ phân loại song song, sau đó kết hợp các bộ phân loại bằng metalearning, cùng với cơ chế cost-sensitive learning (AdaCost) để tối thiểu hóa tổn thất do gian lận. Kết quả thực nghiệm trên dữ liệu thực tế từ Chase Bank và First Union cho thấy phương pháp kết hợp các bộ phân loại có thể giảm đáng kể chi phí tổn thất do gian lận và trong nhiều thí nghiệm vượt qua cả các bộ phân loại đơn lẻ và hệ thống phát hiện gian lận thương mại hiện có.

## 2. Waleed Hilal, S. Andrew Gadsden & John Yawney (2022)
```bibtex
@article{hilal2022financial,
  title={Financial fraud: a review of anomaly detection techniques and recent advances},
  author={Hilal, Waleed and Gadsden, S Andrew and Yawney, John},
  journal={Expert systems With applications},
  volume={193},
  pages={116429},
  year={2022},
  publisher={Elsevier}
}
```
**Đóng góp**: Nghiên cứu cung cấp một nguồn tổng quan có hệ thống và toàn diện về các kỹ thuật anomaly detection được áp dụng trong phát hiện gian lận tài chính, đặc biệt trong bối cảnh dữ liệu mất cân bằng, thiếu nhãn và hành vi gian lận thay đổi theo thời gian. Nghiên cứu thực hiện một critical review các công trình về financial fraud detection, phân loại và tổng hợp các phương pháp học có giám sát, bán giám sát và không giám sát, đồng thời xem xét các thước đo đánh giá, thách thức và hạn chế của từng hướng tiếp cận

# Tài liệu tham khảo: Credit Risk / Credit Scoring

## 3. Edward I. Altman (1968)
```bibtex
@article{altman1968financial,
  title={Financial ratios, discriminant analysis and the prediction of corporate bankruptcy},
  author={Altman, Edward I},
  journal={The journal of finance},
  volume={23},
  number={4},
  pages={589--609},
  year={1968},
  publisher={JSTOR}
}
```
**Đóng góp**: Nghiên cứu giải quyết vấn đề dự đoán khả năng phá sản doanh nghiệp, đồng thời khắc phục hạn chế của cách phân tích từng financial ratio riêng lẻ bằng cách kết hợp nhiều chỉ số tài chính trong một mô hình đa biến. Tác giả sử dụng Multiple Discriminant Analysis (MDA) để lựa chọn và kết hợp các financial ratios thành một discriminant function, từ đó phân biệt doanh nghiệp phá sản và không phá sản. Kết quả dẫn đến mô hình Z-score dựa trên năm nhóm chỉ số tài chính, cho thấy cách tiếp cận đa biến có thể cung cấp cơ sở định lượng cho việc dự đoán và đánh giá rủi ro tài chính của doanh nghiệp.

## 4.Björn Rafn Gunnarsson, Seppe vanden Broucke, Bart Baesens, María Óskarsdóttir & Wilfried Lemahieu (2021)
```bibtex
@article{gunnarsson2021deep,
  title={Deep learning for credit scoring: Do or don’t?},
  author={Gunnarsson, Bj{\"o}rn Rafn and Vanden Broucke, Seppe and Baesens, Bart and {\'O}skarsd{\'o}ttir, Mar{\'\i}a and Lemahieu, Wilfried},
  journal={European Journal of Operational Research},
  volume={295},
  number={1},
  pages={292--305},
  year={2021},
  publisher={Elsevier}
}
```
**Đóng góp**: Nghiên cứu đánh giá liệu deep learning có thực sự phù hợp với credit scoring hay không, trong bối cảnh các nghiên cứu trước đó còn sử dụng ít bộ dữ liệu và chưa đánh giá đầy đủ hiệu năng cũng như lợi nhuận của mô hình. Tác giả thực hiện so sánh MLP và Deep Belief Network với logistic regression, decision tree, random forest và XGBoost trên 10 bộ dữ liệu credit scoring thực tế, sử dụng nhiều performance measures, bao gồm cả profit-driven measure, đồng thời đưa Bayesian hypothesis testing vào việc so sánh các mô hình. Kết quả cho thấy XGBoost đạt hiệu năng tốt nhất, trong khi deep neural networks không vượt qua các mô hình nông hơn và có chi phí tính toán cao hơn; do đó, khi mục tiêu chính là performance, XGBoost được khuyến nghị thay cho các phương pháp deep learning được khảo sát.

# Tài liệu tham khảo: Customer Segmentation

## 5. Girish Punj & David W. Stewart (1983)
```bibtex
@article{punj1983cluster,
  title={Cluster analysis in marketing research: Review and suggestions for application},
  author={Punj, Girish and Stewart, David W},
  journal={Journal of marketing research},
  volume={20},
  number={2},
  pages={134--148},
  year={1983},
  publisher={SAGE Publications Sage CA: Los Angeles, CA}
}
```
**Đóng góp**: Nghiên cứu giải quyết vấn đề lựa chọn và áp dụng cluster analysis trong marketing research, trong bối cảnh các nghiên cứu trước đó sử dụng nhiều phương pháp phân cụm khác nhau nhưng chưa có sự thống nhất về hiệu quả và cách đánh giá. Tác giả tổng quan và đánh giá các phương pháp clustering dựa trên bằng chứng thực nghiệm, đồng thời đề xuất quy trình phân cụm hai giai đoạn, trong đó sử dụng Ward’s minimum variance hoặc simple average linkage để xác định sơ bộ các cluster, sau đó tinh chỉnh bằng phương pháp iterative partitioning. Nghiên cứu cũng hệ thống hóa các vấn đề quan trọng trong việc lựa chọn phương pháp, biến số, metric và validation của kết quả clustering, qua đó cung cấp nền tảng phương pháp luận cho việc ứng dụng cluster analysis vào market/customer segmentation.

## 6. Joni Salminen, Mekhail Mustak, Muhammad Sufyan & Bernard J. Jansen (2023)
```bibtex
@article{salminen2023can,
  title={How can algorithms help in segmenting users and customers? A systematic review and research agenda for algorithmic customer segmentation},
  author={Salminen, Joni and Mustak, Mekhail and Sufyan, Muhammad and Jansen, Bernard J},
  journal={Journal of Marketing Analytics},
  volume={11},
  number={4},
  pages={677--692},
  year={2023},
  publisher={Springer}
}
```
**Đóng góp**:Nghiên cứu giải cung cấp cái nhìn hệ thống và cập nhật về cách các thuật toán được sử dụng trong customer segmentation, đặc biệt trong bối cảnh AI/ML ngày càng được áp dụng rộng rãi. Tác giả thực hiện systematic literature review trên 172 nghiên cứu, xác định 46 thuật toán và 14 metrics đánh giá, cho thấy K-Means là thuật toán được sử dụng phổ biến nhất; đồng thời phân tích số lượng segment, hyperparameters và mức độ tham gia của domain experts trong việc đánh giá kết quả. Nghiên cứu từ đó chỉ ra rằng các vấn đề nền tảng mà Punj & Stewart (1983) nêu ra — như lựa chọn metric, biến phân khúc, cross-validation và external validation — vẫn chưa được giải quyết triệt để sau 40 năm, đồng thời đề xuất các hướng nghiên cứu mới như chuẩn hóa evaluation framework, đánh giá theo business outcomes, tích hợp nhiều thuật toán và tăng vai trò của con người trong quá trình segmentation.

