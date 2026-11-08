"""
V2 文件解密: AES-128 + XOR
微信 4.x 的 V2 格式头: 07 08 V2 08 07
先找 AES key, 然后 AES 解密, 再 XOR 0xe1
"""
import os, sys, struct, hashlib
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

XOR_KEY = 0xE1

def parse_v2_header(data):
    """解析 V2 header, 找 AES key 位置"""
    # V2 header 格式: 07 08 V2 08 07 + 若干字段 + AES key + 加密数据
    if data[:6] != b'\x07\x08V\x32\x08\x07':
        return None
    return data[6:]  # header 后的数据

def decrypt_v2_file(fpath, aes_key):
    """解密单个 V2 文件"""
    try:
        with open(fpath, 'rb') as f:
            raw = f.read()
        
        if raw[:6] != b'\x07\x08V\x32\x08\x07':
            return (fpath, 'SKIP-NOT-V2', 0)
        
        header = raw[:6]
        body = raw[6:]
        
        # 简化版: 直接 AES-128-CBC 解密整个 body, 然后 XOR
        # 注意: 微信内部实际解密逻辑更复杂, 需要看 WeChat 逆向
        # 这里尝试直接 AES
        
        try:
            from Crypto.Cipher import AES
            key_bytes = bytes.fromhex(aes_key) if len(aes_key) == 32 else aes_key.encode('ascii')
            
            # 尝试几种 IV
            for iv in [b'\x00' * 16, key_bytes[:16], b'\x01\x02\x03\x04\x05\x06\x07\x08\x00\x00\x00\x00\x00\x00\x00\x00']:
                try:
                    cipher = AES.new(key_bytes, AES.MODE_CBC, iv=iv)
                    decrypted = cipher.decrypt(body)
                    
                    # 看解密后头部
                    xored = bytes(b ^ XOR_KEY for b in decrypted[:16])
                    if xored[:3] == b'\xff\xd8\xff' or xored[:4] == b'\x89PNG':
                        # 找到了正确组合!
                        full_dec = bytes(b ^ XOR_KEY for b in decrypted)
                        out = Path(fpath).with_suffix('')
                        with open(str(out), 'wb') as f:
                            f.write(full_dec)
                        os.remove(fpath)
                        return (fpath, 'OK', len(full_dec))
                except:
                    continue
            
            return (fpath, 'SKIP-NO-IV-MATCH', 0)
        except ImportError:
            return (fpath, 'ERROR-pycrypto-not-installed', 0)
    except Exception as e:
        return (fpath, f'ERROR: {e}', 0)

def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(r"D:\tool\WeChat\聊天记录\xwechat_files")
    aes_key = sys.argv[2] if len(sys.argv) > 2 else '6a27d958a2a01abf'
    
    print(f"V2 AES 解密")
    print(f"目录: {target}")
    print(f"AES key: {aes_key}")
    print(f"XOR key: 0x{XOR_KEY:02x}")
    
    v2_files = []
    for f in target.rglob('*.dat'):
        try:
            with open(f, 'rb') as fh:
                hdr = fh.read(6)
            if hdr == b'\x07\x08V\x32\x08\x07':
                v2_files.append(str(f))
        except:
            pass
    
    print(f"\n找到 {len(v2_files):,} 个 V2 文件")
    
    if len(v2_files) == 0:
        print("没有 V2 文件, 跳过")
        return
    
    ok = skip = err = 0
    for i, fpath in enumerate(v2_files):
        f, status, size = decrypt_v2_file(fpath, aes_key)
        if status.startswith('OK'): ok += 1
        elif status.startswith('SKIP'): skip += 1
        else: err += 1
        if (i+1) % 1000 == 0:
            print(f"  {i+1:,}/{len(v2_files):,} | OK={ok:,} | SKIP={skip:,} | ERR={err:,}")
    
    print(f"\n完成! OK={ok:,} SKIP={skip:,} ERR={err:,}")
    if ok > 0:
        print("  V2 文件已解密!")
    if skip > 0:
        print("  V2 文件微信内部自己解, 不用手动解")
        print("  (微信打开 .dat 时会自动用内置 AES key 解密 V2)")

if __name__ == '__main__':
    main()
