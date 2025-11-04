#!/bin/bash
# 一键生成所有对比图表脚本
# 用法: ./generate_all_plots.sh

set -e  # 遇到错误立即退出

# 配置变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RESULTS_DIR="$PROJECT_ROOT/benchmarks/results/sglang_summary"

# CSV文件路径（自动查找最新的文件）
AGG_CSV=$(ls -t "$RESULTS_DIR"/distserve_metrics_agg_*.csv 2>/dev/null | head -1)
DISAGG_CSV=$(ls -t "$RESULTS_DIR"/distserve_metrics_disagg_*.csv 2>/dev/null | head -1)

# 检查CSV文件是否存在
if [ ! -f "$AGG_CSV" ]; then
    echo "❌ Error: Aggregated CSV file not found: $AGG_CSV"
    exit 1
fi

if [ ! -f "$DISAGG_CSV" ]; then
    echo "❌ Error: Disaggregated CSV file not found: $DISAGG_CSV"
    exit 1
fi

echo "📊 Starting to generate all comparison plots..."
echo "   Aggregated CSV: $AGG_CSV"
echo "   Disaggregated CSV: $DISAGG_CSV"
echo ""

cd "$PROJECT_ROOT"

# # 1. ITL vs Throughput 对比图
# echo "📈 Generating ITL vs Throughput comparison plot..."
# python benchmarks/analysis/plot_itl_throughput.py \
#     --csv-agg "$AGG_CSV" \
#     --csv-disagg "$DISAGG_CSV" \
#     --output "$RESULTS_DIR/plot_itl_throughput_compare.png"
# echo "✅ ITL vs Throughput plot saved"
# echo ""

# # 2. Concurrency vs Throughput 对比图
# echo "📈 Generating Concurrency vs Throughput comparison plot..."
# python benchmarks/analysis/plot_concurrency_throughput.py \
#     --csv-agg "$AGG_CSV" \
#     --csv-disagg "$DISAGG_CSV" \
#     --output "$RESULTS_DIR/plot_concurrency_throughput_compare.png"
# echo "✅ Concurrency vs Throughput plot saved"
# echo ""

# 2.5. TTFT vs Concurrency 对比图
echo "📈 Generating TTFT vs Concurrency comparison plot..."
python benchmarks/analysis/plot_ttft_concurrency.py \
    --csv-agg "$AGG_CSV" \
    --csv-disagg "$DISAGG_CSV" \
    --output "$RESULTS_DIR/plot_ttft_concurrency_compare.png"
echo "✅ TTFT vs Concurrency plot saved"
echo ""

# 2.6. ITL vs Concurrency 对比图
echo "📈 Generating ITL vs Concurrency comparison plot..."
python benchmarks/analysis/plot_itl_concurrency.py \
    --csv-agg "$AGG_CSV" \
    --csv-disagg "$DISAGG_CSV" \
    --output "$RESULTS_DIR/plot_itl_concurrency_compare.png"
echo "✅ ITL vs Concurrency plot saved"
echo ""

# # 3. SLO Scaling - Throughput 对比图
# echo "📈 Generating SLO Scaling (Throughput) comparison plot..."
# python benchmarks/analysis/plot_slo_scaling_throughput.py \
#     --csv-agg "$AGG_CSV" \
#     --csv-disagg "$DISAGG_CSV" \
#     --output "$RESULTS_DIR/plot_slo_scaling_throughput_compare.png" \
#     --y-axis throughput \
#     --scale-min 0.0 \
#     --scale-max 2.0 \
#     --scale-step 0.05
# echo "✅ SLO Scaling (Throughput) plot saved"
# echo ""

# 4. SLO Scaling - Concurrency 对比图
echo "📈 Generating SLO Scaling (Concurrency) comparison plot..."
python benchmarks/analysis/plot_slo_scaling_throughput.py \
    --csv-agg "$AGG_CSV" \
    --csv-disagg "$DISAGG_CSV" \
    --output "$RESULTS_DIR/plot_slo_scaling_concurrency_compare.png" \
    --y-axis concurrency \
    --scale-min 0.0 \
    --scale-max 5.0 \
    --scale-step 0.1
echo "✅ SLO Scaling (Concurrency) plot saved"
echo ""

echo "🎉 All plots generated successfully!"
echo "   Output directory: $RESULTS_DIR"
echo ""
echo "Generated files:"
ls -lh "$RESULTS_DIR"/plot_*_compare.png 2>/dev/null || echo "   (No comparison plots found)"

