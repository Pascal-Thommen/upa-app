from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserRoleBase(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    name: str | None = None
    role: str = Field("editor", pattern="^(admin|editor)$")
    permissions: list[str] = Field(default_factory=list)


class UserRoleCreate(UserRoleBase):
    pass


class UserRoleResponse(UserRoleBase):
    id: int
    is_primary: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
