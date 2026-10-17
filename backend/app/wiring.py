"""Composition root: the one place that knows every module.

- `import_models()` — registers all ORM tables in Base.metadata (Alembic, tests).
- `wire()` — registers event subscribers and job handlers of all modules (backend and worker).
  Each module exposes `register(bus)` in its handlers.py once it has any; add the call here.
"""

_wired = False


def import_models() -> None:
    import app.core.jobs
    import app.modules.audit.models
    import app.modules.handovers.models
    import app.modules.identity.models
    import app.modules.org.models  # noqa: F401


def wire() -> None:
    global _wired
    if _wired:
        return
    import_models()
    _wired = True
