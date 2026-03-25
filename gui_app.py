#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import multiprocessing
import os
import queue
import threading
import tkinter as tk
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from paxishi_extractor import ensure_utf8_stdio, get_file_logger, run_pipeline

ensure_utf8_stdio()


class QueueHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue[str]):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        self.log_queue.put(message)


def build_gui_logger(log_queue: queue.Queue[str]) -> logging.Logger:
    logger = logging.getLogger("paxishi.gui")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        queue_handler = QueueHandler(log_queue)
        queue_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(queue_handler)

        file_logger = get_file_logger("paxishi.file")
        for handler in file_logger.handlers:
            logger.addHandler(handler)

    return logger


class ProcessingThread(threading.Thread):
    def __init__(
        self,
        root_dir: Path,
        password: str,
        status_var: tk.StringVar,
        progress_var: tk.DoubleVar,
        window: "Application",
        log_queue: queue.Queue[str],
    ) -> None:
        super().__init__()
        self.root_dir = root_dir
        self.password = password
        self.status_var = status_var
        self.progress_var = progress_var
        self.window = window
        self.log_queue = log_queue
        self.logger = build_gui_logger(log_queue)
        self.stop_event = threading.Event()
        self.executor: Optional[ProcessPoolExecutor] = None

    def stop(self) -> None:
        self.stop_event.set()
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)

    def run(self) -> None:
        try:
            self.progress_var.set(0)

            def status_cb(message: str) -> None:
                self.status_var.set(message)
                self.log_queue.put(message)

            def progress_cb(current: int, total: int) -> None:
                if total > 0:
                    self.progress_var.set(current / total * 100)

            def executor_factory() -> ProcessPoolExecutor:
                self.executor = ProcessPoolExecutor(
                    max_workers=os.cpu_count() or 4,
                    mp_context=multiprocessing.get_context("spawn"),
                )
                return self.executor

            ok = run_pipeline(
                self.root_dir,
                self.password,
                logger=self.logger,
                status_cb=status_cb,
                progress_cb=progress_cb,
                executor_factory=executor_factory,
                should_stop=self.stop_event.is_set,
            )

            if not ok and not self.stop_event.is_set():
                self.log_queue.put("错误: 处理未完成。")
        except Exception as exc:
            error_msg = f"处理过程中出错: {exc}"
            self.status_var.set(error_msg)
            self.logger.error(error_msg)
            self.log_queue.put(f"错误: {error_msg}")
        finally:
            if self.executor:
                self.executor.shutdown(wait=False, cancel_futures=True)
                self.executor = None
            self.window.quit_button.config(state=tk.NORMAL)
            self.window.start_button.config(state=tk.NORMAL)


class Application(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("7z文件批量解压工具")
        self.geometry("800x600")

        self.processing_thread: Optional[ProcessingThread] = None
        self.log_queue: queue.Queue[str] = queue.Queue()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        main_frame = ttk.Frame(self, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.grid_rowconfigure(4, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(main_frame, text="选择目录:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.dir_var = tk.StringVar()
        dir_entry = ttk.Entry(main_frame, textvariable=self.dir_var, width=50)
        dir_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5)
        ttk.Button(main_frame, text="浏览", command=self.browse_directory).grid(
            row=0, column=2, padx=5, pady=5
        )

        ttk.Label(main_frame, text="解压密码:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.password_var = tk.StringVar(value="1151")
        ttk.Entry(main_frame, textvariable=self.password_var, width=20).grid(
            row=1, column=1, sticky=tk.W, pady=5
        )

        ttk.Label(main_frame, text="状态:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(main_frame, textvariable=self.status_var).grid(
            row=2, column=1, columnspan=2, sticky=tk.W, pady=5
        )

        ttk.Label(main_frame, text="进度:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.progress_var = tk.DoubleVar()
        ttk.Progressbar(
            main_frame, length=300, variable=self.progress_var, mode="determinate"
        ).grid(row=3, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)

        self.log_text = tk.Text(log_frame, height=20, width=80)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text["yscrollcommand"] = scrollbar.set

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=3, pady=10)

        self.start_button = ttk.Button(button_frame, text="开始处理", command=self.start_processing)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.quit_button = ttk.Button(button_frame, text="退出程序", command=self.quit_app)
        self.quit_button.pack(side=tk.LEFT, padx=5)

        self.after(100, self.update_log)

    def browse_directory(self) -> None:
        directory = filedialog.askdirectory()
        if directory:
            self.dir_var.set(directory)

    def update_log(self) -> None:
        while True:
            try:
                log_message = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, log_message + "\n")
                self.log_text.see(tk.END)
            except queue.Empty:
                break
        self.after(100, self.update_log)

    def start_processing(self) -> None:
        directory = self.dir_var.get()
        password = self.password_var.get()

        if not directory:
            messagebox.showerror("错误", "请选择目录！")
            return

        if not password:
            messagebox.showerror("错误", "请输入解压密码！")
            return

        self.log_text.delete(1.0, tk.END)
        self.start_button.config(state=tk.DISABLED)
        self.quit_button.config(state=tk.DISABLED)

        self.processing_thread = ProcessingThread(
            Path(directory),
            password,
            self.status_var,
            self.progress_var,
            self,
            self.log_queue,
        )
        self.processing_thread.start()

    def on_closing(self) -> None:
        if self.processing_thread and self.processing_thread.is_alive():
            if messagebox.askokcancel("确认", "正在处理文件，确定要退出吗？"):
                self.processing_thread.stop()
                self.processing_thread.join(timeout=2)
                self.quit()
        else:
            self.quit()

    def quit_app(self) -> None:
        if self.processing_thread and self.processing_thread.is_alive():
            if messagebox.askokcancel("确认退出", "正在处理文件，确定要退出吗？"):
                self.processing_thread.stop()
                self.processing_thread.join(timeout=2)
                self.quit()
        else:
            if messagebox.askokcancel("确认退出", "确定要退出程序吗？"):
                self.quit()


if __name__ == "__main__":
    app = Application()
    app.mainloop()
