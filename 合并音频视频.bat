@echo off
chcp 65001 >nul
for %%i in (*.mp4) do (
  if exist "%%~ni.m4a" (
    ffmpeg -i "%%~ni.mp4" -i "%%~ni.m4a" -c copy "%%~ni.mkv"
    del "%%~ni.mp4" "%%~ni.m4a"
  )
)
pause >nul
