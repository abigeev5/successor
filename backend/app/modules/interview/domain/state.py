"""Interview state.

Aspect coverage lives in the `process_aspects` table (shared by all sessions of a handover).
`interview_sessions.state_json` keeps only per-session things: phase, current process, candidates, probes.
"""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.interview.domain.aspects import ASPECT_KEYS

AspectStatus = Literal["missing", "partial", "covered"]


class Phase(StrEnum):
    INTRO = "intro"
    MAP = "map"
    WALKTHROUGH = "walkthrough"
    DEEPEN = "deepen"
    WRAPUP = "wrapup"
    DONE = "done"


class AspectState(BaseModel):
    status: AspectStatus = "missing"
    not_applicable: bool = False


class ProcessInfo(BaseModel):
    id: uuid.UUID
    name: str
    criticality: int = 2


class ProcessCandidate(BaseModel):
    name: str
    description: str = ""


class Probe(BaseModel):
    process_id: uuid.UUID | None = None
    aspect: str | None = None
    kind: str


class InterviewState(BaseModel):
    schema_version: int = 1
    phase: Phase = Phase.INTRO
    current_process_id: uuid.UUID | None = None
    done_process_ids: list[uuid.UUID] = Field(default_factory=list)
    candidates: list[ProcessCandidate] = Field(default_factory=list)
    map_questions: int = 0
    last_probe: Probe | None = None
    probe_streak: int = 0


@dataclass
class Snapshot:
    """Everything the planner needs; built by the service from the DB."""

    state: InterviewState
    processes: list[ProcessInfo]
    aspects: dict[uuid.UUID, dict[str, AspectState]] = field(default_factory=dict)

    def aspects_of(self, process_id: uuid.UUID) -> dict[str, AspectState]:
        current = self.aspects.get(process_id, {})
        return {key: current.get(key, AspectState()) for key in ASPECT_KEYS}

    def process(self, process_id: uuid.UUID | None) -> ProcessInfo | None:
        return next((p for p in self.processes if p.id == process_id), None)


def coverage(aspects: dict[str, AspectState]) -> float:
    """(covered + 0.5·partial) / 11; «not applicable» counts as covered."""
    score = 0.0
    for key in ASPECT_KEYS:
        state = aspects.get(key, AspectState())
        if state.status == "covered" or state.not_applicable:
            score += 1.0
        elif state.status == "partial":
            score += 0.5
    return score / len(ASPECT_KEYS)
