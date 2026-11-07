"""Steps of a recording from the LLM, fixed by code (inside the duration, ordered, no overlaps)."""

from dataclasses import dataclass, replace

MIN_STEP_MS = 1000
FRAME_BEFORE_END_MS = 500  # the screenshot is taken just before the step ends


@dataclass(frozen=True)
class StepDraft:
    title: str
    action: str
    rationale: str | None
    start_ms: int
    end_ms: int


def fix_steps(steps: list[StepDraft], duration_ms: int) -> list[StepDraft]:
    """Clamp to the recording, sort, cut overlaps; drop steps that become too short or have no title."""
    clamped = []
    for s in steps:
        start, end = max(0, s.start_ms), min(duration_ms, s.end_ms)
        title = s.title.strip()
        if title and end - start >= MIN_STEP_MS:
            rationale = (s.rationale or "").strip() or None
            clamped.append(
                replace(
                    s, title=title, action=s.action.strip(), rationale=rationale, start_ms=start, end_ms=end
                )
            )
    clamped.sort(key=lambda s: (s.start_ms, s.end_ms))
    fixed: list[StepDraft] = []
    for s in clamped:
        if fixed and s.start_ms < fixed[-1].end_ms:
            s = replace(s, start_ms=fixed[-1].end_ms)
        if s.end_ms - s.start_ms >= MIN_STEP_MS:
            fixed.append(s)
    return fixed


def frame_at(step: StepDraft) -> int:
    return max(step.start_ms, step.end_ms - FRAME_BEFORE_END_MS)


def timecode(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def procedure_markdown(steps: list[StepDraft], screenshot_urls: list[str | None]) -> str:
    """Card body: numbered steps with the reason and a screenshot."""
    items = []
    for n, (step, url) in enumerate(zip(steps, screenshot_urls, strict=True), start=1):
        action = f" {step.action}" if step.action and step.action != step.title else ""
        parts = [f"{n}. **{step.title.rstrip('.')}.**{action}"]
        if step.rationale:
            parts.append(f"   _Почему так:_ {step.rationale}")
        if url:
            parts.append(f"   ![Шаг {n}]({url})")
        items.append("\n\n".join(parts))  # separate paragraphs inside the list item
    return "\n\n".join(items)
