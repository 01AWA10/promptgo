@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "PORT=7317"
if not "%~1"=="" set "PORT=%~1"

set "PY="
where py >nul 2>nul
if %errorlevel%==0 set "PY=py -3"

if not defined PY (
  where python >nul 2>nul
  if !errorlevel!==0 set "PY=python"
)

if not defined PY (
  echo [错误] 未检测到 Python 3，请先安装 Python 3.11+ 并加入 PATH。
  pause
  exit /b 1
)

echo 正在启动 PromptGo 本地服务，端口 !PORT! ...
!PY! "%~dp0server\app.py" --port !PORT! --open
if errorlevel 1 pause
endlocal
