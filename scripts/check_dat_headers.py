"""
扫描 .dat 文件加密格式分布
对每个 .dat 读文件头, 判断加密类型:
  V2:        07 08 56 32 08 07 (6字节 V2 header + AES)
  变种1:     1E 39 1E          (XOR 0xe1 → JPEG FF D8 FF)
  变种2:     68 B1 AF A6       (XOR 0xe1 → PNG 89 50 4E 47)
  明文 JPEG: FF D8 FF
  明文 PNG:  89 50 4E 47
  其他:      未知
"""
import os, sys, time
from pathlib import Path
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')

XOR_KEY = 0xE1

def classify_header(data):
    """8字节数据 → 加密类型"""
    if data[:6] == b'\x07\x08V\x32\x08\x07':
        return "V2"
    if data[:3] == bytes([0x1E, 0x39, 0x1E]):
        return "XOR-JPEG"      # XOR 后 → FF D8 FF
    if data[:4] == bytes([0x68, 0xB1, 0xAF, 0xA6]):
        return "XOR-PNG"      # XOR 后 → 89 50 4E 47
    if data[:3] == b'\xff\xd8\xff':
        return "PLAIN-JPEG"
    if data[:4] == b'\x89PNG':
        return "PLAIN-PNG"
    # XOR 看是不是已知 magic
    xored = bytes(b ^ XOR_KEY for b in data[:4])
    if xored[:3] == b'\xff\xd8\xff':
        return "XOR-JPEG"
    if xored[:4] == b'\x89PNG':
        return "XOR-PNG"
    return "UNKNOWN"

def main():
    scan_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(r"D:\tool\WeChat\聊天记录\xwechat_files")
    
    print(f"扫描目录: {scan_dir}")
    
    counts = Counter()
    sizes = defaultdict(int)
    year_counts = defaultdict(lambda: Counter())
    total = 0
    t0 = time.time()
    
    for f in scan_dir.rglob('*.dat'):
        try:
            with open(f, 'rb') as fh:
                hdr = fh.read(16)
            ftype = classify_header(hdr)
            fsize = f.stat().st_size
            counts[ftype] += 1
            sizes[ftype] += fsize
            total += 1
            
            # 从路径提年份
            import re
            m = re.search(r'(\d{4}-\d{2})', str(f))
            if m:
                year_counts[m.group(1)][ftype] += 1
            
            if total % 10000 == 0:
                elapsed = time.time() - t0
                print(f"  ... {total:,} 文件 ({elapsed:.0f}s)")
        except:
            counts["ERROR"] += 1
    
    elapsed = time.time() - t0
    
    print(f"\n{'='*60}")
    print(f"扫描完成! {total:,} 文件, {elapsed:.0f}s")
    print(f"{'='*60}")
    print(f"{'类型':<12} {'数量':>10} {'占比':>8} {'总大小':>12}")
    print("-" * 44)
    
    for ftype, cnt in counts.most_common():
        pct = cnt / total * 100 if total else 0
        mb = sizes[ftype] / 1024 / 1024
        icon = {
            'V2': '🔐', 'XOR-JPEG': '🖼️', 'XOR-PNG': '🖼️',
            'PLAIN-JPEG': '⚠️', 'PLAIN-PNG': '⚠️', 'UNKNOWN': '❓', 'ERROR': '❌'
        }.get(ftype, '')
        print(f"{icon} {ftype:<10} {cnt:>10,} {pct:>7.1f}% {mb:>10.0f} MB")
    
    # 按年份分布 (前20个)
    if year_counts:
        print(f"\n{'='*60}")
        print("按年份分布 (前20):")
        print(f"{'年月':<10}", end="")
        for t in ['V2', 'XOR-JPEG', 'XOR-PNG', '其他']:
            print(f" {t:>10}", end="")
        print()
        print("-" * 52)
        for ym in sorted(year_counts.keys())[:20]:
            yc = year_counts[ym]
            other = sum(c for k, c in yc.items() if k not in ['V2', 'XOR-JPEG', 'XOR-PNG'])
            print(f"{ym:<10} {yc['V2']:>10,} {yc['XOR-JPEG']:>10,} {yc['XOR-PNG']:>10,} {other:>10,}")
    
    # 警告
    plain_count = counts.get('PLAIN-JPEG', 0) + counts.get('PLAIN-PNG', 0)
    if plain_count > 0:
        print(f"\n⚠️ 警告: {plain_count} 个明文文件!")
        print("  微信打开会先 XOR 0xe1, 明文→垃圾数据→显示不出来")
        print("  请运行 re_encrypt_parallel.py 加密回去")
    
    unknown_count = counts.get('UNKNOWN', 0)
    if unknown_count > 0:
        print(f"⚠️ 警告: {unknown_count} 个未知格式! ({unknown_count/total*100:.1f}%)")
        print("  微信也解不开这些文件")

if __name__ == '__main__':
    main()
