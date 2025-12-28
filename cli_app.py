#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import locale

# 设置默认编码为UTF-8
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
from pathlib import Path
import py7zr
import logging
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
import sys

# 配置日志记录
logging.basicConfig(
    filename='process.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    encoding='utf-8'
)

def setup_logger():
    """设置并返回一个日志记录器。"""
    logger = logging.getLogger(__name__)
    return logger

logger = setup_logger()

def rename_files(root_dir):
    """
    步骤1：
    单线程遍历目录，如果文件名中包含'7z'但不以'.7z'结尾，则重命名为'.7z'结尾。
    """
    logger.info("=== 步骤1：开始文件重命名 ===")
    print("=== 步骤1：开始文件重命名 ===")
    all_files = list(root_dir.rglob('*'))
    files_to_process = [path for path in all_files if path.is_file()]
    for file_path in tqdm(files_to_process, desc="重命名文件"):
        filename = file_path.name
        lower_name = filename.lower()
        # 如果文件名中包含'7z'但不以'.7z'结尾
        if '7z' in lower_name and not lower_name.endswith('.7z'):
            index = lower_name.find('7z')
            if index != -1:
                base_name = filename[:index+2]
                new_file_name = base_name + '.7z'
                new_file_path = file_path.with_name(new_file_name)
                try:
                    file_path.rename(new_file_path)
                    logger.info(f"已重命名文件: {file_path} -> {new_file_path}")
                except Exception as e:
                    logger.error(f"重命名文件失败: {file_path}. 错误: {e}")
    logger.info("=== 文件重命名完成 ===\n")
    print("=== 文件重命名完成 ===\n")

def collect_7z_files(root_dir):
    """
    步骤2：
    收集所有以'.7z'结尾的文件路径到列表中并返回。
    """
    logger.info("=== 步骤2：收集7z文件 ===")
    print("=== 步骤2：收集7z文件 ===")
    all_files = list(root_dir.rglob('*.7z'))
    if not all_files:
        logger.info("未找到任何7z文件。")
        print("未找到任何7z文件。")
    else:
        logger.info(f"共收集到 {len(all_files)} 个7z文件。")
        print(f"共收集到 {len(all_files)} 个7z文件。")
    logger.info("=== 收集7z文件完成 ===\n")
    print("=== 收集7z文件完成 ===\n")
    return all_files

def extract_7z_file(file_path, password):
    """
    解压单个7z文件，如果失败则抛出异常。
    py7zr的extractall默认覆盖同名文件，无需额外设置。
    """
    extract_path = file_path.parent  # 解压到与7z文件相同的目录
    logger.info(f"开始解压文件: {file_path} 到目录: {extract_path}")
    print(f"开始解压文件: {file_path}")
    start_time = time.time()
    try:
        with py7zr.SevenZipFile(file_path, mode='r', password=password) as z:
            # extractall会默认覆盖已有文件
            z.extractall(path=extract_path)
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"已成功解压: {file_path}，耗时: {elapsed_time:.2f} 秒")
        print(f"已成功解压: {file_path}，耗时: {elapsed_time:.2f} 秒")
    except Exception as e:
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.error(f"解压文件失败: {file_path}. 错误: {e}，耗时: {elapsed_time:.2f} 秒")
        print(f"解压文件失败: {file_path}. 错误: {e}，耗时: {elapsed_time:.2f} 秒")
        raise  # 抛出异常让上层捕获

def decompress_7z_files(all_7z_files, password):
    """
    步骤3：
    使用多进程解压指定列表中的所有7z文件。
    如果任意文件解压失败，则不删除7z文件并退出程序。
    """
    logger.info("=== 步骤3：开始解压7z文件 ===")
    print("=== 步骤3：开始解压7z文件 ===")
    if not all_7z_files:
        logger.info("无7z文件可解压。")
        print("无7z文件可解压。")
        return True  # 没有需要解压的文件当作成功

    extraction_failed = False

    with ProcessPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
        future_to_file = {executor.submit(extract_7z_file, file_path, password): file_path for file_path in all_7z_files}
        for future in tqdm(as_completed(future_to_file), total=len(future_to_file), desc="解压进度"):
            file_path = future_to_file[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"解压文件失败: {file_path}. 错误: {e}")
                extraction_failed = True
    
    if extraction_failed:
        logger.error("存在解压失败的文件，程序将退出并不会删除原始7z文件。")
        print("存在解压失败的文件，程序将退出并不会删除原始7z文件。")
        sys.exit(1)
    else:
        logger.info("=== 解压7z文件完成 ===\n")
        print("=== 解压7z文件完成 ===\n")
        return True

def delete_7z_files(all_7z_files):
    """
    步骤4：
    解压完成后，删除所有原始7z文件。
    """
    logger.info("=== 步骤4：开始删除已解压的7z文件 ===")
    print("=== 步骤4：开始删除已解压的7z文件 ===")
    for file_path in tqdm(all_7z_files, desc="删除7z文件"):
        try:
            file_path.unlink()
            logger.info(f"已删除7z文件: {file_path}")
        except Exception as e:
            logger.error(f"删除7z文件失败: {file_path}. 错误: {e}")
    logger.info("=== 已删除所有原始7z文件 ===\n")
    print("=== 已删除所有原始7z文件 ===\n")

def sanitize_filename_for_nas(filename, file_path):
    """
    处理文件名以确保NAS兼容性，并处理重名情况
    """
    import re
    import unicodedata
    from pathlib import Path

    # 最大文件名长度（不包括扩展名）
    MAX_BASENAME_LEN = 30

    # 替换或删除的特殊字符映射
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
        '　': ' ',  # 全角空格替换为半角空格
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

    # 1. 分离文件名和扩展名
    stem, suffix = os.path.splitext(filename)
    
    # 2. 替换特殊字符
    for old, new in REPLACEMENTS.items():
        stem = stem.replace(old, new)
    
    # 3. 移除表情符号和其他特殊Unicode字符
    stem = ''.join(c for c in stem if not unicodedata.combining(c) and c.isprintable())
    
    # 4. 将多个空格替换为单个空格
    stem = re.sub(r'\s+', ' ', stem)
    
    # 5. 移除开头和结尾的空格和点
    stem = stem.strip(' .')
    
    # 6. 确保文件名不为空
    if not stem:
        stem = 'file'
    
    # 7. 截断文件名（考虑中文字符）
    encoded_stem = stem.encode('utf-8')
    if len(encoded_stem) > MAX_BASENAME_LEN:
        # 按字节截断，确保不会破坏UTF-8编码
        while len(encoded_stem) > MAX_BASENAME_LEN:
            stem = stem[:-1]
            encoded_stem = stem.encode('utf-8')
    
    # 8. 处理重名文件
    parent_dir = Path(file_path).parent
    counter = 1
    new_name = f"{stem}{suffix}"
    
    while (parent_dir / new_name).exists():
        # 如果文件已存在，在文件名后添加数字
        new_stem = f"{stem}_{counter}"
        # 确保添加数字后的文件名不会超过长度限制
        while len(new_stem.encode('utf-8')) > MAX_BASENAME_LEN:
            stem = stem[:-1]
            new_stem = f"{stem}_{counter}"
        new_name = f"{new_stem}{suffix}"
        counter += 1
    
    # 9. 确保文件名的总长度不超过255字节（大多数文件系统的限制）
    while len(new_name.encode('utf-8')) > 255:
        if '_' in stem:
            stem = stem[:stem.rindex('_')]
        else:
            stem = stem[:-1]
        new_name = f"{stem}{suffix}"
    
    return new_name

def check_and_truncate_long_filenames(root_dir):
    """
    最终步骤前：
    检查文件名长度及无效字符，对文件名进行清理和截断以确保NAS兼容性。
    """
    logger.info("=== 最终步骤前：检查并处理文件名以确保NAS兼容性 ===")
    print("=== 最终步骤前：检查并处理文件名以确保NAS兼容性 ===")

    all_files = list(root_dir.rglob('*'))
    processed_count = 0
    error_count = 0

    # 按目录深度排序，确保先处理深层目录的文件
    all_files.sort(key=lambda x: len(x.parts), reverse=True)

    for file_path in tqdm(all_files, desc="处理文件名"):
        if file_path.is_file():
            original_filename = file_path.name
            try:
                # 处理文件名，传入完整的文件路径以处理重名情况
                new_name = sanitize_filename_for_nas(original_filename, file_path)
                new_file_path = file_path.with_name(new_name)
                
                # 如果文件名发生变化，则重命名
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
    print(f"=== 文件名处理完成: 成功处理 {processed_count} 个文件，失败 {error_count} 个 ===\n")

def all_done():
    """
    步骤5：
    所有任务完成后打印/记录消息。
    """
    logger.info("所有任务已完成。")
    print("\n所有任务已完成。")


if __name__ == "__main__":
    # 设置要处理的根目录和解压密码，请根据实际情况修改
    root_directory = Path("D:/b/")  # 修改为实际路径
    extract_password = '1151'            # 修改为实际密码

    logger.info(f"开始处理目录: {root_directory}\n")
    print(f"开始处理目录: {root_directory}\n")

    # 第一次循环 (1, 2, 3, 4)
    rename_files(root_directory)   # 步骤1
    all_7z_files = collect_7z_files(root_directory)  # 步骤2

    # 解压7z文件 (步骤3)
    # 如果解压失败，程序会在此处退出，不会执行后续删除操作
    decompress_7z_files(all_7z_files, extract_password)  

    # 解压成功后删除7z文件 (步骤4)
    delete_7z_files(all_7z_files)  

    # 第二次循环 (1, 2, 3, 4)
    rename_files(root_directory)   # 再次步骤1
    all_7z_files = collect_7z_files(root_directory)  # 再次步骤2

    # 再次解压7z文件 (步骤3)
    # 如果解压失败，程序会在此处退出，不会执行后续删除操作
    decompress_7z_files(all_7z_files, extract_password) 

    # 再次解压成功后删除7z文件 (再次步骤4)
    delete_7z_files(all_7z_files)  

    # 最终步骤前检查并截断过长的文件名
    check_and_truncate_long_filenames(root_directory)

    # 最终步骤5
    all_done()  # 步骤5
