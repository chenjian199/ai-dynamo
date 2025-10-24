#export CONCURRENCIES="256"
export TOKENIZER_PATH="/home/bedicloud/models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B"
export ENDPOINT="http://localhost:8001"
export DEPLOYMENT_MODEL_ID="/shared-models/DeepSeek/DeepSeek-R1-Distill-Qwen-7B"
python3 -m benchmarks.utils.benchmark \
      --benchmark-name sglang-agg \
      --endpoint-url "${ENDPOINT}" \
      --model "${DEPLOYMENT_MODEL_ID}"
