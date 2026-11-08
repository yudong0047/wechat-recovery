---
name: restore-wechat-data
description: 从损坏/缺失的微信数据库恢复文字消息、图片和文件。当用户提到"微信数据库损坏""修复微信聊天记录""图片显示不出来""微信修复数据后老消息丢了""wechat recovery/restore/fix"或"weixin 恢复/修复"时触发。自动扫描全盘找 xwechat_files 目录 → 解密 message_*.db/media_*.db → XOR/V2 解密加密变种 .dat → 清缓存重启微信。支持多账号合并 (旧微信号的数据拷到当前目录)。仅 Windows。
---

# WeChat 数据恢复 Skill

## 何时使用
- 用户说微信"数据库损坏""修复数据后老消息没了"
- 图片/文件显示为黑框或空白
- 需要合并多份微信数据（旧电脑/旧硬盘/云备份）
- 想解密 message_*.db 导出聊天记录

## 核心流程

```
用户说"帮我恢复微信数据"
  → [1] 定位微信目录 (run scripts/deep_scan.py)
  → [2] 找主账号 xwechat_files, 列出所有 wxid_ 子目录
  → [3] 扫 .dat 加密格式 (run scripts/check_dat_headers.py)
  → [4] 判断问题类型:
        - 明文 .dat → 跑 re_encrypt_parallel.py
        - V2 格式 → 微信自己解, 不用动
        - 未知格式 → 报告 + 尝试 XOR
        - 文件不在磁盘 → 报告"物理缺失, 需外部备份"
  → [5] 解密 message_*.db/media_*.db (run scripts/decrypt_all_dbs.py)
  → [6] 清缓存 + 重启微信 (run scripts/clear_cache.py)
  → [7] 汇总报告: 恢复了多少消息/图片, 缺了多少
```

## 必须遵守的规则

### 密钥 (预填, 直接用)
- **XOR_KEY = 225 (0xe1)** — 所有 .dat 变种格式
- **AES_KEY = 6a27d958a2a01abf** — V2 格式
- **DB_KEY = 2893cdc3e8ef46dc8abd82e9c4c4b8907a8718d582724bbe9cd794f66b90b8ba** — WCDB/SQLCipher v4

### 绝对不能做
1. **不要把 .dat 覆盖成明文 JPG/PNG** — 微信打开会自动 XOR 0xe1, 明文→垃圾数据→黑框!
2. **不要改 V2 格式文件** (头 `07 08 V2 08 07`) — 微信内部有内置 AES key 会自己解
3. **不要删原始备份数据库** — decrypted/ 目录的 .db 是只读参考
4. **不要跳过清缓存** — .dat 改了必须清 cache/Thumb, 不然微信用旧缩略图

### 关键原理
- **WCDB = SQLCipher v4**: AES-256-CBC, page_size=4096, RESERVE=80 (IV16+HMAC64), PBKDF2-SHA512 256000 iter
- **微信 4.x message DB 路径**: `db_storage/message/message_0.db`, `db_storage/message/message_1.db` ... (不是直接在 db_storage 下)
- **微信 3.x message DB 路径**: `Msg/Multi/MSG0.db`, `Msg/MediaMSG0.db` (和 4.x 格式不同, key 也不同)
- **message DB 解密 key 是随机的!** — 不同账号 key 不同, 需要从 global_config 或 remote API 获取
- **辅助 DB (contact/session/general) key 是固定的**: `2893cdc3e8ef46dc8abd82e9c4c4b8907a8718d582724bbe9cd794f66b90b8ba`

## 脚本调用

所有脚本在 `scripts/` 目录下, 通过 `run.bat` 或直接 `python` 调用:

```bash
# 1. 全盘扫描
python scripts/deep_scan.py

# 2. 扫格式
python scripts/check_dat_headers.py [扫描目录]

# 3. 反向加密 (明文→加密, 让微信能解!)
python scripts/re_encrypt_parallel.py [目录]

# 4. XOR 解密 (加密→明文, 导出用, 慎用!)
python scripts/xor_decrypt_all.py [目录] [加后缀?]

# 5. 清缓存 + 重启微信
python scripts/clear_cache.py [缓存目录]

# 6. 批量解密数据库
python scripts/decrypt_all_dbs.py [db_storage目录] [输出目录] [key]

# 7. fetch remote API key
python scripts/fetch_v2_keys.py

# 8. 语音还原 (v1.1): media_N.db 的 SILK v3 BLOB -> MP3
pip install pysilk
python scripts/restore_voice.py "<微信账号目录>" "<输出目录>"
```

## 典型诊断场景

### 场景 1: 图片全黑框
```
check_dat_headers.py 输出很多 PLAIN-JPEG/PLAIN-PNG
→ 之前有人 (或之前的 DSH) 错误地把 .dat 解密后没加密回去
→ 运行 re_encrypt_parallel.py
→ 清缓存
```

### 场景 2: 老年份图片没有
```
deep_scan.py → 只有一个 xwechat_files
check_dat_headers.py → 格式全正确
→ 看看 .dat 文件的年月分布
→ 如果某年开始 0 文件: 微信修复时删掉了
→ 合并旧电脑/旧硬盘数据: robocopy src dst /E *.dat
→ 如果全电脑都没有: 物理文件丢失, 找外部备份
```

### 场景 4: 想导出语音消息 (v1.1)
```
用户说"语音能还原吗""语音消息导出""聊天里的语音在哪"
→ 关键认知: 微信 4.x 语音不是独立 .amr 文件!
   在 db_storage/message/media_N.db 的 VoiceInfo.voice_data BLOB
   格式 0x02 + "#!SILK_V3" + SILK 流
→ 全盘散落的 .amr SILK 文件大多是 QQ/TIM 的, 不是微信
→ 依赖: pip install pysilk (ffmpeg 可选, 用于 MP3)
→ 运行: python scripts/restore_voice.py <账号目录> <输出目录>
→ 输出: 按 年月/会话 分组的 MP3 + 语音台账.csv
→ 采样率 24000Hz 单声道; 纯只读, 不改动微信目录
```

### 场景 3: 数据库解密 key 不匹配
```
decrypt_all_dbs.py 报 HMAC mismatch
→ 这是微信 3.x 账号, key 和 4.x 不同
→ 用 fetch_v2_keys.py 从 remote API 拿 key
→ 或者从 global_config 里算
→ 或者用 WeChatDataAnalysis 的 DLL key scan
```

## 合并多份数据

从旧电脑拷数据过来 (只拷 .dat, 不覆盖):
```bash
robocopy "旧电脑\xwechat_files\微信ID\msg\attach" \
         "新电脑\xwechat_files\微信ID\msg\attach" \
         *.dat /E /R:1 /W:1
```

## 输出格式

报告必须包含:
1. **扫描到的目录列表** — 每个的大小和 wxid
2. **.dat 格式分布** — V2/XOR-JPEG/XOR-PNG/明文/未知 各多少
3. **按年月分布** — 最早哪年有文件
4. **恢复统计** — 解密成功多少 DB, 加密/解密了多少 .dat
5. **异常清单** — 哪些年完全没有, 哪些文件格式未知, 哪些 DB key 不匹配
6. **下一步建议** — 从哪合并, 外部备份在哪

## 依赖
- Python 3.10+
- requests (`pip install requests`)
- WeChatDataAnalysis (`pip install wechat-data-analysis`)
- pycryptodome 可选 (`pip install pycryptodome`)
- pysilk (`pip install pysilk`) — 语音还原 (v1.1)
- ffmpeg 可选 (加入 PATH, 语音 WAV→MP3)
- Windows only (微信仅 Windows)

## 语音还原技术要点 (v1.1)
- 位置: `db_storage/message/media_0.db.factory/<时间戳>/media_0.db`
  → 表 `VoiceInfo` → 列 `voice_data` (BLOB)
- 头: `02 23 21 53 49 4C 4B 5F 56 33` = `\x02#!SILK_V3`
- ffmpeg 8.x **不支持** SILK, 必须 `pysilk.decode()`
- `pysilk.decode()` 的 input 必须是 file-like (`io.BytesIO`), 传 bytes 会报
  `TypeError: input except a file-like object`
- 采样率 24000Hz；PCM s16le → WAV → (ffmpeg libmp3lame) MP3
- `media_0.db` 顶层那个文件是占位/损坏的, 要进 `.factory/<时间戳>/` 子目录
- 会话名从 `message_N.db` 的 `chat_name`/`name2id` 等表映射, 失败则回退 `会话_<id>`
