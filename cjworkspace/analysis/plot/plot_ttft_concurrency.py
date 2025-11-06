#!/usr/bin/env python3
"""
从 distserve_metrics CSV 文件中提取数据并绘制并发度 vs TTFT 图表

x轴: 并发度 (concurrency)
y轴: TTFT (time_to_first_token)
"""

import csv
import argparse
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from typing import List, Dict


def load_csv_data(csv_file: str) -> List[Dict]:
    """
    从CSV文件加载数据
    
    Returns:
        包含所有行的字典列表
    """
    data = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 转换数值字段
            numeric_row = {}
            for key, value in row.items():
                if key == 'concurrency':
                    numeric_row[key] = int(value) if value else 0
                else:
                    try:
                        numeric_row[key] = float(value) if value else 0.0
                    except (ValueError, TypeError):
                        numeric_row[key] = value
            data.append(numeric_row)
    
    return data


def plot_ttft_concurrency_compare(
    data_agg: List[Dict],
    data_disagg: List[Dict],
    output_file: str = None,
    title: str = "TTFT vs Concurrency",
    xlabel: str = "Concurrency",
    ttft_col: str = 'time_to_first_token_p90',
    isl: float = None,
    osl: float = None,
    label_agg: str = None,
    label_disagg: str = None
):
    """
    在同一图中绘制agg和disagg的TTFT对比曲线
    
    Args:
        data_agg: 聚合模式数据列表
        data_disagg: 分离模式数据列表
        output_file: 输出文件路径
        title: 图表标题
        xlabel: x轴标签
        ttft_col: TTFT列名（默认使用p90）
        isl: 输入序列长度
        osl: 输出序列长度
    """
    # 按并发度排序
    sorted_data_agg = sorted(data_agg, key=lambda x: x.get('concurrency', 0))
    sorted_data_disagg = sorted(data_disagg, key=lambda x: x.get('concurrency', 0))
    
    # 提取数据
    concurrencies_agg = [row['concurrency'] for row in sorted_data_agg]
    ttfts_agg = [row.get(ttft_col, 0.0) for row in sorted_data_agg]
    
    concurrencies_disagg = [row['concurrency'] for row in sorted_data_disagg]
    ttfts_disagg = [row.get(ttft_col, 0.0) for row in sorted_data_disagg]
    
    # 创建图表
    plt.figure(figsize=(12, 8))
    
    # 获取标签（从数据或参数）
    agg_label = label_agg if label_agg else (data_agg[0].get('deployment_name', 'Aggregated') if data_agg else 'Aggregated')
    disagg_label = label_disagg if label_disagg else (data_disagg[0].get('deployment_name', 'Disaggregated') if data_disagg else 'Disaggregated')
    
    # 构建标题后缀
    title_suffix = ""
    if isl is not None and osl is not None:
        title_suffix = f" (ISL={isl:.0f}, OSL={osl:.0f})"
    
    # 绘制agg曲线
    plt.plot(concurrencies_agg, ttfts_agg, marker='o', linewidth=2, 
             markersize=6, color='blue', label=agg_label, alpha=0.8)
    
    # 绘制disagg曲线
    plt.plot(concurrencies_disagg, ttfts_disagg, marker='s', linewidth=2,
             markersize=6, color='red', label=disagg_label, alpha=0.8)
    
    plt.xlabel(xlabel, fontsize=12)
    plt.ylabel('Time To First Token (ms)', fontsize=12)
    plt.title(f'TTFT vs Concurrency{title_suffix} ({agg_label} vs {disagg_label})', fontsize=14, fontweight='bold')
    plt.legend(loc='best', fontsize=10)
    plt.grid(True, alpha=0.3, linestyle='--')
    
    all_concurrencies = concurrencies_agg + concurrencies_disagg
    all_ttfts = ttfts_agg + ttfts_disagg
    if all_concurrencies:
        plt.xlim(left=0)
    if all_ttfts and max(all_ttfts) > 0:
        plt.ylim(bottom=0)
    
    # 调整布局
    plt.tight_layout()
    
    # 保存或显示
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Plot saved to: {output_file}")
    else:
        plt.show()
    
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description='Plot TTFT vs concurrency from distserve metrics CSV'
    )
    parser.add_argument(
        '--csv-agg',
        type=str,
        required=True,
        help='Aggregated mode CSV file path'
    )
    parser.add_argument(
        '--csv-disagg',
        type=str,
        required=True,
        help='Disaggregated mode CSV file path'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output image file path (default: plot_ttft_concurrency_compare_TIMESTAMP.png)'
    )
    parser.add_argument(
        '--ttft-col',
        type=str,
        default='time_to_first_token_p90',
        help='TTFT column name (default: time_to_first_token_p90). Options: time_to_first_token_avg, time_to_first_token_p90, time_to_first_token_p99, etc.'
    )
    
    args = parser.parse_args()
    
    # 加载数据
    print(f"📊 Loading aggregated data from: {args.csv_agg}")
    data_agg = load_csv_data(args.csv_agg)
    print(f"✅ Loaded {len(data_agg)} data points (agg)")
    
    print(f"📊 Loading disaggregated data from: {args.csv_disagg}")
    data_disagg = load_csv_data(args.csv_disagg)
    print(f"✅ Loaded {len(data_disagg)} data points (disagg)")
    
    # 检查必需的列是否存在
    for data, name in [(data_agg, "agg"), (data_disagg, "disagg")]:
        if 'concurrency' not in data[0]:
            print(f"❌ Error: Column 'concurrency' not found in {name} CSV")
            return
        if args.ttft_col not in data[0]:
            print(f"❌ Error: Column '{args.ttft_col}' not found in {name} CSV")
            print(f"   Available TTFT columns: {', '.join([k for k in data[0].keys() if 'time_to_first_token' in k])}")
            return
    
    # 读取ISL和OSL
    isl = data_agg[0].get('input_sequence_length_avg', None) if data_agg else None
    osl = data_agg[0].get('output_sequence_length_avg', None) if data_agg else None
    if isl is None and data_disagg:
        isl = data_disagg[0].get('input_sequence_length_avg', None)
        osl = data_disagg[0].get('output_sequence_length_avg', None)
    
    # 显示统计信息
    ttfts_agg = [row.get(args.ttft_col, 0.0) for row in data_agg]
    ttfts_disagg = [row.get(args.ttft_col, 0.0) for row in data_disagg]
    
    print(f"\n📈 Statistics:")
    if isl is not None and osl is not None:
        print(f"   Input Sequence Length (ISL): {isl:.0f}")
        print(f"   Output Sequence Length (OSL): {osl:.0f}")
    print(f"\n   Aggregated TTFT ({args.ttft_col}):")
    print(f"      Range: {min(ttfts_agg):.2f} - {max(ttfts_agg):.2f} ms")
    print(f"      Average: {np.mean(ttfts_agg):.2f} ms")
    print(f"\n   Disaggregated TTFT ({args.ttft_col}):")
    print(f"      Range: {min(ttfts_disagg):.2f} - {max(ttfts_disagg):.2f} ms")
    print(f"      Average: {np.mean(ttfts_disagg):.2f} ms")
    
    # 生成输出文件名
    if args.output:
        output_file = args.output
    else:
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"plot_ttft_concurrency_compare_{timestamp}.png"
    
    # 获取部署名称作为标签
    label_agg = data_agg[0].get('deployment_name', 'Aggregated') if data_agg else None
    label_disagg = data_disagg[0].get('deployment_name', 'Disaggregated') if data_disagg else None
    
    # 绘制对比图
    print(f"\n📊 Generating comparison plot...")
    plot_ttft_concurrency_compare(
        data_agg, data_disagg,
        output_file=output_file,
        title="TTFT vs Concurrency",
        ttft_col=args.ttft_col,
        isl=isl, osl=osl,
        label_agg=label_agg,
        label_disagg=label_disagg
    )
    
    print(f"\n✅ Done!")


if __name__ == '__main__':
    main()

