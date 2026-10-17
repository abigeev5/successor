"""Logging setup.

Rule (SPEC, 12): logs never contain user texts — questions, answers, transcripts, messages.
Log ids, statuses and timings only.
"""

import logging


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
