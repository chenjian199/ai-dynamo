#!/usr/bin/env python3
# calc_kv_per_token.py
import argparse
from transformers import AutoConfig

DTYPE_BYTES = {
    "fp16": 2, "bf16": 2, "float16": 2, "bfloat16": 2,
    "fp32": 4, "float32": 4,
    "fp8": 1,  # 近似；不同 FP8 格式略有差异
}

def calc_kv_bytes_per_token(cfg, kv_dtype_bytes=2):
    n_layers = getattr(cfg, "num_hidden_layers", None) or getattr(cfg, "n_layer", None)
    n_heads = getattr(cfg, "num_attention_heads", None) or getattr(cfg, "n_head", None)
    n_kv_heads = getattr(cfg, "num_key_value_heads", None) or getattr(cfg, "n_kv_head", n_heads)
    hidden = getattr(cfg, "hidden_size", None) or getattr(cfg, "n_embd", None)

    if not all([n_layers, n_heads, n_kv_heads, hidden]):
        raise ValueError("缺少必要的配置字段：hidden_size/num_attention_heads/num_key_value_heads/num_hidden_layers")

    head_dim = hidden // n_heads
    elems_per_token = 2 * n_layers * n_kv_heads * head_dim  # 2 = K+V
    bytes_per_token = elems_per_token * kv_dtype_bytes
    return bytes_per_token, dict(n_layers=n_layers, n_heads=n_heads, n_kv_heads=n_kv_heads, head_dim=head_dim)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model",default="/raid5/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B",  help="HF 模型名或本地目录")
    ap.add_argument("--kv-dtype", default="fp16", help="KV 数据类型: fp16/bf16/fp32/fp8")
    args = ap.parse_args()

    kv_bytes = DTYPE_BYTES.get(args.kv_dtype.lower(), None)
    if kv_bytes is None:
        raise SystemExit(f"不支持的 --kv-dtype: {args.kv_dtype}")

    cfg = AutoConfig.from_pretrained(args.model, trust_remote_code=True)
    bpt, meta = calc_kv_bytes_per_token(cfg, kv_bytes)
    print(f"[模型] {args.model}")
    print(f"[结构] layers={meta['n_layers']}, heads={meta['n_heads']}, kv_heads={meta['n_kv_heads']}, head_dim={meta['head_dim']}")
    print(f"[假定 KV dtype] {args.kv_dtype} -> {kv_bytes} bytes")
    print(f"[理论 KV 大小/每 token] {bpt/1024/1024:.3f} MiB  ({bpt} bytes)")
