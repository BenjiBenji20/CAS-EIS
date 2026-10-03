from datetime import datetime, timezone
from pydantic import BaseModel, Field


class SchemaResponseDetails(BaseModel):
    status: bool = Field(
        False,
        description="Response details"
    )
    description: str | None = Field(
        None,
        description="Response description.",
        min_length=1,
        max_length=255
    )
    date_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Response date time creation."
    )
    count: int | None = Field(
        None,
        description="Response count."
    )
    