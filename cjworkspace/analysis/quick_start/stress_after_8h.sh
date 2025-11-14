#!/usr/bin/env bash
# 用法:
#   ./run_after_8h.sh "your_long_running_command" "your_next_command"
# 例子:
#   ./run_after_8h.sh "python job.py" "bash deploy.sh"
#   ./run_after_8h.sh "bash components/backends/sglang/launch/disagg.sh" "bash benchmarks/analysis/continue_stress.sh"

set -euo pipefail

# if [[ $# -lt 2 ]]; then
#   echo "Usage: $0 \"your_cmd\" \"next_cmd\" [delay]"
#   echo "Example: $0 \"python job.py\" \"bash deploy.sh\" 8h"
#   exit 1
# fi

YOUR_CMD="${1:-bash cjworkspace/analysis/quick_start/continue_stress_disagg.sh}"
NEXT_CMD="${2:-bash cjworkspace/analysis/quick_start/continue_stress_agg.sh}"
DELAY="${3:-26h}"       # 支持 8h、8h30m、510m、30600s 等

# 启动前一个命令到后台运行（不阻塞）
nohup bash -lc "$YOUR_CMD"  2>&1 &
PID=$!
disown $PID 2>/dev/null || true

echo "[INFO] started YOUR_CMD (pid=$PID). Will run NEXT_CMD after $DELAY."

# 到达延时后，尝试优雅退出并强杀兜底，然后执行 NEXT_CMD
(
  sleep "$DELAY"

  # 优雅结束
  if kill -0 "$PID" 2>/dev/null; then
    kill -TERM "$PID" 2>/dev/null || true
    sleep 600
  fi

  # 强杀兜底
  if kill -0 "$PID" 2>/dev/null; then
    kill -KILL "$PID" 2>/dev/null || true
    sleep 600
  fi

  echo "[INFO] running NEXT_CMD after $DELAY..."
  nohup bash -lc "$NEXT_CMD" > /dev/null 2>&1 &
) > /dev/null 2>&1 &
SCHEDULER_PID=$!
disown $SCHEDULER_PID 2>/dev/null || true

echo "[INFO] scheduler detached. Logs will follow the processes' own outputs."