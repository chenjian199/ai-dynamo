#!/bin/bash

set -euo pipefail

#=====color=====
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

#=====log =====
log() { echo -e "${BLUE}[$(date '+%F %T')]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%F %T')] WARN:${NC} $*"; }
error() { echo -e "${RED}[$(date '+%F %T')] ERROR:${NC} $*"; }
success() { echo -e "${GREEN}[$(date '+%F %T')] SUCCESS:${NC} $*"; }

#=====set env variables=====
NS="dynamo-kubernetes"
VLLM_CONFIGS=(
  # Aggregated configurations
  "vllm-agg-kvbm|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/agg_kvbm.yaml"
  "vllm-agg-router|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/agg_router.yaml"
  "vllm-agg|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/agg.yaml"
  
  # Disaggregated configurations
  "vllm-disagg-kvbm-4p4d|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg_kvbm_4p4d.yaml"
  "vllm-disagg-kvbm-tp2|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg_kvbm_tp2.yaml"
  "vllm-disagg-kvbm|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg_kvbm.yaml"
  "vllm-v1-disagg-router|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg_router.yaml"
  "vllm-disagg|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg.yaml"
  "vllm-disagg-multinode|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg-multinode.yaml"
  "vllm-disagg-planner|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg_planner.yaml"
)

#=====select vllm configuration=====
echo "select vllm configuration:"
for i in "${!VLLM_CONFIGS[@]}"; do
  IFS="|" read -r config_name config_path <<< "${VLLM_CONFIGS[$i]}"
  echo "$((i+1)). $config_name ($config_path)"
done

read -rp "input index [1-${#VLLM_CONFIGS[@]}]:" num

if [[ $num =~ ^[0-9]+$ ]] && (( num >= 1 && num <= ${#VLLM_CONFIGS[@]} )); then
  selected="${VLLM_CONFIGS[$((num-1))]}"
  IFS="|" read -r NAME YAML <<< "$selected"
else
  echo "invalid index, exit"
  exit 1
fi

#=====configuration parameters=====
LOCAL_PORT=8003
ENDPOINT="http://127.0.0.1:${LOCAL_PORT}"
NAMESPACE="dynamo-kubernetes"
SERVICE_NAME="${NAME}-frontend"
SERVICE_PORT=8000
PORT_FORWARD_PID=""
PORT_FORWARD_LOG="/tmp/port_forward.log"

#=====extreme test configuration=====
STRESS_CONCURRENCIES="100,200,300,400,410,420,430,440,450,460,470,480,490,500,510,520,530,540,550,575,600,625,650,700,750,800,850,900,950,1000"
DEPLOYMENT_MODEL_ID="${DEPLOYMENT_MODEL_ID:-DeepSeek-R1-Distill-Qwen-7B}"
TOKENIZER_PATH="${TOKENIZER_PATH:-/home/bedicloud/models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B}"

#=====test parameters=====
ISL=2000  # 输入序列长度
OSL=256   # 输出序列长度
STDDEV=10 # 标准差

#=====result directory=====
STRESS_RESULTS_DIR="benchmarks/results/${NAME}_stress_test_$(date +%Y%m%d_%H%M%S)"

#=====port forwarding=====
start_port_forward() {
    log "start port forwarding: ${NAMESPACE}/${SERVICE_NAME}:${SERVICE_PORT} -> localhost:${LOCAL_PORT}"
    
    # check if port is already in use
    if lsof -iTCP:"${LOCAL_PORT}" -sTCP:LISTEN -Pn >/dev/null 2>&1; then
        log "local port ${LOCAL_PORT} is occupied, try to kill the old port-forward process"
        pkill -f "kubectl -n ${NAMESPACE} port-forward svc/${SERVICE_NAME} ${LOCAL_PORT}:${SERVICE_PORT}" || true
        sleep 1
    fi
    
    # start port forwarding in background (completely silent)
    nohup kubectl -n "${NAMESPACE}" port-forward "svc/${SERVICE_NAME}" "${LOCAL_PORT}:${SERVICE_PORT}" > "${PORT_FORWARD_LOG}" 2>&1 &
    PORT_FORWARD_PID=$!
    
    # ensure the process is completely detached from terminal
    disown $PORT_FORWARD_PID 2>/dev/null || true
    
    log "port-forward PID: ${PORT_FORWARD_PID}"
    log "port-forward logs: ${PORT_FORWARD_LOG}"
    
    # wait for port forwarding to be ready
    local retry_count=0
    local max_retries=30
    while [[ $retry_count -lt $max_retries ]]; do
        if curl -s "${ENDPOINT}/v1/models" > /dev/null 2>&1; then
            success "port forwarding is ready"
            return 0
        fi
        retry_count=$((retry_count + 1))
        log "waiting for port forwarding to be ready... (${retry_count}/${max_retries})"
        sleep 1
    done
    
    error "port forwarding failed to start after ${max_retries} seconds"
    return 1
}

stop_port_forward() {
    if [[ -n "${PORT_FORWARD_PID}" ]] && kill -0 "${PORT_FORWARD_PID}" 2>/dev/null; then
        log "stop port forwarding (PID: ${PORT_FORWARD_PID})"
        kill "${PORT_FORWARD_PID}" || true
        wait "${PORT_FORWARD_PID}" 2>/dev/null || true
        PORT_FORWARD_PID=""
    fi
    
    # also kill any remaining port-forward processes
    pkill -f "kubectl -n ${NAMESPACE} port-forward svc/${SERVICE_NAME} ${LOCAL_PORT}:${SERVICE_PORT}" || true
}

#=====GPU monitoring=====
start_gpu_monitoring() {
    local monitor_file="$1"
    log "start GPU monitoring to file: $monitor_file"
    
    # background start GPU monitoring
    {
        echo "timestamp,gpu_id,utilization,memory_used,memory_total,power_draw,temperature"
        while true; do
            nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu \
                      --format=csv,noheader,nounits | \
            while IFS=',' read -r gpu_id util mem_used mem_total power temp; do
                util=$(echo "$util" | tr -d ' ')
                mem_used=$(echo "$mem_used" | tr -d ' ')
                if [[ "$util" -gt 0 && "$mem_used" -gt 0 ]]; then
                    echo "$(date '+%Y-%m-%d %H:%M:%S'),$gpu_id,$util,$mem_used,$mem_total,$power,$temp"
                fi
            done
            sleep 1
        done
    } > "$monitor_file" &
    
    echo $! > "${monitor_file}.pid"
    log "GPU monitoring process PID: $(cat ${monitor_file}.pid)"
}

stop_gpu_monitoring() {
    local monitor_file="$1"
    if [[ -f "${monitor_file}.pid" ]]; then
        local pid=$(cat "${monitor_file}.pid")
        if kill -0 "$pid" 2>/dev/null; then
            log "stop GPU monitoring process (PID: $pid)"
            kill "$pid"
            wait "$pid" 2>/dev/null || true
        fi
        rm -f "${monitor_file}.pid"
    fi
}

#=====check GPU status=====
check_gpu_status() {
    log "check GPU status..."
    nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,power.draw \
              --format=csv,noheader,nounits | \
    while IFS=',' read -r gpu_id name util mem_used mem_total power; do
        log "GPU $gpu_id: $name, utilization: ${util}%, memory: ${mem_used}/${mem_total}MB, power: ${power}W"
    done
}

#=====run single concurrency test=====
run_concurrency_test() {
    local concurrency=$1
    local output_dir="$2"
    
    log "start testing concurrency: $concurrency"
    
    # create output directory
    mkdir -p "$output_dir"
    
    # run genai-perf
    local cmd=(
        "genai-perf" "profile"
        "-m" "$DEPLOYMENT_MODEL_ID"
        "--endpoint-type" "chat"
        "--streaming"
        "-u" "$ENDPOINT"
        "--synthetic-input-tokens-mean" "$ISL"
        "--synthetic-input-tokens-stddev" "$STDDEV"
        "--concurrency" "$concurrency"
        "--output-tokens-mean" "$OSL"
        "--extra-inputs" "max_tokens:$OSL"
        "--extra-inputs" "min_tokens:$OSL"
        "--extra-inputs" "ignore_eos:true"
        "--tokenizer" "$TOKENIZER_PATH"
        "--artifact-dir" "$output_dir"
        "--" "-vv" "--max-threads=500"
    )
    
    log "execute command: ${cmd[*]}"
    
    if "${cmd[@]}"; then
        success "concurrency $concurrency test completed"
        return 0
    else
        error "concurrency $concurrency test failed"
        return 1
    fi
}

#=====analyze test results=====
analyze_results() {
    local results_dir="$1"
    local analysis_file="$results_dir/analysis.txt"
    
    log "analyze test results..."
    
    {
        echo "=== GPU extreme throughput test analysis ==="
        echo "test time: $(date)"
        echo "model: $DEPLOYMENT_MODEL_ID"
        echo "input length: $ISL tokens"
        echo "output length: $OSL tokens"
        echo ""
        
        echo "=== performance metrics for each concurrency ==="
        printf "┌────────────────────┬────────────────────┬────────────────────┬────────────────────┬────────────────────┐\n"
        printf "│ %-18s │ %-18s │ %-18s │ %-18s │ %-18s │\n" "concurrency" "request throughput" "output throughput" "per usr throughput" "average latency"
        printf "├────────────────────┼────────────────────┼────────────────────┼────────────────────┼────────────────────┤\n"
            
        for concurrency_dir in "$results_dir"/c*; do
            if [[ -d "$concurrency_dir" ]]; then
                local concurrency=$(basename "$concurrency_dir" | sed 's/c//')
                local json_file=$(find "$concurrency_dir" -name "profile_export_genai_perf.json" | head -1)
                
                if [[ -f "$json_file" ]]; then
                    local req_throughput=$(jq -r '.request_throughput.avg' "$json_file")
                    local output_throughput=$(jq -r '.output_token_throughput.avg' "$json_file")
                    local per_user_throughput=$(jq -r '.output_token_throughput_per_user.avg' "$json_file")
                    local avg_latency=$(jq -r '.request_latency.avg' "$json_file")
                    
                    printf "│ %-18s │ %-18.2f │ %-18.2f │ %-18.2f │ %-18.2f │\n" \
                           "$concurrency" "$req_throughput" "$output_throughput" "$per_user_throughput" "$avg_latency"
                fi
            fi
        done
        
        printf "└────────────────────┴────────────────────┴────────────────────┴────────────────────┴────────────────────┘\n"
        echo ""
        echo "=== performance bottleneck analysis ==="
        
        # find the highest throughput
        local max_throughput=0
        local max_concurrency=0
        for concurrency_dir in "$results_dir"/c*; do
            if [[ -d "$concurrency_dir" ]]; then
                local concurrency=$(basename "$concurrency_dir" | sed 's/c//')
                local json_file=$(find "$concurrency_dir" -name "profile_export_genai_perf.json" | head -1)
                
                if [[ -f "$json_file" ]]; then
                    local output_throughput=$(jq -r '.output_token_throughput.avg' "$json_file")
                    if (( $(echo "$output_throughput > $max_throughput" | bc -l) )); then
                        max_throughput=$output_throughput
                        max_concurrency=$concurrency
                    fi
                fi
            fi
        done
        
        echo "highest output throughput: ${max_throughput} tokens/s (concurrency: $max_concurrency)"
        
        # analyze GPU utilization
        if [[ -f "$results_dir/gpu_monitor.csv" ]]; then
            echo ""
            echo "=== GPU utilization analysis ==="
            echo "GPU monitoring data saved to: $results_dir/gpu_monitor.csv"
        fi
        
    } > "$analysis_file"
    
    log "analysis results saved to: $analysis_file"
    cat "$analysis_file"
}

#=====main function=====
main() {
    log "start GPU extreme throughput stress test"
    
    # check dependencies
    if ! command -v nvidia-smi &> /dev/null; then
        error "nvidia-smi not found, please ensure NVIDIA driver is installed"
        exit 1
    fi
    
    if ! command -v genai-perf &> /dev/null; then
        error "genai-perf not found, please ensure it is installed"
        exit 1
    fi
    
    if ! command -v jq &> /dev/null; then
        error "jq not found, please install: sudo apt-get install jq"
        exit 1
    fi
    
    if ! command -v bc &> /dev/null; then
        error "bc not found, please install: sudo apt-get install bc"
        exit 1
    fi
    
    # create result directory
    mkdir -p "$STRESS_RESULTS_DIR"
    log "results will be saved to: $STRESS_RESULTS_DIR"
    
    # start port forwarding
    if ! start_port_forward; then
        error "failed to start port forwarding"
        exit 1
    fi
    
    # check GPU status
    check_gpu_status
    
    # start GPU monitoring
    start_gpu_monitoring "$STRESS_RESULTS_DIR/gpu_monitor.csv"
    
    # set cleanup function
    cleanup() {
        log "clean up resources..."
        stop_gpu_monitoring "$STRESS_RESULTS_DIR/gpu_monitor.csv"
        stop_port_forward
    }
    trap cleanup EXIT
    
    # run stress test
    local failed_tests=0
    local total_tests=0
    
    IFS=',' read -ra CONCURRENCIES <<< "$STRESS_CONCURRENCIES"
    for concurrency in "${CONCURRENCIES[@]}"; do
        total_tests=$((total_tests + 1))
        local output_dir="$STRESS_RESULTS_DIR/c$concurrency"
        
        log "test progress: $total_tests/${#CONCURRENCIES[@]} - concurrency: $concurrency"
        
        if run_concurrency_test "$concurrency" "$output_dir"; then
            success "concurrency $concurrency test completed"
        else
            error "concurrency $concurrency test failed"
            failed_tests=$((failed_tests + 1))
            
            # if consecutive failures, stop the test
            if [[ $failed_tests -ge 3 ]]; then
                warn "consecutive failures too many, stop the test"
                break
            fi
        fi
        
        # short break, let the GPU cool down
        sleep 5
    done
    
    # analyze results
    analyze_results "$STRESS_RESULTS_DIR"
    
    # 总结
    log "stress test completed"
    log "total tests: $total_tests"
    log "failed tests: $failed_tests"
    log "results directory: $STRESS_RESULTS_DIR"
}

# run main function
main "$@"
