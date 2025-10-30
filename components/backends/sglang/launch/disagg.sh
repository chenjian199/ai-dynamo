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

########### RoCE v2 RDMA 环境 ###########
# UCX（nixl 用）
#export UCX_TLS=rc_mlx5,dc_mlx5,ud_mlx5,sm,self,cuda_copy,gdr_copy
export UCX_TLS=rc_x,cuda_ipc,sm,self,cuda_copy,gdr_copy
export UCX_SOCKADDR_TLS_PRIORITY=rdmacm,tcp
export UCX_NET_DEVICES=mlx5_2:1          # 按需改成你的目标口
export UCX_IB_GID_INDEX=3
export UCX_IB_TRAFFIC_CLASS=138
export UCX_IB_GPU_DIRECT_RDMA=y
export UCX_IB_PCI_RELAXED_ORDERING=y
export UCX_RNDV_SCHEME=auto
export UCX_LOG_LEVEL=info               # 排障时再开

# # NCCL（TP/PP 通信）
export NCCL_IB_DISABLE=0
export NCCL_IB_HCA=mlx5_2
export NCCL_IB_GID_INDEX=3
export NCCL_IB_TC=138
export NCCL_SOCKET_IFNAME=enp27s0np0     # 对应 mlx5_2 的网口
#export NCCL_DEBUG=INFO
#########################################

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

