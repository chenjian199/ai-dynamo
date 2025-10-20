#!/usr/bin/env bash

set -euo pipefail

#=====configuration=====
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
  "vllm-disagg-2p6d|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg_2p6d.yaml"
  "vllm-disagg-6p2d|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg_6p2d.yaml"
  "vllm-disagg-multinode|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg-multinode.yaml"
  "vllm-disagg-planner|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg_planner.yaml"
  
  # Optimized PD configurations for prefix caching
  "vllm-disagg-optimized-prefix|/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg_optimized_prefix.yaml"
)

#=====select vllm configuration=====
echo "select vllm configuration:"
for i in "${!VLLM_CONFIGS[@]}"; do
  IFS="|" read -r config_name config_path <<< "${VLLM_CONFIGS[$i]}"
  echo "$((i+1)). $config_name ($config_path)"
done

read -rp "input index [1-${#VLLM_CONFIGS[@]}]: " num

if [[ $num =~ ^[0-9]+$ ]] && (( num >= 1 && num <= ${#VLLM_CONFIGS[@]} )); then
  selected="${VLLM_CONFIGS[$((num-1))]}"
  IFS="|" read -r NAME YAML <<< "$selected"
else
  echo "invalid index, exit"
  exit 1
fi


#=====configuration=====
NS="dynamo-kubernetes"
SERVICE_NAME="${NAME}-frontend"
LOCAL_PORT="8005"
SVC_PORT="8000"
ENDPOINT="http://127.0.0.1:${LOCAL_PORT}"
BENCH_NAME="${NAME}_$(date +%Y%m%d_%H%M%S)"
CONCURRENCIES="${CONCURRENCIES:-1,2,5,10,25,50,100,250,300,310,320,330,340,350,360,370,380,390,400,410,420,430,440,450,460,470,480,490,500,510,520,530,540,550,575,600,625,650,700,750,800,850,900,950,1000}"
DEPLOYMENT_MODEL_ID="${DEPLOYMENT_MODEL_ID:-DeepSeek-R1-Distill-Qwen-7B}"
TOKENIZER_PATH="${TOKENIZER_PATH:-/home/bedicloud/models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B}"
CLEANUP="${CLEANUP:-0}"
DISTSERVE_TEST="${DISTSERVE_TEST:-1}"  # 是否运行DistServe风格测试 (0=传统测试, 1=DistServe测试)

#=====log related=====
log() { echo "[$(date '+%F %T')] $*"; }

#=====utility functions=====
run() { log "RUN: $*"; "$@"; }

retry() {
  local max="${1}"; shift
  local sleep_s="${1}"; shift
  local n=0
  until "$@"; do
    n=$((n+1))
    if (( n >= max )); then
      log "ERROR: retry ${max} times failed: $*"
      return 1
    fi
    log "WARN: failed, retry in ${sleep_s}s (${n}/${max}) ..."
    sleep "${sleep_s}"
  done
}

#=====deployment functions=====
wait_deploy_ready() {
  local dep="$1"
  log "waiting for deployment: $dep"
  run kubectl -n "${NS}" rollout status deploy/"${dep}" --timeout=300s
}

wait_all_deployments() {
  local count=0
  
  # wait for DynamoGraphDeployment to create actual deployments
  log "waiting 30 seconds for DynamoGraphDeployment to create deployments..."
  sleep 30
  
  # method 1: discover by name prefix
  log "discovering deployments by name prefix: ${NAME}-"
  deployments=$(kubectl -n "${NS}" get deployments -o name 2>/dev/null | grep "^deployment.apps/${NAME}-" | sed 's/deployment.apps\///' || true)
  log "method 1 found: $deployments"
  
  # method 2: discover by label selector (if method 1 fails)
  if [[ -z "$deployments" ]]; then
    log "method 1 failed, trying label selector"
    deployments=$(kubectl -n "${NS}" get deployments -l "app.kubernetes.io/instance=${NAME}" -o name 2>/dev/null | sed 's/deployment.apps\///' || true)
    log "method 2 found: $deployments"
  fi
  
  # method 3: discover by JSONPath with name prefix (if method 2 fails)
  if [[ -z "$deployments" ]]; then
    log "method 2 failed, trying JSONPath discovery"
    deployments=$(kubectl -n "${NS}" get deployments -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null | grep "^${NAME}-" || true)
    log "method 3 found: $deployments"
  fi
  
  # fallback: hardcoded list
  if [[ -z "$deployments" ]]; then
    log "all discovery methods failed, using fallback list"
    deployments="${NAME}-frontend
${NAME}-vllmdecodeworker
${NAME}-vllmprefillworker"
  fi
  
  log "found deployments: $(echo "$deployments" | tr '\n' ' ')"
  
  # wait for each deployment
  while IFS= read -r deployment; do
    if [[ -n "$deployment" ]]; then
      count=$((count + 1))
      log "waiting for deployment ${count}: $deployment"
      wait_deploy_ready "$deployment"
    fi
  done <<< "$deployments"
  
  log "all ${count} deployments are ready"
}

#=====port forwarding functions=====
start_port_forward() {
  log "start port forwarding: svc/${SERVICE_NAME} ${LOCAL_PORT}:${SVC_PORT}"
  # if there is a port forwarding occupying the same port, kill it first
  if lsof -iTCP:"${LOCAL_PORT}" -sTCP:LISTEN -Pn >/dev/null 2>&1; then
    log "local port ${LOCAL_PORT} is occupied, try to kill the old port-forward process"
    pkill -f "kubectl -n ${NS} port-forward svc/${SERVICE_NAME} ${LOCAL_PORT}:${SVC_PORT}" || true
    sleep 1
  fi

  # background start (completely silent)
  kubectl -n "${NS}" port-forward "svc/${SERVICE_NAME}" "${LOCAL_PORT}:${SVC_PORT}" > /dev/null 2>&1 &
  PF_PID=$!
  
  log "port-forward PID=${PF_PID}"

  # verify port available (repeatedly probe /v1/models)
  log "waiting for service to be ready (this may take several minutes)..."
  retry 30 1 bash -lc "curl -sSf ${ENDPOINT}/v1/models >/dev/null"
  log "port forwarding available: ${ENDPOINT}"
}

stop_port_forward() {
  if [[ -n "${PF_PID}" ]] && kill -0 "${PF_PID}" 2>/dev/null; then
    log "stop port forwarding (PID=${PF_PID})"
    kill "${PF_PID}" || true
    wait "${PF_PID}" || true
  fi
}

#=====GPU monitoring functions=====
start_gpu_monitoring() {
    local monitor_file="$1"
    log "start GPU monitoring to file: $monitor_file"
    
    # background start GPU monitoring
    {
        echo "timestamp,gpu_id,utilization,memory_used,memory_total,power_draw,temperature"
        local count=0
        while true; do
            count=$((count + 1))
            nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu \
                      --format=csv,noheader,nounits | \
            while IFS=',' read -r gpu_id util mem_used mem_total power temp; do
                util=$(echo "$util" | tr -d ' ')
                mem_used=$(echo "$mem_used" | tr -d ' ')
                echo "$(date '+%Y-%m-%d %H:%M:%S'),$gpu_id,$util,$mem_used,$mem_total,$power,$temp"
            done
            #echo "GPU monitoring cycle: $count"
            sleep 1
            
            # check if we should stop (if PID file is deleted, stop monitoring)
            if [[ ! -f "${monitor_file}.pid" ]]; then
                log "GPU monitoring stopped (PID file removed)"
                break
            fi
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

#=====deploy=====
log "deploy: ${NAME} from ${YAML}"
run kubectl -n "${NS}" apply -f "${YAML}"

# wait for all deployments to be ready
wait_all_deployments

# start port forwarding
start_port_forward

# start GPU monitoring
GPU_MONITOR_FILE="benchmarks/results/${BENCH_NAME}/gpu_monitor.csv"
mkdir -p "benchmarks/results/${BENCH_NAME}"
start_gpu_monitoring "$GPU_MONITOR_FILE"

# set cleanup function
cleanup() {
    log "clean up resources..."
    stop_gpu_monitoring "$GPU_MONITOR_FILE"
    stop_port_forward
    if [[ "${CLEANUP}" == "1" ]]; then
        log "CLEANUP=1, delete deployment ${NAME}"
        kubectl -n "${NS}" delete dynamographdeployment "${NAME}" || true
    fi
}
trap cleanup EXIT

#=====run benchmark=====
if [[ "${DISTSERVE_TEST}" == "1" ]]; then
    log "run DistServe-style benchmark: ${BENCH_NAME} | model: ${DEPLOYMENT_MODEL_ID}"
    export CONCURRENCIES
    export TOKENIZER_PATH
    
    # 运行DistServe风格的SLO测试
    run python3 benchmarks/analysis/distserve_benchmark_copy.py "${NAME}"
    
    log "DistServe benchmark completed, results directory: benchmarks/results"
else
    log "run traditional benchmark: ${BENCH_NAME} | model: ${DEPLOYMENT_MODEL_ID}"
    export CONCURRENCIES
    export TOKENIZER_PATH
    run python3 -m benchmarks.utils.benchmark \
      --benchmark-name "${BENCH_NAME}" \
      --endpoint-url "${ENDPOINT}" \
      --model "${DEPLOYMENT_MODEL_ID}"

    log "benchmark completed, results directory: benchmarks/results"

    export CONCURRENCIES="256"
    run python3 -m benchmarks.utils.benchmark \
      --benchmark-name "${BENCH_NAME}" \
      --endpoint-url "${ENDPOINT}" \
      --model "${DEPLOYMENT_MODEL_ID}" \
      --isl 512 \
      --osl 240
fi

#=====analyze benchmark results=====
analyze_benchmark_results() {
    local results_dir="$1"
    local analysis_file="$results_dir/analysis.txt"
    
    log "analyze benchmark results in: $results_dir"
    
    {
        echo "=== Benchmark Performance Analysis ==="
        echo "test time: $(date)"
        echo "model: $DEPLOYMENT_MODEL_ID"
        echo "deployment: $NAME"
        echo ""
        
        echo "=== performance metrics for each concurrency ==="
        printf "┌────────────────────┬────────────────────┬────────────────────┬────────────────────┬────────────────────┬────────────────────┬────────────────────┬────────────────────┐\n"
        printf "│ %-18s │ %-18s │ %-18s │ %-18s │ %-18s │ %-18s │ %-18s │ %-18s │\n" "concurrency" "request throughput" "output throughput" "per usr throughput" "avg latency (ms)" "ttft avg (ms)" "itl avg (ms)" "tpot avg (ms)"
        printf "├────────────────────┼────────────────────┼────────────────────┼────────────────────┼────────────────────┼────────────────────┼────────────────────┼────────────────────┤\n"
        
        # collect all data first, then sort by concurrency
        local temp_file=$(mktemp)
        for concurrency_dir in "$results_dir"/c*; do
            if [[ -d "$concurrency_dir" ]]; then
                local concurrency=$(basename "$concurrency_dir" | sed 's/c//')
                local json_file=$(find "$concurrency_dir" -name "profile_export_genai_perf.json" | head -1)
                
                if [[ -f "$json_file" ]]; then
                    local req_throughput=$(jq -r '.request_throughput.avg' "$json_file")
                    local output_throughput=$(jq -r '.output_token_throughput.avg' "$json_file")
                    local per_user_throughput=$(jq -r '.output_token_throughput_per_user.avg' "$json_file")
                    local avg_latency=$(jq -r '.request_latency.avg' "$json_file")
                    local ttft_avg=$(jq -r '.time_to_first_token.avg' "$json_file")
                    local itl_avg=$(jq -r '.inter_token_latency.avg' "$json_file")
                    local tpot_avg=$(jq -r '.time_to_second_token.avg' "$json_file")
                    
                    # write to temp file with concurrency as first field for sorting
                    printf "%s|%.2f|%.2f|%.2f|%.2f|%.2f|%.2f|%.2f\n" \
                           "$concurrency" "$req_throughput" "$output_throughput" "$per_user_throughput" "$avg_latency" "$ttft_avg" "$itl_avg" "$tpot_avg" >> "$temp_file"
                fi
            fi
        done
        
        # sort by concurrency (first field) and print
        sort -n -t'|' -k1 "$temp_file" | while IFS='|' read -r concurrency req_throughput output_throughput per_user_throughput avg_latency ttft_avg itl_avg tpot_avg; do
            printf "│ %-18s │ %-18.2f │ %-18.2f │ %-18.2f │ %-18.2f │ %-18.2f │ %-18.2f │ %-18.2f │\n" \
                   "$concurrency" "$req_throughput" "$output_throughput" "$per_user_throughput" "$avg_latency" "$ttft_avg" "$itl_avg" "$tpot_avg"
        done
        
        rm -f "$temp_file"
        
        printf "└────────────────────┴────────────────────┴────────────────────┴────────────────────┴────────────────────┴────────────────────┴────────────────────┴────────────────────┘\n"
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
        local gpu_monitor_file="$results_dir/gpu_monitor.csv"
        if [[ -f "$gpu_monitor_file" ]]; then
            echo ""
            echo "=== GPU utilization analysis ==="
            echo "GPU monitoring data saved to: $gpu_monitor_file"
            
            # calculate average GPU utilization
            if [[ -s "$gpu_monitor_file" ]]; then
                local avg_util=$(tail -n +2 "$gpu_monitor_file" | cut -d',' -f3 | awk '{sum+=$1; count++} END {if(count>0) print sum/count; else print 0}')
                local max_util=$(tail -n +2 "$gpu_monitor_file" | cut -d',' -f3 | sort -n | tail -1)
                local avg_mem=$(tail -n +2 "$gpu_monitor_file" | cut -d',' -f4 | awk '{sum+=$1; count++} END {if(count>0) print sum/count; else print 0}')
                local max_mem=$(tail -n +2 "$gpu_monitor_file" | cut -d',' -f4 | sort -n | tail -1)
                
                echo "average GPU utilization: ${avg_util}%"
                echo "maximum GPU utilization: ${max_util}%"
                echo "average memory usage: ${avg_mem}MB"
                echo "maximum memory usage: ${max_mem}MB"
            fi
        fi
        
        echo ""
        echo "=== test configuration ==="
        echo "concurrencies tested: $CONCURRENCIES"
        echo "model: $DEPLOYMENT_MODEL_ID"
        echo "endpoint: $ENDPOINT"
        echo "deployment: $NAME"
        
    } > "$analysis_file"
    
    log "analysis results saved to: $analysis_file"
    cat "$analysis_file"
}

# analyze results for both benchmark runs
if [[ -d "benchmarks/results/${BENCH_NAME}" ]]; then
    analyze_benchmark_results "benchmarks/results/${BENCH_NAME}"
fi

# Usage examples:
# 1. Traditional benchmark test (default):
#    ./run.sh
#    CLEANUP=1 ./run.sh  # with cleanup
#
# 2. DistServe-style SLO test:
#    DISTSERVE_TEST=1 ./run.sh
#    DISTSERVE_TEST=1 CLEANUP=1 ./run.sh  # with cleanup
