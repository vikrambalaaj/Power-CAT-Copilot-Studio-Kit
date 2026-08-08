"""Structured logger factory backed by structlog with fallback."""
from __future__ import annotations

import logging

try:
    import structlog
    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False


class _LoggerAdapter:
    def __init__(self, logger):
        self._logger = logger

    def debug(self, msg, *args, **kwargs):
        if kwargs:
            msg = f"{msg} {kwargs}"
        self._logger.debug(msg, *args)

    def info(self, msg, *args, **kwargs):
        if kwargs:
            msg = f"{msg} {kwargs}"
        self._logger.info(msg, *args)

    def warning(self, msg, *args, **kwargs):
        if kwargs:
            msg = f"{msg} {kwargs}"
        self._logger.warning(msg, *args)

    def error(self, msg, *args, **kwargs):
        if kwargs:
            msg = f"{msg} {kwargs}"
        self._logger.error(msg, *args)


def get_logger(name: str):
    if HAS_STRUCTLOG:
        return structlog.get_logger(name)
    logger = logging.getLogger(name)
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)
    return _LoggerAdapter(logger)
