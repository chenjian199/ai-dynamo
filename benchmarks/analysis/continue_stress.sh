iso=(2000 2000 2000 5000 5000 5000 10000 10000 10000 20000)
osl=(512 1000 2000 512 1000 2000 512 1000 2000 512)
concurrency=(1 10 50 100 150 200 250 300 350 400 450)
duration=60

for iso,osl in zip(iso,osl); do
    python3 benchmarks/analysis/stress_test.py \
        --isl $iso \
        --osl $osl \
        --concurrency $concurrency \
        --duration $duration \
        --service-url http://127.0.0.1:8003 \
        --model /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B \
        --tokenizer /home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B
done