#!/usr/bin/env python3
"""
从 distserve_agg.py 生成的测试结果中提取所有指标，汇总到 CSV 表格

用法:
    python extract_distserve_metrics.py [--output-dir OUTPUT_DIR] [--output-csv OUTPUT_CSV]
"""

import json
import csv
import glob
import os
import sys
import re
from pathlib import Path
from typing import Dict, List, Any
import argparse


def get_isl_osl_from_json(json_file: str) -> tuple[float, float]:
    """
    从JSON文件中读取ISL和OSL
    
    Returns:
        (isl, osl) 元组，如果读取失败则返回 (None, None)
    """
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        isl = None
        osl = None
        
        # 尝试从input_sequence_length和output_sequence_length中读取avg值
        if 'input_sequence_length' in data:
            isl_dict = data['input_sequence_length']
            if isinstance(isl_dict, dict) and 'avg' in isl_dict:
                isl = float(isl_dict['avg'])
        
        if 'output_sequence_length' in data:
            osl_dict = data['output_sequence_length']
            if isinstance(osl_dict, dict) and 'avg' in osl_dict:
                osl = float(osl_dict['avg'])
        
        return isl, osl
    except Exception as e:
        print(f"⚠️  Warning: Failed to read ISL/OSL from {json_file}: {e}")
        return None, None


def find_result_files(base_dir: str = None, mode: str = "agg", filter_isl: float = None, filter_osl: float = None, filter_deployment: str = None) -> Dict[tuple, tuple]:
    """
    查找所有并发度下的 profile_export_genai_perf.json 文件，按 (concurrency, isl, osl, deployment_name) 组合区分
    
    Args:
        base_dir: 基础目录（如果为None，则使用 cjworkspace/temp）
        mode: "agg" 或 "disagg" 模式
        filter_isl: 可选，过滤特定的ISL值
        filter_osl: 可选，过滤特定的OSL值
    
    Returns:
        Dict[(concurrency, isl, osl, deployment_name), (json_file_path, deployment_name)]
    """
    result_files = {}
    
    # 如果未指定base_dir，使用cjworkspace/temp
    if base_dir is None:
        script_dir = Path(__file__).parent
        # 从 cjworkspace/analysis/plot 往上两级到 cjworkspace
        cjworkspace_dir = script_dir.parent.parent
        base_dir = str(cjworkspace_dir / "temp")
    
    # 根据模式选择目录模式
    # 新格式: {mode}_{deployment_name}_isl{isl}_osl{osl}_concurrency{concurrency}
    # 也支持旧格式: {mode}_isl{isl}_osl{osl}_concurrency{concurrency}（向后兼容）
    if mode == "disagg":
        pattern = os.path.join(base_dir, "disagg*_isl*_osl*_concurrency*")
    else:
        pattern = os.path.join(base_dir, "agg*_isl*_osl*_concurrency*")
    
    test_dirs = glob.glob(pattern)
    
    for test_dir in test_dirs:
        # 从目录名提取信息
        dir_name = os.path.basename(test_dir)
        
        # 尝试匹配新格式: {mode}_{deployment_name}_isl{isl}_osl{osl}_concurrency{concurrency}
        # 使用非贪婪匹配来捕获可能包含下划线的部署名称
        match = re.match(rf'{mode}_(.+?)_isl(\d+(?:\.\d+)?)_osl(\d+(?:\.\d+)?)_concurrency(\d+)', dir_name)
        deployment_name = None
        if match:
            deployment_name = match.group(1)
            isl = float(match.group(2))
            osl = float(match.group(3))
            concurrency = int(match.group(4))
        else:
            # 尝试匹配旧格式: {mode}_isl{isl}_osl{osl}_concurrency{concurrency}（向后兼容）
            match = re.match(rf'{mode}_isl(\d+(?:\.\d+)?)_osl(\d+(?:\.\d+)?)_concurrency(\d+)', dir_name)
            if match:
                deployment_name = mode  # 使用默认值
                isl = float(match.group(1))
                osl = float(match.group(2))
                concurrency = int(match.group(3))
            else:
                # 如果无法解析，尝试从JSON文件读取
                json_pattern = os.path.join(test_dir, "**", "profile_export_genai_perf.json")
                json_files = glob.glob(json_pattern, recursive=True)
                if json_files:
                    json_file = json_files[0]
                    isl, osl = get_isl_osl_from_json(json_file)
                    if isl is None or osl is None:
                        continue
                    # 尝试从目录名中提取并发度
                    concurrency_match = re.search(r'concurrency(\d+)', dir_name)
                    if concurrency_match:
                        concurrency = int(concurrency_match.group(1))
                        deployment_name = mode  # 使用默认值
                    else:
                        continue
                else:
                    continue
        
        # 如果指定了过滤器，检查是否符合
        if filter_isl is not None and abs(isl - filter_isl) > 0.1:
            continue
        if filter_osl is not None and abs(osl - filter_osl) > 0.1:
            continue
        if filter_deployment:
            # 支持用逗号分隔的多个部署名；大小写不敏感，精确匹配或前缀匹配
            wanted = [d.strip().lower() for d in filter_deployment.split(',') if d.strip()]
            name_lc = (deployment_name or '').lower()
            # 精确匹配或作为前缀匹配（例如 "3p1d" 匹配 "3p1d" 或 "3p1d_xxx"）
            if wanted and not any(name_lc == w or name_lc.startswith(w + '_') for w in wanted):
                continue
        
        # 查找 JSON 文件
        json_pattern = os.path.join(test_dir, "**", "profile_export_genai_perf.json")
        json_files = glob.glob(json_pattern, recursive=True)
        
        if not json_files:
            continue
        
        # 使用最新的JSON文件
        json_file = max(json_files, key=lambda x: os.path.getmtime(x))
        
        # 验证JSON文件中的ISL/OSL是否与目录名匹配
        json_isl, json_osl = get_isl_osl_from_json(json_file)
        if json_isl is not None and json_osl is not None:
            # 如果JSON中的值与目录名不匹配，使用JSON中的值
            if abs(json_isl - isl) > 0.1 or abs(json_osl - osl) > 0.1:
                isl = json_isl
                osl = json_osl
        
        # 使用 (concurrency, isl, osl, deployment_name) 作为键
        key = (concurrency, isl, osl, deployment_name)
        
        # 如果同一个组合有多个文件，使用最新的
        if key in result_files:
            existing_file = result_files[key][0]
            existing_mtime = os.path.getmtime(existing_file)
            current_mtime = os.path.getmtime(json_file)
            if current_mtime > existing_mtime:
                result_files[key] = (json_file, deployment_name)
                print(f"✅ Updated concurrency {concurrency} ISL={isl:.0f} OSL={osl:.0f} deployment={deployment_name}: {json_file}")
        else:
            result_files[key] = (json_file, deployment_name)
            print(f"✅ Found concurrency {concurrency} ISL={isl:.0f} OSL={osl:.0f} deployment={deployment_name}: {json_file}")
    
    return result_files


def extract_all_metrics(json_file: str) -> Dict[str, Any]:
    """
    从 JSON 文件中提取所有可用的指标
    
    Returns:
        包含所有指标和统计值的字典
    """
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    metrics = {}
    
    # 统计值类型（按常见顺序）
    stat_types = ['avg', 'min', 'max', 'median', 'p50', 'p90', 'p95', 'p99', 'std', 'count']
    
    def extract_metric_dict(prefix: str, metric_dict: Dict[str, Any]):
        """从字典中提取指标，字典通常包含统计值如 avg, p90 等"""
        # 提取所有统计值
        for stat in stat_types:
            if stat in metric_dict:
                stat_key = f"{prefix}_{stat}" if prefix else stat
                metrics[stat_key] = metric_dict[stat]
        
        # 如果存在原始数据数组，记录数据点数量
        if 'data' in metric_dict and isinstance(metric_dict['data'], list):
            data_list = metric_dict['data']
            if data_list:
                metrics[f"{prefix}_data_count"] = len(data_list)
    
    # 处理顶级字段
    for key, value in data.items():
        if isinstance(value, dict):
            # 检查是否是包含统计值的字典（如 time_to_first_token, inter_token_latency）
            if any(stat in value for stat in stat_types):
                extract_metric_dict(key, value)
            else:
                # 可能是嵌套结构，递归处理
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, dict) and any(stat in sub_value for stat in stat_types):
                        extract_metric_dict(f"{key}_{sub_key}", sub_value)
                    elif isinstance(sub_value, (int, float, str)):
                        metrics[f"{key}_{sub_key}"] = sub_value
        elif isinstance(value, (int, float, str)):
            metrics[key] = value
        elif isinstance(value, list):
            metrics[f"{key}_count"] = len(value)
    
    return metrics


def collect_all_metrics(result_files: Dict[tuple, tuple]) -> List[Dict[str, Any]]:
    """
    收集所有并发度的指标数据（支持按ISL/OSL/部署名称区分）
    
    Args:
        result_files: Dict[(concurrency, isl, osl, deployment_name), (json_file_path, deployment_name)]
    
    Returns:
        包含所有指标的字典列表
    """
    all_results = []
    
    # 按 (concurrency, isl, osl, deployment_name) 排序
    for key in sorted(result_files.keys()):
        concurrency, isl, osl, deployment_name = key
        json_file, deployment_name_from_dict = result_files[key]
        
        try:
            metrics = extract_all_metrics(json_file)
            metrics['concurrency'] = concurrency
            metrics['deployment_name'] = deployment_name_from_dict or deployment_name or 'unknown'
            # 确保ISL和OSL被包含（如果extract_all_metrics没有提取到）
            if 'input_sequence_length_avg' not in metrics or metrics['input_sequence_length_avg'] == 0:
                metrics['input_sequence_length_avg'] = isl
            if 'output_sequence_length_avg' not in metrics or metrics['output_sequence_length_avg'] == 0:
                metrics['output_sequence_length_avg'] = osl
            all_results.append(metrics)
            print(f"✅ Extracted metrics for concurrency {concurrency} ISL={isl:.0f} OSL={osl:.0f} deployment={metrics['deployment_name']}")
        except Exception as e:
            print(f"❌ Error extracting metrics for concurrency {concurrency} ISL={isl:.0f} OSL={osl:.0f}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    return all_results


def get_all_columns(all_results: List[Dict[str, Any]]) -> List[str]:
    """
    获取所有可能的列名（按固定顺序）
    """
    # 定义列的顺序：先 concurrency, deployment_name, ISL, OSL，然后是各种指标的统计值
    column_order = ['concurrency', 'deployment_name', 'input_sequence_length_avg', 'output_sequence_length_avg']
    
    # 定义指标的优先级顺序
    metric_order = [
        'time_to_first_token',
        'inter_token_latency',
        'request_latency',
        'prefill_latency',
        'decode_latency',
        'request_throughput',
        'output_token_throughput',
        'output_token_throughput_per_user',
        'input_token_count',
        'output_token_count',
        'total_token_count',
    ]
    
    # 统计值的顺序
    stat_order = ['avg', 'min', 'max', 'median', 'p50', 'p90', 'p95', 'p99', 'std', 'count']
    
    # 构建列名
    for metric in metric_order:
        for stat in stat_order:
            column_order.append(f"{metric}_{stat}")
    
    # 添加其他可能存在的列
    all_keys = set()
    for result in all_results:
        all_keys.update(result.keys())
    
    # 添加未在预设顺序中的列
    other_columns = sorted([k for k in all_keys if k not in column_order])
    
    # 确保所有列都被包含，但保持预设顺序
    final_columns = column_order + other_columns
    
    # 只返回实际存在的列
    existing_columns = [col for col in final_columns if any(col in result for result in all_results)]
    
    return existing_columns


def write_csv(results: List[Dict[str, Any]], output_file: str):
    """
    将结果写入 CSV 文件
    """
    if not results:
        print("❌ No results to write")
        return
    
    columns = get_all_columns(results)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        
        for result in results:
            row = {col: result.get(col, '') for col in columns}
            writer.writerow(row)
    
    print(f"✅ CSV file written: {output_file}")
    print(f"   Total rows: {len(results)}")
    print(f"   Total columns: {len(columns)}")


def main():
    parser = argparse.ArgumentParser(
        description='Extract all metrics from distserve_agg.py test results to CSV'
    )
    parser.add_argument(
        '--base-dir',
        type=str,
        default=None,
        help='Base directory to search for test results (default: cjworkspace/temp relative to project root)'
    )
    parser.add_argument(
        '--output-csv',
        type=str,
        default=None,
        help='Output CSV file path (default: distserve_metrics_TIMESTAMP.csv)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Output directory for CSV file (default: current directory)'
    )
    parser.add_argument(
        '--mode',
        type=str,
        choices=['agg', 'disagg'],
        default='agg',
        help='Test mode: agg (aggregated) or disagg (disaggregated) (default: agg)'
    )
    parser.add_argument(
        '--filter-isl',
        type=float,
        default=None,
        help='Filter by specific input sequence length (ISL). If not specified, includes all ISL values.'
    )
    parser.add_argument(
        '--filter-osl',
        type=float,
        default=None,
        help='Filter by specific output sequence length (OSL). If not specified, includes all OSL values.'
    )
    parser.add_argument(
        '--filter-deployment',
        type=str,
        default=None,
        help='Filter by deployment name (supports comma-separated values, case-insensitive, substring match).'
    )
    
    args = parser.parse_args()
    
    print("🔍 Searching for test result files...")
    print(f"   Base directory: {args.base_dir}")
    print(f"   Mode: {args.mode}")
    if args.filter_isl is not None:
        print(f"   Filter ISL: {args.filter_isl}")
    if args.filter_osl is not None:
        print(f"   Filter OSL: {args.filter_osl}")
    if args.filter_deployment:
        print(f"   Filter deployment: {args.filter_deployment}")
    
    # 查找所有结果文件（按 (concurrency, isl, osl) 组合区分）
    result_files = find_result_files(args.base_dir, args.mode, args.filter_isl, args.filter_osl, args.filter_deployment)
    
    if not result_files:
        print("❌ No result files found!")
        if args.base_dir:
            search_dir = args.base_dir
        else:
            script_dir = Path(__file__).parent
            # 从 cjworkspace/analysis/plot 往上两级到 cjworkspace
            cjworkspace_dir = script_dir.parent.parent
            search_dir = str(cjworkspace_dir / "temp")
        
        if args.mode == "disagg":
            print(f"   Searched in: {search_dir}/disagg_isl*_osl*_concurrency*")
        else:
            print(f"   Searched in: {search_dir}/agg_isl*_osl*_concurrency*")
        sys.exit(1)
    
    # 统计信息
    unique_concurrencies = set()
    isl_osl_combinations = set()
    deployment_names = set()
    for key in result_files.keys():
        concurrency, isl, osl, deployment_name = key
        unique_concurrencies.add(concurrency)
        isl_osl_combinations.add((isl, osl))
        deployment_names.add(deployment_name)
    
    print(f"\n✅ Found {len(result_files)} test results")
    print(f"   Unique concurrency levels: {sorted(unique_concurrencies)}")
    print(f"   ISL/OSL combinations: {sorted(isl_osl_combinations)}")
    print(f"   Deployment names: {sorted(deployment_names)}")
    if len(isl_osl_combinations) > 1:
        print(f"   ⚠️  Note: Multiple ISL/OSL combinations found. All will be included in the CSV.")
    if len(deployment_names) > 1:
        print(f"   ⚠️  Note: Multiple deployment names found. All will be included in the CSV.")
    
    # 收集所有指标
    print("\n📊 Extracting metrics...")
    all_results = collect_all_metrics(result_files)
    
    if not all_results:
        print("❌ No metrics extracted!")
        sys.exit(1)
    
    # 生成输出文件名
    if args.output_csv:
        output_file = args.output_csv
    else:
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"distserve_metrics_{args.mode}_{timestamp}.csv"
    
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        output_file = os.path.join(args.output_dir, os.path.basename(output_file))
    
    # 写入 CSV
    print(f"\n💾 Writing CSV file...")
    write_csv(all_results, output_file)
    
    print(f"\n✅ Done! Results saved to: {output_file}")
    
    # 显示一些统计信息
    if all_results:
        print(f"\n📈 Summary:")
        print(f"   Total data points: {len(all_results)}")
        
        # 统计唯一的并发度数量和ISL/OSL组合
        unique_concurrencies = set(r['concurrency'] for r in all_results)
        unique_isl_osl = set((r.get('input_sequence_length_avg', 0), r.get('output_sequence_length_avg', 0)) for r in all_results)
        
        print(f"   Unique concurrency levels: {len(unique_concurrencies)}")
        print(f"   Concurrency range: {min(unique_concurrencies)} - {max(unique_concurrencies)}")
        print(f"   ISL/OSL combinations: {len(unique_isl_osl)}")
        for isl, osl in sorted(unique_isl_osl):
            count = sum(1 for r in all_results if abs(r.get('input_sequence_length_avg', 0) - isl) < 0.1 and 
                       abs(r.get('output_sequence_length_avg', 0) - osl) < 0.1)
            print(f"      ISL={isl:.0f} OSL={osl:.0f}: {count} data points")
        
        # 显示可用指标的示例
        sample = all_results[0]
        key_metrics = [k for k in sample.keys() if k not in ['concurrency', 'input_sequence_length_avg', 'output_sequence_length_avg']]
        print(f"   Available metrics: {len(key_metrics)}")
        print(f"   Sample metrics: {', '.join(sorted(key_metrics)[:10])}...")


if __name__ == '__main__':
    main()

