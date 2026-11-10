# 微信「迁移与备份」RMFH 漫游备份包 — 逆向分析与恢复路径

> 版本：v1.0（2026-11-11）
> 适用：微信 PC 端「迁移与备份 → 备份聊天记录至电脑」产出的备份包
> 结论先行：**备份包本体加密无法离线解出（密钥为一次性、服务器参与协商）；找回历史数据应走「源设备数据库直取」而非破解备份包。**

---

## 一、备份包是什么

微信 PC 端「迁移与备份 → 备份聊天记录至电脑」会在你指定的位置生成一个目录：

```
<备份根>\wxid_xxxx\
  roam_device_info.dat          ← 漫游设备标识（明文 protobuf + ECDSA 签名）
  <32位hex>\
    alt_name.dat / backup.attr
    files\<包号>\
      backup_time.dat / detail.dat / phoneid.dat / phone_history.dat
      pkg.attr / pkg_info.dat / tar_index.dat
      <会话目录>\
        ChatPackage\<起毫秒>-<止毫秒>    ← 聊天记录正文（加密）
        Index\<起毫秒>-<止毫秒>          ← 索引（加密）
        Media\<起毫秒>-<止毫秒>.tar.enc  ← 媒体包（加密）
        Media\<msgId>_l                  ← 图片（加密）
        Media\<msgId>_m                  ← 语音（加密）
```

- 同一账号可有多份备份，`files\` 下的**包号**（1/2/3/4/5…）区分
- `pkg_info.dat` 是**明文 protobuf**，可直接读出：`WXGBACKUPPACKAGEPREFIX_聊天 N`、备份账号 `xxx@ilink.im.sdk`、来源设备名（如 `User-2023MDOGPN` / `家里主机`）、`source_device_id`

---

## 二、RMFH 容器结构（已实测）

每个内容文件都是同一套布局：

```
[ 128 字节 RMFH 头 ][ 正文(密文) ][ 128 字节 RMFT 尾 ]
```

**RMFH 头（128B）**
- `52 4d 46 48` = `RMFH`
- `cc 9d 3d 60` = 固定魔数（全包相同，非时间戳）
- `01 00 01 xx` = 版本 + 类型码：`0x80` 媒体 / `0x8f` ChatPackage / `0x92` Index 与元数据
- `[20:32]` = 12 字节 per-file nonce（末字节恒为 `00`）

**RMFT 尾（128B）**
- `52 4d 46 54` = `RMFT`，`a7 26 b7 33` = 固定魔数
- `[10:26]` = 16 字节（疑似 GCM tag）

**判定是否为加密**：正文熵 ≈ 8.000 bits/byte（满熵），zstd / zlib / gzip / raw-deflate / lz4 全部解压失败 → **完全加密，非压缩**。

---

## 三、加密机制（从 roam_server.dll 源码字符串还原）

`roam_server.dll` 带编译路径的调试字符串，把整套栈钉死：

| 环节 | 实现 | 出处 |
|---|---|---|
| 压缩 | LZ4 | `adam_packer_utils.cpp` → `Lz4Compress failed` |
| 加密 | AES-GCM（mbedtls） | `adam_crypto_utils.cpp` → `aes_gcm_encrypt/decrypt` |
| 密钥 | sessionkey | `not have sessionkey yet!` |
| 派生 | HKDF → 48 字节 | `ilink_device_instance_impl.cpp` → `cloudsessionkey. HKDF result is not 48!!` |
| 密钥材料 | rdmkey + svrrdmkey | `rdmkey or svrrdmkey is empty just reset sesssioninfo!` |
| svrrdmkey 来源 | **服务器（ECDH 握手）** | `adam_ecdh_client.cpp` → `calculate_session_key_from_cloud_handshake` → `ReceiveCloudHandShakeResponse` |
| 服务器公钥 | P-256 ECDSA（硬编码 PEM） | `cloud_svr_ecdsa_pub_key` |

**密钥协商流程**：
```
设备生成 device_random + ECDH 密钥对
  → 发给服务器（GenerateCloudHandShakePacket）
  → 服务器返回 svrrdmkey + ECDH 公钥
  → 双方算出 ECDH 共享密钥
  → sessionkey = HKDF(rdmkey, svrrdmkey) → 48 字节
  → 每个文件用 sessionkey 派生 per-file key，LZ4 压缩 + AES-GCM 加密
```

---

## 四、为什么离线解不开（关键认知）

1. **svrrdmkey 是服务器在一次 ECDH 握手时下发的随机数，不落盘、不在备份包内**。
2. **每次备份都是全新握手、全新 sessionkey**：实测同一设备两次备份的 `roam_device_info.dat` 后半段（密钥材料）完全不同 → 每次备份的 key 用完即弃。
3. `roam_device_info.dat` 里虽有两个 32 字节值，但经穷举（HKDF 547 组合、X25519 ECDH 双向、AES-GCM 约 5000 组合）**均不能解密正文** —— 它们不是 rdmkey+svrrdmkey 那对。
4. 已知 PC 端三把密钥（XOR 225 / AES `6a27…` / WCDB `2893cd…`）**与本备份包无关**（那是本机 `.dat`/`.db` 的体系）。

**结论：离线破解 RMFH 备份包在数学上不可行**——密钥的一半在腾讯服务器手里，且每次备份都换。

---

## 五、动态抓密钥的可行性（已验证受限）

- `roam_server.dll` 为**按需加载**：只在真正触发「恢复/备份」时才进内存。
- 本机抓包尝试（frida）：被微信 **TenProtect 反调试**拦截（`Unable to allocate target memory`），用户态注入不可行。
- 即便抓到，也只能拿到**当前这次握手的 sessionkey**——它只能解**当前这次备份**，**解不了历史旧备份**（旧 key 已随那次握手消亡）。

**结论：动态抓密钥对「解历史备份」无效**，只能解「现在正在做的这次备份」。

---

## 六、正确的找回历史数据路径（重要）

**不要试图破解备份包。** 找回历史聊天记录/媒体的正确顺序：

1. **首选：源设备数据库直取**
   如果原设备（手机或电脑）微信里记录还在，直接操作它的**本地数据库**（`xwechat_files\wxid_xxx\db_storage\message\message_*.db`），
   用本工具包的 WCDB 密钥（`2893cd…`）解密导出 —— 这绕开了备份包加密，直连数据源。

2. **次选：源设备 → 手机 → 目标设备**
   源设备微信「迁移聊天记录到手机」→ 手机「备份到电脑」→ 目标电脑。
   全程官方功能，零风险。

3. **备份包「恢复」的真实行为**
   - 微信 4.2 的「备份与恢复」：备份=手机→电脑，恢复=电脑→手机，**无「恢复到本机电脑」入口**
   - 「导入较早版本的备份」：仅支持 **4.0.0 以下**旧格式，当前 4.2 的备份认不出

4. **备份包媒体覆盖可能不全**
   实测某账号 2016-2018 三年媒体仅 0.6 GB，而 2020 年一年就 0.56 GB——**早期媒体备份可能不全**（换机/未全选/微信策略）。源设备数据库通常更全。

---

## 七、实用工具

本仓库相关脚本（见 `D:\DSH Desktop\应用开发\wechat_import_2026\`，可归档至此）：

| 脚本 | 作用 |
|---|---|
| `inventory_L.py` | 盘点备份包：会话数、ChatPackage、Media 数、时间跨度 |
| `layout_probe.py` | 验证 RMFH…RMFT 容器布局 + 解 pkg_info.dat 明文 protobuf |
| `body_test.py` | 判定正文是压缩还是加密（熵 + zstd/zlib/lz4 穷举） |
| `re4_dll.py` / `re5_anchor.py` / `re6_sessionkey.py` | roam DLL crypto 依赖与密钥派生链定位 |
| `re11_pe.py` / `re12_xref.py` / `re13_disasm.py` | PE 结构 / 字符串 xref / 加密函数反汇编 |

**Python 依赖**：`D:\tool\Python314\python.exe`（需 `cryptography`、`zstandard`、`capstone`；默认 python 无）。

---

## 八、一句话总结

> **RMFH 备份包 = 一次性密钥 + 服务器协商，离线不可解、动态只能抓当次。找回历史数据，永远优先取源设备本地数据库，其次走官方迁移，不要试图破解备份包。**
