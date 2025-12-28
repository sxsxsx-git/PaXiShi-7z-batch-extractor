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
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
import threading
import queue
import multiprocessing

# 设置默认编码为UTF-8，添加错误处理
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass  # 忽略配置错误，继续执行

# 配置日志记录
def setup_file_logger():
    """设置文件日志记录器"""
    logger = logging.getLogger('file_logger')
    logger.setLevel(logging.INFO)
    
    # 检查是否已经有处理器，避免重复添加
    if not logger.handlers:
        try:
            handler = logging.FileHandler('process.log', 'a', encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)
        except Exception:
            # 如果无法创建日志文件，使用NullHandler
            logger.addHandler(logging.NullHandler())
    
    return logger

# 创建文件日志记录器
file_logger = setup_file_logger()

class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))

def setup_logger(log_queue):
    """设置并返回一个日志记录器"""
    logger = logging.getLogger(f'queue_logger_{id(log_queue)}')
    logger.setLevel(logging.INFO)
    
    # 检查是否已经有处理器，避免重复添加
    if not logger.handlers:
        # 添加队列处理器
        queue_handler = QueueHandler(log_queue)
        queue_handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(queue_handler)
        
        # 添加文件处理器
        try:
            handler = logging.FileHandler('process.log', 'a', encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)
        except Exception:
            pass
    
    return logger

class ProcessingThread(threading.Thread):
    def __init__(self, root_dir, password, status_var, progress_var, window, log_queue):
        super().__init__()
        self.root_dir = root_dir
        self.password = password
        self.status_var = status_var
        self.progress_var = progress_var
        self.window = window
        self.log_queue = log_queue
        self.logger = setup_logger(log_queue)
        self.executor = None
        self.running = True

    def stop(self):
        """停止处理线程"""
        self.running = False
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None

    def run(self):
        try:
            self.process_files()
        except Exception as e:
            error_msg = f"处理过程中出错: {str(e)}"
            self.status_var.set(error_msg)
            self.logger.error(error_msg)
            # 使用日志显示错误，而不是弹出窗口
            self.log_queue.put(f"错误: {error_msg}")
        finally:
            if self.executor:
                self.executor.shutdown(wait=False)
            self.window.quit_button.config(state=tk.NORMAL)
            self.window.start_button.config(state=tk.NORMAL)

    def process_files(self):
        if not self.running:
            return

        # 第一次循环
        self.status_var.set("步骤1：开始文件重命名")
        rename_files(self.root_dir, self.status_var, self.progress_var, self.logger)
        
        if not self.running:
            return
            
        self.status_var.set("步骤2：收集7z文件")
        all_7z_files = collect_7z_files(self.root_dir, self.logger)
        
        if not self.running:
            return
            
        self.status_var.set("步骤3：开始解压7z文件")
        # 使用spawn上下文创建进程池
        self.executor = ProcessPoolExecutor(max_workers=os.cpu_count() or 4, mp_context=multiprocessing.get_context('spawn'))
        if decompress_7z_files(all_7z_files, self.password, self.status_var, self.progress_var, self.logger, self.executor):
            if not self.running:
                return
            self.status_var.set("步骤4：删除已解压的7z文件")
            delete_7z_files(all_7z_files, self.status_var, self.progress_var, self.logger)
        
        if not self.running:
            return
            
        # 第二次循环
        self.status_var.set("再次步骤1：开始文件重命名")
        rename_files(self.root_dir, self.status_var, self.progress_var, self.logger)
        
        if not self.running:
            return
            
        self.status_var.set("再次步骤2：收集7z文件")
        all_7z_files = collect_7z_files(self.root_dir, self.logger)
        
        if not self.running:
            return
            
        self.status_var.set("再次步骤3：开始解压7z文件")
        # 使用spawn上下文创建进程池
        self.executor = ProcessPoolExecutor(max_workers=os.cpu_count() or 4, mp_context=multiprocessing.get_context('spawn'))
        if decompress_7z_files(all_7z_files, self.password, self.status_var, self.progress_var, self.logger, self.executor):
            if not self.running:
                return
            self.status_var.set("再次步骤4：删除已解压的7z文件")
            delete_7z_files(all_7z_files, self.status_var, self.progress_var, self.logger)
        
        if not self.running:
            return
            
        self.status_var.set("最终步骤：检查并处理文件名")
        check_and_truncate_long_filenames(self.root_dir, self.status_var, self.progress_var, self.logger)
        
        if not self.running:
            return
            
        self.status_var.set("所有任务已完成！")
        self.logger.info("所有任务已完成！")
        # 使用日志显示完成信息，而不是弹出窗口
        self.log_queue.put("完成: 所有任务已完成！")

def rename_files(root_dir, status_var=None, progress_var=None, logger=None):
    """重命名文件"""
    logger.info("=== 步骤1：开始文件重命名 ===")
    all_files = list(root_dir.rglob('*'))
    files_to_process = [path for path in all_files if path.is_file()]
    
    if progress_var:
        progress_var.set(0)
    
    total_files = len(files_to_process)
    processed_count = 0
    error_count = 0
    
    for i, file_path in enumerate(files_to_process):
        if progress_var:
            progress_var.set((i + 1) / total_files * 100)
        
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
                    processed_count += 1
                    logger.info(f"已重命名文件: {file_path} -> {new_file_path}")
                except Exception as e:
                    error_count += 1
                    logger.error(f"重命名文件失败: {file_path}. 错误: {e}")
    
    logger.info(f"=== 文件重命名完成: 成功处理 {processed_count} 个文件，失败 {error_count} 个 ===\n")

def collect_7z_files(root_dir, logger=None):
    """收集7z文件"""
    logger.info("=== 步骤2：收集7z文件 ===")
    all_files = list(root_dir.rglob('*.7z'))
    if not all_files:
        logger.info("未找到任何7z文件。")
    else:
        logger.info(f"共收集到 {len(all_files)} 个7z文件。")
    logger.info("=== 收集7z文件完成 ===\n")
    return all_files

def extract_7z_file(file_path, password, logger=None):
    """解压单个7z文件"""
    # 在子进程中重新设置日志记录器
    if logger is None:
        logger = setup_file_logger()
    
    extract_path = file_path.parent
    try:
        logger.info(f"开始解压文件: {file_path} 到目录: {extract_path}")
        start_time = time.time()
        
        with py7zr.SevenZipFile(file_path, mode='r', password=password) as z:
            z.extractall(path=extract_path)
            
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"已成功解压: {file_path}，耗时: {elapsed_time:.2f} 秒")
        return True
    except Exception as e:
        end_time = time.time()
        elapsed_time = end_time - start_time
        error_msg = f"解压文件失败: {file_path}. 错误: {e}，耗时: {elapsed_time:.2f} 秒"
        if logger:
            logger.error(error_msg)
        raise Exception(error_msg)

def decompress_7z_files(all_7z_files, password, status_var=None, progress_var=None, logger=None, executor=None):
    """解压所有7z文件"""
    logger.info("=== 步骤3：开始解压7z文件 ===")
    if not all_7z_files:
        logger.info("无7z文件可解压。")
        return True

    extraction_failed = False
    total_files = len(all_7z_files)
    success_count = 0
    error_count = 0
    
    if progress_var:
        progress_var.set(0)

    future_to_file = {executor.submit(extract_7z_file, file_path, password, None): file_path 
                     for file_path in all_7z_files}
    
    completed = 0
    for future in as_completed(future_to_file):
        completed += 1
        if progress_var:
            progress_var.set(completed / total_files * 100)
        
        file_path = future_to_file[future]
        try:
            future.result()
            success_count += 1
        except Exception as e:
            error_count += 1
            logger.error(f"解压文件失败: {file_path}. 错误: {e}")
            extraction_failed = True
    
    if extraction_failed:
        logger.error(f"存在解压失败的文件，程序将退出并不会删除原始7z文件。成功: {success_count}，失败: {error_count}")
        return False
    
    logger.info(f"=== 解压7z文件完成: 成功解压 {success_count} 个文件，失败 {error_count} 个 ===\n")
    return True

def delete_7z_files(all_7z_files, status_var=None, progress_var=None, logger=None):
    """删除7z文件"""
    logger.info("=== 步骤4：开始删除已解压的7z文件 ===")
    
    if progress_var:
        progress_var.set(0)
    
    total_files = len(all_7z_files)
    success_count = 0
    error_count = 0
    
    for i, file_path in enumerate(all_7z_files):
        if progress_var:
            progress_var.set((i + 1) / total_files * 100)
        
        try:
            file_path.unlink()
            success_count += 1
            logger.info(f"已删除7z文件: {file_path}")
        except Exception as e:
            error_count += 1
            logger.error(f"删除7z文件失败: {file_path}. 错误: {e}")
    
    logger.info(f"=== 已删除所有原始7z文件: 成功删除 {success_count} 个文件，失败 {error_count} 个 ===\n")

def sanitize_filename_for_nas(filename, file_path):
    """处理文件名以确保NAS兼容性"""
    import re
    import unicodedata
    
    MAX_BASENAME_LEN = 30
    REPLACEMENTS = {
        '⚡': 'lightning', '【': '[', '】': ']', '！': '!', '？': '?',
        '：': '-', '；': ';', '，': ',', '（': '(', '）': ')',
        '　': ' ', '@': 'at', '|': '-', '\\': '-', '/': '-',
        '*': '-', '?': '-', '"': "'", '<': '(', '>': ')',
        '\n': ' ', '\r': ' ', '\t': ' ',
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

def check_and_truncate_long_filenames(root_dir, status_var=None, progress_var=None, logger=None):
    """检查并处理文件名"""
    logger.info("=== 最终步骤前：检查并处理文件名以确保NAS兼容性 ===")
    
    all_files = list(root_dir.rglob('*'))
    processed_count = 0
    error_count = 0
    
    if progress_var:
        progress_var.set(0)
    
    all_files.sort(key=lambda x: len(x.parts), reverse=True)
    total_files = len(all_files)
    
    for i, file_path in enumerate(all_files):
        if progress_var:
            progress_var.set((i + 1) / total_files * 100)
        
        if file_path.is_file():
            original_filename = file_path.name
            try:
                new_name = sanitize_filename_for_nas(original_filename, file_path)
                new_file_path = file_path.with_name(new_name)
                
                if new_file_path != file_path:
                    try:
                        file_path.rename(new_file_path)
                        processed_count += 1
                        logger.info(f"文件名修改: {file_path} -> {new_file_path}")
                    except Exception as e:
                        error_count += 1
                        logger.error(f"重命名文件失败: {file_path}. 错误: {e}")
            except Exception as e:
                error_count += 1
                logger.error(f"处理文件名失败: {file_path}. 错误: {e}")
    
    logger.info(f"=== 文件名处理完成: 成功处理 {processed_count} 个文件，失败 {error_count} 个 ===\n")

class Application(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("7z文件批量解压工具")
        self.geometry("800x600")
        
        # 添加处理线程属性
        self.processing_thread = None
        
        # 创建日志队列
        self.log_queue = queue.Queue()
        
        # 绑定窗口关闭事件
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 配置主窗口网格
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # 创建主框架
        main_frame = ttk.Frame(self, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置主框架网格
        main_frame.grid_rowconfigure(4, weight=1)  # 日志框架行可以扩展
        main_frame.grid_columnconfigure(1, weight=1)  # 中间列可以扩展
        
        # 目录选择
        ttk.Label(main_frame, text="选择目录:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.dir_var = tk.StringVar()
        dir_entry = ttk.Entry(main_frame, textvariable=self.dir_var, width=50)
        dir_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(main_frame, text="浏览", command=self.browse_directory).grid(row=0, column=2, padx=5, pady=5)
        
        # 密码输入
        ttk.Label(main_frame, text="解压密码:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.password_var = tk.StringVar(value="1151")
        ttk.Entry(main_frame, textvariable=self.password_var, width=20).grid(row=1, column=1, sticky=tk.W, pady=5)
        
        # 状态显示
        ttk.Label(main_frame, text="状态:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(main_frame, textvariable=self.status_var).grid(row=2, column=1, columnspan=2, sticky=tk.W, pady=5)
        
        # 进度条
        ttk.Label(main_frame, text="进度:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.progress_var = tk.DoubleVar()
        ttk.Progressbar(main_frame, length=300, variable=self.progress_var, mode='determinate').grid(row=3, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # 日志显示区域
        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.log_text = tk.Text(log_frame, height=20, width=80)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text['yscrollcommand'] = scrollbar.set
        
        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=3, pady=10)
        
        self.start_button = ttk.Button(button_frame, text="开始处理", command=self.start_processing)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.quit_button = ttk.Button(button_frame, text="退出程序", command=self.quit_app)
        self.quit_button.pack(side=tk.LEFT, padx=5)
        
        # 配置日志更新
        self.after(100, self.update_log)
        
    def browse_directory(self):
        """选择目录"""
        directory = filedialog.askdirectory()
        if directory:
            self.dir_var.set(directory)
            
    def update_log(self):
        """更新日志显示"""
        while True:
            try:
                log_message = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, log_message + '\n')
                self.log_text.see(tk.END)
            except queue.Empty:
                break
        self.after(100, self.update_log)
        
    def start_processing(self):
        """开始处理文件"""
        directory = self.dir_var.get()
        password = self.password_var.get()
        
        if not directory:
            messagebox.showerror("错误", "请选择目录！")
            return
        
        if not password:
            messagebox.showerror("错误", "请输入解压密码！")
            return
        
        # 清空日志显示
        self.log_text.delete(1.0, tk.END)
        
        self.start_button.config(state=tk.DISABLED)
        self.quit_button.config(state=tk.DISABLED)
        
        # 创建并启动处理线程
        self.processing_thread = ProcessingThread(
            Path(directory),
            password,
            self.status_var,
            self.progress_var,
            self,
            self.log_queue
        )
        self.processing_thread.start()

    def on_closing(self):
        """处理窗口关闭事件"""
        if self.processing_thread and self.processing_thread.is_alive():
            if messagebox.askokcancel("确认", "正在处理文件，确定要退出吗？"):
                self.processing_thread.stop()
                self.processing_thread.join(timeout=2)  # 等待线程结束
                self.quit()
        else:
            self.quit()

    def quit_app(self):
        """退出应用程序"""
        if self.processing_thread and self.processing_thread.is_alive():
            if messagebox.askokcancel("确认退出", "正在处理文件，确定要退出吗？"):
                self.processing_thread.stop()
                self.processing_thread.join(timeout=2)  # 等待线程结束
                self.quit()
        else:
            if messagebox.askokcancel("确认退出", "确定要退出程序吗？"):
                self.quit()

if __name__ == "__main__":
    app = Application()
    app.mainloop()
