# Quy tắc nhãn 12 tháng — quá hạn nghiêm trọng

Tài liệu này là nguồn duy nhất mô tả định nghĩa nhãn dùng cho bài toán dự đoán
nguy cơ quá hạn từ **hồ sơ tại thời điểm khởi tạo**. Mã nguồn thực thi quy tắc
nằm ở `scripts/label/label_rules.py`; tài liệu này và mã phải được sửa cùng nhau.

## 1. Đơn vị phân tích và nguồn dữ liệu

- Mỗi dòng nhãn tương ứng **một khoản vay** (một `loan_id` trong origination).
- Nguồn: `parquet/orig/quarter=<YYYYQn>/data.parquet` (31 cột) và
  `parquet/perf/quarter=<YYYYQn>/data.parquet` (35 cột), đọc trực tiếp bằng DuckDB.
- Không dùng `warehouse.duckdb` vì database này không chứa đủ 110 quý.
- Không đưa dữ liệu performance vào tập đặc trưng. Performance chỉ dùng để tạo nhãn.

## 2. Ánh xạ cột thực tế

| Khái niệm | Cột | Ghi chú |
| --- | --- | --- |
| Loan identifier | `loan_id` | VARCHAR, không bao giờ cast sang số |
| Original first payment date | `first_payment_date` | dạng số `YYYYMM` |
| Origination cohort | `quarter` (tên partition) | = quý khởi tạo, không suy từ `first_payment_date` |
| Monthly reporting period | `monthly_reporting_period` | `YYYYMM` |
| Delinquency status | `current_loan_delinquency_status` | `00`–`99`, `RA`, `XX` |
| Zero balance code | `zero_balance_code` | `01`,`02`,`03`,`09`,`15`,`16`,`96` |
| Zero balance effective date | `zero_balance_effective_date` | `YYYYMM` |
| Loan age | `loan_age` | **không** dùng làm mốc cửa sổ |
| Modification flag | `modification_flag` | `Y`, `P`, NULL |
| Loan purpose | `loan_purpose` | `P` Purchase, `C` Refinance - Cash Out, `N` Refinance - No Cash Out, `R` Refinance - Not Specified, `9` Not Available (Release 48); dữ liệu này không có `R` |

Tham chiếu tài liệu: Freddie Mac Single-Family Loan-Level Dataset General User
Guide, **Release 48** (phát hành 2026-10-28), quy định origination cutoff
2026-06-30 và performance cutoff 2026-06-30.

## 3. Cửa sổ nhãn

- Bắt đầu: `first_payment_date` của khoản vay.
- Kết thúc: tháng bắt đầu + 11 tháng, **tính cả hai đầu** — tổng 12 tháng lịch.
- Ví dụ: first payment 2020-03 → cửa sổ 202003…202102.
- Đơn vị tháng được tuyến tính hoá: `idx = (YYYYMM // 100) * 12 + YYYYMM % 100`,
  nên việc so sánh và cộng trừ xử lý đúng qua ranh giới năm.
- **Không** dùng `loan_age`, vì trường này được reset sau modification (tài liệu
  Freddie Mac, câu hỏi Q35: công thức tính `loan_age` đổi sau modification).
- **Không** lấy "12 dòng performance đầu tiên": khoảng trống tháng phải được phát
  hiện, không bị nén lại.

## 4. Biến cố

Một khoản vay có biến cố khi trong cửa sổ tồn tại tháng có:

- `current_loan_delinquency_status` là mã số **≥ 03** (tức `03`…`99`); hoặc
- `current_loan_delinquency_status = 'RA'` (REO Acquisition).

Chi tiết triển khai: `RA` được quy về 99 trước khi so sánh, `XX` quy về NULL
(không phải 0). Trạng thái không parse được **không** bao giờ được hiểu là
"không quá hạn".

Đây là nhãn **quá hạn nghiêm ngặt/REO theo định nghĩa nghiên cứu**, không phải
nhãn tổn thất tài chính và không tương ứng phân loại nợ pháp lý Việt Nam.

Trong phiên bản nhãn này:

- Zero balance code **không** tự động tạo nhãn dương.
- Mã `15` (whole loan sale) **không** phải biến cố.
- Biến cố ngoài cửa sổ không làm thay đổi nhãn.

## 5. Trạng thái nhãn

### Positive
Có biến cố đã xác minh trong cửa sổ. Khoản vay **vẫn dương** nếu sau đó phục hồi
(quá hạn rồi trở lại `00`/`01`/`02`).

### Negative
Không có biến cố **và** đáp ứng một trong hai điều kiện:

1. **Đủ 12 tháng** trong cửa sổ với trạng thái diễn giải được là không có biến
   cố, cửa sổ đã kết thúc trước hoặc tại performance cutoff; hoặc
2. **Tất toán tự chọn trong cửa sổ**: zero balance code `01` với
   `zero_balance_effective_date` nằm trong cửa sổ, và mọi tháng từ đầu cửa sổ
   đến **tháng báo cáo cuối cùng** đều quan sát được
   (`observed_month_count_in_window >= expected_months`) với
   `unknown_status_month_count = 0`.

Với trường hợp tất toán, tiêu chí cho phép kết luận âm tính là: mã kết thúc là
`01` và **không thiếu tháng nào** và **không có tháng trạng thái không xác định**
trước khi kết thúc. Nếu thiếu hoặc chưa rõ, khoản vay thành `unknown` — không giả
định là đang trả đúng hạn.

### Hai ngày khác nhau của một sự kiện kết thúc

Mỗi dòng zero balance mang hai ngày, và **không** được dùng lẫn:

| trường | dùng để | vì sao |
| --- | --- | --- |
| `zero_balance_effective_date` | quyết định sự kiện kết thúc **có nằm trong cửa sổ hay không** | đây là ngày khoản vay thực sự rời khỏi theo dõi |
| `monthly_reporting_period` của dòng đó | đo **số tháng phải quan sát** (`expected_months`) | đây là chu kỳ servicer thực sự báo cáo; tháng effective theo định nghĩa không bao giờ có dòng dữ liệu |

Trên toàn bộ 35.908.478 khoản có mã kết thúc, hai ngày lệch nhau ở **58.034**
dòng; 599 dòng rơi khác phía ranh giới cửa sổ. Dùng effective date cho ranh giới
(đúng) đổi nhãn 1.187 khoản so với dùng reporting month. Dùng nó cho **cả**
`expected_months` thì 238 khoản `negative` bị đẩy thành `unknown` một cách giả
tạo, vì đòi quan sát một tháng không bao giờ được báo cáo — nên coverage vẫn bám
reporting month. Chi tiết: `output/label_tables/termination_date_analysis.md`.

Nếu một khoản kết thúc **trước** khi cửa sổ bắt đầu và cửa sổ không quan sát
được, nhãn là `unknown` (`terminated_before_window`); nếu cửa sổ vẫn quan sát đủ
12 tháng sạch thì nhãn âm tính, vì kết luận dựa trên chính lịch sử trong cửa sổ.

### Unknown
Không có bằng chứng dương tính nhưng chưa đủ bằng chứng âm tính. Các lý do chính
tắc, đúng theo thứ tự trong biểu thức `CASE` của `label_rules.decide_sql()`:

| Lý do | Ý nghĩa |
| --- | --- |
| `missing_fpd` | Thiếu hoặc sai `first_payment_date` |
| `no_performance` | Không có bản ghi performance nào |
| `conflicting_duplicate_rows` | Cùng `(loan_id, tháng)` có nhiều dòng khác nội dung (kể cả ngay tại tháng có biến cố) |
| `terminated_before_window` | Kết thúc **trước** khi cửa sổ bắt đầu, chưa quan sát được cửa sổ |
| `terminated_sale` | Bán khoản vay (`15`, `16`) **trong** cửa sổ, chưa từng 90+ ngày |
| `terminated_defect` | Lỗi underwriting/servicing (`96`) **trong** cửa sổ |
| `terminated_credit_event_without_d90` | Biến cố tín dụng (`02`,`03`,`09`) **trong** cửa sổ nhưng không quan sát được `03`+ |
| `terminated_other` | Mã kết thúc khác chưa phân loại, **trong** cửa sổ |
| `incomplete_before_termination` | Thiếu tháng trước khi kết thúc (chỉ khi chưa kết luận được) |
| `window_not_mature` | Cửa sổ chưa kết thúc tại performance cutoff |
| `cohort_not_mature` | Cả cohort chưa trưởng thành theo quy tắc công bố |
| `unknown_status_in_window` | Có `XX`/trạng thái không diễn giải được trong cửa sổ |
| `incomplete_window_gap` | Thiếu tháng giữa cửa sổ |

**Sự kiện kết thúc ngoài cửa sổ không đổi nhãn.** Một khoản vay có đủ 12 tháng
trong cửa sổ, trạng thái diễn giải được là không có biến cố, thì là `negative` —
kể cả khi sau đó nó bị bán (`15`/`16`), mua lại do lỗi (`96`), hay kết thúc vì
biến cố tín dụng (`02`/`03`/`09`) ở một tháng nằm **sau** cửa sổ. Các lý do
`terminated_*` ở trên chỉ áp dụng khi sự kiện kết thúc rơi **bên trong** cửa sổ
và cắt đứt khả năng quan sát trước khi đủ 12 tháng. Đây từng là lỗi khiến 772.247
khoản vay bị gán `unknown` oan (đã sửa, có kiểm thử `T20`–`T25`).

Nguyên tắc: nếu đã có **biến cố dương tính chắc chắn**, việc thiếu các tháng khác
**không** xoá bằng chứng đó. Nhưng nếu xung đột dữ liệu rơi đúng vào tháng chứa
bằng chứng biến cố (`conflict_event_month`), khoản vay bị hạ xuống `unknown` thay vì chọn
một dòng bất kỳ.

`label_reason` chỉ mô tả **lý do chưa xác định được nhãn** (hoặc lý do không đủ
điều kiện nghiên cứu chính). Một khoản vay đã có kết luận rõ ràng thì
`label_reason = NULL`, kể cả khi nó kết thúc giữa cửa sổ: trường hợp tất toán tự
chọn đã được chứng minh âm tính bằng chính tiêu chí tất toán, nên **không** bị
xếp vào `incomplete_before_termination`.

Quy tắc này áp dụng bất kể cửa sổ đã kết thúc hay chưa. Một khoản tất toán tự
chọn ở tháng thứ 3 của cửa sổ, trong cohort mà cửa sổ chưa đóng tại performance
cutoff, vẫn là **negative** (bằng chứng tất toán là đủ) và `label_reason = NULL`;
nó chỉ không đủ điều kiện nghiên cứu chính vì `window_mature = false`, với
`primary_exclusion_reason = 'window_not_mature'`.

Đã có hai lỗi thực tế trong mạch lý do này, cả hai được phát hiện bằng kiểm tra
trên dữ liệu thật chứ không phải bằng cảm nhận:

1. Mọi khoản tất toán sớm (kể cả loại đã kết luận âm tính) bị gắn
   `incomplete_before_termination` — sửa bằng cách trả `NULL` cho kết luận đã
   xác định.
2. Sau khi sửa (1), vẫn còn 51.539 khoản âm tính mang lý do "không đầy đủ" vì
   điều kiện cũ chỉ trả `NULL` khi `mature = 1`. Đã sửa thành trả `NULL` cho mọi
   khoản `negative`, và `primary_exclusion_reason` nay ghi `window_not_mature` cho
   mọi khoản đã kết luận nhưng cửa sổ chưa đóng.

Cả hai đều có kiểm thử hồi quy (`T09`, `T19` trong `test_label_logic.py`) và kiểm
tra tương ứng trong `verify_labels.py`.

## 6. Trùng lặp và xung đột

- Origination: mỗi `loan_id` phải xuất hiện đúng một lần trong toàn bộ 110 quý.
- Performance: mỗi cặp `(loan_id, monthly_reporting_period)` phải là duy nhất.
- Bản ghi **trùng hoàn toàn** (cùng hash toàn dòng) không làm thay đổi nhãn; chỉ
  ghi cờ `duplicate_flag` và `duplicate_row_count`.
- Bản ghi **cùng khoá nhưng khác nội dung** làm phát sinh `conflict_flag`. Phân
  biệt hai loại xung đột ảnh hưởng khác nhau đến kết luận:
  - `conflict_any` (có bất kỳ tháng nào trong cửa sổ mâu thuẫn) → nếu chưa có
    biến cố, nhãn thành `unknown` vì mâu thuẫn có thể đang che một biến cố.
  - `conflict_event_month` (chính tháng mang biến cố có mâu thuẫn) → biến cố
    không chắc chắn, nhãn thành `unknown` dù đã có `03`+.
  - Mâu thuẫn ở một tháng **khác** tháng biến cố, khi biến cố ở tháng của nó là
    sạch, thì **không** huỷ kết luận `positive`; chỉ ghi cờ để không âm thầm bỏ
    qua.
- Không tự chọn một dòng khi gặp trùng xung đột.

## 7. Tách nhãn khỏi điều kiện trưởng thành

Ba khái niệm được lưu **riêng biệt**:

- `label_status`: `positive` / `negative` / `unknown`.
- `window_mature`: cửa sổ của **khoản vay** đã kết thúc trước hoặc tại
  performance cutoff (`win_end_idx <= cutoff_idx`).
- `cohort_mature`: toàn bộ phạm vi cửa sổ dự kiến của **cohort** đã trưởng thành.
  Quy tắc công bố (dựa trên tháng first-payment, không phải tháng cuối quý):
  mốc neo của cohort là **phân vị 99 (`quantile_disc`) của `first_payment_date`**
  trong cohort; cohort trưởng thành khi `mốc neo + 11 tháng <= cutoff`. Mốc neo
  được ghi lại trong cột `cohort_anchor_first_payment_month` để kiểm tra được.
- `eligible_for_primary_study` = `label_status <> 'unknown'` **và** `cohort_mature`
  **và** `window_mature`.

Ghi chú thiết kế: `cohort_mature` **không** dùng `max(first_payment_date)` thực tế
của cohort, vì khoảng 0,3–0,5% khoản vay trong mỗi cohort là khoản vay modified /
converted mà `first_payment_date` phản ánh ngày sửa đổi (Freddie Mac FAQ Q37),
có thể muộn hơn nhiều năm — dùng max sẽ khiến mọi cohort (kể cả 1999Q1) mãi mãi
chưa trưởng thành. Phân vị 99 đủ cao để đại diện cho "phạm vi dự kiến" của
cohort (99,3% khoản vay có `first_payment_date` trong quý khởi tạo + 3 tháng) mà
vẫn bền với các khoản vay lệch. Hệ quả: cohort 2025Q1 chuyển sang chưa trưởng
thành (mốc neo 202505 → cửa sổ kết thúc 202604 > cutoff 202603), đúng với bản
chất "chưa đủ dữ liệu cho cả cohort".

Hệ quả: một khoản vay mới có thể đã ghi nhận biến cố và có `label_status =
positive`, nhưng **không** đủ điều kiện vào nghiên cứu chính nếu cửa sổ của nó
chưa kết thúc tại cutoff. Nhờ vậy không có chuyện chỉ những ca dương xuất hiện
sớm của một cohort chưa trưởng thành được đưa vào tập nghiên cứu trong khi các
ca còn lại chưa có đáp án.

## 8. Bảng nhãn xuất ra

Đường dẫn: `output/labels/cohort=<YYYYQn>/data.parquet` (một file mỗi cohort).

Cột bắt buộc theo yêu cầu:

```
loan_id, cohort, original_first_payment_date, label_window_start, label_window_end,
performance_cutoff, first_observed_month, last_observed_month,
observed_month_count_in_window, unknown_status_month_count, missing_month_count,
first_event_month, termination_code, termination_month, window_mature,
cohort_mature, label_status, label_12m, eligible_for_primary_study,
primary_exclusion_reason, quality_flags
```

Cột audit bổ sung (giải thích):

| Cột | Ý nghĩa |
| --- | --- |
| `label_reason` | Lý do nhãn `unknown`, hoặc lý do không đủ điều kiện nghiên cứu chính |
| `expected_months` | Số tháng kỳ vọng trong cửa sổ tính đến lúc kết thúc khoản vay |
| `has_event` | Có ít nhất một tháng có biến cố trong cửa sổ |
| `duplicate_row_count` | Số dòng thừa trong các nhóm khoá trùng |
| `conflict_flag` | Có tháng nào trong cửa sổ mâu thuẫn nội dung (`conflict_any`) |
| `event_conflict_flag` | Chính tháng mang biến cố có mâu thuẫn (`conflict_event_month`) |
| `duplicate_flag` | Có bản ghi trùng hoàn toàn |
| `termination_effective_month` | `zero_balance_effective_date` của sự kiện kết thúc (cùng sự kiện với mã) |
| `termination_date_mismatch` | `zero_balance_effective_date` khác `monthly_reporting_period` của sự kiện kết thúc |
| `n_termination_events` | Số sự kiện zero-balance (cảnh báo nếu > 1) |
| `cohort_anchor_first_payment_month` | Mốc neo dùng cho `cohort_mature` (phân vị 99 của `first_payment_date`) |

Quy ước giá trị:

- `label_12m = 1` khi `positive`; `= 0` khi `negative`; `= NULL` khi `unknown`.
- Cột `label_12m` **luôn** là kiểu số nguyên có NULL; khi join/export phải giữ
  NULL, không `coalesce` về 0.
- Các cột đếm (`observed_month_count_in_window`, `unknown_status_month_count`,
  `missing_month_count`, `duplicate_row_count`) được cast tường minh sang
  `BIGINT`. Lý do: `sum()` của DuckDB trả về `HUGEINT`, và Parquet lưu kiểu này
  dưới dạng `DOUBLE`, khiến cột đếm bị đọc ra thành số thực (ví dụ
  `12.0` thay vì `12`). Đây là lỗi kiểu dữ liệu đã được phát hiện và sửa; nếu
  một cột đếm xuất hiện dưới dạng `DOUBLE` trong bảng nhãn thì đó là hồi quy.
- Mỗi khoản vay chỉ có **một** `primary_exclusion_reason`, xác định trong
  `label_rules.finish_sql()`: `cohort_not_mature` → `window_not_mature` →
  `label_reason` của khoản chưa kết luận. Các lý do loại trừ khác (nếu có) không
  bị mất: cột `label_reason` và cờ `quality_flags` vẫn ghi nhận, và
  `reason_summary.csv` thống kê riêng từng lý do.
- Bảng lý do ở §5 và hàm `decide_sql()` là **một** nguồn sự thật: thứ tự trong
  bài kiểm tra được đọc trực tiếp từ biểu thức `CASE` trong SQL, không lặp lại ở
  một hằng số Python riêng (một hằng số như vậy từng bị lệch thứ tự so với SQL và
  đã bị xoá).

### Bảng tổng hợp theo cohort

`output/label_tables/cohort_summary.csv` (và `.parquet`) có đúng các cột yêu cầu:

```
cohort, total_loans, mature_loans, positive_count, negative_count, unknown_count,
eligible_count, eligible_positive_count, eligible_negative_count,
eligible_event_rate, cohort_mature
```

`eligible_event_rate` là **tỷ lệ dạng phân số** (0–1) để dùng trực tiếp khi tính
toán. Kèm thêm `eligible_event_rate_pct` (cùng tử số/mẫu số, nhân 100, làm tròn
4 chữ số) chỉ để đọc cho dễ; hai cột này luôn nhất quán vì tính từ cùng một biểu
thức.

`mature_loans` đếm theo `window_mature` (cửa sổ 12 tháng của chính khoản vay đã
kết thúc trước cutoff của cohort), khác với `cohort_mature` (toàn bộ cohort đã
trưởng thành theo quy tắc ở §7).

## 9. Quy ước performance cutoff

Cutoff được lấy **theo từng cohort**, không phải một hằng số toàn cục:
`performance_cutoff = max(monthly_reporting_period)` của partition performance
tương ứng.

Lý do: trong kho parquet hiện tại, 85 cohort có performance đến `202606`, nhưng
25 cohort (2020Q1…2026Q1) chỉ đến `202603` — các cohort này được ingest từ bản
Release 47 và chưa được làm mới lên Release 48. Dùng một cutoff toàn cục sẽ đánh
dấu nhầm các cửa sổ là đã trưởng thành khi thực tế chưa có dữ liệu.

Giá trị `202606` khớp với performance cutoff mà Release 48 công bố, nên cutoff
suy ra từ dữ liệu được xác nhận chéo bởi tài liệu. Đây là cutoff suy luận từ dữ
liệu **có** đối chiếu tài liệu; không phải thời gian hiện tại.

**Cutoff và phiên bản nguồn được ghi lại theo từng partition** trong
`output/labels/manifest.json`: mỗi cohort có `performance_cutoff` (suy ra từ
`max(monthly_reporting_period)`), `source_version` (`release_48` cho cutoff
202606, `release_47_inferred` cho 25 cohort dừng ở 202603), `cohort_mature`,
`cohort_anchor_first_payment_month` và `total_loans`. Cột `performance_cutoff`
trong bảng nhãn cũng ghi lại giá trị này cho từng dòng.

## 10. Chạy lại

```bash
# 1) khảo sát dữ liệu (read-only)
./venv/bin/python scripts/label/profile_data.py

# 2) kiểm thử logic trên dữ liệu nhỏ có đáp án biết trước
./venv/bin/python scripts/label/test_label_logic.py

# 3) xây bảng nhãn cho cả 110 cohort
./venv/bin/python scripts/label/build_labels.py --force

# hoặc một vài cohort
./venv/bin/python scripts/label/build_labels.py --quarters 2020Q1 2005Q3
```

Biến môi trường: `DQ_MEMORY_LIMIT` (mặc định `3GB`), `DQ_THREADS` (mặc định `6`),
`DQ_WORK_DIR` (thư mục spill, mặc định `.label_tmp`).

## 11. Giới hạn đã biết

- Không có manifest/release metadata trong kho dữ liệu; cutoff chỉ suy ra từ
  `max(monthly_reporting_period)` và đối chiếu với Release Notes.
- `XX` là sentinel "Not Available". Trong dữ liệu hiện tại `XX` chỉ xuất hiện ở
  `loan_age = 0` (chu kỳ trước first payment date) nên **không** lọt vào cửa sổ
  nhãn. Nếu một lần ingest khác tạo ra `XX` bên trong cửa sổ, quy tắc xử lý là
  `unknown`, không phải 0.
- Một số khoản vay có lịch sử performance bắt đầu **sau** first payment date;
  những khoản này không thể kết luận âm tính và rơi vào `unknown`.
- Tài liệu Freddie Mac không công bố quy tắc "phải quá hạn liên tục bao nhiêu
  tháng"; nhãn ở đây là "chạm ngưỡng 90+ ngày trong cửa sổ", không yêu cầu liên tục.
- `loan_purpose` có **51 dòng** mang giá trị `9`, chỉ trong 1999Q1–1999Q3. `9` là
  mã **được tài liệu định nghĩa** = Not Available (General User Guide Release 48),
  không phải giá trị lạ. Nó là trường đặc trưng, **không** tham gia tạo nhãn. Trong
  bảng Gold, 51 dòng này bị loại khỏi phạm vi Purchase vì `loan_purpose <> 'P'`,
  không bị ép sang `N`.
- Hai bản Release cùng tồn tại trong kho: 85 cohort có performance tới `202606`,
  25 cohort (2020Q1…2026Q1) chỉ tới `202603`. Vì cutoff lấy theo cohort, sự khác
  biệt này được xử lý đúng, nhưng nên làm mới 25 cohort đó trước khi công bố số
  liệu cuối.
- `perf_v2` chỉ có 2 cohort và **không** được dùng ở đây; mọi tính toán đọc
  `parquet/perf/`.

## 12. Nhật ký sửa đổi (vòng review)

**Vòng 2 — sửa theo review (chỉ logic nhãn, không re-ingest):**

1. **Sửa lỗi "kết thúc sau cửa sổ bị gán unknown".** 772.247 khoản vay có đủ 12
   tháng sạch nhưng bị bán/kết thúc *sau* cửa sổ đã bị gán `unknown` oan; nay là
   `negative`. Mã kết thúc chỉ tác động nhãn khi nằm **trong** cửa sổ.
2. **Đọc mã + ngày từ cùng sự kiện** zero-balance; thêm cột
   `termination_effective_month`, `termination_date_mismatch` (58.034 dòng lệch
   ngày), `n_termination_events` (0 dòng đa sự kiện).
3. **Tách xung đột**: `conflict_any` vs `conflict_event_month` — mâu thuẫn ở tháng
   khác tháng biến cố không còn huỷ kết luận `positive`.
4. **Định nghĩa lại `cohort_mature`** bằng mốc neo phân vị 99 của
   `first_payment_date` (thay cho tháng cuối quý); 2025Q1 chuyển sang chưa trưởng
   thành. Mốc neo ghi ở `cohort_anchor_first_payment_month`.
5. **Đối chiếu tập** `(loan_id, first_event_month)` thay vì chỉ tổng số dương.
6. **Bảng trước/sau theo cohort** (`output/label_tables/label_changes_summary.csv`,
   `diff_before_after.log`) và **manifest** nguồn theo partition
   (`output/labels/manifest.json`). Bảng theo cohort thay cho file diff từng khoản
   vay (43 MB, 897.664 dòng) — file đó đã bị xoá vì không ai đọc được và cũng
   không cần: mọi thay đổi đều nằm trong bảng tổng hợp theo cohort.

Kết quả: `unknown` 4.038.346 → 3.266.099 (−772.247); đủ điều kiện 45.257.313 →
45.904.144 (+646.831); tỷ lệ biến cố 0,516% → 0,508%; cohort đủ điều kiện muộn
nhất 2025Q1 → 2024Q4. Tập dương tính **không đổi** (234.824), vì bản sửa chỉ tác
động ranh giới unknown/negative.

## 13. Vòng 3 — trước khi tạo Gold

**1. Ngày kết thúc thực sự.** Đã đo hai cách dùng effective date:
dùng cho ranh giới cửa sổ **và** cho `expected_months` đổi 322 nhãn, trong đó
238 khoản `negative` bị đẩy thành `unknown` một cách giả tạo (đòi quan sát tháng
effective, mà tháng đó không bao giờ có dòng dữ liệu). Dùng cho **ranh giới** mà
thôi thì đổi 1.187 nhãn, toàn bộ `unknown` → `negative`. Chọn cách thứ hai.
Chi tiết: `output/label_tables/termination_date_analysis.md`.

**2. Lỗ hổng tất toán trước cửa sổ.** 31.057 khoản kết thúc **trước** tháng bắt
đầu cửa sổ; trước đây 30.311 khoản mã `01` trong số đó được gán `negative` dù
**không quan sát được tháng nào** trong cửa sổ (công thức `expected_months` ra số
âm nên điều kiện coverage luôn đúng). Nay là `unknown` với lý do
`terminated_before_window`; `expected_months` được chặn dưới bằng 0. Chỉ 1 khoản
trong nhóm này có > 0 tháng quan sát.

**3. Manifest cộng dồn.** Ghi manifest theo kiểu hợp nhất với file cũ, nên chạy
`--quarters` trên một tập con **không** xoá thông tin của các partition không
đụng tới; `run_cohorts` ghi lại lần chạy này chạm cohort nào, và
`source_version_rule` nói rõ `release_47_inferred` là suy luận từ biên dữ liệu
performance (202603), không phải đọc từ metadata phát hành.

**4. Bảng trước/sau theo cohort.** `output/label_tables/label_changes_summary.csv`
thay cho file diff từng khoản vay (43 MB, 897.664 dòng — đã xoá).

**5. Schema origination.** `output/schema/orig_schema.{csv,md}`,
`loan_purpose_stats.csv`, `loan_purpose_by_cohort.csv`: 31 cột, mỗi cột một kiểu
duy nhất trên 110 partition, `loan_purpose` `N` 38,29% / `P` 37,28% / `C` 24,43%
/ `9` 51 dòng (1999Q1–Q3, giữ nguyên không đổi thành `N`).

**6. Dữ liệu nghiên cứu.** `scripts/gold/build_research_dataset.py` dùng allow-list,
lọc Purchase eligible và kiểm tra join 1:1. Bộ hiện hành ở `output/research/` có
16.641.482 khoản và 18 predictors; nhãn toàn origination giữ riêng ở `output/labels/`.
Role pilot lấy từ `membership.parquet`; xem `docs/data-contract.md`.
