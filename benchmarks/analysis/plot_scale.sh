cd /home/bedicloud/dynamo-main &&  \
    python benchmarks/analysis/plot_slo_scaling_throughput.py  \
    --csv-agg benchmarks/results/sglang_summary/distserve_metrics_20251103_082910.csv \
    --csv-disagg benchmarks/results/sglang_summary/distserve_metrics_disagg_20251103_115241.csv \
    --output benchmarks/results/sglang_summary/plot_slo_scaling_throughput_compare.png