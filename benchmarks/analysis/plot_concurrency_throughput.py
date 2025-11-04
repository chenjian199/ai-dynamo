#!/usr/bin/env python3
"""
从 distserve_metrics CSV 文件中提取数据并绘制并发度 vs 请求吞吐率图表

x轴: 并发度 (concurrency)
y轴: 请求吞吐率 (request_throughput_avg)
"""

import csv
import argparse
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple


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


def plot_concurrency_throughput(
    data: List[Dict],
    output_file: str = None,
    title: str = "Throughput vs Concurrency",
    xlabel: str = "Concurrency",
    request_col: str = 'request_throughput_avg',
    token_col: str = 'output_token_throughput_avg',
    isl: float = None,
    osl: float = None,
    label: str = None,
    color_req: str = 'blue',
    color_token: str = 'red',
    marker_req: str = 'o',
    marker_token: str = 's'
):
    """
    绘制并发度与吞吐率的关系图（分成两张独立的图）
    
    Args:
        data: 数据列表
        output_file: 输出文件路径（如果不指定则显示）
        title: 图表标题
        xlabel: x轴标签
        request_col: 请求吞吐率列名
        token_col: 输出token吞吐率列名
        isl: 输入序列长度
        osl: 输出序列长度
        label: 图例标签前缀
        color_req: 请求吞吐率线条颜色
        color_token: token吞吐率线条颜色
        marker_req: 请求吞吐率标记样式
        marker_token: token吞吐率标记样式
    """
    # 按并发度排序
    sorted_data = sorted(data, key=lambda x: x.get('concurrency', 0))
    
    # 提取数据
    concurrencies = [row['concurrency'] for row in sorted_data]
    request_throughputs = [row.get(request_col, 0.0) for row in sorted_data]
    token_throughputs = [row.get(token_col, 0.0) for row in sorted_data]
    
    # 创建两个子图
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 12))
    
    # 构建标题后缀（包含ISL和OSL信息）
    title_suffix = ""
    if isl is not None and osl is not None:
        title_suffix = f" (ISL={isl:.0f}, OSL={osl:.0f})"
    
    # 构建标签
    req_label = f"{label} - Request Throughput" if label else 'Request Throughput (req/s)'
    token_label = f"{label} - Token Throughput" if label else 'Output Token Throughput (tokens/s)'
    
    # 第一张图：请求吞吐率
    ax1.plot(concurrencies, request_throughputs, marker=marker_req, linewidth=2, 
             markersize=6, color=color_req, label=req_label, alpha=0.8)
    ax1.set_xlabel(xlabel, fontsize=12)
    ax1.set_ylabel('Request Throughput (req/s)', fontsize=12)
    ax1.set_title(f'Request Throughput vs Concurrency{title_suffix}', fontsize=14, fontweight='bold')
    ax1.legend(loc='best', fontsize=10)
    ax1.grid(True, alpha=0.3, linestyle='--')
    if concurrencies:
        ax1.set_xlim(left=0)
    if request_throughputs and max(request_throughputs) > 0:
        ax1.set_ylim(bottom=0)
    
    # 第二张图：输出token吞吐率
    ax2.plot(concurrencies, token_throughputs, marker=marker_token, linewidth=2,
             markersize=6, color=color_token, label=token_label, alpha=0.8)
    ax2.set_xlabel(xlabel, fontsize=12)
    ax2.set_ylabel('Output Token Throughput (tokens/s)', fontsize=12)
    ax2.set_title(f'Output Token Throughput vs Concurrency{title_suffix}', fontsize=14, fontweight='bold')
    ax2.legend(loc='best', fontsize=10)
    ax2.grid(True, alpha=0.3, linestyle='--')
    if concurrencies:
        ax2.set_xlim(left=0)
    if token_throughputs and max(token_throughputs) > 0:
        ax2.set_ylim(bottom=0)
    
    # 整体标题
    main_title = f"{title}{title_suffix}" if title_suffix else title
    fig.suptitle(main_title, fontsize=16, fontweight='bold', y=0.995)
    
    # 调整布局
    plt.tight_layout()
    
    # 保存或显示
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Plot saved to: {output_file}")
    else:
        plt.show()
    
    plt.close()


def plot_concurrency_throughput_compare(
    data_agg: List[Dict],
    data_disagg: List[Dict],
    output_file: str = None,
    title: str = "Throughput vs Concurrency",
    xlabel: str = "Concurrency",
    request_col: str = 'request_throughput_avg',
    token_col: str = 'output_token_throughput_avg',
    isl: float = None,
    osl: float = None
):
    """
    在同一图中绘制agg和disagg的对比曲线
    """
    # 按并发度排序
    sorted_data_agg = sorted(data_agg, key=lambda x: x.get('concurrency', 0))
    sorted_data_disagg = sorted(data_disagg, key=lambda x: x.get('concurrency', 0))
    
    # 提取数据
    concurrencies_agg = [row['concurrency'] for row in sorted_data_agg]
    request_throughputs_agg = [row.get(request_col, 0.0) for row in sorted_data_agg]
    token_throughputs_agg = [row.get(token_col, 0.0) for row in sorted_data_agg]
    
    concurrencies_disagg = [row['concurrency'] for row in sorted_data_disagg]
    request_throughputs_disagg = [row.get(request_col, 0.0) for row in sorted_data_disagg]
    token_throughputs_disagg = [row.get(token_col, 0.0) for row in sorted_data_disagg]
    
    # 创建两个子图
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 12))
    
    # 构建标题后缀
    title_suffix = ""
    if isl is not None and osl is not None:
        title_suffix = f" (ISL={isl:.0f}, OSL={osl:.0f})"
    
    # 第一张图：请求吞吐率
    ax1.plot(concurrencies_agg, request_throughputs_agg, marker='o', linewidth=2, 
             markersize=6, color='blue', label='Aggregated', alpha=0.8)
    ax1.plot(concurrencies_disagg, request_throughputs_disagg, marker='s', linewidth=2,
             markersize=6, color='red', label='Disaggregated', alpha=0.8)
    ax1.set_xlabel(xlabel, fontsize=12)
    ax1.set_ylabel('Request Throughput (req/s)', fontsize=12)
    ax1.set_title(f'Request Throughput vs Concurrency{title_suffix} (Agg vs Disagg)', fontsize=14, fontweight='bold')
    ax1.legend(loc='best', fontsize=10)
    ax1.grid(True, alpha=0.3, linestyle='--')
    all_concurrencies = concurrencies_agg + concurrencies_disagg
    all_req = request_throughputs_agg + request_throughputs_disagg
    if all_concurrencies:
        ax1.set_xlim(left=0)
    if all_req and max(all_req) > 0:
        ax1.set_ylim(bottom=0)
    
    # 第二张图：输出token吞吐率
    ax2.plot(concurrencies_agg, token_throughputs_agg, marker='o', linewidth=2,
             markersize=6, color='blue', label='Aggregated', alpha=0.8)
    ax2.plot(concurrencies_disagg, token_throughputs_disagg, marker='s', linewidth=2,
             markersize=6, color='red', label='Disaggregated', alpha=0.8)
    ax2.set_xlabel(xlabel, fontsize=12)
    ax2.set_ylabel('Output Token Throughput (tokens/s)', fontsize=12)
    ax2.set_title(f'Output Token Throughput vs Concurrency{title_suffix} (Agg vs Disagg)', fontsize=14, fontweight='bold')
    ax2.legend(loc='best', fontsize=10)
    ax2.grid(True, alpha=0.3, linestyle='--')
    all_tokens = token_throughputs_agg + token_throughputs_disagg
    if all_concurrencies:
        ax2.set_xlim(left=0)
    if all_tokens and max(all_tokens) > 0:
        ax2.set_ylim(bottom=0)
    
    # 整体标题
    main_title = f"{title}{title_suffix}" if title_suffix else title
    fig.suptitle(main_title, fontsize=16, fontweight='bold', y=0.995)
    
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
        description='Plot concurrency vs request throughput from distserve metrics CSV'
    )
    parser.add_argument(
        '--csv',
        type=str,
        default=None,
        help='Input CSV file path (single mode)'
    )
    parser.add_argument(
        '--csv-agg',
        type=str,
        default=None,
        help='Aggregated mode CSV file path (for comparison)'
    )
    parser.add_argument(
        '--csv-disagg',
        type=str,
        default=None,
        help='Disaggregated mode CSV file path (for comparison)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output image file path (default: plot_concurrency_throughput_TIMESTAMP.png)'
    )
    parser.add_argument(
        '--request-col',
        type=str,
        default='request_throughput_avg',
        help='Request throughput column name (default: request_throughput_avg)'
    )
    parser.add_argument(
        '--token-col',
        type=str,
        default='output_token_throughput_avg',
        help='Output token throughput column name (default: output_token_throughput_avg)'
    )
    
    args = parser.parse_args()
    
    # 判断是单文件模式还是对比模式
    compare_mode = args.csv_agg is not None and args.csv_disagg is not None
    
    if compare_mode:
        # 对比模式：加载两个CSV文件
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
            if args.request_col not in data[0]:
                print(f"❌ Error: Column '{args.request_col}' not found in {name} CSV")
                return
            if args.token_col not in data[0]:
                print(f"❌ Error: Column '{args.token_col}' not found in {name} CSV")
                return
        
        # 读取ISL和OSL
        isl = data_agg[0].get('input_sequence_length_avg', None) if data_agg else None
        osl = data_agg[0].get('output_sequence_length_avg', None) if data_agg else None
        if isl is None and data_disagg:
            isl = data_disagg[0].get('input_sequence_length_avg', None)
            osl = data_disagg[0].get('output_sequence_length_avg', None)
        
        print(f"\n📈 Statistics:")
        if isl is not None and osl is not None:
            print(f"   Input Sequence Length (ISL): {isl:.0f}")
            print(f"   Output Sequence Length (OSL): {osl:.0f}")
        
        # 生成输出文件名
        if args.output:
            output_file = args.output
        else:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"plot_concurrency_throughput_compare_{timestamp}.png"
        
        # 绘制对比图
        print(f"\n📊 Generating comparison plot...")
        plot_concurrency_throughput_compare(
            data_agg, data_disagg,
            output_file=output_file,
            title="Throughput vs Concurrency",
            request_col=args.request_col,
            token_col=args.token_col,
            isl=isl, osl=osl
        )
        
    else:
        # 单文件模式
        if not args.csv:
            print("❌ Error: Either --csv or both --csv-agg and --csv-disagg must be provided")
            return
        
        print(f"📊 Loading data from: {args.csv}")
        data = load_csv_data(args.csv)
        print(f"✅ Loaded {len(data)} data points")
        
        # 检查必需的列是否存在
        if 'concurrency' not in data[0]:
            print(f"❌ Error: Column 'concurrency' not found in CSV")
            return
        
        if args.request_col not in data[0]:
            print(f"❌ Error: Column '{args.request_col}' not found in CSV")
            return
        
        if args.token_col not in data[0]:
            print(f"❌ Error: Column '{args.token_col}' not found in CSV")
            return
        
        # 显示统计信息
        concurrencies = [row['concurrency'] for row in data]
        request_throughputs = [row.get(args.request_col, 0.0) for row in data]
        token_throughputs = [row.get(args.token_col, 0.0) for row in data]
        
        isl = data[0].get('input_sequence_length_avg', None) if data else None
        osl = data[0].get('output_sequence_length_avg', None) if data else None
        
        print(f"\n📈 Statistics:")
        print(f"   Concurrency range: {min(concurrencies)} - {max(concurrencies)}")
        if isl is not None and osl is not None:
            print(f"   Input Sequence Length (ISL): {isl:.0f}")
            print(f"   Output Sequence Length (OSL): {osl:.0f}")
        print(f"\n   Request Throughput:")
        print(f"      Range: {min(request_throughputs):.2f} - {max(request_throughputs):.2f} req/s")
        print(f"      Average: {np.mean(request_throughputs):.2f} req/s")
        print(f"      Max: {max(request_throughputs):.2f} req/s (at concurrency {concurrencies[request_throughputs.index(max(request_throughputs))]})")
        print(f"\n   Output Token Throughput:")
        print(f"      Range: {min(token_throughputs):.2f} - {max(token_throughputs):.2f} tokens/s")
        print(f"      Average: {np.mean(token_throughputs):.2f} tokens/s")
        print(f"      Max: {max(token_throughputs):.2f} tokens/s (at concurrency {concurrencies[token_throughputs.index(max(token_throughputs))]})")
        
        # 生成输出文件名
        if args.output:
            output_file = args.output
        else:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"plot_concurrency_throughput_{timestamp}.png"
        
        # 绘制图表
        print(f"\n📊 Generating plot...")
        plot_concurrency_throughput(
            data,
            output_file=output_file,
            title="Throughput vs Concurrency",
            request_col=args.request_col,
            token_col=args.token_col,
            isl=isl,
            osl=osl
        )
    
    print(f"\n✅ Done!")


if __name__ == '__main__':
    main()

