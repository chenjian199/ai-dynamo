cd /workspace

python3 -m benchmarks.utils.benchmark \
   --benchmark-name disagg3p1d \
   --endpoint-url http://localhost:8005 \
   --model "/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B" \
   --output-dir ./benchmarks/results

python3 -m benchmarks.utils.plot \
    --data-dir ./benchmarks/results \
    --benchmark-name disagg3p1d