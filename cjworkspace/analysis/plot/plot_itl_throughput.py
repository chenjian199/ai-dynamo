#!/usr/bin/env python3
"""
从 distserve_metrics CSV 文件中提取数据并绘制 ITL vs 最大吞吐率图表

x轴: ITL阈值（0, 5, 10, 15, ... ms）
y轴: 满足 p90 ITL < 阈值时的最大请求吞吐率
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


def find_max_throughput_for_itl_threshold(
    data: List[Dict],
    itl_threshold: float,
    itl_p90_col: str = 'inter_token_latency_p90',
    throughput_col: str = 'request_throughput_avg'
) -> float:
    """
    找到满足 p90 ITL < 阈值时的最大请求吞吐率
    
    Args:
        data: 数据列表
        itl_threshold: ITL阈值（毫秒）
        itl_p90_col: ITL P90列名
        throughput_col: 吞吐率列名
    
    Returns:
        最大吞吐率，如果没有满足条件的数据则返回0
    """
    max_throughput = 0.0
    
    for row in data:
        itl_p90 = row.get(itl_p90_col, float('inf'))
        throughput = row.get(throughput_col, 0.0)
        
        # 检查是否满足条件：p90 ITL < 阈值
        if itl_p90 < itl_threshold and throughput > max_throughput:
            max_throughput = throughput
    
    return max_throughput


def calculate_itl_throughput_curve(
    data: List[Dict],
    max_itl: float = 100.0,
    step: float = 5.0,
    itl_p90_col: str = 'inter_token_latency_p90',
    throughput_col: str = 'request_throughput_avg'
) -> Tuple[List[float], List[float]]:
    """
    计算ITL阈值与最大吞吐率的曲线
    
    Args:
        data: 数据列表
        max_itl: 最大ITL阈值（毫秒）
        step: ITL阈值步长（毫秒）
        itl_p90_col: ITL P90列名
        throughput_col: 吞吐率列名
    
    Returns:
        (itl_thresholds, max_throughputs) 元组
    """
    itl_thresholds = []
    max_throughputs = []
    
    # 从0开始，每次增加step，直到max_itl
    itl_threshold = 0.0
    while itl_threshold <= max_itl:
        max_throughput = find_max_throughput_for_itl_threshold(
            data, itl_threshold, itl_p90_col, throughput_col
        )
        
        itl_thresholds.append(itl_threshold)
        max_throughputs.append(max_throughput)
        
        itl_threshold += step
    
    return itl_thresholds, max_throughputs


def plot_itl_throughput(
    itl_thresholds: List[float],
    max_throughputs: List[float],
    output_file: str = None,
    title: str = "Maximum Request Throughput vs ITL Threshold",
    xlabel: str = "ITL Threshold (ms, p90 < threshold)",
    ylabel: str = "Max Request Throughput (req/s)",
    isl: float = None,
    osl: float = None,
    label: str = None,
    color: str = 'blue',
    marker: str = 'o'
):
    """
    绘制ITL阈值与最大吞吐率的关系图
    
    Args:
        itl_thresholds: ITL阈值列表
        max_throughputs: 对应的最大吞吐率列表
        output_file: 输出文件路径（如果不指定则显示）
        title: 图表标题
        xlabel: x轴标签
        ylabel: y轴标签
        isl: 输入序列长度
        osl: 输出序列长度
        label: 图例标签
        color: 线条颜色
        marker: 标记样式
    """
    plt.figure(figsize=(12, 8))
    
    # 构建标题后缀（包含ISL和OSL信息）
    title_suffix = ""
    if isl is not None and osl is not None:
        title_suffix = f" (ISL={isl:.0f}, OSL={osl:.0f})"
    
    # 绘制曲线
    plt.plot(itl_thresholds, max_throughputs, marker=marker, linewidth=2, markersize=6,
             color=color, label=label, alpha=0.8)
    
    # 设置标签和标题
    plt.xlabel(xlabel, fontsize=12)
    plt.ylabel(ylabel, fontsize=12)
    plt.title(f"{title}{title_suffix}", fontsize=14, fontweight='bold')
    
    # 添加图例
    if label:
        plt.legend(loc='best', fontsize=10)
    
    # 添加网格
    plt.grid(True, alpha=0.3, linestyle='--')
    
    # 设置x轴从0开始
    plt.xlim(left=0)
    
    # 如果y轴有数据，设置y轴从0开始
    if max_throughputs:
        max_y = max(max_throughputs) if max_throughputs else 0
        if max_y > 0:
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


def plot_itl_throughput_compare(
    itl_thresholds_agg: List[float],
    max_throughputs_agg: List[float],
    itl_thresholds_disagg: List[float],
    max_throughputs_disagg: List[float],
    output_file: str = None,
    title: str = "Maximum Request Throughput vs ITL Threshold",
    xlabel: str = "ITL Threshold (ms, p90 < threshold)",
    ylabel: str = "Max Request Throughput (req/s)",
    isl: float = None,
    osl: float = None,
    label_agg: str = None,
    label_disagg: str = None
):
    """
    在同一图中绘制agg和disagg的对比曲线
    """
    plt.figure(figsize=(12, 8))
    
    # 使用提供的标签，如果没有则使用默认值
    agg_label = label_agg if label_agg else 'Aggregated'
    disagg_label = label_disagg if label_disagg else 'Disaggregated'
    
    # 构建标题后缀
    title_suffix = ""
    if isl is not None and osl is not None:
        title_suffix = f" (ISL={isl:.0f}, OSL={osl:.0f})"
    
    # 绘制agg曲线
    plt.plot(itl_thresholds_agg, max_throughputs_agg, marker='o', linewidth=2, 
             markersize=6, color='blue', label=agg_label, alpha=0.8)
    
    # 绘制disagg曲线
    plt.plot(itl_thresholds_disagg, max_throughputs_disagg, marker='s', linewidth=2,
             markersize=6, color='red', label=disagg_label, alpha=0.8)
    
    # 设置标签和标题
    plt.xlabel(xlabel, fontsize=12)
    plt.ylabel(ylabel, fontsize=12)
    plt.title(f"{title}{title_suffix}", fontsize=14, fontweight='bold')
    
    # 添加图例
    plt.legend(loc='best', fontsize=10)
    
    # 添加网格
    plt.grid(True, alpha=0.3, linestyle='--')
    
    # 设置x轴从0开始
    plt.xlim(left=0)
    
    # 设置y轴从0开始
    all_throughputs = max_throughputs_agg + max_throughputs_disagg
    if all_throughputs and max(all_throughputs) > 0:
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
        description='Plot ITL threshold vs maximum request throughput from distserve metrics CSV'
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
        help='Output image file path (default: plot_itl_throughput_TIMESTAMP.png)'
    )
    parser.add_argument(
        '--max-itl',
        type=float,
        default=100.0,
        help='Maximum ITL threshold in ms (default: 100)'
    )
    parser.add_argument(
        '--step',
        type=float,
        default=5.0,
        help='ITL threshold step size in ms (default: 5)'
    )
    parser.add_argument(
        '--itl-col',
        type=str,
        default='inter_token_latency_p90',
        help='ITL P90 column name (default: inter_token_latency_p90)'
    )
    parser.add_argument(
        '--throughput-col',
        type=str,
        default='request_throughput_avg',
        help='Request throughput column name (default: request_throughput_avg)'
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
            if args.itl_col not in data[0]:
                print(f"❌ Error: Column '{args.itl_col}' not found in {name} CSV")
                return
            if args.throughput_col not in data[0]:
                print(f"❌ Error: Column '{args.throughput_col}' not found in {name} CSV")
                return
        
        # 计算两条曲线
        print(f"\n🔍 Calculating ITL vs throughput curves...")
        print(f"   ITL threshold range: 0 to {args.max_itl} ms, step: {args.step} ms")
        
        itl_thresholds_agg, max_throughputs_agg = calculate_itl_throughput_curve(
            data_agg, max_itl=args.max_itl, step=args.step,
            itl_p90_col=args.itl_col, throughput_col=args.throughput_col
        )
        
        itl_thresholds_disagg, max_throughputs_disagg = calculate_itl_throughput_curve(
            data_disagg, max_itl=args.max_itl, step=args.step,
            itl_p90_col=args.itl_col, throughput_col=args.throughput_col
        )
        
        # 读取ISL和OSL（优先使用agg的，如果不存在则用disagg的）
        isl = data_agg[0].get('input_sequence_length_avg', None) if data_agg else None
        osl = data_agg[0].get('output_sequence_length_avg', None) if data_agg else None
        if isl is None and data_disagg:
            isl = data_disagg[0].get('input_sequence_length_avg', None)
            osl = data_disagg[0].get('output_sequence_length_avg', None)
        
        # 获取部署名称作为标签
        label_agg = data_agg[0].get('deployment_name', 'Aggregated') if data_agg else None
        label_disagg = data_disagg[0].get('deployment_name', 'Disaggregated') if data_disagg else None
        
        print(f"\n📈 Statistics:")
        if isl is not None and osl is not None:
            print(f"   Input Sequence Length (ISL): {isl:.0f}")
            print(f"   Output Sequence Length (OSL): {osl:.0f}")
        if label_agg and label_disagg:
            print(f"   Deployment 1: {label_agg}")
            print(f"   Deployment 2: {label_disagg}")
        
        # 生成输出文件名
        if args.output:
            output_file = args.output
        else:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"plot_itl_throughput_compare_{timestamp}.png"
        
        # 构建标题
        if label_agg and label_disagg:
            plot_title = f"Maximum Request Throughput vs ITL Threshold\n({label_agg} vs {label_disagg})"
        else:
            plot_title = f"Maximum Request Throughput vs ITL Threshold\n(p90 ITL < threshold, Agg vs Disagg)"
        
        # 绘制对比图
        print(f"\n📊 Generating comparison plot...")
        plot_itl_throughput_compare(
            itl_thresholds_agg, max_throughputs_agg,
            itl_thresholds_disagg, max_throughputs_disagg,
            output_file=output_file,
            title=plot_title,
            isl=isl, osl=osl,
            label_agg=label_agg,
            label_disagg=label_disagg
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
        if args.itl_col not in data[0]:
            print(f"❌ Error: Column '{args.itl_col}' not found in CSV")
            return
        
        if args.throughput_col not in data[0]:
            print(f"❌ Error: Column '{args.throughput_col}' not found in CSV")
            return
        
        # 计算曲线数据
        print(f"\n🔍 Calculating ITL vs throughput curve...")
        print(f"   ITL threshold range: 0 to {args.max_itl} ms, step: {args.step} ms")
        
        itl_thresholds, max_throughputs = calculate_itl_throughput_curve(
            data, max_itl=args.max_itl, step=args.step,
            itl_p90_col=args.itl_col, throughput_col=args.throughput_col
        )
        
        # 显示统计信息
        non_zero_count = sum(1 for t in max_throughputs if t > 0)
        print(f"✅ Calculated {len(itl_thresholds)} data points")
        print(f"   Non-zero throughput points: {non_zero_count}")
        
        max_throughput_value = max(max_throughputs) if max_throughputs else 0
        max_idx = max_throughputs.index(max_throughput_value) if max_throughputs else 0
        max_itl_threshold = itl_thresholds[max_idx] if itl_thresholds else 0
        
        isl = data[0].get('input_sequence_length_avg', None) if data else None
        osl = data[0].get('output_sequence_length_avg', None) if data else None
        
        print(f"\n📈 Statistics:")
        if isl is not None and osl is not None:
            print(f"   Input Sequence Length (ISL): {isl:.0f}")
            print(f"   Output Sequence Length (OSL): {osl:.0f}")
        print(f"   Maximum throughput: {max_throughput_value:.2f} req/s")
        print(f"   Achieved at ITL threshold: {max_itl_threshold:.1f} ms")
        
        # 生成输出文件名
        if args.output:
            output_file = args.output
        else:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"plot_itl_throughput_{timestamp}.png"
        
        # 绘制图表
        print(f"\n📊 Generating plot...")
        plot_itl_throughput(
            itl_thresholds, max_throughputs,
            output_file=output_file,
            title=f"Maximum Request Throughput vs ITL Threshold\n(p90 ITL < threshold)",
            isl=isl, osl=osl
        )
    
    print(f"\n✅ Done!")


if __name__ == '__main__':
    main()

