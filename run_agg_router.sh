export DEPLOYMENT_MODEL_ID=DeepSeek-R1-Distill-Qwen-7B
export TOKENIZER_PATH=/home/bedicloud/models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B

export CONCURRENCIES="256"
#export export CONCURRENCIES="1,2,5,10,25,50,100,250,500"
python3 -m benchmarks.utils.benchmark \
    --benchmark-name agg_router \
    --endpoint-url http://localhost:8003 \
    --model "DeepSeek-R1-Distill-Qwen-7B" \
    --isl 512 \
    --osl 240
