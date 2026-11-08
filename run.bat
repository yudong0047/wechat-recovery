@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   微信数据恢复工具包 v1.0
echo   WeChat Data Recovery Toolkit
echo ========================================
echo.

REM ====== 配置 ======
set "PYTHON=D:\tool\Python314\python.exe"
set "WORKDIR=%~dp0"
set "WECHAT_DIR=D:\tool\WeChat\聊天记录\xwechat_files"
set "KEY_INFO=2893cdc3e8ef46dc8abd82e9c4c4b8907a8718d582724bbe9cd794f66b90b8ba"

:MENU
echo.
echo 请选择要执行的操作:
echo.
echo   [1] 全盘扫描微信数据目录 (找 xwechat_files / wxid_ 目录)
echo   [2] 扫描 .dat 文件加密格式分布 (V2 / 变种 / 明文)
echo   [3] XOR 批量解密 .dat (老版本图片, key=0xe1)
echo   [4] 反向加密 .dat (明文→加密, 让微信能解)
echo   [5] AES + XOR 解密 V2 文件 (需要 AES key)
echo   [6] 用 remote API 自动获取 AES/XOR key
echo   [7] 清微信缩略图缓存 + 重启微信
echo   [8] 一键全流程: 扫描→解密→加密→清缓存
echo   [9] 合并多份微信数据 (从其他目录拷贝 .dat)
echo  [10] 解密 message_*.db / media_*.db (导出聊天内容)
echo  [11] 检查文件权限 + 修复只读属性
echo  [12] 退出
echo.
set /p choice=请输入编号: 

if "%choice%"=="1" goto SCAN
if "%choice%"=="2" goto CHECK
if "%choice%"=="3" goto XOR_DECRYPT
if "%choice%"=="4" goto RE_ENCRYPT
if "%choice%"=="5" goto V2_DECRYPT
if "%choice%"=="6" goto FETCH_KEY
if "%choice%"=="7" goto CLEAR_CACHE
if "%choice%"=="8" goto FULL_AUTO
if "%choice%"=="9" goto MERGE
if "%choice%"=="10" goto DECRYPT_DB
if "%choice%"=="11" goto FIX_PERM
if "%choice%"=="12" goto END
goto MENU

:SCAN
echo.
echo === 全盘扫描微信数据目录 ===
"%PYTHON%" "%WORKDIR%scripts\deep_scan.py"
goto MENU

:CHECK
echo.
echo === 扫描 .dat 加密格式 ===
set /p SCAN_DIR=扫描目录 (回车用默认%WECHAT_DIR%): 
if "%SCAN_DIR%"=="" set "SCAN_DIR=%WECHAT_DIR%"
"%PYTHON%" "%WORKDIR%scripts\check_dat_headers.py" "%SCAN_DIR%"
goto MENU

:XOR_DECRYPT
echo.
echo === XOR 批量解密 ===
echo 这会把加密的变种格式 (.dat) 直接解成明文 JPG/PNG
echo 但微信会对明文再 XOR 一次, 反而显示不出来!
echo 只有导出备份时才用这个
set /p CONFIRM=确认? (Y=是 / N=跳过): 
if "%CONFIRM%"=="Y" (
    "%PYTHON%" "%WORKDIR%scripts\xor_decrypt_all.py"
) else (
    echo 跳过
)
goto MENU

:RE_ENCRYPT
echo.
echo === 反向加密 (明文→加密变种) ===
echo 这是最关键的一步!
echo 如果之前错误地把 .dat 覆盖成了明文 JPG, 跑这个加密回去
echo 微信就能正常 XOR 解密显示了
set /p RE_DIR=目录 (回车用默认%WECHAT_DIR%): 
if "%RE_DIR%"=="" set "RE_DIR=%WECHAT_DIR%"
"%PYTHON%" "%WORKDIR%scripts\re_encrypt_parallel.py" "%RE_DIR%"
goto MENU

:V2_DECRYPT
echo.
echo === V2 文件 AES 解密 ===
set /p V2_DIR=目录 (回车用默认%WECHAT_DIR%): 
if "%V2_DIR%"=="" set "V2_DIR=%WECHAT_DIR%"
set /p AES_KEY=输入 AES key (回车用从 remote API 拿到的): 
if "%AES_KEY%"=="" set "AES_KEY=6a27d958a2a01abf"
"%PYTHON%" "%WORKDIR%scripts\v2_decrypt.py" "%V2_DIR%" "%AES_KEY%"
goto MENU

:FETCH_KEY
echo.
echo === 从 remote API 获取密钥 ===
echo 上传 global_config + global_config.crc 自动拿 xor_key 和 aes_key
"%PYTHON%" "%WORKDIR%scripts\fetch_v2_keys.py"
goto MENU

:CLEAR_CACHE
echo.
echo === 清缓存 + 重启微信 ===
echo 1. 关微信
echo 2. 清缩略图缓存 (cache/Thumb 目录)
echo 3. 重启微信
echo 让微信重新扫描 .dat 生成缩略图
"%PYTHON%" "%WORKDIR%scripts\clear_cache.py"
goto MENU

:FULL_AUTO
echo.
echo === 一键全流程 ===
echo 1. 扫描格式分布
echo 2. 反向加密 (明文→加密变种)
echo 3. 清缓存 + 重启微信
echo 4. 提示完成
echo.
echo 开始...
echo.
echo [Step 1] 扫描格式...
"%PYTHON%" "%WORKDIR%scripts\check_dat_headers.py" "%WECHAT_DIR%"
echo.
echo [Step 2] 反向加密...
"%PYTHON%" "%WORKDIR%scripts\re_encrypt_parallel.py" "%WECHAT_DIR%"
echo.
echo [Step 3] 清缓存重启...
"%PYTHON%" "%WORKDIR%scripts\clear_cache.py"
echo.
echo [完成] 微信已重启! 去聊天记录里翻老年份图片吧!
goto MENU

:MERGE
echo.
echo === 合并多份微信数据 ===
set /p SRC=源目录 (其他位置的 xwechat_files): 
if "%SRC%"=="" (
    echo 跳过
    goto MENU
)
set /p DST=目标目录 (回车=%WECHAT_DIR%): 
if "%DST%"=="" set "DST=%WECHAT_DIR%"
echo 从 %SRC% 拷贝 .dat → %DST%
echo (只拷贝目标里不存在的文件, 不覆盖!)
robocopy "%SRC%" "%DST%" *.dat /E /R:1 /W:1 /NJH /NJS
echo 合并完成
goto MENU

:DECRYPT_DB
echo.
echo === 解密数据库 ===
set /p DB_DIR=db_storage 目录: 
if "%DB_DIR%"=="" set "DB_DIR=%WECHAT_DIR%\wxid_db7cm2zc6ou321_a13f\db_storage"
set /p OUT_DIR=输出目录: 
if "%OUT_DIR%"=="" set "OUT_DIR=%WORKDIR%decrypted"
"%PYTHON%" "%WORKDIR%scripts\decrypt_all_dbs.py" "%DB_DIR%" "%OUT_DIR%" "%KEY_INFO%"
goto MENU

:FIX_PERM
echo.
echo === 修复文件权限 ===
echo 把所有 .dat 的只读属性去掉
$py -c "
import os
import sys
from pathlib import Path
base = Path(sys.argv[1] if len(sys.argv) > 1 else r'D:\tool\WeChat\聊天记录\xwechat_files')
fixed = 0
for f in base.rglob('*.dat'):
    try:
        import stat
        attrs = os.stat(f)
        if attrs.st_mode & stat.S_IREAD:
            os.chmod(f, attrs.st_mode | stat.S_IWRITE)
            fixed += 1
    except:
        pass
print(f'修复 {fixed} 个文件')
" "%WECHAT_DIR%"
goto MENU

:END
echo.
echo 再见!
endlocal
