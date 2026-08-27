"""Daily file logging with defensive secret redaction."""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"-----BEGIN(?: ENCRYPTED)? PRIVATE KEY-----.*?-----END(?: ENCRYPTED)? PRIVATE KEY-----", re.S),
    re.compile(r"(?i)(passphrase|password|api[_ -]?key|secret)\s*[:=]\s*\S+"),
    re.compile(r"(?i)TECHNOCORE_IDENTITY_PASSPHRASE=\S+"),
]


def redact(value: Any) -> str:
    text = str(value)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        return redact(rendered)


def get_logger(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("arxiv_research_agent")
    logger.setLevel(logging.INFO)
    target = (log_dir / (datetime.now().date().isoformat() + ".log")).resolve()
    if not any(
        isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename).resolve() == target
        for handler in logger.handlers
    ):
        handler = logging.FileHandler(target, encoding="utf-8")
        handler.setFormatter(
            RedactingFormatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    logger.propagate = False
    return logger
