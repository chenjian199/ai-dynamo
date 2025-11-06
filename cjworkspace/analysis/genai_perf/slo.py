#!/usr/bin/env python3
"""
持续性能测试脚本 - 基于distserve_benchmark
支持在特定并发条件下持续测试60秒，并比较多个部署的性能
"""

import json
import subprocess
import time
import os
import sys
import threading
import concurrent.futures
from typing import List, Dict, Tuple, Optional
import statistics
from pathlib import Path
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt

# 添加项目路径
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.append(str(project_root / "benchmarks" / "utils"))
from genai import run_genai_perf

class ContinuousBenchmark:
    """持续性能测试类"""
    
    def __init__(self, model_name: str = None):
        self.model_name = model_name or os.environ.get('DEPLOYMENT_MODEL_ID', '/shared-models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B')
        print(f"model_name: {self.model_name}")
        self.results = {}
        self.start_time = None
        
        # SLO配置
        self.slo_configs = {
            'ultra_strict': {'ttft': 4000, 'tpot': 20},
            'strict': {'ttft': 4000, 'tpot': 40},
            'moderate': {'ttft': 15000, 'tpot': 20},
            'loose': {'ttft': 15000, 'tpot': 40},
        }
        
    def run_continuous_test(self, 
                          deployment_name: str, 
                          service_url: str, 
                          concurrency: int, 
                          duration_seconds: int = 60,
                          slo_config: str = 'moderate') -> Dict:
        """
        运行持续测试
        
        Args:
            deployment_name: 部署名称
            service_url: 服务URL
            concurrency: 并发数
            duration_seconds: 测试持续时间（秒）
            slo_config: SLO配置名称
        """
        
        print(f"\n🚀 开始测试部署: {deployment_name}")
        print(f"   服务URL: {service_url}")
        print(f"   并发数: {concurrency}")
        print(f"   持续时间: {duration_seconds}秒")
        print(f"   SLO配置: {slo_config}")
        
        slo = self.slo_configs[slo_config]
        print(f"   SLO要求: TTFT<{slo['ttft']}ms, TPOT<{slo['tpot']}ms")
        
        # 创建输出目录
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = project_root / "cjworkspace" / "results" / "sglang" / f"continuous_test_{deployment_name}_{concurrency}_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 运行持续测试
        start_time = time.time()
        test_results = []
        
        try:
            # 使用genai-perf进行持续测试
            # 注意：这里需要修改genai.py以支持持续时间参数
            result = self._run_genai_perf_continuous(
                service_url=service_url,
                model_name=self.model_name,
                concurrency=concurrency,
                duration_seconds=duration_seconds,
                output_dir=output_dir
            )
            
            if result:
                # 分析结果
                analysis = self._analyze_continuous_results(result, slo, duration_seconds)
                analysis['deployment_name'] = deployment_name
                analysis['service_url'] = service_url
                analysis['concurrency'] = concurrency
                analysis['duration_seconds'] = duration_seconds
                analysis['slo_config'] = slo_config
                analysis['timestamp'] = timestamp
                
                return analysis
            else:
                print(f"❌ 测试失败: {deployment_name}")
                return None
                
        except Exception as e:
            print(f"❌ 测试异常: {deployment_name} - {str(e)}")
            return None
    
    def _run_genai_perf_continuous(self, 
                                 service_url: str, 
                                 model_name: str, 
                                 concurrency: int, 
                                 duration_seconds: int,
                                 output_dir: Path) -> Optional[Dict]:
        """运行持续时间的genai-perf测试"""
        
        # 构建命令 - 使用measurement-interval控制测试持续时间
        # 3 × measurement-interval = 60000ms (60秒)
        cmd = [
            "genai-perf",
            "profile",
            "-m", model_name,
            "--endpoint-type", "chat",
            "--streaming",
            "-u", service_url,
            "--synthetic-input-tokens-mean", "5000",
            "--synthetic-input-tokens-stddev", "0",
            "--concurrency", str(concurrency),
            "--output-tokens-mean", "512",
            "--extra-inputs", "max_tokens:512",
            "--extra-inputs", "min_tokens:512",
            "--extra-inputs", "ignore_eos:true",
            "--tokenizer", "/raid5/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
            "--artifact-dir", str(output_dir),
            #"--measurement-interval", "20000",    # 测量间隔20秒，3×20=60秒
            "--request-count", str(concurrency * 4),          # 足够大的请求数量
            "--",
            "-vv",
            "--max-threads=300",
        ]
        
        print(f"   执行命令: {' '.join(cmd)}")
        
        try:
            # 运行命令
            process = subprocess.Popen(
                cmd,
                cwd=str(output_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            
            stdout, stderr = process.communicate()  # 额外2分钟超时
            
            if process.returncode == 0:
                print(f"   ✅ genai-perf执行成功")
                
                # 读取结果文件
                json_files = list(output_dir.glob("**/profile_export_genai_perf.json"))
                if json_files:
                    with open(json_files[0], 'r') as f:
                        return json.load(f)
                else:
                    print(f"   ⚠️  未找到结果文件")
                    return None
            else:
                print(f"   ❌ genai-perf执行失败 (返回码: {process.returncode})")
                if stderr:
                    print(f"   错误信息: {stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print(f"   ⏰ 测试超时")
            process.kill()
            return None
        except Exception as e:
            print(f"   ❌ 执行异常: {str(e)}")
            return None
    
    def _analyze_continuous_results(self, result_data: Dict, slo: Dict, duration_seconds: int) -> Dict:
        """分析持续测试结果"""
        
        # 提取关键指标
        metrics = {
            'request_throughput_avg': result_data.get('request_throughput', {}).get('avg', 0),
            'request_throughput_p90': result_data.get('request_throughput', {}).get('p90', 0),
            'output_token_throughput_avg': result_data.get('output_token_throughput', {}).get('avg', 0),
            'output_token_throughput_p90': result_data.get('output_token_throughput', {}).get('p90', 0),
            'output_token_throughput_per_user_avg': result_data.get('output_token_throughput_per_user', {}).get('avg', 0),
            'output_token_throughput_per_user_p90': result_data.get('output_token_throughput_per_user', {}).get('p90', 0),
            'ttft_avg': result_data.get('time_to_first_token', {}).get('avg', 0),
            'ttft_p90': result_data.get('time_to_first_token', {}).get('p90', 0),
            'itl_avg': result_data.get('inter_token_latency', {}).get('avg', 0),
            'itl_p90': result_data.get('inter_token_latency', {}).get('p90', 0),
            'request_latency_avg': result_data.get('request_latency', {}).get('avg', 0),
            'request_latency_p90': result_data.get('request_latency', {}).get('p90', 0),
            'request_count': result_data.get('request_count', {}).get('count', 0),
        }
        
        # 计算TPOT (Time Per Output Token)
        if metrics['itl_avg'] > 0:
            metrics['tpot_avg'] = metrics['itl_avg']
            metrics['tpot_p90'] = metrics['itl_p90']
        else:
            metrics['tpot_avg'] = 0
            metrics['tpot_p90'] = 0
        
        # SLO满足率分析
        ttft_slo_met = metrics['ttft_p90'] <= slo['ttft']
        tpot_slo_met = metrics['tpot_p90'] <= slo['tpot']
        slo_met = ttft_slo_met and tpot_slo_met
        
        # 计算Goodput
        if slo_met:
            goodput = metrics['request_throughput_avg']
            token_goodput = metrics['output_token_throughput_avg']
            token_goodput_per_user = metrics['output_token_throughput_per_user_avg']
        else:
            goodput = 0
            token_goodput = 0
            token_goodput_per_user = 0
        
        # 计算效率指标
        efficiency_metrics = {
            'slo_satisfaction_rate': 1.0 if slo_met else 0.0,
            'ttft_slo_met': ttft_slo_met,
            'tpot_slo_met': tpot_slo_met,
            'goodput': goodput,
            'token_goodput': token_goodput,
            'token_goodput_per_user': token_goodput_per_user,
            'goodput_efficiency': goodput / max(metrics['request_throughput_avg'], 1),
            'requests_per_second': metrics['request_count'] / duration_seconds,
        }
        
        return {
            'metrics': metrics,
            'efficiency': efficiency_metrics,
            'slo_analysis': {
                'slo_met': slo_met,
                'ttft_slo_met': ttft_slo_met,
                'tpot_slo_met': tpot_slo_met,
                'ttft_p90': metrics['ttft_p90'],
                'tpot_p90': metrics['tpot_p90'],
                'ttft_threshold': slo['ttft'],
                'tpot_threshold': slo['tpot'],
            }
        }
    
    def run_multi_deployment_test(self, 
                                deployments: List[Dict], 
                                concurrency: int,
                                duration_seconds: int = 60,
                                slo_config: str = 'moderate',
                                parallel: bool = True) -> Dict:
        """
        运行多部署比较测试
        
        Args:
            deployments: 部署配置列表，每个元素包含 {'name': str, 'url': str}
            concurrency: 并发数
            duration_seconds: 测试持续时间
            slo_config: SLO配置
            parallel: 是否并行测试
        """
        
        print(f"\n🎯 开始多部署比较测试")
        print(f"   部署数量: {len(deployments)}")
        print(f"   并发数: {concurrency}")
        print(f"   持续时间: {duration_seconds}秒")
        print(f"   SLO配置: {slo_config}")
        print(f"   并行测试: {'是' if parallel else '否'}")
        
        results = {}
        start_time = time.time()
        
        if parallel:
            # 并行测试
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(deployments)) as executor:
                future_to_deployment = {
                    executor.submit(
                        self.run_continuous_test,
                        deployment['name'],
                        deployment['url'],
                        concurrency,
                        duration_seconds,
                        slo_config
                    ): deployment for deployment in deployments
                }
                
                for future in concurrent.futures.as_completed(future_to_deployment):
                    deployment = future_to_deployment[future]
                    try:
                        result = future.result()
                        if result:
                            results[deployment['name']] = result
                            print(f"✅ 完成测试: {deployment['name']}")
                        else:
                            print(f"❌ 测试失败: {deployment['name']}")
                    except Exception as e:
                        print(f"❌ 测试异常: {deployment['name']} - {str(e)}")
        else:
            # 串行测试
            for deployment in deployments:
                result = self.run_continuous_test(
                    deployment['name'],
                    deployment['url'],
                    concurrency,
                    duration_seconds,
                    slo_config
                )
                if result:
                    results[deployment['name']] = result
                    print(f"✅ 完成测试: {deployment['name']}")
                else:
                    print(f"❌ 测试失败: {deployment['name']}")
        
        total_time = time.time() - start_time
        print(f"\n⏱️  总测试时间: {total_time:.2f}秒")
        
        return {
            'test_config': {
                'concurrency': concurrency,
                'duration_seconds': duration_seconds,
                'slo_config': slo_config,
                'parallel': parallel,
                'total_time': total_time,
            },
            'results': results,
            'summary': self._generate_summary(results)
        }
    
    def _generate_summary(self, results: Dict) -> Dict:
        """生成测试结果摘要"""
        
        if not results:
            return {'error': 'No results to summarize'}
        
        summary = {
            'deployment_count': len(results),
            'successful_tests': len([r for r in results.values() if r is not None]),
            'slo_satisfaction': {},
            'performance_ranking': {},
            'best_performers': {}
        }
        
        # SLO满足率统计
        slo_satisfied = [name for name, result in results.items() 
                        if result and result['slo_analysis']['slo_met']]
        summary['slo_satisfaction'] = {
            'satisfied_count': len(slo_satisfied),
            'satisfied_deployments': slo_satisfied,
            'satisfaction_rate': len(slo_satisfied) / len(results)
        }
        
        # 性能排名
        goodput_ranking = sorted(
            [(name, result['efficiency']['goodput']) for name, result in results.items() if result],
            key=lambda x: x[1],
            reverse=True
        )
        summary['performance_ranking'] = {
            'by_goodput': goodput_ranking,
            'by_token_goodput': sorted(
                [(name, result['efficiency']['token_goodput']) for name, result in results.items() if result],
                key=lambda x: x[1],
                reverse=True
            )
        }
        
        # 最佳表现者
        if goodput_ranking:
            summary['best_performers'] = {
                'highest_goodput': goodput_ranking[0],
                'lowest_latency': min(
                    [(name, result['metrics']['ttft_p90']) for name, result in results.items() if result],
                    key=lambda x: x[1]
                ) if results else None
            }
        
        return summary
    
    def save_results(self, results: Dict, output_file: str = None):
        """保存测试结果"""
        
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"continuous_benchmark_results_{timestamp}.json"
        
        output_path = Path(output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 结果已保存到: {output_path}")
        return output_path
    
    def generate_report(self, results: Dict, output_file: str = None):
        """生成测试报告"""
        
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"continuous_benchmark_report_{timestamp}.txt"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("持续性能测试报告\n")
            f.write("=" * 80 + "\n\n")
            
            # 测试配置
            config = results['test_config']
            f.write("测试配置:\n")
            f.write(f"  并发数: {config['concurrency']}\n")
            f.write(f"  持续时间: {config['duration_seconds']}秒\n")
            f.write(f"  SLO配置: {config['slo_config']}\n")
            f.write(f"  并行测试: {'是' if config['parallel'] else '否'}\n")
            f.write(f"  总测试时间: {config['total_time']:.2f}秒\n\n")
            
            # 摘要信息
            summary = results['summary']
            f.write("测试摘要:\n")
            f.write(f"  部署数量: {summary['deployment_count']}\n")
            f.write(f"  成功测试: {summary['successful_tests']}\n")
            f.write(f"  SLO满足率: {summary['slo_satisfaction']['satisfaction_rate']:.2%}\n")
            f.write(f"  满足SLO的部署: {', '.join(summary['slo_satisfaction']['satisfied_deployments'])}\n\n")
            
            # 性能排名
            f.write("性能排名 (按Goodput):\n")
            for i, (name, goodput) in enumerate(summary['performance_ranking']['by_goodput'], 1):
                f.write(f"  {i}. {name}: {goodput:.2f} req/s\n")
            f.write("\n")
            
            # 详细结果
            f.write("详细结果:\n")
            f.write("-" * 80 + "\n")
            for name, result in results['results'].items():
                if result:
                    f.write(f"\n部署: {name}\n")
                    f.write(f"  服务URL: {result['service_url']}\n")
                    f.write(f"  SLO满足: {'是' if result['slo_analysis']['slo_met'] else '否'}\n")
                    f.write(f"  TTFT P90: {result['metrics']['ttft_p90']:.2f}ms\n")
                    f.write(f"  TPOT P90: {result['metrics']['tpot_p90']:.2f}ms\n")
                    f.write(f"  请求吞吐率: {result['metrics']['request_throughput_avg']:.2f} req/s\n")
                    f.write(f"  Token吞吐率: {result['metrics']['output_token_throughput_avg']:.2f} tokens/s\n")
                    f.write(f"  Goodput: {result['efficiency']['goodput']:.2f} req/s\n")
                    f.write(f"  Token Goodput: {result['efficiency']['token_goodput']:.2f} tokens/s\n")
                else:
                    f.write(f"\n部署: {name} - 测试失败\n")
        
        print(f"📊 报告已生成: {output_file}")
        return output_file


def main():
    """主函数 - 示例用法"""
    
    # 创建测试实例
    benchmark = ContinuousBenchmark()
    
    # 定义要测试的部署
    deployments = [
        {
            'name': 'sglang-agg',
            'url': 'http://127.0.0.1:8003'
        },
        {
            'name': 'sglang-disagg',
            'url': 'http://127.0.0.1:8005'
        }
    ]
    
    # 测试配置
    concurrencies = list(range(1, 31, 2))  # 从1到30，每次增加2: [1, 3, 5, 7, ..., 29]
    duration_seconds = 60  # 持续时间
    slo_config = 'moderate'  # SLO配置
    parallel = True  # 是否并行测试
    
    print("🚀 开始持续性能测试 - 并发数扫描")
    print(f"测试配置: 并发数范围={concurrencies}, 持续时间={duration_seconds}秒, SLO={slo_config}")
    print(f"部署: {[d['name'] for d in deployments]}")
    
    # 运行并发数扫描测试
    all_results = {}
    for concurrency in concurrencies:
        print(f"\n📊 测试并发数: {concurrency}")
        
        results = benchmark.run_multi_deployment_test(
            deployments=deployments,
            concurrency=concurrency,
            duration_seconds=duration_seconds,
            slo_config=slo_config,
            parallel=parallel
        )
        
        if results:
            all_results[f'concurrency_{concurrency}'] = results
            
            # 打印当前并发数的摘要
            summary = results['summary']
            if 'successful_tests' in summary:
                print(f"  ✅ 完成测试: 成功={summary['successful_tests']}/{summary['deployment_count']}")
                print(f"  📈 SLO满足率: {summary['slo_satisfaction']['satisfaction_rate']:.2%}")
            else:
                print("  ⚠️ 本轮没有成功结果（可能命令行参数错误或服务不可达）")
            
            # 显示每个部署的详细指标
            for deployment_name, result in results['results'].items():
                if result:
                    metrics = result['metrics']
                    slo_analysis = result['slo_analysis']
                    print(f"    📊 {deployment_name}:")
                    print(f"      TTFT P90: {metrics['ttft_p90']:.2f}ms (SLO: {slo_analysis['ttft_slo_met']})")
                    print(f"      ITL P90: {metrics['itl_p90']:.2f}ms (SLO: {slo_analysis['tpot_slo_met']})")
                    print(f"      Goodput: {result['efficiency']['goodput']:.2f} req/s")
                    print(f"      Token Goodput: {result['efficiency']['token_goodput']:.2f} tokens/s")
            
            if 'performance_ranking' in summary and summary['performance_ranking'].get('by_goodput'):
                best = summary['performance_ranking']['by_goodput'][0]
                print(f"  🏆 最佳性能: {best[0]} (Goodput: {best[1]:.2f} req/s)")
        else:
            print(f"  ❌ 测试失败")
    
    # 保存汇总结果
    if all_results:
        json_file = benchmark.save_results(all_results, 'concurrency_scan_results.json')
        print(f"\n💾 汇总结果已保存到: {json_file}")
        
        # 生成最终摘要
        print(f"\n📈 并发数扫描完成!")
        print(f"测试的并发数: {concurrencies}")
        print(f"成功完成的测试: {len(all_results)}/{len(concurrencies)}")
        
        # 找出最佳并发数和相关统计
        best_concurrency = None
        best_goodput = 0
        latency_stats = {}
        
        for concurrency in concurrencies:
            key = f'concurrency_{concurrency}'
            if key in all_results:
                results = all_results[key]
                if results['summary']['performance_ranking']['by_goodput']:
                    goodput = results['summary']['performance_ranking']['by_goodput'][0][1]
                    if goodput > best_goodput:
                        best_goodput = goodput
                        best_concurrency = concurrency
                
                # 收集延迟统计
                for deployment_name, result in results['results'].items():
                    if result:
                        if deployment_name not in latency_stats:
                            latency_stats[deployment_name] = {
                                'ttft_p90_values': [],
                                'itl_p90_values': [],
                                'goodput_values': []
                            }
                        latency_stats[deployment_name]['ttft_p90_values'].append(result['metrics']['ttft_p90'])
                        latency_stats[deployment_name]['itl_p90_values'].append(result['metrics']['itl_p90'])
                        latency_stats[deployment_name]['goodput_values'].append(result['efficiency']['goodput'])
        
        if best_concurrency:
            print(f"🏆 最佳并发数: {best_concurrency} (Goodput: {best_goodput:.2f} req/s)")
        
        # 显示延迟统计摘要
        print(f"\n📊 延迟统计摘要:")
        for deployment_name, stats in latency_stats.items():
            if stats['ttft_p90_values']:
                avg_ttft = sum(stats['ttft_p90_values']) / len(stats['ttft_p90_values'])
                min_ttft = min(stats['ttft_p90_values'])
                max_ttft = max(stats['ttft_p90_values'])
                
                avg_itl = sum(stats['itl_p90_values']) / len(stats['itl_p90_values'])
                min_itl = min(stats['itl_p90_values'])
                max_itl = max(stats['itl_p90_values'])
                
                avg_goodput = sum(stats['goodput_values']) / len(stats['goodput_values'])
                max_goodput = max(stats['goodput_values'])
                
                print(f"  📈 {deployment_name}:")
                print(f"    TTFT P90: 平均={avg_ttft:.2f}ms, 最小={min_ttft:.2f}ms, 最大={max_ttft:.2f}ms")
                print(f"    ITL P90: 平均={avg_itl:.2f}ms, 最小={min_itl:.2f}ms, 最大={max_itl:.2f}ms")
                print(f"    Goodput: 平均={avg_goodput:.2f} req/s, 最大={max_goodput:.2f} req/s")
    else:
        print(f"\n❌ 没有成功的测试结果")


if __name__ == "__main__":
    main()