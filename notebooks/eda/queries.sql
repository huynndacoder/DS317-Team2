-- =====================================================================
-- eda_queries.sql : EDA bộ dữ liệu Parquet (orig + perf) bằng DuckDB
-- Chạy bằng CLI:   duckdb eda.duckdb < sql/eda_queries.sql
-- Hoặc chạy từng khối trong DBeaver / DuckDB UI / notebook.
--
-- TÊN CỘT MẶC ĐỊNH (Find & Replace nếu tên thật khác):
--   loan_id, monthly_reporting_period, current_loan_delinquency_status,
--   credit_score, original_interest_rate, ltv, dti, loan_purpose  (đã khớp dữ liệu thật)
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. SETUP
-- ---------------------------------------------------------------------
SET memory_limit = '6GB';              -- chỉnh theo RAM máy
SET threads = 4;
SET temp_directory = './duckdb_tmp';

CREATE OR REPLACE VIEW orig AS
SELECT * FROM read_parquet('parquet/orig/*/data.parquet', hive_partitioning=true, union_by_name=true);

CREATE OR REPLACE VIEW perf AS
SELECT * FROM read_parquet('parquet/perf/*/data.parquet', hive_partitioning=true, union_by_name=true);

-- orig_s: TOÀN BỘ orig, mã "không có dữ liệu" (9999/999) đã đổi thành NULL
CREATE OR REPLACE VIEW orig_s AS
SELECT * REPLACE (
    NULLIF(credit_score, 9999)    AS credit_score,
    NULLIF(vantage_score_4, 9999) AS vantage_score_4,
    NULLIF(dti, 999)              AS dti,
    NULLIF(ltv, 999)              AS ltv,
    NULLIF(cltv, 999)             AS cltv,
    NULLIF(mi_percentage, 999)    AS mi_percentage
) FROM orig;

-- perf_s: 1 quý để profile (perf toàn bộ ~533 triệu dòng). Đổi quý nếu cần.
CREATE OR REPLACE VIEW perf_s AS SELECT * FROM perf WHERE quarter = '2023Q1';

-- ---------------------------------------------------------------------
-- BƯỚC 1. HIỂU CẤU TRÚC DỮ LIỆU
-- ---------------------------------------------------------------------
-- 1.1 Tên cột, kiểu dữ liệu
DESCRIBE orig;
DESCRIBE perf;

-- 1.2 Số dòng theo quý (phát hiện quý thiếu / bất thường)
SELECT quarter, COUNT(*) AS n_orig FROM orig GROUP BY 1 ORDER BY 1;
SELECT quarter, COUNT(*) AS n_perf FROM perf GROUP BY 1 ORDER BY 1;

-- 1.3 Xem mẫu
SELECT * FROM orig_s LIMIT 5;
SELECT * FROM perf_s LIMIT 5;

-- 1.4 Schema có đồng nhất giữa các quý không (cột lệch kiểu hoặc thiếu ở vài quý)
SELECT 'orig' AS bang, name, COUNT(DISTINCT type) AS so_kieu, list(DISTINCT type) AS cac_kieu,
       COUNT(DISTINCT file_name) AS so_file
FROM parquet_schema('parquet/orig/*/data.parquet') WHERE name <> 'schema' GROUP BY name
HAVING COUNT(DISTINCT type) > 1
    OR COUNT(DISTINCT file_name) < (SELECT COUNT(DISTINCT file_name) FROM parquet_schema('parquet/orig/*/data.parquet'))
UNION ALL
SELECT 'perf', name, COUNT(DISTINCT type), list(DISTINCT type), COUNT(DISTINCT file_name)
FROM parquet_schema('parquet/perf/*/data.parquet') WHERE name <> 'schema' GROUP BY name
HAVING COUNT(DISTINCT type) > 1
    OR COUNT(DISTINCT file_name) < (SELECT COUNT(DISTINCT file_name) FROM parquet_schema('parquet/perf/*/data.parquet'));

-- 1.5 Thống kê nhanh toàn bộ cột (có null_percentage)
SUMMARIZE orig_s;
SUMMARIZE perf_s;

-- ---------------------------------------------------------------------
-- BƯỚC 2. KIỂM TRA CHẤT LƯỢNG DỮ LIỆU
-- ---------------------------------------------------------------------
-- 2.1 Giá trị thiếu (mỗi cột: số NULL và %)
SELECT COUNT(*) AS tong_dong, COUNT(*) - COUNT(COLUMNS(*)) FROM orig_s;
SELECT COUNT(*) AS tong_dong, COUNT(*) - COUNT(COLUMNS(*)) FROM perf_s;

-- 2.2 Mã đặc biệt thay cho NULL: xem min/max và giá trị phổ biến nhất
SELECT MIN(credit_score) mn, MAX(credit_score) mx FROM orig_s;   -- lặp lại cho các cột số khác
SELECT credit_score, COUNT(*) n FROM orig_s GROUP BY 1 ORDER BY n DESC LIMIT 5;
SELECT current_loan_delinquency_status, COUNT(*) n FROM perf_s GROUP BY 1 ORDER BY n DESC LIMIT 10;

-- 2.3 Trùng khóa
-- orig: mỗi khoản vay phải xuất hiện đúng 1 lần
SELECT loan_id, COUNT(*) c FROM orig_s GROUP BY 1 HAVING c > 1 ORDER BY c DESC LIMIT 20;
-- perf: mỗi (khoản vay, kỳ báo cáo) đúng 1 lần
SELECT loan_id, monthly_reporting_period, COUNT(*) c FROM perf_s GROUP BY 1, 2 HAVING c > 1 ORDER BY c DESC LIMIT 20;

-- 2.4 Toàn vẹn giữa hai bảng (chạy trên TOÀN BỘ dữ liệu mới có ý nghĩa)
SELECT
  (SELECT COUNT(DISTINCT loan_id) FROM perf_s) AS loan_trong_perf,
  (SELECT COUNT(*) FROM (SELECT DISTINCT loan_id FROM perf_s) p ANTI JOIN orig_s o USING (loan_id)) AS perf_mo_coi,
  (SELECT COUNT(*) FROM orig_s o ANTI JOIN (SELECT DISTINCT loan_id FROM perf_s) p USING (loan_id)) AS orig_khong_co_perf;

-- 2.5 Giá trị không hợp lệ (SỬA ngưỡng theo nghiệp vụ)
SELECT
  COUNT(*) FILTER (WHERE original_interest_rate <= 0 OR original_interest_rate > 20)          AS lai_suat_la,
  COUNT(*) FILTER (WHERE ltv <= 0 OR ltv > 200)                   AS ltv_la,
  COUNT(*) FILTER (WHERE credit_score < 300 OR credit_score > 850) AS fico_la,
  COUNT(*) AS tong
FROM orig_s;

-- Kiểu dữ liệu sai (số bị lưu thành chuỗi): đếm giá trị không ép được sang số
SELECT COUNT(*) AS khong_ep_duoc_sang_so
FROM perf_s WHERE current_loan_delinquency_status IS NOT NULL AND TRY_CAST(current_loan_delinquency_status AS INTEGER) IS NULL;

-- 2.6 Ngoại lệ theo IQR (lặp lại cho các cột số khác)
WITH s AS (
  SELECT quantile_cont(original_interest_rate, 0.25) q1, quantile_cont(original_interest_rate, 0.75) q3 FROM orig_s
)
SELECT COUNT(*) FILTER (WHERE original_interest_rate < q1 - 1.5*(q3-q1) OR original_interest_rate > q3 + 1.5*(q3-q1)) AS so_ngoai_le,
       COUNT(original_interest_rate) AS so_non_null,
       ANY_VALUE(q1 - 1.5*(q3-q1)) AS can_duoi, ANY_VALUE(q3 + 1.5*(q3-q1)) AS can_tren
FROM orig_s, s;

-- ---------------------------------------------------------------------
-- BƯỚC 3. PHÂN TÍCH ĐƠN BIẾN
-- ---------------------------------------------------------------------
-- 3.1 Thống kê mô tả biến số (lặp lại cho các cột số khác)
SELECT COUNT(credit_score) n, AVG(credit_score) mean, STDDEV(credit_score) std,
       MIN(credit_score) min, quantile_cont(credit_score, 0.25) q1, MEDIAN(credit_score) median,
       quantile_cont(credit_score, 0.75) q3, MAX(credit_score) max,
       skewness(credit_score) skew, kurtosis(credit_score) kurt
FROM orig_s;

-- Thống kê nhiều cột cùng lúc
SELECT AVG(COLUMNS(['credit_score','original_interest_rate','ltv','dti'])) FROM orig_s;

-- 3.2 Histogram bằng SQL (chỉ trả về vài chục dòng, dùng để vẽ)
SELECT FLOOR(credit_score / 20) * 20 AS bin, COUNT(*) AS n FROM orig_s GROUP BY 1 ORDER BY 1;
SELECT FLOOR(original_interest_rate / 0.25) * 0.25 AS bin, COUNT(*) AS n FROM orig_s GROUP BY 1 ORDER BY 1;

-- 3.3 Biến phân loại
SELECT loan_purpose, COUNT(*) n, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM orig_s GROUP BY 1 ORDER BY n DESC;

-- 3.4 Trạng thái trễ hạn (perf)
SELECT current_loan_delinquency_status, COUNT(*) n, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM perf_s GROUP BY 1 ORDER BY n DESC;

-- ---------------------------------------------------------------------
-- BƯỚC 4. PHÂN TÍCH HAI BIẾN VÀ NHIỀU BIẾN
-- ---------------------------------------------------------------------
-- 4.1 Xu hướng theo quý (dùng orig, KHÔNG phải orig_s, nếu muốn xem tất cả các quý)
SELECT quarter, COUNT(*) n, AVG(original_interest_rate) lai_suat_tb, AVG(credit_score) fico_tb,
       AVG(ltv) ltv_tb, AVG(dti) dti_tb
FROM orig GROUP BY 1 ORDER BY 1;

-- 4.2 Tương quan giữa các biến số
SELECT corr(credit_score, original_interest_rate) AS fico_rate,
       corr(ltv, original_interest_rate)          AS ltv_rate,
       corr(dti, original_interest_rate)          AS dti_rate,
       corr(credit_score, ltv)      AS fico_ltv
FROM orig_s;

-- 4.3 So sánh theo nhóm
SELECT loan_purpose, COUNT(*) n, AVG(original_interest_rate) rate_tb, MEDIAN(original_interest_rate) rate_median,
       AVG(credit_score) fico_tb
FROM orig_s GROUP BY 1 ORDER BY n DESC;

-- 4.4 Mẫu để vẽ scatter (không vẽ toàn bộ dữ liệu)
SELECT credit_score, original_interest_rate FROM orig_s USING SAMPLE 50000;

-- 4.5 Kết hợp orig và perf: TỔNG HỢP perf về mức khoản vay TRƯỚC, rồi mới join
-- Định nghĩa vỡ nợ bên dưới là ví dụ (>= 3), SỬA theo bộ dữ liệu của bạn.
CREATE OR REPLACE TABLE loan_perf_agg AS
SELECT loan_id,
       COUNT(*) AS so_thang,
       MAX(CASE WHEN TRY_CAST(current_loan_delinquency_status AS INTEGER) >= 3
                  OR current_loan_delinquency_status = 'RA' THEN 1 ELSE 0 END) AS tung_vo_no,
       MAX(CASE WHEN (TRY_CAST(current_loan_delinquency_status AS INTEGER) >= 3
                  OR current_loan_delinquency_status = 'RA') AND loan_age <= 24 THEN 1 ELSE 0 END) AS vo_no_24m
FROM perf GROUP BY 1;   -- quét toàn bộ perf, mất vài phút

-- Tỷ lệ vỡ nợ theo nhóm điểm tín dụng
SELECT FLOOR(o.credit_score / 50) * 50 AS nhom_fico,
       COUNT(*) AS n_khoan_vay, AVG(p.vo_no_24m) AS ty_le_vo_no_24m
FROM orig_s o JOIN loan_perf_agg p USING (loan_id)
WHERE o.quarter <= '2024Q1' AND o.credit_score IS NOT NULL   -- đủ 24 tháng quan sát
GROUP BY 1 ORDER BY 1;

-- Tỷ lệ vỡ nợ theo quý khởi tạo (chú ý right-censoring ở các quý gần nhất)
SELECT o.quarter, COUNT(*) AS n, AVG(p.tung_vo_no) AS ty_le_vo_no, AVG(p.so_thang) AS so_thang_tb
FROM orig_s o JOIN loan_perf_agg p USING (loan_id)
GROUP BY 1 ORDER BY 1;

-- ---------------------------------------------------------------------
-- BƯỚC 5. XUẤT DỮ LIỆU ĐÃ LÀM SẠCH (bỏ comment khi đã chốt quy tắc)
-- ---------------------------------------------------------------------
-- COPY (
--   SELECT * FROM orig
--   WHERE credit_score BETWEEN 300 AND 850 AND original_interest_rate > 0
-- ) TO 'clean/orig' (FORMAT PARQUET, PARTITION_BY (quarter), COMPRESSION ZSTD, OVERWRITE_OR_IGNORE);
