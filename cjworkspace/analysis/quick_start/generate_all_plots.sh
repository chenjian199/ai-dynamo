#!/bin/bash
# 一键生成所有对比图表脚本
# 用法: 
#   1. agg vs disagg 对比: ./generate_all_plots.sh [--isl N] [--osl N] [--agg-deploy NAME] [--disagg-deploy NAME] [--base-dir DIR]
#   2. agg vs agg 对比: ./generate_all_plots.sh --isl N --osl N --agg-deploy-1 NAME1 --agg-deploy-2 NAME2 [--base-dir DIR]
#   3. disagg vs disagg 对比: ./generate_all_plots.sh --isl N --osl N --disagg-deploy-1 NAME1 --disagg-deploy-2 NAME2 [--base-dir DIR]
# 示例:
#   ./generate_all_plots.sh --isl 5000 --osl 100 --agg-deploy 4a --disagg-deploy 3p1d_router
#   ./generate_all_plots.sh --isl 5000 --osl 100 --agg-deploy-1 1a --agg-deploy-2 1a_router
#   ./generate_all_plots.sh --isl 5000 --osl 100 --disagg-deploy-1 3p1d --disagg-deploy-2 3p1d_newrouter

set -e  # 遇到错误立即退出

# 配置变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 从 cjworkspace/analysis/quick_start 往上三级到项目根目录
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RESULTS_DIR="$PROJECT_ROOT/cjworkspace/results/sglang"
PLOT_DIR="$PROJECT_ROOT/cjworkspace/analysis/plot"
EXTRACT_SCRIPT="$PLOT_DIR/extract_distserve_metrics.py"

# 解析可选参数
FILTER_ISL=""
FILTER_OSL=""
AGG_DEPLOY=""
DISAGG_DEPLOY=""
AGG_DEPLOY_1=""
AGG_DEPLOY_2=""
DISAGG_DEPLOY_1=""
DISAGG_DEPLOY_2=""
BASE_DIR=""
SKIP_EXTRACT=false
COMPARE_MODE="agg_vs_disagg"  # 默认模式：agg vs disagg

while [[ $# -gt 0 ]]; do
    case "$1" in
        --isl)
            FILTER_ISL="$2"; shift 2;;
        --osl)
            FILTER_OSL="$2"; shift 2;;
        --agg-deploy)
            AGG_DEPLOY="$2"; shift 2;;
        --disagg-deploy)
            DISAGG_DEPLOY="$2"; shift 2;;
        --agg-deploy-1)
            AGG_DEPLOY_1="$2"; COMPARE_MODE="agg_vs_agg"; shift 2;;
        --agg-deploy-2)
            AGG_DEPLOY_2="$2"; COMPARE_MODE="agg_vs_agg"; shift 2;;
        --disagg-deploy-1)
            DISAGG_DEPLOY_1="$2"; COMPARE_MODE="disagg_vs_disagg"; shift 2;;
        --disagg-deploy-2)
            DISAGG_DEPLOY_2="$2"; COMPARE_MODE="disagg_vs_disagg"; shift 2;;
        --base-dir)
            BASE_DIR="$2"; shift 2;;
        --skip-extract|--no-extract)
            SKIP_EXTRACT=true; shift;;
        -h|--help)
            echo "Usage:"
            echo "  Agg vs Disagg: $0 [--isl N] [--osl N] [--agg-deploy NAME] [--disagg-deploy NAME] [--base-dir DIR] [--skip-extract]"
            echo "  Agg vs Agg: $0 --isl N --osl N --agg-deploy-1 NAME1 --agg-deploy-2 NAME2 [--base-dir DIR] [--skip-extract]"
            echo "  Disagg vs Disagg: $0 --isl N --osl N --disagg-deploy-1 NAME1 --disagg-deploy-2 NAME2 [--base-dir DIR] [--skip-extract]"
            echo ""
            echo "Options:"
            echo "  --skip-extract    Skip data extraction step, use existing CSV files"
            exit 0;;
        *)
            echo "Unknown option: $1"; exit 1;;
    esac
done

# 检查对比模式参数
if [ "$COMPARE_MODE" = "disagg_vs_disagg" ]; then
    if [ -z "$DISAGG_DEPLOY_1" ] || [ -z "$DISAGG_DEPLOY_2" ]; then
        echo "❌ Error: --disagg-deploy-1 and --disagg-deploy-2 must both be specified for disagg comparison mode"
        exit 1
    fi
    if [ -z "$FILTER_ISL" ] || [ -z "$FILTER_OSL" ]; then
        echo "❌ Error: --isl and --osl must be specified for disagg comparison mode"
        exit 1
    fi
elif [ "$COMPARE_MODE" = "agg_vs_agg" ]; then
    if [ -z "$AGG_DEPLOY_1" ] || [ -z "$AGG_DEPLOY_2" ]; then
        echo "❌ Error: --agg-deploy-1 and --agg-deploy-2 must both be specified for agg comparison mode"
        exit 1
    fi
    if [ -z "$FILTER_ISL" ] || [ -z "$FILTER_OSL" ]; then
        echo "❌ Error: --isl and --osl must be specified for agg comparison mode"
        exit 1
    fi
fi

# 根据模式创建子目录
if [ "$COMPARE_MODE" = "disagg_vs_disagg" ]; then
    # Disagg对比模式：sglang_summary_{部署1}_{部署2}_isl{ISL}_osl{OSL}/
    SUBDIR="sglang_summary_${DISAGG_DEPLOY_1}_${DISAGG_DEPLOY_2}_isl${FILTER_ISL}_osl${FILTER_OSL}"
elif [ "$COMPARE_MODE" = "agg_vs_agg" ]; then
    # Agg对比模式：sglang_summary_{部署1}_{部署2}_isl{ISL}_osl{OSL}/
    SUBDIR="sglang_summary_${AGG_DEPLOY_1}_${AGG_DEPLOY_2}_isl${FILTER_ISL}_osl${FILTER_OSL}"
else
    # Agg vs Disagg模式：sglang_summary_{agg部署}_{disagg部署}_isl{ISL}_osl{OSL}/
    # 如果没有指定部署名，使用默认值
    AGG_NAME="${AGG_DEPLOY:-agg}"
    DISAGG_NAME="${DISAGG_DEPLOY:-disagg}"
    if [ -n "$FILTER_ISL" ] && [ -n "$FILTER_OSL" ]; then
        SUBDIR="sglang_summary_${AGG_NAME}_${DISAGG_NAME}_isl${FILTER_ISL}_osl${FILTER_OSL}"
    else
        SUBDIR="sglang_summary_${AGG_NAME}_${DISAGG_NAME}"
    fi
fi

# 创建子目录
OUTPUT_DIR="$RESULTS_DIR/$SUBDIR"
mkdir -p "$OUTPUT_DIR"

# 确保输出目录存在
mkdir -p "$RESULTS_DIR"

# 步骤0: 提取数据成表格（如果未跳过）
if [ "$SKIP_EXTRACT" = false ]; then
    echo "📋 [Step 0] Extracting metrics to CSV tables..."
    echo "   Output directory: $OUTPUT_DIR"
    echo "   Compare mode: $COMPARE_MODE"
    echo ""

    if [ "$COMPARE_MODE" = "disagg_vs_disagg" ]; then
    # Disagg对比模式：提取两个disagg部署的数据
    echo "📊 [0.1/2] Extracting disagg deployment 1: $DISAGG_DEPLOY_1..."
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    CSV1_NAME="distserve_metrics_disagg_${DISAGG_DEPLOY_1}_${TIMESTAMP}.csv"
    python3 "$EXTRACT_SCRIPT" \
        --mode disagg \
        --output-dir "$OUTPUT_DIR" \
        --output-csv "$CSV1_NAME" \
        ${BASE_DIR:+--base-dir "$BASE_DIR"} \
        ${FILTER_ISL:+--filter-isl "$FILTER_ISL"} \
        ${FILTER_OSL:+--filter-osl "$FILTER_OSL"} \
        --filter-deployment "$DISAGG_DEPLOY_1" \
        || {
        echo "⚠️  Warning: Failed to extract disagg deployment 1. Trying to find existing CSV..."
    }
    
    echo ""
    echo "📊 [0.2/2] Extracting disagg deployment 2: $DISAGG_DEPLOY_2..."
    CSV2_NAME="distserve_metrics_disagg_${DISAGG_DEPLOY_2}_${TIMESTAMP}.csv"
    python3 "$EXTRACT_SCRIPT" \
        --mode disagg \
        --output-dir "$OUTPUT_DIR" \
        --output-csv "$CSV2_NAME" \
        ${BASE_DIR:+--base-dir "$BASE_DIR"} \
        ${FILTER_ISL:+--filter-isl "$FILTER_ISL"} \
        ${FILTER_OSL:+--filter-osl "$FILTER_OSL"} \
        --filter-deployment "$DISAGG_DEPLOY_2" \
        || {
        echo "⚠️  Warning: Failed to extract disagg deployment 2. Trying to find existing CSV..."
    }
    
    echo ""
    
    # 查找生成的CSV文件（按时间戳匹配，或找最新的匹配部署名的）
    AGG_CSV=$(ls -t "$OUTPUT_DIR"/distserve_metrics_disagg_${DISAGG_DEPLOY_1}_*.csv 2>/dev/null | head -1)
    DISAGG_CSV=$(ls -t "$OUTPUT_DIR"/distserve_metrics_disagg_${DISAGG_DEPLOY_2}_*.csv 2>/dev/null | head -1)
    
    # 如果找不到，尝试按时间戳匹配
    if [ -z "$AGG_CSV" ]; then
        AGG_CSV="$OUTPUT_DIR/$CSV1_NAME"
    fi
    if [ -z "$DISAGG_CSV" ]; then
        DISAGG_CSV="$OUTPUT_DIR/$CSV2_NAME"
    fi
elif [ "$COMPARE_MODE" = "agg_vs_agg" ]; then
    # Agg对比模式：提取两个agg部署的数据
    echo "📊 [0.1/2] Extracting agg deployment 1: $AGG_DEPLOY_1..."
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    CSV1_NAME="distserve_metrics_agg_${AGG_DEPLOY_1}_${TIMESTAMP}.csv"
    python3 "$EXTRACT_SCRIPT" \
        --mode agg \
        --output-dir "$OUTPUT_DIR" \
        --output-csv "$CSV1_NAME" \
        ${BASE_DIR:+--base-dir "$BASE_DIR"} \
        ${FILTER_ISL:+--filter-isl "$FILTER_ISL"} \
        ${FILTER_OSL:+--filter-osl "$FILTER_OSL"} \
        --filter-deployment "$AGG_DEPLOY_1" \
        || {
        echo "⚠️  Warning: Failed to extract agg deployment 1. Trying to find existing CSV..."
    }
    
    echo ""
    echo "📊 [0.2/2] Extracting agg deployment 2: $AGG_DEPLOY_2..."
    CSV2_NAME="distserve_metrics_agg_${AGG_DEPLOY_2}_${TIMESTAMP}.csv"
    python3 "$EXTRACT_SCRIPT" \
        --mode agg \
        --output-dir "$OUTPUT_DIR" \
        --output-csv "$CSV2_NAME" \
        ${BASE_DIR:+--base-dir "$BASE_DIR"} \
        ${FILTER_ISL:+--filter-isl "$FILTER_ISL"} \
        ${FILTER_OSL:+--filter-osl "$FILTER_OSL"} \
        --filter-deployment "$AGG_DEPLOY_2" \
        || {
        echo "⚠️  Warning: Failed to extract agg deployment 2. Trying to find existing CSV..."
    }
    
    echo ""
    
    # 查找生成的CSV文件（优先使用时间戳匹配，确保精确匹配）
    # 首先尝试使用时间戳匹配
    if [ -f "$OUTPUT_DIR/$CSV1_NAME" ]; then
        AGG_CSV="$OUTPUT_DIR/$CSV1_NAME"
    else
        # 如果时间戳匹配失败，使用精确的部署名匹配（使用basename确保精确匹配）
        AGG_CSV=$(ls -t "$OUTPUT_DIR"/distserve_metrics_agg_*.csv 2>/dev/null | while read f; do
            basename "$f" | grep -qE "^distserve_metrics_agg_${AGG_DEPLOY_1}_[0-9]{8}_[0-9]{6}\.csv$" && echo "$f"
        done | head -1)
    fi
    
    if [ -f "$OUTPUT_DIR/$CSV2_NAME" ]; then
        DISAGG_CSV="$OUTPUT_DIR/$CSV2_NAME"
    else
        # 如果时间戳匹配失败，使用精确的部署名匹配
        DISAGG_CSV=$(ls -t "$OUTPUT_DIR"/distserve_metrics_agg_*.csv 2>/dev/null | while read f; do
            basename "$f" | grep -qE "^distserve_metrics_agg_${AGG_DEPLOY_2}_[0-9]{8}_[0-9]{6}\.csv$" && echo "$f"
        done | head -1)
    fi
else
    # 默认模式：agg vs disagg
    # 提取 agg 数据
    echo "📊 [0.1/2] Extracting aggregated (agg) metrics..."
    python3 "$EXTRACT_SCRIPT" \
        --mode agg \
        --output-dir "$OUTPUT_DIR" \
        ${BASE_DIR:+--base-dir "$BASE_DIR"} \
        ${FILTER_ISL:+--filter-isl "$FILTER_ISL"} \
        ${FILTER_OSL:+--filter-osl "$FILTER_OSL"} \
        ${AGG_DEPLOY:+--filter-deployment "$AGG_DEPLOY"} \
        || {
        echo "⚠️  Warning: Failed to extract aggregated metrics. Continuing with existing CSV files..."
    }
    
    # 提取 disagg 数据
    echo ""
    echo "📊 [0.2/2] Extracting disaggregated (disagg) metrics..."
    python3 "$EXTRACT_SCRIPT" \
        --mode disagg \
        --output-dir "$OUTPUT_DIR" \
        ${BASE_DIR:+--base-dir "$BASE_DIR"} \
        ${FILTER_ISL:+--filter-isl "$FILTER_ISL"} \
        ${FILTER_OSL:+--filter-osl "$FILTER_OSL"} \
        ${DISAGG_DEPLOY:+--filter-deployment "$DISAGG_DEPLOY"} \
        || {
        echo "⚠️  Warning: Failed to extract disaggregated metrics. Continuing with existing CSV files..."
    }
    
    echo ""
    
    # CSV文件路径（自动查找最新的文件）
    AGG_CSV=$(ls -t "$OUTPUT_DIR"/distserve_metrics_agg_*.csv 2>/dev/null | head -1)
    DISAGG_CSV=$(ls -t "$OUTPUT_DIR"/distserve_metrics_disagg_*.csv 2>/dev/null | head -1)
    fi
else
    # 跳过提取，直接查找现有CSV文件
    echo "📋 [Step 0] Skipping data extraction, using existing CSV files..."
    echo "   Output directory: $OUTPUT_DIR"
    echo "   Compare mode: $COMPARE_MODE"
    echo ""
    
    if [ "$COMPARE_MODE" = "disagg_vs_disagg" ]; then
        # 查找两个disagg部署的CSV文件
        AGG_CSV=$(ls -t "$OUTPUT_DIR"/distserve_metrics_disagg_${DISAGG_DEPLOY_1}_*.csv 2>/dev/null | head -1)
        DISAGG_CSV=$(ls -t "$OUTPUT_DIR"/distserve_metrics_disagg_${DISAGG_DEPLOY_2}_*.csv 2>/dev/null | head -1)
    elif [ "$COMPARE_MODE" = "agg_vs_agg" ]; then
        # 查找两个agg部署的CSV文件（使用精确匹配避免1a匹配到1a_router）
        AGG_CSV=$(ls -t "$OUTPUT_DIR"/distserve_metrics_agg_*.csv 2>/dev/null | while read f; do
            basename "$f" | grep -qE "^distserve_metrics_agg_${AGG_DEPLOY_1}_[0-9]{8}_[0-9]{6}\.csv$" && echo "$f"
        done | head -1)
        DISAGG_CSV=$(ls -t "$OUTPUT_DIR"/distserve_metrics_agg_*.csv 2>/dev/null | while read f; do
            basename "$f" | grep -qE "^distserve_metrics_agg_${AGG_DEPLOY_2}_[0-9]{8}_[0-9]{6}\.csv$" && echo "$f"
        done | head -1)
    else
        # 查找agg和disagg的CSV文件
        AGG_CSV=$(ls -t "$OUTPUT_DIR"/distserve_metrics_agg_*.csv 2>/dev/null | head -1)
        DISAGG_CSV=$(ls -t "$OUTPUT_DIR"/distserve_metrics_disagg_*.csv 2>/dev/null | head -1)
    fi
fi

# 检查CSV文件是否存在
if [ ! -f "$AGG_CSV" ]; then
    if [ "$COMPARE_MODE" = "disagg_vs_disagg" ]; then
        echo "❌ Error: CSV file for deployment 1 ($DISAGG_DEPLOY_1) not found in: $OUTPUT_DIR"
    elif [ "$COMPARE_MODE" = "agg_vs_agg" ]; then
        echo "❌ Error: CSV file for deployment 1 ($AGG_DEPLOY_1) not found in: $OUTPUT_DIR"
    else
        echo "❌ Error: Aggregated CSV file not found in: $OUTPUT_DIR"
    fi
    echo "   Please extract metrics first using extract_distserve_metrics.py"
    exit 1
fi

if [ ! -f "$DISAGG_CSV" ]; then
    if [ "$COMPARE_MODE" = "disagg_vs_disagg" ]; then
        echo "❌ Error: CSV file for deployment 2 ($DISAGG_DEPLOY_2) not found in: $OUTPUT_DIR"
    elif [ "$COMPARE_MODE" = "agg_vs_agg" ]; then
        echo "❌ Error: CSV file for deployment 2 ($AGG_DEPLOY_2) not found in: $OUTPUT_DIR"
    else
        echo "❌ Error: Disaggregated CSV file not found in: $OUTPUT_DIR"
    fi
    echo "   Please extract metrics first using extract_distserve_metrics.py"
    exit 1
fi

echo "📊 Starting to generate all comparison plots..."
if [ "$COMPARE_MODE" = "disagg_vs_disagg" ]; then
    echo "   Deployment 1 ($DISAGG_DEPLOY_1) CSV: $AGG_CSV"
    echo "   Deployment 2 ($DISAGG_DEPLOY_2) CSV: $DISAGG_CSV"
elif [ "$COMPARE_MODE" = "agg_vs_agg" ]; then
    echo "   Deployment 1 ($AGG_DEPLOY_1) CSV: $AGG_CSV"
    echo "   Deployment 2 ($AGG_DEPLOY_2) CSV: $DISAGG_CSV"
else
    echo "   Aggregated CSV: $AGG_CSV"
    echo "   Disaggregated CSV: $DISAGG_CSV"
fi
echo "   Output directory: $OUTPUT_DIR"
echo ""

cd "$PROJECT_ROOT"

# 1. TTFT vs Concurrency 对比图 (p90)
echo "📈 [1/5] Generating TTFT (p90) vs Concurrency comparison plot..."
python3 "$PLOT_DIR/plot_ttft_concurrency.py" \
    --csv-agg "$AGG_CSV" \
    --csv-disagg "$DISAGG_CSV" \
    --output "$OUTPUT_DIR/plot_ttft_p90_concurrency_compare.png" \
    --ttft-col time_to_first_token_p90
echo "✅ TTFT (p90) vs Concurrency plot saved"
echo ""

# 2. TTFT vs Concurrency 对比图 (avg)
echo "📈 [2/5] Generating TTFT (avg) vs Concurrency comparison plot..."
python3 "$PLOT_DIR/plot_ttft_concurrency.py" \
    --csv-agg "$AGG_CSV" \
    --csv-disagg "$DISAGG_CSV" \
    --output "$OUTPUT_DIR/plot_ttft_avg_concurrency_compare.png" \
    --ttft-col time_to_first_token_avg
echo "✅ TTFT (avg) vs Concurrency plot saved"
echo ""

# 3. ITL vs Concurrency 对比图 (p90)
echo "📈 [3/5] Generating ITL (p90) vs Concurrency comparison plot..."
python3 "$PLOT_DIR/plot_itl_concurrency.py" \
    --csv-agg "$AGG_CSV" \
    --csv-disagg "$DISAGG_CSV" \
    --output "$OUTPUT_DIR/plot_itl_p90_concurrency_compare.png" \
    --itl-col inter_token_latency_p90
echo "✅ ITL (p90) vs Concurrency plot saved"
echo ""

# 4. ITL vs Concurrency 对比图 (avg)
echo "📈 [4/5] Generating ITL (avg) vs Concurrency comparison plot..."
python3 "$PLOT_DIR/plot_itl_concurrency.py" \
    --csv-agg "$AGG_CSV" \
    --csv-disagg "$DISAGG_CSV" \
    --output "$OUTPUT_DIR/plot_itl_avg_concurrency_compare.png" \
    --itl-col inter_token_latency_avg
echo "✅ ITL (avg) vs Concurrency plot saved"
echo ""

# 5. Concurrency vs Throughput 对比图
echo "📈 [5/6] Generating Concurrency vs Throughput comparison plot..."
python3 "$PLOT_DIR/plot_concurrency_throughput.py" \
    --csv-agg "$AGG_CSV" \
    --csv-disagg "$DISAGG_CSV" \
    --output "$OUTPUT_DIR/plot_concurrency_throughput_compare.png"
echo "✅ Concurrency vs Throughput plot saved"
echo ""

# 6. ITL vs Throughput 对比图
echo "📈 [6/7] Generating ITL vs Throughput comparison plot..."
python3 "$PLOT_DIR/plot_itl_throughput.py" \
    --csv-agg "$AGG_CSV" \
    --csv-disagg "$DISAGG_CSV" \
    --output "$OUTPUT_DIR/plot_itl_throughput_compare.png"
echo "✅ ITL vs Throughput plot saved"
echo ""

# 7. SLO Scaling - Throughput 对比图
echo "📈 [7/8] Generating SLO Scaling (Throughput) comparison plot..."
python3 "$PLOT_DIR/plot_slo_scaling_throughput.py" \
    --csv-agg "$AGG_CSV" \
    --csv-disagg "$DISAGG_CSV" \
    --output "$OUTPUT_DIR/plot_slo_scaling_throughput_compare.png" \
    --y-axis throughput \
    --scale-min 0.0 \
    --scale-max 5.0 \
    --scale-step 0.1
echo "✅ SLO Scaling (Throughput) plot saved"
echo ""

# 8. SLO Scaling - Concurrency 对比图
echo "📈 [8/8] Generating SLO Scaling (Concurrency) comparison plot..."
python3 "$PLOT_DIR/plot_slo_scaling_throughput.py" \
    --csv-agg "$AGG_CSV" \
    --csv-disagg "$DISAGG_CSV" \
    --output "$OUTPUT_DIR/plot_slo_scaling_concurrency_compare.png" \
    --y-axis concurrency \
    --scale-min 0.0 \
    --scale-max 5.0 \
    --scale-step 0.1
echo "✅ SLO Scaling (Concurrency) plot saved"
echo ""

echo "🎉 All plots generated successfully!"
echo "   Output directory: $OUTPUT_DIR"
echo ""
echo "Generated files:"
ls -lh "$OUTPUT_DIR"/plot_*_compare.png 2>/dev/null | awk '{print "   " $9 " (" $5 ")"}' || echo "   (No comparison plots found)"

