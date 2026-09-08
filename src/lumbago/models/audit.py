"""Append-only audit records for changes to Lumbago data."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, JsonValue, field_validator

from lumbago.models.base import LumbagoModel, normalize_to_utc, utc_now


class AuditAction(StrEnum):
    """An operation captured in Lumbago's audit history."""

    DELETE = "delete"


class AuditEvent(LumbagoModel):
    """An immutable description of an operation performed on a Lumbago record."""

    id: UUID = Field(
        default_factory=uuid4,
        description="Stable unique identifier for this audit event.",
    )
    occurred_at: AwareDatetime = Field(
        default_factory=utc_now,
        description="UTC timestamp recording when the operation occurred.",
    )
    action: AuditAction = Field(description="Operation performed on the record.")
    record_type: str = Field(
        min_length=1,
        max_length=200,
        description="Concrete Lumbago model type affected by the operation.",
    )
    record_id: UUID = Field(description="Stable identifier of the affected record.")
    actor: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description=(
            "Optional application-defined identifier for the person or process that "
            "performed the operation."
        ),
    )
    snapshot: dict[str, JsonValue] = Field(
        description="JSON-compatible snapshot of the record immediately before deletion."
    )

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        """Store the event timestamp in UTC."""

        return normalize_to_utc(value)
