@echo off
rem ============================================================
rem  合并视频（音频 / 字幕 / 封面）—— Python 版启动器
rem  双击：处理本文件所在目录
rem  拖入文件夹：处理那个文件夹（可带子目录用 -R）
rem  拖入单个 mp4：只处理那一个文件
rem  命令行：merge.bat [选项] [目录或文件 ...]
rem ============================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "HERE=%~dp0"
set "RC=0"

call :FindPython
if not defined PY (
    echo.
    echo [错误] 没有找到 Python 3。
    echo        请安装 Python 3.9 或更高版本，安装时勾选 "Add python.exe to PATH"。
    echo.
    if "%~1"=="" pause
    exit /b 2
)

if not "%~1"=="" goto RunWithArgs

rem 双击：处理脚本所在目录，结束前暂停
%PY% "%HERE%merge_videos.py" --no-pause "%HERE%."
set "RC=%errorlevel%"
echo.
if "%RC%"=="1" echo [退出码 1] 有文件未能合并，源文件未改动，详见上方汇总。
if "%RC%"=="2" echo [退出码 2] 参数或运行环境有问题，详见上方错误信息。
if "%RC%"=="130" echo [退出码 130] 已中断，源文件未改动。
pause
exit /b %RC%

:RunWithArgs
%PY% "%HERE%merge_videos.py" %*
set "RC=%errorlevel%"
exit /b %RC%

:FindPython
set "PY="
where py >nul 2>&1
if errorlevel 1 goto TryPython
py -3 --version >nul 2>&1
if errorlevel 1 goto TryPython
set "PY=py -3"
goto :eof
:TryPython
where python >nul 2>&1
if errorlevel 1 goto :eof
python --version >nul 2>&1
if errorlevel 1 goto :eof
set "PY=python"
goto :eof