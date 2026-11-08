# -*- coding: utf-8 -*-
"""
DRY RUN 测试: 只扫描 + AI 诊断, 不做任何修改
"""
import os, sys, time, stat
from pathlib import Path
from collections import Counter, defaultdict
from multiprocessing import Pool, cpu_count

sys.stdout.reconfigure(encoding='utf-8')

XOR_KEY = 0xE1
SKIP_DIRS = {'Windows', 'Program Files', 'Program Files (x86)', 'ProgramData',
             'System Volume Information', '$Recycle.Bin', 'node_modules', 'WinSxS'}

def find_wechat_dirs():
    print("[1/2] 全盘扫描...")
    drives = [d for d in 'CDEFGHLM' if os.path.exists(f"{d}:\\")]
    found = []
    for drive in drives:
        print(f"  {drive}:\\ ...", end='', flush=True)
        cnt = 0
        try:
            for root, dirs, files in os.walk(f"{drive}:\\", topdown=True):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
                if 'AppData' in root and 'Tencent' not in root and 'WeChat' not in root:
                    dirs[:] = []
                    continue
                name = os.path.basename(root).lower()
                if name in ['xwechat_files', 'wechat files']:
                    size = sum(os.path.getsize(os.path.join(root, f)) 
                        for f in files if os.path.isfile(os.path.join(root, f))) / 1024 / 1024
                    wxids = []
                    for wxid_dir in dirs:
                        if wxid_dir.startswith('wxid_'):
                            wp = os.path.join(root, wxid_dir)
                            try:
                                ws = sum(os.path.getsize(os.path.join(dp, f))
                                    for dp, dn, fns in os.walk(wp) for f in fns) / 1024 / 1024
                                wxids.append((wxid_dir, ws))
                            except: pass
                    found.append((root, size, wxids))
                cnt += len(files)
            print(f" {cnt:,} 文件")
        except PermissionError:
            print(" skip")
    
    print(f"\n找到 {len(found)} 个微信目录:")
    for p, s, ws in found:
        print(f"  {s:8.1f} MB | {p}")
        for w, sz in ws:
            print(f"    └─ {sz:7.1f} MB | {w}")
    return found

def classify_header(data):
    if data[:6] == b'\x07\x08V\x32\x08\x07': return "V2"
    if data[:3] == bytes([0x1E, 0x39, 0x1E]): return "XOR-JPEG"
    if data[:4] == bytes([0x68, 0xB1, 0xAF, 0xA6]): return "XOR-PNG"
    if data[:3] == b'\xff\xd8\xff': return "PLAIN-JPEG"
    if data[:4] == b'\x89PNG': return "PLAIN-PNG"
    xored = bytes(b ^ XOR_KEY for b in data[:4])
    if xored[:3] == b'\xff\xd8\xff': return "XOR-JPEG"
    if xored[:4] == b'\x89PNG': return "XOR-PNG"
    return "UNKNOWN"

def scan_and_diagnose(root_dir):
    print(f"\n[2/2] 扫 .dat 格式: {root_dir}")
    counts = Counter()
    year_counts = defaultdict(lambda: Counter())
    total = 0
    
    for f in Path(root_dir).rglob('*.dat'):
        try:
            with open(f, 'rb') as fh:
                hdr = fh.read(16)
            ftype = classify_header(hdr)
            counts[ftype] += 1
            total += 1
            import re
            m = re.search(r'(\d{4}-\d{2})', str(f))
            if m: year_counts[m.group(1)][ftype] += 1
            if total % 5000 == 0:
                print(f"    ... {total:,}")
        except: counts["ERROR"] += 1
    
    print(f"\n=== 格式分布 ===")
    print(f"{'类型':<12} {'数量':>10} {'占比':>8}")
    print("-" * 32)
    for ftype, cnt in counts.most_common():
        pct = cnt / total * 100 if total else 0
        print(f"{ftype:<10} {cnt:>10,} {pct:>7.1f}%")
    
    print(f"\n=== AI 诊断 ===")
    plain = counts.get('PLAIN-JPEG',0) + counts.get('PLAIN-PNG',0)
    v2 = counts.get('V2',0)
    unknown = counts.get('UNKNOWN',0)
    encrypted = counts.get('XOR-JPEG',0) + counts.get('XOR-PNG',0)
    
    print(f"\n📋 统计:")
    print(f"  加密变种 (微信能解):  {encrypted:>10,}")
    print(f"  V2 (微信自解):        {v2:>10,}")
    print(f"  明文 ❌ 需加密回去:   {plain:>10,}")
    print(f"  未知 ❓:              {unknown:>10,}")
    print(f"  总计:                 {total:>10,}")
    
    if plain > total * 0.05:
        print(f"\n⚠️  问题: {plain:,} 个明文文件!")
        print(f"   微信打开会自动 XOR 0xe1 → 明文变垃圾 → 显示黑框")
        print(f"   修复: python re_encrypt_parallel.py [目录]")
    
    if year_counts:
        ym_list = sorted(year_counts.keys())
        print(f"\n📅 .dat 按年月分布 ({ym_list[0]} ~ {ym_list[-1]}):")
        print(f"  {'年月':<10} {'加密':>8} {'明文':>8} {'V2':>8} {'其他':>8}")
        print("  " + "-" * 50)
        for ym in ym_list:
            yc = year_counts[ym]
            enc = yc.get('XOR-JPEG',0) + yc.get('XOR-PNG',0)
            plain2 = yc.get('PLAIN-JPEG',0) + yc.get('PLAIN-PNG',0)
            other = sum(v for k, v in yc.items() if k not in ['XOR-JPEG','XOR-PNG','PLAIN-JPEG','PLAIN-PNG','V2'])
            print(f"  {ym:<10} {enc:>8,} {plain2:>8,} {yc.get('V2',0):>8,} {other:>8,}")
        
        # 检查断档
        gaps = []
        for i in range(1, len(ym_list)):
            prev = ym_list[i-1]
            curr = ym_list[i]
            if curr[:4] == prev[:4]:
                if int(curr[5:7]) - int(prev[5:7]) > 1:
                    gaps.append(f"{prev} → {curr}")
            else:
                gaps.append(f"{prev} → {curr}")
        
        if gaps:
            print(f"\n⚠️  断档:")
            for g in gaps[:5]:
                print(f"   {g}")
            print(f"\n   🔴 这些月份的 .dat 文件物理不存在!")
            print(f"   微信修复数据时可能删除了")
            print(f"   需要从外部备份 (旧电脑/旧硬盘/云盘/压缩包) 合并")
    
    return counts

if __name__ == '__main__':
    print("=" * 60)
    print("  WeChat Recovery — DRY RUN (只读扫描)")
    print("=" * 60)
    
    found = find_wechat_dirs()
    if not found:
        print("\n没找到微信目录!")
        sys.exit(1)
    
    # 选最大的
    main_dir = sys.argv[1] if len(sys.argv) > 1 else max(found, key=lambda x: x[1])[0]
    counts = scan_and_diagnose(main_dir)
    
    print(f"\n{'='*60}")
    print("  DRY RUN 完成 — 只读, 没改任何文件")
    print("  真正修复: python auto_recover.py [目录]")
    print(f"{'='*60}")
