#!/bin/bash
curl -s http://127.0.0.1:8005/health 

curl -s http://127.0.0.1:8005/v1/models | jq '.'

# 同时发送5条请求
for i in {1..5}; do
  curl -s -X POST http://127.0.0.1:8005/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d "{
      \"model\": \"/raid5/models/deepseek-ai/DeepSeek-R1-Distill-Llama-8B\",
      \"messages\": [{\"role\": \"user\", \"content\": \"Hello request $i\"}],
      \"max_tokens\": 50
    }" | jq '.choices[0].message.content' &
done

# 等待所有后台任务完成
wait
echo "All 5 requests completed"

