#!/usr/bin/env python3
"""
自动处理 sglang_new 目录中的 agg 和 disagg 文件
- 匹配相同输入输出长度的文件对
- 生成图表到 sglang_plot
- 生成表格到 sglang_table
"""
import re
import subprocess
from pathlib import Path
from collections import defaultdict

def extract_isl_osl_from_filename(filename: Path) -> tuple[None, None] | tuple[int, int]:
    """从文件名中提取输入输出长度"""
    filename_str = filename.stem
    
    # 匹配 isl{数字}_osl{数字} 格式
    pattern = r'isl(\d+)[_\-]osl(\d+)'
    match = re.search(pattern, filename_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    
    return None, None

def find_file_pairs(sglang_new_dir: Path):
    """找到相同 isl 和 osl 的 agg/disagg 文件对"""
    agg_files = {}  # {(isl, osl): Path}
    disagg_files = {}  # {(isl, osl): Path}
    
    for file in sglang_new_dir.glob("*.txt"):
        isl, osl = extract_isl_osl_from_filename(file)
        if isl is None or osl is None:
            print(f"⚠️  跳过无法解析的文件: {file.name}")
            continue
        
        if file.name.startswith("agg_"):
            agg_files[(isl, osl)] = file
        elif file.name.startswith("disagg_"):
            disagg_files[(isl, osl)] = file
    
    # 找到交集（两个都有的 (isl, osl)）
    common_keys = set(agg_files.keys()) & set(disagg_files.keys())
    
    pairs = []
    for key in sorted(common_keys):
        pairs.append((key, agg_files[key], disagg_files[key]))
    
    return pairs

def process_pairs(pairs, plot_script, compare_script, output_plot_dir, output_table_dir):
    """处理每对文件，生成图表和表格"""
    plot_dir = Path(output_plot_dir)
    table_dir = Path(output_table_dir)
    
    # 确保输出目录存在
    plot_dir.mkdir(parents=True, exist_ok=True)
    table_dir.mkdir(parents=True, exist_ok=True)
    
    for (isl, osl), agg_file, disagg_file in pairs:
        print(f"\n{'='*80}")
        print(f"处理: ISL={isl}, OSL={osl}")
        print(f"  agg:    {agg_file.name}")
        print(f"  disagg: {disagg_file.name}")
        print(f"{'='*80}")
        
        # 生成图表文件名
        plot_filename = f"p90_itl_ttft_isl{isl}_osl{osl}.png"
        plot_path = plot_dir / plot_filename
        
        # 生成表格文件名
        table_filename = f"comparison_isl{isl}_osl{osl}.txt"
        table_path = table_dir / table_filename
        
        # 运行绘图脚本
        print(f"\n📊 生成图表: {plot_path}")
        try:
            result = subprocess.run(
                ["python3", str(plot_script), str(agg_file), str(disagg_file), str(plot_path)],
                capture_output=True,
                text=True,
                check=True
            )
            print(result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)
            print(f"✅ 图表已保存: {plot_path}")
        except subprocess.CalledProcessError as e:
            print(f"❌ 绘图失败: {e}")
            print(f"STDOUT: {e.stdout}")
            print(f"STDERR: {e.stderr}")
            continue
        
        # 运行对比脚本
        print(f"\n📋 生成表格: {table_path}")
        try:
            result = subprocess.run(
                ["python3", str(compare_script), str(agg_file), str(disagg_file), str(table_path)],
                capture_output=True,
                text=True,
                check=True
            )
            print(result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)
            print(f"✅ 表格已保存: {table_path}")
        except subprocess.CalledProcessError as e:
            print(f"❌ 表格生成失败: {e}")
            print(f"STDOUT: {e.stdout}")
            print(f"STDERR: {e.stderr}")
            continue

def main():
    # 路径配置
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    
    sglang_new_dir = project_root / "cjworkspace" / "results" / "sglang" / "sglang_new"
    plot_script = script_dir / "plot_itl_ttft.py"
    compare_script = script_dir / "compare_results.py"
    output_plot_dir = project_root / "cjworkspace" / "results" / "sglang" / "sglang_plot"
    output_table_dir = project_root / "cjworkspace" / "results" / "sglang" / "sglang_table"
    
    # 检查目录和文件是否存在
    if not sglang_new_dir.exists():
        print(f"❌ 目录不存在: {sglang_new_dir}")
        return
    
    if not plot_script.exists():
        print(f"❌ 脚本不存在: {plot_script}")
        return
    
    if not compare_script.exists():
        print(f"❌ 脚本不存在: {compare_script}")
        return
    
    # 查找文件对
    print(f"🔍 扫描目录: {sglang_new_dir}")
    pairs = find_file_pairs(sglang_new_dir)
    
    if not pairs:
        print("❌ 未找到匹配的文件对")
        return
    
    print(f"\n✅ 找到 {len(pairs)} 对匹配的文件:")
    for (isl, osl), agg_file, disagg_file in pairs:
        print(f"  ISL={isl}, OSL={osl}:")
        print(f"    - agg:    {agg_file.name}")
        print(f"    - disagg: {disagg_file.name}")
    
    # 处理文件对
    print(f"\n🚀 开始处理...")
    process_pairs(pairs, plot_script, compare_script, output_plot_dir, output_table_dir)
    
    print(f"\n{'='*80}")
    print("✅ 处理完成!")
    print(f"📊 图表保存在: {output_plot_dir}")
    print(f"📋 表格保存在: {output_table_dir}")

if __name__ == "__main__":
    main()

