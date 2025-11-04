#!/usr/bin/env python3
"""
绘制相同部署类型和输入输出长度的多个文件在一张图上
用于对比同一配置下不同时间点的测试结果
"""
import re
import sys
from pathlib import Path
from collections import defaultdict
import matplotlib.pyplot as plt
from plot_itl_ttft import parse_result_file, extract_isl_osl_from_filename

# 预定义颜色列表，用于区分不同文件
COLORS = [
    "#1f77b4",  # 蓝色
    "#ff7f0e",  # 橙色
    "#2ca02c",  # 绿色
    "#d62728",  # 红色
    "#9467bd",  # 紫色
    "#8c564b",  # 棕色
    "#e377c2",  # 粉色
    "#7f7f7f",  # 灰色
    "#bcbd22",  # 橄榄色
    "#17becf",  # 青色
]

def plot_multi_files(datas_list: list[dict[int, dict[str, float]]],
                     file_names: list[str],
                     title: str,
                     out_path: Path,
                     input_len: int | None = None,
                     output_len: int | None = None):
    """
    绘制多个文件的数据在一张图上
    
    Args:
        datas_list: 多个文件的解析数据列表
        file_names: 对应的文件名列表（用于图例）
        title: 图表标题
        out_path: 输出路径
        input_len: 输入长度
        output_len: 输出长度
    """
    if not datas_list:
        print("No data to plot")
        return
    
    # 找到所有并发度的并集
    all_conc_sets = [set(data.keys()) for data in datas_list]
    all_conc = sorted(set().union(*all_conc_sets))
    
    if not all_conc:
        print("No concurrency levels found.")
        return
    
    print(f"Concurrency levels: {all_conc}")
    print(f"Number of files: {len(datas_list)}")
    
    # 准备数据：每个文件的 ITL 和 TTFT 列表
    itl_data = []  # [[file1_itl_values], [file2_itl_values], ...]
    ttft_data = []  # [[file1_ttft_values], [file2_ttft_values], ...]
    
    for data in datas_list:
        itl_data.append([data.get(c, {}).get("itl_p90") for c in all_conc])
        ttft_data.append([data.get(c, {}).get("ttft_p90") for c in all_conc])
    
    # 创建图表
    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                                         gridspec_kw={"height_ratios": [2, 2]})
    
    x = list(range(len(all_conc)))
    width = 0.15  # 柱状图宽度（根据文件数量调整）
    
    # 如果文件很多，使用折线图；否则使用分组柱状图
    use_line_chart = len(datas_list) > 6
    
    if use_line_chart:
        # 使用折线图
        for i, (itl_vals, ttft_vals, file_name) in enumerate(zip(itl_data, ttft_data, file_names)):
            color = COLORS[i % len(COLORS)]
            # 提取时间戳作为标签
            timestamp = re.search(r'(\d{8}_\d{6})', file_name)
            label = timestamp.group(1) if timestamp else f"File {i+1}"
            
            # 绘制 ITL（顶部）
            valid_itl = [(j, v) for j, v in enumerate(itl_vals) if v is not None]
            if valid_itl:
                x_itl = [p[0] for p in valid_itl]
                y_itl = [p[1] for p in valid_itl]
                ax_top.plot(x_itl, y_itl, marker='o', color=color, alpha=0.8, 
                           label=f"{label} ITL", linewidth=2, markersize=4)
            
            # 绘制 TTFT（底部）
            valid_ttft = [(j, v) for j, v in enumerate(ttft_vals) if v is not None]
            if valid_ttft:
                x_ttft = [p[0] for p in valid_ttft]
                y_ttft = [p[1] for p in valid_ttft]
                ax_bot.plot(x_ttft, y_ttft, marker='s', color=color, alpha=0.6, 
                           label=f"{label} TTFT", linewidth=2, markersize=4)
    else:
        # 使用分组柱状图
        total_width = len(datas_list) * width
        start_offset = -(total_width - width) / 2
        
        for i, (itl_vals, ttft_vals, file_name) in enumerate(zip(itl_data, ttft_data, file_names)):
            color = COLORS[i % len(COLORS)]
            offset = start_offset + i * width
            timestamp = re.search(r'(\d{8}_\d{6})', file_name)
            label = timestamp.group(1) if timestamp else f"File {i+1}"
            
            # 绘制 ITL（顶部）
            for j, v in enumerate(itl_vals):
                if v is not None:
                    ax_top.bar(j + offset, v, width=width, color=color, alpha=0.8,
                              label=f"{label} ITL" if j == 0 else None)
            
            # 绘制 TTFT（底部）
            for j, v in enumerate(ttft_vals):
                if v is not None:
                    ax_bot.bar(j + offset, v, width=width, color=color, alpha=0.5,
                              label=f"{label} TTFT" if j == 0 else None)
    
    # 设置 ITL 坐标轴
    all_itl_vals = [v for itl_list in itl_data for v in itl_list if v is not None]
    max_itl = max(all_itl_vals) if all_itl_vals else 0.0
    ax_top.set_ylabel("ITL p90 (ms)")
    ax_top.set_title(title)
    if max_itl > 0:
        ax_top.set_ylim(0, max_itl * 1.15)
    ax_top.grid(axis='y', linestyle='--', alpha=0.2)
    
    # 设置 TTFT 坐标轴
    all_ttft_vals = [v for ttft_list in ttft_data for v in ttft_list if v is not None]
    max_ttft = max(all_ttft_vals) if all_ttft_vals else 0.0
    ax_bot.set_ylabel("TTFT p90 (ms)")
    if max_ttft > 0:
        ax_bot.set_yscale('symlog', linthresh=max(1.0, max_ttft * 0.02))
        ax_bot.set_ylim(0, max_ttft * 1.15)
    ax_bot.invert_yaxis()  # 向下
    ax_bot.axhline(0, color="black", linewidth=1)
    ax_bot.grid(axis='y', linestyle='--', alpha=0.2)
    
    # X 轴
    ax_bot.set_xticks(x)
    ax_bot.set_xticklabels([str(c) for c in all_conc])
    ax_bot.set_xlabel("Concurrency")
    
    # 图例
    handles_t, labels_t = ax_top.get_legend_handles_labels()
    handles_b, labels_b = ax_bot.get_legend_handles_labels()
    handles = handles_t + handles_b
    labels = labels_t + labels_b
    uniq = {}
    for h, l in zip(handles, labels):
        if l not in uniq:
            uniq[l] = h
    
    # 根据图例数量调整列数
    ncol = min(3, len(uniq))
    ax_top.legend(uniq.values(), uniq.keys(), ncol=ncol, fontsize=8, loc="upper right")
    
    # 输入输出长度标注
    if input_len is not None and output_len is not None:
        length_text = f"Input Length: {input_len:,}, Output Length: {output_len:,}"
    else:
        length_text = "Input/Output Length: N/A"
    fig.text(0.5, 0.02, length_text, 
             ha='center', fontsize=10, style='italic')
    
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"Saved figure to: {out_path}")


def find_and_group_files(sglang_last_dir: Path):
    """
    找到并分组文件：按部署类型和输入输出长度分组
    
    Returns:
        {(deployment_type, isl, osl): [file_paths]}
    """
    groups = defaultdict(list)
    
    for file in sglang_last_dir.glob("*.txt"):
        isl, osl = extract_isl_osl_from_filename(file)
        if isl is None or osl is None:
            print(f"⚠️  跳过无法解析的文件: {file.name}")
            continue
        
        # 提取部署类型（agg 或 disagg）
        if file.name.startswith("agg_"):
            deploy_type = "agg"
        elif file.name.startswith("disagg_"):
            deploy_type = "disagg"
        else:
            print(f"⚠️  跳过未知部署类型: {file.name}")
            continue
        
        groups[(deploy_type, isl, osl)].append(file)
    
    # 对每个组的文件按时间戳排序
    for key in groups:
        groups[key].sort(key=lambda f: f.name)
    
    return groups


def main():
    if len(sys.argv) > 1:
        sglang_last_dir = Path(sys.argv[1])
    else:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent
        sglang_last_dir = project_root / "benchmarks/results/sglang_last"
    
    output_dir = sglang_last_dir.parent / "sglang_plot"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not sglang_last_dir.exists():
        print(f"❌ 目录不存在: {sglang_last_dir}")
        return
    
    print(f"🔍 扫描目录: {sglang_last_dir}")
    groups = find_and_group_files(sglang_last_dir)
    
    if not groups:
        print("❌ 未找到匹配的文件")
        return
    
    print(f"\n✅ 找到 {len(groups)} 组文件:")
    for (deploy_type, isl, osl), files in sorted(groups.items()):
        print(f"  {deploy_type} ISL={isl} OSL={osl}: {len(files)} 个文件")
        for f in files:
            print(f"    - {f.name}")
    
    # 处理每组文件
    for (deploy_type, isl, osl), files in sorted(groups.items()):
        if len(files) == 0:
            continue
        
        print(f"\n{'='*80}")
        print(f"处理: {deploy_type} ISL={isl} OSL={osl} ({len(files)} 个文件)")
        print(f"{'='*80}")
        
        # 解析所有文件
        datas_list = []
        file_names = []
        for file in files:
            print(f"  解析: {file.name}")
            data = parse_result_file(file)
            if data:
                datas_list.append(data)
                file_names.append(file.name)
        
        if not datas_list:
            print(f"  ⚠️  跳过：没有有效数据")
            continue
        
        # 生成输出文件名
        output_filename = f"p90_itl_ttft_{deploy_type}_isl{isl}_osl{osl}.png"
        output_path = output_dir / output_filename
        
        # 生成标题
        title = f"p90 ITL (up) vs p90 TTFT (down) — {deploy_type.upper()} ({len(datas_list)} runs)"
        
        # 绘制图表
        plot_multi_files(datas_list, file_names, title, output_path, 
                        input_len=isl, output_len=osl)
    
    print(f"\n{'='*80}")
    print("✅ 处理完成!")
    print(f"📊 图表保存在: {output_dir}")


if __name__ == "__main__":
    main()

