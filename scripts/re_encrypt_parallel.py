"""
反向加密: 把明文 JPG/PNG → XOR 加密变种格式
关键修复: 如果之前错误地把 .dat 覆盖成了明文 JPG
微信打开时会先 XOR 0xe1 → 明文变垃圾 → 显示不了
跑这个脚本: 明文再 XOR 一次 → 回到加密变种格式 → 微信能解!

变种1 (JPG):   FF D8 FF → XOR 0xe1 → 1E 39 1E
变种2 (PNG):    89 50 4E 47 → XOR 0xe1 → 68 B1 AF A6
"""
import os, sys, time, stat
from pathlib import Path
from multiprocessing import Pool, cpu_count
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

XOR_KEY = 0xE1

def should_encrypt_header(data):
    """判断文件头是不是明文 (需要加密回去)"""
    if data[:3] == b'\xff\xd8\xff':       # JPEG
        return True, 'XOR-JPEG'
    if data[:4] == b'\x89PNG':             # PNG
        return True, 'XOR-PNG'
    return False, None

def xor_encrypt_file(args):
    """加密单个文件"""
    fpath, force = args
    try:
        size = os.path.getsize(fpath)
        if size < 3:
            return (fpath, 'SKIP-TOO-SMALL', 0)
        
        with open(fpath, 'rb') as f:
            hdr = f.read(16)
        
        need, ftype = should_encrypt_header(hdr)
        if not need:
            return (fpath, 'SKIP-ALREADY-ENCRYPTED', 0)
        
        if not force:
            # 读整个文件
            with open(fpath, 'rb') as f:
                data = f.read()
        else:
            with open(fpath, 'rb') as f:
                data = f.read()
        
        # XOR 加密
        encrypted = bytes(b ^ XOR_KEY for b in data)
        
        # 修复只读属性
        try:
            os.chmod(fpath, stat.S_IWRITE | stat.S_IREAD)
        except:
            pass
        
        # 写回
        with open(fpath, 'wb') as f:
            f.write(encrypted)
        
        return (fpath, f'OK-{ftype}', size)
    except PermissionError:
        # 去掉只读再试
        try:
            os.chmod(fpath, stat.S_IWRITE | stat.S_IREAD)
            with open(fpath, 'rb') as f:
                data = f.read()
            encrypted = bytes(b ^ XOR_KEY for b in data)
            with open(fpath, 'wb') as f:
                f.write(encrypted)
            return (fpath, 'OK-PERM-FIXED', os.path.getsize(fpath))
        except Exception as e:
            return (fpath, f'ERROR-PERM: {e}', 0)
    except Exception as e:
        return (fpath, f'ERROR: {e}', 0)

def main():
    target_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(r"D:\tool\WeChat\聊天记录\xwechat_files")
    
    print(f"反向加密目录: {target_dir}")
    print(f"XOR key: 0x{XOR_KEY:02x}")
    print("扫描文件...")
    
    # 收集所有 .dat
    files = []
    for f in target_dir.rglob('*.dat'):
        if f.stat().st_size >= 3:
            files.append((str(f), False))
    
    print(f"共 {len(files):,} 个 .dat 文件待处理")
    print("开始加密 (8进程)...\n")
    
    t0 = time.time()
    counts = Counter()
    total_bytes = 0
    done = 0
    
    with Pool(min(8, cpu_count())) as pool:
        for result in pool.imap_unordered(xor_encrypt_file, files, chunksize=100):
            fpath, status, size = result
            counts[status.split('-')[0]] += 1
            if status.startswith('OK'):
                total_bytes += size
            done += 1
            
            if done % 5000 == 0 or done == len(files):
                elapsed = time.time() - t0
                print(f"  {done:,}/{len(files):,} | OK={counts.get('OK',0):,} | "
                      f"SKIP={counts.get('SKIP',0):,} | ERR={counts.get('ERROR',0):,} | {elapsed:.0f}s")
    
    elapsed = time.time() - t0
    
    print(f"\n{'='*50}")
    print(f"完成! {elapsed:.0f}s, 处理 {len(files):,} 文件")
    print(f"{'='*50}")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v:,}")
    print(f"  加密总大小: {total_bytes/1024/1024:.0f} MB")
    
    print(f"\n✅ 加密完成!")
    print("   下一步: 清微信缓存 + 重启微信")
    print("   运行 run.bat → 选 [7] 清缓存重启")

if __name__ == '__main__':
    main()
