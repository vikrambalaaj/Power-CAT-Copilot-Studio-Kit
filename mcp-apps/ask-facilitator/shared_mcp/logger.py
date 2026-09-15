"""Structured logging for shared MCP components."""
from __future__ import annotations

import logging
import os
import sys

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


class StructLogAdapter:
    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def debug(self, msg: str, **kwargs):
        self._logger.debug(f"{msg} {kwargs if kwargs else ''}")

    def info(self, msg: str, **kwargs):
        self._logger.info(f"{msg} {kwargs if kwargs else ''}")

    def warning(self, msg: str, **kwargs):
        self._logger.warning(f"{msg} {kwargs if kwargs else ''}")

    def error(self, msg: str, **kwargs):
        self._logger.error(f"{msg} {kwargs if kwargs else ''}")


def get_logger(name: str) -> StructLogAdapter:
    return StructLogAdapter(logging.getLogger(name))
