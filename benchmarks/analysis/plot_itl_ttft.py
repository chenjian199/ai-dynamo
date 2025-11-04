#!/usr/bin/env python3
import re
import sys
from pathlib import Path
import matplotlib.pyplot as plt

# 解析结果文件，提取：{concurrency: {"ttft_p90": float_ms, "itl_p90": float_ms}}
def parse_result_file(path: Path) -> dict[int, dict[str, float]]:
    data = {}
    conc = None
    ttft_p90 = None
    itl_p90 = None

    # 表头顺序: Statistic, avg, min, max, p99, p90, p75
    def extract_p90_from_row(line: str) -> float | None:
        # 用竖线分列
        parts = [p.strip() for p in line.split("│")]
        # 期望至少 8 列（两侧也有边框列，加上Statistic列）
        if len(parts) < 8:
            return None
        # 列索引: 0(空), 1(Statistic/标签), 2(avg), 3(min), 4(max), 5(p99), 6(p90), 7(p75), 8(空)
        # 但实际可能是: 0(空), 1(标签), 2(avg), 3(min), 4(max), 5(p99), 6(p90), 7(p75)
        try:
            # 尝试 parts[6] (标准位置)
            if len(parts) >= 7:
                p90_str = parts[6]
                # 处理被截断的数字：移除逗号、省略号等，但保留数字和小数点
                # 先移除所有非数字字符（但保留小数点），如果还有内容就转换
                p90_clean = re.sub(r'[^\d.]', '', p90_str)
                if p90_clean:
                    return float(p90_clean)
                # 如果清理后为空，尝试用正则表达式提取数字模式（包括被截断的）
                # 查找类似 "1,071,5" 或 "10715" 的模式
                match = re.search(r'[\d,]+\.?\d*', p90_str)
                if match:
                    num_str = match.group(0).replace(",", "")
                    if num_str:
                        return float(num_str)
            # 如果列数不够，尝试 parts[5]
            elif len(parts) >= 6:
                p90_str = parts[5]
                p90_clean = re.sub(r'[^\d.]', '', p90_str)
                if p90_clean:
                    return float(p90_clean)
                match = re.search(r'[\d,]+\.?\d*', p90_str)
                if match:
                    num_str = match.group(0).replace(",", "")
                    if num_str:
                        return float(num_str)
            return None
        except (ValueError, IndexError):
            return None

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        
    i = 0
    in_table = False
    table_header_passed = False
    
    while i < len(lines):
        line = lines[i].rstrip("\n")

        # 捕获并发度
        m = re.search(r"DECODE TEST RESULTS - Concurrency:\s*(\d+)", line)
        if m:
            # 如果上一个块已经有数据但尚未落盘，落盘（即使只有部分数据也保存）
            if conc is not None and (ttft_p90 is not None or itl_p90 is not None):
                data[conc] = {"ttft_p90": ttft_p90, "itl_p90": itl_p90}
            conc = int(m.group(1))
            ttft_p90 = None
            itl_p90 = None
            in_table = False
            table_header_passed = False
            i += 1
            continue
        
        # 检测表格开始（支持Statistic被截断的情况，也支持只有表格边框的情况）
        # 如果遇到包含表格边框字符且有avg/min/max/p90等列标题的行，也认为是表格开始
        if (("Statistic" in line or "Statist" in line or "avg" in line) and 
            ("┃" in line or "┡" in line or "│" in line)):
            in_table = True
            table_header_passed = False
            i += 1
            continue
        
        # 如果遇到表格边框行（┡开头的分隔线），且下一行有数据，也认为是表格开始
        if ("┡" in line or ("━" in line and "┃" in line)) and not in_table:
            # 检查接下来的几行是否有数据行
            if i + 1 < len(lines):
                next_line = lines[i+1].rstrip("\n")
                if "│" in next_line and ("Time To" in next_line or "Inter" in next_line or 
                                         any(c.isdigit() for c in next_line)):
                    in_table = True
                    table_header_passed = False
                    i += 1
                    continue
        
        # 跳过表头分隔线
        if in_table and ("┡" in line or ("━" in line and "┃" not in line and "│" not in line)):
            i += 1
            continue
        
        if not in_table:
            i += 1
            continue
        
        # 在表格中解析数据行
        if "│" in line and "Statistic" not in line:
            if not table_header_passed:
                table_header_passed = True
            
            # 检查是否是数据行（包含数字）
            parts = line.split("│")
            has_number = False
            for part in parts:
                part_clean = part.strip().replace(",", "")
                # 检查是否包含数字（包括被截断的数字，如包含省略号的）
                if part_clean:
                    # 移除省略号等非数字字符后再检查
                    part_num_only = part_clean.replace("…", "").replace(".", "")
                    if part_num_only and part_num_only.isdigit():
                        has_number = True
                        break
                    # 也使用正则表达式检查是否有数字模式
                    if re.search(r'\d', part_clean):
                        has_number = True
                        break
            
            if has_number:
                # Time To First Token - 可能是多行，但数据在第一行
                if "Time To" in line:
                    # 检查是否包含 "First" 或在后续行中有 "First"
                    is_ttft = "First" in line
                    if not is_ttft:
                        # 检查接下来的几行（最多3行）是否有 "First"
                        for offset in range(1, 4):
                            if i + offset < len(lines):
                                next_line = lines[i + offset].rstrip("\n")
                                if "First" in next_line:
                                    is_ttft = True
                                    break
                                # 如果遇到下一个数据行（包含数字的Time To行），说明这是Second Token，停止检查
                                if "Time To" in next_line and "│" in next_line:
                                    parts_next = next_line.split("│")
                                    if any(p.strip().replace(",", "").replace(".", "").isdigit() 
                                           for p in parts_next if p.strip()):
                                        break
                    
                    if is_ttft:
                        val = extract_p90_from_row(line)
                        if val is not None:
                            ttft_p90 = val

                # Inter Token Latency - 可能是多行，但数据在第一行
                elif "Inter" in line:
                    is_itl = False
                    # 检查后续行是否有 "Token" 和 "Latency"
                    if i + 2 < len(lines):
                        next1 = lines[i+1].rstrip("\n")
                        next2 = lines[i+2].rstrip("\n")
                        if "Token" in next1 and "Latency" in next2:
                            is_itl = True
                    elif i + 1 < len(lines):
                        next1 = lines[i+1].rstrip("\n")
                        if "Token" in next1 and "Latency" in next1:
                            is_itl = True
                    # 或者当前行包含完整信息
                    if "Token" in line and "Latency" in line:
                        is_itl = True
                    
                    if is_itl:
                        val = extract_p90_from_row(line)
                        if val is not None:
                            itl_p90 = val
            
            # 表格结束
            if "└" in line:
                in_table = False
        
        i += 1
    
    # 文件结束时落盘最后一个块（即使只有部分数据也保存）
    if conc is not None and (ttft_p90 is not None or itl_p90 is not None):
        data[conc] = {"ttft_p90": ttft_p90, "itl_p90": itl_p90}

    return data


def extract_isl_osl_from_filename(filename: Path) -> tuple[None, None] | tuple[int, int]:
    """从文件名中提取输入输出长度（格式：*_isl2000_osl512_* 或 isl2000_osl512）"""
    filename_str = filename.stem  # 不含扩展名的文件名
    
    # 匹配 isl{数字}_osl{数字} 格式
    pattern = r'isl(\d+)[_\-]osl(\d+)'
    match = re.search(pattern, filename_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    
    # 尝试匹配 osl{数字}_isl{数字} 格式
    pattern = r'osl(\d+)[_\-]isl(\d+)'
    match = re.search(pattern, filename_str)
    if match:
        return int(match.group(2)), int(match.group(1))
    
    return None, None

def plot_dual_bars(agg_data: dict[int, dict[str, float]],
                   disagg_data: dict[int, dict[str, float]],
                   title: str,
                   out_path: Path,
                   input_len: int | None = None,
                   output_len: int | None = None):
    # 并发度集合（交集），只绘制两个文件都存在的并发度，并打印各自检测到的并发度，便于排查缺失
    conc_agg = sorted(agg_data.keys())
    conc_dis = sorted(disagg_data.keys())
    print(f"agg conc detected: {conc_agg}")
    print(f"disagg conc detected: {conc_dis}")
    all_conc = sorted(set(conc_agg) & set(conc_dis))
    if not all_conc:
        print("No common concurrency levels found in both files.")
        print(f"Missing in agg: {set(conc_dis) - set(conc_agg)}")
        print(f"Missing in disagg: {set(conc_agg) - set(conc_dis)}")
        return

    # 组装数据
    # 对每个并发度，可能某个文件缺失该并发度或缺某项指标：用 None 表示缺失，绘图时跳过
    agg_itl = [agg_data.get(c, {}).get("itl_p90") for c in all_conc]
    dis_itl = [disagg_data.get(c, {}).get("itl_p90") for c in all_conc]
    agg_ttft = [agg_data.get(c, {}).get("ttft_p90") for c in all_conc]
    dis_ttft = [disagg_data.get(c, {}).get("ttft_p90") for c in all_conc]

    # 上下两个坐标轴：上(ITL)、下(TTFT，向下显示)
    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                                         gridspec_kw={"height_ratios": [2, 2]})

    x = list(range(len(all_conc)))
    # 两根柱紧密拼接：中心间距=柱宽，边缘无空隙
    width = 0.2  # 单柱宽度

    # 顶部：ITL（各自独立的 y 轴范围）
    # 分别绘制，跳过 None
    for i, v in enumerate(agg_itl):
        if v is not None:
            ax_top.bar(i - width/2, v, width=width, color="#1f77b4", alpha=0.9, label="agg ITL p90 (ms)" if i == 0 else None)
    for i, v in enumerate(dis_itl):
        if v is not None:
            ax_top.bar(i + width/2, v, width=width, color="#ff7f0e", alpha=0.9, label="disagg ITL p90 (ms)" if i == 0 else None)
    max_itl_vals = [v for v in (agg_itl + dis_itl) if v is not None]
    max_itl = max(max_itl_vals) if max_itl_vals else 0.0
    ax_top.set_ylabel("ITL p90 (ms)")
    ax_top.set_title(title)
    if max_itl > 0:
        ax_top.set_ylim(0, max_itl * 1.15)
    ax_top.grid(axis='y', linestyle='--', alpha=0.2)

    # 底部：TTFT（正值绘制，向下显示）
    for i, v in enumerate(agg_ttft):
        if v is not None:
            ax_bot.bar(i - width/2, v, width=width, color="#1f77b4", alpha=0.45, label="agg TTFT p90 (ms)" if i == 0 else None)
    for i, v in enumerate(dis_ttft):
        if v is not None:
            ax_bot.bar(i + width/2, v, width=width, color="#ff7f0e", alpha=0.45, label="disagg TTFT p90 (ms)" if i == 0 else None)
    max_ttft_vals = [v for v in (agg_ttft + dis_ttft) if v is not None]
    max_ttft = max(max_ttft_vals) if max_ttft_vals else 0.0
    ax_bot.set_ylabel("TTFT p90 (ms)")
    # 渐变坐标：小值线性，大值对数，保持小值可见
    if max_ttft > 0:
        ax_bot.set_yscale('symlog', linthresh=max(1.0, max_ttft * 0.02))
        ax_bot.set_ylim(0, max_ttft * 1.15)
    ax_bot.invert_yaxis()  # 向下
    ax_bot.axhline(0, color="black", linewidth=1)
    ax_bot.grid(axis='y', linestyle='--', alpha=0.2)

    # X 轴（并发度）
    ax_bot.set_xticks(x)
    ax_bot.set_xticklabels([str(c) for c in all_conc])
    ax_bot.set_xlabel("Concurrency")

    # 合并图例（两个坐标轴）
    handles_t, labels_t = ax_top.get_legend_handles_labels()
    handles_b, labels_b = ax_bot.get_legend_handles_labels()
    handles = handles_t + handles_b
    labels = labels_t + labels_b
    uniq = {}
    for h, l in zip(handles, labels):
        if l not in uniq:
            uniq[l] = h
    ax_top.legend(uniq.values(), uniq.keys(), ncol=2, fontsize=9, loc="upper right")

    # 在图表下方添加输入输出长度标注
    if input_len is not None and output_len is not None:
        length_text = f"Input Length: {input_len:,}, Output Length: {output_len:,}"
    else:
        length_text = "Input/Output Length: N/A"
    fig.text(0.5, 0.02, length_text, 
             ha='center', fontsize=10, style='italic')
    
    fig.tight_layout(rect=[0, 0.04, 1, 1])  # 为底部标注留出空间
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"Saved figure to: {out_path}")


def disagg_sign(v: float) -> float:
    # Y 轴向下显示，取负值
    return -float(v)


def main():
    if len(sys.argv) < 3:
        print("Usage: python plot_p90_itl_ttft.py <agg_file> <disagg_file> [output_png]")
        print("Example:")
        print("  python plot_p90_itl_ttft.py "
              "benchmarks/results/sglang/decode_20251029_075443.txt "
              "benchmarks/results/sglang/disagg_20251029_094805.txt "
              "benchmarks/analysis/p90_itl_ttft.png")
        sys.exit(1)

    agg_file = Path(sys.argv[1])
    disagg_file = Path(sys.argv[2])
    out_png = Path(sys.argv[3]) if len(sys.argv) >= 4 else Path("benchmarks/results/sglang_/p90_itl_ttft.png")

    # 从文件名提取输入输出长度
    input_len, output_len = extract_isl_osl_from_filename(agg_file)
    if input_len is None or output_len is None:
        # 如果agg文件名中没有，尝试从disagg文件名提取
        input_len, output_len = extract_isl_osl_from_filename(disagg_file)

    agg = parse_result_file(agg_file)
    dis = parse_result_file(disagg_file)

    title = "p90 ITL (up) vs p90 TTFT (down) — agg vs disagg"
    plot_dual_bars(agg, dis, title, out_png, input_len=input_len, output_len=output_len)


if __name__ == "__main__":
    main()