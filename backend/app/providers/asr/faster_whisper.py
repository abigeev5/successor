"""Speech recognition with faster-whisper (model `small` by default).

The model is loaded lazily on the first call, so the app starts without it. Weights are
downloaded by faster-whisper on first use; in a closed contour set ASR_MODEL to a local directory.
Decoding uses PyAV inside faster-whisper, so webm/opus from the browser works without ffmpeg.
"""

import threading
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.providers.asr.base import Segment, Transcript, Word


class FasterWhisperASR:
    name = "faster_whisper"

    def __init__(self, settings: Settings) -> None:
        self.model = settings.asr_model
        self._device = settings.asr_device
        self._compute_type = settings.asr_compute_type
        self._download_root = settings.asr_download_root or None
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self.model,
                    device=self._device,
                    compute_type=self._compute_type,
                    download_root=self._download_root,
                )
        return self._model

    def transcribe(self, audio_path: Path, language: str = "ru") -> Transcript:
        segments, info = self._load().transcribe(
            str(audio_path), language=language, word_timestamps=True, vad_filter=True
        )
        result = [
            Segment(
                start_ms=round(s.start * 1000),
                end_ms=round(s.end * 1000),
                text=s.text.strip(),
                words=[
                    Word(round(w.start * 1000), round(w.end * 1000), w.word.strip()) for w in (s.words or [])
                ],
            )
            for s in segments  # a generator: recognition happens while iterating
        ]
        return Transcript(segments=result, duration_ms=round(info.duration * 1000))

    async def health(self) -> bool:
        # Loading the model here would download weights; report whether the library is usable.
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True
