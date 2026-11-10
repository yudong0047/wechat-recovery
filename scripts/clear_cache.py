"""
清微信缩略图缓存 + 重启微信
1. 关闭微信进程
2. 删除 cache 目录下的 Thumb 缓存
3. 重新启动微信
"""
import os, sys, time
from pathlib import Path
import subprocess

sys.stdout.reconfigure(encoding='utf-8')

DEFAULT_CACHE_DIR = Path(r"D:\WeChat\xwechat_files\wxid_XXXXXXXXXXXX_a13f\cache")

def kill_wechat():
    """关闭微信"""
    print("[1/3] 关闭微信...")
    try:
        result = subprocess.run(
            ['taskkill', '/F', '/IM', 'WeChat.exe'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("  ✅ 已关闭微信")
        else:
            print("  (微信没在运行)")
    except Exception as e:
        print(f"  ⚠️ 关闭失败: {e}")
    time.sleep(2)

def clear_cache(cache_dir):
    """清缩略图缓存"""
    print(f"[2/3] 清缓存: {cache_dir}")
    
    total_files = 0
    total_size = 0
    
    # 删除整个 cache 目录下的文件
    if cache_dir.exists():
        # 只删 Thumb 相关的, 保留配置
        for thumb_dir in cache_dir.rglob('Thumb'):
            for root, dirs, files in os.walk(thumb_dir):
                for f in files:
                    fpath = os.path.join(root, f)
                    try:
                        size = os.path.getsize(fpath)
                        os.remove(fpath)
                        total_files += 1
                        total_size += size
                    except Exception as e:
                        print(f"    删不掉 {fpath}: {e}")
        
        # 也删所有 .thumb 文件
        for f in cache_dir.rglob('*.thumb'):
            try:
                size = os.path.getsize(str(f))
                os.remove(str(f))
                total_files += 1
                total_size += size
            except:
                pass
        
        # 删 cache/Message 下的文件 (微信的消息缓存)
        for msg_cache in cache_dir.rglob('Message'):
            for root, dirs, files in os.walk(msg_cache):
                for f in files:
                    fpath = os.path.join(root, f)
                    try:
                        size = os.path.getsize(fpath)
                        os.remove(fpath)
                        total_files += 1
                        total_size += size
                    except:
                        pass
    
    print(f"  ✅ 清除 {total_files:,} 个文件 ({total_size/1024/1024:.0f} MB)")

def start_wechat():
    """启动微信"""
    print("[3/3] 启动微信...")
    
    # 找 WeChat.exe
    candidates = [
        r"D:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
        r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
        r"D:\WeChat\WeChat.exe",
    ]
    
    wechat_exe = None
    for c in candidates:
        if os.path.exists(c):
            wechat_exe = c
            break
    
    if wechat_exe:
        try:
            subprocess.Popen([wechat_exe])
            print(f"  ✅ 已启动: {wechat_exe}")
        except Exception as e:
            print(f"  ⚠️ 启动失败: {e}")
    else:
        # 尝试用开始菜单
        try:
            subprocess.Popen(['cmd', '/c', 'start', '', 'WeChat'])
            print("  ✅ 已启动 WeChat")
        except:
            print("  ⚠️ 找不到 WeChat.exe, 请手动启动")

def main():
    cache_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CACHE_DIR
    
    print("=== 清缓存 + 重启微信 ===")
    print(f"缓存目录: {cache_dir}")
    print()
    
    kill_wechat()
    time.sleep(1)
    clear_cache(cache_dir)
    start_wechat()
    
    print("\n✅ 完成! 微信现在正在重新扫描媒体文件生成缩略图")
    print("   打开聊天记录, 翻到老年份, 图片应该能出来了!")

if __name__ == '__main__':
    main()
