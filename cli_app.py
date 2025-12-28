#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional

from tqdm import tqdm

from paxishi_extractor import ensure_utf8_stdio, get_file_logger, run_pipeline

ensure_utf8_stdio()


class CLIProgress:
    def __init__(self) -> None:
        self.bar: Optional[tqdm] = None

    def status(self, message: str) -> None:
        if self.bar:
            self.bar.close()
            self.bar = None
        print(message)

    def progress(self, current: int, total: int) -> None:
        if current == 0:
            if self.bar:
                self.bar.close()
                self.bar = None
            return
        if self.bar is None:
            self.bar = tqdm(total=total, desc="进度", leave=False)
        if self.bar.total != total:
            self.bar.total = total
        self.bar.n = current
        self.bar.refresh()
        if current >= total:
            self.bar.close()
            self.bar = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PaXiShi 7z batch extractor")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("D:/b/"),
        help="Root directory to process (default: D:/b/)",
    )
    parser.add_argument(
        "--password",
        type=str,
        default="1151",
        help="Archive password (default: 1151)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger = get_file_logger("paxishi.cli")
    progress = CLIProgress()

    def executor_factory() -> ProcessPoolExecutor:
        return ProcessPoolExecutor(
            max_workers=os.cpu_count() or 4,
            mp_context=multiprocessing.get_context("spawn"),
        )

    ok = run_pipeline(
        args.root,
        args.password,
        logger=logger,
        status_cb=progress.status,
        progress_cb=progress.progress,
        executor_factory=executor_factory,
    )

    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
