@echo off
REM 设置字符编码为 UTF-8
chcp 65001 >nul

REM 遍历当前目录下的所有 .mp4 文件
for %%i in (*.mp4) do (
  REM 检查是否存在对应的 .m4a 文件
  if exist "%%~ni.m4a" (
    echo 正在处理文件 %%~ni.mp4 和 %%~ni.m4a...
    REM 将 .mp4 文件重命名为 .ts 文件
    ren "%%~ni.mp4" "%%~ni.ts"
    REM 使用 ffmpeg 将 .m4a 和 .ts 合并为新的 .mp4 文件
    ffmpeg -i "%%~ni.ts" -i "%%~ni.m4a" -c copy "%%~ni.mp4"
    if not errorlevel 1 (
      echo 成功: 已合并为 %%~ni.mp4。
      REM 删除临时的 .ts 和原始的 .m4a 文件
      if exist "%%~ni.ts" del "%%~ni.ts"
      if exist "%%~ni.m4a" del "%%~ni.m4a"
    ) else (
      echo 错误: 合并 %%~ni.ts 和 %%~ni.m4a 时失败。
    )
  )
)

REM 暂停以防止窗口立即关闭
pause >nul
