"""Bus-factor risk of a process (SPEC 7.9). Pure: no database.

holder_factor   = 1.0 if nobody else knows the process; 0.6 one person; 0.3 two; 0.1 more
deadline_factor = 1.0 if ≤ 14 days left (or overdue); 0.7 if ≤ 30; 0.4 otherwise or no deadline
risk            = criticality/3 × holder_factor × (1 − coverage_approved) × deadline_factor
"""

from dataclasses import dataclass
from enum import StrEnum


class RiskLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class RiskThresholds:
    """Level boundaries; from settings RISK_HIGH / RISK_MEDIUM."""

    high: float = 0.35
    medium: float = 0.15


def holder_factor(holders: int) -> float:
    """`holders` — people with level owner/knows, not counting the expert of an active handover."""
    if holders <= 0:
        return 1.0
    if holders == 1:
        return 0.6
    if holders == 2:
        return 0.3
    return 0.1


def deadline_factor(days_left: int | None) -> float:
    if days_left is None:
        return 0.4
    if days_left <= 14:
        return 1.0
    if days_left <= 30:
        return 0.7
    return 0.4


def risk_score(*, criticality: int, holders: int, coverage_approved: float, days_left: int | None) -> float:
    return criticality / 3 * holder_factor(holders) * (1 - coverage_approved) * deadline_factor(days_left)


def risk_level(score: float, thresholds: RiskThresholds) -> RiskLevel:
    if score >= thresholds.high:
        return RiskLevel.HIGH
    if score >= thresholds.medium:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
