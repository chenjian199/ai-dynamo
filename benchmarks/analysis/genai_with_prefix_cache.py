#!/usr/bin/env python3
"""
测试脚本：使用前缀缓存来验证PD分离的真正优势
"""

import subprocess
import os
import json
import time
from pathlib import Path

def run_genai_perf_with_prefix_cache(
    service_url: str,
    model_name: str,
    prefix_length: int,
    unique_length: int,
    osl: int,
    num_prefix_prompts: int,
    concurrency: int,
    output_dir: Path,
) -> bool:
    """运行带有前缀缓存的genai-perf测试"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    deployment_model_id = os.environ.get("DEPLOYMENT_MODEL_ID", model_name)
    tokenizer_arg = os.environ.get("TOKENIZER_PATH", model_name)
    
    cmd = [
        "genai-perf",
        "profile",
        "-m", deployment_model_id,
        "--endpoint-type", "chat",
        "--streaming",
        "-u", service_url,
        "--synthetic-input-tokens-mean", str(unique_length),
        "--synthetic-input-tokens-stddev", "0",
        "--concurrency", str(concurrency),
        "--output-tokens-mean", str(osl),
        "--extra-inputs", f"max_tokens:{osl}",
        "--extra-inputs", f"min_tokens:{osl}",
        "--extra-inputs", "ignore_eos:true",
        "--tokenizer", tokenizer_arg,
        "--prefix-prompt-length", str(prefix_length),
        "--num-prefix-prompts", str(num_prefix_prompts),
        "--artifact-dir", str(output_dir),
        "--", "-vv", "--max-threads=300",
    ]
    
    print(f"Running genai-perf with prefix cache:")
    print(f"  Prefix length: {prefix_length}")
    print(f"  Unique length: {unique_length}")
    print(f"  Total ISL: {prefix_length + unique_length}")
    print(f"  OSL: {osl}")
    print(f"  Concurrency: {concurrency}")
    print(f"  Num prefix prompts: {num_prefix_prompts}")
    
    try:
        gap_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = gap_process.communicate(timeout=300)
        
        if gap_process.returncode == 0:
            print(f"✅ Concurrency {concurrency} test completed successfully")
            return True
        else:
            print(f"❌ Concurrency {concurrency} test failed")
            print(f"STDERR: {stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ Concurrency {concurrency} test timed out after 5 minutes")
        gap_process.terminate()
        gap_process.kill()
        return False
    except Exception as e:
        print(f"💥 Concurrency {concurrency} test failed with error: {e}")
        return False

def main():
    # 配置参数
    service_url = "http://127.0.0.1:8003"
    model_name = "DeepSeek-R1-Distill-Qwen-7B"
    
    # 前缀缓存测试参数
    prefix_length = 1900  # 共享前缀长度
    unique_length = 100   # 每个请求独有的token长度
    total_isl = prefix_length + unique_length  # 总输入长度
    osl = 256
    num_prefix_prompts = 10  # 前缀模板数量
    
    # 测试并发数
    concurrencies = [1, 10, 50, 100, 200, 300, 400, 500,600,700,800,900,1000]
    
    # 输出目录
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    base_output_dir = Path(f"/home/bedicloud/dynamo-main/benchmarks/results/prefix_cache_test_{timestamp}")
    
    print("🚀 开始前缀缓存测试")
    print(f"📊 测试配置:")
    print(f"  总输入长度: {total_isl}")
    print(f"  前缀长度: {prefix_length} ({prefix_length/total_isl*100:.1f}%)")
    print(f"  独有长度: {unique_length} ({unique_length/total_isl*100:.1f}%)")
    print(f"  输出长度: {osl}")
    print(f"  前缀模板数: {num_prefix_prompts}")
    print(f"  测试并发数: {concurrencies}")
    print()
    
    results = {}
    
    for concurrency in concurrencies:
        print(f"🔄 测试并发数: {concurrency}")
        
        output_dir = base_output_dir / f"c{concurrency}"
        
        success = run_genai_perf_with_prefix_cache(
            service_url=service_url,
            model_name=model_name,
            prefix_length=prefix_length,
            unique_length=unique_length,
            osl=osl,
            num_prefix_prompts=num_prefix_prompts,
            concurrency=concurrency,
            output_dir=output_dir,
        )
        
        results[concurrency] = success
        
        if success:
            print(f"✅ 并发数 {concurrency} 测试成功")
        else:
            print(f"❌ 并发数 {concurrency} 测试失败")
        
        print(f"⏳ 等待5秒后继续下一个测试...")
        time.sleep(5)
        print()
    
    # 生成测试报告
    print("📋 测试结果汇总:")
    print("=" * 50)
    successful_tests = sum(1 for success in results.values() if success)
    total_tests = len(results)
    
    print(f"总测试数: {total_tests}")
    print(f"成功测试: {successful_tests}")
    print(f"失败测试: {total_tests - successful_tests}")
    print(f"成功率: {successful_tests/total_tests*100:.1f}%")
    print()
    
    print("详细结果:")
    for concurrency, success in results.items():
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  并发数 {concurrency:3d}: {status}")
    
    print(f"\n📁 结果保存在: {base_output_dir}")
    print("🎯 这个测试应该能展示PD分离的真正优势！")

if __name__ == "__main__":
    main()
