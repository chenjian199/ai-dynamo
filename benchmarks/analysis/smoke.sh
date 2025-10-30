#!/bin/bash
curl -s http://127.0.0.1:8003/health 

curl -s http://127.0.0.1:8003/v1/models | jq '.'

curl -s -X POST http://127.0.0.1:8003/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/home/bedicloud/models/deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }' | jq '.choices[0].message.content'

