from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AudienceGroupBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    badge_class: str | None = Field("bg-slate-100 text-slate-800 border-slate-200", max_length=100)
    google_group: str | None = Field(None, max_length=255)
    emails: list[str] = Field(default_factory=list)


class AudienceGroupCreate(AudienceGroupBase):
    id: str | None = Field(None, min_length=2, max_length=50)


class AudienceGroupUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    badge_class: str | None = Field(None, max_length=100)
    google_group: str | None = Field(None, max_length=255)
    emails: list[str] | None = None


class AudienceGroupResponse(AudienceGroupBase):
    id: str
    is_system: bool = False
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
