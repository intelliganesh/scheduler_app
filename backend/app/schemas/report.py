from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReportCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    created_at: datetime
