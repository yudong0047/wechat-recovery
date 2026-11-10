"""
从 remote API 自动获取 AES key 和 XOR key
API: https://your-key-api.example.com/api/key
需要上传 global_config + global_config.crc
"""
import os, sys, time, json, hashlib
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

try:
    import requests
except ImportError:
    print("需要安装 requests: pip install requests")
    sys.exit(1)

# 禁用环境代理
for env in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    os.environ.pop(env, None)

API_URL = "https://your-key-api.example.com/api/key"

def find_global_config():
    """找 global_config 文件"""
    candidates = [
        r"D:\WeChat\xwechat_files",
        r"C:\Users\<You>\Documents\WeChat Files",
        r"D:\Users\<You>\Documents\xwechat_files",
    ]
    
    for c in candidates:
        p = Path(c)
        if p.exists():
            for f in p.rglob('global_config'):
                if not f.name.endswith('.crc'):
                    return str(f)
    return None

def get_crc(filepath):
    """计算 CRC"""
    with open(filepath, 'rb') as f:
        data = f.read()
    # CRC32
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
    return crc ^ 0xFFFFFFFF

def main():
    print("=== Remote API 密钥获取 ===")
    print(f"API: {API_URL}")
    print()
    
    gc_path = find_global_config()
    if not gc_path:
        print("❌ 没找到 global_config 文件!")
        print("   请手动指定路径作为参数")
        sys.exit(1)
    
    print(f"找到 global_config: {gc_path}")
    
    crc_path = gc_path + '.crc'
    crc = 0
    if os.path.exists(crc_path):
        with open(crc_path, 'r') as f:
            crc = int(f.read().strip(), 16)
        print(f"CRC (文件): 0x{crc:08x}")
    else:
        crc = get_crc(gc_path)
        print(f"CRC (计算): 0x{crc:08x}")
    
    print(f"上传文件...")
    try:
        with open(gc_path, 'rb') as f:
            files = {'config': f}
            data = {'crc': format(crc, '08x')}
            resp = requests.post(API_URL, files=files, data=data, verify=False, timeout=30)
        
        print(f"HTTP {resp.status_code}")
        
        if resp.status_code == 200:
            result = resp.json()
            print(f"响应: {json.dumps(result, indent=2)}")
            
            xor_key = result.get('xor_key', '')
            aes_key = result.get('aes_key', '')
            
            print(f"\n✅ 获取成功!")
            print(f"  XOR key: 0x{xor_key}")
            print(f"  AES key: {aes_key}")
            
            # 保存
            save_path = Path(__file__).parent.parent / 'config' / 'media_keys.txt'
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(f"# Media encryption keys\n")
                f.write(f"# 获取时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 来源: {API_URL}\n\n")
                f.write(f"XOR_KEY={xor_key}\n")
                f.write(f"AES_KEY={aes_key}\n")
            
            print(f"  已保存: {save_path}")
        else:
            print(f"❌ API 返回错误: {resp.text}")
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        print("   可能原因: 网络不通 / API 挂了 / 代理问题")
        print("   试试手动指定 global_config 路径")

if __name__ == '__main__':
    main()
