"""Turn analysis (output of analyze_turn) and how it updates the snapshot."""

import uuid
from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.interview.domain.aspects import BY_KEY
from app.modules.interview.domain.state import AspectState, ProcessCandidate, Snapshot
from app.modules.org.domain.matching import match_name

_RANK = {"missing": 0, "partial": 1, "covered": 2}


class AspectTouch(BaseModel):
    process_name: str | None = None
    aspect: str
    status: Literal["partial", "covered", "not_applicable"]


class NewProcess(BaseModel):
    name: str
    description: str = ""


class TurnAnalysis(BaseModel):
    """All fields have defaults: an empty answer from the model means «nothing learned»."""

    aspects_touched: list[AspectTouch] = Field(default_factory=list)
    is_vague: bool = False
    vague_reason: str | None = None
    new_processes: list[NewProcess] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)


def apply_analysis(snapshot: Snapshot, analysis: TurnAnalysis) -> tuple[Snapshot, set[tuple[uuid.UUID, str]]]:
    """Returns a new snapshot and the (process, aspect) pairs that changed. Statuses only go up."""
    result = deepcopy(snapshot)
    changed: set[tuple[uuid.UUID, str]] = set()
    names = [(p.id, p.name) for p in result.processes]

    for touch in analysis.aspects_touched:
        if touch.aspect not in BY_KEY:
            continue
        process_id = match_name(touch.process_name, names) or result.state.current_process_id
        if process_id is None or result.process(process_id) is None:
            continue
        aspects = result.aspects.setdefault(process_id, {})
        current = aspects.get(touch.aspect, AspectState())
        if touch.status == "not_applicable":
            updated = (
                current if current.status == "covered" else AspectState(status="covered", not_applicable=True)
            )
        elif _RANK[touch.status] > _RANK[current.status]:
            updated = AspectState(status=touch.status, not_applicable=False)
        else:
            updated = current
        if updated != current:
            aspects[touch.aspect] = updated
            changed.add((process_id, touch.aspect))

    known = names + [(uuid.uuid4(), c.name) for c in result.state.candidates]
    for new in analysis.new_processes:
        name = new.name.strip()
        if name and match_name(name, known) is None:
            result.state.candidates.append(ProcessCandidate(name=name, description=new.description.strip()))
            known.append((uuid.uuid4(), name))
    return result, changed
