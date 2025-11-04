#!/usr/bin/env python3
"""
根据SLO约束放缩因子绘制吞吐率曲线

功能：
1. 定义SLO约束字典（包含可放缩和不可放缩的指标）
2. 可放缩指标按放缩因子（5.0到0.0，步长0.1）同步放缩
3. 对于每个放缩因子，找到满足所有约束的最大吞吐率
4. 绘制两张图：请求吞吐率和输出token吞吐率
"""

import csv
import argparse
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional


# ==================== SLO约束配置 ====================
# 在这里定义你的SLO约束字典
# scalable_metrics: 可以同步放缩的指标
# fixed_metrics: 固定不变的指标

SLO_CONFIG = {
    'scalable_metrics': {
        # 可放缩指标：{'metric_name': original_value}
        # 这些指标会按放缩因子同步缩放
        'time_to_first_token_p90': 4000.0,  # ms
        'inter_token_latency_p90': 10.0,     # ms
    },
    'fixed_metrics': {
        # 固定指标：{'metric_name': fixed_value}
        # 这些指标不受放缩因子影响
        # 可以留空 {}，表示没有固定约束
    }
}

# 默认列名映射（CSV中的实际列名）
METRIC_COLUMN_MAP = {
    'time_to_first_token_p90': 'time_to_first_token_p90',
    'inter_token_latency_p90': 'inter_token_latency_p90',
    'request_throughput_avg': 'request_throughput_avg',
    'output_token_throughput_avg': 'output_token_throughput_avg',
}


def load_csv_data(csv_file: str) -> List[Dict]:
    """从CSV文件加载数据"""
    data = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
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


def check_slo_constraints(
    row: Dict,
    scalable_metrics: Dict[str, float],
    fixed_metrics: Dict[str, float],
    scale_factor: float,
    metric_column_map: Dict[str, str]
) -> bool:
    """
    检查数据点是否满足SLO约束
    
    Args:
        row: 数据行
        scalable_metrics: 可放缩指标字典
        fixed_metrics: 固定指标字典
        scale_factor: 放缩因子
        metric_column_map: 指标名到CSV列名的映射
    
    Returns:
        是否满足所有约束
    """
    # 检查可放缩指标（实际值 < 放缩后的约束值）
    for metric_name, original_constraint in scalable_metrics.items():
        csv_column = metric_column_map.get(metric_name, metric_name)
        actual_value = row.get(csv_column, float('inf'))
        
        # 放缩后的约束值 = 原始值 * 放缩因子
        scaled_constraint = original_constraint * scale_factor
        
        # 需要满足：实际值 < 放缩后的约束值
        if actual_value >= scaled_constraint:
            return False
    
    # 检查固定指标（实际值 < 固定约束值）
    for metric_name, fixed_constraint in fixed_metrics.items():
        csv_column = metric_column_map.get(metric_name, metric_name)
        actual_value = row.get(csv_column, float('inf'))
        
        # 需要满足：实际值 < 固定约束值
        if actual_value >= fixed_constraint:
            return False
    
    return True


def find_max_concurrency_for_scale_factor(
    data: List[Dict],
    scalable_metrics: Dict[str, float],
    fixed_metrics: Dict[str, float],
    scale_factor: float,
    metric_column_map: Dict[str, str]
) -> int:
    """
    找到给定放缩因子下满足所有约束的最大并发度
    
    Returns:
        max_concurrency: 最大并发度，如果没有满足条件的数据则返回0
    """
    max_concurrency = 0
    
    for row in data:
        # 检查是否满足约束
        if check_slo_constraints(row, scalable_metrics, fixed_metrics, 
                                 scale_factor, metric_column_map):
            concurrency = row.get('concurrency', 0)
            if isinstance(concurrency, (int, float)):
                concurrency = int(concurrency)
                if concurrency > max_concurrency:
                    max_concurrency = concurrency
    
    return max_concurrency


def find_max_throughput_for_scale_factor(
    data: List[Dict],
    scalable_metrics: Dict[str, float],
    fixed_metrics: Dict[str, float],
    scale_factor: float,
    metric_column_map: Dict[str, str],
    request_col: str = 'request_throughput_avg',
    token_col: str = 'output_token_throughput_avg'
) -> Tuple[float, float]:
    """
    找到给定放缩因子下满足所有约束的最大吞吐率
    
    Returns:
        (max_request_throughput, max_token_throughput)
    """
    max_request_throughput = 0.0
    max_token_throughput = 0.0
    
    for row in data:
        # 检查是否满足约束
        if check_slo_constraints(row, scalable_metrics, fixed_metrics, 
                                 scale_factor, metric_column_map):
            request_throughput = row.get(request_col, 0.0)
            token_throughput = row.get(token_col, 0.0)
            
            if request_throughput > max_request_throughput:
                max_request_throughput = request_throughput
            
            if token_throughput > max_token_throughput:
                max_token_throughput = token_throughput
    
    return max_request_throughput, max_token_throughput


def calculate_scaling_curve_concurrency(
    data: List[Dict],
    scalable_metrics: Dict[str, float],
    fixed_metrics: Dict[str, float],
    metric_column_map: Dict[str, str],
    scale_range: Tuple[float, float] = (0.0, 5.0),
    scale_step: float = 0.1
) -> Tuple[List[float], List[int]]:
    """
    计算放缩因子与最大并发度的关系曲线
    
    Returns:
        (scale_factors, max_concurrencies)
    """
    scale_factors = []
    max_concurrencies = []
    
    scale_min, scale_max = scale_range
    
    # 从最大值到最小值（或反之，根据需求）
    # 计算需要多少步
    num_steps = int((scale_max - scale_min) / scale_step) + 1
    
    for i in range(num_steps):
        current_scale = scale_max - i * scale_step
        # 处理浮点数精度问题，四舍五入到合适的小数位数
        decimal_places = len(str(scale_step).split('.')[-1]) if '.' in str(scale_step) else 0
        current_scale = round(current_scale, decimal_places + 2)
        
        max_concurrency = find_max_concurrency_for_scale_factor(
            data, scalable_metrics, fixed_metrics, current_scale,
            metric_column_map
        )
        
        scale_factors.append(current_scale)
        max_concurrencies.append(max_concurrency)
        
        # 如果已经到达最小值，退出
        if current_scale <= scale_min + 1e-10:
            break
    
    return scale_factors, max_concurrencies


def calculate_scaling_curve_throughput(
    data: List[Dict],
    scalable_metrics: Dict[str, float],
    fixed_metrics: Dict[str, float],
    metric_column_map: Dict[str, str],
    scale_range: Tuple[float, float] = (0.0, 5.0),
    scale_step: float = 0.1,
    request_col: str = 'request_throughput_avg',
    token_col: str = 'output_token_throughput_avg'
) -> Tuple[List[float], List[float], List[float]]:
    """
    计算放缩因子与最大吞吐率的关系曲线
    
    Returns:
        (scale_factors, max_request_throughputs, max_token_throughputs)
    """
    scale_factors = []
    max_request_throughputs = []
    max_token_throughputs = []
    
    scale_min, scale_max = scale_range
    
    # 从最大值到最小值（或反之，根据需求）
    # 计算需要多少步
    num_steps = int((scale_max - scale_min) / scale_step) + 1
    
    for i in range(num_steps):
        current_scale = scale_max - i * scale_step
        # 处理浮点数精度问题，四舍五入到合适的小数位数
        decimal_places = len(str(scale_step).split('.')[-1]) if '.' in str(scale_step) else 0
        current_scale = round(current_scale, decimal_places + 2)
        
        max_req, max_token = find_max_throughput_for_scale_factor(
            data, scalable_metrics, fixed_metrics, current_scale,
            metric_column_map, request_col, token_col
        )
        
        scale_factors.append(current_scale)
        max_request_throughputs.append(max_req)
        max_token_throughputs.append(max_token)
        
        # 如果已经到达最小值，退出
        if current_scale <= scale_min + 1e-10:
            break
    
    return scale_factors, max_request_throughputs, max_token_throughputs


def plot_scaling_concurrency(
    scale_factors: List[float],
    max_concurrencies: List[int],
    output_file: str = None,
    title: str = "Maximum Concurrency vs SLO Scaling Factor",
    isl: float = None,
    osl: float = None,
    scalable_metrics: Dict[str, float] = None,
    fixed_metrics: Dict[str, float] = None,
    label: str = None,
    color: str = 'blue',
    marker: str = 'o'
):
    """
    绘制放缩因子与最大并发度的关系图
    """
    # 构建标题后缀
    title_suffix = ""
    if isl is not None and osl is not None:
        title_suffix = f" (ISL={isl:.0f}, OSL={osl:.0f})"
    
    # 构建约束信息文本
    constraint_text = ""
    if scalable_metrics:
        constraint_text += "\nScalable: " + ", ".join([f"{k}={v}" for k, v in scalable_metrics.items()])
    if fixed_metrics:
        constraint_text += "\nFixed: " + ", ".join([f"{k}={v}" for k, v in fixed_metrics.items()])
    
    # 创建单个图
    plt.figure(figsize=(12, 8))
    
    # 构建标签
    plot_label = f"{label} - Max Concurrency" if label else 'Max Concurrency'
    
    # 绘制曲线
    plt.plot(scale_factors, max_concurrencies, marker=marker, linewidth=2, 
             markersize=6, color=color, label=plot_label, alpha=0.8)
    plt.xlabel('SLO Scaling Factor', fontsize=12)
    plt.ylabel('Max Concurrency', fontsize=12)
    plt.title(f'Maximum Concurrency vs SLO Scaling Factor{title_suffix}{constraint_text}', 
              fontsize=14, fontweight='bold')
    plt.legend(loc='best', fontsize=10)
    plt.grid(True, alpha=0.3, linestyle='--')
    # 反转x轴，让大值在左边，小值在右边
    if scale_factors:
        plt.xlim(left=min(scale_factors), right=max(scale_factors))
        plt.gca().invert_xaxis()  # 反转x轴
    if max_concurrencies and max(max_concurrencies) > 0:
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


def plot_scaling_concurrency_compare(
    scale_factors_agg: List[float],
    max_concurrencies_agg: List[int],
    scale_factors_disagg: List[float],
    max_concurrencies_disagg: List[int],
    output_file: str = None,
    title: str = "Maximum Concurrency vs SLO Scaling Factor",
    isl: float = None,
    osl: float = None,
    scalable_metrics: Dict[str, float] = None,
    fixed_metrics: Dict[str, float] = None
):
    """
    在同一图中绘制agg和disagg的对比曲线
    """
    # 构建标题后缀
    title_suffix = ""
    if isl is not None and osl is not None:
        title_suffix = f" (ISL={isl:.0f}, OSL={osl:.0f})"
    
    # 构建约束信息文本
    constraint_text = ""
    if scalable_metrics:
        constraint_text += "\nScalable: " + ", ".join([f"{k}={v}" for k, v in scalable_metrics.items()])
    if fixed_metrics:
        constraint_text += "\nFixed: " + ", ".join([f"{k}={v}" for k, v in fixed_metrics.items()])
    
    # 创建单个图
    plt.figure(figsize=(12, 8))
    
    # 绘制agg曲线
    plt.plot(scale_factors_agg, max_concurrencies_agg, marker='o', linewidth=2, 
             markersize=6, color='blue', label='Aggregated', alpha=0.8)
    
    # 绘制disagg曲线
    plt.plot(scale_factors_disagg, max_concurrencies_disagg, marker='s', linewidth=2,
             markersize=6, color='red', label='Disaggregated', alpha=0.8)
    
    plt.xlabel('SLO Scaling Factor', fontsize=12)
    plt.ylabel('Max Concurrency', fontsize=12)
    plt.title(f'Maximum Concurrency vs SLO Scaling Factor{title_suffix}{constraint_text} (Agg vs Disagg)', 
              fontsize=14, fontweight='bold')
    plt.legend(loc='best', fontsize=10)
    plt.grid(True, alpha=0.3, linestyle='--')
    
    # 反转x轴，让大值在左边，小值在右边
    all_scale_factors = scale_factors_agg + scale_factors_disagg
    if all_scale_factors:
        plt.xlim(left=min(all_scale_factors), right=max(all_scale_factors))
        plt.gca().invert_xaxis()
    
    all_concurrencies = max_concurrencies_agg + max_concurrencies_disagg
    if all_concurrencies and max(all_concurrencies) > 0:
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


def plot_scaling_throughput(
    scale_factors: List[float],
    max_request_throughputs: List[float],
    max_token_throughputs: List[float],
    output_file: str = None,
    title: str = "Maximum Throughput vs SLO Scaling Factor",
    isl: float = None,
    osl: float = None,
    scalable_metrics: Dict[str, float] = None,
    fixed_metrics: Dict[str, float] = None,
    label: str = None,
    color_req: str = 'blue',
    color_token: str = 'red',
    marker_req: str = 'o',
    marker_token: str = 's'
):
    """
    绘制放缩因子与最大吞吐率的关系图
    """
    # 构建标题后缀
    title_suffix = ""
    if isl is not None and osl is not None:
        title_suffix = f" (ISL={isl:.0f}, OSL={osl:.0f})"
    
    # 构建约束信息文本
    constraint_text = ""
    if scalable_metrics:
        constraint_text += "\nScalable: " + ", ".join([f"{k}={v}" for k, v in scalable_metrics.items()])
    if fixed_metrics:
        constraint_text += "\nFixed: " + ", ".join([f"{k}={v}" for k, v in fixed_metrics.items()])
    
    # 创建两个子图
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 12))
    
    # 构建标签
    label_req = f"{label} - Request" if label else 'Max Request Throughput'
    label_token = f"{label} - Token" if label else 'Max Token Throughput'
    
    # 第一张图：请求吞吐率
    ax1.plot(scale_factors, max_request_throughputs, marker=marker_req, linewidth=2, 
             markersize=6, color=color_req, label=label_req, alpha=0.8)
    ax1.set_xlabel('SLO Scaling Factor', fontsize=12)
    ax1.set_ylabel('Max Request Throughput (req/s)', fontsize=12)
    ax1.set_title(f'Maximum Request Throughput vs SLO Scaling Factor{title_suffix}{constraint_text}', 
                  fontsize=14, fontweight='bold')
    ax1.legend(loc='best', fontsize=10)
    ax1.grid(True, alpha=0.3, linestyle='--')
    if scale_factors:
        ax1.set_xlim(left=min(scale_factors), right=max(scale_factors))
        ax1.invert_xaxis()  # 反转x轴
    if max_request_throughputs and max(max_request_throughputs) > 0:
        ax1.set_ylim(bottom=0)
    
    # 第二张图：token吞吐率
    ax2.plot(scale_factors, max_token_throughputs, marker=marker_token, linewidth=2, 
             markersize=6, color=color_token, label=label_token, alpha=0.8)
    ax2.set_xlabel('SLO Scaling Factor', fontsize=12)
    ax2.set_ylabel('Max Token Throughput (tokens/s)', fontsize=12)
    ax2.set_title(f'Maximum Token Throughput vs SLO Scaling Factor{title_suffix}{constraint_text}', 
                  fontsize=14, fontweight='bold')
    ax2.legend(loc='best', fontsize=10)
    ax2.grid(True, alpha=0.3, linestyle='--')
    if scale_factors:
        ax2.set_xlim(left=min(scale_factors), right=max(scale_factors))
        ax2.invert_xaxis()  # 反转x轴
    if max_token_throughputs and max(max_token_throughputs) > 0:
        ax2.set_ylim(bottom=0)
    
    # 调整布局
    plt.tight_layout()
    
    # 保存或显示
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Plot saved to: {output_file}")
    else:
        plt.show()
    
    plt.close()


def plot_scaling_throughput_compare(
    scale_factors_agg: List[float],
    max_request_throughputs_agg: List[float],
    max_token_throughputs_agg: List[float],
    scale_factors_disagg: List[float],
    max_request_throughputs_disagg: List[float],
    max_token_throughputs_disagg: List[float],
    output_file: str = None,
    title: str = "Maximum Throughput vs SLO Scaling Factor",
    isl: float = None,
    osl: float = None,
    scalable_metrics: Dict[str, float] = None,
    fixed_metrics: Dict[str, float] = None
):
    """
    在同一图中绘制agg和disagg的对比曲线
    """
    # 构建标题后缀
    title_suffix = ""
    if isl is not None and osl is not None:
        title_suffix = f" (ISL={isl:.0f}, OSL={osl:.0f})"
    
    # 构建约束信息文本
    constraint_text = ""
    if scalable_metrics:
        constraint_text += "\nScalable: " + ", ".join([f"{k}={v}" for k, v in scalable_metrics.items()])
    if fixed_metrics:
        constraint_text += "\nFixed: " + ", ".join([f"{k}={v}" for k, v in fixed_metrics.items()])
    
    # 创建两个子图
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 12))
    
    # 第一张图：请求吞吐率
    ax1.plot(scale_factors_agg, max_request_throughputs_agg, marker='o', linewidth=2, 
             markersize=6, color='blue', label='Aggregated', alpha=0.8)
    ax1.plot(scale_factors_disagg, max_request_throughputs_disagg, marker='s', linewidth=2,
             markersize=6, color='red', label='Disaggregated', alpha=0.8)
    ax1.set_xlabel('SLO Scaling Factor', fontsize=12)
    ax1.set_ylabel('Max Request Throughput (req/s)', fontsize=12)
    ax1.set_title(f'Maximum Request Throughput vs SLO Scaling Factor{title_suffix}{constraint_text} (Agg vs Disagg)', 
                  fontsize=14, fontweight='bold')
    ax1.legend(loc='best', fontsize=10)
    ax1.grid(True, alpha=0.3, linestyle='--')
    all_scale_factors = scale_factors_agg + scale_factors_disagg
    if all_scale_factors:
        ax1.set_xlim(left=min(all_scale_factors), right=max(all_scale_factors))
        ax1.invert_xaxis()  # 反转x轴
    all_req_throughputs = max_request_throughputs_agg + max_request_throughputs_disagg
    if all_req_throughputs and max(all_req_throughputs) > 0:
        ax1.set_ylim(bottom=0)
    
    # 第二张图：token吞吐率
    ax2.plot(scale_factors_agg, max_token_throughputs_agg, marker='o', linewidth=2, 
             markersize=6, color='blue', label='Aggregated', alpha=0.8)
    ax2.plot(scale_factors_disagg, max_token_throughputs_disagg, marker='s', linewidth=2,
             markersize=6, color='red', label='Disaggregated', alpha=0.8)
    ax2.set_xlabel('SLO Scaling Factor', fontsize=12)
    ax2.set_ylabel('Max Token Throughput (tokens/s)', fontsize=12)
    ax2.set_title(f'Maximum Token Throughput vs SLO Scaling Factor{title_suffix}{constraint_text} (Agg vs Disagg)', 
                  fontsize=14, fontweight='bold')
    ax2.legend(loc='best', fontsize=10)
    ax2.grid(True, alpha=0.3, linestyle='--')
    if all_scale_factors:
        ax2.set_xlim(left=min(all_scale_factors), right=max(all_scale_factors))
        ax2.invert_xaxis()  # 反转x轴
    all_token_throughputs = max_token_throughputs_agg + max_token_throughputs_disagg
    if all_token_throughputs and max(all_token_throughputs) > 0:
        ax2.set_ylim(bottom=0)
    
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
        description='Plot maximum throughput vs SLO scaling factor'
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
        help='Output image file path'
    )
    parser.add_argument(
        '--scale-min',
        type=float,
        default=0.0,
        help='Minimum scaling factor (default: 0.0)'
    )
    parser.add_argument(
        '--scale-max',
        type=float,
        default=5.0,
        help='Maximum scaling factor (default: 5.0)'
    )
    parser.add_argument(
        '--scale-step',
        type=float,
        default=0.1,
        help='Scaling factor step size (default: 0.1)'
    )
    parser.add_argument(
        '--y-axis',
        type=str,
        choices=['throughput', 'concurrency'],
        default='throughput',
        help='Y-axis metric: throughput (request and token throughput) or concurrency (max concurrency) (default: throughput)'
    )
    
    args = parser.parse_args()
    
    # 判断是单文件模式还是对比模式
    compare_mode = args.csv_agg is not None and args.csv_disagg is not None
    
    # 获取SLO配置
    scalable_metrics = SLO_CONFIG.get('scalable_metrics', {})
    fixed_metrics = SLO_CONFIG.get('fixed_metrics', {})
    
    print(f"\n📋 SLO Configuration:")
    if scalable_metrics:
        print(f"   Scalable metrics (will be scaled):")
        for metric, value in scalable_metrics.items():
            print(f"      {metric}: {value}")
    if fixed_metrics:
        print(f"   Fixed metrics (constant):")
        for metric, value in fixed_metrics.items():
            print(f"      {metric}: {value}")
    if not scalable_metrics and not fixed_metrics:
        print("   ⚠️  No SLO constraints defined! Please edit SLO_CONFIG in the script.")
    
    metric_column_map = METRIC_COLUMN_MAP
    all_metrics = list(scalable_metrics.keys()) + list(fixed_metrics.keys())
    
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
            for metric in all_metrics:
                csv_col = metric_column_map.get(metric, metric)
                if csv_col not in data[0]:
                    print(f"❌ Error: Column '{csv_col}' (for metric '{metric}') not found in {name} CSV")
                    return
        
        # 读取ISL和OSL
        isl = data_agg[0].get('input_sequence_length_avg', None) if data_agg else None
        osl = data_agg[0].get('output_sequence_length_avg', None) if data_agg else None
        if isl is None and data_disagg:
            isl = data_disagg[0].get('input_sequence_length_avg', None)
            osl = data_disagg[0].get('output_sequence_length_avg', None)
        
        # 计算两条曲线
        print(f"\n🔍 Calculating scaling curves...")
        print(f"   Scaling factor range: {args.scale_min} to {args.scale_max}, step: {args.scale_step}")
        print(f"   Y-axis metric: {args.y_axis}")
        
        if args.y_axis == 'concurrency':
            scale_factors_agg, max_concurrencies_agg = calculate_scaling_curve_concurrency(
                data_agg, scalable_metrics, fixed_metrics, metric_column_map,
                scale_range=(args.scale_min, args.scale_max), scale_step=args.scale_step
            )
            
            scale_factors_disagg, max_concurrencies_disagg = calculate_scaling_curve_concurrency(
                data_disagg, scalable_metrics, fixed_metrics, metric_column_map,
                scale_range=(args.scale_min, args.scale_max), scale_step=args.scale_step
            )
            
            print(f"✅ Calculated {len(scale_factors_agg)} data points for each mode")
            
            # 显示统计信息
            if max_concurrencies_agg:
                max_agg = max(max_concurrencies_agg)
                max_agg_idx = max_concurrencies_agg.index(max_agg)
                max_agg_scale = scale_factors_agg[max_agg_idx]
                print(f"\n📈 Aggregated Statistics:")
                print(f"   Maximum concurrency: {max_agg} (at scale factor {max_agg_scale:.2f})")
            
            if max_concurrencies_disagg:
                max_disagg = max(max_concurrencies_disagg)
                max_disagg_idx = max_concurrencies_disagg.index(max_disagg)
                max_disagg_scale = scale_factors_disagg[max_disagg_idx]
                print(f"\n📈 Disaggregated Statistics:")
                print(f"   Maximum concurrency: {max_disagg} (at scale factor {max_disagg_scale:.2f})")
            
            # 生成输出文件名
            if args.output:
                output_file = args.output
            else:
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_file = f"plot_slo_scaling_concurrency_compare_{timestamp}.png"
            
            # 绘制对比图
            print(f"\n📊 Generating comparison plot...")
            plot_scaling_concurrency_compare(
                scale_factors_agg, max_concurrencies_agg,
                scale_factors_disagg, max_concurrencies_disagg,
                output_file=output_file,
                title="Maximum Concurrency vs SLO Scaling Factor (Agg vs Disagg)",
                isl=isl, osl=osl,
                scalable_metrics=scalable_metrics,
                fixed_metrics=fixed_metrics
            )
        else:
            # throughput 模式
            scale_factors_agg, max_request_throughputs_agg, max_token_throughputs_agg = calculate_scaling_curve_throughput(
                data_agg, scalable_metrics, fixed_metrics, metric_column_map,
                scale_range=(args.scale_min, args.scale_max), scale_step=args.scale_step
            )
            
            scale_factors_disagg, max_request_throughputs_disagg, max_token_throughputs_disagg = calculate_scaling_curve_throughput(
                data_disagg, scalable_metrics, fixed_metrics, metric_column_map,
                scale_range=(args.scale_min, args.scale_max), scale_step=args.scale_step
            )
            
            print(f"✅ Calculated {len(scale_factors_agg)} data points for each mode")
            
            # 生成输出文件名
            if args.output:
                output_file = args.output
            else:
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_file = f"plot_slo_scaling_throughput_compare_{timestamp}.png"
            
            # 绘制对比图
            print(f"\n📊 Generating comparison plot...")
            plot_scaling_throughput_compare(
                scale_factors_agg, max_request_throughputs_agg, max_token_throughputs_agg,
                scale_factors_disagg, max_request_throughputs_disagg, max_token_throughputs_disagg,
                output_file=output_file,
                title="Maximum Throughput vs SLO Scaling Factor (Agg vs Disagg)",
                isl=isl, osl=osl,
                scalable_metrics=scalable_metrics,
                fixed_metrics=fixed_metrics
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
        for metric in all_metrics:
            csv_col = metric_column_map.get(metric, metric)
            if csv_col not in data[0]:
                print(f"❌ Error: Column '{csv_col}' (for metric '{metric}') not found in CSV")
                print(f"   Available columns: {', '.join(list(data[0].keys())[:10])}...")
                return
        
        # 读取ISL和OSL
        isl = data[0].get('input_sequence_length_avg', None) if data else None
        osl = data[0].get('output_sequence_length_avg', None) if data else None
        
        # 计算曲线数据
        print(f"\n🔍 Calculating scaling curve...")
        print(f"   Scaling factor range: {args.scale_min} to {args.scale_max}, step: {args.scale_step}")
        print(f"   Y-axis metric: {args.y_axis}")
        
        if args.y_axis == 'concurrency':
            scale_factors, max_concurrencies = calculate_scaling_curve_concurrency(
                data, scalable_metrics, fixed_metrics, metric_column_map,
                scale_range=(args.scale_min, args.scale_max), scale_step=args.scale_step
            )
            
            # 显示统计信息
            print(f"✅ Calculated {len(scale_factors)} data points")
            
            non_zero = sum(1 for c in max_concurrencies if c > 0)
            print(f"   Non-zero concurrency points: {non_zero}")
            
            # 找到最大值
            if max_concurrencies:
                max_concurrency_value = max(max_concurrencies)
                max_concurrency_idx = max_concurrencies.index(max_concurrency_value)
                max_concurrency_scale = scale_factors[max_concurrency_idx]
                print(f"\n📈 Concurrency Statistics:")
                print(f"   Maximum: {max_concurrency_value} (at scale factor {max_concurrency_scale:.2f})")
            
            # 生成输出文件名
            if args.output:
                output_file = args.output
            else:
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_file = f"plot_slo_scaling_concurrency_{timestamp}.png"
            
            # 绘制图表
            print(f"\n📊 Generating plot...")
            plot_scaling_concurrency(
                scale_factors, max_concurrencies,
                output_file=output_file,
                title="Maximum Concurrency vs SLO Scaling Factor",
                isl=isl, osl=osl,
                scalable_metrics=scalable_metrics,
                fixed_metrics=fixed_metrics
            )
        else:
            # throughput 模式
            scale_factors, max_request_throughputs, max_token_throughputs = calculate_scaling_curve_throughput(
                data, scalable_metrics, fixed_metrics, metric_column_map,
                scale_range=(args.scale_min, args.scale_max), scale_step=args.scale_step
            )
            
            # 显示统计信息
            print(f"✅ Calculated {len(scale_factors)} data points")
            
            non_zero_req = sum(1 for t in max_request_throughputs if t > 0)
            non_zero_token = sum(1 for t in max_token_throughputs if t > 0)
            print(f"   Non-zero request throughput points: {non_zero_req}")
            print(f"   Non-zero token throughput points: {non_zero_token}")
            
            # 找到最大值
            if max_request_throughputs:
                max_req_value = max(max_request_throughputs)
                max_req_idx = max_request_throughputs.index(max_req_value)
                max_req_scale = scale_factors[max_req_idx]
                print(f"\n📈 Request Throughput Statistics:")
                print(f"   Maximum: {max_req_value:.2f} req/s (at scale factor {max_req_scale:.2f})")
            
            if max_token_throughputs:
                max_token_value = max(max_token_throughputs)
                max_token_idx = max_token_throughputs.index(max_token_value)
                max_token_scale = scale_factors[max_token_idx]
                print(f"\n📈 Token Throughput Statistics:")
                print(f"   Maximum: {max_token_value:.2f} tokens/s (at scale factor {max_token_scale:.2f})")
            
            # 生成输出文件名
            if args.output:
                output_file = args.output
            else:
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_file = f"plot_slo_scaling_throughput_{timestamp}.png"
            
            # 绘制图表
            print(f"\n📊 Generating plot...")
            plot_scaling_throughput(
                scale_factors, max_request_throughputs, max_token_throughputs,
                output_file=output_file,
                title="Maximum Throughput vs SLO Scaling Factor",
                isl=isl, osl=osl,
                scalable_metrics=scalable_metrics,
                fixed_metrics=fixed_metrics
            )
    
    print(f"\n✅ Done!")


if __name__ == '__main__':
    main()

