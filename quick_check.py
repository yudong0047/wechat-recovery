# -*- coding: utf-8 -*-
"""
只看格式分布 + 最早年份, 快速版本
"""
import sys, os, re
from pathlib import Path
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')

XOR_KEY = 0xE1
root = r'D:\WeChat\xwechat_files\wxid_XXXXXXXXXXXX_a13f'

def classify_header(data):
    if data[:6] == b'\x07\x08V\x32\x08\x07': return 'V2'
    if data[:3] == bytes([0x1E, 0x39, 0x1E]): return 'XOR-JPEG'
    if data[:4] == bytes([0x68, 0xB1, 0xAF, 0xA6]): return 'XOR-PNG'
    if data[:3] == b'\xff\xd8\xff': return 'PLAIN-JPEG'
    if data[:4] == b'\x89PNG': return 'PLAIN-PNG'
    xored = bytes(b ^ XOR_KEY for b in data[:4])
    if xored[:3] == b'\xff\xd8\xff': return 'XOR-JPEG'
    if xored[:4] == b'\x89PNG': return 'XOR-PNG'
    return 'UNKNOWN'

counts = Counter()
year_counts = defaultdict(lambda: Counter())
earliest_years = Counter()
total = 0

for f in Path(root).rglob('*.dat'):
    try:
        with open(f, 'rb') as fh: hdr = fh.read(16)
        ftype = classify_header(hdr)
        counts[ftype] += 1
        total += 1
        # 路径提年月
        m = re.search(r'(\\|\s)(20\d{2}-\d{2})', str(f))
        if m:
            ym = m.group(2)
            year_counts[ym][ftype] += 1
            earliest_years[ym[:4]] += 1
        # 看文件创建/修改时间
        st = f.stat()
        import datetime
        ctime = datetime.datetime.fromtimestamp(st.st_mtime)
        earliest_years[ctime.strftime('%Y') + '_mtime'] += 1
    except Exception as e:
        counts['ERROR'] += 1
        if counts['ERROR'] <= 3:
            print(f"  ERR {f}: {e}")

print(f"=== 格式分布 (共 {total:,} .dat) ===")
print(f"{'类型':<12} {'数量':>10} {'占比':>8}")
print('-' * 32)
for ftype, cnt in counts.most_common():
    print(f'{ftype:<10} {cnt:>10,} {cnt/total*100:>7.1f}%')

# 加密 vs 明文 vs V2
enc = counts.get('XOR-JPEG',0) + counts.get('XOR-PNG',0)
plain = counts.get('PLAIN-JPEG',0) + counts.get('PLAIN-PNG',0)
v2 = counts.get('V2',0)
unk = counts.get('UNKNOWN',0)

print(f"\n=== 汇总 ===")
print(f"加密变种 (正常):  {enc:>10,} ({enc/total*100:.1f}%)")
print(f"V2 (微信自解):    {v2:>10,} ({v2/total*100:.1f}%)")
print(f"明文 (需加密):    {plain:>10,} ({plain/total*100:.1f}%)  ⚠️" if plain > 0 else f"明文:             {plain:>10,}")
print(f"未知:             {unk:>10,} ({unk/total*100:.1f}%)")

print(f"\n=== 路径年月分布 ===")
ym_list = sorted(year_counts.keys())
if ym_list:
    print(f"最早: {ym_list[0]}")
    print(f"最晚: {ym_list[-1]}")
    print(f"覆盖 {len(ym_list)} 个月")
    
    # 按年汇总
    yr_totals = Counter()
    for ym, yc in year_counts.items():
        yr_totals[ym[:4]] += sum(yc.values())
    for yr in sorted(yr_totals.keys()):
        print(f"  {yr}: {yr_totals[yr]:>10,} 个 .dat")

print(f"\n=== 关键发现 ===")
if plain > 0:
    print(f"  ⚠️  {plain:,} 个明文! 需要加密回去 (跑 re_encrypt_parallel.py)")
else:
    print(f"  ✅ 没有明文文件, 格式全正常!")

if ym_list:
    # 检查 2016-2018 有没有
    early = [ym for ym in ym_list if ym[:4] in ['2016','2017','2018']]
    if early:
        print(f"  ✅ 2016-2018 有数据: {', '.join(sorted(early)[:3])}")
    else:
        print(f"  🔴 2016-2018 没有 .dat 文件! 微信修复时删掉了")
        print(f"     需要从外部备份 (压缩包/旧硬盘/云盘) 恢复")
