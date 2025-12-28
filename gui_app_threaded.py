#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import locale
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import py7zr
import logging
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
import queue

class SevenZipExtractorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("7z批量解压工具")
        self.root.geometry("800x600")
        
        # 初始化变量
        self.root_directory = Path("")
        self.extract_password = ""
        self.running = False
        self.log_queue = queue.Queue()
        
        # 创建界面
        self.create_widgets()
        
        # 启动日志更新线程
        self.start_log_updater()
        
        # 配置日志
        self.setup_logger()
    
    def setup_logger(self):
        """设置日志记录器"""
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            filename='process.log',
            filemode='a',
            format='%(asctime)s - %(levelname)s - %(message)s',
            level=logging.INFO,
            encoding='utf-8'
        )
    
    def create_widgets(self):
        """创建GUI控件"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 目录选择区域
        dir_frame = ttk.LabelFrame(main_frame, text="解压目录", padding="10")
        dir_frame.pack(fill=tk.X, pady=5)
        
        self.dir_entry = ttk.Entry(dir_frame)
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        dir_btn = ttk.Button(dir_frame, text="浏览...", command=self.select_directory)
        dir_btn.pack(side=tk.RIGHT)
        
        # 密码输入区域
        pwd_frame = ttk.LabelFrame(main_frame, text="解压密码 (默认:1151)", padding="10")
        pwd_frame.pack(fill=tk.X, pady=5)
        
        self.pwd_entry = ttk.Entry(pwd_frame, show="*")
        self.pwd_entry.pack(fill=tk.X)
        self.pwd_entry.insert(0, "1151")  # 设置默认密码
        
        # 控制按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        self.start_btn = ttk.Button(btn_frame, text="开始解压", command=self.start_extraction)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self.stop_extraction, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # 日志显示区域
        log_frame = ttk.LabelFrame(main_frame, text="操作日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        # 进度条
        self.progress = ttk.Progressbar(main_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.pack(fill=tk.X, pady=5)
    
    def select_directory(self):
        """选择解压目录"""
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.root_directory = Path(dir_path)
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, dir_path)
    
    def start_extraction(self):
        """开始解压过程"""
        if not self.root_directory or not self.root_directory.exists():
            messagebox.showerror("错误", "请选择有效的解压目录")
            return
        
        self.extract_password = self.pwd_entry.get()
        if not self.extract_password:
            messagebox.showwarning("警告", "解压密码不能为空")
            return
        
        # 更新UI状态
        self.running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress["value"] = 0
        
        # 在后台线程中运行解压过程
        threading.Thread(target=self.run_extraction, daemon=True).start()
    
    def stop_extraction(self):
        """停止解压过程"""
        self.running = False
        self.log("用户请求停止解压")
    
    def run_extraction(self):
        """执行解压过程"""
        try:
            self.log(f"开始处理目录: {self.root_directory}\n")
            
            # 第一次循环 (1, 2, 3, 4)
            self.rename_files()   # 步骤1
            all_7z_files = self.collect_7z_files()  # 步骤2
            
            # 解压7z文件 (步骤3)
            if not self.decompress_7z_files(all_7z_files):
                return
            
            # 解压成功后删除7z文件 (步骤4)
            self.delete_7z_files(all_7z_files)
            
            # 第二次循环 (1, 2, 3, 4)
            self.rename_files()   # 再次步骤1
            all_7z_files = self.collect_7z_files()  # 再次步骤2
            
            # 再次解压7z文件 (步骤3)
            if not self.decompress_7z_files(all_7z_files):
                return
            
            # 再次解压成功后删除7z文件 (再次步骤4)
            self.delete_7z_files(all_7z_files)
            
            # 最终步骤前检查并截断过长的文件名
            self.check_and_truncate_long_filenames()
            
            # 最终步骤5
            self.all_done()
            
        except Exception as e:
            self.log(f"发生错误: {str(e)}", level="error")
        finally:
            self.running = False
            self.root.after(0, self.reset_ui)
    
    def reset_ui(self):
        """重置UI状态"""
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.progress["value"] = 0
        self.dir_entry.delete(0, tk.END)
        self.root_directory = Path("")
    
    def log(self, message, level="info"):
        """记录日志"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_message = f"[{timestamp}] {message}"
        
        # 添加到队列供日志更新线程处理
        self.log_queue.put((log_message, level))
        
        # 记录到文件
        if level == "error":
            self.logger.error(message)
        else:
            self.logger.info(message)
    
    def start_log_updater(self):
        """启动日志更新线程"""
        def update_log():
            while True:
                try:
                    message, level = self.log_queue.get_nowait()
                    self.log_text.config(state=tk.NORMAL)
                    
                    # 根据日志级别设置颜色
                    if level == "error":
                        self.log_text.tag_config("error", foreground="red")
                        self.log_text.insert(tk.END, message + "\n", "error")
                    else:
                        self.log_text.insert(tk.END, message + "\n")
                    
                    self.log_text.config(state=tk.DISABLED)
                    self.log_text.see(tk.END)
                except queue.Empty:
                    break
            
            # 每100ms检查一次新日志
            self.root.after(100, update_log)
        
        self.root.after(100, update_log)
    
    # 以下是原CLI功能的GUI适配版本
    def rename_files(self):
        """步骤1：重命名文件"""
        self.log("=== 步骤1：开始文件重命名 ===")
        all_files = list(self.root_directory.rglob('*'))
        files_to_process = [path for path in all_files if path.is_file()]
        
        self.progress["maximum"] = len(files_to_process)
        self.progress["value"] = 0
        
        for i, file_path in enumerate(files_to_process):
            if not self.running:
                return False
            
            filename = file_path.name
            lower_name = filename.lower()
            if '7z' in lower_name and not lower_name.endswith('.7z'):
                index = lower_name.find('7z')
                if index != -1:
                    base_name = filename[:index+2]
                    new_file_name = base_name + '.7z'
                    new_file_path = file_path.with_name(new_file_name)
                    try:
                        file_path.rename(new_file_path)
                        self.log(f"已重命名文件: {file_path} -> {new_file_path}")
                    except Exception as e:
                        self.log(f"重命名文件失败: {file_path}. 错误: {e}", level="error")
            
            self.progress["value"] = i + 1
            self.root.update()
        
        self.log("=== 文件重命名完成 ===\n")
        return True
    
    def collect_7z_files(self):
        """步骤2：收集7z文件"""
        self.log("=== 步骤2：收集7z文件 ===")
        all_files = list(self.root_directory.rglob('*.7z'))
        
        if not all_files:
            self.log("未找到任何7z文件。")
        else:
            self.log(f"共收集到 {len(all_files)} 个7z文件。")
        
        self.log("=== 收集7z文件完成 ===\n")
        return all_files
    
    def extract_7z_file(self, file_path):
        """解压单个7z文件"""
        extract_path = file_path.parent
        self.log(f"开始解压文件: {file_path} 到目录: {extract_path}")
        start_time = time.time()
        
        try:
            with py7zr.SevenZipFile(file_path, mode='r', password=self.extract_password) as z:
                z.extractall(path=extract_path)
            
            end_time = time.time()
            elapsed_time = end_time - start_time
            self.log(f"已成功解压: {file_path}，耗时: {elapsed_time:.2f} 秒")
            return True
        except Exception as e:
            end_time = time.time()
            elapsed_time = end_time - start_time
            self.log(f"解压文件失败: {file_path}. 错误: {e}，耗时: {elapsed_time:.2f} 秒", level="error")
            return False
    
    def decompress_7z_files(self, all_7z_files):
        """步骤3：解压7z文件"""
        self.log("=== 步骤3：开始解压7z文件 ===")
        
        if not all_7z_files:
            self.log("无7z文件可解压。")
            return True
        
        self.progress["maximum"] = len(all_7z_files)
        self.progress["value"] = 0
        
        extraction_failed = False
        
        # 创建线程池但不使用with语句，避免自动关闭
        executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)
        try:
            futures = {executor.submit(self.extract_7z_file, file_path): file_path for file_path in all_7z_files}
            
            for i, future in enumerate(as_completed(futures)):
                if not self.running:
                    executor.shutdown(wait=False)
                    return False
                
                file_path = futures[future]
                try:
                    if not future.result():
                        extraction_failed = True
                except Exception as e:
                    self.log(f"解压文件失败: {file_path}. 错误: {e}", level="error")
                    extraction_failed = True
                
                self.progress["value"] = i + 1
                self.root.update()
                
        except Exception as e:
            self.log(f"创建线程池失败: {str(e)}", level="error")
            executor.shutdown(wait=False)
            return False
        
        if extraction_failed:
            self.log("存在解压失败的文件，程序将退出并不会删除原始7z文件。", level="error")
            return False
        else:
            self.log("=== 解压7z文件完成 ===\n")
            return True
    
    def delete_7z_files(self, all_7z_files):
        """步骤4：删除7z文件"""
        self.log("=== 步骤4：开始删除已解压的7z文件 ===")
        
        self.progress["maximum"] = len(all_7z_files)
        self.progress["value"] = 0
        
        for i, file_path in enumerate(all_7z_files):
            if not self.running:
                return
            
            try:
                file_path.unlink()
                self.log(f"已删除7z文件: {file_path}")
            except Exception as e:
                self.log(f"删除7z文件失败: {file_path}. 错误: {e}", level="error")
            
            self.progress["value"] = i + 1
            self.root.update()
        
        self.log("=== 已删除所有原始7z文件 ===\n")
    
    def sanitize_filename_for_nas(self, filename, file_path):
        """处理文件名以确保NAS兼容性"""
        import re
        import unicodedata
        
        MAX_BASENAME_LEN = 30
        REPLACEMENTS = {
            '⚡': 'lightning',
            '【': '[',
            '】': ']',
            '！': '!',
            '？': '?',
            '：': '-',
            '；': ';',
            '，': ',',
            '（': '(',
            '）': ')',
            '　': ' ',
            '@': 'at',
            '|': '-',
            '\\': '-',
            '/': '-',
            '*': '-',
            '?': '-',
            '"': "'",
            '<': '(',
            '>': ')',
            '\n': ' ',
            '\r': ' ',
            '\t': ' ',
        }
        
        stem, suffix = os.path.splitext(filename)
        
        for old, new in REPLACEMENTS.items():
            stem = stem.replace(old, new)
        
        stem = ''.join(c for c in stem if not unicodedata.combining(c) and c.isprintable())
        stem = re.sub(r'\s+', ' ', stem)
        stem = stem.strip(' .')
        
        if not stem:
            stem = 'file'
        
        encoded_stem = stem.encode('utf-8')
        if len(encoded_stem) > MAX_BASENAME_LEN:
            while len(encoded_stem) > MAX_BASENAME_LEN:
                stem = stem[:-1]
                encoded_stem = stem.encode('utf-8')
        
        parent_dir = Path(file_path).parent
        counter = 1
        new_name = f"{stem}{suffix}"
        
        while (parent_dir / new_name).exists():
            new_stem = f"{stem}_{counter}"
            while len(new_stem.encode('utf-8')) > MAX_BASENAME_LEN:
                stem = stem[:-1]
                new_stem = f"{stem}_{counter}"
            new_name = f"{new_stem}{suffix}"
            counter += 1
        
        while len(new_name.encode('utf-8')) > 255:
            if '_' in stem:
                stem = stem[:stem.rindex('_')]
            else:
                stem = stem[:-1]
            new_name = f"{stem}{suffix}"
        
        return new_name
    
    def check_and_truncate_long_filenames(self):
        """最终步骤前：检查并处理文件名"""
        self.log("=== 最终步骤前：检查并处理文件名以确保NAS兼容性 ===")
        
        all_files = list(self.root_directory.rglob('*'))
        processed_count = 0
        error_count = 0
        
        all_files.sort(key=lambda x: len(x.parts), reverse=True)
        
        self.progress["maximum"] = len(all_files)
        self.progress["value"] = 0
        
        for i, file_path in enumerate(all_files):
            if not self.running:
                return
            
            if file_path.is_file():
                original_filename = file_path.name
                try:
                    new_name = self.sanitize_filename_for_nas(original_filename, file_path)
                    new_file_path = file_path.with_name(new_name)
                    
                    if new_file_path != file_path:
                        try:
                            file_path.rename(new_file_path)
                            processed_count += 1
                            self.log(f"文件名修改: {file_path} -> {new_file_path}")
                        except Exception as e:
                            error_count += 1
                            self.log(f"重命名文件失败: {file_path}. 错误: {e}", level="error")
                except Exception as e:
                    error_count += 1
                    self.log(f"处理文件名失败: {file_path}. 错误: {e}", level="error")
            
            self.progress["value"] = i + 1
            self.root.update()
        
        self.log(f"=== 文件名处理完成: 成功处理 {processed_count} 个文件，失败 {error_count} 个 ===\n")
    
    def all_done(self):
        """步骤5：所有任务完成"""
        self.log("所有任务已完成。")

def main():
    """主程序入口"""
    print("正在启动7z批量解压工具GUI...")  # 调试信息
    root = tk.Tk()
    try:
        app = SevenZipExtractorGUI(root)
        print("GUI初始化完成，进入主循环...")  # 调试信息
        root.mainloop()
    except Exception as e:
        print(f"GUI启动失败: {str(e)}")  # 调试信息
        raise

if __name__ == "__main__":
    main()
