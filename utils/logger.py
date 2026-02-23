import logging
import sys
from pathlib import Path


LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

_fmt = logging.Formatter(
    fmt="%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_fmt)

    # File handler (DEBUG and above)
    fh = logging.FileHandler(LOG_DIR / "orchestrator.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger
