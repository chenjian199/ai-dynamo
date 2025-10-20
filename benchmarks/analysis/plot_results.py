#!/usr/bin/env python3

import os
import json
import glob
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import re

def extract_deployment_name(benchmark_name):
    """从benchmark名称中提取简洁的部署名称"""
    # 移除时间戳部分
    name = re.sub(r'_\d{8}_\d{6}$', '', benchmark_name)
    
    # 简化部署名称
    name_mapping = {
        'vllm-agg': 'agg',
        'vllm-agg-kvbm': 'agg-kvbm',
        'vllm-agg-router': 'agg-router',
        'vllm-disagg': 'disagg',
        'vllm-disagg-kvbm': 'disagg-kvbm',
        'vllm-disagg-kvbm-4p4d': 'disagg-4p4d',
        'vllm-disagg-kvbm-tp2': 'disagg-tp2',
        'vllm-v1-disagg-router': 'disagg-router',
        'vllm-disagg-2p6d': 'disagg-2p6d',
        'vllm-disagg-6p2d': 'disagg-6p2d',
        'vllm-disagg-multinode': 'disagg-multinode',
        'vllm-disagg-planner': 'disagg-planner'
    }
    
    return name_mapping.get(name, name)

def load_benchmark_data(results_dir):
    """加载所有benchmark结果数据"""
    data = {}
    
    # 查找所有benchmark结果目录
    benchmark_dirs = glob.glob(os.path.join(results_dir, "vllm-*"))
    # 过滤出包含时间戳的目录
    benchmark_dirs = [d for d in benchmark_dirs if re.search(r'_\d{8}_\d{6}$', os.path.basename(d))]
    
    for benchmark_dir in benchmark_dirs:
        benchmark_name = os.path.basename(benchmark_dir)
        deployment_name = extract_deployment_name(benchmark_name)
        
        if deployment_name not in data:
            data[deployment_name] = {}
        
        # 查找所有并发数目录
        concurrency_dirs = glob.glob(os.path.join(benchmark_dir, "c*"))
        
        for concurrency_dir in concurrency_dirs:
            concurrency = int(os.path.basename(concurrency_dir)[1:])  # 移除'c'前缀
            
            # 查找JSON结果文件（支持嵌套路径）
            json_files = glob.glob(os.path.join(concurrency_dir, "**", "profile_export_genai_perf.json"), recursive=True)
            
            if json_files:
                json_file = json_files[0]
                try:
                    with open(json_file, 'r') as f:
                        result_data = json.load(f)
                    
                    # 提取关键指标
                    metrics = {
                        'request_throughput': result_data.get('request_throughput', {}).get('avg', 0),
                        'output_token_throughput': result_data.get('output_token_throughput', {}).get('avg', 0),
                        'output_token_throughput_per_user': result_data.get('output_token_throughput_per_user', {}).get('avg', 0),
                        'request_latency': result_data.get('request_latency', {}).get('avg', 0),
                        'time_to_first_token': result_data.get('time_to_first_token', {}).get('avg', 0),
                        'inter_token_latency': result_data.get('inter_token_latency', {}).get('avg', 0),
                        'time_to_second_token': result_data.get('time_to_second_token', {}).get('avg', 0)
                    }
                    
                    data[deployment_name][concurrency] = metrics
                    
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Warning: Failed to parse {json_file}: {e}")
                    continue
    
    return data

def plot_metric(data, metric_name, metric_display_name, ylabel, output_dir):
    """绘制单个指标的图表"""
    plt.figure(figsize=(12, 8))
    
    # 定义高对比度颜色和线型
    colors = ['#FF0000', '#0000FF', '#00AA00', '#FF8000', '#8000FF', 
              '#FF0080', '#00AAAA', '#AA0000', '#0000AA', '#AA8000']
    linestyles = ['-', '--', '-.', ':', '-', '--', '-.', ':', '-', '--']
    
    color_idx = 0
    
    for deployment_name, concurrency_data in data.items():
        if not concurrency_data:
            continue
            
        # 提取并发数和对应的指标值
        concurrencies = []
        values = []
        
        for concurrency in sorted(concurrency_data.keys()):
            if metric_name in concurrency_data[concurrency]:
                value = concurrency_data[concurrency][metric_name]
                if value > 0:  # 只绘制有效数据
                    concurrencies.append(concurrency)
                    values.append(value)
        
        if concurrencies and values:
            # 在标签中添加序号
            label_with_number = f"{color_idx + 1}. {deployment_name}"
            plt.plot(concurrencies, values, 
                    color=colors[color_idx % len(colors)],
                    linestyle=linestyles[color_idx % len(linestyles)],
                    marker='o', markersize=6, linewidth=3,
                    label=label_with_number, alpha=0.9)
            
            # 在曲线上标注序号
            if len(concurrencies) > 0:
                # 选择中间位置标注序号
                mid_idx = len(concurrencies) // 2
                plt.annotate(f'{color_idx + 1}', 
                           xy=(concurrencies[mid_idx], values[mid_idx]),
                           xytext=(0, 0), textcoords='offset points',
                           bbox=dict(boxstyle='circle,pad=0.3', 
                                   facecolor='white', 
                                   edgecolor=colors[color_idx % len(colors)],
                                   linewidth=2),
                           fontsize=12, color=colors[color_idx % len(colors)], 
                           weight='bold', ha='center', va='center')
            
            color_idx += 1
    
    plt.xlabel('Concurrency', fontsize=12)
    plt.ylabel(ylabel, fontsize=12)
    plt.title(f'{metric_display_name} vs Concurrency', fontsize=14, fontweight='bold')
    plt.grid(True, alpha=0.3)
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    
    # 设置x轴为对数刻度（如果并发数范围很大）
    if max([max(concurrency_data.keys()) for concurrency_data in data.values() if concurrency_data]) > 100:
        plt.xscale('log')
    
    # 智能调整y轴范围，去除极值并最大化曲线分离
    all_values = []
    for concurrency_data in data.values():
        for concurrency, metrics in concurrency_data.items():
            if metric_name in metrics and metrics[metric_name] > 0:
                all_values.append(metrics[metric_name])
    
    if all_values and len(all_values) > 4:
        # 排序并去除极值（去除最高和最低的5%）
        sorted_values = sorted(all_values)
        n = len(sorted_values)
        remove_count = max(1, int(n * 0.05))  # 至少去除1个极值
        
        # 去除极值
        trimmed_values = sorted_values[remove_count:-remove_count] if remove_count > 0 else sorted_values
        
        if trimmed_values:
            y_min = min(trimmed_values)
            y_max = max(trimmed_values)
            y_range = y_max - y_min
            
            if y_range > 0:
                # 使用很小的边距，最大化区分度
                y_margin = y_range * 0.02  # 只增加2%的边距
                plt.ylim(y_min - y_margin, y_max + y_margin)
                
                # 设置不等间距的y轴刻度
                import numpy as np
                # 创建更密集的刻度，特别是在数据密集的区域
                y_ticks = np.linspace(y_min - y_margin, y_max + y_margin, 15)
                plt.yticks(y_ticks)
            else:
                # 对于没有差异的数据，使用固定的小范围
                center = y_min
                plt.ylim(center * 0.98, center * 1.02)
    elif all_values:
        # 数据点太少，使用原始逻辑
        y_min = min(all_values)
        y_max = max(all_values)
        y_range = y_max - y_min
        if y_range > 0:
            y_margin = y_range * 0.05
            plt.ylim(y_min - y_margin, y_max + y_margin)
    
    plt.tight_layout()
    
    # 保存图片
    output_file = os.path.join(output_dir, f'{metric_name}.png')
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Saved plot: {output_file}")

def plot_metric_focused(data, metric_name, metric_display_name, ylabel, output_dir, focus_range=(300, 550)):
    """绘制单个指标的详细图表（聚焦特定区间）"""
    plt.figure(figsize=(14, 8))
    
    # 定义高对比度颜色和线型
    colors = ['#FF0000', '#0000FF', '#00AA00', '#FF8000', '#8000FF', 
              '#FF0080', '#00AAAA', '#AA0000', '#0000AA', '#AA8000']
    linestyles = ['-', '--', '-.', ':', '-', '--', '-.', ':', '-', '--']
    
    color_idx = 0
    
    for deployment_name, concurrency_data in data.items():
        if not concurrency_data:
            continue
            
        # 提取并发数和对应的指标值
        concurrencies = []
        values = []
        
        for concurrency in sorted(concurrency_data.keys()):
            if metric_name in concurrency_data[concurrency]:
                value = concurrency_data[concurrency][metric_name]
                if value > 0:  # 只绘制有效数据
                    concurrencies.append(concurrency)
                    values.append(value)
        
        if concurrencies and values:
            # 在标签中添加序号
            label_with_number = f"{color_idx + 1}. {deployment_name}"
            plt.plot(concurrencies, values, 
                    color=colors[color_idx % len(colors)],
                    linestyle=linestyles[color_idx % len(linestyles)],
                    marker='o', markersize=6, linewidth=3,
                    label=label_with_number, alpha=0.9)
            
            # 在曲线上标注序号
            if len(concurrencies) > 0:
                # 选择中间位置标注序号
                mid_idx = len(concurrencies) // 2
                plt.annotate(f'{color_idx + 1}', 
                           xy=(concurrencies[mid_idx], values[mid_idx]),
                           xytext=(0, 0), textcoords='offset points',
                           bbox=dict(boxstyle='circle,pad=0.3', 
                                   facecolor='white', 
                                   edgecolor=colors[color_idx % len(colors)],
                                   linewidth=2),
                           fontsize=12, color=colors[color_idx % len(colors)], 
                           weight='bold', ha='center', va='center')
            
            color_idx += 1
    
    plt.xlabel('Concurrency', fontsize=14)
    plt.ylabel(ylabel, fontsize=14)
    plt.title(f'{metric_display_name} vs Concurrency (Focus: {focus_range[0]}-{focus_range[1]})', 
              fontsize=16, fontweight='bold')
    plt.grid(True, alpha=0.3)
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=12)
    
    # 设置x轴范围，聚焦到指定区间
    plt.xlim(focus_range[0], focus_range[1])
    
    # 设置x轴刻度，每10个单位一个刻度
    plt.xticks(range(focus_range[0], focus_range[1] + 1, 10), rotation=45)
    
    # 添加垂直网格线，每10个单位一条
    plt.gca().set_xticks(range(focus_range[0], focus_range[1] + 1, 10), minor=True)
    plt.grid(True, which='minor', alpha=0.2)
    
    # 智能调整y轴范围，去除极值并最大化曲线分离
    all_values = []
    for concurrency_data in data.values():
        for concurrency, metrics in concurrency_data.items():
            if metric_name in metrics and metrics[metric_name] > 0:
                all_values.append(metrics[metric_name])
    
    if all_values and len(all_values) > 4:
        # 排序并去除极值（去除最高和最低的5%）
        sorted_values = sorted(all_values)
        n = len(sorted_values)
        remove_count = max(1, int(n * 0.05))  # 至少去除1个极值
        
        # 去除极值
        trimmed_values = sorted_values[remove_count:-remove_count] if remove_count > 0 else sorted_values
        
        if trimmed_values:
            y_min = min(trimmed_values)
            y_max = max(trimmed_values)
            y_range = y_max - y_min
            
            if y_range > 0:
                # 使用很小的边距，最大化区分度
                y_margin = y_range * 0.02  # 只增加2%的边距
                plt.ylim(y_min - y_margin, y_max + y_margin)
                
                # 设置不等间距的y轴刻度
                import numpy as np
                # 创建更密集的刻度，特别是在数据密集的区域
                y_ticks = np.linspace(y_min - y_margin, y_max + y_margin, 15)
                plt.yticks(y_ticks)
            else:
                # 对于没有差异的数据，使用固定的小范围
                center = y_min
                plt.ylim(center * 0.98, center * 1.02)
    elif all_values:
        # 数据点太少，使用原始逻辑
        y_min = min(all_values)
        y_max = max(all_values)
        y_range = y_max - y_min
        if y_range > 0:
            y_margin = y_range * 0.05
            plt.ylim(y_min - y_margin, y_max + y_margin)
    
    plt.tight_layout()
    
    # 保存图片
    output_file = os.path.join(output_dir, f'{metric_name}_focused_300_550.png')
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Saved focused plot: {output_file}")

def main():
    # 设置路径
    results_dir = "/home/bedicloud/dynamo-main/benchmarks/results"
    output_dir = "/home/bedicloud/dynamo-main/benchmarks/results/plot"
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 加载数据
    print("Loading benchmark data...")
    data = load_benchmark_data(results_dir)
    
    if not data:
        print("No benchmark data found!")
        return
    
    print(f"Found data for deployments: {list(data.keys())}")
    
    # 定义要绘制的指标
    metrics = {
        'request_throughput': ('Request Throughput', 'Requests/sec'),
        'output_token_throughput': ('Output Token Throughput', 'Tokens/sec'),
        'output_token_throughput_per_user': ('Per-User Token Throughput', 'Tokens/sec/user'),
        'request_latency': ('Request Latency', 'Latency (ms)'),
        'time_to_first_token': ('Time to First Token (TTFT)', 'TTFT (ms)'),
        'inter_token_latency': ('Inter-Token Latency (ITL)', 'ITL (ms)'),
        'time_to_second_token': ('Time per Output Token (TPOT)', 'TPOT (ms)')
    }
    
    # 绘制每个指标的图表
    for metric_name, (display_name, ylabel) in metrics.items():
        print(f"Plotting {display_name}...")
        plot_metric(data, metric_name, display_name, ylabel, output_dir)
        
        # 绘制聚焦到300-550区间的详细图表
        print(f"Plotting {display_name} (focused 300-550)...")
        plot_metric_focused(data, metric_name, display_name, ylabel, output_dir)
    
    print(f"\nAll plots saved to: {output_dir}")
    
    # 打印数据统计
    print("\nData summary:")
    for deployment_name, concurrency_data in data.items():
        if concurrency_data:
            concurrencies = sorted(concurrency_data.keys())
            print(f"  {deployment_name}: {len(concurrencies)} concurrency levels ({min(concurrencies)}-{max(concurrencies)})")

if __name__ == "__main__":
    main()
