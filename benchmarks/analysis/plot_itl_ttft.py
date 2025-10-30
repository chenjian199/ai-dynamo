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

    # 表头顺序: avg, min, max, p99, p90, p75
    def extract_p90_from_row(line: str) -> float | None:
        # 用竖线分列
        parts = [p.strip() for p in line.split("│")]
        # 期望至少 8 列（两侧也有边框列）
        if len(parts) < 8:
            return None
        # 列索引: 0(边框),1(avg),2(min),3(max),4(p99),5(p90),6(p75),7(边框)
        try:
            return float(parts[5].replace(",", ""))  # 去掉可能的千分位逗号
        except ValueError:
            return None

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.rstrip("\n")

            # 捕获并发度
            m = re.search(r"DECODE TEST RESULTS - Concurrency:\s*(\d+)", line)
            if m:
                # 如果上一个块已经有数据但尚未落盘，落盘
                if conc is not None and ttft_p90 is not None and itl_p90 is not None:
                    data[conc] = {"ttft_p90": ttft_p90, "itl_p90": itl_p90}
                conc = int(m.group(1))
                ttft_p90 = None
                itl_p90 = None
                continue

            # 抓 Time To First Token 行的 p90
            if "Time To First Token" in line and "(ms)" in line:
                val = extract_p90_from_row(line)
                if val is not None:
                    ttft_p90 = val
                continue

            # 抓 Inter Token Latency 行的 p90
            if ("Inter Token Latency" in line and "(ms)" in line) or ("Inter Token Latency (ms)" in line):
                val = extract_p90_from_row(line)
                if val is not None:
                    itl_p90 = val
                continue

        # 文件结束时落盘最后一个块
        if conc is not None and ttft_p90 is not None and itl_p90 is not None:
            data[conc] = {"ttft_p90": ttft_p90, "itl_p90": itl_p90}

    return data


def plot_dual_bars(agg_data: dict[int, dict[str, float]],
                   disagg_data: dict[int, dict[str, float]],
                   title: str,
                   out_path: Path):
    # 取两个文件都有的并发度
    common_conc = sorted(set(agg_data.keys()) & set(disagg_data.keys()))
    if not common_conc:
        print("No common concurrency levels found between two files.")
        return

    # 组装数据
    agg_itl = [agg_data[c]["itl_p90"] for c in common_conc]
    dis_itl = [disagg_data[c]["itl_p90"] for c in common_conc]
    agg_ttft = [agg_data[c]["ttft_p90"] for c in common_conc]
    dis_ttft = [disagg_data[c]["ttft_p90"] for c in common_conc]

    # 上下两个坐标轴：上(ITL)、下(TTFT，向下显示)
    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                                         gridspec_kw={"height_ratios": [2, 2]})

    x = list(range(len(common_conc)))
    width = 0.18
    offset = 0.22

    # 顶部：ITL（各自独立的 y 轴范围）
    ax_top.bar([i - offset for i in x], agg_itl, width=width, color="#1f77b4", alpha=0.9, label="agg ITL p90 (ms)")
    ax_top.bar([i + offset for i in x], dis_itl, width=width, color="#ff7f0e", alpha=0.9, label="disagg ITL p90 (ms)")
    max_itl = max(agg_itl + dis_itl) if (agg_itl or dis_itl) else 0.0
    ax_top.set_ylabel("ITL p90 (ms)")
    ax_top.set_title(title)
    if max_itl > 0:
        ax_top.set_ylim(0, max_itl * 1.15)
    ax_top.grid(axis='y', linestyle='--', alpha=0.2)

    # 底部：TTFT（正值绘制，向下显示）
    ax_bot.bar([i - offset for i in x], agg_ttft, width=width, color="#1f77b4", alpha=0.45, label="agg TTFT p90 (ms)")
    ax_bot.bar([i + offset for i in x], dis_ttft, width=width, color="#ff7f0e", alpha=0.45, label="disagg TTFT p90 (ms)")
    max_ttft = max(agg_ttft + dis_ttft) if (agg_ttft or dis_ttft) else 0.0
    ax_bot.set_ylabel("TTFT p90 (ms)")
    if max_ttft > 0:
        ax_bot.set_ylim(0, max_ttft * 1.15)
    ax_bot.invert_yaxis()  # 向下
    ax_bot.axhline(0, color="black", linewidth=1)
    ax_bot.grid(axis='y', linestyle='--', alpha=0.2)

    # X 轴（并发度）
    ax_bot.set_xticks(x)
    ax_bot.set_xticklabels([str(c) for c in common_conc])
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

    fig.tight_layout()
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
    out_png = Path(sys.argv[3]) if len(sys.argv) >= 4 else Path("benchmarks/analysis/p90_itl_ttft.png")

    agg = parse_result_file(agg_file)
    dis = parse_result_file(disagg_file)

    title = "p90 ITL (up) vs p90 TTFT (down) — agg vs disagg"
    plot_dual_bars(agg, dis, title, out_png)


if __name__ == "__main__":
    main()