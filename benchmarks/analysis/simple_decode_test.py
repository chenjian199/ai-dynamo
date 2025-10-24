#!/usr/bin/env python3
"""
Simple Decode Test - 持续测试指定并发度下的 decode 性能

在指定并发度下持续测试 60 秒，打印 genai-perf 结果
"""

import json
import os
import sys
import subprocess
import time
from pathlib import Path
from typing import List
from datetime import datetime

class SimpleDecodeTest:
    """简单的 Decode 持续测试"""
    
    def __init__(self, 
                 service_url: str = None,
                 model_name: str = None):
        self.service_url = service_url or os.getenv('SERVICE_URL', 'http://127.0.0.1:8003')
        self.model_name = model_name or os.getenv('DEPLOYMENT_MODEL_ID', '/shared-models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B')
        
        # 创建结果目录
        self.results_dir = Path('/home/bedicloud/dynamo-main/benchmarks/results')
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成时间戳
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
    def run_decode_test(self, 
                       concurrency: int,
                       isl: int = 2000,      # 最小输入长度
                       osl: int = 2000,     # 输出长度
                       duration: int = 60): # 测试持续时间(秒)
        """
        运行指定并发度的 decode 测试
        
        Args:
            concurrency: 并发度
            isl: 输入序列长度 (最小化以专注 decode)
            osl: 输出序列长度
            duration: 测试持续时间(秒)
        """
        print(f"\n{'='*60}")
        print(f"DECODE TEST: Concurrency={concurrency}, Duration={duration}s")
        print(f"Input Length: {isl}, Output Length: {osl}")
        print(f"{'='*60}")
        
        # 创建输出目录
        output_dir = Path(f"/tmp/simple_decode_test_{concurrency}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 构建 genai-perf 命令
        cmd = [
            "genai-perf", "profile",
            "-m", self.model_name,
            "--endpoint-type", "chat",
            "--streaming",
            "-u", self.service_url,
            "--concurrency", str(concurrency),
            "--synthetic-input-tokens-mean", "20000",
            "--synthetic-input-tokens-stddev", "0",
            "--num-prefix-prompts", "1",
            "--prefix-prompt-length", "0",
            "--output-tokens-mean", "10000",
            "--output-tokens-stddev", "0",
            #"--request-count", str(concurrency * 10),  # 足够的请求数
            "--measurement-interval", "20000",
            "--tokenizer", f"/home/bedicloud/models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B",
            "--artifact-dir", str(output_dir),
            "--", "-vv", "--max-threads=300"
        ]
        
        print(f"Running genai-perf with concurrency {concurrency}...")
        print(f"Command: {' '.join(cmd)}")
        print(f"Output directory: {output_dir}")
        
        try:
            # 使用 Popen 和 communicate 来捕获并显示输出
            process = subprocess.Popen(
                cmd,
                cwd=str(output_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            
            # 获取输出
            stdout, stderr = process.communicate(timeout=400)
            
            if process.returncode == 0:
                print("✅ Genai-perf completed successfully")
                if stdout:
                    print("\n" + "="*60)
                    print("GENAI-PERF RESULTS:")
                    print("="*60)
                    print(stdout)
                    print("="*60)
                    
                    # 保存结果到文件
                    self.save_results(concurrency, stdout)
                if stderr:
                    #print(f"\nstderr: {stderr}")
                    pass
            else:
                print(f"❌ Genai-perf failed with return code: {process.returncode}")
                if stderr:
                    print(f"stderr: {stderr}")
                if stdout:
                    print(f"stdout: {stdout}")
                    
        except Exception as e:
            print(f"❌ Error during test: {e}")
            import traceback
            traceback.print_exc()
    
    def save_results(self, concurrency: int, stdout: str,  success: bool = True):
        """保存测试结果到文件"""
        # 创建结果文件
        result_file = self.results_dir / f"decode_{self.timestamp}.txt"
        
        # 准备结果内容
        content = []
        content.append("=" * 80)
        content.append(f"DECODE TEST RESULTS - Concurrency: {concurrency}")
        content.append(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content.append(f"Model: {self.model_name}")
        content.append(f"Service URL: {self.service_url}")
        content.append(f"Status: {'SUCCESS' if success else 'FAILED'}")
        content.append("=" * 80)
        content.append("")
        
        if stdout:
            content.append("GENAI-PERF OUTPUT:")
            content.append("-" * 40)
            content.append(stdout)
            content.append("-" * 40)
            content.append("")
        
        
        content.append("=" * 80)
        content.append("")
        
        # 写入文件 (追加模式)
        with open(result_file, 'a', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"📊 Results saved to: {result_file}")
    
    def run_multiple_concurrency_test(self, 
                                     concurrency_list: List[int],
                                     isl: int = 10,
                                     osl: int = 256,
                                     duration: int = 60):
        """
        在多个并发度下运行测试
        
        Args:
            concurrency_list: 并发度列表
            isl: 输入序列长度
            osl: 输出序列长度  
            duration: 每个测试的持续时间(秒)
        """
        print(f"\n{'='*80}")
        print(f"SIMPLE DECODE TEST SUITE")
        print(f"Concurrency levels: {concurrency_list}")
        print(f"Test duration per level: {duration}s")
        print(f"Input length: {isl}, Output length: {osl}")
        print(f"{'='*80}")
        
        for i, concurrency in enumerate(concurrency_list, 1):
            print(f"\n[{i}/{len(concurrency_list)}] Testing concurrency {concurrency}")
            self.run_decode_test(
                concurrency=concurrency,
                isl=isl,
                osl=osl,
                duration=duration
            )
            
            # 测试之间的间隔
            if i < len(concurrency_list):
                print(f"\n⏳ Waiting 5s before next test...")
                time.sleep(5)
        
        print(f"\n✅ All tests completed!")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Simple Decode Test')
    parser.add_argument('--concurrency', type=int, nargs='+', default=[1, 10, 50, 100, 250, 300 ,350,400,450],
                       help='Concurrency levels to test (default: 1 5 10 20)')
    parser.add_argument('--duration', type=int, default=60,
                       help='Test duration in seconds (default: 60)')
    parser.add_argument('--isl', type=int, default=2000,
                       help='Input sequence length (default: 2000)')
    parser.add_argument('--osl', type=int, default=2000,
                       help='Output sequence length (default: 256)')
    parser.add_argument('--service-url', type=str,
                       default=os.getenv('SERVICE_URL', 'http://127.0.0.1:8003'),
                       help='Service URL')
    parser.add_argument('--model', type=str,
                       default=os.getenv('DEPLOYMENT_MODEL_ID', '/shared-models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B'),
                       help='Model name')
    
    args = parser.parse_args()
    
    # 创建测试实例
    tester = SimpleDecodeTest(
        service_url=args.service_url,
        model_name=args.model
    )
    
    # 运行测试
    tester.run_multiple_concurrency_test(
        concurrency_list=args.concurrency,
        isl=args.isl,
        osl=args.osl,
        duration=args.duration
    )


if __name__ == '__main__':
    main()
