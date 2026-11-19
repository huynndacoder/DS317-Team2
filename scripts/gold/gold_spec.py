#!/usr/bin/env python3
"""Authoritative column dictionary for the Gold research dataset.

This module is the single source of truth for three questions the modelling code
must never answer on its own:

  1. what role does each column play (feature / identifier / target /
     split_metadata / audit_only / excluded)?
  2. for a feature, what is its documented missing-code semantics?
  3. what normalisation is applied *before* the split, and what is deliberately
     left for after the split?

Every sentinel and every definition change below is cited to a source. Where a
source could not be retrieved the entry says UNVERIFIED rather than guessing.
Sources used (all fetched, Release 48, 2026-10-28):

  UG  = Freddie Mac Single-Family Loan-Level Dataset, General User Guide,
        Release 48 (October 2026), Origination Data File glossary.
  RN  = Freddie Mac SFLLD Release Notes (Releases 1-48).
  FAQ = Freddie Mac SFLLD FAQ, January 2026.
  FL  = file_layout_july_2026.xlsx, sheet "Origination Data File".

Emits feature_dictionary.csv and feature_dictionary.md next to the other Gold
artefacts. Run: ./venv/bin/python scripts/gold/gold_spec.py
"""
import csv
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "research"

# ---------------------------------------------------------------------------
# Roles. Every column in Gold v1 (features + audit) gets exactly one.
# ---------------------------------------------------------------------------
ROLES = ("feature", "identifier", "target", "split_metadata", "audit_only", "excluded")

# Baseline feature set for the first model. Deliberately smaller than the list
# of things that are *allowed*: a column can be legitimate and still be left out
# of the baseline while its availability is argued.
BASELINE = [
    "original_upb",
    "original_loan_term",
    "original_interest_rate",
    "ltv",
    "cltv",
    "dti",
    "mi_percentage",
    "number_of_units",
    "number_of_borrowers",
    "credit_score",
    "first_time_homebuyer_flag",
    "channel",
    "property_type",
    "property_state",
    "occupancy_status",
    "prepayment_penalty_flag",
    "super_conforming_flag",
    "harp_indicator",
]

# ---------------------------------------------------------------------------
# The dictionary. One dict per column; keys match the requested schema exactly.
# ---------------------------------------------------------------------------
D = []


def col(**kw):
    missing = [k for k in (
        "column", "role", "meaning", "source_column", "semantic_type",
        "available_at_scoring_time", "availability_evidence", "missing_codes",
        "valid_domain", "historical_definition_changes", "normalization_rule",
        "baseline_decision", "decision_reason", "source_reference") if k not in kw]
    assert not missing, f"{kw.get('column')}: missing {missing}"
    assert kw["role"] in ROLES, kw["role"]
    D.append(kw)


# === identifiers, target, split metadata ==================================
col(column="loan_id", role="identifier", meaning="Mã khoản vay duy nhất (Freddie Mac)",
    source_column="loan_id", semantic_type="string_id",
    available_at_scoring_time="yes",
    availability_evidence="Khoá của file origination; dùng để join, không mang thông tin dự báo.",
    missing_codes="none (0 null trên 49.348.308 dòng)",
    valid_domain=r"^F[0-9]{2}Q[0-9][0-9]{7}$ (kiểm tra ở §8)",
    historical_definition_changes="none",
    normalization_rule="giữ nguyên, không đổi",
    baseline_decision="không vào X",
    decision_reason="Định danh, không phải đặc trưng; đưa vào X sẽ khiến mô hình học thuộc bản ghi.",
    source_reference="UG, Origination Data File")

col(column="label_12m", role="target", meaning="Nhãn quá hạn nghiêm trọng/REO trong 12 kỳ thanh toán đầu tiên",
    source_column="(dẫn xuất từ performance — xem docs/label_rules.md)",
    semantic_type="binary",
    available_at_scoring_time="no",
    availability_evidence="Nhãn chỉ quan sát được SAU khi cửa sổ 12 tháng kết thúc; xây từ current_loan_delinquency_status và zero_balance_code.",
    missing_codes="NULL = chưa xác định (không bao giờ thành 0)",
    valid_domain="{0,1,NULL}",
    historical_definition_changes="Định nghĩa nhãn đổi ở vòng 2 và vòng 3 (xem docs/label_rules.md §12–13); phiên bản hiện hành là v3.",
    normalization_rule="không đổi; NULL giữ nguyên NULL",
    baseline_decision="target, không vào X",
    decision_reason="Biến phụ thuộc.",
    source_reference="docs/label_rules.md")

col(column="cohort", role="split_metadata", meaning="Quý khởi tạo (partition gốc của file origination)",
    source_column="quarter (cột partition vật lý của parquet origination)",
    semantic_type="categorical_period",
    available_at_scoring_time="yes",
    availability_evidence="Là quý phát hành của chính khoản vay; biết tại thời điểm khởi tạo.",
    missing_codes="none",
    valid_domain="YYYYQn, 1999Q1 … 2026Q2 (110 giá trị)",
    historical_definition_changes="none",
    normalization_rule="giữ nguyên dạng chuỗi YYYYQn",
    baseline_decision="metadata chia tập, chưa vào X",
    decision_reason="Dùng để chia theo thời gian. Đưa vào X sẽ cho mô hình học xu hướng thời gian của nhãn, thứ không tồn tại khi dự báo một khoản vay mới ở tương lai.",
    source_reference="UG; README (partition layout)")

col(column="loan_purpose", role="excluded", meaning="Mục đích vay",
    source_column="loan_purpose", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="Khai báo tại khởi tạo; UG: trường của hồ sơ origination.",
    missing_codes="`9` = Not Available (51 dòng, 1999Q1–Q3)",
    valid_domain="P = Purchase; C = Refinance - Cash Out; N = Refinance - No Cash Out; R = Refinance - Not Specified; 9 = Not Available. Dữ liệu này chỉ có N/P/C/9; `R` không xuất hiện.",
    historical_definition_changes="Bảng trường Release 19 (2018-03) chỉ liệt kê P/C/N/9, chưa có `R`; Release 47/48 đổi nhãn `C` từ 'Cash-out Refinance' thành 'Refinance - Cash Out' (mã không đổi).",
    normalization_rule="dùng để LỌC `P`; sau lọc là hằng số",
    baseline_decision="không vào X (dùng để lọc Purchase)",
    decision_reason="Sau khi lọc Purchase-only, cột này chỉ còn một giá trị ⇒ zero variance, không mang thông tin. Giữ ở metadata để truy vết.",
    source_reference="UG R48 'Loan Purpose'; RN Release 19")

# === audit-only / metadata ================================================
_AUDIT = [
    ("label_status", "positive / negative / unknown", "Nhãn ba trạng thái trước khi mã hoá 0/1",
     "Kết luận của bộ quy tắc nhãn; chỉ biết sau cửa sổ."),
    ("eligible_for_primary_study", "boolean", "Đủ điều kiện vào nghiên cứu chính",
     "Tổng hợp của maturity + nhãn xác định + không lỗi nghiêm trọng."),
    ("original_first_payment_date", "YYYYMM", "Kỳ thanh toán đầu tiên theo lịch gốc",
     "Mốc neo cửa sổ nhãn. KHÔNG phải leakage: nó là ngày đến hạn đầu tiên, biết tại khởi tạo."),
    ("label_window_start", "YYYYMM", "Tháng bắt đầu cửa sổ nhãn", "= first_payment_date."),
    ("label_window_end", "YYYYMM", "Tháng kết thúc cửa sổ nhãn", "= start + 11 tháng lịch."),
    ("performance_cutoff", "YYYYMM", "Biên dữ liệu performance của partition",
     "Thuộc về quá trình thu thập dữ liệu, không phải thuộc tính khoản vay."),
    ("window_mature", "boolean", "Cửa sổ riêng của khoản vay đã kết thúc trước cutoff",
     "Phụ thuộc thời điểm trích xuất."),
    ("cohort_mature", "boolean", "Cả cohort đã trưởng thành theo mốc neo p99",
     "Phụ thuộc thời điểm trích xuất."),
    ("first_event_month", "YYYYMM", "Tháng biến cố 90+ đầu tiên", "Chỉ biết sau khi quan sát."),
    ("termination_code", "mã zero-balance", "Mã kết thúc khoản vay", "Chỉ biết sau khi khoản vay kết thúc."),
    ("termination_month", "YYYYMM", "Tháng báo cáo của sự kiện kết thúc", "Chỉ biết sau."),
    ("observed_month_count_in_window", "integer", "Số tháng quan sát được trong cửa sổ", "Thuộc tính của dữ liệu, không phải của khoản vay."),
    ("missing_month_count", "integer", "Số tháng thiếu trong cửa sổ", "Như trên."),
    ("primary_exclusion_reason", "string", "Lý do loại trừ chính", "Chỉ tồn tại cho khoản không đủ điều kiện."),
    ("label_reason", "string", "Lý do nhãn chưa xác định", "Như trên."),
    ("quality_flags", "string", "Cờ chất lượng (conflict/dup/…)", "Chẩn đoán."),
]
for name, stype, meaning, why in _AUDIT:
    col(column=name, role="audit_only", meaning=meaning, source_column="(audit, sinh bởi build_labels.py)",
        semantic_type=stype, available_at_scoring_time="no",
        availability_evidence=why + " Đây là thông tin của quá trình xây nhãn/trích xuất, không có tại thời điểm chấm điểm.",
        missing_codes="n/a", valid_domain="n/a",
        historical_definition_changes="none",
        normalization_rule="không đổi; giữ nguyên trong audit",
        baseline_decision="audit_only, không vào X",
        decision_reason="Nếu vào X sẽ là leakage trực tiếp (chứa chính kết luận, hoặc thông tin chỉ có sau cửa sổ).",
        source_reference="scripts/label/build_labels.py; docs/label_rules.md")

# === features ============================================================
col(column="original_upb", role="feature",
    meaning="Số dư gốc tại khởi tạo (làm tròn $1.000)",
    source_column="original_upb", semantic_type="numeric_amount",
    available_at_scoring_time="yes",
    availability_evidence="UG: 'The dollar amount of the loan as stated on the note at the time the loan was originated.'",
    missing_codes="không có sentinel được tài liệu hoá (UG không nêu mã thiếu)",
    valid_domain="> 0; đã kiểm tra min/max ở feature_quality",
    historical_definition_changes="none",
    normalization_rule="giữ nguyên số; không log, không chia scale trước split",
    baseline_decision="DÙNG",
    decision_reason="Điều khoản khoản vay, biết tại khởi tạo, quan hệ trực tiếp với khả năng trả nợ.",
    source_reference="UG R48 'Original UPB'")

col(column="original_loan_term", role="feature",
    meaning="Số tháng vay theo lịch trả nợ",
    source_column="original_loan_term", semantic_type="numeric_count",
    available_at_scoring_time="yes",
    availability_evidence="UG: 'The number of months in which regularly scheduled borrower payments are due', tính từ ngày đáo hạn − ngày thanh toán đầu + 1.",
    missing_codes="không có sentinel được tài liệu hoá",
    valid_domain="thường 60–480; xem phân bố thực tế",
    historical_definition_changes="none",
    normalization_rule="giữ nguyên",
    baseline_decision="DÙNG",
    decision_reason="Điều khoản khoản vay tại khởi tạo; ảnh hưởng trực tiếp tới lịch trả nợ.",
    source_reference="UG R48 'Original Loan Term'")

col(column="original_interest_rate", role="feature",
    meaning="Lãi suất danh nghĩa tại khởi tạo (%/năm)",
    source_column="original_interest_rate", semantic_type="numeric_rate",
    available_at_scoring_time="yes",
    availability_evidence="UG: 'The interest rate of the loan as stated on the note at the time the loan was originated.'",
    missing_codes="không có sentinel; có đúng 1 dòng NULL trên 49.348.308",
    valid_domain="> 0; kiểm tra outlier theo phân bố, KHÔNG cắt",
    historical_definition_changes="none",
    normalization_rule="giữ nguyên; gắn cờ 1 dòng NULL",
    baseline_decision="DÙNG",
    decision_reason="Điều khoản khoản vay; yếu tố quyết định khả năng trả nợ hàng tháng.",
    source_reference="UG R48 'Original Interest Rate'")

col(column="ltv", role="feature", meaning="Tỷ lệ vay/giá trị tại khởi tạo (%)",
    source_column="ltv", semantic_type="numeric_ratio",
    available_at_scoring_time="yes",
    availability_evidence="UG: đo tại thời điểm khởi tạo từ giá trị tài sản và số tiền vay.",
    missing_codes="`999` = Not Available (1.858 dòng); FAQ coi `999` và null là một",
    valid_domain="2018Q1 và trước: 6–105%; 2018Q2 trở đi: 1–998%",
    historical_definition_changes="RN Release 29 (2021-10): mở rộng dải hợp lệ lên 1–998% **chỉ cho khoản khởi tạo 2018Q2 trở đi**. Trước đó trần là 105%.",
    normalization_rule="`999` → NULL; các giá trị ngoài dải của giai đoạn áp dụng → đếm vào invalid_value rồi → NULL",
    baseline_decision="DÙNG",
    decision_reason="Chỉ số rủi ro tín dụng cốt lõi tại khởi tạo; dải thay đổi đã được xử lý theo giai đoạn.",
    source_reference="UG R48 'Original LTV'; RN Release 29")

col(column="cltv", role="feature", meaning="Tỷ lệ vay/giá trị gộp (gồm cả khoản vay thứ cấp) (%)",
    source_column="cltv", semantic_type="numeric_ratio",
    available_at_scoring_time="yes",
    availability_evidence="UG: đo tại khởi tạo, gộp mọi khoản vay có bảo đảm trên tài sản.",
    missing_codes="`999` = Not Available (2.193 dòng); UG: nếu CLTV < LTV thì CLTV được công bố là Not Available",
    valid_domain="2018Q1 và trước: 6–200%; 2018Q2 trở đi: 1–998%",
    historical_definition_changes="RN Release 29 (2021-10): mở rộng dải 1–998% cho 2018Q2 trở đi.",
    normalization_rule="`999` → NULL; ngoài dải → invalid rồi NULL. Giữ cờ `cltv_lt_ltv` để truy vết trường hợp UG mô tả.",
    baseline_decision="DÙNG",
    decision_reason="Bổ sung cho LTV khi có vay thứ cấp; khác LTV ở nhóm có second lien.",
    source_reference="UG R48 'Original CLTV'; RN Release 29")

col(column="dti", role="feature", meaning="Tỷ lệ nợ/thu nhập tại khởi tạo (%)",
    source_column="dti", semantic_type="numeric_ratio",
    available_at_scoring_time="yes",
    availability_evidence="UG: tỷ lệ đo tại khởi tạo từ nghĩa vụ nợ hàng tháng / thu nhập.",
    missing_codes="`999` = Not Available (3.293.086 dòng — 6,7% toàn bộ); UG: tỷ lệ > 65% được công bố là Not Available; **mọi khoản HARP đều là Not Available**",
    valid_domain="0–65%",
    historical_definition_changes="none documented",
    normalization_rule="`999` → NULL; > 65 → invalid → NULL",
    baseline_decision="DÙNG (kèm cảnh báo)",
    decision_reason="Chỉ số rủi ro quan trọng, nhưng thiếu 6,7% và thiếu có hệ thống ở nhóm HARP ⇒ phải đọc cùng `harp_indicator`.",
    source_reference="UG R48 'Original DTI'; FAQ Jan 2026")

col(column="mi_percentage", role="feature", meaning="Tỷ lệ bảo hiểm khoản vay (%)",
    source_column="mi_percentage", semantic_type="numeric_ratio",
    available_at_scoring_time="yes",
    availability_evidence="UG: tỷ lệ MI tại khởi tạo do seller báo cáo.",
    missing_codes="`999` = Not Available (735 dòng); **`0` = No MI** — đây là giá trị hợp lệ, không phải thiếu",
    valid_domain="1–55%; 0 = không có MI",
    historical_definition_changes="none",
    normalization_rule="`999` → NULL; **giữ 0** (No MI) và tạo biến dẫn xuất `has_mi = mi_percentage > 0`",
    baseline_decision="DÙNG",
    decision_reason="Sự hiện diện của MI phản ánh LTV cao; phân biệt 0 (không có MI) với 999 (không biết) là bắt buộc để không trộn 'không có' với 'không biết'.",
    source_reference="UG R48 'MI %'")

col(column="number_of_units", role="feature", meaning="Số căn trên tài sản (1–4)",
    source_column="number_of_units", semantic_type="numeric_count",
    available_at_scoring_time="yes",
    availability_evidence="UG: thuộc tính tài sản tại khởi tạo.",
    missing_codes="`99` = Not Available (2.432 dòng)",
    valid_domain="1–4",
    historical_definition_changes="none",
    normalization_rule="`99` → NULL; ngoài 1–4 → invalid → NULL",
    baseline_decision="DÙNG",
    decision_reason="Bất động sản nhiều căn có rủi ro khác biệt; biết tại khởi tạo.",
    source_reference="UG R48 'Number of Units'")

col(column="number_of_borrowers", role="feature", meaning="Số người vay",
    source_column="number_of_borrowers", semantic_type="numeric_count (định nghĩa đổi 2018Q2)",
    available_at_scoring_time="yes",
    availability_evidence="UG: số người vay trên hồ sơ tại khởi tạo.",
    missing_codes="`99` = Not Available (6.949 dòng, **toàn bộ ở 2018Q1 và trước**)",
    valid_domain="2018Q1 và trước: `1` = 1 người vay, `2` = **>1 người vay** (nhị phân). 2018Q2 trở đi: `1` = 1 người, `2` = 2 người, … `10` = 10 người (đếm thật). `99` = Not Available",
    historical_definition_changes="**CÓ — hiệu lực 2018Q2.** RN Release 29 (2021-10) mục 6: 'Expanded the valid value ranges … This change only impacts loans originated 2018Q2 and later. … c. Number of Borrowers — 1-10'. Trước 2018Q2 cột là cờ nhị phân; từ 2018Q2 là số đếm thật. Dữ liệu xác nhận: pre-2018Q2 chỉ có 1/2/99; from-2018Q2 có 1..6.",
    normalization_rule="Biểu diễn thống nhất 3 nhóm: `one` (1), `multiple` (2+), `unknown` (99→NULL). Giữ cột raw `number_of_borrowers_raw` để truy vết.",
    baseline_decision="DÙNG (dạng 3 nhóm)",
    decision_reason="Vì `2` đổi nghĩa tại 2018Q2, dùng số đếm thô sẽ khiến mô hình học một bước nhảy giả tại 2018Q2. Nhóm 3 giá trị giữ được ý nghĩa bất biến theo thời gian. **Không** coi `99` là 'nhiều người vay'.",
    source_reference="UG R48 'Number of Borrowers'; RN Release 29 mục 6")

col(column="credit_score", role="feature", meaning="Điểm tín dụng Classic FICO tại khởi tạo",
    source_column="credit_score", semantic_type="numeric_score",
    available_at_scoring_time="yes",
    availability_evidence="UG: 'the score known at the time of acquisition and … the score used to originate the mortgage'.",
    missing_codes="`9999` = Not Available (76.020 dòng)",
    valid_domain="300–850",
    historical_definition_changes="**CÓ, hai lần.** (a) RN Release 2 (2013-05): 'credit scores now will be determined using a methodology more consistent with … loans originated after 2002 … changed marginally, by up to 2 points.' (b) Release 47 đổi tên trường thành 'Classic FICO'; FAQ Q27 nói Freddie Mac không công bố điểm nào trong nhiều điểm thu thập được điền vào trường.",
    normalization_rule="`9999` → NULL; <300 hoặc >850 → invalid → NULL. **Không** chuẩn hoá theo năm (không trừ trung bình theo cohort) vì đó là biến đổi phụ thuộc nhãn/thời gian.",
    baseline_decision="DÙNG (kèm ghi chú không so sánh tuyệt đối qua 2013)",
    decision_reason="Chỉ số dự báo mạnh nhất trong hồ sơ khởi tạo. Bước nhảy 2013 tối đa ~2 điểm — nhỏ so với độ phân giải 300–850, nhưng phải ghi nhận.",
    source_reference="UG R48 'Classic FICO'; RN Release 2; FAQ Q27")

col(column="vantage_score_4", role="excluded", meaning="Điểm VantageScore 4.0",
    source_column="vantage_score_4", semantic_type="numeric_score",
    available_at_scoring_time="không chứng minh được cho giai đoạn huấn luyện",
    availability_evidence="RN Release 47 (2026-07): 'New field: VantageScore4' — trường mới thêm ở Release 47, vị trí 31. Dữ liệu xác nhận: chỉ 273/306.102 dòng năm 2026 có giá trị hợp lệ, **0 dòng** hợp lệ ở mọi năm trước đó; 49.348.035/49.348.308 dòng là `9999`.",
    missing_codes="`9999` = Not Available",
    valid_domain="300–850",
    historical_definition_changes="Trường chỉ tồn tại từ Release 47; không có cho khoản khởi tạo trước 2026.",
    normalization_rule="không dùng",
    baseline_decision="LOẠI khỏi baseline",
    decision_reason="Không tồn tại trong toàn bộ giai đoạn huấn luyện (1999–2024). Đưa vào sẽ là cột 100% missing ở train và có giá trị ở test ⇒ mô hình không thể học, và mọi so sánh theo thời gian đều sai.",
    source_reference="RN Release 47; UG R48 'VantageScore 4.0'; kiểm chứng trên dữ liệu")

col(column="first_time_homebuyer_flag", role="feature", meaning="Người mua nhà lần đầu",
    source_column="first_time_homebuyer_flag", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="UG: khai báo tại khởi tạo.",
    missing_codes="`9` = Not Available (19.053 dòng)",
    valid_domain="Y / N / 9",
    historical_definition_changes="none",
    normalization_rule="`9` → NULL (unknown); Y/N giữ nguyên",
    baseline_decision="DÙNG",
    decision_reason="Biết tại khởi tạo; nhóm người mua lần đầu có hành vi rủi ro khác biệt.",
    source_reference="UG R48 'First Time Homebuyer Flag'")

col(column="channel", role="feature", meaning="Kênh khởi tạo",
    source_column="channel", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="UG: kênh mà khoản vay được khởi tạo.",
    missing_codes="`9` = Not Available (1.812 dòng)",
    valid_domain="R = Retail; C = Correspondent; T = TPO (third-party origination); B = Broker; 9 = Not Available",
    historical_definition_changes="none",
    normalization_rule="`9` → NULL",
    baseline_decision="DÙNG",
    decision_reason="Kênh ảnh hưởng tới chất lượng hồ sơ; biết tại khởi tạo.",
    source_reference="UG R48 'Channel'")

col(column="product_type", role="excluded", meaning="Loại sản phẩm",
    source_column="product_type", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="UG: loại sản phẩm tại khởi tạo.",
    missing_codes="none",
    valid_domain="FRM / ARM. **Dữ liệu này chỉ có `FRM`** (49.348.308/49.348.308).",
    historical_definition_changes="none",
    normalization_rule="không dùng",
    baseline_decision="LOẠI khỏi baseline",
    decision_reason="Hằng số trên toàn bộ dữ liệu ⇒ zero variance, không mang thông tin. Vẫn giữ trong audit để truy vết vì sao.",
    source_reference="UG R48 'Product Type'; kiểm chứng trên dữ liệu")

col(column="property_type", role="feature", meaning="Loại tài sản",
    source_column="property_type", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="UG: loại tài sản bảo đảm tại khởi tạo.",
    missing_codes="`99` = Not Available (1.877 dòng)",
    valid_domain="SF = Single Family; PU = Planned Unit Development; CO = Condo; MH = Manufactured Housing; CP = Co-op; 99 = Not Available",
    historical_definition_changes="none",
    normalization_rule="`99` → NULL",
    baseline_decision="DÙNG",
    decision_reason="Loại tài sản ảnh hưởng khả năng thanh lý và rủi ro; biết tại khởi tạo.",
    source_reference="UG R48 'Property Type'")

col(column="property_state", role="feature", meaning="Bang/lãnh thổ của tài sản",
    source_column="property_state", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="UG: vị trí tài sản tại khởi tạo.",
    missing_codes="**không có sentinel được tài liệu hoá** (UG không định nghĩa mã 'unknown'); dữ liệu có đúng 1 NULL",
    valid_domain="54 giá trị: 50 bang + DC + PR + GU + VI; 1 NULL",
    historical_definition_changes="none",
    normalization_rule="giữ nguyên 54 giá trị + NULL; **không** gộp bang hiếm theo tần suất trước split",
    baseline_decision="DÙNG",
    decision_reason="Khác biệt vùng miền về rủi ro tín dụng và pháp lý; biết tại khởi tạo. Gộp nhóm hiếm để sau split.",
    source_reference="UG R48 'Property State'; kiểm chứng trên dữ liệu")

col(column="occupancy_status", role="feature", meaning="Mục đích cư trú",
    source_column="occupancy_status", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="UG: mục đích sử dụng tài sản tại khởi tạo.",
    missing_codes="`9` = Not Available (1 dòng)",
    valid_domain="P = Primary Residence; I = Investment Property; S = Second Home; 9 = Not Available",
    historical_definition_changes="none",
    normalization_rule="`9` → NULL",
    baseline_decision="DÙNG",
    decision_reason="Nhà đầu tư/second home có hành vi vỡ nợ khác chủ ở; biết tại khởi tạo.",
    source_reference="UG R48 'Occupancy Status'")

col(column="prepayment_penalty_flag", role="feature", meaning="Có phí trả trước",
    source_column="prepayment_penalty_flag", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="UG: điều khoản hợp đồng tại khởi tạo.",
    missing_codes="none",
    valid_domain="Y / N",
    historical_definition_changes="none",
    normalization_rule="giữ nguyên",
    baseline_decision="DÙNG",
    decision_reason="Điều khoản hợp đồng; ảnh hưởng tới lựa chọn tất toán sớm.",
    source_reference="UG R48 'Prepayment Penalty Flag'")

col(column="interest_only_indicator", role="excluded", meaning="Khoản vay chỉ trả lãi",
    source_column="interest_only_indicator", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="UG: điều khoản tại khởi tạo.",
    missing_codes="none",
    valid_domain="Y / N. **Dữ liệu này chỉ có `N`** (49.348.308/49.348.308).",
    historical_definition_changes="none",
    normalization_rule="không dùng",
    baseline_decision="LOẠI khỏi baseline",
    decision_reason="Hằng số ⇒ zero variance. Ghi lại để sau này nếu nạp thêm dữ liệu có IO loan thì xét lại.",
    source_reference="UG R48 'Interest Only Indicator'; kiểm chứng trên dữ liệu")

col(column="super_conforming_flag", role="feature", meaning="Khoản vay vượt chuẩn conforming",
    source_column="super_conforming_flag", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="UG: phân loại tại khởi tạo theo hạn mức.",
    missing_codes="none",
    valid_domain="Y / N",
    historical_definition_changes="none",
    normalization_rule="giữ nguyên",
    baseline_decision="DÙNG",
    decision_reason="Khoản vay giá trị lớn có rủi ro khác biệt; biết tại khởi tạo.",
    source_reference="UG R48 'Super Conforming Flag'")

col(column="harp_indicator", role="feature", meaning="Khoản vay thuộc chương trình HARP",
    source_column="harp_indicator", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="UG: chỉ báo khoản vay được khởi tạo theo HARP; xác định tại khởi tạo.",
    missing_codes="none",
    valid_domain="Y / N",
    historical_definition_changes="HARP chỉ tồn tại từ 2009 ⇒ `Y` chỉ xuất hiện từ cohort 2009 trở đi; trước đó toàn `N`. Đây là đặc điểm của chương trình, không phải lỗi dữ liệu.",
    normalization_rule="giữ nguyên; **bắt buộc** đọc cùng `dti` vì mọi khoản HARP có DTI = 999",
    baseline_decision="DÙNG (kèm ghi chú tương tác với dti)",
    decision_reason="Vừa là đặc trưng sản phẩm vừa là biến giải thích cho cơ chế thiếu của DTI.",
    source_reference="UG R48 'HARP Indicator'; UG 'Original DTI'")

col(column="valuation_method", role="excluded", meaning="Phương pháp định giá tài sản",
    source_column="valuation_method", semantic_type="categorical_code",
    available_at_scoring_time="không có cho phần lớn giai đoạn",
    availability_evidence="UG: 'Populated only for loans originated on or after January 1, 2017. ACE+PDR is effective for loans originated on or after July 17, 2022.' Dữ liệu xác nhận: 31.937.280 dòng trước 2017 toàn `7` (Not Available); 2017Q1–2022Q2 có 1/2/7; từ 2022Q3 có thêm `4`.",
    missing_codes="`7` = Not Available",
    valid_domain="1 = Appraisal Waiver (ACE); 2 = Appraisal; 3 = Other; 4 = ACE+PDR; 7 = Not Available",
    historical_definition_changes="**CÓ.** RN Release 26 (2021-01): thêm trường 'going back to 2017'. RN Release 35 (2023-04): thêm mã `4`. RN Release 46 (2026-01): 'codes used to describe Property Valuation Method were redefined'. Bộ mã trước Release 46: **UNVERIFIED** (không truy cập được user guide lưu trữ).",
    normalization_rule="không dùng",
    baseline_decision="LOẠI khỏi baseline",
    decision_reason="65% dòng là Not Available vì trường không tồn tại trước 2017; bộ mã lại bị định nghĩa lại ở Release 46 nên không so sánh được xuyên thời gian. Cần một nghiên cứu riêng trước khi dùng.",
    source_reference="UG R48 'Property Valuation Method'; RN Release 26, 35, 46")

col(column="seller_name", role="excluded", meaning="Tên tổ chức bán khoản vay cho Freddie Mac",
    source_column="seller_name", semantic_type="categorical_high_cardinality",
    available_at_scoring_time="chưa chứng minh được",
    availability_evidence="UG: 'The name of the entity acting as the seller of the loan to Freddie Mac **at the time of acquisition**' — về định nghĩa là biết tại thời điểm mua. NHƯNG: (a) seller dưới 1% UPB/quý bị thay bằng 'OTHER'; (b) RN Release 26 (2021-01) đổi sang 'Global Seller-Servicer family name', tức tên tập đoàn hiện tại gán ngược lên khoản vay lịch sử.",
    missing_codes="'OTHER' = bị che do dưới ngưỡng 1%, không phải thiếu thật",
    valid_domain="chuỗi tên + 'OTHER'",
    historical_definition_changes="RN Release 24 (2020-04) đổi sang chuỗi không nén; **RN Release 26 (2021-01) đổi sang tên tập đoàn Global Seller-Servicer** — đây là thay đổi hồi tố, mức độ ảnh hưởng chưa được công bố (UNVERIFIED).",
    normalization_rule="không dùng",
    baseline_decision="LOẠI khỏi baseline",
    decision_reason="Thông tin công bố tại acquisition, nhưng khả năng sẵn có đúng như lúc chấm điểm **chưa được chứng minh**: tên đã bị viết lại theo tập đoàn hiện tại ở Release 26, nên giá trị hôm nay không phải giá trị quan sát được trong quá khứ. Đây là rủi ro look-ahead, không phải 'chắc chắn leakage' — cần bằng chứng trước khi dùng.",
    source_reference="UG R48 'Seller Name'; RN Release 24, 26; FAQ Q34")

col(column="first_payment_date", role="split_metadata",
    meaning="Kỳ thanh toán đầu tiên theo lịch GỐC",
    source_column="first_payment_date", semantic_type="YYYYMM",
    available_at_scoring_time="yes — biết tại khởi tạo",
    availability_evidence="UG: 'Loan First Payment Date' là một trường của hồ sơ origination, tức có tại thời điểm khởi tạo. Nó là ngày đến hạn đầu tiên theo hợp đồng, không phải thông tin tương lai.",
    missing_codes="none (0 null / 0 giá trị không hợp lệ trên 49.348.308 dòng)",
    valid_domain="YYYYMM, 199901–202607",
    historical_definition_changes="Không đổi định nghĩa. **Nhưng** với khoản vay đã modification hoặc construction-to-perm, giá trị này có thể phản ánh ngày thanh toán đầu tiên SAU modification (FAQ Q37): đó là lý do `max(first_payment_date)` theo cohort không dùng được để suy maturity, và là lý do `cohort_mature` dùng mốc neo p99 thay vì max.",
    normalization_rule="giữ nguyên YYYYMM; dùng để suy ra cửa sổ nhãn, KHÔNG dùng làm feature",
    baseline_decision="metadata, không vào X",
    decision_reason="Không phải leakage: nó xác định cửa sổ nhãn nhưng bản thân ngày này biết trước khi khoản vay bắt đầu trả nợ. Loại khỏi X vì nó là mốc thời gian (sẽ trùng với cohort), không phải vì rò rỉ. Cần thận trọng về ý nghĩa: với khoản đã modification, giá trị có thể đã bị dịch, nên không được dùng nó như 'tuổi khoản vay tại khởi tạo'.",
    source_reference="UG R48 'Loan First Payment Date'; FAQ Q37; docs/label_rules.md §7")

col(column="maturity_date", role="excluded",
    meaning="Ngày đáo hạn theo lịch",
    source_column="maturity_date", semantic_type="YYYYMM",
    available_at_scoring_time="yes",
    availability_evidence="UG: ngày đáo hạn trên hợp đồng tại khởi tạo.",
    missing_codes="none",
    valid_domain="YYYYMM",
    historical_definition_changes="none",
    normalization_rule="không dùng",
    baseline_decision="LOẠI khỏi baseline",
    decision_reason="Trùng lặp thông tin: UG định nghĩa `original_loan_term` chính là maturity_date − first_payment_date + 1, nên maturity là tổ hợp tuyến tính của hai cột đã có. Giữ term, bỏ maturity để tránh cộng tuyến hoàn hảo.",
    source_reference="UG R48 'Loan Maturity Date'; 'Original Loan Term'")

col(column="postal_code", role="excluded", meaning="3 số đầu mã bưu chính",
    source_column="postal_code", semantic_type="categorical_high_cardinality",
    available_at_scoring_time="yes",
    availability_evidence="UG: vị trí tài sản tại khởi tạo.",
    missing_codes="`000` = Unknown",
    valid_domain="3 chữ số; 000 = Unknown",
    historical_definition_changes="none",
    normalization_rule="không dùng",
    baseline_decision="LOẠI khỏi baseline",
    decision_reason="Bản chất là định danh địa lý bậc rất cao (~900 giá trị), gần như là khoá. `property_state` đã bao phủ khía cạnh địa lý ở mức thô hơn nhưng ổn định. Dùng postal_code làm tăng nguy cơ học thuộc bản ghi mà không thêm tín hiệu rủi ro.",
    source_reference="UG R48 'Postal Code'")

col(column="msa", role="excluded", meaning="Mã vùng thống kê đô thị",
    source_column="msa", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="UG: vùng đô thị của tài sản tại khởi tạo.",
    missing_codes="không có sentinel được tài liệu hoá; dữ liệu có 11.473.268 dòng NULL (23,25%)",
    valid_domain="mã MSA; 23% NULL",
    historical_definition_changes="none",
    normalization_rule="không dùng",
    baseline_decision="LOẠI khỏi baseline",
    decision_reason="Thiếu 23% là mức quá cao cho một biến địa lý đã có `property_state` thay thế; bản chất cũng là định danh vùng. Xét lại sau khi có lý do cụ thể.",
    source_reference="UG R48 'MSA'; kiểm chứng trên dữ liệu")

col(column="pre_harp_loan_id", role="excluded", meaning="Mã khoản vay gốc trước khi vào HARP",
    source_column="pre_harp_loan_id", semantic_type="string_id",
    available_at_scoring_time="chỉ với khoản HARP",
    availability_evidence="UG: chỉ điền cho khoản vay được refinance vào HARP; không áp dụng cho khoản thường.",
    missing_codes="NULL = không áp dụng (94,19% dòng)",
    valid_domain="mã khoản vay",
    historical_definition_changes="none",
    normalization_rule="không dùng",
    baseline_decision="LOẠI khỏi baseline",
    decision_reason="94% NULL và phần không NULL là **định danh của một khoản vay khác**, không phải thuộc tính của khoản này.",
    source_reference="UG R48 'Pre-HARP Loan ID'")

col(column="program_indicator", role="excluded", meaning="Chỉ báo chương trình đặc biệt",
    source_column="program_indicator", semantic_type="categorical_code",
    available_at_scoring_time="yes",
    availability_evidence="UG: chỉ báo chương trình tại khởi tạo.",
    missing_codes="NULL = không thuộc chương trình (97,46% dòng)",
    valid_domain="mã chương trình",
    historical_definition_changes="none",
    normalization_rule="không dùng",
    baseline_decision="LOẠI khỏi baseline",
    decision_reason="97,46% NULL ⇒ gần như hằng số; phần còn lại quá nhỏ để học mà không gây overfit.",
    source_reference="UG R48 'Program Indicator'")

col(column="quarter", role="excluded", meaning="Cột partition vật lý của parquet",
    source_column="quarter", semantic_type="partition_key",
    available_at_scoring_time="n/a",
    availability_evidence="Không phải trường nghiệp vụ; là tên thư mục partition do pipeline ingest sinh ra.",
    missing_codes="n/a", valid_domain="YYYYQn",
    historical_definition_changes="none",
    normalization_rule="không dùng",
    baseline_decision="LOẠI (trùng `cohort`)",
    decision_reason="Trùng hoàn toàn với `cohort`; giữ một bản để tránh hai cột giống hệt nhau.",
    source_reference="scripts/ingest_stream.py; README")


# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------
FIELDS = ["column", "role", "meaning", "source_column", "semantic_type",
          "available_at_scoring_time", "availability_evidence", "missing_codes",
          "valid_domain", "historical_definition_changes", "normalization_rule",
          "baseline_decision", "decision_reason", "source_reference"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # guard: no duplicate columns, every column has a role, baseline ⊆ features
    names = [c["column"] for c in D]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"duplicate dictionary rows: {dupes}"
    feat = {c["column"] for c in D if c["role"] == "feature"}
    assert set(BASELINE) <= feat, f"baseline names not marked feature: {set(BASELINE) - feat}"

    with (OUT / "feature_dictionary.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for c in sorted(D, key=lambda r: (ROLES.index(r["role"]), r["column"])):
            w.writerow(c)

    # Markdown: a summary table of every column, then one section per feature
    md = ["# Feature dictionary — Gold research dataset", ""]
    md.append("Nguồn: Freddie Mac SFLLD General User Guide **Release 48** (2026-10-28), "
              "Release Notes (R1–R48), FAQ (2026-01), `file_layout_july_2026.xlsx`. "
              "Mọi sentinel dưới đây đều dẫn nguồn; chỗ nào không lấy được tài liệu thì ghi "
              "**UNVERIFIED** thay vì suy đoán.\n")
    md.append(f"Tổng số cột được khai báo: **{len(D)}**. "
              f"Baseline dùng **{len(BASELINE)}** đặc trưng.\n")

    md.append("## 1. Phân vai toàn bộ cột\n")
    md.append("| cột | vai trò | baseline | lý do ngắn |")
    md.append("| --- | --- | --- | --- |")
    for c in sorted(D, key=lambda r: (ROLES.index(r["role"]), r["column"])):
        base = "**có**" if c["column"] in BASELINE else "không"
        short = c["decision_reason"].split(". ")[0]
        if len(short) > 150:
            short = short[:147] + "…"
        md.append(f"| `{c['column']}` | {c['role']} | {base} | {short} |")

    md.append("\n## 2. Đặc trưng baseline — chi tiết\n")
    for c in D:
        if c["column"] not in BASELINE:
            continue
        md.append(f"### `{c['column']}`\n")
        for k in ("meaning", "source_column", "semantic_type",
                  "available_at_scoring_time", "availability_evidence",
                  "missing_codes", "valid_domain", "historical_definition_changes",
                  "normalization_rule", "decision_reason", "source_reference"):
            md.append(f"- **{k}**: {c[k]}")
        md.append("")

    md.append("\n## 3. Cột bị loại — chi tiết\n")
    for c in D:
        if c["role"] != "excluded":
            continue
        md.append(f"### `{c['column']}`\n")
        for k in ("meaning", "available_at_scoring_time", "availability_evidence",
                  "missing_codes", "valid_domain", "historical_definition_changes",
                  "decision_reason", "source_reference"):
            md.append(f"- **{k}**: {c[k]}")
        md.append("")

    md.append("\n## 4. Quy tắc chuẩn hoá — trước và sau split\n")
    md.append("**Được làm TRƯỚC chia tập** (xác định bằng tài liệu, không dùng thống kê của nhãn):")
    md.append("- Giải mã sentinel theo bảng trên (`9999`, `999`, `99`, `9`, `7`, `000`, `'OTHER'`).")
    md.append("- Ép kiểu và kiểm tra miền giá trị **theo giai đoạn áp dụng** (LTV/CLTV trước và sau 2018Q2).")
    md.append("- Biến dẫn xuất có công thức cố định: `has_mi`, `borrower_count_band`, `ltv_band` nếu cần.")
    md.append("- Giữ cột raw cho các cột có thay đổi định nghĩa (`number_of_borrowers_raw`).")
    md.append("")
    md.append("**KHÔNG được làm trước chia tập:**")
    md.append("- Điền median/mode. - Scaling. - Học vocabulary / gộp nhóm hiếm theo tần suất. "
              "- Chọn feature theo tương quan với nhãn. - Target encoding. - Resampling/SMOTE. "
              "- Winsorize hoặc cắt outlier.")
    md.append("")
    md.append("Lý do: mỗi phép trên đều ước lượng một tham số từ dữ liệu. Nếu ước lượng trên "
              "toàn bộ dữ liệu rồi mới chia, tham số đó đã nhìn thấy test ⇒ rò rỉ âm thầm mà "
              "không thể phát hiện bằng kiểm tra chia tập.\n")

    md.append("\n## 5. Danh sách cột cho code huấn luyện\n")
    md.append("```python")
    md.append(f"FEATURES = {BASELINE!r}")
    md.append('TARGET = "label_12m"')
    md.append('SPLIT_METADATA = ["cohort", "first_payment_date"]')
    md.append('AUDIT_ONLY = [c for c in ALL_COLUMNS if c not in FEATURES + [TARGET] + SPLIT_METADATA]')
    md.append("```")
    md.append("")
    md.append("Code huấn luyện phải đọc feature list từ file này (hoặc từ manifest), "
              "**không** tự liệt kê cột.\n")

    (OUT / "feature_dictionary.md").write_text("\n".join(md) + "\n")

    roles = {}
    for c in D:
        roles.setdefault(c["role"], []).append(c["column"])
    print(f"feature_dictionary.csv/.md written — {len(D)} columns")
    for r in ROLES:
        print(f"  {r:15s} {len(roles.get(r, [])):2d}  {' '.join(sorted(roles.get(r, [])))}")
    print(f"  baseline features: {len(BASELINE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
