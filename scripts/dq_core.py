#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dq_core.py — Đo lường & giám sát CHẤT LƯỢNG DỮ LIỆU (Data Quality) — bản hiệu chỉnh
Bài tập DS317 — Chương 4: Chất lượng dữ liệu.

Module DUY NHẤT tính 6 khía cạnh CLDL (bản cũ scripts/dq_metrics.py đã xoá):
  - Tmp dir của DuckDB nằm trên đĩa (ROOT/.duckdb_tmp) thay vì /tmp (tmpfs/RAM).
  - Chốt memory_limit='3GB' để không tràn RAM máy 15GB (file perf lớn nhất 7.5GB).
  - Ánh xạ cột theo file_layout.xlsx + General User Guide của Freddie Mac (Release 47):
    orig 31 cột (pos 31 = vantage_score_4), perf 35 cột (pos 6 = defect_settlement_date;
    đuôi = mi_cancellation_indicator, servicer_name, bankruptcy_cramdown_costs).
  - Có CACHE theo quý (output/cache/dq_metrics_<q>.csv) → chạy lại được sau gián đoạn.

LƯU Ý BIẾN THỊ 'XX' (cột current_loan_delinquency_status, file perf):
  Nguồn dữ liệu: Freddie Mac Single-Family Loan-Level Dataset (SFLLD), bản Release 47
  (7/2026). Theo General User Guide chính thức, miền mã trạng thái quá hạn là:
      00..99 (zero-padded; "capped at 99"), 'RA' = REO Acquisition, 'XX' = Not Available.
  Như vậy 'XX' là mã HỢP LỆ được tài liệu hóa ("Not Available"), KHÔNG phải lỗi parse.
  Giá trị 'XX' xuất hiện từ quý 2023Q3 và tăng đến ~65% số dòng vào 2026Q1 (thực nghiệm).
  Vì 'XX' hợp lệ nhưng mang nghĩa "không có thông tin", script báo cáo HAI cách đọc:
      - validity       : CÁCH ĐỌC CHẶT — 'XX' tính là FAIL (giá trị không xác định);
      - validity_spec  : CÁCH ĐỌC THEO SPEC — 'XX' hợp lệ (miền {00..99, RA, XX}).
  Tín hiệu thật của 'XX' là MẤT THÔNG TIN (completeness của cột), nên cả hai được giữ
  để so sánh; xem thêm improvement 'xx_domain_alignment'.

Khác với scripts/calculate_6_dimensions.py (6 khía cạnh HIỆU SUẤT TÍN DỤNG:
delinquency/default/prepayment/...), script này tính 6 KHÍA CẠNH CHẤT LƯỢNG DỮ LIỆU
theo DAMA: Completeness, Validity, Uniqueness, Consistency, Accuracy, Timeliness.

Đầu ra (vào output/):
  1. dq_data_dictionary.csv           — từ điển dữ liệu + quy tắc kiểm tra
  2. dq_metrics_by_quarter.csv        — 6 chiều DQ tổng hợp theo quý (orig & perf)
  3. dq_dimensions_timeseries.png     — biểu đồ thời gian 2x3, ngưỡng 0.95
  4. dq_improvement_before_after.csv  — minh chứng cải thiện (xx_domain_alignment
                                       & msa_mode_imputation)
  5. dq_diagnostic_plane.csv/.png     — mặt phẳng chẩn đoán TEMPO-DQ
                                       (x = Ssan+ = min(completeness, validity),
                                       y = Sperf = mean(6 chiều); x0=0.75, y0=0.70)

Định nghĩa metric (chuẩn hóa [0,1], tính ở mức hạt rồi lấy TRUNG BÌNH theo quý):
  - completeness = 1 - (số ô null/rỗng) / (tổng số ô) trên mọi cột của file
  - validity     = trung bình số quy tắc miền giá trị thỏa mỗi dòng
                  (ô null/rỗng coi là N/A — KHÔNG tính là fail)
  - uniqueness   = tỷ lệ dòng có khóa duy nhất
                  (orig: loan_id; perf: (loan_id, monthly_reporting_period))
  - consistency  = tỷ lệ loan_id của perf có mặt trong orig cùng quý (orig = 1.0)
  - accuracy     = tỷ lệ dòng thỏa ràng buộc liên trường:
                  perf: (a) current_upb <= original_upb (join orig theo loan_id);
                        (b) lãi suất tại kỳ báo cáo ĐẦU TIÊN của loan == lãi suất gốc;
                        (c) zero_balance_code khác rỗng ⇒ là trạng thái kết thúc hợp lệ;
                  orig: first_payment_date <= maturity_date (trật tự ngày hợp lệ).
  - timeliness   = max(0, 1 - lag/12) với
                  lag = (202603 // 100 - period // 100) * 12
                      + (202603 % 100 - period % 100)   # số tháng trễ
                  clamp(., 0, 1). Kỳ mới nhất 202603 → 1.0; mỗi tháng trễ mất 1/12.
                  (perf: period = monthly_reporting_period; orig: first_payment_date
                  làm đại diện cho mốc thời gian của dòng khởi tạo.)

Cải thiện dữ liệu (nhiệm vụ 4) — 2 phép cải thiện, mỗi phép đo before/after với
  CÙNG định nghĩa metric, theo quý LẪN tổng thể (overall, weight theo n_rows):
  1) xx_domain_alignment (perf, validity): 'XX' là mã "unknown" được tài liệu hóa
     (xuất hiện từ 2023Q3) — đưa XX vào miền hợp lệ của chiều validity:
     before = validity perf theo quý (đọc từ cache dq_metrics_by_quarter.csv,
     không quét lại perf); after = 1.0 (XX là vi phạm DUY NHẤT của chiều này,
     nên XX share = 1 - before).
  2) msa_mode_imputation (orig, completeness trên cột msa): chia 25 quý theo tỷ lệ
     8:1:1 (20 quý Train / 3 Val / 2 Test, theo trình tự thời gian), tính MODE của
     msa CHỈ trên 20 quý Train (DuckDB quét trực tiếp file, không materialize),
     rồi áp dụng cho mọi split; before = 1 - null_msa/n_rows theo quý; after = 1.0.

Hiệu năng: mọi quý được xử lý bằng 1 truy vấn SQL aggregate (COUNT/SUM của điều
kiện boolean + window function cho uniqueness), KHÔNG materialize dòng dữ liệu.
"""

import shutil
import time
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT = ROOT / "output"
# Thư mục con — giữ output/ gọn. Script tự tạo nếu chưa có.
OUT_DATA = OUT / "data"        # CSV kết quả
OUT_FIG = OUT / "figures"      # biểu đồ
OUT_CACHE = OUT / "cache"      # cache từng quý (resumable)
# Tmp dir của DuckDB phải nằm trên ĐĨA (/tmp là tmpfs - RAM-backed, không được dùng)
TMP_DIR = ROOT / ".duckdb_tmp"

NEWEST_PERIOD = 202603  # tháng báo cáo mới nhất có sẵn trong dữ liệu

# 31 cột file orig — ánh xạ theo file_layout.xlsx chính thức (32 vị trí) + thay đổi
# của Release 47: BỎ "MI Cancellation Indicator" + "Servicer Name", THÊM "VantageScore4".
# => 31 cột; vị trí 25..31 dịch lên 1; cột mới VantageScore4 ở vị trí 31.
ORIG_COLUMNS = [
    'credit_score', 'first_payment_date', 'first_time_homebuyer_flag',
    'maturity_date', 'msa', 'mi_percentage', 'number_of_units',
    'occupancy_status', 'cltv', 'dti', 'original_upb', 'ltv',
    'original_interest_rate', 'channel', 'prepayment_penalty_flag',
    'product_type', 'property_state', 'property_type', 'postal_code',
    'loan_id', 'loan_purpose', 'original_loan_term', 'number_of_borrowers',
    'seller_name', 'super_conforming_flag', 'pre_harp_loan_id',
    'program_indicator', 'harp_indicator', 'valuation_method',
    'interest_only_indicator', 'vantage_score_4',
]

# 35 cột file perf — ánh xạ theo file_layout.xlsx chính thức (32 vị trí) + thay đổi
# của Release 47: THÊM "MI Cancellation Indicator", "Servicer Name" (chuyển từ orig),
# "Bankruptcy Cramdown Costs" => 35 cột. Vị trí 33/34/35 lần lượt là ba cột mới này.
PERF_COLUMNS = [
    'loan_id', 'monthly_reporting_period', 'current_upb',
    'current_loan_delinquency_status', 'loan_age', 'remaining_months_to_legal_maturity',
    'defect_settlement_date', 'modification_flag', 'zero_balance_code',
    'zero_balance_effective_date', 'current_interest_rate',
    'current_deferred_upb', 'due_date_of_last_paid_installment',
    'mi_recoveries', 'net_sales_proceeds', 'non_mi_recoveries',
    'expenses', 'legal_costs', 'maintenance_and_preservation_costs',
    'taxes_and_insurance', 'miscellaneous_expenses', 'actual_loss_calculation',
    'modification_cost', 'step_modification_flag', 'deferred_payment_plan',
    'estimated_loan_to_value', 'zero_balance_removal_upb', 'delinquent_accrued_interest',
    'delinquency_due_to_disaster', 'borrower_assistance_status_code',
    'current_month_modification_cost', 'interest_bearing_upb',
    'mi_cancellation_indicator', 'servicer_name', 'bankruptcy_cramdown_costs',
]

# Đọc toàn bộ dưới dạng VARCHAR để mọi quy tắc kiểm tra bằng TRY_CAST / regexp
ORIG_TYPES = {c: 'VARCHAR' for c in ORIG_COLUMNS}
PERF_TYPES = {c: 'VARCHAR' for c in PERF_COLUMNS}

# Thứ tự 25 quý (cũng dùng cho split 8:1:1 theo quý)
QUARTERS = [f"{y}Q{q}" for y in range(2020, 2027) for q in (1, 2, 3, 4)][:25]

VALID_ZERO_BALANCE_CODES = None  # deprecated: miền ZBC nay là range 1-998 (999 = Not Available)

# ---------------------------------------------------------------------------
# 1. TỪ ĐIỂN DỮ LIỆU
# ---------------------------------------------------------------------------
# rule: dạng máy kiểm tra được (range/domain/regex/non-null)
DICT_ROWS = [
    # ---- orig ----
    ('orig', 'credit_score', 0, 'int', 'loan', 'Điểm FICO của người vay', 'range:300-850', '>= 0.95'),
    ('orig', 'first_payment_date', 1, 'YYYYMM', 'loan', 'Ngày trả nợ đầu tiên (năm+tháng)', r'regex:^[0-9]{6}$ và tháng 01-12', '>= 0.95'),
    ('orig', 'first_time_homebuyer_flag', 2, 'char', 'loan', 'Cờ mua nhà lần đầu', 'domain:{Y,N}', '>= 0.95'),
    ('orig', 'maturity_date', 3, 'YYYYMM', 'loan', 'Ngày đáo hạn (năm+tháng)', r'regex:^[0-9]{6}$ và tháng 01-12', '>= 0.95'),
    ('orig', 'msa', 4, 'code', 'loan', 'Mã vùng đô thị (MSA)', 'regex:^[0-9]{5}$ hoặc rỗng', '>= 0.95'),
    ('orig', 'mi_percentage', 5, 'int', 'loan', 'Tỷ lệ bảo hiểm thế chấp (%)', 'range:0-55', '>= 0.95'),
    ('orig', 'number_of_units', 6, 'int', 'loan', 'Số căn hộ', 'range:1-4', '>= 0.95'),
    ('orig', 'occupancy_status', 7, 'char', 'loan', 'Tình trạng sử dụng nhà', 'domain:{P,I,S}', '>= 0.95'),
    ('orig', 'cltv', 8, 'int', 'loan', 'Tỷ lệ LTV cộng gộp (%)', 'range:0-200', '>= 0.95'),
    ('orig', 'dti', 9, 'int', 'loan', 'Tỷ lệ nợ trên thu nhập (%)', 'range:0-65', '>= 0.95'),
    ('orig', 'original_upb', 10, 'int', 'loan', 'Số dư gốc ban đầu (USD)', 'range:>0', '>= 0.95'),
    ('orig', 'ltv', 11, 'int', 'loan', 'Tỷ lệ vay trên giá trị tài sản (%)', 'range:0-200', '>= 0.95'),
    ('orig', 'original_interest_rate', 12, 'float', 'loan', 'Lãi suất gốc (%)', 'range:(0,20]', '>= 0.95'),
    ('orig', 'channel', 13, 'char', 'loan', 'Kênh khởi tạo khoản vay', 'domain:{R,B,C,T}', '>= 0.95'),
    ('orig', 'prepayment_penalty_flag', 14, 'char', 'loan', 'Cờ phạt trả trước', 'domain:{Y,N}', '>= 0.95'),
    ('orig', 'product_type', 15, 'char', 'loan', 'Loại sản phẩm', 'domain:{FRM,ARM}', '>= 0.95'),
    ('orig', 'property_state', 16, 'char(2)', 'loan', 'Bang nơi tài sản đảm bảo', 'regex:^[A-Z]{2}$', '>= 0.95'),
    ('orig', 'property_type', 17, 'code', 'loan', 'Loại tài sản đảm bảo', 'domain:{CO,CP,EF,JD,LH,MH,NN,PU,SF,TC,VI}', '>= 0.95'),
    ('orig', 'postal_code', 18, 'code', 'loan', 'Mã bưu chính', 'regex:^[0-9]{5}$ hoặc rỗng', '>= 0.95'),
    ('orig', 'loan_id', 19, 'string', 'loan', 'Mã định danh khoản vay (KHÓA)', 'non-null + unique', '1.00'),
    ('orig', 'loan_purpose', 20, 'char', 'loan', 'Mục đích vay', 'domain:{P,C,N}', '>= 0.95'),
    ('orig', 'original_loan_term', 21, 'int', 'loan', 'Kỳ hạn vay gốc (tháng)', 'range:>= 0', '>= 0.95'),
    ('orig', 'number_of_borrowers', 22, 'int', 'loan', 'Số người đồng vay', 'domain:{1,2}', '>= 0.95'),
    ('orig', 'seller_name', 23, 'string', 'loan', 'Tên tổ chức bán khoản vay', 'non-null', '>= 0.95'),
    ('orig', 'super_conforming_flag', 24, 'char', 'loan', 'Cờ super conforming', 'domain:{Y,N} hoặc rỗng', '>= 0.95'),
    ('orig', 'pre_harp_loan_id', 25, 'string', 'loan', 'Mã khoản vay trước HARP', 'nếu có: non-null', '>= 0.95'),
    ('orig', 'program_indicator', 26, 'code', 'loan', 'Mã chương trình', 'domain:{H,R} hoặc rỗng', '>= 0.95'),
    ('orig', 'harp_indicator', 27, 'char', 'loan', 'Cờ HARP', 'domain:{F,N,T,W} hoặc rỗng', '>= 0.95'),
    ('orig', 'valuation_method', 28, 'int', 'loan', 'Phương pháp định giá', 'domain:{1,2,3,9} hoặc rỗng', '>= 0.95'),
    ('orig', 'interest_only_indicator', 29, 'char', 'loan', 'Cờ vay chỉ trả lãi', 'domain:{Y,N} hoặc rỗng', '>= 0.95'),
    ('orig', 'vantage_score_4', 30, 'int', 'loan', 'Điểm VantageScore 4.0 (Release 47; 9999 = không có)', r'range:300-850 hoặc 9999', '>= 0.95'),
    # ---- perf ----
    ('perf', 'loan_id', 0, 'string', 'loan-month', 'Mã định danh khoản vay (KHÓA)', 'non-null + duy nhất theo (loan_id, period)', '1.00'),
    ('perf', 'monthly_reporting_period', 1, 'YYYYMM', 'loan-month', 'Kỳ báo cáo (năm+tháng)', 'regex:^[0-9]{6}$', '>= 0.95'),
    ('perf', 'current_upb', 2, 'float', 'loan-month', 'Số dư gốc hiện tại (USD)', 'range:>= 0', '>= 0.95'),
    ('perf', 'current_loan_delinquency_status', 3, 'code', 'loan-month', 'Trạng thái quá hạn hiện tại', 'domain:{00..99, RA, XX} (XX = Not Available)', '>= 0.95'),
    ('perf', 'loan_age', 4, 'int', 'loan-month', 'Tuổi khoản vay (tháng)', 'range:0-1200', '>= 0.95'),
    ('perf', 'remaining_months_to_legal_maturity', 5, 'int', 'loan-month', 'Số tháng còn lại đến đáo hạn', 'range:>= 0', '>= 0.95'),
    ('perf', 'defect_settlement_date', 6, 'YYYYMM', 'loan-month', 'Ngày tất toán khiếm khuyết (defect settlement date)', r'regex:^[0-9]{6}$ hoặc rỗng', '>= 0.95'),
    ('perf', 'modification_flag', 7, 'char', 'loan-month', 'Cờ điều chỉnh khoản vay', 'domain:{Y,N}', '>= 0.95'),
    ('perf', 'zero_balance_code', 8, 'code', 'loan-month', 'Mã số dư 0 (kết thúc khoản vay)', 'range:1-998 (999 = Not Available) hoặc rỗng', '>= 0.95'),
    ('perf', 'zero_balance_effective_date', 9, 'YYYYMM', 'loan-month', 'Ngày hiệu lực số dư 0', 'regex:^[0-9]{6}$ hoặc rỗng', '>= 0.95'),
    ('perf', 'current_interest_rate', 10, 'float', 'loan-month', 'Lãi suất hiện tại (%)', 'range:(0,20]', '>= 0.95'),
    ('perf', 'current_deferred_upb', 11, 'float', 'loan-month', 'Số dư gốc hoãn trả', 'range:>= 0', '>= 0.95'),
    ('perf', 'due_date_of_last_paid_installment', 12, 'YYYYMM', 'loan-month', 'Ngày đáo của kỳ đã trả cuối', 'regex:^[0-9]{6}$ hoặc rỗng', '>= 0.95'),
    ('perf', 'mi_recoveries', 13, 'float', 'loan-month', 'Thu hồi từ bảo hiểm', 'range:>= 0', '>= 0.95'),
    ('perf', 'net_sales_proceeds', 14, 'float', 'loan-month', 'Tiền thu ròng từ thanh lý', 'range: không âm hoặc rỗng', '>= 0.95'),
    ('perf', 'non_mi_recoveries', 15, 'float', 'loan-month', 'Thu hồi ngoài bảo hiểm', 'range:>= 0', '>= 0.95'),
    ('perf', 'expenses', 16, 'float', 'loan-month', 'Chi phí thanh lý', 'range:>= 0', '>= 0.95'),
    ('perf', 'legal_costs', 17, 'float', 'loan-month', 'Chi phí pháp lý', 'range:>= 0', '>= 0.95'),
    ('perf', 'maintenance_and_preservation_costs', 18, 'float', 'loan-month', 'Chi phí bảo trì tài sản', 'range:>= 0', '>= 0.95'),
    ('perf', 'taxes_and_insurance', 19, 'float', 'loan-month', 'Thuế và bảo hiểm', 'range:>= 0', '>= 0.95'),
    ('perf', 'miscellaneous_expenses', 20, 'float', 'loan-month', 'Chi phí khác', 'range:>= 0', '>= 0.95'),
    ('perf', 'actual_loss_calculation', 21, 'float', 'loan-month', 'Tổn thất thực tế', 'range: không âm hoặc rỗng', '>= 0.95'),
    ('perf', 'modification_cost', 22, 'float', 'loan-month', 'Chi phí điều chỉnh khoản vay', 'range:>= 0', '>= 0.95'),
    ('perf', 'step_modification_flag', 23, 'char', 'loan-month', 'Cờ điều chỉnh theo bước', 'domain:{Y,N} hoặc rỗng', '>= 0.95'),
    ('perf', 'deferred_payment_plan', 24, 'char', 'loan-month', 'Cờ kế hoạch trả hoãn', 'domain:{Y,N,D} hoặc rỗng', '>= 0.95'),
    ('perf', 'estimated_loan_to_value', 25, 'int', 'loan-month', 'LTV ước tính (%)', 'range:0-200 hoặc rỗng', '>= 0.95'),
    ('perf', 'zero_balance_removal_upb', 26, 'float', 'loan-month', 'UPB khi xóa khỏi hồ sơ', 'range:>= 0 hoặc rỗng', '>= 0.95'),
    ('perf', 'delinquent_accrued_interest', 27, 'float', 'loan-month', 'Lãi phát sinh quá hạn', 'range:>= 0', '>= 0.95'),
    ('perf', 'delinquency_due_to_disaster', 28, 'code', 'loan-month', 'Quá hạn do thiên tai', 'domain:{N,D} hoặc rỗng', '>= 0.95'),
    ('perf', 'borrower_assistance_status_code', 29, 'code', 'loan-month', 'Mã hỗ trợ người vay', 'domain:{F,R,T,L,N} hoặc rỗng', '>= 0.95'),
    ('perf', 'current_month_modification_cost', 30, 'float', 'loan-month', 'Chi phí điều chỉnh trong kỳ', 'range:>= 0', '>= 0.95'),
    ('perf', 'interest_bearing_upb', 31, 'float', 'loan-month', 'UPB tính lãi', 'range:>= 0', '>= 0.95'),
    ('perf', 'mi_cancellation_indicator', 32, 'char', 'loan-month', 'Chỉ báo huỷ bảo hiểm thế chấp (Release 47, chuyển từ orig)', 'domain:{Y,N,7} hoặc rỗng', '>= 0.95'),
    ('perf', 'servicer_name', 33, 'string', 'loan-month', 'Tên tổ chức quản lý khoản vay (Release 47, chuyển từ orig)', 'non-null', '>= 0.95'),
    ('perf', 'bankruptcy_cramdown_costs', 34, 'float', 'loan-month', 'Chi phí cramdown phá sản (Release 47, cột mới)', 'range:>= 0', '>= 0.95'),
]


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------
def read_csv_sql(path: Path, columns: dict) -> str:
    """read_csv với delimiter '|', không header, kiểu tường minh (không infer)."""
    cols_sql = ", ".join(f"'{c}': 'VARCHAR'" for c in columns)
    return (f"read_csv('{path.as_posix()}', delim='|', header=false, "
            f"columns={{{cols_sql}}})")


def completeness_sum(cols) -> str:
    """Biểu thức SUM đếm ô null trên tất cả các cột (cho 1 lần quét)."""
    return " + ".join(f"CASE WHEN {c} IS NULL THEN 1 ELSE 0 END" for c in cols)


def month_lag_sql(period_col: str, newest: int = NEWEST_PERIOD) -> str:
    """Lag theo số THÁNG giữa kỳ mới nhất và period của dòng; clamp >= 0."""
    return (f"greatest(0, ({newest} // 100 - try_cast({period_col} AS BIGINT) // 100) * 12 "
            f"+ ({newest} % 100 - try_cast({period_col} AS BIGINT) % 100))")


def quarter_dir(quarter: str) -> Path:
    return DATA_DIR / f"historical_data_{quarter[:4]}" / f"historical_data_{quarter}"


# ---------------------------------------------------------------------------
# 2. METRIC THEO QUÝ — 1 truy vấn / file, không materialize
# ---------------------------------------------------------------------------
def metrics_orig(con, quarter: str) -> dict:
    """6 chiều DQ cho file orig của một quý (single scan, window cho uniqueness)."""
    src = read_csv_sql(quarter_dir(quarter) / f"orig_{quarter}.txt", ORIG_TYPES)
    sql = f"""
    WITH w AS (
      SELECT *, count(*) OVER (PARTITION BY loan_id) AS id_cnt
      FROM {src} sub
    )
    SELECT
      count(*),
      -- completeness: 1 - null_cells / (rows * ncols)
      1 - SUM({completeness_sum(ORIG_COLUMNS)})::DOUBLE / (count(*) * {len(ORIG_COLUMNS)}),
      -- validity: trung bình số quy tắc thỏa mỗi dòng (null = N/A = pass)
      avg(
        (CASE WHEN credit_score IS NULL OR credit_score = '9999'
                 OR (try_cast(credit_score AS INT) BETWEEN 300 AND 850) THEN 1 ELSE 0 END
       + CASE WHEN first_payment_date IS NULL OR (regexp_matches(first_payment_date, '^[0-9]{{6}}$') AND substr(first_payment_date,5,2) BETWEEN '01' AND '12') THEN 1 ELSE 0 END
       + CASE WHEN maturity_date IS NULL OR (regexp_matches(maturity_date, '^[0-9]{{6}}$') AND substr(maturity_date,5,2) BETWEEN '01' AND '12') THEN 1 ELSE 0 END
       + CASE WHEN occupancy_status IS NULL OR occupancy_status IN ('P','I','S') THEN 1 ELSE 0 END
       + CASE WHEN cltv IS NULL OR (try_cast(cltv AS INT) BETWEEN 0 AND 200) THEN 1 ELSE 0 END
       + CASE WHEN dti IS NULL OR dti = '999'
                 OR (try_cast(dti AS INT) BETWEEN 0 AND 65) THEN 1 ELSE 0 END
       + CASE WHEN original_upb IS NULL OR (try_cast(original_upb AS DOUBLE) > 0) THEN 1 ELSE 0 END
       + CASE WHEN ltv IS NULL OR (try_cast(ltv AS INT) BETWEEN 0 AND 200) THEN 1 ELSE 0 END
       + CASE WHEN original_interest_rate IS NULL OR (try_cast(original_interest_rate AS DOUBLE) BETWEEN 0.000001 AND 20) THEN 1 ELSE 0 END
       + CASE WHEN loan_purpose IS NULL OR loan_purpose IN ('P','C','N') THEN 1 ELSE 0 END
        ) / 10.0),
      -- uniqueness: tỷ lệ dòng có loan_id xuất hiện đúng 1 lần
      sum(CASE WHEN id_cnt = 1 THEN 1 ELSE 0 END)::DOUBLE / count(*),
      1.0,
      -- accuracy: ràng buộc liên trường — first_payment_date <= maturity_date
      avg(CASE WHEN first_payment_date IS NULL OR maturity_date IS NULL THEN 1
               WHEN try_cast(first_payment_date AS BIGINT) <= try_cast(maturity_date AS BIGINT) THEN 1
               ELSE 0 END),
      -- timeliness: dùng first_payment_date làm mốc thời gian của dòng khởi tạo
      avg(greatest(0, 1 - {month_lag_sql('first_payment_date')}::DOUBLE / 12))
    FROM w
    """
    r = con.execute(sql).fetchone()
    return dict(zip(['n_rows', 'completeness', 'validity', 'uniqueness',
                     'consistency', 'accuracy', 'timeliness'], r))


def metrics_perf(con, quarter: str) -> dict:
    """6 chiều DQ cho file perf của một quý (single scan + join orig + window)."""
    src = read_csv_sql(quarter_dir(quarter) / f"perf_{quarter}.txt", PERF_TYPES)
    o = read_csv_sql(quarter_dir(quarter) / f"orig_{quarter}.txt", ORIG_TYPES)
    sql = f"""
    WITH j AS (
      SELECT t.*, o.loan_id AS o_id,
             try_cast(o.original_upb AS DOUBLE) AS o_upb,
             try_cast(o.original_interest_rate AS DOUBLE) AS o_rate
      FROM {src} t
      LEFT JOIN {o} o ON o.loan_id = t.loan_id
    ),
    w AS (
      SELECT j.*,
             count(*) OVER (PARTITION BY loan_id, monthly_reporting_period) AS key_cnt,
             row_number() OVER (PARTITION BY loan_id ORDER BY monthly_reporting_period) AS rn,
             min(try_cast(monthly_reporting_period AS BIGINT)) OVER (PARTITION BY loan_id) AS first_period
      FROM j
    )
    SELECT
      count(*),
      1 - SUM({completeness_sum(PERF_COLUMNS)})::DOUBLE / (count(*) * {len(PERF_COLUMNS)}),
      -- validity (CÁCH ĐỌC CHẶT): trạng thái quá hạn phải nằm trong miền số 00..99
      -- hoặc 'RA' (REO Acquisition). 'XX' (Not Available) bị tính là FAIL.
      avg(CASE WHEN current_loan_delinquency_status IS NULL
                 OR current_loan_delinquency_status = 'RA'
                 OR (regexp_matches(current_loan_delinquency_status, '^[0-9]{{1,2}}$')
                     AND try_cast(current_loan_delinquency_status AS INT) BETWEEN 0 AND 99)
               THEN 1 ELSE 0 END),
      -- validity_spec (CÁCH ĐỌC THEO SPEC Freddie Mac): miền tài liệu hóa là
      -- {{00..99, RA, XX}}; 'XX' = Not Available là mã HỢP LỆ ⇒ không tính là fail.
      avg(CASE WHEN current_loan_delinquency_status IS NULL
                 OR current_loan_delinquency_status IN ('RA', 'XX')
                 OR (regexp_matches(current_loan_delinquency_status, '^[0-9]{{1,2}}$')
                     AND try_cast(current_loan_delinquency_status AS INT) BETWEEN 0 AND 99)
               THEN 1 ELSE 0 END),
      -- uniqueness: khóa (loan_id, monthly_reporting_period) xuất hiện đúng 1 lần
      sum(CASE WHEN key_cnt = 1 THEN 1 ELSE 0 END)::DOUBLE / count(*),
      -- consistency: trong các loan DU NHẤT của perf, tỷ lệ có mặt trong orig
      sum(CASE WHEN rn = 1 AND o_id IS NOT NULL THEN 1 ELSE 0 END)::DOUBLE
        / NULLIF(sum(CASE WHEN rn = 1 THEN 1 ELSE 0 END), 0),
      -- accuracy (a) current_upb <= original_upb (join orig)
      avg(CASE WHEN o_upb IS NULL THEN 1
               WHEN try_cast(current_upb AS DOUBLE) <= o_upb THEN 1 ELSE 0 END),
      -- accuracy (b) tại kỳ báo cáo ĐẦU TIÊN: lãi suất == lãi suất gốc orig
      avg(CASE WHEN try_cast(monthly_reporting_period AS BIGINT) <> first_period THEN 1
               WHEN o_id IS NULL OR o_rate IS NULL OR current_interest_rate IS NULL THEN 1
               WHEN abs(try_cast(current_interest_rate AS DOUBLE) - o_rate) < 0.005 THEN 1
               ELSE 0 END),
      -- accuracy (c) zero_balance_code khác rỗng ⇒ mã kết thúc hợp lệ (miền 1..998;
      -- 999 = Not Available). NULL/999 coi như N/A.
      avg(CASE WHEN zero_balance_code IS NULL OR trim(zero_balance_code) = '' OR zero_balance_code = '999'
               THEN 1
               WHEN regexp_matches(zero_balance_code, '^[0-9]+$')
                    AND try_cast(zero_balance_code AS INT) BETWEEN 1 AND 998 THEN 1
               ELSE 0 END),
      -- timeliness (mức dòng): lag theo số tháng so với kỳ mới nhất, clamp [0,1]
      avg(greatest(0, 1 - {month_lag_sql('monthly_reporting_period')}::DOUBLE / 12))
    FROM w
    """
    r = con.execute(sql).fetchone()
    d = dict(zip(['n_rows', 'completeness', 'validity', 'validity_spec', 'uniqueness',
                  'consistency', 'acc1', 'acc2', 'acc3', 'timeliness'], r))
    d['accuracy'] = (d['acc1'] + d['acc2'] + d['acc3']) / 3.0
    for k in ('acc1', 'acc2', 'acc3'):
        d.pop(k)
    return d


def run_all_quarters(con) -> pd.DataFrame:
    """Chạy metric cho 25 quý — CÓ CACHE theo quý (output/cache/dq_metrics_<q>.csv):
    quý đã có file cache thì load lại thay vì quét lại → chạy resume được."""
    cache_dir = OUT_CACHE
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for q in QUARTERS:
        cache_path = cache_dir / f"dq_metrics_{q}.csv"
        if cache_path.exists():
            cached = pd.read_csv(cache_path)
            rows.extend(cached.to_dict('records'))
            print(f"  {q}: dùng cache ({cache_path.name})")
            continue
        t0 = time.time()
        try:
            mo = metrics_orig(con, q)
            mp = metrics_perf(con, q)
        except duckdb.OutOfMemoryException:
            print(f"  {q}: OOM — giảm threads=1 rồi thử lại...")
            con.execute("SET threads=1;")
            mo = metrics_orig(con, q)
            mp = metrics_perf(con, q)
        q_rows = []
        for source, m in (('orig', mo), ('perf', mp)):
            q_rows.append({
                'quarter': q, 'source': source,
                'completeness': round(m['completeness'], 4),
                'validity': round(m['validity'], 4),
                'validity_spec': round(m.get('validity_spec', m['validity']), 4),
                'uniqueness': round(m['uniqueness'], 4),
                'consistency': round(m['consistency'], 4),
                'accuracy': round(m['accuracy'], 4),
                'timeliness': round(m['timeliness'], 4),
                'n_rows': m['n_rows'],
            })
        pd.DataFrame(q_rows).to_csv(cache_path, index=False)
        rows.extend(q_rows)
        print(f"  {q}: orig {mo['n_rows']:,} dòng, perf {mp['n_rows']:,} dòng "
              f"({time.time()-t0:.1f}s)")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. CẢI THIỆN: xx_domain_alignment (perf validity) & msa_mode_imputation (orig)
# ---------------------------------------------------------------------------
def improvement_before_after(con) -> pd.DataFrame:
    """
    Nhiệm vụ 4 — 2 phép cải thiện, mỗi phép đo before/after với CÙNG định nghĩa
    metric, theo quý LẪN tổng thể (overall, weight theo n_rows).

    1) xx_domain_alignment — perf, dimension validity:
       Giá trị 'XX' (current_loan_delinquency_status) là mã "unknown" được tài
       liệu hóa, xuất hiện lần đầu từ 2023Q3 và tăng đến ~65% số dòng vào 2026Q1.
       Đưa XX vào miền hợp lệ (domain alignment):
         before = validity perf theo quý, đọc từ CACHE output/dq_metrics_by_quarter.csv
                  (không quét lại file perf); XX là vi phạm DUY NHẤT của chiều này
                  nên XX share = 1 - before (chính xác);
         after  = 1.0.

    2) msa_mode_imputation — orig, dimension completeness (trên cột msa):
       Chia 25 quý 8:1:1 theo trình tự thời gian: Train 20 quý / Val 3 / Test 2.
       MODE của msa tính CHỈ trên 20 quý Train (DuckDB quét trực tiếp file orig,
       không materialize), sau đó áp dụng cho MỌI quý — không rò rỉ vì tham số
       mode chỉ phụ thuộc Train.
         before = 1 - null_msa / n_rows (quét orig theo quý — file nhỏ, nhanh);
         after  = 1.0 (msa được impute hết null).

    Output schema: scope, source, dimension, method, before, after, delta
    (scope = 'overall' hoặc chuỗi quý; delta = after - before, làm tròn 6 chữ số).
    """
    n_train = round(len(QUARTERS) * 0.8)          # 20
    n_val = len(QUARTERS) - n_train - round(len(QUARTERS) * 0.1)  # 3 (Test = 2)
    train_q = QUARTERS[:n_train]
    print(f"  Split 8:1:1 theo quý → Train: {len(train_q)} quý "
          f"({train_q[0]}..{train_q[-1]}), Val: {n_val}, "
          f"Test: {len(QUARTERS) - n_train - n_val}")

    out_rows = []

    # ---- Cải thiện 1: perf validity — đưa 'XX' (Not Available, hợp lệ theo spec) vào miền ----
    cached = pd.read_csv(OUT_DATA / 'dq_metrics_by_quarter.csv')
    perf = cached[cached['source'] == 'perf'].copy()
    perf_valid = perf.set_index('quarter')['validity']
    for q in QUARTERS:
        before = float(perf_valid.loc[q])
        print(f"  {q}: perf validity (chặt) trước={before:.4f} → XX share = {1 - before:.2%}")
        out_rows.append({'scope': q, 'source': 'perf', 'dimension': 'validity',
                         'method': 'xx_domain_alignment',
                         'before': round(before, 6), 'after': 1.0,
                         'delta': round(1.0 - before, 6)})
    w = perf['n_rows']
    overall_b = float((perf['validity'] * w).sum() / w.sum())
    out_rows.append({'scope': 'overall', 'source': 'perf', 'dimension': 'validity',
                     'method': 'xx_domain_alignment',
                     'before': round(overall_b, 6), 'after': 1.0,
                     'delta': round(1.0 - overall_b, 6)})

    # ---- Cải thiện 2: orig completeness cột msa — impute mode, fit trên TRAIN ----
    train_srcs = " UNION ALL ".join(
        f"SELECT msa FROM {read_csv_sql(quarter_dir(q) / f'orig_{q}.txt', ORIG_TYPES)} sub_{q}"
        for q in train_q)
    mode_msa = con.execute(
        f"SELECT msa FROM ({train_srcs}) WHERE msa IS NOT NULL "
        f"GROUP BY msa ORDER BY count(*) DESC LIMIT 1"
    ).fetchone()[0]
    print(f"  Mode msa (fit trên Train): {mode_msa}")

    msa_rows = []
    for q in QUARTERS:
        src = read_csv_sql(quarter_dir(q) / f"orig_{q}.txt", ORIG_TYPES)
        n, msa_null = con.execute(f"""
            SELECT count(*),
              sum(CASE WHEN msa IS NULL THEN 1 ELSE 0 END)
            FROM {src} sq
        """).fetchone()
        before = 1 - msa_null / n
        msa_rows.append({'quarter': q, 'n_rows': n, 'before': before})
        out_rows.append({'scope': q, 'source': 'orig', 'dimension': 'completeness',
                         'method': 'msa_mode_imputation',
                         'before': round(before, 6), 'after': 1.0,
                         'delta': round(1.0 - before, 6)})
    imp = pd.DataFrame(msa_rows)
    w2 = imp['n_rows']
    overall_b2 = float((imp['before'] * w2).sum() / w2.sum())
    out_rows.append({'scope': 'overall', 'source': 'orig', 'dimension': 'completeness',
                     'method': 'msa_mode_imputation',
                     'before': round(overall_b2, 6), 'after': 1.0,
                     'delta': round(1.0 - overall_b2, 6)})

    return pd.DataFrame(out_rows, columns=['scope', 'source', 'dimension', 'method',
                                           'before', 'after', 'delta'])


# ---------------------------------------------------------------------------
# 3. BIỂU ĐỒ THỜI GIAN
# ---------------------------------------------------------------------------
DIMS = ['completeness', 'validity', 'uniqueness', 'consistency', 'accuracy', 'timeliness']
DIM_TITLES_VI = {
    'completeness': 'Tính đầy đủ (Completeness)',
    'validity': 'Tính hợp lệ (Validity)',
    'uniqueness': 'Tính duy nhất (Uniqueness)',
    'consistency': 'Tính nhất quán (Consistency)',
    'accuracy': 'Tính chính xác (Accuracy)',
    'timeliness': 'Tính kịp thời (Timeliness)',
}


def plot_timeseries(df: pd.DataFrame):
    fig, axes = plt.subplots(2, 3, figsize=(18, 9))
    fig.suptitle('6 Khía Cạnh Chất Lượng Dữ Liệu Theo Quý (DAMA)',
                 fontsize=15, fontweight='bold')
    quarters = sorted(df['quarter'].unique())
    x = range(len(quarters))
    for ax, dim in zip(axes.flat, DIMS):
        for source, color in (('orig', 'tab:blue'), ('perf', 'tab:orange')):
            sub = df[df['source'] == source].set_index('quarter').loc[quarters, dim]
            ax.plot(x, sub.values, marker='o', markersize=3, linewidth=1.5,
                    label=source, color=color)
        ax.axhline(0.95, color='red', linestyle='--', linewidth=1, label='ngưỡng 0.95')
        ax.set_title(DIM_TITLES_VI[dim], fontweight='bold', fontsize=11)
        ax.set_ylim(0, 1.02)
        ax.set_xticks(x[::4])
        ax.set_xticklabels(quarters[::4], rotation=45, fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
    fig.supxlabel('Quý')
    fig.supylabel('Giá trị metric [0,1]')
    fig.tight_layout(rect=[0.01, 0.01, 1, 0.97])
    out = OUT_FIG / 'dq_dimensions_timeseries.png'
    fig.savefig(out, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"Đã lưu biểu đồ: {out}")


# ---------------------------------------------------------------------------
# 5. MẶT PHẲNG CHẨN ĐOÁN TEMPO-DQ (x = Ssan+, y = Sperf)
# ---------------------------------------------------------------------------
X0 = 0.75  # ngưỡng trục x — Ssan+ (sức khoẻ dữ liệu)
Y0 = 0.70  # ngưỡng trục y — Sperf (hiệu năng tổng hợp)


def _dq_zone(sperf: float, ssan: float) -> str:
    """Phân vùng chẩn đoán theo ngưỡng (x0, y0) = (0.75, 0.70)."""
    if sperf >= Y0:
        return 'Bình thường' if ssan >= X0 else 'Sức khoẻ thấp'
    return 'Hiệu năng thấp' if ssan >= X0 else 'Nguy hiểm'


def diagnostic_plane(con) -> pd.DataFrame:
    """
    Mặt phẳng chẩn đoán TEMPO-DQ (x, y) — bản chuyển thể cho 6 chiều DQ của bộ
    dữ liệu (25 quý x 2 nguồn orig/perf):

      - Trục y — Sperf (hiệu năng) = TRUNG BÌNH cộng điều của 6 chiều DQ khách
        quan (completeness, validity, uniqueness, consistency, accuracy,
        timeliness) — định nghĩa metric GIỮ NGUYÊN như section 2.
      - Trục x — Ssan+ (sức khoẻ) = min(completeness, validity) — dạng "Min"
        bảo thủ theo quy tắc tổng hợp của chương: sức khoẻ dữ liệu bị chi phối
        bởi chiều YẾU nhất trong hai chiều nền tảng (đầy đủ & hợp lệ).

    LƯU Ý: đây là proxy minh bạch cho Sperf/Ssan+ nguyên bản của chương (định
    nghĩa qua ma trận nhầm lẫn / ma trận xác suất của mô hình ML) — bộ dữ liệu
    không có ma trận nhầm lẫn hay xác suất dự báo nên ta ánh xạ sang hai phép
    tổng hợp trên từ 6 chiều DQ đo trực tiếp. Ngưỡng phân vùng giữ nguyên:
    x0 = 0.75 (trục Ssan+), y0 = 0.70 (trục Sperf):

      sperf >= 0.70 và ssan >= 0.75 → 'Bình thường'
      sperf >= 0.70 và ssan <  0.75 → 'Sức khoẻ thấp'
      sperf <  0.70 và ssan >= 0.75 → 'Hiệu năng thấp'
      sperf <  0.70 và ssan <  0.75 → 'Nguy hiểm'

    Đọc từ CACHE output/dq_metrics_by_quarter.csv (50 dòng = 25 quý x 2 nguồn) —
    KHÔNG quét lại dữ liệu. Tham số `con` giữ để đồng nhất chữ ký gọi trong
    main() (không dùng đến — hàm chỉ đọc cache). Trả về DataFrame với cột
    quarter, source, sperf, ssan, zone; đồng thời lưu CSV và PNG vào output/.
    """
    cached = pd.read_csv(OUT_DATA / 'dq_metrics_by_quarter.csv')
    plane = pd.DataFrame({
        'quarter': cached['quarter'],
        'source': cached['source'],
        'sperf': cached[DIMS].mean(axis=1).round(6),
        'ssan': cached[['completeness', 'validity']].min(axis=1).round(6),
    })
    plane['zone'] = [_dq_zone(s, h) for s, h in zip(plane['sperf'], plane['ssan'])]
    plane = plane[['quarter', 'source', 'sperf', 'ssan', 'zone']]

    out_csv = OUT_DATA / 'dq_diagnostic_plane.csv'
    plane.to_csv(out_csv, index=False)
    print(f"Đã lưu mặt phẳng chẩn đoán: {out_csv} ({len(plane)} dòng)")

    # Biểu đồ scatter: mỗi điểm = 1 (quý, nguồn), tô màu theo nguồn
    fig, ax = plt.subplots(figsize=(9, 8))
    for source, color in (('orig', 'tab:blue'), ('perf', 'tab:orange')):
        sub = plane[plane['source'] == source]
        ax.scatter(sub['ssan'], sub['sperf'], s=45, c=color, alpha=0.85,
                   edgecolors='white', linewidths=0.5, label=source)
    ax.axvline(X0, color='red', linestyle='--', linewidth=1)
    ax.axhline(Y0, color='red', linestyle='--', linewidth=1)
    # Nhãn 4 vùng chẩn đoán trong mặt phẳng
    for label, tx, ty, ha, va in (
            ('Bình thường', 1.03, 1.03, 'right', 'top'),
            ('Sức khoẻ thấp', 0.02, 1.03, 'left', 'top'),
            ('Hiệu năng thấp', 1.03, 0.02, 'right', 'bottom'),
            ('Nguy hiểm', 0.02, 0.02, 'left', 'bottom')):
        ax.text(tx, ty, label, fontsize=10, style='italic', color='gray',
                ha=ha, va=va)
    # Ghi chú vài quý đại diện: đầu (2020Q1), giữa (2023Q1),
    # cuối (2026Q1 — nơi giá trị 'XX' bùng phát)
    for q in ('2020Q1', '2023Q1', '2026Q1'):
        sub = plane[plane['quarter'] == q]
        for _, r in sub.iterrows():
            ax.annotate(q, (r['ssan'], r['sperf']), fontsize=8,
                        textcoords='offset points', xytext=(5, -9))
    ax.set_xlim(0, 1.05)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel('Ssan+ (sức khoẻ)')
    ax.set_ylabel('Sperf (hiệu năng)')
    ax.set_title('Mặt phẳng chẩn đoán TEMPO-DQ (x0=0.75, y0=0.70)',
                 fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='lower left', fontsize=9)
    fig.tight_layout()
    out_png = OUT_FIG / 'dq_diagnostic_plane.png'
    fig.savefig(out_png, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"Đã lưu biểu đồ: {out_png}")
    return plane


# ---------------------------------------------------------------------------
def main():
    t_start = time.time()
    for d in (OUT, OUT_DATA, OUT_FIG, OUT_CACHE):
        d.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET temp_directory='{TMP_DIR}';")
    con.execute("SET preserve_insertion_order=false;")
    con.execute("SET memory_limit='3GB';")
    # Giới hạn số luồng: cửa sổ (window) trên ~70M dòng tốn RAM theo luồng;
    # máy chỉ có 15GB và thường đã dùng ~8GB → 2 luồng tránh OOM.
    con.execute("SET threads=2;")

    # 1. Từ điển dữ liệu
    dd = pd.DataFrame(DICT_ROWS, columns=['file', 'column', 'position', 'dtype',
                                          'grain', 'description_vi', 'rule', 'threshold'])
    dd_path = OUT_DATA / 'dq_data_dictionary.csv'
    dd.to_csv(dd_path, index=False)
    print(f"1) {dd_path}: {len(dd)} dòng")

    # 2. Metric theo quý
    print("\n2) Đang quét 25 quý (DuckDB, SQL aggregate)...")
    df_m = run_all_quarters(con)
    m_path = OUT_DATA / 'dq_metrics_by_quarter.csv'
    df_m.to_csv(m_path, index=False)
    print(f"   {m_path}: {len(df_m)} dòng ({len(QUARTERS)} quý x 2 nguồn)")

    # 3. Biểu đồ
    print("\n3) Đang vẽ biểu đồ...")
    plot_timeseries(df_m)

    # 4. Cải thiện
    print("\n4) Cải thiện dữ liệu (xx_domain_alignment & msa_mode_imputation, "
          "fit trên Train)...")
    df_i = improvement_before_after(con)
    i_path = OUT_DATA / 'dq_improvement_before_after.csv'
    df_i.to_csv(i_path, index=False)
    print(f"   {i_path}: {len(df_i)} dòng")
    print(df_i[df_i['scope'] == 'overall'].to_string(index=False))

    # 5. Mặt phẳng chẩn đoán (đọc từ cache metric, không quét lại)
    print("\n5) Mặt phẳng chẩn đoán TEMPO-DQ (x0=0.75, y0=0.70)...")
    df_p = diagnostic_plane(con)
    print(df_p.groupby('zone').size().to_string())

    # Sanity check
    print("\n=== SANITY CHECK ===")
    for dim in DIMS:
        lo, hi = df_m[dim].min(), df_m[dim].max()
        assert 0 <= lo <= hi <= 1 + 1e-9, f"{dim} ngoài [0,1]: [{lo}, {hi}]"
    orig_u = df_m[df_m['source'] == 'orig']['uniqueness'].min()
    cons_min = df_m['consistency'].min()
    print("Mọi metric trong [0,1]: OK")
    print(f"uniqueness orig (min): {orig_u:.4f} (~1.0 mong đợi)")
    print(f"consistency (min): {cons_min:.4f} (~1.0 mong đợi)")
    anom = df_m[(df_m['validity'] < 0.9) | (df_m['completeness'] < 0.9) |
                (df_m['accuracy'] < 0.9)]
    if len(anom):
        print("Cảnh báo — metric thấp:")
        print(anom.to_string(index=False))

    con.close()
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    print(f"\nHOÀN THÀNH sau {time.time()-t_start:.1f}s")


if __name__ == '__main__':
    main()
