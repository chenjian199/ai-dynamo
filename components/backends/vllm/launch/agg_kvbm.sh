#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
set -e
trap 'echo Cleaning up...; kill 0' EXIT

# run ingress
python3 -m dynamo.frontend --http-port=8003 &

# run worker with KVBM enabled
# NOTE: remove --enforce-eager for production use
DYN_KVBM_CPU_CACHE_GB=200 \
CUDA_VISIBLE_DEVICES=0,1,2,3 \
  python3 -m dynamo.vllm  \
  --model /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B \
  --connector kvbm &

DYN_KVBM_CPU_CACHE_GB=200 \
CUDA_VISIBLE_DEVICES=4,5,6,7 \
  python3 -m dynamo.vllm  \
  --model /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B \
  --is-prefill-worker \
  --connector kvbm 