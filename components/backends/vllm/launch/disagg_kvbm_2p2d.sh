#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
set -e
trap 'echo Cleaning up...; kill 0' EXIT

# run ingress with KV router
python -m dynamo.frontend --router-mode kv --http-port=8005 &

# run decode workers on GPU 0 and 1, without enabling KVBM
CUDA_VISIBLE_DEVICES=0,1,2,3 \
  python3 -m dynamo.vllm \
    --model /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B \
    --connector nixl  &

# DYN_KVBM_BARRIER_ID_PREFIX=kvbm_1 \
DYN_KVBM_CPU_CACHE_GB=200 \
CUDA_VISIBLE_DEVICES=4,5,6,7 \
  python3 -m dynamo.vllm \
    --model /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B \
    --is-prefill-worker \
    --connector kvbm nixl 
