#!/bin/bash
# Script để xem kết quả phân tích 6 dimensions

echo "=================================="
echo "KẾT QUẢ PHÂN TÍCH 6 KHÍA CẠNH"
echo "=================================="
echo ""

# Hiển thị bảng tóm tắt
echo "📊 BẢNG TÓM TẮT THEO QUÝ:"
echo ""
cat output/6_dimensions_summary_by_quarter.csv | column -t -s,
echo ""

# Thống kê file
echo "📁 CÁC FILE ĐÃ TẠO:"
echo ""
echo "1. Biểu đồ chính:"
ls -lh output/6_dimensions_analysis.png | awk '{print "   " $9 " (" $5 ")"}'
echo ""

echo "2. Bảng CSV:"
ls -lh output/6_dimensions_summary_by_quarter.csv | awk '{print "   " $9 " (" $5 ")"}'
echo ""

echo "3. Tài liệu:"
echo "   - README_6_DIMENSIONS.md"
echo "   - KETQUA_6_DIMENSIONS.md"
echo "   - ThucHanh/6_Dimensions_Analysis.ipynb"
echo ""

echo "4. Source code:"
echo "   - scripts/calculate_6_dimensions.py"
echo ""

# Hướng dẫn xem biểu đồ
echo "=================================="
echo "CÁCH XEM BIỂU đồ:"
echo "=================================="
echo ""
echo "Option 1: Mở bằng trình xem ảnh"
echo "  $ xdg-open output/6_dimensions_analysis.png"
echo ""
echo "Option 2: Trong VS Code / OpenCode"
echo "  - Click vào file: output/6_dimensions_analysis.png"
echo ""
echo "Option 3: Jupyter Notebook (tương tác)"
echo "  - Mở file: ThucHanh/6_Dimensions_Analysis.ipynb"
echo ""

# Tóm tắt insights
echo "=================================="
echo "PHÁT HIỆN CHÍNH:"
echo "=================================="
echo ""
echo "✅ 6 khía cạnh đã được tính:"
echo "   1. Delinquency Rate - Tăng 0.185% → 0.546% (+195%)"
echo "   2. Default Rate - 0.0% (chưa có vỡ nợ)"
echo "   3. Prepayment Rate - 0.0% (chưa có trả trước)"
echo "   4. Loss Severity - 0.0% (chưa có tổn thất)"
echo "   5. Total UPB - Tăng $1.53B → $3.84B (+150%)"
echo "   6. Credit Score - Giảm nhẹ 100.0 → 99.971"
echo ""
echo "⚠️  Cảnh báo:"
echo "   - Nợ quá hạn tăng gấp 3 lần trong 1 năm"
echo "   - Nợ quá hạn nghiêm trọng (90+ days) xuất hiện từ Q2"
echo ""
echo "📈 Tích cực:"
echo "   - Thị trường tăng trưởng mạnh (+150% UPB)"
echo "   - Chất lượng tín dụng vẫn cao (>99.9)"
echo "   - Chưa có vỡ nợ trong giai đoạn phân tích"
echo ""
