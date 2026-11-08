# -*- coding: utf-8 -*-
"""
微信 4.x 语音还原 (通用版)
==========================
从 media_0/1.db 的 VoiceInfo.voice_data 提取 SILK v3 BLOB,
解码成 MP3, 按会话+年月分目录, 生成 CSV 台账。

用法:
    python restore_voice.py <微信账号目录或 xwechat_files> <输出目录>

示例:
    python restore_voice.py "D:\\WeChat\\xwechat_files\\wxid_xxx_xxxx" "D:\\语音还原"

依赖:
    pip install pysilk        # SILK 解码 (有 Windows 预编译 wheel)
    ffmpeg 在 PATH 中          # WAV -> MP3
    (脚本只读源数据, 绝不改动微信目录)

原理:
    微信 4.x 的语音不是独立 .amr 文件, 而是存在 media_N.db 的
    VoiceInfo.voice_data BLOB 里, 格式为 0x02 + "#!SILK_V3" + SILK 流。
    ffmpeg 不支持 SILK, 需 pysilk (腾讯变体) 解码为 PCM,
    再经 WAV 转 MP3。采样率 24000Hz 单声道。
"""
import os, sys, sqlite3, io, wave, subprocess, csv, time, datetime, shutil
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

SAMPLE_RATE = 24000


def check_deps():
    """检查 pysilk / ffmpeg, 缺失则给出明确提示"""
    missing = []
    try:
        import pysilk  # noqa
    except ImportError:
        missing.append("pysilk  (安装: pip install pysilk)")
    if not shutil.which('ffmpeg'):
        missing.append("ffmpeg  (需加入 PATH, 用于 WAV->MP3; 没有也能只导 WAV)")
    return missing


def find_media_dbs(root):
    """找所有有效 media_N.db (兼容 factory 时间戳子目录 / 直接存放)"""
    dbs = []
    for base, dirs, files in os.walk(root):
        for f in files:
            if f.startswith('media_') and f.endswith('.db'):
                fp = os.path.join(base, f)
                try:
                    with open(fp, 'rb') as fh:
                        if fh.read(16).startswith(b'SQLite format 3'):
                            dbs.append(fp)
                except OSError:
                    pass
    return sorted(set(dbs))


def collect_voice_rows(dbs):
    """从所有 media 库读 VoiceInfo 语音 BLOB"""
    rows = []
    for db in dbs:
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            cur = conn.cursor()
            cur.execute("SELECT chat_name_id, create_time, local_id, svr_id, voice_data "
                        "FROM VoiceInfo WHERE voice_data IS NOT NULL")
            for r in cur:
                rows.append(r)
            conn.close()
        except sqlite3.Error as e:
            print(f"  [跳过] {os.path.basename(db)}: {e}")
    return rows


def load_chat_names(root):
    """尽量从 message_N.db 里取 chat_name_id -> 名称 映射 (失败不影响)"""
    names = {}
    for base, dirs, files in os.walk(root):
        for f in files:
            if not (f.startswith('message_') and f.endswith('.db')):
                continue
            try:
                c = sqlite3.connect(f"file:{os.path.join(base, f)}?mode=ro", uri=True, timeout=2)
                tabs = [t[0] for t in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                for t in tabs:
                    if t.lower() in ('chat_name', 'name2id', 'chat', 'contact', 'session'):
                        try:
                            for rr in c.execute(f"SELECT * FROM [{t}] LIMIT 500"):
                                names[str(rr[0])] = str(rr[1])[:40]
                        except sqlite3.Error:
                            pass
                c.close()
            except sqlite3.Error:
                pass
    return names


def _wav_to_mp3(wav_path, mp3_path, want_mp3):
    """WAV -> MP3, 返回错误串(空=成功)"""
    if not want_mp3:
        return ""
    try:
        r = subprocess.run(
            ['ffmpeg', '-y', '-loglevel', 'error', '-i', wav_path,
             '-codec:a', 'libmp3lame', '-qscale:a', '4', mp3_path],
            capture_output=True, timeout=60)
        if r.returncode != 0:
            return f"mp3: {r.stderr.decode(errors='replace')[:80]}"
        try:
            os.remove(wav_path)  # 删中间 WAV, 只留 MP3
        except OSError:
            pass
    except Exception as e:
        return f"mp3: {e}"
    return ""


def silk_to_audio(blob, wav_path, mp3_path, want_mp3):
    """微信语音 BLOB -> WAV (-> MP3), 返回 (时长秒, 成功?, 错误)

    支持两种封装:
      1) \x02#!SILK_V3 ...  -> pysilk 解码 (绝大多数, 13295 条)
      2) #!AMR\\n\\x02#!SILK_V3 ... -> AMR 外壳, ffmpeg 可直接解 (22 条)
         剥掉 '#!AMR\\n' 后也可交 pysilk, 二者皆可还原。
    """
    import pysilk

    # ---- 分支 A: AMR 外壳 (头 '#!AMR\\n') ----
    if blob[:6] == b'#!AMR\n' and shutil.which('ffmpeg'):
        tmp_amr = wav_path[:-4] + '.amr'
        try:
            with open(tmp_amr, 'wb') as fh:
                fh.write(blob)
            r = subprocess.run(
                ['ffmpeg', '-y', '-loglevel', 'error', '-i', tmp_amr,
                 '-ar', str(SAMPLE_RATE), '-ac', '1', wav_path],
                capture_output=True, timeout=60)
            if r.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 1000:
                dur = (os.path.getsize(wav_path) - 44) / 2 / SAMPLE_RATE
                err = _wav_to_mp3(wav_path, mp3_path, want_mp3)
                return (dur, not err, err)
        except Exception:
            pass
        finally:
            try:
                os.remove(tmp_amr)
            except OSError:
                pass
        # ffmpeg 失败则继续走 pysilk (剥掉 AMR 头)

    # ---- 分支 B: 标准 SILK v3 / 剥壳后的 SILK ----
    data = blob
    if blob[:6] == b'#!AMR\n':
        data = blob[6:]  # 去掉 AMR 外壳, 剩 \x02#!SILK_V3...
    pcm = b''
    # B1: 标准解码
    try:
        out = io.BytesIO()
        pysilk.decode(io.BytesIO(data), out, SAMPLE_RATE)
        pcm = out.getvalue()
    except Exception:
        pass
    # B2: 容错解码 (被截断的长语音, loss=True)
    if len(pcm) < 100:
        try:
            out = io.BytesIO()
            pysilk.decode(io.BytesIO(data), out, SAMPLE_RATE, loss=True)
            pcm = out.getvalue()
        except Exception:
            pass
    # B3: 手动切帧, 丢掉尾部残缺帧再解 (300KB 上限截断的长语音)
    if len(pcm) < 100 and len(data) > 10:
        header = data[:10]
        body = data[10:]
        frames, i = [], 0
        while i + 2 <= len(body):
            ln = int.from_bytes(body[i:i+2], 'little')
            if ln <= 0 or ln > 2000 or i + 2 + ln > len(body):
                break
            frames.append(body[i:i+2+ln])
            i += 2 + ln
        if frames:
            for payload in (header + b''.join(frames), b''.join(frames)):
                try:
                    out = io.BytesIO()
                    pysilk.decode(io.BytesIO(payload), out, SAMPLE_RATE)
                    if len(out.getvalue()) > 100:
                        pcm = out.getvalue()
                        break
                except Exception:
                    pass
    if len(pcm) < 100:
        return 0, False, "decode: INVALID (源数据可能截断/损坏)"
    dur = len(pcm) / 2 / SAMPLE_RATE
    try:
        with wave.open(wav_path, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm)
    except Exception as e:
        return 0, False, f"wav: {e}"
    err = _wav_to_mp3(wav_path, mp3_path, want_mp3)
    return dur, not err, err


def safe_name(s, fallback):
    s = "".join(c for c in s if c not in '\\/:*?"<>|').strip()[:40]
    return s or fallback


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("!! 需要两个参数: <微信账号目录> <输出目录>")
        sys.exit(1)
    root, outroot = sys.argv[1], sys.argv[2]

    print("=" * 72)
    print("  微信 4.x 语音还原")
    print(f"  源: {root}")
    print(f"  出: {outroot}")
    print("=" * 72)

    if not os.path.isdir(root):
        print(f"!! 源目录不存在: {root}")
        sys.exit(1)

    missing = check_deps()
    if missing:
        print("\n!! 缺少依赖:")
        for m in missing:
            print(f"   - {m}")
        print("   (若只想导 WAV, 可忽略 ffmpeg 提示)")
    want_mp3 = shutil.which('ffmpeg') is not None
    try:
        import pysilk  # noqa
    except ImportError:
        print("!! 必须先装 pysilk: pip install pysilk")
        sys.exit(1)

    os.makedirs(outroot, exist_ok=True)

    dbs = find_media_dbs(root)
    print(f"\n找到 {len(dbs)} 个有效 media 数据库")
    rows = collect_voice_rows(dbs)
    print(f"合计 {len(rows):,} 条语音")
    if not rows:
        print("没有语音可还原 (可能不是微信 4.x 目录, 或 VoiceInfo 表为空)")
        sys.exit(0)

    names = load_chat_names(root)
    print(f"会话名映射: {len(names)} 个")

    log_path = os.path.join(outroot, '语音台账.csv')
    log_rows, ok, fail = [], 0, 0
    by_ym = defaultdict(int)
    t0 = time.time()

    for idx, (chat_id, ctime, lid, svrid, blob) in enumerate(rows):
        try:
            dt = datetime.datetime.fromtimestamp(ctime)
            ym = dt.strftime('%Y-%m')
            timestr = dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, OSError, OverflowError):
            ym, timestr = '未知时间', str(ctime)

        cname = names.get(str(chat_id), f"会话_{chat_id}")
        sdir = os.path.join(outroot, ym, safe_name(cname, f"会话_{chat_id}"))
        os.makedirs(sdir, exist_ok=True)

        stem = f"{timestr.replace(':', '-').replace(' ', '_')}_{svrid}"
        mp3_path = os.path.join(sdir, stem + '.mp3')
        wav_path = os.path.join(sdir, stem + '.wav')

        final = mp3_path if want_mp3 else wav_path
        if os.path.exists(final) and os.path.getsize(final) > 1000:
            ok += 1
            by_ym[ym] += 1
            continue

        dur, success, err = silk_to_audio(blob, wav_path, mp3_path, want_mp3)
        if success:
            ok += 1
            by_ym[ym] += 1
            log_rows.append([timestr, ym, cname, chat_id, svrid, f"{dur:.2f}",
                             os.path.basename(final), "OK", ""])
        else:
            fail += 1
            log_rows.append([timestr, ym, cname, chat_id, svrid, f"{dur:.2f}",
                             "", "FAIL", err])

        if (idx + 1) % 500 == 0:
            print(f"  ... {idx + 1:,}/{len(rows):,}  成功 {ok:,} 失败 {fail:,}  "
                  f"{time.time() - t0:.0f}s")

    with open(log_path, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['时间', '年月', '会话', 'chat_id', 'svr_id', '时长(秒)', '文件名', '状态', '错误'])
        w.writerows(log_rows)

    el = time.time() - t0
    print(f"\n{'=' * 72}")
    print(f"  完成! 成功 {ok:,}  失败 {fail:,}  耗时 {el:.0f}s ({el / 60:.1f}min)")
    print(f"  输出: {outroot}")
    print(f"  台账: {log_path}")
    print(f"{'=' * 72}")
    print("\n按年月分布:")
    for ym in sorted(by_ym):
        print(f"  {ym}: {by_ym[ym]:>6,}")
    if fail:
        print("\n失败样本:")
        for r in [x for x in log_rows if x[7] == 'FAIL'][:10]:
            print(f"  {r[0]} {r[2]} -> {r[8][:60]}")


if __name__ == '__main__':
    main()
