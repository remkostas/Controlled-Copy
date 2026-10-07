"""Extractors for the PDF time-limit test. Must live in an importable module (spawned child)."""

import time


def never_finishes(data: bytes, max_pages: int):
    time.sleep(60)
    return "ok", []
