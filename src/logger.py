"""Lightweight logging + refresh-log helpers."""
from __future__ import annotations

import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

import config


def get_logger(name: str = "oem_tracker") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(config.LOGS_DIR / "tracker.log")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


REFRESH_LOG_FIELDS = [
    "refresh_timestamp",
    "current_date",
    "raw_records",
    "accepted_records",
    "rejected_records",
    "unmapped_candidates",
    "companies",
    "duration_seconds",
    "status",
    "notes",
]


def append_refresh_log(row: dict, path: Path = config.REFRESH_LOG) -> None:
    """Append one row to refresh_log.csv, creating header if needed."""
    exists = path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REFRESH_LOG_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in REFRESH_LOG_FIELDS})
