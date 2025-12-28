import logging
import sys
from pathlib import Path
from typing import Union


def ensure_utf8_stdio() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        # Best effort; avoid crashing on unsupported terminals.
        pass


def get_file_logger(
    name: str = "paxishi",
    log_path: Union[str, Path] = "process.log",
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        try:
            handler = logging.FileHandler(log_path, "a", encoding="utf-8")
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        except Exception:
            logger.addHandler(logging.NullHandler())

    return logger
