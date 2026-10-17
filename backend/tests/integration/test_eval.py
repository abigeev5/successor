"""`make eval` (SPEC 11.2): the script runs on the demo data and derives refusals for every threshold."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.search.models import CardChunk
from app.providers.registry import build_providers

REPO = Path(__file__).resolve().parents[3]


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


def row(ev: ModuleType, answerable: bool, cosine: float, coverage: float, status: str = "answered") -> object:
    item = ev.Item("q", "?", answerable, False, "ответ", ["Карточка"] if answerable else [])
    return ev.Row(item, status, None, "ответ [1]", ["Карточка"], 1.0, "verified", cosine, 1, coverage, 10)


def test_refusals_are_derived_for_each_threshold() -> None:
    ev = load("run_eval", REPO / "eval" / "run_eval.py")
    rows = [
        row(ev, True, 0.70, 0.2),  # found by meaning
        row(ev, True, 0.35, 0.9),  # found by words
        row(ev, False, 0.40, 0.3),  # refused from 0.45 on
        row(ev, False, 0.80, 0.9, status="refused"),  # the LLM said NO_ANSWER: refused at any threshold
    ]
    low = ev.compute(rows, ev.Thresholds(0.30, 0.6))
    assert (low.correct_refusals, low.false_refusals) == (0.5, 0.0)
    mid = ev.compute(rows, ev.Thresholds(0.45, 0.6))
    assert (mid.correct_refusals, mid.false_refusals, mid.citation_recall) == (1.0, 0.0, 1.0)
    high = ev.compute(rows, ev.Thresholds(0.75, 0.95))
    assert high.false_refusals == 1.0
    assert ev.best_of(rows, [ev.Thresholds(t, 0.6) for t in ev.SWEEP]) == ev.Thresholds(0.45, 0.6)
    assert ev.percentile([5, 1, 3, 2, 4], 0.95) == 5 and ev.percentile([5, 1, 3, 2, 4], 0.5) == 3


async def test_eval_runs_on_demo_data_and_keeps_nothing(db: AsyncSession) -> None:
    await load("seed_script", REPO / "seed" / "seed.py").seed(db)
    ev = load("run_eval", REPO / "eval" / "run_eval.py")
    chunks_before = await db.scalar(select(func.count()).select_from(CardChunk))
    settings = get_settings()
    providers = build_providers(settings)
    items = ev.load_dataset(ev.DATASET)
    assert len(items) >= 50 and sum(not i.answerable for i in items) >= 15
    assert 5 <= sum(i.tricky for i in items) <= 10

    rows, _ = await ev.run_questions(db, providers, settings, items[:5] + items[-3:])
    await db.rollback()
    assert await db.scalar(select(func.count()).select_from(CardChunk)) == chunks_before
    report = ev.render_report(rows, settings, providers, "fake", "answer@1")
    assert "## Метрики" in report and "`RAG_MIN_SIMILARITY`" in report and "## Провалы" in report
