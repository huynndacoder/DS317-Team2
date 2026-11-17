# Phạm vi repo public

## Commit

- Source ingest, labels, Gold, model và verifier/package checker.
- Cấu hình pilot và dependency declarations.
- Synthetic tests/CI.
- Notebook/SQL source không có outputs.
- Tài liệu phương pháp, trạng thái và số liệu tổng hợp không có loan IDs.

## Giữ local

- Raw zips/TXT, Parquet, DuckDB warehouse, output/cache.
- Models, pickles, loan-level labels/predictions/audit rows.
- Agent checkpoint, conversation/instruction/audit history, paths máy cá nhân.
- Giáo trình/PDF/DOCX, paper PDFs.
- Bộ icon/diagram Databricks và exploration không còn thuộc scope chính.
- Notebook outputs và dữ liệu minh họa thực.

Không dùng blanket ignore `*.csv`: các CSV tổng hợp nhỏ trong `reports/` được phép commit.
Chặn dữ liệu bằng directory boundaries và file formats; kiểm explicit staged-file list
trước mỗi commit. Không dùng `git add .` cho một workspace có dữ liệu/agent state.

## Dọn dẹp lần này

Public tree được chuẩn bị trong worktree riêng, giữ checkout và index làm việc gốc.
Các staged deletions và file đang sửa của teammate ở checkout gốc không bị reset/stash.

Bản public bỏ Team2 discovery notes, lab/course material và các entrypoints pipeline
TXT/warehouse cũ khỏi HEAD; chúng không bị xóa khỏi workspace gốc.
Lịch sử Git không được rewrite.
Source nhãn/Gold/model đã audit được giữ nguyên nội dung và đường dẫn tương đối.

EDA/DQ notebooks được strip outputs trong bản public. Notebook gốc vẫn ở workspace local.
Các script literature search và agent instructions chưa phải phương pháp nghiên cứu đã chốt,
nên không được xuất bản thành kết quả có thẩm quyền.
