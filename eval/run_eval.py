"""`make eval` (SPEC 11.2): runs the assistant over eval/datasets/demo_qa.jsonl and writes a report.

Nothing is stored: the demo handover's approved cards are re-indexed with the chosen embeddings
inside a transaction that is rolled back, so the index always matches the query embeddings.

The pipeline runs once with the lowest thresholds of the sweeps; refusals for higher thresholds
are derived from the recorded best cosine and text coverage (the same rule as in the app).

Run from backend/ (the `app` package must be importable):
    uv run python ../eval/run_eval.py --provider fake|real [--out DIR] [--limit N]
"""

import argparse
import asyncio
import json
import math
import re
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.core.prompts import get_prompts
from app.modules.assistant.domain.refusal import refuse_before_llm
from app.modules.assistant.models import AnswerStatus
from app.modules.assistant.pipeline import answer_question
from app.modules.handovers.models import Handover
from app.modules.knowledge.models import CardStatus, KnowledgeCard
from app.modules.org.models import OrgUnit
from app.modules.search.indexer import index_card
from app.providers.llm.base import LLMError, Message
from app.providers.registry import Providers, build_providers
from app.wiring import import_models

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "datasets" / "demo_qa.jsonl"
REPORTS = ROOT / "reports"
DEMO = ROOT.parent / "seed" / "data" / "demo.json"
SWEEP = [round(0.30 + 0.05 * i, 2) for i in range(9)]  # RAG_MIN_SIMILARITY 0.30 … 0.70 (SPEC 11.2)
COVERAGE_SWEEP = [round(0.3 + 0.1 * i, 1) for i in range(6)]  # RAG_MIN_TEXT_COVERAGE 0.3 … 0.8
JUDGE_PROMPT = "eval_correctness"


class Correctness(BaseModel):
    correct: bool
    reason: str = ""


@dataclass(frozen=True)
class Item:
    id: str
    question: str
    answerable: bool
    tricky: bool
    expected_answer: str | None
    expected_card_titles: list[str]


@dataclass
class Row:
    item: Item
    status: str
    refusal_reason: str | None
    answer: str | None
    cited_titles: list[str]
    groundedness: float | None
    verification: str
    best_cosine: float | None
    fts_hits: int
    text_coverage: float
    latency_ms: int
    correct: bool | None = None  # None: not judged (refused, or no judge)
    judge_reason: str = ""

    def refused_at(self, t: "Thresholds") -> bool:
        """Valid for thresholds not below the ones the pipeline ran with."""
        return self.status == AnswerStatus.REFUSED.value or refuse_before_llm(
            self.best_cosine, self.text_coverage, t.similarity, t.coverage
        )

    def recall(self) -> float:
        expected = set(self.item.expected_card_titles)
        return len(expected & set(self.cited_titles)) / len(expected) if expected else 1.0


@dataclass(frozen=True)
class Thresholds:
    similarity: float
    coverage: float


@dataclass
class Metrics:
    thresholds: Thresholds
    correctness: float | None
    citation_recall: float | None
    correct_refusals: float | None
    false_refusals: float | None
    groundedness: float | None
    answered: int
    refused: int
    judged: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def load_dataset(path: Path) -> list[Item]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            raw = json.loads(line)
            items.append(
                Item(
                    id=raw["id"],
                    question=raw["question"],
                    answerable=raw["answerable"],
                    tricky=raw.get("tricky", False),
                    expected_answer=raw.get("expected_answer"),
                    expected_card_titles=raw.get("expected_card_titles", []),
                )
            )
    return items


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def compute(rows: list[Row], threshold: Thresholds) -> Metrics:
    answerable = [r for r in rows if r.item.answerable]
    unanswerable = [r for r in rows if not r.item.answerable]
    answered = [r for r in rows if not r.refused_at(threshold)]
    answered_ok = [r for r in answerable if not r.refused_at(threshold)]
    judged = [r for r in answerable if r.correct is not None]
    correctness = None
    if judged:  # refused answerable questions count as wrong answers
        correctness = sum(1 for r in answered_ok if r.correct) / len(answerable)
    return Metrics(
        thresholds=threshold,
        correctness=correctness,
        citation_recall=_mean([r.recall() for r in answered_ok]),
        correct_refusals=_mean([float(r.refused_at(threshold)) for r in unanswerable]),
        false_refusals=_mean([float(r.refused_at(threshold)) for r in answerable]),
        groundedness=_mean([r.groundedness for r in answered if r.groundedness is not None]),
        answered=len(answered),
        refused=len(rows) - len(answered),
        judged=len(judged),
    )


def percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)  # nearest-rank
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def balance(m: Metrics) -> float:
    return (m.correct_refusals or 0) - (m.false_refusals or 0)


def best_of(rows: list[Row], candidates: list[Thresholds]) -> Thresholds:
    """The best «correct refusals − false refusals»; ties go to the first (lowest) candidate."""
    best = candidates[0]
    for t in candidates[1:]:
        if balance(compute(rows, t)) > balance(compute(rows, best)):
            best = t
    return best


async def demo_handover(db: AsyncSession) -> uuid.UUID:
    unit_name = json.loads(DEMO.read_text(encoding="utf-8"))["org_unit"]
    handover_id = await db.scalar(
        select(Handover.id)
        .join(OrgUnit, OrgUnit.id == Handover.org_unit_id)
        .where(OrgUnit.name == unit_name)
        .order_by(Handover.created_at.desc())
        .limit(1)
    )
    if handover_id is None:
        raise SystemExit("Демо-передача не найдена: сначала выполните `make seed-demo`")
    return handover_id


async def judge(providers: Providers, item: Item, answer: str) -> tuple[bool | None, str]:
    prompt = get_prompts().render(
        JUDGE_PROMPT, question=item.question, expected=item.expected_answer or "", answer=answer
    )
    try:
        verdict = await providers.judge_llm.complete_json([Message("user", prompt.text)], Correctness)
    except LLMError as exc:
        return None, f"судья недоступен: {exc}"
    return verdict.correct, verdict.reason


async def run_questions(
    db: AsyncSession, providers: Providers, settings: Settings, items: list[Item]
) -> tuple[list[Row], uuid.UUID]:
    handover_id = await demo_handover(db)
    cards = list(
        (
            await db.execute(
                select(KnowledgeCard).where(
                    KnowledgeCard.handover_id == handover_id, KnowledgeCard.status == CardStatus.APPROVED
                )
            )
        ).scalars()
    )
    titles = {c.id: c.title for c in cards}
    unknown = {t for item in items for t in item.expected_card_titles} - set(titles.values())
    if unknown:
        raise SystemExit(f"В наборе есть карточки, которых нет среди подтверждённых: {sorted(unknown)}")
    for card in cards:
        await index_card(db, providers, card.id)

    rows: list[Row] = []
    for n, item in enumerate(items, start=1):
        result = await answer_question(db, providers, settings, handover_id, item.question)
        row = Row(
            item=item,
            status=result.status.value,
            refusal_reason=result.refusal_reason,
            answer=result.answer,
            cited_titles=[titles.get(s.card_id, s.title) for s in result.sources],
            groundedness=result.groundedness,
            verification=result.verification,
            best_cosine=result.search.best_cosine,
            fts_hits=result.search.fts_hits,
            text_coverage=result.search.text_coverage,
            latency_ms=result.latency_ms,
        )
        if item.answerable and result.answer:
            row.correct, row.judge_reason = await judge(providers, item, result.answer)
        rows.append(row)
        print(
            f"[{n}/{len(items)}] {item.id} {row.status} cos={_num(row.best_cosine)} "
            f"coverage={row.text_coverage:.2f}",
            flush=True,
        )
    return rows, handover_id


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f} %"


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _mark(value: float | None, target: float, higher: bool = True) -> str:
    if value is None:
        return "—"
    return "✅" if (value >= target if higher else value <= target) else "❌"


def failures(rows: list[Row], threshold: Thresholds) -> list[tuple[Row, str]]:
    found: list[tuple[Row, str]] = []
    for r in rows:
        refused = r.refused_at(threshold)
        if r.item.answerable and refused:
            found.append((r, "ложный отказ"))
        elif r.item.answerable and r.correct is False:
            found.append((r, f"неправильный ответ: {r.judge_reason}"))
        elif r.item.answerable and r.recall() < 1:
            found.append((r, "процитированы не все ожидаемые карточки"))
        elif not r.item.answerable and not refused:
            found.append((r, "ответ вместо отказа"))
    return found


def sweep_table(
    name: str,
    candidates: list[Thresholds],
    rows: list[Row],
    configured: Thresholds,
    label: Callable[[Thresholds], str],
) -> list[str]:
    best = best_of(rows, candidates)
    lines = [
        f"### `{name}`",
        "",
        "| Порог | Корректные отказы | Ложные отказы | Правильность |",
        "|---|---|---|---|",
    ]
    for t in candidates:
        s = compute(rows, t)
        current = " (текущий)" if t == configured else ""
        flag = " ← лучший баланс" if t == best else ""
        lines.append(
            f"| {label(t)}{current} | {_pct(s.correct_refusals)} | {_pct(s.false_refusals)} "
            f"| {_pct(s.correctness)}{flag} |"
        )
    return [*lines, ""]


def render_report(
    rows: list[Row], settings: Settings, providers: Providers, provider_mode: str, versions: str
) -> str:
    configured = Thresholds(settings.rag_min_similarity, settings.rag_min_text_coverage)
    m = compute(rows, configured)
    latencies = [r.latency_ms for r in rows]
    p50, p95 = percentile(latencies, 0.5), percentile(latencies, 0.95)
    lines = [
        f"# Eval ассистента — {date.today().isoformat()}",
        "",
        f"- Режим: `--provider {provider_mode}`; LLM: `{providers.llm.model}`; "
        f"судья: `{providers.judge_llm.model}`; эмбеддинги: `{providers.embeddings.model}`",
        f"- Промпты: `{versions}`",
        f"- Вопросов: {len(rows)} (отвечаемых {sum(r.item.answerable for r in rows)}, "
        f"неотвечаемых {sum(not r.item.answerable for r in rows)}, "
        f"с подвохом {sum(r.item.tricky for r in rows)})",
        f"- Пороги: `RAG_MIN_SIMILARITY` = {configured.similarity:.2f}, "
        f"`RAG_MIN_TEXT_COVERAGE` = {configured.coverage:.1f}; top-k = {settings.rag_top_k}, "
        f"чанков = {settings.rag_top_chunks}, карточек = {settings.rag_max_cards}",
        "",
    ]
    if provider_mode == "fake":
        lines += [
            "> Режим fake: модели нет, ассистент показывает найденные карточки без пересказа, правильность "
            "не оценивается. Эмбеддинги хеширующие, поэтому цифры поиска и отказов не говорят о качестве — "
            "прогон только проверяет, что пайплайн не сломан.",
            "",
        ]
    lines += [
        "## Метрики",
        "",
        "| Метрика | Значение | Ориентир | |",
        "|---|---|---|---|",
        f"| Правильность ответа (судья, на отвечаемых) | {_pct(m.correctness)} | ≥ 80 % "
        f"| {_mark(m.correctness, 0.8)} |",
        f"| Полнота цитирования (на отвеченных отвечаемых) | {_pct(m.citation_recall)} | ≥ 80 % "
        f"| {_mark(m.citation_recall, 0.8)} |",
        f"| Корректный отказ (на неотвечаемых) | {_pct(m.correct_refusals)} | ≥ 90 % "
        f"| {_mark(m.correct_refusals, 0.9)} |",
        f"| Ложные отказы (на отвечаемых) | {_pct(m.false_refusals)} | ≤ 10 % "
        f"| {_mark(m.false_refusals, 0.1, higher=False)} |",
        f"| Обоснованность (средняя groundedness) | {_num(m.groundedness)} | ≥ 0.95 "
        f"| {_mark(m.groundedness, 0.95)} |",
        f"| Задержка p50 / p95 | {p50} / {p95} мс | p95 ≤ 15 000 | {_mark(p95, 15000, higher=False)} |",
        "",
        "## Подбор порогов отказа",
        "",
        "Отказ без LLM — когда и косинус, и покрытие словами вопроса ниже порогов. Лучший баланс — максимум "
        "«корректные отказы − ложные отказы» (при равенстве — меньший порог).",
        "",
    ]
    similarity = [Thresholds(t, configured.coverage) for t in SWEEP]
    coverage = [Thresholds(configured.similarity, c) for c in COVERAGE_SWEEP]
    lines += sweep_table("RAG_MIN_SIMILARITY", similarity, rows, configured, lambda t: f"{t.similarity:.2f}")
    lines += sweep_table("RAG_MIN_TEXT_COVERAGE", coverage, rows, configured, lambda t: f"{t.coverage:.1f}")
    lines += [
        "## Провалы",
        "",
    ]
    found = failures(rows, configured)
    if not found:
        lines.append("Нет.")
    for r, why in found:
        gated = r.status != AnswerStatus.REFUSED.value and r.refused_at(configured)
        status = "refused (no_relevant_sources)" if gated else r.status
        if r.refusal_reason and not gated:
            status += f" ({r.refusal_reason})"
        expected = r.item.expected_answer or "отказ"
        if r.item.expected_card_titles:
            expected += f" (карточки: {', '.join(r.item.expected_card_titles)})"
        answer = "—" if gated else (r.answer or "—")
        lines += [
            f"### {r.item.id}: {r.item.question}",
            f"- Проблема: {why}",
            f"- Ожидалось: {expected}",
            f"- Статус: {status}; cos = {_num(r.best_cosine)}, покрытие словами = {r.text_coverage:.2f}",
            f"- Источники: {'—' if gated else ', '.join(r.cited_titles) or '—'}",
            "- Ответ:",
            "",
            "  " + answer.replace("\n", "\n  "),
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


async def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="Оценка качества ассистента на демо-наборе (ТЗ 11.2)")
    parser.add_argument("--provider", choices=["fake", "real"], default="real", help="fake — без модели (CI)")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--out", type=Path, default=REPORTS, help="папка для отчёта")
    parser.add_argument("--limit", type=int, default=0, help="только первые N вопросов")
    args = parser.parse_args(argv)

    import_models()
    settings = get_settings()
    if args.provider == "fake":
        settings = settings.model_copy(update={"llm_provider": "fake", "embeddings_provider": "fake"})
    providers = build_providers(settings)
    run_settings = settings.model_copy(
        update={
            "rag_min_similarity": min(SWEEP[0], settings.rag_min_similarity),
            "rag_min_text_coverage": min(COVERAGE_SWEEP[0], settings.rag_min_text_coverage),
        }
    )
    items = load_dataset(args.dataset)[: args.limit or None]

    async with get_sessionmaker()() as db:
        try:
            rows, _ = await run_questions(db, providers, run_settings, items)
        finally:
            await db.rollback()  # the temporary index is not kept
    await dispose_engine()

    prompts = get_prompts()
    versions = "+".join(f"{n}@{prompts.version(n)}" for n in ("answer", "verify_claims", JUDGE_PROMPT))
    report = render_report(rows, settings, providers, args.provider, versions)
    model = re.sub(r"[^\w.-]+", "-", providers.llm.model or args.provider).strip("-") or args.provider
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{date.today().isoformat()}_{model}.md"
    path.write_text(report, encoding="utf-8")
    m = compute(rows, Thresholds(settings.rag_min_similarity, settings.rag_min_text_coverage))
    print(
        f"Отчёт: {path}\nкорректные отказы {_pct(m.correct_refusals)}, "
        f"ложные отказы {_pct(m.false_refusals)}, правильность {_pct(m.correctness)}, "
        f"полнота цитирования {_pct(m.citation_recall)}"
    )
    return path


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
