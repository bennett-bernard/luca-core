"""Shared foundations for Lumbago's public data models."""

from datetime import UTC, datetime
from typing import Self
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(UTC)


def normalize_to_utc(value: datetime) -> datetime:
    """Return a timezone-aware datetime normalized to UTC."""

    return value.astimezone(UTC)


class LumbagoModel(BaseModel):
    """Base configuration shared by all Lumbago models."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class RecordModel(LumbagoModel):
    """A persistable Lumbago record with stable identity and audit timestamps."""

    id: UUID = Field(
        default_factory=uuid4,
        description=(
            "Stable unique identifier for this record. The value remains unchanged "
            "when the record is updated."
        ),
    )
    created_at: AwareDatetime = Field(
        default_factory=utc_now,
        description=(
            "Timezone-aware timestamp recording when this record was first created."
        ),
    )
    updated_at: AwareDatetime = Field(
        default_factory=utc_now,
        description=(
            "Timezone-aware timestamp recording the most recent change to this record."
        ),
    )
    metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
        description=(
            "Caller-defined JSON-compatible attributes that extend the record without "
            "changing Lumbago's core schema."
        ),
    )

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_audit_timestamps(cls, value: datetime) -> datetime:
        """Store every supplied audit timestamp in UTC."""

        return normalize_to_utc(value)

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> Self:
        """Ensure modification time never predates creation time."""

        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be on or after created_at")
        return self
