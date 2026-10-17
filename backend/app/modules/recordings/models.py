import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPk, str_enum


class RecordingStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class RecordingStage(StrEnum):
    """What the worker is doing now; the page shows it instead of a job progress bar (D-060)."""

    AUDIO = "audio"
    SPEECH = "speech"
    STEPS = "steps"
    SCREENSHOTS = "screenshots"


class Recording(UUIDPk, Timestamps, Base):
    __tablename__ = "recordings"

    handover_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("handovers.id", ondelete="CASCADE"), index=True)
    process_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processes.id", ondelete="SET NULL"))
    video_asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[RecordingStatus] = mapped_column(
        str_enum(RecordingStatus, "recording_status"), default=RecordingStatus.UPLOADED
    )
    stage: Mapped[RecordingStage | None] = mapped_column(str_enum(RecordingStage, "recording_stage"))
    error: Mapped[str | None] = mapped_column(Text)  # shown to the expert
    duration_ms: Mapped[int | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class SegmentSource(StrEnum):
    RECORDING = "recording"
    INTERVIEW_AUDIO = "interview_audio"


class TranscriptSegment(UUIDPk, Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (Index("ix_transcript_segments_source", "source_type", "source_id"),)

    source_type: Mapped[SegmentSource] = mapped_column(str_enum(SegmentSource, "segment_source"))
    source_id: Mapped[uuid.UUID]
    start_ms: Mapped[int]
    end_ms: Mapped[int]
    text: Mapped[str] = mapped_column(Text)


class RecordingStep(UUIDPk, Base):
    __tablename__ = "recording_steps"
    __table_args__ = (UniqueConstraint("recording_id", "idx"),)

    recording_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"))
    idx: Mapped[int]  # from 1
    title: Mapped[str] = mapped_column(String(300))
    action: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    start_ms: Mapped[int]
    end_ms: Mapped[int]
    screenshot_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )
    screenshot_blurred: Mapped[bool] = mapped_column(default=False)
