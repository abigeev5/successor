import uuid

import pytest

from app.modules.handovers.domain.policy import HandoverFacts, HandoverRole, Viewer, resolve_role

UNIT = uuid.uuid4()
OTHER_UNIT = uuid.uuid4()
MANAGER = uuid.uuid4()


def facts(member_role: str | None = None, org_unit: uuid.UUID = UNIT) -> HandoverFacts:
    return HandoverFacts(manager_id=MANAGER, org_unit_id=org_unit, member_role=member_role)


def viewer(role: str, org_unit: uuid.UUID | None = None, user_id: uuid.UUID | None = None) -> Viewer:
    return Viewer(user_id=user_id or uuid.uuid4(), global_role=role, org_unit_id=org_unit)


def test_admin_sees_everything() -> None:
    assert resolve_role(viewer("admin"), facts()) is HandoverRole.ADMIN


def test_handover_manager_has_access_even_from_other_unit() -> None:
    assert resolve_role(viewer("manager", OTHER_UNIT, MANAGER), facts()) is HandoverRole.MANAGER


def test_manager_of_same_unit_has_access() -> None:
    assert resolve_role(viewer("manager", UNIT), facts()) is HandoverRole.MANAGER


def test_manager_of_other_unit_has_no_access() -> None:
    assert resolve_role(viewer("manager", OTHER_UNIT), facts()) is None


def test_manager_without_unit_has_no_access() -> None:
    assert resolve_role(viewer("manager", None), facts()) is None


@pytest.mark.parametrize(
    ("member_role", "expected"),
    [("expert", HandoverRole.EXPERT), ("successor", HandoverRole.SUCCESSOR), (None, None)],
)
def test_membership_defines_role(member_role: str | None, expected: HandoverRole | None) -> None:
    # The global role does not matter for members: one person may be an expert here and a successor there.
    assert resolve_role(viewer("successor", UNIT), facts(member_role)) is expected


def test_expert_of_other_handover_has_no_access() -> None:
    assert resolve_role(viewer("expert", UNIT), facts(None)) is None
