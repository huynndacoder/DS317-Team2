#!/usr/bin/env python3
"""
Tính toán 6 khía cạnh (dimensions) ở mức hạt dữ liệu (loan-level),
tổng hợp theo bảng/phiên bản, và vẽ biểu đồ theo lô/giai đoạn thời gian.

6 khía cạnh thường gặp trong phân tích dữ liệu tín dụng:
1. Delinquency (Tỷ lệ nợ quá hạn)
2. Default (Tỷ lệ vỡ nợ)
3. Prepayment (Tỷ lệ trả trước hạn)
4. Loss Severity (Mức độ tổn thất)
5. Current UPB (Số dư gốc hiện tại)
6. Credit Performance Score (Điểm hiệu suất tín dụng)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Thiết lập style cho biểu đồ
sns.set_style("darkgrid")
plt.rcParams['figure.figsize'] = (14, 8)

class LoanPerformanceAnalyzer:
    """Phân tích hiệu suất khoản vay theo 6 khía cạnh"""
    
    # Cấu trúc cột cho performance data (35 cột)
    PERF_COLUMNS = [
        'loan_id', 'monthly_reporting_period', 'current_upb', 
        'current_loan_delinquency_status', 'loan_age', 'remaining_months_to_legal_maturity',
        'repurchase_flag', 'modification_flag', 'zero_balance_code', 
        'zero_balance_effective_date', 'current_interest_rate',
        'current_deferred_upb', 'due_date_of_last_paid_installment',
        'mi_recoveries', 'net_sales_proceeds', 'non_mi_recoveries',
        'expenses', 'legal_costs', 'maintenance_and_preservation_costs',
        'taxes_and_insurance', 'miscellaneous_expenses', 'actual_loss_calculation',
        'modification_cost', 'step_modification_flag', 'deferred_payment_plan',
        'estimated_loan_to_value', 'zero_balance_removal_upb', 'delinquent_accrued_interest',
        'delinquency_due_to_disaster', 'borrower_assistance_status_code',
        'current_month_modification_cost', 'interest_bearing_upb',
        'payment_deferral_modification', 'last_paid_installment_date', 'filler'
    ]
    
    # Cấu trúc cột cho origination data (31 cột)
    ORIG_COLUMNS = [
        'credit_score', 'first_payment_date', 'first_time_homebuyer_flag',
        'maturity_date', 'msa', 'mi_percentage', 'number_of_units',
        'occupancy_status', 'cltv', 'dti', 'original_upb', 'ltv',
        'original_interest_rate', 'channel', 'prepayment_penalty_flag',
        'product_type', 'property_state', 'property_type', 'postal_code',
        'loan_id', 'loan_purpose', 'original_loan_term', 'number_of_borrowers',
        'seller_name', 'servicer_name', 'super_conforming_flag',
        'pre_harp_loan_id', 'program_indicator', 'harp_indicator',
        'valuation_method', 'interest_only_indicator', 'filler'
    ]
    
    def __init__(self, data_dir='data/historical_data_2025'):
        self.data_dir = Path(data_dir)
        self.quarters = ['2025Q1', '2025Q2', '2025Q3', '2025Q4']
        
    def load_data(self, quarter, sample_size=100000):
        """Load dữ liệu performance và origination cho một quý"""
        print(f"\nĐang tải dữ liệu {quarter}...")
        
        # Load performance data
        perf_file = self.data_dir / f'perf_{quarter}.txt'
        perf_df = pd.read_csv(
            perf_file, 
            sep='|', 
            names=self.PERF_COLUMNS,
            nrows=sample_size,
            dtype={'loan_id': str, 'monthly_reporting_period': str}
        )
        
        # Load origination data
        orig_file = self.data_dir / f'orig_{quarter}.txt'
        orig_df = pd.read_csv(
            orig_file,
            sep='|',
            names=self.ORIG_COLUMNS,
            dtype={'loan_id': str}
        )
        
        print(f"  Performance: {len(perf_df):,} records")
        print(f"  Origination: {len(orig_df):,} records")
        
        return perf_df, orig_df
    
    def calculate_dimensions(self, perf_df, orig_df):
        """Tính toán 6 khía cạnh ở mức loan-level"""
        
        # Merge data
        df = perf_df.merge(orig_df[['loan_id', 'credit_score', 'original_upb', 'ltv', 'dti']], 
                          on='loan_id', how='left')
        
        # 1. Delinquency Status (0=current, 1=30days, 2=60days, etc.)
        df['delinquency_status'] = pd.to_numeric(
            df['current_loan_delinquency_status'], errors='coerce'
        ).fillna(0)
        df['is_delinquent'] = (df['delinquency_status'] > 0).astype(int)
        df['is_seriously_delinquent'] = (df['delinquency_status'] >= 3).astype(int)
        
        # 2. Default Status (zero_balance_code = 03, 06, 09 = foreclosure/short sale)
        default_codes = ['03', '06', '09']
        df['is_default'] = df['zero_balance_code'].isin(default_codes).astype(int)
        
        # 3. Prepayment Status (zero_balance_code = 01 = prepaid)
        df['is_prepaid'] = (df['zero_balance_code'] == '01').astype(int)
        
        # 4. Loss Severity (actual_loss / original_upb)
        df['loss_severity'] = (
            pd.to_numeric(df['actual_loss_calculation'], errors='coerce').fillna(0) / 
            df['original_upb'].replace(0, np.nan)
        ).fillna(0)
        
        # 5. Current UPB
        df['current_upb'] = pd.to_numeric(df['current_upb'], errors='coerce').fillna(0)
        
        # 6. Credit Performance Score (composite score)
        # Điểm từ 0-100: cao = tốt, thấp = xấu
        df['credit_performance_score'] = self._calculate_performance_score(df)
        
        return df
    
    def _calculate_performance_score(self, df):
        """Tính điểm hiệu suất tín dụng tổng hợp (0-100)"""
        score = 100.0
        
        # Giảm điểm theo mức độ quá hạn
        score -= df['delinquency_status'] * 10
        
        # Giảm điểm nếu vỡ nợ
        score -= df['is_default'] * 50
        
        # Điều chỉnh theo credit score gốc
        credit_score_normalized = (df['credit_score'].fillna(700) - 300) / 550 * 20
        score += credit_score_normalized
        
        # Đảm bảo trong khoảng [0, 100]
        score = score.clip(0, 100)
        
        return score
    
    def aggregate_by_period(self, df):
        """Tổng hợp 6 khía cạnh theo tháng báo cáo"""
        
        agg_dict = {
            # Dimension 1: Delinquency Rate
            'is_delinquent': 'mean',
            'is_seriously_delinquent': 'mean',
            
            # Dimension 2: Default Rate
            'is_default': 'mean',
            
            # Dimension 3: Prepayment Rate
            'is_prepaid': 'mean',
            
            # Dimension 4: Loss Severity
            'loss_severity': 'mean',
            
            # Dimension 5: Current UPB
            'current_upb': 'sum',
            
            # Dimension 6: Credit Performance Score
            'credit_performance_score': 'mean',
            
            # Số lượng khoản vay
            'loan_id': 'count'
        }
        
        result = df.groupby('monthly_reporting_period').agg(agg_dict)
        result.columns = [
            'delinquency_rate', 'serious_delinquency_rate',
            'default_rate', 'prepayment_rate', 'avg_loss_severity',
            'total_upb', 'avg_credit_score', 'loan_count'
        ]
        
        # Chuyển đổi tỷ lệ sang phần trăm
        rate_columns = ['delinquency_rate', 'serious_delinquency_rate', 
                       'default_rate', 'prepayment_rate']
        result[rate_columns] = result[rate_columns] * 100
        
        result = result.sort_index()
        return result
    
    def plot_dimensions(self, aggregated_results, output_dir='output'):
        """Vẽ biểu đồ 6 khía cạnh theo thời gian"""
        
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        
        # Ghép tất cả các quý
        all_data = pd.concat(aggregated_results, axis=0)
        all_data.index = pd.to_datetime(all_data.index, format='%Y%m')
        all_data = all_data.sort_index()
        
        # Tạo figure với 6 subplots (2x3)
        fig, axes = plt.subplots(3, 2, figsize=(16, 12))
        fig.suptitle('6 Khía Cạnh Hiệu Suất Khoản Vay Theo Thời Gian', 
                    fontsize=16, fontweight='bold')
        
        # 1. Delinquency Rates
        ax = axes[0, 0]
        ax.plot(all_data.index, all_data['delinquency_rate'], 
               marker='o', label='Tổng nợ quá hạn', linewidth=2)
        ax.plot(all_data.index, all_data['serious_delinquency_rate'], 
               marker='s', label='Nợ quá hạn nghiêm trọng (90+ days)', linewidth=2)
        ax.set_title('1. Tỷ Lệ Nợ Quá Hạn (%)', fontweight='bold')
        ax.set_ylabel('Tỷ lệ (%)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 2. Default Rate
        ax = axes[0, 1]
        ax.plot(all_data.index, all_data['default_rate'], 
               marker='o', color='red', linewidth=2)
        ax.set_title('2. Tỷ Lệ Vỡ Nợ (%)', fontweight='bold')
        ax.set_ylabel('Tỷ lệ (%)')
        ax.grid(True, alpha=0.3)
        
        # 3. Prepayment Rate
        ax = axes[1, 0]
        ax.plot(all_data.index, all_data['prepayment_rate'], 
               marker='o', color='green', linewidth=2)
        ax.set_title('3. Tỷ Lệ Trả Trước Hạn (%)', fontweight='bold')
        ax.set_ylabel('Tỷ lệ (%)')
        ax.grid(True, alpha=0.3)
        
        # 4. Loss Severity
        ax = axes[1, 1]
        ax.plot(all_data.index, all_data['avg_loss_severity'] * 100, 
               marker='o', color='orange', linewidth=2)
        ax.set_title('4. Mức Độ Tổn Thất Trung Bình (%)', fontweight='bold')
        ax.set_ylabel('Tỷ lệ (%)')
        ax.grid(True, alpha=0.3)
        
        # 5. Total UPB
        ax = axes[2, 0]
        ax.plot(all_data.index, all_data['total_upb'] / 1e9, 
               marker='o', color='purple', linewidth=2)
        ax.set_title('5. Tổng Số Dư Gốc Hiện Tại (Billion $)', fontweight='bold')
        ax.set_ylabel('Số dư (Billion $)')
        ax.grid(True, alpha=0.3)
        
        # 6. Credit Performance Score
        ax = axes[2, 1]
        ax.plot(all_data.index, all_data['avg_credit_score'], 
               marker='o', color='blue', linewidth=2)
        ax.set_title('6. Điểm Hiệu Suất Tín Dụng (0-100)', fontweight='bold')
        ax.set_ylabel('Điểm')
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Lưu biểu đồ
        output_file = output_dir / '6_dimensions_analysis.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"\nĐã lưu biểu đồ: {output_file}")
        plt.close()
        
        return all_data
    
    def create_summary_table(self, all_data, output_dir='output'):
        """Tạo bảng tóm tắt theo quý"""
        
        output_dir = Path(output_dir)
        
        # Thêm cột Quarter
        all_data['quarter'] = all_data.index.to_period('Q')
        
        # Tổng hợp theo quý
        quarterly = all_data.groupby('quarter').agg({
            'delinquency_rate': 'mean',
            'serious_delinquency_rate': 'mean',
            'default_rate': 'mean',
            'prepayment_rate': 'mean',
            'avg_loss_severity': 'mean',
            'total_upb': 'mean',
            'avg_credit_score': 'mean',
            'loan_count': 'sum'
        })
        
        # Làm tròn số
        quarterly = quarterly.round(3)
        
        # Lưu ra CSV
        output_file = output_dir / '6_dimensions_summary_by_quarter.csv'
        quarterly.to_csv(output_file)
        print(f"Đã lưu bảng tóm tắt: {output_file}")
        
        # In ra console
        print("\n" + "="*80)
        print("TỔNG HỢP 6 KHÍA CẠNH THEO QUÝ")
        print("="*80)
        print(quarterly.to_string())
        print("="*80)
        
        return quarterly
    
    def run_analysis(self, sample_size=100000):
        """Chạy toàn bộ phân tích"""
        
        print("="*80)
        print("PHÂN TÍCH 6 KHÍA CẠNH HIỆU SUẤT KHOẢN VAY")
        print("="*80)
        
        aggregated_results = []
        
        for quarter in self.quarters:
            try:
                # Load data
                perf_df, orig_df = self.load_data(quarter, sample_size)
                
                # Calculate dimensions
                print(f"  Đang tính toán 6 khía cạnh...")
                df_with_dimensions = self.calculate_dimensions(perf_df, orig_df)
                
                # Aggregate by period
                print(f"  Đang tổng hợp theo tháng...")
                agg_result = self.aggregate_by_period(df_with_dimensions)
                aggregated_results.append(agg_result)
                
                print(f"✓ Hoàn thành {quarter}")
                
            except Exception as e:
                print(f"✗ Lỗi khi xử lý {quarter}: {str(e)}")
        
        if not aggregated_results:
            print("\n✗ Không có dữ liệu để phân tích!")
            return
        
        # Plot dimensions
        print("\nĐang tạo biểu đồ...")
        all_data = self.plot_dimensions(aggregated_results)
        
        # Create summary table
        print("\nĐang tạo bảng tóm tắt...")
        quarterly_summary = self.create_summary_table(all_data)
        
        print("\n" + "="*80)
        print("✓ HOÀN THÀNH PHÂN TÍCH!")
        print("="*80)


def main():
    """Hàm chính"""
    
    # Khởi tạo analyzer
    analyzer = LoanPerformanceAnalyzer()
    
    # Chạy phân tích với sample size (có thể điều chỉnh)
    # Dùng sample_size nhỏ hơn để chạy nhanh, hoặc None để load toàn bộ
    analyzer.run_analysis(sample_size=100000)


if __name__ == '__main__':
    main()
