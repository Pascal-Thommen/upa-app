from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserRoleCreate(BaseModel):
    """Alta o actualizacion de una cuenta autorizada por matriz de permisos."""

    email: str = Field(..., min_length=5, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, pattern="^(admin|editor)$")
    permissions: list[str] | None = Field(default=None)


class UserRoleUpdate(BaseModel):
    """Edicion de permisos de una cuenta existente (el correo viene en la ruta)."""

    name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, pattern="^(admin|editor)$")
    permissions: list[str] | None = Field(default=None)


class UserRoleResponse(BaseModel):
    id: int
    email: str
    name: str | None = None
    role: str = "editor"
    permissions: list[str] = Field(default_factory=list)
    is_primary: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
