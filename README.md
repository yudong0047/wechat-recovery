# 微信数据恢复工具包 v1.0

## 📦 工具包内容

```
WeChatRecoveryToolkit/
├── run.bat                    ← 双击这个! 菜单式界面
├── README.md                  ← 本文件
├── config/
│   └── media_keys.txt         ← 加密密钥 (已预填)
├── scripts/
│   ├── deep_scan.py           ← 全盘搜微信数据目录
│   ├── check_dat_headers.py   ← 扫描 .dat 加密格式分布
│   ├── xor_decrypt_all.py     ← XOR 解密 (明文→图片, 导出用)
│   ├── re_encrypt_parallel.py ← 反向加密 (明文→加密, 让微信能解!) ⭐核心
│   ├── v2_decrypt.py          ← V2 文件 AES+XOR 解密
│   ├── fetch_v2_keys.py       ← remote API 自动拿 AES/XOR key
│   ├── clear_cache.py         ← 清缩略图缓存 + 重启微信
│   └── decrypt_all_dbs.py     ← 批量解密 .db (WCDB/SQLCipher)
├── reference/
│   ├── wechat_encryption.md   ← 加密原理详解
│   └── troubleshooting.md     ← 常见问题排查
└── tools/
    └── (放 WeChatDataAnalysis wheel)
```

## 🚀 快速上手

### 场景 A: 拷到新电脑上，发现老数据在别处

```bat
1. 双击 run.bat
2. 选 [1] 全盘扫描 → 自动找所有 xwechat_files 目录
3. 选 [9] 合并数据 → 把其他目录的 .dat 拷贝过来
4. 选 [8] 一键全流程 → 自动加密 + 清缓存 + 重启微信
5. 翻聊天记录 → 图片出来了!
```

### 场景 B: 微信显示"数据库损坏"修复后图片黑框

```bat
1. 关微信
2. 选 [4] 反向加密 → 把明文 .dat XOR 回加密格式
3. 选 [7] 清缓存 + 重启微信
4. 图片应该能显示了
```

### 场景 C: 想导出图片做备份

```bat
1. 选 [3] XOR 解密 → 加密 .dat 变明文 JPG/PNG
2. 选 [5] V2 解密 → V2 文件也要解
3. ⚠️ 但解完一定要记得重新加密回去! (选 [4])
```

## 🔑 密钥说明

| Key | 值 | 用途 |
|-----|-----|------|
| **XOR_KEY** | `225` (0xe1) | 变种格式 .dat 加密 |
| **AES_KEY** | `6a27d958a2a01abf` | V2 格式 .dat AES 解密 |
| **DB_KEY** | `2893cdc3e8ef46dc8abd82e9c4c4b8907a8718d582724bbe9cd794f66b90b8ba` | 数据库 WCDB 加密 |

## ⚠️ 关键注意事项

### 1. 永远不要把 .dat 覆盖成明文 JPG!
微信打开 .dat 会**自动 XOR 0xe1**。如果是明文 JPG：
```
明文 JPG (FF D8 FF) → XOR 0xe1 → 垃圾数据 (1E 39 1E) → 显示黑框!
```
必须保持加密变种格式：
```
加密 (1E 39 1E) → XOR 0xe1 → 明文 JPG (FF D8 FF) → 正常显示 ✅
```

### 2. 清缓存一定要做!
微信的缩略图缓存在 `cache/Thumb/` 里。任何 .dat 修改后必须清缓存，不然微信用旧缓存显示，看不到最新效果。

### 3. V2 文件微信自己会解
V2 格式 (`07 08 V2 08 07`) 微信内部有内置 AES key，会自动解密。
**不要手动改 V2 文件！** 除非确实需要导出。

### 4. 数据库恢复
微信 4.x 用 WCDB = SQLCipher v4。如果 message_*.db 丢了，可以从原始备份恢复（记得重新加密）。

## 🔧 依赖

| 依赖 | 用途 | 安装 |
|------|------|------|
| Python 3.10+ | 主脚本 | 预装 |
| requests | remote API | `pip install requests` |
| WeChatDataAnalysis | DB 解密 | `pip install wechat-data-analysis` |
| pycryptodome | AES 解密 (可选) | `pip install pycryptodome` |

## 📞 故障排查

**Q: 脚本报错 "File not found"**
A: 改 run.bat 里的 `WECHAT_DIR` 为实际路径

**Q: 数据库解密失败 HMAC mismatch**
A: KEY 不对！微信 3.x 和 4.x 密钥不同。4.x 的 DB_KEY 是固定的：`2893cdc3e8ef46dc8abd82e9c4c4b8907a8718d582724bbe9cd794f66b90b8ba`

**Q: 加密后还是看不到**
A: 1) 检查文件头是不是真的加密了 → 看 run.bat [2] 格式扫描
   2) 清缓存 → 选 [7]
   3) 重启微信

**Q: 2016-2019 的图片确实没了？**
A: 微信"修复数据"时删除了磁盘文件。必须从外部备份（压缩包/云盘/旧硬盘）恢复。

## 📝 更新日志

- **v1.0** (2026-11-08) — 初始版本，基于 wxid_db7cm2zc6ou321 主账号测试
