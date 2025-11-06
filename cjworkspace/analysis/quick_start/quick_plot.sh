#!/bin/bash
# 快速绘图脚本：对比 disagg 3p1d 和 3p1d_newrouter (ISL=5000, OSL=100)
# 使用 --skip-extract 跳过数据提取，直接使用现有CSV文件

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

./generate_all_plots.sh --isl 5000 --osl 100 --disagg-deploy-1 3p1d --disagg-deploy-2 3p1d_newrouter --skip-extract

