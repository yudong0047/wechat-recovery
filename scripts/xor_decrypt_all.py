"""
XOR 批量解密 .dat 文件 (导出用)
把加密变种 .dat 解成明文 JPG/PNG
注意: 解完后微信打开会再 XOR 一次 → 反而显示不了!
      只有做备份导出时才用
"""
import os, sys, time, stat
from pathlib import Path
from multiprocessing import Pool, cpu_count
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

XOR_KEY = 0xE1

def xor_decrypt_file(args):
    fpath, suffix = args
    try:
        with open(fpath, 'rb') as f:
            data = f.read()
        
        if len(data) < 3:
            return (fpath, 'SKIP', 0)
        
        # 先 XOR 看结果是什么
        decrypted = bytes(b ^ XOR_KEY for b in data[:16])
        
        ftype = None
        if decrypted[:3] == b'\xff\xd8\xff':
            ftype = 'JPG'
        elif decrypted[:4] == b'\x89PNG':
            ftype = 'PNG'
        
        if ftype:
            # 完整 XOR
            full_dec = bytes(b ^ XOR_KEY for b in data)
            
            # 修复只读
            try:
                os.chmod(fpath, stat.S_IWRITE | stat.S_IREAD)
            except:
                pass
            
            out_path = Path(fpath).with_suffix('')
            if suffix:
                out_path = Path(f"{fpath}.{ftype.lower()}")
            
            with open(str(out_path), 'wb') as f:
                f.write(full_dec)
            
            if not suffix:
                os.remove(fpath)
            
            return (fpath, f'OK-{ftype}', len(full_dec))
        else:
            return (fpath, 'SKIP-NOT-VARIANT', 0)
    except Exception as e:
        return (fpath, f'ERROR: {e}', 0)

def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(r"D:\tool\WeChat\聊天记录\xwechat_files")
    
    suffix = len(sys.argv) > 2  # 加扩展名
    
    print(f"XOR 解密目录: {target}")
    print(f"XOR key: 0x{XOR_KEY:02x}")
    print(f"输出方式: {'加 .jpg/.png 扩展名' if suffix else '覆盖原文件'}")
    print("扫描...")
    
    files = [(str(f), suffix) for f in target.rglob('*.dat') if f.stat().st_size >= 3]
    print(f"共 {len(files):,} 个 .dat")
    
    t0 = time.time()
    counts = Counter()
    done = 0
    
    with Pool(min(8, cpu_count())) as pool:
        for result in pool.imap_unordered(xor_decrypt_file, files, chunksize=100):
            fpath, status, size = result
            counts[status.split('-')[0]] += 1
            done += 1
            if done % 5000 == 0:
                elapsed = time.time() - t0
                print(f"  {done:,}/{len(files):,} | OK={counts.get('OK',0):,} | SKIP={counts.get('SKIP',0):,} | {elapsed:.0f}s")
    
    elapsed = time.time() - t0
    
    print(f"\n{'='*50}")
    print(f"完成! {elapsed:.0f}s")
    print(f"  OK:   {counts.get('OK',0):,}")
    print(f"  SKIP: {counts.get('SKIP',0):,} (V2 文件或非变种)")
    print(f"  ERR:  {counts.get('ERROR',0):,}")

if __name__ == '__main__':
    main()
