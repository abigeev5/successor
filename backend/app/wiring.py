"""Composition root: the one place that knows every module.

- `import_models()` — registers all ORM tables in Base.metadata (Alembic, tests).
- `wire()` — registers event subscribers, job handlers and source resolvers of all modules
  (backend and worker). It starts from a clean registry, so calling it again is safe.
"""


def import_models() -> None:
    import app.core.jobs
    import app.core.storage
    import app.modules.analytics.models
    import app.modules.audit.models
    import app.modules.handovers.models
    import app.modules.identity.models
    import app.modules.interview.models
    import app.modules.knowledge.models
    import app.modules.org.models
    import app.modules.privacy.models  # noqa: F401


def wire() -> None:
    from app.core import jobs
    from app.core.events import bus
    from app.modules.analytics import handlers as analytics
    from app.modules.interview import handlers as interview
    from app.modules.knowledge import resolvers

    import_models()
    bus.clear()
    jobs.clear_handlers()
    resolvers.clear()
    interview.register(bus)
    analytics.register(bus)
