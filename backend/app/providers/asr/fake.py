"""FakeASR (SPEC, 5.3): returns the transcript from `<audio name>.transcript.json` next to the audio file."""

import json
from dataclasses import dataclass
from pathlib import Path

from app.providers.asr.base import Transcript


def transcript_path(audio_path: Path) -> Path:
    return audio_path.with_suffix(".transcript.json")


@dataclass
class FakeASR:
    name: str = "fake"

    def transcribe(self, audio_path: Path, language: str = "ru") -> Transcript:
        path = transcript_path(audio_path)
        if not path.is_file():
            raise FileNotFoundError(f"FakeASR: нет файла транскрипта {path.name}")
        return Transcript.from_dict(json.loads(path.read_text(encoding="utf-8")))

    async def health(self) -> bool:
        return True
