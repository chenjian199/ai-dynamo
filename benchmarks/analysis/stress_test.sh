python3 benchmarks/analysis/stress_test.py \
    --concurrency 1 10 50 100 250 300 350 400 450 \
    --duration 120 \
    --isl 2000 \
    --osl 2000 \
    --service-url http://127.0.0.1:8003 \
    --model /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B \
    --tokenizer /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B
