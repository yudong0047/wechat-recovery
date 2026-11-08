"""
全盘扫描微信数据目录
找 xwechat_files / WeChat Files / wxid_ 目录
输出所有发现的目录及其大小
"""
import os, sys, time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

drives = [d for d in 'CDEFGHLM' if os.path.exists(f"{d}:\\")]
skip = {'Windows', 'Program Files', 'Program Files (x86)', 'ProgramData', 
        'System Volume Information', '$Recycle.Bin', 'node_modules', 'WinSxS'}

found = []
t0 = time.time()
total = 0

print(f"扫描盘符: {drives}")
print(f"跳过: {skip}")
print("-" * 50)

for drive in drives:
    print(f"扫 {drive}:\\ ...")
    try:
        for root, dirs, files in os.walk(f"{drive}:\\", topdown=True):
            dirs[:] = [d for d in dirs if d not in skip and not d.startswith('.')]
            
            # AppData 只扫 Tencent
            if 'AppData' in root and 'Tencent' not in root and 'WeChat' not in root:
                dirs[:] = []
                continue
            
            total += len(files)
            
            name = os.path.basename(root).lower()
            if name in ['xwechat_files', 'wechat files'] or name.startswith('wxid_'):
                size = sum(os.path.getsize(os.path.join(root, f)) for f in files if os.path.isfile(os.path.join(root, f)))
                size_mb = size / 1024 / 1024
                found.append((root, size_mb, len(files)))
                tag = "📁" if 'xwechat' in name or 'wechat files' in name else "🆔"
                print(f"  {tag} {size_mb:8.1f} MB | {root}")
                
                # 如果是 xwechat_files, 继续看里面的 wxid 子目录
                if 'xwechat' in name or 'wechat files' in name:
                    for wxid_dir in dirs:
                        if wxid_dir.startswith('wxid_') or wxid_dir.startswith('xwechat_'):
                            wxid_path = os.path.join(root, wxid_dir)
                            try:
                                wxid_size = sum(os.path.getsize(os.path.join(dp, f)) 
                                    for dp, dn, fns in os.walk(wxid_path) for f in fns) / 1024 / 1024
                                print(f"      └─ {wxid_size:.1f} MB | {wxid_dir}")
                            except:
                                pass
            
            # 进度
            if total % 50000 == 0:
                elapsed = time.time() - t0
                print(f"    ... 已扫 {total:,} 文件, {elapsed:.0f}s")
    except PermissionError:
        pass
    except Exception as e:
        print(f"  跳过: {e}")

elapsed = time.time() - t0

print(f"\n{'='*50}")
print(f"扫描完成! 耗时 {elapsed:.0f}s, 共 {total:,} 文件")
print(f"找到 {len(found)} 个微信相关目录:")
print("-" * 50)
for p, s, c in sorted(found, key=lambda x: -x[1]):
    print(f"  {s:8.1f} MB ({c:6d} 文件) | {p}")

# 保存结果
out_file = os.path.join(os.path.dirname(__file__), 'scan_result.txt')
with open(out_file, 'w', encoding='utf-8') as f:
    f.write(f"扫描时间: {time.strftime('%Y-%m-%d %H:%M')}\n")
    f.write(f"耗时: {elapsed:.0f}s\n\n")
    for p, s, c in sorted(found, key=lambda x: -x[1]):
        f.write(f"{s:.1f} MB | {c} 文件 | {p}\n")
print(f"\n结果已保存: {out_file}")
