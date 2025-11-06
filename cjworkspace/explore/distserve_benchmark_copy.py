#!/usr/bin/env python3
"""
基于DistServe论文理论的PD分离性能测试
实现SLO约束下的Goodput测试
"""

import json
import subprocess
import time
import os
import sys
from typing import List, Dict, Tuple
import statistics
from pathlib import Path

# 添加项目路径
sys.path.append('/home/bedicloud/dynamo-main/benchmarks/utils')
from genai import run_genai_perf

class DistServeStyleTest:
    """基于DistServe理论的性能测试"""
    
    def __init__(self, service_url: str = None, model_name: str = None):
        self.results = {}
        
        # 服务URL和模型名称配置（可通过环境变量覆盖）
        self.service_url = service_url or os.environ.get('SERVICE_URL', 'http://127.0.0.1:8004')
        self.model_name = model_name or os.environ.get('DEPLOYMENT_MODEL_ID', 'DeepSeek-R1-Distill-Qwen-7B')
        
        self.slo_configs = {
            # 基于实际数据分析的SLO配置
            'ultra_strict': {'ttft': 50, 'tpot': 8},      # 超严格SLO (P50水平)
            'strict': {'ttft': 100, 'tpot': 12},          # 严格SLO (P75水平)
            'moderate': {'ttft': 200, 'tpot': 15},        # 中等SLO (P90水平)
            'loose': {'ttft': 400, 'tpot': 20},           # 宽松SLO (P95水平)
            'very_loose': {'ttft': 800, 'tpot': 30},      # 很宽松SLO (P99水平)
            #
        }
        
    def run_benchmark_with_slo(self, concurrency: int, slo_config: str) -> Dict:
        """运行带SLO约束的基准测试"""
        
        slo = self.slo_configs[slo_config]
        print(f"Testing concurrency {concurrency} with {slo_config} SLO (TTFT<{slo['ttft']}ms, TPOT<{slo['tpot']}ms)")
        
        # 运行genai-perf测试
        result = run_genai_perf(
            service_url=self.service_url,
            model_name=self.model_name,
            isl=2000,
            osl=2000,
            stddev=0,
            concurrency=concurrency,
            output_dir=Path(f"/tmp/distserve_test_{concurrency}")
        )
        
        if not result:
            return None
            
        # 从输出目录读取结果
        output_dir = Path(f"/tmp/distserve_test_{concurrency}")
        json_files = list(output_dir.glob("**/profile_export_genai_perf.json"))
        
        if not json_files:
            print(f"Warning: No results found in {output_dir}")
            return None
            
        # 读取第一个结果文件
        with open(json_files[0], 'r') as f:
            result_data = json.load(f)
            
        # 分析SLO满足率
        slo_analysis = self.analyze_slo_satisfaction(result_data, slo)
        
        # 计算良请求吞吐率（Goodput）
        total_throughput = result_data.get('request_throughput', {}).get('avg', 0)
        output_token_throughput = result_data.get('output_token_throughput', {}).get('avg', 0)
        output_token_throughput_per_user = result_data.get('output_token_throughput_per_user', {}).get('avg', 0)
        
        # 如果P90满足SLO，则Goodput就是总吞吐率（90%的请求满足SLO）
        # 如果P90不满足SLO，则Goodput为0
        if slo_analysis['slo_met']:
            goodput = total_throughput  # P90满足SLO，90%请求都是良请求
            token_goodput = output_token_throughput
            token_goodput_per_user = output_token_throughput_per_user
        else:
            goodput = 0  # P90不满足SLO，无法保证90%的良请求
            token_goodput = 0
            token_goodput_per_user = 0
        
        return {
            'concurrency': concurrency,
            'slo_config': slo_config,
            'slo': slo,
            'raw_result': result_data,
            'slo_analysis': slo_analysis,
            'total_throughput': total_throughput,
            'request_throughput': goodput,  # 良请求吞吐率
            'output_token_throughput': output_token_throughput,
            'output_token_throughput_per_user': output_token_throughput_per_user,
            'token_goodput': token_goodput,  # 良token吞吐率
            'token_goodput_per_user': token_goodput_per_user  # 每用户良token吞吐率
        }
    
    def analyze_slo_satisfaction(self, result: Dict, slo: Dict) -> Dict:
        """分析SLO满足率（基于P90）"""
        
        # 从结果中提取P90延迟数据
        ttft_stats = result.get('time_to_first_token', {})
        itl_stats = result.get('inter_token_latency', {})
        
        # 提取P90值
        ttft_p90 = ttft_stats.get('p90', float('inf'))
        itl_p90 = itl_stats.get('p90', float('inf'))
        
        # 判断P90是否满足SLO
        # P90 < SLO 意味着90%的请求满足SLO
        ttft_met = ttft_p90 < slo['ttft']
        tpot_met = itl_p90 < slo['tpot']
        
        # 两个条件都必须满足
        slo_met = ttft_met and tpot_met
        
        return {
            'ttft_p90': ttft_p90,
            'itl_p90': itl_p90,
            'ttft_met': ttft_met,
            'tpot_met': tpot_met,
            'slo_met': slo_met,
            'ttft_slo': slo['ttft'],
            'tpot_slo': slo['tpot']
        }
    
    def find_max_goodput(self, slo_config: str) -> int:
        """找到满足SLO约束的最大Goodput"""
        
        print(f"\n🔍 Finding max goodput for {slo_config} SLO...")
        
        # 从低并发开始测试
        concurrency = 1
        max_goodput = 0
        max_goodput_result = {}
        consecutive_failures = 0
        
        while concurrency <= 1000 and consecutive_failures < 3:
            result = self.run_benchmark_with_slo(concurrency, slo_config)
            
            if result is None:
                consecutive_failures += 1
                concurrency += 10
                continue
                
            slo_analysis = result['slo_analysis']
            
            goodput = result.get('request_throughput', 0)
            total_throughput = result.get('total_throughput', 0)
            token_goodput = result.get('token_goodput', 0)
            token_goodput_per_user = result.get('token_goodput_per_user', 0)
            ttft_p90 = slo_analysis.get('ttft_p90', 0)
            itl_p90 = slo_analysis.get('itl_p90', 0)
            
            if slo_analysis['slo_met']:
                if goodput > max_goodput:
                    max_goodput = goodput
                    max_goodput_result = {
                        'concurrency': concurrency,
                        'request_goodput': goodput,
                        'token_goodput': token_goodput,
                        'token_goodput_per_user': token_goodput_per_user,
                        'ttft_p90': ttft_p90,
                        'itl_p90': itl_p90
                    }
                
                print(f"✅ Concurrency {concurrency}: SLO satisfied")
                print(f"   P90: TTFT={ttft_p90:.2f}ms, TPOT={itl_p90:.2f}ms")
                print(f"   Request Goodput: {goodput:.2f} req/s")
                print(f"   Token Goodput: {token_goodput:.2f} tokens/s")
                print(f"   Token Goodput/User: {token_goodput_per_user:.2f} tokens/s/user")
                concurrency += 10
                consecutive_failures = 0
            else:
                print(f"❌ Concurrency {concurrency}: SLO violated (P90: TTFT={ttft_p90:.1f}ms, TPOT={itl_p90:.1f}ms)")
                consecutive_failures += 1
                concurrency += 10
                
                # 如果连续失败，停止测试
                if consecutive_failures >= 3:
                    break
        
        print(f"🎯 Max goodput for {slo_config} SLO:")
        if max_goodput_result:
            print(f"   Concurrency: {max_goodput_result['concurrency']}")
            print(f"   Request Goodput: {max_goodput_result['request_goodput']:.2f} req/s")
            print(f"   Token Goodput: {max_goodput_result['token_goodput']:.2f} tokens/s")
            print(f"   Token Goodput/User: {max_goodput_result['token_goodput_per_user']:.2f} tokens/s/user")
        
        # 返回完整结果
        return max_goodput_result if max_goodput_result else {'request_goodput': 0, 'token_goodput': 0, 'token_goodput_per_user': 0}
    

    def analyze_latency_distribution(self, result: Dict) -> Dict:
        """分析延迟分布"""
        
        ttft_data = result.get('time_to_first_token', {}).get('data', [])
        tpot_data = result.get('inter_token_latency', {}).get('data', [])
        
        if not ttft_data or not tpot_data:
            return {}
        
        analysis = {
            'ttft': {
                'mean': statistics.mean(ttft_data),
                'median': statistics.median(ttft_data),
                'p90': sorted(ttft_data)[int(len(ttft_data) * 0.90)],
                'p95': sorted(ttft_data)[int(len(ttft_data) * 0.95)],
                'p99': sorted(ttft_data)[int(len(ttft_data) * 0.99)],
                'std': statistics.stdev(ttft_data) if len(ttft_data) > 1 else 0
            },
            'tpot': {
                'mean': statistics.mean(tpot_data),
                'median': statistics.median(tpot_data),
                'p90': sorted(tpot_data)[int(len(tpot_data) * 0.90)],
                'p95': sorted(tpot_data)[int(len(tpot_data) * 0.95)],
                'p99': sorted(tpot_data)[int(len(tpot_data) * 0.99)],
                'std': statistics.stdev(tpot_data) if len(tpot_data) > 1 else 0
            }
        }
        
        return analysis
    
    def generate_report(self, results: Dict) -> str:
        """生成测试报告"""
        
        report = []
        report.append("📊 DistServe-Style Performance Test Report")
        report.append("=" * 50)
        report.append()
        
        # SLO约束测试结果
        report.append("🎯 SLO Constraint Test Results:")
        report.append("-" * 30)
        
        for config, config_results in results.items():
            report.append(f"\n📋 {config}:")
            for slo_config, max_goodput in config_results.items():
                report.append(f"   {slo_config} SLO: {max_goodput} requests/sec")
        
        # 性能对比
        report.append("\n📈 Performance Comparison:")
        report.append("-" * 30)
        
        if len(results) >= 2:
            configs = list(results.keys())
            base_config = configs[0]
            
            for slo_config in self.slo_configs.keys():
                base_goodput = results[base_config][slo_config]
                report.append(f"\n{slo_config} SLO:")
                
                for config in configs[1:]:
                    goodput = results[config][slo_config]
                    improvement = (goodput - base_goodput) / base_goodput * 100
                    report.append(f"   {config} vs {base_config}: {improvement:+.2f}%")
        
        # 建议
        report.append("\n💡 Recommendations:")
        report.append("-" * 20)
        report.append("1. 使用prefix_data_generator生成真实测试数据")
        report.append("2. 实施动态负载测试")
        report.append("3. 优化资源配置")
        report.append("4. 监控延迟分布")
        
        return "\n".join(report)
    
    def generate_single_deployment_report(self, deployment_name: str, results: Dict) -> str:
        """生成单个部署的测试报告"""
        
        report = []
        report.append(f"📊 DistServe-Style Performance Test Report - {deployment_name}")
        report.append("=" * 60)
        report.append("")
        
        # SLO约束测试结果
        report.append("🎯 SLO Constraint Test Results:")
        report.append("-" * 30)
        
        for slo_config, result in results.items():
            slo = self.slo_configs[slo_config]
            if isinstance(result, dict):
                req_goodput = result.get('request_goodput', 0)
                token_goodput = result.get('token_goodput', 0)
                token_goodput_per_user = result.get('token_goodput_per_user', 0)
                report.append(f"{slo_config} SLO (TTFT<{slo['ttft']}ms, TPOT<{slo['tpot']}ms):")
                report.append(f"  Request Goodput: {req_goodput:.2f} req/s")
                report.append(f"  Token Goodput: {token_goodput:.2f} tokens/s")
                report.append(f"  Token Goodput/User: {token_goodput_per_user:.2f} tokens/s/user")
            else:
                report.append(f"{slo_config} SLO (TTFT<{slo['ttft']}ms, TPOT<{slo['tpot']}ms): {result} requests/sec")
        
        # 性能分析
        report.append("\n📈 Performance Analysis:")
        report.append("-" * 30)
        
        if results:
            # 找到最大Request Goodput
            best_slo = None
            max_req_goodput = 0
            for slo_config, result in results.items():
                if isinstance(result, dict):
                    req_goodput = result.get('request_goodput', 0)
                    if req_goodput > max_req_goodput:
                        max_req_goodput = req_goodput
                        best_slo = slo_config
            
            if best_slo:
                best_result = results[best_slo]
                report.append(f"Best Performance ({best_slo} SLO):")
                report.append(f"  Request Goodput: {best_result['request_goodput']:.2f} req/s")
                report.append(f"  Token Goodput: {best_result['token_goodput']:.2f} tokens/s")
                report.append(f"  Token Goodput/User: {best_result['token_goodput_per_user']:.2f} tokens/s/user")
                report.append(f"  Concurrency: {best_result['concurrency']}")
            
            # 计算SLO严格度影响
            if len(results) > 1:
                strict_result = results.get('strict', {})
                loose_result = results.get('loose', {})
                
                # 提取request_goodput值
                strict_goodput = strict_result.get('request_goodput', 0) if isinstance(strict_result, dict) else strict_result
                loose_goodput = loose_result.get('request_goodput', 0) if isinstance(loose_result, dict) else loose_result
                
                if strict_goodput > 0 and loose_goodput > 0:
                    improvement = (loose_goodput - strict_goodput) / strict_goodput * 100
                    report.append(f"SLO Relaxation Impact: {improvement:+.2f}% (strict → loose)")
        
        # 建议
        report.append("\n💡 Recommendations:")
        report.append("-" * 20)
        report.append("1. 如果Goodput较低，考虑优化资源配置")
        report.append("2. 如果SLO满足率低，考虑调整worker比例")
        report.append("3. 使用prefix_data_generator生成真实测试数据")
        report.append("4. 监控延迟分布和资源利用率")
        
        return "\n".join(report)
    
    def run_single_deployment_test(self, deployment_name: str = "vllm-agg"):
        """运行单个部署的DistServe风格测试"""
        
        print(f"🚀 Starting DistServe-style test for {deployment_name}...")
        print("=" * 60)
        
        # 测试结果存储
        results = {}
        
        # 测试所有SLO配置
        slo_configs = list(self.slo_configs.keys())
        for i, slo_config in enumerate(slo_configs):
            print(f"\n🔍 [{i+1}/{len(slo_configs)}] Testing {slo_config} SLO...")
            slo = self.slo_configs[slo_config]
            print(f"   SLO: TTFT<{slo['ttft']}ms, TPOT<{slo['tpot']}ms")
            
            try:
                max_goodput = self.find_max_goodput(slo_config)
                results[slo_config] = max_goodput
                print(f"✅ Completed {slo_config} SLO test")
            except Exception as e:
                print(f"❌ Error in {slo_config} SLO test: {e}")
                results[slo_config] = 0
        
        # 生成报告
        report = self.generate_single_deployment_report(deployment_name, results)
        
        # 保存结果到benchmarks/results目录
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        results_dir = "/home/bedicloud/dynamo-main/benchmarks/results"
        os.makedirs(results_dir, exist_ok=True)
        report_file = os.path.join(results_dir, f"distserve_benchmark_{deployment_name}_{timestamp}.txt")
        
        with open(report_file, 'w') as f:
            f.write(report)
        
        print(f"\n📄 Report saved to: {report_file}")
        print("\n" + report)
        
        return results

def main():
    """主函数"""
    
    print("📚 DistServe-Style Performance Test")
    print("Based on: DistServe: Disaggregating Prefill and Decode for Goodput-optimized LLM Serving")
    print("=" * 80)
    
    # 从环境变量获取配置
    service_url = os.environ.get('SERVICE_URL', 'http://127.0.0.1:8005')
    model_name = os.environ.get('DEPLOYMENT_MODEL_ID', 'DeepSeek-R1-Distill-Qwen-7B')
    
    print(f"Service URL: {service_url}")
    print(f"Model Name: {model_name}")
    
    # 检查服务是否可用
    try:
        import requests
        health_url = f"{service_url.rstrip('/')}/health"
        response = requests.get(health_url, timeout=5)
        if response.status_code != 200:
            print(f"❌ Service not available at {service_url}")
            print("Please ensure the service is running and port forwarding is active")
            return
    except Exception as e:
        print(f"❌ Cannot connect to service at {service_url}: {e}")
        print("Please ensure the service is running and port forwarding is active")
        return
    
    # 运行测试
    tester = DistServeStyleTest(service_url=service_url, model_name=model_name)
    
    # 从命令行参数或环境变量获取部署名称
    import sys
    if len(sys.argv) > 1:
        deployment_name = sys.argv[1]
    else:
        deployment_name = os.environ.get('DEPLOYMENT_NAME', 'vllm-agg')
    
    print(f"Testing deployment: {deployment_name}")
    results = tester.run_single_deployment_test(deployment_name)
    
    print(f"\n🎯 Test completed for {deployment_name}")
    print("Results:", results)

if __name__ == "__main__":
    main()
