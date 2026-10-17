import pytest

from app.providers.llm.structured import extract_json


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('Вот ответ: {"a": {"b": 2}} — готово', '{"a": {"b": 2}}'),
        ("[1, 2]", "[1, 2]"),
        ("нет json", "нет json"),
    ],
)
def test_extract_json(raw: str, expected: str) -> None:
    assert extract_json(raw) == expected
