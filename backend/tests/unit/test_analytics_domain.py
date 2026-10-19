"""Risk formula, coverage by approved cards and the metrics export (15)."""

import pytest

from app.modules.analytics.domain.coverage import aspects_covered_by, coverage_approved, matrix_cell
from app.modules.analytics.domain.metrics import CSV_ROWS, csv_rows, format_value, share
from app.modules.analytics.domain.risk import (
    RiskLevel,
    RiskThresholds,
    deadline_factor,
    holder_factor,
    risk_level,
    risk_score,
)
from app.modules.analytics.schemas import MetricsOut
from app.modules.interview.domain.aspects import ASPECT_KEYS
from app.modules.knowledge.domain.card_types import CardType


@pytest.mark.parametrize(("holders", "factor"), [(0, 1.0), (1, 0.6), (2, 0.3), (3, 0.1), (10, 0.1)])
def test_holder_factor(holders: int, factor: float) -> None:
    assert holder_factor(holders) == factor


@pytest.mark.parametrize(
    ("days", "factor"), [(None, 0.4), (-3, 1.0), (0, 1.0), (14, 1.0), (15, 0.7), (30, 0.7), (31, 0.4)]
)
def test_deadline_factor(days: int | None, factor: float) -> None:
    assert deadline_factor(days) == factor


def test_risk_score_is_the_product_of_factors() -> None:
    score = risk_score(criticality=3, holders=0, coverage_approved=0.5, days_left=21)
    assert score == pytest.approx(1.0 * 1.0 * 0.5 * 0.7)
    assert risk_score(criticality=2, holders=1, coverage_approved=0.0, days_left=None) == pytest.approx(
        2 / 3 * 0.6 * 0.4
    )


def test_fully_covered_process_has_no_risk() -> None:
    assert risk_score(criticality=3, holders=0, coverage_approved=1.0, days_left=1) == 0


@pytest.mark.parametrize(
    ("score", "level"),
    [(0.35, RiskLevel.HIGH), (0.9, RiskLevel.HIGH), (0.349, RiskLevel.MEDIUM), (0.15, RiskLevel.MEDIUM),
     (0.149, RiskLevel.LOW), (0.0, RiskLevel.LOW)],
)  # fmt: skip
def test_risk_levels(score: float, level: RiskLevel) -> None:
    assert risk_level(score, RiskThresholds()) is level


def test_thresholds_come_from_config() -> None:
    assert risk_level(0.3, RiskThresholds(high=0.25, medium=0.1)) is RiskLevel.HIGH


def test_a_single_holder_of_a_critical_process_near_the_deadline_is_high_risk() -> None:
    """The demo case: nobody else knows the report, three weeks left, nothing approved."""
    score = risk_score(criticality=3, holders=0, coverage_approved=0.0, days_left=21)
    assert risk_level(score, RiskThresholds()) is RiskLevel.HIGH


def test_card_types_cover_aspects() -> None:
    assert aspects_covered_by([CardType.PROCEDURE]) == {"steps", "tools", "inputs", "trigger"}
    assert aspects_covered_by([CardType.TERM]) == set()
    assert aspects_covered_by([]) == set()


def test_coverage_approved() -> None:
    assert coverage_approved([], set()) == 0
    assert coverage_approved([CardType.PROCEDURE], set()) == pytest.approx(4 / 11)
    assert coverage_approved([CardType.PROCEDURE, CardType.PITFALL], set()) == pytest.approx(5 / 11)


def test_not_applicable_aspects_are_excluded() -> None:
    assert coverage_approved([CardType.PROCEDURE], {"timing", "contacts"}) == pytest.approx(4 / 9)
    # «Not applicable» does not count as covered: it leaves the denominator.
    assert coverage_approved([], {"timing"}) == 0


def test_all_aspects_not_applicable_means_nothing_to_pass_on() -> None:
    all_types = list(CardType)
    assert coverage_approved(all_types, set()) == 1.0
    assert coverage_approved([], set(ASPECT_KEYS)) == 1.0


def test_matrix_cell() -> None:
    covered = {"steps"}
    assert matrix_cell("steps", covered, "missing", False) == "covered"
    assert matrix_cell("exceptions", covered, "covered", False) == "partial"  # told, not yet approved
    assert matrix_cell("exceptions", covered, "partial", False) == "partial"
    assert matrix_cell("exceptions", covered, "missing", False) == "missing"
    assert matrix_cell("steps", covered, "covered", True) == "not_applicable"


def test_share() -> None:
    assert share(1, 4) == 0.25
    assert share(0, 0) is None


def test_format_value() -> None:
    assert format_value(0.256, "share") == "25,6"
    assert format_value(None, "share") == ""
    assert format_value(42, "number") == "42"
    assert format_value(None, "number") == ""


def test_csv_rows_cover_every_metric_in_order() -> None:
    fields = {
        name
        for name, info in MetricsOut.model_fields.items()
        if info.annotation in (int, float | None, int | None)
    }
    exported = {field for field, _, _ in CSV_ROWS}
    assert exported == fields
    values = dict.fromkeys(exported, 1)
    rows = csv_rows(values)
    assert len(rows) == len(CSV_ROWS)
    assert rows[0][0].startswith("Время эксперта")
