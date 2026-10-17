import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest

from app.core import events, jobs
from app.core.events import Event, EventBus


@dataclass(frozen=True)
class SomethingHappened(Event):
    item_id: uuid.UUID
    version: int


async def test_sync_subscribers_run_in_order() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def first(db: Any, event: SomethingHappened) -> None:
        seen.append(f"first:{event.version}")

    async def second(db: Any, event: SomethingHappened) -> None:
        seen.append(f"second:{event.version}")

    bus.subscribe(SomethingHappened, first)
    bus.subscribe(SomethingHappened, second)
    await bus.publish(db=None, event=SomethingHappened(uuid.uuid4(), 2))  # type: ignore[arg-type]
    assert seen == ["first:2", "second:2"]


async def test_job_subscription_enqueues_with_payload_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any], str | None]] = []

    async def fake_enqueue(db: Any, job_type: str, payload: dict[str, Any], *, dedup_key: str | None) -> None:
        calls.append((job_type, payload, dedup_key))

    monkeypatch.setattr(events.jobs, "enqueue", fake_enqueue)
    bus = EventBus()
    bus.subscribe_job(SomethingHappened, "index_item", dedup_key=lambda e: f"index:{e.item_id}:{e.version}")
    item_id = uuid.uuid4()
    await bus.publish(db=None, event=SomethingHappened(item_id, 3))  # type: ignore[arg-type]
    assert calls == [("index_item", {"item_id": str(item_id), "version": 3}, f"index:{item_id}:3")]


async def test_events_of_other_types_are_not_delivered() -> None:
    @dataclass(frozen=True)
    class Other(Event):
        pass

    bus = EventBus()
    seen: list[Any] = []

    async def handler(db: Any, event: Any) -> None:
        seen.append(event)

    bus.subscribe(SomethingHappened, handler)
    await bus.publish(db=None, event=Other())  # type: ignore[arg-type]
    assert seen == []


@pytest.mark.parametrize(("attempts", "seconds"), [(1, 5), (2, 10), (3, 20)])
def test_backoff_is_exponential(attempts: int, seconds: int) -> None:
    assert jobs.backoff_delay(attempts, base_s=5) == timedelta(seconds=seconds)


def test_handler_cannot_be_registered_twice() -> None:
    async def a(ctx: Any, payload: Any) -> None: ...

    async def b(ctx: Any, payload: Any) -> None: ...

    jobs.clear_handlers()
    jobs.register_handler("x", a)
    jobs.register_handler("x", a)  # same handler again is fine (idempotent wiring)
    with pytest.raises(ValueError):
        jobs.register_handler("x", b)
    jobs.clear_handlers()
