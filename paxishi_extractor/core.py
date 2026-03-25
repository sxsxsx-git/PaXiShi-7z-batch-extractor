import logging
import os
import time
from concurrent.futures import Executor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

import py7zr

from .logging_utils import get_file_logger

ProgressCallback = Callable[[int, int], None]
StatusCallback = Callable[[str], None]
StopCallback = Callable[[], bool]


@dataclass
class RenameStats:
    processed: int = 0
    renamed: int = 0
    failed: int = 0


@dataclass
class DeleteStats:
    deleted: int = 0
    failed: int = 0


def _call_progress(progress_cb: Optional[ProgressCallback], current: int, total: int) -> None:
    if progress_cb:
        progress_cb(current, total)


def _should_stop(stop_cb: Optional[StopCallback]) -> bool:
    return bool(stop_cb and stop_cb())


def rename_7z_suffixes(
    root_dir: Path,
    logger: Optional[logging.Logger] = None,
    progress_cb: Optional[ProgressCallback] = None,
    should_stop: Optional[StopCallback] = None,
) -> RenameStats:
    logger = logger or logging.getLogger(__name__)
    files = [path for path in Path(root_dir).rglob("*") if path.is_file()]
    stats = RenameStats(processed=len(files))

    for index, file_path in enumerate(files):
        if _should_stop(should_stop):
            break
        _call_progress(progress_cb, index + 1, stats.processed)

        filename = file_path.name
        lower_name = filename.lower()
        if "7z" in lower_name and not lower_name.endswith(".7z"):
            pos = lower_name.find("7z")
            if pos != -1:
                base_name = filename[: pos + 2]
                new_file_name = base_name + ".7z"
                new_file_path = file_path.with_name(new_file_name)
                try:
                    file_path.rename(new_file_path)
                    stats.renamed += 1
                    logger.info("Renamed file: %s -> %s", file_path, new_file_path)
                except Exception as exc:
                    stats.failed += 1
                    logger.error("Rename failed: %s (%s)", file_path, exc)

    logger.info(
        "Rename complete: processed=%s renamed=%s failed=%s",
        stats.processed,
        stats.renamed,
        stats.failed,
    )
    return stats


def collect_7z_files(root_dir: Path, logger: Optional[logging.Logger] = None) -> list[Path]:
    logger = logger or logging.getLogger(__name__)
    files = list(Path(root_dir).rglob("*.7z"))
    if not files:
        logger.info("No 7z files found.")
    else:
        logger.info("Collected %s 7z files.", len(files))
    return files


def extract_7z_file(
    file_path: Path,
    password: Optional[str],
    logger: Optional[logging.Logger] = None,
) -> bool:
    logger = logger or get_file_logger()
    extract_path = Path(file_path).parent
    start_time = time.time()
    try:
        logger.info("Extracting %s to %s", file_path, extract_path)
        with py7zr.SevenZipFile(file_path, mode="r", password=password or None) as archive:
            archive.extractall(path=extract_path)
        elapsed = time.time() - start_time
        logger.info("Extracted %s in %.2f seconds", file_path, elapsed)
        return True
    except Exception as exc:
        elapsed = time.time() - start_time
        logger.error("Extract failed: %s (%s) in %.2f seconds", file_path, exc, elapsed)
        raise


def decompress_7z_files(
    files: Iterable[Path],
    password: Optional[str],
    logger: Optional[logging.Logger] = None,
    progress_cb: Optional[ProgressCallback] = None,
    executor: Optional[Executor] = None,
    should_stop: Optional[StopCallback] = None,
) -> bool:
    logger = logger or logging.getLogger(__name__)
    file_list = list(files)
    if not file_list:
        logger.info("No 7z files to extract.")
        return True

    total = len(file_list)
    success_count = 0
    error_count = 0

    if executor:
        future_to_file = {
            executor.submit(extract_7z_file, file_path, password, None): file_path
            for file_path in file_list
        }
        completed = 0
        for future in as_completed(future_to_file):
            if _should_stop(should_stop):
                logger.warning("Extraction stopped by user.")
                return False
            completed += 1
            _call_progress(progress_cb, completed, total)
            file_path = future_to_file[future]
            try:
                future.result()
                success_count += 1
            except Exception as exc:
                error_count += 1
                logger.error("Extract failed: %s (%s)", file_path, exc)
    else:
        for index, file_path in enumerate(file_list):
            if _should_stop(should_stop):
                logger.warning("Extraction stopped by user.")
                return False
            _call_progress(progress_cb, index + 1, total)
            try:
                extract_7z_file(file_path, password, logger)
                success_count += 1
            except Exception as exc:
                error_count += 1
                logger.error("Extract failed: %s (%s)", file_path, exc)

    if error_count:
        logger.error("Extraction failed: success=%s failed=%s", success_count, error_count)
        return False

    logger.info("Extraction complete: success=%s failed=%s", success_count, error_count)
    return True


def delete_files(
    files: Iterable[Path],
    logger: Optional[logging.Logger] = None,
    progress_cb: Optional[ProgressCallback] = None,
    should_stop: Optional[StopCallback] = None,
) -> DeleteStats:
    logger = logger or logging.getLogger(__name__)
    file_list = list(files)
    total = len(file_list)
    stats = DeleteStats()

    for index, file_path in enumerate(file_list):
        if _should_stop(should_stop):
            break
        _call_progress(progress_cb, index + 1, total)
        try:
            file_path.unlink()
            stats.deleted += 1
            logger.info("Deleted file: %s", file_path)
        except Exception as exc:
            stats.failed += 1
            logger.error("Delete failed: %s (%s)", file_path, exc)

    logger.info("Delete complete: deleted=%s failed=%s", stats.deleted, stats.failed)
    return stats


def sanitize_filename_for_nas(filename: str, file_path: Path) -> str:
    import re
    import unicodedata

    max_basename_len = 30
    replacements = {
        "【": "[",
        "】": "]",
        "！": "!",
        "？": "?",
        "：": "-",
        "；": ";",
        "，": ",",
        "（": "(",
        "）": ")",
        "　": " ",
        "@": "at",
        "|": "-",
        "\\": "-",
        "/": "-",
        "*": "-",
        "?": "-",
        '"': "'",
        "<": "(",
        ">": ")",
        "\n": " ",
        "\r": " ",
        "\t": " ",
    }

    stem, suffix = os.path.splitext(filename)

    for old, new in replacements.items():
        stem = stem.replace(old, new)

    stem = "".join(c for c in stem if not unicodedata.combining(c) and c.isprintable())
    stem = re.sub(r"\s+", " ", stem).strip(" .")

    if not stem:
        stem = "file"

    encoded_stem = stem.encode("utf-8")
    while len(encoded_stem) > max_basename_len:
        stem = stem[:-1]
        encoded_stem = stem.encode("utf-8")

    parent_dir = Path(file_path).parent
    new_name = f"{stem}{suffix}"
    candidate_path = parent_dir / new_name

    def is_self(path: Path) -> bool:
        try:
            return path.resolve() == Path(file_path).resolve()
        except Exception:
            return path == file_path

    counter = 1
    while candidate_path.exists() and not is_self(candidate_path):
        new_stem = f"{stem}_{counter}"
        while len(new_stem.encode("utf-8")) > max_basename_len:
            stem = stem[:-1]
            new_stem = f"{stem}_{counter}"
        new_name = f"{new_stem}{suffix}"
        candidate_path = parent_dir / new_name
        counter += 1

    while len(new_name.encode("utf-8")) > 255:
        if "_" in stem:
            stem = stem[: stem.rindex("_")]
        else:
            stem = stem[:-1]
        new_name = f"{stem}{suffix}"

    return new_name


def check_and_truncate_long_filenames(
    root_dir: Path,
    logger: Optional[logging.Logger] = None,
    progress_cb: Optional[ProgressCallback] = None,
    should_stop: Optional[StopCallback] = None,
) -> RenameStats:
    logger = logger or logging.getLogger(__name__)
    all_files = list(Path(root_dir).rglob("*"))
    all_files.sort(key=lambda path: len(path.parts), reverse=True)

    stats = RenameStats(processed=len(all_files))
    total = len(all_files)

    for index, file_path in enumerate(all_files):
        if _should_stop(should_stop):
            break
        _call_progress(progress_cb, index + 1, total)
        if not file_path.is_file():
            continue
        try:
            new_name = sanitize_filename_for_nas(file_path.name, file_path)
            new_file_path = file_path.with_name(new_name)
            if new_file_path != file_path:
                file_path.rename(new_file_path)
                stats.renamed += 1
                logger.info("Renamed file: %s -> %s", file_path, new_file_path)
        except Exception as exc:
            stats.failed += 1
            logger.error("Filename sanitize failed: %s (%s)", file_path, exc)

    logger.info(
        "Filename check complete: processed=%s renamed=%s failed=%s",
        stats.processed,
        stats.renamed,
        stats.failed,
    )
    return stats


def run_pipeline(
    root_dir: Path,
    password: Optional[str],
    logger: Optional[logging.Logger] = None,
    status_cb: Optional[StatusCallback] = None,
    progress_cb: Optional[ProgressCallback] = None,
    executor_factory: Optional[Callable[[], Executor]] = None,
    should_stop: Optional[StopCallback] = None,
) -> bool:
    logger = logger or logging.getLogger(__name__)
    root_dir = Path(root_dir)

    def update_status(message: str) -> None:
        if status_cb:
            status_cb(message)
        logger.info(message)

    def reset_progress() -> None:
        if progress_cb:
            progress_cb(0, 1)

    def run_decompress(files: Iterable[Path]) -> bool:
        if executor_factory:
            executor = executor_factory()
            try:
                return decompress_7z_files(
                    files,
                    password,
                    logger=logger,
                    progress_cb=progress_cb,
                    executor=executor,
                    should_stop=should_stop,
                )
            finally:
                executor.shutdown(wait=False)
        return decompress_7z_files(
            files,
            password,
            logger=logger,
            progress_cb=progress_cb,
            executor=None,
            should_stop=should_stop,
        )

    update_status("步骤1：开始文件重命名")
    reset_progress()
    rename_7z_suffixes(root_dir, logger=logger, progress_cb=progress_cb, should_stop=should_stop)
    if _should_stop(should_stop):
        return False

    update_status("步骤2：收集7z文件")
    reset_progress()
    all_7z_files = collect_7z_files(root_dir, logger=logger)
    if _should_stop(should_stop):
        return False

    update_status("步骤3：开始解压7z文件")
    reset_progress()
    if not run_decompress(all_7z_files):
        return False
    if _should_stop(should_stop):
        return False

    update_status("步骤4：删除已解压的7z文件")
    reset_progress()
    delete_files(all_7z_files, logger=logger, progress_cb=progress_cb, should_stop=should_stop)
    if _should_stop(should_stop):
        return False

    update_status("再次步骤1：开始文件重命名")
    reset_progress()
    rename_7z_suffixes(root_dir, logger=logger, progress_cb=progress_cb, should_stop=should_stop)
    if _should_stop(should_stop):
        return False

    update_status("再次步骤2：收集7z文件")
    reset_progress()
    all_7z_files = collect_7z_files(root_dir, logger=logger)
    if _should_stop(should_stop):
        return False

    update_status("再次步骤3：开始解压7z文件")
    reset_progress()
    if not run_decompress(all_7z_files):
        return False
    if _should_stop(should_stop):
        return False

    update_status("再次步骤4：删除已解压的7z文件")
    reset_progress()
    delete_files(all_7z_files, logger=logger, progress_cb=progress_cb, should_stop=should_stop)
    if _should_stop(should_stop):
        return False

    update_status("最终步骤：检查并处理文件名")
    reset_progress()
    check_and_truncate_long_filenames(
        root_dir,
        logger=logger,
        progress_cb=progress_cb,
        should_stop=should_stop,
    )

    if _should_stop(should_stop):
        return False

    update_status("所有任务已完成！")
    return True
