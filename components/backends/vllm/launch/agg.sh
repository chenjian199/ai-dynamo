#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
set -e
trap 'echo Cleaning up...; kill 0' EXIT

# run ingress
python -m dynamo.frontend --http-port=8003 &

# run worker
DYN_SYSTEM_ENABLED=true DYN_SYSTEM_PORT=8081 \
python -m dynamo.vllm \
    --model /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B  \
    --connector none 

