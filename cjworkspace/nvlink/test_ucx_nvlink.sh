#!/bin/bash

cleanup() { 
    echo "stopping dcgmi monitor "
    kill $DCGMI_PID $SERVER_PID  2>/dev/null || true
    wait $DCGMI_PID $SERVER_PID  2>/dev/null || true
    echo "stop dcgmi monitor done"
}

trap cleanup EXIT INT TERM

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/log"
mkdir -p "$LOG_DIR"

export UCX_TLS=cuda_ipc,cuda_copy,sm
export UCX_LOG_LEVEL=INFO

MSG_SIZE=1000000000      # 1GB 消息大小
NUM_ITER=1000       
TEST_TYPE=tag_bw    

echo "start dcgmi monitor"
dcgmi dmon -i 0,1 -e 203,204,449,1009,1010,1011,1012 -d 500 > "$LOG_DIR/dcgmi_monitor.log" 2>&1 &
DCGMI_PID=$!
sleep 2

echo "start ucx server"
CUDA_VISIBLE_DEVICES=0  ucx_perftest  \
    -m cuda \
    2>&1 | tee "$LOG_DIR/ucx_server.log" &
SERVER_PID=$!
sleep 2  

echo "start ucx client"
CUDA_VISIBLE_DEVICES=1 ucx_perftest 127.0.0.1 \
    -t $TEST_TYPE \
    -s $MSG_SIZE \
    -n $NUM_ITER \
    -m cuda \
    2>&1 | tee "$LOG_DIR/ucx_client.log"

echo "test ucx nvlink done"
sleep 2