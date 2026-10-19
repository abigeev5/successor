import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.modules.analytics.domain.coverage import CellStatus
from app.modules.analytics.domain.risk import RiskLevel
from app.modules.org.schemas import HolderOut


class AspectCellOut(BaseModel):
    key: str
    label: str
    status: CellStatus


class ProcessRiskOut(BaseModel):
    process_id: uuid.UUID
    name: str
    criticality: int
    holders: list[HolderOut]  # who else knows it (not the leaving expert)
    coverage: float  # coverage_approved, 0..1
    open_gaps: int  # open gaps of the active handovers of this process
    deadline: date | None  # the nearest deadline among active handovers
    days_left: int | None
    risk: float
    level: RiskLevel
    aspects: list[AspectCellOut]  # the «processes × aspects» matrix row


class RiskMapOut(BaseModel):
    org_unit_id: uuid.UUID
    org_unit_name: str
    high_threshold: float
    medium_threshold: float
    processes: list[ProcessRiskOut]  # sorted by risk, highest first


class HandoverProgressOut(BaseModel):
    handover_id: uuid.UUID
    deadline: date | None
    days_left: int | None
    interview_sessions: int
    interview_minutes: int
    recordings: int
    recording_minutes: int
    review_minutes: int
    cards_draft: int
    cards_approved: int
    cards_rejected: int
    open_gaps: int
    processes: list[ProcessRiskOut]


class OpenGapOut(BaseModel):
    id: uuid.UUID
    handover_id: uuid.UUID
    question: str
    created_at: datetime


class MetricsOut(BaseModel):
    """Product metrics for a period. Shares are 0..1 or null when there is nothing to divide."""

    handover_id: uuid.UUID | None
    org_unit_id: uuid.UUID
    date_from: date | None
    date_to: date | None
    expert_minutes: int
    interview_minutes: int
    recording_minutes: int
    review_minutes: int
    interview_turns: int
    recordings_processed: int
    cards_generated: int
    cards_dropped_no_evidence: int
    cards_approved: int
    cards_approved_edited: int
    cards_rejected: int
    approved_share: float | None  # of generated cards
    questions: int
    answered_share: float | None
    partial_share: float | None
    refused_share: float | None
    helpful_share: float | None  # «помогло» among rated answers
    feedback_count: int
    answer_latency_p95_ms: int | None
    gaps_created: int
    gaps_answered: int
    gaps_open_now: int
    key_processes_coverage: float | None  # mean coverage_approved of processes with criticality 3
    top_open_gaps: list[OpenGapOut]


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    at: datetime
    user_id: uuid.UUID | None
    user_name: str | None
    action: str
    entity: str
    entity_id: uuid.UUID | None
    meta: dict[str, Any]
