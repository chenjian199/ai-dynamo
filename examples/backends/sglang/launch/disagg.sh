#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Setup cleanup trap
cleanup() {
    echo "Cleaning up background processes..."
    kill $DYNAMO_PID $PREFILL_PID1 $PREFILL_PID2 $PREFILL_PID3 2>/dev/null || true
    wait $DYNAMO_PID $PREFILL_PID1 $PREFILL_PID2 $PREFILL_PID3 2>/dev/null || true
    echo "Cleanup complete."
}
trap cleanup EXIT INT TERM


# run ingress
python3 -m dynamo.frontend --http-port=8005 &
DYNAMO_PID=$!
export UCX_LOG_LEVEL=info
#export UCX_TLS=cuda_ipc,cuda_copy,sm
export UCX_NET_DEVICES=mlx5_2:1

# run prefill worker
CUDA_VISIBLE_DEVICES=0 python3 -m dynamo.sglang \
  --model-path /models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --served-model-name /models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --page-size 16 \
  --tp 1 \
  --trust-remote-code \
  --disaggregation-mode prefill \
  --disaggregation-bootstrap-port 12347 \
  --host 0.0.0.0 \
  --disaggregation-transfer-backend nixl &
PREFILL_PID1=$!

CUDA_VISIBLE_DEVICES=1 python3 -m dynamo.sglang \
  --model-path /models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --served-model-name /models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --page-size 16 \
  --tp 1 \
  --trust-remote-code \
  --disaggregation-mode prefill \
  --disaggregation-bootstrap-port 12348 \
  --host 0.0.0.0 \
  --disaggregation-transfer-backend nixl &
PREFILL_PID2=$!

CUDA_VISIBLE_DEVICES=2 python3 -m dynamo.sglang \
  --model-path /models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --served-model-name /models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --page-size 16 \
  --tp 1 \
  --trust-remote-code \
  --disaggregation-mode prefill \
  --disaggregation-bootstrap-port 12349 \
  --host 0.0.0.0 \
  --disaggregation-transfer-backend nixl &
PREFILL_PID3=$!

# run decode worker
CUDA_VISIBLE_DEVICES=3 python3 -m dynamo.sglang \
  --model-path /models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --served-model-name /models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --page-size 16 \
  --tp 1 \
  --trust-remote-code \
  --disaggregation-mode decode \
  --disaggregation-bootstrap-port 12350 \
  --host 0.0.0.0 \
  --disaggregation-transfer-backend nixl
