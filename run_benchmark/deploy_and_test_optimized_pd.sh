#!/usr/bin/env bash

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# 配置
NAMESPACE="dynamo-kubernetes"
DEPLOYMENT_NAME="vllm-disagg-optimized-prefix"
YAML_FILE="/home/bedicloud/dynamo-main/components/backends/vllm/deploy/disagg_optimized_prefix.yaml"
LOCAL_PORT="8003"
SERVICE_PORT="8000"

# 清理函数
cleanup() {
    log_info "Cleaning up resources..."
    
    # 停止端口转发
    pkill -f "kubectl.*port-forward.*${LOCAL_PORT}" || true
    
    # 删除部署
    if [[ "${CLEANUP:-1}" == "1" ]]; then
        log_info "Deleting deployment: ${DEPLOYMENT_NAME}"
        kubectl delete dynamographdeployment "${DEPLOYMENT_NAME}" -n "${NAMESPACE}" --ignore-not-found=true || true
    fi
    
    log_success "Cleanup completed"
}

# 设置退出时清理
trap cleanup EXIT

# 检查依赖
check_dependencies() {
    log_info "Checking dependencies..."
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed"
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        log_error "python3 is not installed"
        exit 1
    fi
    
    if [[ ! -f "${YAML_FILE}" ]]; then
        log_error "YAML file not found: ${YAML_FILE}"
        exit 1
    fi
    
    log_success "All dependencies are available"
}

# 部署优化配置
deploy_optimized_config() {
    log_info "Deploying optimized PD configuration..."
    
    # 应用YAML配置
    kubectl apply -f "${YAML_FILE}" -n "${NAMESPACE}"
    log_success "Applied YAML configuration"
    
    # 等待部署就绪
    log_info "Waiting for deployment to be ready..."
    kubectl wait --for=condition=ready pod -l "app=${DEPLOYMENT_NAME}" -n "${NAMESPACE}" --timeout=300s
    log_success "Deployment is ready"
}

# 启动端口转发
start_port_forward() {
    log_info "Starting port forwarding..."
    
    # 停止现有的端口转发
    pkill -f "kubectl.*port-forward.*${LOCAL_PORT}" || true
    sleep 2
    
    # 启动新的端口转发
    nohup kubectl port-forward "svc/${DEPLOYMENT_NAME}-frontend" "${LOCAL_PORT}:${SERVICE_PORT}" -n "${NAMESPACE}" > /tmp/port-forward-${DEPLOYMENT_NAME}.log 2>&1 &
    sleep 5
    
    # 验证端口转发
    if curl -s "http://127.0.0.1:${LOCAL_PORT}/health" > /dev/null 2>&1; then
        log_success "Port forwarding is working"
    else
        log_warning "Port forwarding may not be ready yet, continuing..."
    fi
}

# 运行基准测试
run_benchmark() {
    log_info "Running benchmark tests..."
    
    # 检查测试脚本是否存在
    if [[ -f "run_benchmark/test_with_prefix_cache.py" ]]; then
        log_info "Running prefix cache benchmark..."
        python3 run_benchmark/test_with_prefix_cache.py
    else
        log_warning "Prefix cache test script not found, running standard benchmark..."
        # 运行标准基准测试
        python3 -c "
import subprocess
import sys

# 简单的基准测试
concurrencies = [1, 10, 50, 100, 200, 300, 400, 500]
for concurrency in concurrencies:
    print(f'Testing concurrency: {concurrency}')
    try:
        result = subprocess.run([
            'genai-perf', 'profile',
            '--model', 'DeepSeek-R1-Distill-Qwen-7B',
            '--tokenizer', '/home/bedicloud/models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B',
            '--endpoint-type', 'chat',
            '--endpoint', 'v1/chat/completions',
            '--streaming',
            '--url', 'http://127.0.0.1:8003',
            '--concurrency', str(concurrency),
            '--synthetic-input-tokens-mean', '2000',
            '--synthetic-input-tokens-stddev', '500',
            '--synthetic-output-tokens-mean', '256',
            '--synthetic-output-tokens-stddev', '64',
            '--duration', '60'
        ], capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print(f'  Concurrency {concurrency}: SUCCESS')
        else:
            print(f'  Concurrency {concurrency}: FAILED')
            print(f'  Error: {result.stderr[:200]}')
    except subprocess.TimeoutExpired:
        print(f'  Concurrency {concurrency}: TIMEOUT')
    except Exception as e:
        print(f'  Concurrency {concurrency}: ERROR - {e}')
"
    fi
    
    log_success "Benchmark tests completed"
}

# 显示性能指标
show_performance_metrics() {
    log_info "Collecting performance metrics..."
    
    # 获取Pod状态
    echo "=== Pod Status ==="
    kubectl get pods -l "app=${DEPLOYMENT_NAME}" -n "${NAMESPACE}" -o wide
    
    echo -e "\n=== Resource Usage ==="
    kubectl top pods -l "app=${DEPLOYMENT_NAME}" -n "${NAMESPACE}" --containers || true
    
    echo -e "\n=== Service Status ==="
    kubectl get svc -l "app=${DEPLOYMENT_NAME}" -n "${NAMESPACE}"
    
    echo -e "\n=== Deployment Status ==="
    kubectl get deployment -l "app=${DEPLOYMENT_NAME}" -n "${NAMESPACE}"
}

# 主函数
main() {
    log_info "Starting optimized PD deployment and testing..."
    echo "=========================================="
    
    # 检查依赖
    check_dependencies
    
    # 部署配置
    deploy_optimized_config
    
    # 启动端口转发
    start_port_forward
    
    # 显示性能指标
    show_performance_metrics
    
    # 运行基准测试
    run_benchmark
    
    log_success "Optimized PD deployment and testing completed!"
    echo "=========================================="
    
    # 显示结果目录
    if [[ -d "benchmarks/results" ]]; then
        echo "Results saved to: benchmarks/results/"
        ls -la benchmarks/results/ | tail -5
    fi
}

# 显示帮助信息
show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  --no-cleanup   Don't cleanup resources on exit"
    echo ""
    echo "Environment variables:"
    echo "  CLEANUP=0      Don't cleanup resources on exit"
    echo ""
    echo "This script will:"
    echo "  1. Deploy the optimized PD configuration"
    echo "  2. Start port forwarding"
    echo "  3. Run benchmark tests"
    echo "  4. Show performance metrics"
    echo "  5. Cleanup resources (unless --no-cleanup is specified)"
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        --no-cleanup)
            export CLEANUP=0
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# 运行主函数
main "$@"
