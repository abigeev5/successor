import json
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.modules.recordings.blur import blur_regions
from app.modules.recordings.domain.pii import PiiKind, find_pii, group_lines, luhn_ok
from app.modules.recordings.domain.steps import StepDraft, fix_steps, frame_at, procedure_markdown, timecode
from app.modules.recordings.ner import find_persons
from app.providers.ocr.base import OcrBox
from app.providers.ocr.fake import FakeOCR
from app.providers.ocr.tesseract import TesseractOCR, parse_tsv

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pii" / "student_card.png"


def words(*lines: str) -> list[OcrBox]:
    """One OCR box per word, 20 px per line, 10 px per character."""
    boxes = []
    for n, line in enumerate(lines):
        x = 0
        for word in line.split():
            boxes.append(OcrBox(word, x, n * 20, len(word) * 10, 16, line=str(n)))
            x += (len(word) + 1) * 10
    return boxes


def kinds(boxes: list[OcrBox]) -> dict[PiiKind, str]:
    return {h.kind: h.text for h in find_pii(boxes)}


def test_regex_detectors() -> None:
    found = kinds(
        words(
            "Телефон: +7 (912) 345-67-89, рабочий 8 495 123 45 67",
            "Почта anna.smirnova@student.demo",
            "СНИЛС 112-233-445 95",
            "Карта 4276 3800 1234 5679",
            "Паспорт 45 08 123456",
        )
    )
    assert found[PiiKind.PHONE] in ("+7 (912) 345-67-89", "8 495 123 45 67")
    assert found[PiiKind.EMAIL] == "anna.smirnova@student.demo"
    assert found[PiiKind.SNILS] == "112-233-445 95"
    assert found[PiiKind.CARD] == "4276 3800 1234 5679"
    assert found[PiiKind.PASSPORT] == "45 08 123456"


def test_card_needs_luhn_and_ordinary_numbers_are_kept() -> None:
    assert luhn_ok("4276380012345679") and not luhn_ok("4276380012345676")
    assert PiiKind.CARD not in kinds(words("Заказ 4276 3800 1234 5676"))
    assert kinds(words("Группа ЭК-21, 17.10.2026, аудитория 305, попытка 2")) == {}


def test_hits_point_at_the_words_that_hold_them() -> None:
    boxes = words("Телефон: +7 (912) 345-67-89 Группа ЭК-21")
    [hit] = find_pii(boxes)
    assert [boxes[i].text for i in hit.boxes] == ["+7", "(912)", "345-67-89"]


def test_lines_by_geometry_when_ocr_gives_no_line_keys() -> None:
    boxes = [OcrBox("б", 50, 2, 10, 16), OcrBox("в", 0, 40, 10, 16), OcrBox("а", 0, 0, 10, 16)]
    assert [[boxes[i].text for i in line] for line in group_lines(boxes)] == [["а", "б"], ["в"]]


def test_ocr_noise_does_not_hide_emails_and_names() -> None:
    found = kinds(
        words("Towra anna.smimova@student demo", "‘Смирнова Анна Павловна. эк обучается", "Петров А. В.")
    )
    assert found[PiiKind.EMAIL] == "anna.smimova@student"
    lines = words("‘Смирнова Анна Павловна. эк", "Преподаватель Петров А. В.", "сотрудник: Ирина Сергеевна")
    assert {h.text for h in find_pii(lines)} == {"Смирнова Анна Павловна", "Петров А. В.", "Ирина Сергеевна"}


def test_person_finder_runs_per_line() -> None:
    seen: list[str] = []
    find_pii(words("Группа ЭК-21", "Студент Смирнова"), lambda text: seen.append(text) or [])
    assert seen == ["Группа ЭК-21", "Студент Смирнова"]


def test_person_names_go_through_the_finder() -> None:
    boxes = words("Студент: Смирнова Анна", "Группа ЭК-21")

    def finder(text: str) -> list[tuple[int, int]]:
        return [(text.index("Смирнова"), text.index("Анна") + 4)] if "Смирнова" in text else []

    [hit] = find_pii(boxes, finder)
    assert hit.kind is PiiKind.PERSON and len(hit.boxes) == 2


def test_fixture_frame_phone_email_and_name_are_blurred(tmp_path: Path) -> None:
    """A frame with a phone, an email and a full name gets blurred."""
    frame = tmp_path / "frame.png"
    shutil.copy(FIXTURE, frame)
    shutil.copy(FIXTURE.with_suffix(".ocr.json"), frame.with_suffix(".ocr.json"))
    boxes = FakeOCR().read(frame)
    hits = find_pii(boxes, find_persons)
    assert {h.kind for h in hits} == {PiiKind.PHONE, PiiKind.EMAIL, PiiKind.PERSON}
    hidden = {i for h in hits for i in h.boxes}
    assert {boxes[i].text for i in hidden} >= {"Смирнова", "Анна", "Павловна", "anna.smirnova@student.demo"}

    before = cv2.imread(str(frame))
    blur_regions(frame, [(boxes[i].x, boxes[i].y, boxes[i].width, boxes[i].height) for i in hidden])
    after = cv2.imread(str(frame))
    for i, box in enumerate(boxes):
        region = (slice(box.y, box.y + box.height), slice(box.x, box.x + box.width))
        changed = np.abs(before[region].astype(int) - after[region].astype(int)).mean()
        if i in hidden:
            assert changed > 10, box.text
        elif box.line == "4":  # «Группа …» is far from personal data and stays as is
            assert changed == 0, box.text


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract не установлен")
def test_tesseract_reads_the_fixture() -> None:
    boxes = TesseractOCR().read(FIXTURE)
    found = {h.kind for h in find_pii(boxes)}
    assert {PiiKind.PHONE, PiiKind.EMAIL} <= found


def test_parse_tesseract_tsv() -> None:
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    rows = ["4\t1\t1\t1\t1\t0\t10\t10\t200\t20\t-1\t", "5\t1\t1\t1\t1\t1\t10\t10\t60\t20\t96.5\tТелефон:"]
    [box] = parse_tsv("\n".join([header, *rows]))
    assert (box.text, box.x, box.line, box.confidence) == ("Телефон:", 10, "1.1.1.1", 0.965)


def step(title: str, start: int, end: int) -> StepDraft:
    return StepDraft(title, f"{title} подробно", None, start, end)


def test_fix_steps_clamps_sorts_and_cuts_overlaps() -> None:
    fixed = fix_steps(
        [
            step("Второй", 9_000, 20_000),
            step("Первый", -500, 10_000),
            step("  ", 21_000, 25_000),
            step("За концом", 59_500, 70_000),
        ],
        duration_ms=60_000,
    )
    assert [(s.title, s.start_ms, s.end_ms) for s in fixed] == [
        ("Первый", 0, 10_000),
        ("Второй", 10_000, 20_000),
    ]


def test_frame_time_and_markdown() -> None:
    s = StepDraft("Открыть карточку студента", "Нажать «Найти»", "так быстрее", 1_000, 5_000)
    assert frame_at(s) == 4_500 and frame_at(step("Короткий", 1_000, 1_200)) == 1_000
    assert timecode(75_000) == "01:15"
    assert procedure_markdown([s], ["/api/assets/a1"]) == (
        "1. **Открыть карточку студента.** Нажать «Найти»\n\n"
        "   _Почему так:_ так быстрее\n\n"
        "   ![Шаг 1](/api/assets/a1)"
    )


def test_fixture_boxes_are_valid_json() -> None:
    assert len(json.loads(FIXTURE.with_suffix(".ocr.json").read_text(encoding="utf-8"))) > 10
