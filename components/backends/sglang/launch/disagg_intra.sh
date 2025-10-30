#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Setup cleanup trap
cleanup() {
    echo "Cleaning up background processes..."
    kill $DYNAMO_PID $PREFILL_PID  >/dev/null || true
    wait $DYNAMO_PID $PREFILL_PID  >/dev/null || true
    echo "Cleanup complete."
}
trap cleanup EXIT INT TERM


# run ingress
python3 -m dynamo.frontend --http-port=8005  &
DYNAMO_PID=$!

CUDA_VISIBLE_DEVICES=0,1,2,3 python3 -m dynamo.sglang \
  --model-path /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B \
  --served-model-name /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B \
  --page-size 16 \
  --tp 4 \
  --trust-remote-code \
  --disaggregation-mode prefill \
  --disaggregation-bootstrap-port 12347 \
  --host 0.0.0.0 \
  --disaggregation-transfer-backend nixl &
PREFILL_PID=$!

# run decode worker
CUDA_VISIBLE_DEVICES=4,5,6,7 python3 -m dynamo.sglang \
  --model-path /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B \
  --served-model-name /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B \
  --page-size 16 \
  --tp 4 \
  --trust-remote-code \
  --disaggregation-mode decode \
  --disaggregation-bootstrap-port 12347 \
  --host 0.0.0.0 \
  --disaggregation-transfer-backend nixl 

