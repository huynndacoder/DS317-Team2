#!/bin/bash
# Script chạy nhanh để tạo báo cáo 6 dimensions

cd "$(dirname "$0")/.."

echo "=================================="
echo "6 DIMENSIONS ANALYSIS - QUICK RUN"
echo "=================================="
echo ""

# Kiểm tra virtual environment
if [ ! -d "venv" ]; then
    echo "⚠️  Virtual environment chưa tồn tại. Đang tạo..."
    python -m venv venv
    venv/bin/pip install -q pandas numpy matplotlib seaborn
fi

# Chạy phân tích
echo "🚀 Đang chạy phân tích 6 khía cạnh..."
venv/bin/python scripts/calculate_6_dimensions.py

echo ""
echo "✅ Hoàn thành!"
echo ""
echo "📊 Kết quả:"
echo "  - Biểu đồ: output/6_dimensions_analysis.png"
echo "  - Bảng CSV: output/6_dimensions_summary_by_quarter.csv"
echo ""
echo "📖 Tài liệu:"
echo "  - README_6_DIMENSIONS.md"
echo "  - KETQUA_6_DIMENSIONS.md"
echo "  - ThucHanh/6_Dimensions_Analysis.ipynb"
echo ""
