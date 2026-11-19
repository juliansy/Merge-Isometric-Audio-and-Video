@echo off
rem ============================================================
rem  Merge audio, subtitles and cover into one mp4 - launcher
rem
rem  Double-click          run on the folder this file sits in
rem  Drop a folder on it   run on that folder (add -R for subfolders)
rem  Drop one mp4 on it    run on that file only
rem  Command line          merge.bat [options] [folder or file ...]
rem
rem  ASCII only, on purpose: a UTF-8 batch file that runs chcp
rem  makes cmd lose its parser offset and execute fragments of
rem  later lines. Every Chinese message is printed by
rem  merge_videos.py instead.
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
    echo [python] Python 3 was not found.
    echo [python] Install Python 3.9 or newer and tick
    echo [python] "Add python.exe to PATH" while installing.
    echo.
    if "%~1"=="" pause
    exit /b 2
)

if not "%~1"=="" goto RunWithArgs

%PY% "%HERE%merge_videos.py" --no-pause "%HERE%."
set "RC=%errorlevel%"
if not "%RC%"=="0" %PY% "%HERE%merge_videos.py" --hint %RC%
echo.
pause
exit /b %RC%

:RunWithArgs
%PY% "%HERE%merge_videos.py" %*
set "RC=%errorlevel%"
if not "%RC%"=="0" %PY% "%HERE%merge_videos.py" --hint %RC%
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
