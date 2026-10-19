"""In-process domain event bus.

- `subscribe` — handler runs inside the publisher's transaction (cheap work: audit, metrics, status changes).
- `subscribe_job` — a row is added to `jobs` in the same transaction; the worker does the heavy work later.

Lower modules publish events; higher modules subscribe. This keeps imports pointing downward.
"""

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

from pydantic_core import to_jsonable_python
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs


@dataclass(frozen=True)
class Event:
    """Base class for domain events. Subclasses are frozen dataclasses with ids, not ORM objects."""


EventHandler = Callable[[AsyncSession, Any], Awaitable[None]]


@dataclass(frozen=True)
class _JobSubscription:
    job_type: str
    payload: Callable[[Any], dict[str, Any]] | None
    dedup_key: Callable[[Any], str] | None


def _default_payload(event: Event) -> dict[str, Any]:
    return to_jsonable_python(asdict(event))  # type: ignore[no-any-return]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[EventHandler]] = defaultdict(list)
        self._jobs: dict[type[Event], list[_JobSubscription]] = defaultdict(list)

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def subscribe_job(
        self,
        event_type: type[Event],
        job_type: str,
        *,
        dedup_key: Callable[[Any], str] | None = None,
        payload: Callable[[Any], dict[str, Any]] | None = None,
    ) -> None:
        self._jobs[event_type].append(_JobSubscription(job_type, payload, dedup_key))

    async def publish(self, db: AsyncSession, event: Event) -> None:
        for handler in self._handlers.get(type(event), []):
            await handler(db, event)
        for sub in self._jobs.get(type(event), []):
            payload = sub.payload(event) if sub.payload else _default_payload(event)
            key = sub.dedup_key(event) if sub.dedup_key else None
            await jobs.enqueue(db, sub.job_type, payload, dedup_key=key)

    def clear(self) -> None:
        """For tests."""
        self._handlers.clear()
        self._jobs.clear()


bus = EventBus()
