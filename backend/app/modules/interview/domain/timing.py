"""Active expert time: sum of gaps between messages, pauses longer than 5 minutes dropped."""

from datetime import datetime

MAX_GAP_S = 5 * 60


def active_increment(previous: datetime | None, now: datetime) -> int:
    if previous is None:
        return 0
    gap = (now - previous).total_seconds()
    return int(gap) if 0 < gap <= MAX_GAP_S else 0
