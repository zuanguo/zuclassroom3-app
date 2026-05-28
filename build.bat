@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ==========================================
echo 开始构建：课堂教学软件 自动保存恢复专业版
echo ==========================================

echo.
echo [1/6] 检查 Python...
python --version
if errorlevel 1 (
    echo 未检测到 Python，请先安装 Python 并加入 PATH
    pause
    exit /b 1
)

echo.
echo [2/6] 安装/检查依赖...
python -m pip install -U pip
python -m pip install -U PySide6 pyinstaller PyMuPDF
if errorlevel 1 (
    echo 依赖安装失败
    pause
    exit /b 1
)

echo.
echo [3/6] 清理旧文件...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist installer_output rmdir /s /q installer_output
if exist ClassroomApp.spec del /q ClassroomApp.spec

echo.
echo [4/6] 准备图标参数...
set ICON_ARG=
if exist app.ico (
    set ICON_ARG=--icon=app.ico
    echo 检测到 app.ico，将使用自定义图标
) else (
    echo 未检测到 app.ico，将使用默认图标
)

echo.
echo [5/6] 打包 EXE...
pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onefile ^
  --name ClassroomApp ^
  --collect-all fitz ^
  --version-file version_info.txt ^
  %ICON_ARG% ^
  classroom_app.py

if errorlevel 1 (
    echo EXE 打包失败
    pause
    exit /b 1
)

echo.
echo [6/6] 生成安装包...
set ISCC_PATH=

if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe

if "%ISCC_PATH%"=="" (
    echo 未找到 Inno Setup 编译器 ISCC.exe
    echo 请先安装 Inno Setup 6:
    echo https://jrsoftware.org/isinfo.php
    pause
    exit /b 1
)

"%ISCC_PATH%" installer.iss
if errorlevel 1 (
    echo 安装包生成失败
    pause
    exit /b 1
)

echo.
echo ==========================================
echo 构建完成！
echo EXE位置：dist\ClassroomApp.exe
echo 安装包位置：installer_output\ClassroomApp_Setup_v1.6.0.exe
echo ==========================================
pause