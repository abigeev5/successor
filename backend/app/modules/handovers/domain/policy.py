"""Pure access policy for a handover.

admin     — every handover;
manager   — the handover's manager, or a manager of the handover's org unit;
expert    — a member with role expert;
successor — a member with role successor.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum


class HandoverRole(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    EXPERT = "expert"
    SUCCESSOR = "successor"


@dataclass(frozen=True)
class Viewer:
    user_id: uuid.UUID
    global_role: str  # identity.UserRole value
    org_unit_id: uuid.UUID | None


@dataclass(frozen=True)
class HandoverFacts:
    manager_id: uuid.UUID
    org_unit_id: uuid.UUID
    member_role: str | None  # MemberRole value of the viewer in this handover, if any


def resolve_role(viewer: Viewer, handover: HandoverFacts) -> HandoverRole | None:
    if viewer.global_role == "admin":
        return HandoverRole.ADMIN
    if viewer.global_role == "manager" and (
        handover.manager_id == viewer.user_id
        or (viewer.org_unit_id is not None and viewer.org_unit_id == handover.org_unit_id)
    ):
        return HandoverRole.MANAGER
    if handover.member_role == "expert":
        return HandoverRole.EXPERT
    if handover.member_role == "successor":
        return HandoverRole.SUCCESSOR
    return None
