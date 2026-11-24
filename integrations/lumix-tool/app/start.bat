@echo off
chcp 65001 >nul
set "ELECTRON_RUN_AS_NODE="
cd /d "%~dp0"
if not exist "node_modules\electron\dist\electron.exe" (
  echo [LumixTool] 还没有安装依赖，请在当前目录运行:
  echo     npm install
  pause
  exit /b 1
)
if not exist "renderer-dist\index.html" (
  echo [LumixTool] 首次启动，正在构建界面...
  call npm run build
  if errorlevel 1 (
    echo [LumixTool] 构建失败。请在当前目录运行 npm run build 查看原因。
    pause
    exit /b 1
  )
)
echo [LumixTool] 正在启动相机工具箱...
if "%LUMIXTOOL_MOCK%"=="1" echo [LumixTool] 模拟模式已启用，不会访问相机。
start "LumixTool" "node_modules\electron\dist\electron.exe" .
