"""ffmpeg / ffprobe calls (blocking: run them in a thread)."""

import subprocess
import wave
from pathlib import Path

TIMEOUT_S = 30 * 60


class MediaError(RuntimeError):
    """The message is shown to the expert."""


def _run(args: list[str], error: str) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    except FileNotFoundError as exc:
        raise MediaError("На сервере не установлен ffmpeg") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"{error}: ffmpeg работал слишком долго") from exc
    if result.returncode != 0:
        raise MediaError(error)
    return result.stdout


def has_audio(video: Path) -> bool:
    out = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(video),
        ],
        "Не удалось прочитать видео — возможно, файл повреждён",
    )
    return bool(out.strip())


def extract_audio(video: Path, wav: Path) -> int:
    """16 kHz mono WAV for ASR (SPEC 7.6); returns its duration in ms.

    The duration comes from the WAV: browser webm files often have no duration in the header.
    """
    _run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            str(wav),
        ],
        "Не удалось извлечь звук из записи",
    )
    with wave.open(str(wav), "rb") as f:
        return f.getnframes() * 1000 // f.getframerate()


def grab_frame(video: Path, at_ms: int, png: Path) -> None:
    _run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{at_ms / 1000:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(png),
        ],
        "Не удалось сохранить кадр записи",
    )
    if not png.is_file():  # past the last frame ffmpeg exits with 0 and writes nothing
        raise MediaError("Не удалось сохранить кадр записи")
