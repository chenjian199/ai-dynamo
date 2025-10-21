#!/usr/bin/env python3
"""
Prefill-only Benchmark (DistServe-style)

Tests TTFT (Time To First Token) performance under different SLO constraints.
Measures:
- Request Goodput (req/s): Requests that meet TTFT SLO
- Token Throughput (tokens/s): Total input tokens processed per second
- P90 TTFT latency
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

try:
    from genai import run_genai_perf
except ImportError:
    print("Error: Could not import genai module from benchmarks/utils")
    sys.exit(1)


class PrefillBenchmark:
    """Benchmark Prefill performance with SLO constraints"""
    
    def __init__(self, 
                 service_url: Optional[str] = None,
                 model_name: Optional[str] = None):
        self.service_url = service_url or os.getenv('SERVICE_URL', 'http://127.0.0.1:8000')
        self.model_name = model_name or os.getenv('DEPLOYMENT_MODEL_ID', 'DeepSeek-R1-Distill-Qwen-7B')
        self.results_dir = Path('/home/bedicloud/dynamo-main/benchmarks/results')
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Prefill-focused SLO configurations (TTFT only)
        self.slo_configs = {
            'ultra_strict': {'ttft': 50},   # 50ms TTFT
            'strict': {'ttft': 100},         # 100ms TTFT
            'moderate': {'ttft': 200},       # 200ms TTFT
            'loose': {'ttft': 400},          # 400ms TTFT
            'very_loose': {'ttft': 800},     # 800ms TTFT
        }
        
    def run_prefill_benchmark(self, 
                              isl: int,
                              osl: int,
                              concurrency: int,
                              ttft_slo: int) -> Optional[Dict[str, Any]]:
        """
        Run a single prefill benchmark with given parameters.
        Note: osl is set to minimal value (1) to focus on prefill.
        
        Returns:
            dict with metrics if successful, None if failed
        """
        print(f"Running prefill test with ISL={isl}, concurrency={concurrency}, TTFT SLO<{ttft_slo}ms")
        
        # For prefill-only test, set output length to 1 to minimize decode time
        output_dir = Path(f"/tmp/prefill_test_{concurrency}")
        
        try:
            success = run_genai_perf(
                service_url=self.service_url,
                model_name=self.model_name,
                isl=isl,
                osl=10,  # Use 10 tokens to get valid metrics (osl=1 causes missing metrics)
                stddev=0,  # Fixed length for consistent prefill testing
                concurrency=concurrency,
                output_dir=output_dir
            )
            
            if not success:
                print(f"❌ genai-perf failed")
                return None
            
            # Parse results
            result_file = Path(output_dir) / f"{self.model_name}-openai-chat-concurrency{concurrency}" / "profile_export_genai_perf.json"
            
            if not result_file.exists():
                print(f"❌ Result file not found: {result_file}")
                return None
            
            with open(result_file, 'r') as f:
                data = json.load(f)
            
            # Extract metrics
            ttft_stats = data.get('time_to_first_token', {})
            request_throughput_stats = data.get('request_throughput', {})
            input_token_throughput_stats = data.get('output_token_throughput_per_user', {})
            
            ttft_p90_ms = ttft_stats.get('p90', float('inf'))  # Already in milliseconds
            
            request_throughput = request_throughput_stats.get('avg', 0)
            input_token_throughput_per_request = input_token_throughput_stats.get('avg', 0)
            
            # Calculate total input token throughput
            total_input_token_throughput = request_throughput * isl
            
            # Check SLO satisfaction (TTFT only for prefill)
            slo_satisfied = ttft_p90_ms < ttft_slo
            goodput = request_throughput if slo_satisfied else 0
            
            status = "✅" if slo_satisfied else "❌"
            print(f"{status} Concurrency {concurrency}: P90 TTFT={ttft_p90_ms:.1f}ms, "
                  f"Goodput={goodput:.2f} req/s, "
                  f"Input Token Throughput={total_input_token_throughput:.2f} tokens/s")
            
            return {
                'concurrency': concurrency,
                'ttft_p90_ms': ttft_p90_ms,
                'request_throughput': request_throughput,
                'request_goodput': goodput,
                'input_token_throughput': total_input_token_throughput,
                'input_token_throughput_per_request': input_token_throughput_per_request,
                'slo_satisfied': slo_satisfied,
                'ttft_slo': ttft_slo,
            }
            
        except Exception as e:
            print(f"❌ Error during benchmark: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def find_max_prefill_goodput(self, 
                                  isl: int,
                                  osl: int,
                                  ttft_slo: int,
                                  start_concurrency: int = 1,
                                  step: int = 10,
                                  max_failures: int = 3) -> Dict[str, Any]:
        """
        Find maximum goodput for given TTFT SLO by iteratively increasing concurrency.
        
        Returns:
            dict with max goodput metrics
        """
        print(f"\n{'='*60}")
        print(f"Finding max prefill goodput for TTFT < {ttft_slo}ms")
        print(f"{'='*60}\n")
        
        concurrency = start_concurrency
        consecutive_failures = 0
        max_goodput_result = {
            'request_goodput': 0,
            'input_token_throughput': 0,
            'input_token_throughput_per_request': 0,
            'concurrency': 0,
            'ttft_p90_ms': 0,
        }
        
        while consecutive_failures < max_failures:
            result = self.run_prefill_benchmark(
                isl=isl,
                osl=osl,
                concurrency=concurrency,
                ttft_slo=ttft_slo
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
                        'input_token_throughput': result['input_token_throughput'],
                        'input_token_throughput_per_request': result['input_token_throughput_per_request'],
                        'concurrency': result['concurrency'],
                        'ttft_p90_ms': result['ttft_p90_ms'],
                    }
                consecutive_failures = 0
            else:
                consecutive_failures += 1
            
            concurrency += step
        
        print(f"\n🎯 Max goodput for TTFT<{ttft_slo}ms:")
        print(f"   Concurrency: {max_goodput_result['concurrency']}")
        print(f"   Request Goodput: {max_goodput_result['request_goodput']:.2f} req/s")
        print(f"   Input Token Throughput: {max_goodput_result['input_token_throughput']:.2f} tokens/s")
        print(f"   Input Token Throughput/Request: {max_goodput_result['input_token_throughput_per_request']:.2f} tokens/s/req")
        print(f"   P90 TTFT: {max_goodput_result['ttft_p90_ms']:.2f}ms")
        
        return max_goodput_result
    
    def run_full_benchmark(self, 
                           deployment_name: str,
                           isl: int = 2000,
                           osl: int = 1) -> Dict[str, Any]:
        """
        Run full prefill benchmark across all SLO configurations.
        
        Args:
            deployment_name: Name of the deployment being tested
            isl: Input sequence length (prompt size)
            osl: Output sequence length (set to 1 for prefill-only)
        
        Returns:
            dict with results for each SLO configuration
        """
        print(f"\n{'='*80}")
        print(f"PREFILL BENCHMARK: {deployment_name}")
        print(f"Input Length: {isl}, Output Length: {osl} (prefill-focused)")
        print(f"{'='*80}\n")
        
        results = {}
        
        for slo_name, slo_config in self.slo_configs.items():
            print(f"\n{'─'*60}")
            print(f"Testing {slo_name.upper()} SLO (TTFT<{slo_config['ttft']}ms)")
            print(f"{'─'*60}")
            
            try:
                max_goodput = self.find_max_prefill_goodput(
                    isl=isl,
                    osl=osl,
                    ttft_slo=slo_config['ttft']
                )
                results[slo_name] = max_goodput
                print(f"✅ Completed {slo_name} SLO test")
            except Exception as e:
                print(f"❌ Error in {slo_name} SLO test: {e}")
                import traceback
                traceback.print_exc()
                results[slo_name] = {
                    'request_goodput': 0,
                    'input_token_throughput': 0,
                    'concurrency': 0,
                    'ttft_p90_ms': 0,
                    'error': str(e)
                }
        
        return results
    
    def generate_report(self, deployment_name: str, results: Dict[str, Any]) -> str:
        """Generate a formatted report of prefill benchmark results"""
        report = []
        report.append("=" * 80)
        report.append(f"PREFILL BENCHMARK REPORT: {deployment_name}")
        report.append("=" * 80)
        report.append(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Model: {self.model_name}")
        report.append(f"Service URL: {self.service_url}")
        report.append("")
        
        report.append("PREFILL GOODPUT BY SLO:")
        report.append("-" * 100)
        report.append(f"{'SLO':<15} {'TTFT Limit':<12} {'Concurrency':<12} "
                     f"{'Goodput':<15} {'Goodput/3':<15} {'Input Tokens/s':<20}")
        report.append(f"{'Name':<15} {'(ms)':<12} {'':<12} {'(req/s)':<15} {'(req/s)':<15} {'(tokens/s)':<20}")
        report.append("-" * 100)
        
        for slo_name, result in results.items():
            slo_config = self.slo_configs[slo_name]
            if 'error' in result:
                report.append(f"{slo_name:<15} {slo_config['ttft']:<12} {'ERROR':<12} "
                            f"{'0.00':<15} {'0.00':<15} {'0.00':<20}")
            else:
                goodput_per_3 = result['request_goodput'] / 3
                report.append(f"{slo_name:<15} {slo_config['ttft']:<12} "
                            f"{result['concurrency']:<12} "
                            f"{result['request_goodput']:<15.2f} "
                            f"{goodput_per_3:<15.2f} "
                            f"{result['input_token_throughput']:<20.2f}")
        
        report.append("")
        report.append("DETAILED METRICS:")
        report.append("-" * 80)
        
        for slo_name, result in results.items():
            if 'error' not in result:
                goodput_per_3 = result['request_goodput'] / 3
                report.append(f"\n{slo_name.upper()} SLO:")
                report.append(f"  Request Goodput: {result['request_goodput']:.2f} req/s")
                report.append(f"  Request Goodput/3: {goodput_per_3:.2f} req/s")
                report.append(f"  Input Token Throughput: {result['input_token_throughput']:.2f} tokens/s")
                report.append(f"  Input Token Throughput per Request: {result['input_token_throughput_per_request']:.2f} tokens/s/req")
                report.append(f"  Optimal Concurrency: {result['concurrency']}")
                report.append(f"  P90 TTFT: {result['ttft_p90_ms']:.2f}ms")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    def save_results(self, deployment_name: str, results: Dict[str, Any], report: str):
        """Save benchmark results and report to files"""
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        # Save JSON results
        json_file = self.results_dir / f"prefill_benchmark_{deployment_name}_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump({
                'deployment': deployment_name,
                'timestamp': timestamp,
                'model': self.model_name,
                'service_url': self.service_url,
                'results': results
            }, f, indent=2)
        
        # Save text report
        txt_file = self.results_dir / f"prefill_benchmark_{deployment_name}_{timestamp}.txt"
        with open(txt_file, 'w') as f:
            f.write(report)
        
        print(f"\n📊 Results saved:")
        print(f"   JSON: {json_file}")
        print(f"   Report: {txt_file}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Prefill-only Benchmark')
    parser.add_argument('--deployment', type=str, required=True,
                       help='Deployment name')
    parser.add_argument('--service-url', type=str,
                       default=os.getenv('SERVICE_URL', 'http://127.0.0.1:8001'),
                       help='Service URL')
    parser.add_argument('--model', type=str,
                       default=os.getenv('DEPLOYMENT_MODEL_ID', 'DeepSeek-R1-Distill-Qwen-7B'),
                       help='Model name')
    parser.add_argument('--isl', type=int, default=2000,
                       help='Input sequence length')
    
    args = parser.parse_args()
    
    tester = PrefillBenchmark(
        service_url=args.service_url,
        model_name=args.model
    )
    
    results = tester.run_full_benchmark(
        deployment_name=args.deployment,
        isl=args.isl,
        osl=1  # Prefill-focused
    )
    
    report = tester.generate_report(args.deployment, results)
    print(f"\n{report}")
    
    tester.save_results(args.deployment, results, report)


if __name__ == '__main__':
    main()

