#!/bin/bash

# Run the container with the specified image and volume mounts
cd /home/bedicloud/dynamo/container && ./run.sh  \
    --image dynamo:latest-sglang-local-dev \
    --rm FALSE \
    -v /raid5/models/deepseek-ai:/models/deepseek-ai \
    --mount-workspace \
    -it \
    --framework sglang \
    -v $HOME/.cache:/home/ubuntu/.cache \
    -- /bin/bash
