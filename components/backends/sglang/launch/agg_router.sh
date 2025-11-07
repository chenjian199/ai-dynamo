#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Setup cleanup trap
cleanup() {
    echo "Cleaning up background processes..."
    kill $DYNAMO_PID $WORKER_PID1 $WORKER_PID2 $WORKER_PID3 2>/dev/null || true
    wait $DYNAMO_PID $WORKER_PID1 $WORKER_PID2 $WORKER_PID3 2>/dev/null || true
    echo "Cleanup complete."
}
trap cleanup EXIT INT TERM

# run ingress
python3 -m dynamo.frontend \
  --router-mode kv \
  --http-port=8003 \
  --kv-overlap-score-weight 10 \
  --router-reset-states &
DYNAMO_PID=$!

# run worker
CUDA_VISIBLE_DEVICES=0 python3 -m dynamo.sglang \
  --model-path /raid5/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B   \
  --served-model-name /raid5/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --page-size 64 \
  --tp 1 \
  --trust-remote-code \
  --kv-events-config '{"publisher":"zmq","topic":"kv-events","endpoint":"tcp://*:5557"}' &
WORKER_PID1=$!

CUDA_VISIBLE_DEVICES=1 python3 -m dynamo.sglang \
  --model-path /raid5/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --served-model-name /raid5/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --page-size 64 \
  --tp 1 \
  --trust-remote-code \
  --kv-events-config '{"publisher":"zmq","topic":"kv-events","endpoint":"tcp://*:5558"}' &
WORKER_PID2=$!

CUDA_VISIBLE_DEVICES=2 python3 -m dynamo.sglang \
  --model-path /raid5/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --served-model-name /raid5/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --page-size 64 \
  --tp 1 \
  --trust-remote-code \
  --kv-events-config '{"publisher":"zmq","topic":"kv-events","endpoint":"tcp://*:5559"}' &
WORKER_PID3=$!

CUDA_VISIBLE_DEVICES=3 python3 -m dynamo.sglang \
  --model-path /raid5/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --served-model-name /raid5/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B \
  --page-size 64 \
  --tp 1 \
  --trust-remote-code \
  --kv-events-config '{"publisher":"zmq","topic":"kv-events","endpoint":"tcp://*:5560"}' 
