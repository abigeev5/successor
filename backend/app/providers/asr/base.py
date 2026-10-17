from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Word:
    start_ms: int
    end_ms: int
    word: str


@dataclass(frozen=True)
class Segment:
    start_ms: int
    end_ms: int
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass(frozen=True)
class Transcript:
    segments: list[Segment]

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.text.strip())

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Transcript":
        return cls(
            segments=[
                Segment(
                    start_ms=int(s["start_ms"]),
                    end_ms=int(s["end_ms"]),
                    text=s["text"],
                    words=[Word(int(w["start_ms"]), int(w["end_ms"]), w["word"]) for w in s.get("words", [])],
                )
                for s in raw["segments"]
            ]
        )


class ASRProvider(Protocol):
    name: str

    def transcribe(self, audio_path: Path, language: str = "ru") -> Transcript: ...

    async def health(self) -> bool: ...
