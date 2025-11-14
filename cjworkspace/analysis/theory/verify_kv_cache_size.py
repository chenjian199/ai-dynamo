#!/usr/bin/env python3
import argparse
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", 
        default="/raid5/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B", 
        help="模型路径，默认 DeepSeek-R1-Distill-Llama-8B")
    parser.add_argument(
        "--num-tokens", 
        type=int, 
        default=414368, 
        help="Token 数，默认 41436")
    parser.add_argument(
        "--kv-size-gb", 
        type=float, 
        default=50.58, 
        help="KV cache 总大小（GB），默认 50.58")
    args = parser.parse_args()
    
    # 计算实际 KV cache 大小
    if args.kv_size_gb:
        actual_bytes = int(args.kv_size_gb * 1024 * 1024 * 1024)
    elif args.k_size_gb and args.v_size_gb:
        actual_bytes = int((args.k_size_gb + args.v_size_gb) * 1024 * 1024 * 1024)
    else:
        print("❌ 请提供 --kv-size-gb 或 --k-size-gb --v-size-gb")
        return 1
    actual_bytes_per_token = actual_bytes / args.num_tokens
    print(f"实际值: {actual_bytes:,} bytes ({actual_bytes/1024/1024/1024:.3f} GiB)")
    print(f"实际值: {int(actual_bytes_per_token):,} bytes/token ({actual_bytes_per_token/1024/1024:.3f} MB/token)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
