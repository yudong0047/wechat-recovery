"""
批量解密所有微信 .db 文件
用 WeChatDatabaseDecryptor (WCDB/SQLCipher v4)
"""
import os, sys, time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, r"<WeChatDataAnalysis>\src")

try:
    from wechat_decrypt_tool.wechat_decrypt import WeChatDatabaseDecryptor
except ImportError:
    print("需要 WeChatDataAnalysis 工具!")
    print("  pip install wechat-data-analysis")
    print(r"  或指定 <WeChatDataAnalysis>\src 在 PYTHONPATH")
    sys.exit(1)

def main():
    db_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(r"D:\WeChat\xwechat_files\wxid_XXXXXXXXXXXX_a13f\db_storage")
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else \
        Path(r"D:\WeChat\decrypted")
    key = sys.argv[3] if len(sys.argv) > 3 else \
        "2893cdc3e8ef46dc8abd82e9c4c4b8907a8718d582724bbe9cd794f66b90b8ba"
    
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"=== 解密数据库 ===")
    print(f"源: {db_dir}")
    print(f"输出: {out_dir}")
    print(f"KEY: {key[:16]}...")
    
    # 找所有 .db
    all_dbs = []
    if db_dir.is_dir():
        for f in db_dir.rglob('*.db'):
            all_dbs.append(f)
    elif db_dir.suffix == '.db':
        all_dbs.append(db_dir)
    
    print(f"\n找到 {len(all_dbs)} 个 .db 文件")
    
    decryptor = WeChatDatabaseDecryptor(key)
    
    ok = fail = skip = 0
    t0 = time.time()
    
    for dbf in all_dbs:
        # 跳过 -wal/-shm/-journal
        if dbf.suffix in ['.wal', '.shm', '.journal']:
            skip += 1
            continue
        
        out_path = out_dir / f"{dbf.stem}.dec.db"
        
        if out_path.exists() and out_path.stat().st_size > 100:
            skip += 1
            print(f"  ⏭️ 已存在: {out_path.name}")
            continue
        
        size_mb = dbf.stat().st_size / 1024 / 1024
        
        try:
            decryptor.decrypt_database(str(dbf), str(out_path))
            out_size = out_path.stat().st_size / 1024 / 1024
            if out_size > 100:
                ok += 1
                print(f"  ✅ {dbf.name} ({size_mb:.1f} MB → {out_size:.1f} MB)")
            else:
                fail += 1
                os.remove(str(out_path))
                print(f"  ❌ {dbf.name} (key 不匹配)")
        except Exception as e:
            fail += 1
            print(f"  ❌ {dbf.name}: {e}")
    
    elapsed = time.time() - t0
    
    print(f"\n{'='*50}")
    print(f"完成! {elapsed:.0f}s")
    print(f"  ✅ 成功: {ok}")
    print(f"  ❌ 失败: {fail} (key 不匹配或损坏)")
    print(f"  ⏭️ 跳过: {skip} (已存在或非 DB)")
    print(f"\n解密后的数据库在: {out_dir}")
    print("  可以用 sqlite3 / DB Browser for SQLite 打开")

if __name__ == '__main__':
    main()
