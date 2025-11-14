#!/usr/bin/env python3
"""
计算相同并发度下，两个部署的 TTFT p90 倍数关系

x轴: 并发度 (concurrency)
y轴: TTFT p90 倍数 (disagg / agg)
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


def calculate_ratio(
    data_agg: List[Dict],
    data_disagg: List[Dict],
    metric_col: str = 'time_to_first_token_p90'
) -> Tuple[List[int], List[float], List[str]]:
    """
    计算相同并发度下的倍数关系（大值/小值，倍数始终 >= 1.0）
    
    Args:
        data_agg: 聚合部署的数据
        data_disagg: 分离部署的数据
        metric_col: 要比较的指标列名
    
    Returns:
        (concurrencies, ratios, labels) 元组
        - ratios: 倍数关系（大值/小值，始终 >= 1.0）
        - labels: 每个点的标签，表示哪个部署的值更大
    """
    # 创建并发度到数据的映射
    agg_dict = {row['concurrency']: row for row in data_agg}
    disagg_dict = {row['concurrency']: row for row in data_disagg}
    
    # 找到共同的并发度
    common_concurrencies = sorted(set(agg_dict.keys()) & set(disagg_dict.keys()))
    
    concurrencies = []
    ratios = []
    labels = []
    
    for c in common_concurrencies:
        agg_value = agg_dict[c].get(metric_col, None)
        disagg_value = disagg_dict[c].get(metric_col, None)
        
        # 检查值是否有效（非零且非空）
        if agg_value is not None and disagg_value is not None and agg_value > 0 and disagg_value > 0:
            # 计算倍数：大值/小值，确保倍数 >= 1.0
            if disagg_value >= agg_value:
                ratio = disagg_value / agg_value
                label = 'disagg/agg'
            else:
                ratio = agg_value / disagg_value
                label = 'agg/disagg'
            
            concurrencies.append(c)
            ratios.append(ratio)
            labels.append(label)
    
    return concurrencies, ratios, labels


def plot_ttft_ratio(
    data_agg: List[Dict],
    data_disagg: List[Dict],
    output_file: str = None,
    title: str = "TTFT p90 Ratio vs Concurrency",
    xlabel: str = "Concurrency",
    ylabel: str = None,  # 将根据实际部署名称动态设置
    ttft_col: str = 'time_to_first_token_p90',
    isl: float = None,
    osl: float = None,
    label_agg: str = None,
    label_disagg: str = None
):
    """
    绘制 TTFT p90 倍数关系图
    
    Args:
        data_agg: 聚合部署的数据
        data_disagg: 分离部署的数据
        output_file: 输出文件路径
        title: 图表标题
        xlabel: X轴标签
        ylabel: Y轴标签
        ttft_col: TTFT列名
        isl: 输入序列长度（用于标题）
        osl: 输出序列长度（用于标题）
        label_agg: 聚合部署的标签
        label_disagg: 分离部署的标签
    """
    # 计算倍数关系（大值/小值）
    concurrencies, ratios, ratio_labels = calculate_ratio(data_agg, data_disagg, ttft_col)
    
    if not concurrencies:
        print("❌ No common concurrency levels found!")
        return
    
    # 创建图表
    plt.figure(figsize=(12, 8))
    
    # 根据哪个值更大，确定图例标签
    # 统计大多数点的比例关系，确定主要模式
    disagg_larger_count = sum(1 for label in ratio_labels if label == 'disagg/agg')
    agg_larger_count = sum(1 for label in ratio_labels if label == 'agg/disagg')
    
    if disagg_larger_count >= agg_larger_count:
        # 大多数情况下 disagg 更大
        legend_label = f'{label_disagg} / {label_agg}'
        ylabel_text = f'TTFT p90 Ratio ({label_disagg} / {label_agg})'
    else:
        # 大多数情况下 agg 更大
        legend_label = f'{label_agg} / {label_disagg}'
        ylabel_text = f'TTFT p90 Ratio ({label_agg} / {label_disagg})'
    
    # 绘制倍数曲线（使用正常坐标，不使用对数坐标）
    plt.plot(concurrencies, ratios, 'o-', linewidth=2, markersize=8, 
             color='#d62728', label=legend_label)
    
    # 添加 y=1 的参考线（表示相等）
    plt.axhline(y=1.0, color='gray', linestyle='--', linewidth=1, alpha=0.5, label='Equal (Ratio = 1.0)')
    
    # 设置标题和标签
    if isl is not None and osl is not None:
        full_title = f"{title}\n(ISL={isl:.0f}, OSL={osl:.0f})"
    else:
        full_title = title
    
    plt.title(full_title, fontsize=14, fontweight='bold')
    plt.xlabel(xlabel, fontsize=12)
    plt.ylabel(ylabel_text, fontsize=12)
    
    # 不使用对数坐标，使用正常坐标
    # 设置X轴范围
    if concurrencies:
        plt.xlim(left=0)
    
    # 添加网格
    plt.grid(True, alpha=0.3, linestyle='--')
    
    # 添加图例
    plt.legend(loc='best', fontsize=10)
    
    # 添加说明文字
    plt.figtext(0.02, 0.02, 
                f"Ratio = larger value / smaller value (always >= 1.0)\nRatio = 1.0 means equal performance",
                fontsize=9, style='italic', alpha=0.7)
    
    plt.tight_layout()
    
    # 保存图表
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"✅ Saved plot: {output_path}")
    else:
        plt.show()
    
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description='Plot TTFT p90 ratio (disagg/agg) vs concurrency'
    )
    parser.add_argument(
        '--csv-agg',
        type=str,
        required=True,
        help='CSV file for aggregated deployment'
    )
    parser.add_argument(
        '--csv-disagg',
        type=str,
        required=True,
        help='CSV file for disaggregated deployment'
    )
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Output PNG file path'
    )
    parser.add_argument(
        '--ttft-col',
        type=str,
        default='time_to_first_token_p90',
        help='TTFT column name (default: time_to_first_token_p90)'
    )
    parser.add_argument(
        '--title',
        type=str,
        default='TTFT p90 Ratio vs Concurrency',
        help='Plot title'
    )
    
    args = parser.parse_args()
    
    # 加载数据
    print(f"📊 Loading aggregated data from: {args.csv_agg}")
    data_agg = load_csv_data(args.csv_agg)
    print(f"✅ Loaded {len(data_agg)} data points (agg)")
    
    print(f"📊 Loading disaggregated data from: {args.csv_disagg}")
    data_disagg = load_csv_data(args.csv_disagg)
    print(f"✅ Loaded {len(data_disagg)} data points (disagg)")
    
    # 检查必需的列
    if args.ttft_col not in data_agg[0]:
        print(f"❌ Error: Column '{args.ttft_col}' not found in agg CSV")
        return
    if args.ttft_col not in data_disagg[0]:
        print(f"❌ Error: Column '{args.ttft_col}' not found in disagg CSV")
        return
    
    # 读取ISL和OSL
    isl = data_agg[0].get('input_sequence_length_avg', None) if data_agg else None
    osl = data_agg[0].get('output_sequence_length_avg', None) if data_agg else None
    if isl is None and data_disagg:
        isl = data_disagg[0].get('input_sequence_length_avg', None)
        osl = data_disagg[0].get('output_sequence_length_avg', None)
    
    # 获取部署名称作为标签
    label_agg = data_agg[0].get('deployment_name', 'Aggregated') if data_agg else 'Aggregated'
    label_disagg = data_disagg[0].get('deployment_name', 'Disaggregated') if data_disagg else 'Disaggregated'
    
    # 绘制图表
    plot_ttft_ratio(
        data_agg=data_agg,
        data_disagg=data_disagg,
        output_file=args.output,
        title=args.title,
        ttft_col=args.ttft_col,
        isl=isl,
        osl=osl,
        label_agg=label_agg,
        label_disagg=label_disagg
    )


if __name__ == '__main__':
    main()

