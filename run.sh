#!/usr/bin/env bash

set -euo pipefail

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

#=====port forwarding=====
LOCAL_PORT=8003
SVC_PORT=8000
SVC_NAME="${NAME}-frontend"

#=====benchmark related=====
BENCH_NAME="${NAME}"
ENDPOINT="http://127.0.0.1:${LOCAL_PORT}"
CONCURRENCIES="${CONCURRENCIES:-1,2,5,10,25,50,100,250,500}"

#=====model related=====
DEPLOYMENT_MODEL_ID="${DEPLOYMENT_MODEL_ID:-DeepSeek-R1-Distill-Qwen-7B}"
TOKENIZER_PATH="${TOKENIZER_PATH:-/home/bedicloud/models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B}"

#=====cleanup related=====
CLEANUP="${CLEANUP:-0}"

#=====log related=====
log() { echo "[$(date '+%F %T')] $*"; }

#=====run command and print log=====
run() {
  log "RUN: $*"
  "$@"
}

#=====retry tool=====
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

#=====wait deployment ready=====
wait_deploy_ready() {
  local dep="$1"
  retry 60 5 kubectl -n "${NS}" get deploy "${dep}" >/dev/null 2>&1
  run kubectl -n "${NS}" rollout status deploy/"${dep}" --timeout=300s
}

#=====wait service ready=====
wait_service() {
  local svc="$1"
  retry 60 3 kubectl -n "${NS}" get svc "${svc}" >/dev/null 2>&1
}

#=====port forwarding and verify=====
PF_PID=""
start_port_forward() {
  log "start port forwarding: svc/${SVC_NAME} ${LOCAL_PORT}:${SVC_PORT}"
  # if there is a port forwarding occupying the same port, kill it first
  if lsof -iTCP:"${LOCAL_PORT}" -sTCP:LISTEN -Pn >/dev/null 2>&1; then
    log "local port ${LOCAL_PORT} is occupied, try to kill the old port-forward process"
    pkill -f "kubectl -n ${NS} port-forward svc/${SVC_NAME} ${LOCAL_PORT}:${SVC_PORT}" || true
    sleep 1
  fi

  # background start
  kubectl -n "${NS}" port-forward "svc/${SVC_NAME}" "${LOCAL_PORT}:${SVC_PORT}" > /tmp/port-forward-${NAME}.log 2>&1 &
  PF_PID=$!
  log "port-forward PID=${PF_PID}"

  # verify port available (repeatedly probe /v1/models)
  retry 60 1 bash -lc "curl -sSf ${ENDPOINT}/v1/models >/dev/null"
  log "port forwarding available: ${ENDPOINT}"
}

stop_port_forward() {
  if [[ -n "${PF_PID}" ]] && kill -0 "${PF_PID}" 2>/dev/null; then
    log "stop port forwarding (PID=${PF_PID})"
    kill "${PF_PID}" || true
    wait "${PF_PID}" || true
  fi
}

#=====cleanup on exit=====
cleanup_on_exit() {
  stop_port_forward
  if [[ "${CLEANUP}" == "1" ]]; then
    log "CLEANUP=1, delete deployment ${NAME}"
    kubectl -n "${NS}" delete dynamographdeployment "${NAME}" || true
  fi
}
trap cleanup_on_exit EXIT

#=====apply cr and wait for components ready=====
run kubectl -n "${NS}" apply -f "${YAML}"

# wait for service ready
wait_service "${SVC_NAME}"

# automatically discover and wait for all deployments
wait_all_deployments() {
  log "discovering deployments for deployment: ${NAME}"
  
  # wait a moment for deployments to be created by the operator
  log "waiting for operator to create deployments..."
  sleep 3
  
  # method 1: get all deployments that start with our deployment name
  local deployments
  deployments=$(kubectl -n "${NS}" get deployments -o name 2>/dev/null | grep "^deployment.apps/${NAME}-" | sed 's/deployment.apps\///' || true)
  
  # debug: show all deployments in namespace
  log "all deployments in namespace ${NS}:"
  kubectl -n "${NS}" get deployments -o name 2>/dev/null || true
  
  if [[ -z "$deployments" ]]; then
    log "WARN: no deployments found with prefix '${NAME}-'"
    
    # method 2: try to find deployments by label selector
    log "attempting to discover deployments by label selector..."
    deployments=$(kubectl -n "${NS}" get deployments -l "app.kubernetes.io/instance=${NAME}" -o name 2>/dev/null | sed 's/deployment.apps\///' || true)
    
    if [[ -z "$deployments" ]]; then
      # method 3: try to find deployments by owner reference or other labels
      log "attempting to discover deployments by owner reference..."
      deployments=$(kubectl -n "${NS}" get deployments -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null | grep "^${NAME}-" || true)
      
      if [[ -z "$deployments" ]]; then
        log "WARN: no deployments found by any method, falling back to manual list"
        # fallback to manual list for backward compatibility
        wait_deploy_ready "${NAME}-frontend"
        wait_deploy_ready "${NAME}-vllmdecodeworker" 
        wait_deploy_ready "${NAME}-vllmprefillworker"
        return
      fi
    fi
  fi
  
  log "found deployments: $(echo "$deployments" | tr '\n' ' ')"
  
  # wait for each discovered deployment
  local count=0
  while IFS= read -r deployment; do
    if [[ -n "$deployment" ]]; then
      count=$((count + 1))
      log "waiting for deployment ${count}: $deployment"
      wait_deploy_ready "$deployment"
    fi
  done <<< "$deployments"
  
  log "successfully waited for ${count} deployments"
}

wait_all_deployments

#=====print svc/pods=====
run kubectl -n "${NS}" get svc -o wide
run kubectl -n "${NS}" get pods -o wide

#=====start port forwarding and verify=====
start_port_forward

# verify if the model is visible in the router
log "verify if the model is visible in the router:"
run curl -s "${ENDPOINT}/v1/models" | sed -e 's/{"object":"list","data":/models=/' -e 's/}]}/}]\\n/'

#=====run benchmark=====
log "run benchmark: ${BENCH_NAME} | model: ${DEPLOYMENT_MODEL_ID}"
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
log "benchmark completed, results directory: benchmarks/results"

# if you want to delete the deployment at the end of the script, pass CLEANUP=1
# CLEANUP=1 ./run.sh
