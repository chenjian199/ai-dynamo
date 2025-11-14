#!/usr/bin/env bash
iso=( 2000 2000 5000  10000 20000 20000  2000 2000 2000 10000)
osl=( 256 512 512 1000 1000 2000 2000 4000 10000 20000)
concurrency=(1 10 50 100 150 200 250 300 350 400 450)
duration=120

# 遍历 iso/osl 的索引，成对使用
for i in "${!iso[@]}"; do
    isl_val="${iso[$i]}"
    osl_val="${osl[$i]}"

    python3 cjworkspace/analysis/genai_perf/stress_test.py \
        --isl "${isl_val}" \
        --osl "${osl_val}" \
        --concurrency "${concurrency[@]}" \
        --duration "${duration}" \
        --service-url http://127.0.0.1:8005 \
        --model /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B \
        --tokenizer /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B
done