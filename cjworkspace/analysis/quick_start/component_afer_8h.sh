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

YOUR_CMD="${1:-bash components/backends/sglang/launch/disagg.sh}"
NEXT_CMD="${2:-bash components/backends/sglang/launch/agg.sh}"
DELAY="${3:-24h}"      # 支持 24h、1d、8h30m、510m、30600s 等（默认24小时/1天）

# 创建日志目录
LOG_DIR="${HOME}/.logs/component_after_8h"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
YOUR_CMD_LOG="${LOG_DIR}/your_cmd_${TIMESTAMP}.log"
NEXT_CMD_LOG="${LOG_DIR}/next_cmd_${TIMESTAMP}.log"
SCHEDULER_LOG="${LOG_DIR}/scheduler_${TIMESTAMP}.log"

# 启动前一个命令到后台运行（使用 nohup 确保关闭终端也能继续执行）
nohup bash -lc "$YOUR_CMD" > "$YOUR_CMD_LOG" 2>&1 &
PID=$!

echo "[INFO] started YOUR_CMD (pid=$PID). Will run NEXT_CMD after $DELAY."
echo "[INFO] YOUR_CMD logs: $YOUR_CMD_LOG"

# 脱离当前shell会话，防止终端关闭时被杀死
# nohup 已经处理了大部分情况，但显式 disown 更保险
disown $PID 2>/dev/null || true

# 到达延时后，尝试优雅退出并强杀兜底，然后执行 NEXT_CMD
(
  # 设置独立的进程组，确保不会收到终端的SIGHUP信号
  set -m
  
  sleep "$DELAY"

  # 优雅结束
  if kill -0 "$PID" 2>/dev/null; then
    echo "[INFO] $(date): Attempting graceful termination of PID $PID" >> "$SCHEDULER_LOG"
    kill -TERM "$PID" 2>/dev/null || true
    sleep 600
  fi

  # 强杀兜底
  if kill -0 "$PID" 2>/dev/null; then
    echo "[INFO] $(date): Force killing PID $PID" >> "$SCHEDULER_LOG"
    kill -KILL "$PID" 2>/dev/null || true
    sleep 600
  fi

  echo "[INFO] $(date): running NEXT_CMD after $DELAY..." >> "$SCHEDULER_LOG"
  nohup bash -lc "$NEXT_CMD" > "$NEXT_CMD_LOG" 2>&1 &
) > "$SCHEDULER_LOG" 2>&1 &
SCHEDULER_PID=$!

# 脱离调度器进程，确保它也不会被终端关闭影响
disown $SCHEDULER_PID 2>/dev/null || true

echo "[INFO] scheduler started (pid=$SCHEDULER_PID). Scheduler logs: $SCHEDULER_LOG"
echo "[INFO] NEXT_CMD will log to: $NEXT_CMD_LOG"
echo "[INFO] All processes detached. Safe to close terminal."