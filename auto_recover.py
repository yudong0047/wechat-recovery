"""
微信数据一键诊断 + 修复
把所有步骤合在一起: 扫描 → 判断 → 修复 → 清缓存
AI 辅助判断: 根据 .dat 格式分布自动决定怎么修
"""
import os, sys, time, stat, shutil
from pathlib import Path
from collections import Counter, defaultdict
from multiprocessing import Pool, cpu_count

sys.stdout.reconfigure(encoding='utf-8')

# ============= 配置区 =============
XOR_KEY = 0xE1          # .dat 变种格式 XOR key
AES_KEY = '6a27d958a2a01abf'  # V2 文件 AES key
DB_KEY_FIXED = "2893cdc3e8ef46dc8abd82e9c4c4b8907a8718d582724bbe9cd794f66b90b8ba"

SKIP_DIRS = {'Windows', 'Program Files', 'Program Files (x86)', 'ProgramData',
             'System Volume Information', '$Recycle.Bin', 'node_modules', 'WinSxS'}

DIAG = {'scan': True, 'encrypt': True, 'merge': False, 'decrypt_db': True,
        'clear_cache': True, 'dry_run': False}
# =================================

def step(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ========== Step 1: 全盘扫描 ==========
def find_wechat_dirs():
    step("[1/6] 全盘扫描微信数据目录")
    drives = [d for d in 'CDEFGHLM' if os.path.exists(f"{d}:\\")]
    found = []
    t0 = time.time()
    for drive in drives:
        print(f"  扫 {drive}:\\ ...")
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
                    # 里面的 wxid 子目录
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
                    tag = "📁" if 'xwechat' in name else "🆔"
                    print(f"    {tag} {size:8.1f} MB | {os.path.basename(root)}")
                    for wid, ws in wxids:
                        print(f"      └─ {ws:7.1f} MB | {wid}")
        except PermissionError: pass
    
    elapsed = time.time() - t0
    print(f"\n  扫描完成! {elapsed:.0f}s, 找到 {len(found)} 个目录")
    return found

# ========== Step 2: .dat 格式分布 ==========
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

def scan_dat_formats(root_dir):
    step(f"[2/6] 扫 .dat 格式分布 ({root_dir})")
    counts = Counter()
    sizes = defaultdict(int)
    year_counts = defaultdict(lambda: Counter())
    total = 0
    
    for f in Path(root_dir).rglob('*.dat'):
        try:
            with open(f, 'rb') as fh:
                hdr = fh.read(16)
            ftype = classify_header(hdr)
            fsize = f.stat().st_size
            counts[ftype] += 1
            sizes[ftype] += fsize
            total += 1
            import re
            m = re.search(r'(\d{4}-\d{2})', str(f))
            if m: year_counts[m.group(1)][ftype] += 1
            if total % 5000 == 0:
                print(f"    ... {total:,} 文件")
        except: counts["ERROR"] += 1
    
    print(f"\n  共 {total:,} 个 .dat 文件")
    print(f"  {'类型':<12} {'数量':>10} {'占比':>8} {'总大小':>10}")
    print("  " + "-" * 42)
    for ftype, cnt in counts.most_common():
        pct = cnt / total * 100 if total else 0
        mb = sizes[ftype] / 1024 / 1024
        print(f"  {ftype:<10} {cnt:>10,} {pct:>7.1f}% {mb:>9.0f} MB")
    
    # 按年份分布
    if year_counts:
        print(f"\n  按年份分布 (前15):")
        print(f"  {'年月':<10}", end="")
        for t in ['加密','明文','V2','未知']: print(f" {t:>8}", end="")
        print()
        print("  " + "-" * 50)
        for ym in sorted(year_counts.keys())[:15]:
            yc = year_counts[ym]
            enc = yc.get('XOR-JPEG',0) + yc.get('XOR-PNG',0)
            plain = yc.get('PLAIN-JPEG',0) + yc.get('PLAIN-PNG',0)
            print(f"  {ym:<10} {enc:>8,} {plain:>8,} {yc.get('V2',0):>8,} {yc.get('UNKNOWN',0):>8,}")
    
    return counts, sizes, year_counts, total

# ========== Step 3: AI 判断 ==========
def ai_diagnose(counts, year_counts, total):
    step("[3/6] AI 诊断")
    findings = []
    actions = []
    
    plain = counts.get('PLAIN-JPEG',0) + counts.get('PLAIN-PNG',0)
    v2 = counts.get('V2',0)
    unknown = counts.get('UNKNOWN',0)
    encrypted = counts.get('XOR-JPEG',0) + counts.get('XOR-PNG',0)
    
    # 类型 A: 明文
    if plain > total * 0.05:
        findings.append(f"⚠️ {plain:,} 个明文文件! ({plain/total*100:.1f}%)")
        findings.append("   微信打开会自动 XOR → 明文变垃圾 → 显示黑框")
        actions.append("跑 re_encrypt_parallel.py 加密回去")
    
    # 类型 B: V2 异常
    if v2 > 0:
        findings.append(f"ℹ️ {v2:,} 个 V2 文件 — 微信内部有 AES key 会自动解")
        findings.append("   不要手动改 V2! 除非确实需要导出")
    
    # 类型 C: 未知
    if unknown > 0:
        findings.append(f"❓ {unknown:,} 个未知格式!")
        findings.append("   微信也解不开, 可能是损坏或其他加密方式")
        actions.append("尝试 fetch_v2_keys.py 拿新 key")
    
    # 类型 D: 物理缺失
    if year_counts:
        ym_list = sorted(year_counts.keys())
        first = ym_list[0] if ym_list else None
        last = ym_list[-1] if ym_list else None
        
        # 检查断档
        gaps = []
        for i in range(1, len(ym_list)):
            ym_prev = ym_list[i-1]
            ym_curr = ym_list[i]
            if ym_curr[:4] == ym_prev[:4]:
                if int(ym_curr[5:7]) - int(ym_prev[5:7]) > 1:
                    gaps.append(f"{ym_prev} → {ym_curr}")
            else:
                gaps.append(f"{ym_prev} → {ym_curr}")
        
        if gaps:
            findings.append(f"⚠️ 断档: {', '.join(gaps[:3])}")
            findings.append("   这些月份的文件可能被微信修复时删掉了")
            actions.append("从旧电脑/旧硬盘/云盘合并数据 (robocopy)")
        
        # 最早年份
        findings.append(f"📅 .dat 覆盖: {first} ~ {last}")
        
        # 统计各年份
        ystats = defaultdict(int)
        for ym, yc in year_counts.items():
            ystats[ym[:4]] += sum(yc.values())
        for yr, cnt in sorted(ystats.items()):
            print(f"    {yr}: {cnt:,} 文件")
    
    # 类型 E: 主账号有明文, 旧账号全加密
    if encrypted > plain * 20 and encrypted > 1000:
        findings.append(f"✅ {encrypted:,} 个加密文件 (正常, 微信能解)")
        findings.append("   只有少量明文需要修复")
    
    print(f"\n  📋 发现:")
    for f in findings: print(f"    {f}")
    print(f"\n  🛠️  建议操作:")
    for i, a in enumerate(actions, 1): print(f"    {i}. {a}")
    
    return actions

# ========== Step 4: 自动加密 ==========
def auto_encrypt(root_dir, counts):
    step("[4/6] 自动加密 (明文→加密变种)")
    plain = counts.get('PLAIN-JPEG',0) + counts.get('PLAIN-PNG',0)
    if plain == 0:
        print("  ✅ 没有明文文件, 跳过")
        return
    
    print(f"  发现 {plain:,} 个明文文件, 开始加密...")
    
    files = []
    for f in Path(root_dir).rglob('*.dat'):
        try:
            with open(f, 'rb') as fh:
                hdr = fh.read(4)
            if hdr[:3] == b'\xff\xd8\xff' or hdr[:4] == b'\x89PNG':
                files.append(str(f))
        except: pass
    
    print(f"  待加密: {len(files):,} 个文件")
    
    def encrypt_one(fpath):
        try:
            with open(fpath, 'rb') as f: data = f.read()
            enc = bytes(b ^ XOR_KEY for b in data)
            os.chmod(fpath, stat.S_IWRITE | stat.S_IREAD)
            with open(fpath, 'wb') as f: f.write(enc)
            return (fpath, 'OK', len(data))
        except: return (fpath, 'ERR', 0)
    
    ok = err = 0
    t0 = time.time()
    with Pool(min(8, cpu_count())) as pool:
        for result in pool.imap_unordered(encrypt_one, files, chunksize=100):
            _, status, _ = result
            if status == 'OK': ok += 1
            else: err += 1
            if (ok+err) % 5000 == 0:
                print(f"    {ok+err:,}/{len(files):,} | OK={ok:,} | ERR={err:,}")
    
    print(f"\n  ✅ 加密完成! {ok:,} 成功, {err:,} 失败, 耗时 {time.time()-t0:.0f}s")

# ========== Step 5: 解密数据库 ==========
def decrypt_dbs(root_dir, out_dir):
    step("[5/6] 解密数据库")
    db_dir = Path(root_dir) / 'db_storage'
    if not db_dir.exists():
        # 往上一级找
        for wxid in Path(root_dir).parent.glob('wxid_*'):
            candidate = wxid / 'db_storage'
            if candidate.exists():
                db_dir = candidate
                break
    
    if not db_dir.exists():
        print(f"  ⚠️ 找不到 db_storage 目录, 跳过 DB 解密")
        return
    
    try:
        sys.path.insert(0, r"<WeChatDataAnalysis>\src")
        from wechat_decrypt_tool.wechat_decrypt import WeChatDatabaseDecryptor
    except ImportError:
        print("  ⚠️ WeChatDataAnalysis 未安装, 跳过 DB 解密")
        return
    
    all_dbs = list(db_dir.rglob('*.db'))
    print(f"  找到 {len(all_dbs)} 个 .db 文件")
    
    decryptor = WeChatDatabaseDecryptor(DB_KEY_FIXED)
    ok = fail = skip = 0
    
    for dbf in all_dbs:
        if dbf.suffix in ['.wal', '.shm', '.journal']: skip += 1; continue
        out_path = Path(out_dir) / f"{dbf.stem}.dec.db"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        if out_path.exists() and out_path.stat().st_size > 100:
            skip += 1
            continue
        
        try:
            decryptor.decrypt_database(str(dbf), str(out_path))
            if out_path.stat().st_size > 100:
                ok += 1
                print(f"    ✅ {dbf.name}")
            else:
                fail += 1
                os.remove(str(out_path))
                print(f"    ❌ {dbf.name} (key 不匹配)")
        except Exception as e:
            fail += 1
            print(f"    ❌ {dbf.name}: {str(e)[:40]}")
    
    print(f"\n  ✅ DB 解密: {ok} 成功, {fail} 失败 (key 不匹配), {skip} 跳过")
    if ok > 0:
        print(f"  输出: {out_dir}")
        print("  用 DB Browser for SQLite / sqlite3 打开即可看聊天记录")

# ========== Step 6: 清缓存 + 重启 ==========
def clear_cache_and_restart(root_dir):
    step("[6/6] 清缓存 + 重启微信")
    
    # 找 cache 目录
    cache_dir = None
    for wxid in Path(root_dir).parent.glob('wxid_*'):
        cd = wxid / 'cache'
        if cd.exists():
            cache_dir = cd
            break
    
    if not cache_dir:
        print("  ⚠️ 找不到 cache 目录, 跳过清缓存")
        return
    
    print(f"  cache: {cache_dir}")
    
    # 关微信
    import subprocess
    try:
        subprocess.run(['taskkill', '/F', '/IM', 'WeChat.exe'], 
                      capture_output=True, timeout=10)
        print("  ✅ 已关闭微信")
    except: pass
    time.sleep(2)
    
    # 清 Thumb
    total = 0
    for thumb in cache_dir.rglob('Thumb'):
        for root, dirs, files in os.walk(thumb):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                    total += 1
                except: pass
    print(f"  ✅ 清除 {total:,} 个缩略图缓存")
    
    # 清 .thumb
    for f in cache_dir.rglob('*.thumb'):
        try: os.remove(str(f))
        except: pass
    
    # 重启微信
    for wechat in [
        r"D:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
        r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
    ]:
        if os.path.exists(wechat):
            subprocess.Popen([wechat])
            print(f"  ✅ 已启动微信")
            return
    
    print("  ⚠️ 找不到 WeChat.exe, 请手动启动")

# ========== 主流程 ==========
def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║          微信数据一键诊断 + 修复 v2.0                    ║")
    print("║     AI 自动判断问题 → 自动修复 → 自动清缓存              ║")
    print("╚══════════════════════════════════════════════════════════╝")
    
    if DIAG['dry_run']:
        print("\n⚠️  DRY RUN 模式: 只扫描, 不修复")
    
    # Step 1: 扫描
    found = find_wechat_dirs()
    if not found:
        print("\n❌ 全盘没找到任何 xwechat_files / WeChat Files 目录!")
        print("   微信可能装在非标准路径, 手动指定: python auto_recover.py [路径]")
        return
    
    # 选最大的那个目录 (主账号)
    main_dir = sys.argv[1] if len(sys.argv) > 1 else \
        max(found, key=lambda x: x[1])[0]
    
    print(f"\n🎯 主目录: {main_dir}")
    
    # Step 2: 扫格式
    counts, sizes, year_counts, total = scan_dat_formats(main_dir)
    
    # Step 3: AI 诊断
    actions = ai_diagnose(counts, year_counts, total)
    
    # Step 4: 自动加密
    if DIAG['encrypt'] and not DIAG['dry_run']:
        auto_encrypt(main_dir, counts)
    
    # Step 5: DB 解密
    if DIAG['decrypt_db'] and not DIAG['dry_run']:
        out_dir = Path(main_dir).parent.parent / 'toolkit_decrypted'
        decrypt_dbs(main_dir, str(out_dir))
    
    # Step 6: 清缓存
    if DIAG['clear_cache'] and not DIAG['dry_run']:
        clear_cache_and_restart(main_dir)
    
    # ========== 最终报告 ==========
    print(f"\n{'='*60}")
    print("  📊 最终报告")
    print(f"{'='*60}")
    print(f"  扫描目录: {main_dir}")
    print(f"  .dat 总数: {total:,}")
    print(f"  加密正常: {counts.get('XOR-JPEG',0)+counts.get('XOR-PNG',0):,}")
    print(f"  V2 (微信自解): {counts.get('V2',0):,}")
    print(f"  明文 (已加密): {counts.get('PLAIN-JPEG',0)+counts.get('PLAIN-PNG',0):,}")
    print(f"  未知: {counts.get('UNKNOWN',0):,}")
    
    if year_counts:
        ym_list = sorted(year_counts.keys())
        print(f"\n  📅 覆盖年份: {ym_list[0]} ~ {ym_list[-1]}")
        
        # 哪年断档
        gaps = []
        for i in range(1, len(ym_list)):
            prev = ym_list[i-1]
            curr = ym_list[i]
            if curr[:4] == prev[:4]:
                if int(curr[5:7]) - int(prev[5:7]) > 1:
                    gaps.append(f"{prev} → {curr}")
            else:
                print(f"  ⚠️ 年份跳断: {prev} → {curr}")
        
        if gaps:
            print(f"  ⚠️ 月份断档: {', '.join(gaps[:3])}")
            print(f"     这些月份的 .dat 文件物理缺失!")
            print(f"     需要从外部备份合并")
    
    print(f"\n  🎯 建议下一步:")
    for action in actions:
        print(f"    • {action}")
    
    print(f"\n  ✅ 打开微信, 翻聊天记录, 看看图片出来了没!")

if __name__ == '__main__':
    main()
