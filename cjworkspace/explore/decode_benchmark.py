#!/usr/bin/env python3
"""
Decode-only Benchmark (DistServe-style)

Tests TPOT (Time Per Output Token) / ITL (Inter-Token Latency) performance under different SLO constraints.
Measures:
- Request Goodput (req/s): Requests that meet TPOT SLO
- Token Throughput (tokens/s): Total output tokens generated per second
- P90 ITL (Inter-Token Latency) as proxy for TPOT
"""

import json
import os
import sys
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Add benchmarks/utils to path
sys.path.append('/home/bedicloud/dynamo-main/benchmarks/utils')

# Direct genai-perf command used instead of run_genai_perf


class DecodeBenchmark:
    """Benchmark Decode performance with SLO constraints"""
    
    def __init__(self, 
                 service_url: Optional[str] = None,
                 model_name: Optional[str] = None):
        self.service_url = service_url or os.getenv('SERVICE_URL', 'http://127.0.0.1:8003')
        self.model_name = model_name or os.getenv('DEPLOYMENT_MODEL_ID', '/shared-models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B')
        self.results_dir = Path('/home/bedicloud/dynamo-main/benchmarks/results')
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Decode-focused SLO configurations (TPOT/ITL only)
        self.slo_configs = {
            'ultra_strict': {'tpot': 8},    # 8ms per token
            'strict': {'tpot': 12},          # 12ms per token
            'moderate': {'tpot': 15},        # 15ms per token
            'loose': {'tpot': 20},           # 20ms per token
            'very_loose': {'tpot': 30},     # 30ms per token
        }
        
    def run_decode_benchmark(self, 
                            isl: int,
                            osl: int,
                            concurrency: int,
                            tpot_slo: int) -> Optional[Dict[str, Any]]:
        """
        Run a single decode benchmark with given parameters.
        Note: isl is set to minimal value to focus on decode.
        
        Returns:
            dict with metrics if successful, None if failed
        """
        print(f"Running decode test with OSL={osl}, concurrency={concurrency}, TPOT SLO<{tpot_slo}ms")
        
        # For decode-only test, set input length to minimal to focus on generation
        output_dir = Path(f"/tmp/decode_test_{concurrency}")
        
        try:
            # Direct genai-perf command for decode-only testing
            cmd = [
                "genai-perf", "profile",
                "-m", self.model_name,
                "--endpoint-type", "chat",
                "--streaming",
                "-u", self.service_url,
                "--concurrency", str(concurrency),
                "--synthetic-input-tokens-mean", "1",
                "--synthetic-input-tokens-stddev", "0",
                "--num-prefix-prompts", "1",
                "--prefix-prompt-length", str(isl),
                "--output-tokens-mean", str(osl),
                "--output-tokens-stddev", "0",
                #"--measurement-interval", "5000",
                #"--warmup-request-count", str(concurrency * 2),
                "--request-count", str(concurrency * 3),
                "--tokenizer", f"/home/bedicloud/models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B",
                "--artifact-dir", str(output_dir),
                "--", "-vv", "--max-threads=300"
            ]
            
            print(f"Running genai-perf with isl {isl}, osl {osl}, concurrency {concurrency}")
            
            # 确保输出目录存在
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 使用 Popen 和 communicate 来捕获并显示输出，就像 run_genai_perf 一样
            process = subprocess.Popen(
                cmd,
                cwd=str(output_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = process.communicate(timeout=400)
            
            if process.returncode == 0:
                print("Genai-perf profiling completed successfully")
                if stdout:
                    print(stdout)  # 这里打印 genai-perf 的表格输出！
                if stderr:
                    #print(f"stderr: {stderr}")
                    pass
            else:
                #print(f"❌ genai-perf failed with error code: {process.returncode}")
                if stderr:
                    #print(f"stderr: {stderr}")
                    pass
                return None
            
            # Parse results - use the same logic as prefill_benchmark.py
            # genai-perf creates directories with the full model path, so we need to match that exactly
            model_safe_name = self.model_name.replace('/', '_')  # Only replace slashes, keep hyphens
            result_file = Path(output_dir) / f"_{model_safe_name}-openai-chat-concurrency{concurrency}" / "profile_export_genai_perf.json"
            
            # If the expected path doesn't exist, try to find the actual directory
            if not result_file.exists():
                # Look for any directory that matches the pattern
                import glob
                pattern = str(output_dir / f"*{concurrency}*" / "profile_export_genai_perf.json")
                matching_files = glob.glob(pattern)
                
                if matching_files:
                    # Use the most recent file (genai-perf creates new ones each time)
                    result_file = Path(max(matching_files, key=lambda x: Path(x).stat().st_mtime))
                    print(f"🔍 Found result file: {result_file}")
                else:
                    # Fallback to model name only version
                    model_name_only = Path(self.model_name).name  # Extract just the model name
                    result_file = Path(output_dir) / f"{model_name_only}-openai-chat-concurrency{concurrency}" / "profile_export_genai_perf.json"
                    print(f"⚠️  Using fallback path: {result_file}")
            else:
                print(f"✅ Using primary path: {result_file}")
                
            # Debug: Check which file we're actually using
            if result_file.exists():
                with open(result_file, 'r') as f:
                    data = json.load(f)
                itl_p90 = data.get('inter_token_latency', {}).get('p90', 'Not found')
                print(f"📊 Reading ITL P90: {itl_p90}ms from {result_file}")
            
            if not result_file.exists():
                print(f"❌ Result file not found: {result_file}")
                return None
            
            with open(result_file, 'r') as f:
                data = json.load(f)
            
            # Extract metrics
            itl_stats = data.get('inter_token_latency', {})
            request_throughput_stats = data.get('request_throughput', {})
            output_token_throughput_stats = data.get('output_token_throughput_per_user', {})
            output_seq_len_stats = data.get('output_sequence_length', {})
            
            itl_p90_ms = itl_stats.get('p90', float('inf'))  # Already in milliseconds (approximates TPOT)
            
            request_throughput = request_throughput_stats.get('avg', 0)
            output_token_throughput_per_request = output_token_throughput_stats.get('avg', 0)
            avg_output_len = output_seq_len_stats.get('avg', osl)
            
            # Calculate total output token throughput
            total_output_token_throughput = request_throughput * avg_output_len
            
            # Check SLO satisfaction (ITL/TPOT only for decode)
            slo_satisfied = itl_p90_ms < tpot_slo
            goodput = request_throughput if slo_satisfied else 0
            
            status = "✅" if slo_satisfied else "❌"
            print(f"{status} Concurrency {concurrency}: P90 ITL={itl_p90_ms:.1f}ms, "
                  f"Goodput={goodput:.2f} req/s, "
                  f"Output Token Throughput={total_output_token_throughput:.2f} tokens/s")
            
            return {
                'concurrency': concurrency,
                'itl_p90_ms': itl_p90_ms,
                'request_throughput': request_throughput,
                'request_goodput': goodput,
                'output_token_throughput': total_output_token_throughput,
                'output_token_throughput_per_request': output_token_throughput_per_request,
                'avg_output_len': avg_output_len,
                'slo_satisfied': slo_satisfied,
                'tpot_slo': tpot_slo,
            }
            
        except Exception as e:
            print(f"❌ Error during benchmark: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def find_max_decode_goodput(self, 
                               isl: int,
                               osl: int,
                               tpot_slo: int,
                               start_concurrency: int = 1,
                               step: int = 10,
                               max_failures: int = 3) -> Dict[str, Any]:
        """
        Find maximum goodput for given TPOT SLO by iteratively increasing concurrency.
        
        Returns:
            dict with max goodput metrics
        """
        print(f"\n{'='*60}")
        print(f"Finding max decode goodput for TPOT < {tpot_slo}ms")
        print(f"{'='*60}\n")
        
        concurrency = start_concurrency
        consecutive_failures = 0
        max_goodput_result = {
            'request_goodput': 0,
            'output_token_throughput': 0,
            'output_token_throughput_per_request': 0,
            'concurrency': 0,
            'itl_p90_ms': 0,
            'avg_output_len': 0,
        }
        
        while consecutive_failures < max_failures:
            result = self.run_decode_benchmark(
                isl=isl,
                osl=osl,
                concurrency=concurrency,
                tpot_slo=tpot_slo
            )
            
            if result is None:
                print(f"⚠️  Test failed, skipping concurrency {concurrency}")
                consecutive_failures += 1
                concurrency += step
                continue
            
            if result['slo_satisfied']:
                # Update max goodput
                if result['request_goodput'] > max_goodput_result['request_goodput']:
                    max_goodput_result = {
                        'request_goodput': result['request_goodput'],
                        'output_token_throughput': result['output_token_throughput'],
                        'output_token_throughput_per_request': result['output_token_throughput_per_request'],
                        'concurrency': result['concurrency'],
                        'itl_p90_ms': result['itl_p90_ms'],
                        'avg_output_len': result['avg_output_len'],
                    }
                consecutive_failures = 0
            else:
                consecutive_failures += 1
            
            concurrency += step
        
        print(f"\n🎯 Max goodput for TPOT<{tpot_slo}ms:")
        print(f"   Concurrency: {max_goodput_result['concurrency']}")
        print(f"   Request Goodput: {max_goodput_result['request_goodput']:.2f} req/s")
        print(f"   Output Token Throughput: {max_goodput_result['output_token_throughput']:.2f} tokens/s")
        print(f"   Output Token Throughput/Request: {max_goodput_result['output_token_throughput_per_request']:.2f} tokens/s/req")
        print(f"   P90 ITL: {max_goodput_result['itl_p90_ms']:.2f}ms")
        
        return max_goodput_result
    
    def run_full_benchmark(self, 
                          deployment_name: str,
                          isl: int = 100,
                          osl: int = 256) -> Dict[str, Any]:
        """
        Run full decode benchmark across all SLO configurations.
        
        Args:
            deployment_name: Name of the deployment being tested
            isl: Input sequence length (minimal for decode-only)
            osl: Output sequence length (generation length)
        
        Returns:
            dict with results for each SLO configuration
        """
        print(f"\n{'='*80}")
        print(f"DECODE BENCHMARK: {deployment_name}")
        print(f"Input Length: {isl} (minimal), Output Length: {osl} (decode-focused)")
        print(f"{'='*80}\n")
        
        results = {}
        
        for slo_name, slo_config in self.slo_configs.items():
            print(f"\n{'─'*60}")
            print(f"Testing {slo_name.upper()} SLO (TPOT<{slo_config['tpot']}ms)")
            print(f"{'─'*60}")
            
            try:
                max_goodput = self.find_max_decode_goodput(
                    isl=isl,
                    osl=osl,
                    tpot_slo=slo_config['tpot']
                )
                results[slo_name] = max_goodput
                print(f"✅ Completed {slo_name} SLO test")
            except Exception as e:
                print(f"❌ Error in {slo_name} SLO test: {e}")
                import traceback
                traceback.print_exc()
                results[slo_name] = {
                    'request_goodput': 0,
                    'output_token_throughput': 0,
                    'concurrency': 0,
                    'itl_p90_ms': 0,
                    'error': str(e)
                }
        
        return results
    
    def generate_report(self, deployment_name: str, results: Dict[str, Any]) -> str:
        """Generate a formatted report of decode benchmark results"""
        report = []
        report.append("=" * 80)
        report.append(f"DECODE BENCHMARK REPORT: {deployment_name}")
        report.append("=" * 80)
        report.append(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Model: {self.model_name}")
        report.append(f"Service URL: {self.service_url}")
        report.append("")
        
        report.append("DECODE GOODPUT BY SLO:")
        report.append("-" * 100)
        report.append(f"{'SLO':<15} {'TPOT Limit':<12} {'Concurrency':<12} "
                     f"{'Goodput':<15} {'Goodput/3':<15} {'Output Tokens/s':<20}")
        report.append(f"{'Name':<15} {'(ms)':<12} {'':<12} {'(req/s)':<15} {'(req/s)':<15} {'(tokens/s)':<20}")
        report.append("-" * 100)
        
        for slo_name, result in results.items():
            slo_config = self.slo_configs[slo_name]
            if 'error' in result:
                report.append(f"{slo_name:<15} {slo_config['tpot']:<12} {'ERROR':<12} "
                            f"{'0.00':<15} {'0.00':<15} {'0.00':<20}")
            else:
                goodput_per_3 = result['request_goodput'] / 3
                report.append(f"{slo_name:<15} {slo_config['tpot']:<12} "
                            f"{result['concurrency']:<12} "
                            f"{result['request_goodput']:<15.2f} "
                            f"{goodput_per_3:<15.2f} "
                            f"{result['output_token_throughput']:<20.2f}")
        
        report.append("")
        report.append("DETAILED METRICS:")
        report.append("-" * 80)
        
        for slo_name, result in results.items():
            if 'error' not in result:
                goodput_per_3 = result['request_goodput'] / 3
                report.append(f"\n{slo_name.upper()} SLO:")
                report.append(f"  Request Goodput: {result['request_goodput']:.2f} req/s")
                report.append(f"  Request Goodput/3: {goodput_per_3:.2f} req/s")
                report.append(f"  Output Token Throughput: {result['output_token_throughput']:.2f} tokens/s")
                report.append(f"  Output Token Throughput per Request: {result['output_token_throughput_per_request']:.2f} tokens/s/req")
                report.append(f"  Optimal Concurrency: {result['concurrency']}")
                report.append(f"  P90 ITL (TPOT proxy): {result['itl_p90_ms']:.2f}ms")
                report.append(f"  Average Output Length: {result.get('avg_output_len', 0):.2f} tokens")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    def save_results(self, deployment_name: str, results: Dict[str, Any], report: str):
        """Save benchmark results and report to files"""
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # Save JSON results
        json_file = self.results_dir / f"decode_benchmark_{deployment_name}_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump({
                'deployment': deployment_name,
                'timestamp': timestamp,
                'model': self.model_name,
                'service_url': self.service_url,
                'results': results
            }, f, indent=2)
        
        # Save text report
        txt_file = self.results_dir / f"decode_benchmark_{deployment_name}_{timestamp}.txt"
        with open(txt_file, 'w') as f:
            f.write(report)
        
        print(f"\n📊 Results saved:")
        print(f"   JSON: {json_file}")
        print(f"   Report: {txt_file}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Decode-only Benchmark')
    parser.add_argument('--deployment', type=str, required=True,
                       help='Deployment name')
    parser.add_argument('--service-url', type=str,
                       default=os.getenv('SERVICE_URL', 'http://127.0.0.1:8003'),
                       help='Service URL')
    parser.add_argument('--model', type=str,
                       default=os.getenv('DEPLOYMENT_MODEL_ID', '/shared-models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B'),
                       help='Model name')
    parser.add_argument('--osl', type=int, default=256,
                       help='Output sequence length')
    
    args = parser.parse_args()
    
    tester = DecodeBenchmark(
        service_url=args.service_url,
        model_name=args.model
    )
    
    results = tester.run_full_benchmark(
        deployment_name=args.deployment,
        isl=2000,  # Minimal input for decode-focused test
        osl=args.osl
    )
    
    report = tester.generate_report(args.deployment, results)
    print(f"\n{report}")
    
    tester.save_results(args.deployment, results, report)


if __name__ == '__main__':
    main()

