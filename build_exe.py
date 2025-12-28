#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import shutil
import time
from pathlib import Path

def check_and_install_pyinstaller():
    """检查并安装PyInstaller"""
    try:
        import pyinstaller
        print("PyInstaller 已安装")
    except ImportError:
        print("正在安装PyInstaller...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
            print("PyInstaller 安装成功")
        except subprocess.CalledProcessError:
            print("PyInstaller 安装失败")
            sys.exit(1)

def build_executable():
    """构建可执行文件"""
    def safe_remove(path):
        """安全删除文件或目录"""
        max_retries = 3
        delay = 1  # 秒
        
        for i in range(max_retries):
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                return True
            except PermissionError:
                if i == max_retries - 1:
                    print(f"警告: 无法删除 {path}, 跳过...")
                    return False
                time.sleep(delay)
            except FileNotFoundError:
                return True
        return False

    # 清理旧的构建目录
    build_dir = Path("build")
    if build_dir.exists():
        safe_remove(build_dir)
    
    # 清理旧的dist目录
    dist_dir = Path("dist")
    if dist_dir.exists():
        safe_remove(dist_dir)
    
    # 检查spec文件并删除
    spec_file = Path("main_gui.spec")
    if spec_file.exists():
        safe_remove(spec_file)
    
    # 构建命令
    build_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name=7z批量解压工具",
        "--add-data=process.log;.",
        "--windowed",
        "main_gui.py"
    ]
    
    print("正在构建可执行文件...")
    try:
        subprocess.check_call(build_cmd)
        print(f"构建成功! 可执行文件位于: {dist_dir/'7z批量解压工具.exe'}")
    except subprocess.CalledProcessError as e:
        print(f"构建失败: {e}")
        sys.exit(1)
    
    # 复制必要的资源文件
    print("复制资源文件...")
    shutil.copy("process.log", dist_dir)
    
    print("清理临时文件...")
    safe_remove(build_dir)
    safe_remove(spec_file)

if __name__ == "__main__":
    print("=== 7z批量解压工具EXE构建脚本 ===")
    check_and_install_pyinstaller()
    build_executable()
    print("=== 构建完成 ===")
