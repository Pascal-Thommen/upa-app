import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_email_list(values: list[str]) -> list[str]:
    """Normaliza (minusculas, sin espacios) y elimina duplicados conservando el orden."""
    seen: dict[str, None] = {}
    for raw in values:
        email = str(raw).strip().lower()
        if email:
            seen.setdefault(email, None)
    return list(seen)


class AudienceGroupBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    google_groups: list[str] = Field(default_factory=list, description="Correos de grupos de Google Workspace")
    emails: list[str] = Field(default_factory=list, description="Direcciones de correo agregadas manualmente")

    @field_validator("google_groups", "emails")
    @classmethod
    def _validate_emails(cls, values: list[str]) -> list[str]:
        cleaned = clean_email_list(values)
        invalid = [e for e in cleaned if not EMAIL_PATTERN.match(e)]
        if invalid:
            raise ValueError("Direcciones de correo no validas: " + ", ".join(invalid))
        return cleaned


class AudienceGroupCreate(AudienceGroupBase):
    id: str | None = Field(None, min_length=2, max_length=50)


class AudienceGroupUpdate(BaseModel):
    """Edicion completa desde la mascara de grupos (el identificador y el origen no cambian)."""

    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    google_groups: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)

    @field_validator("google_groups", "emails")
    @classmethod
    def _validate_emails(cls, values: list[str]) -> list[str]:
        cleaned = clean_email_list(values)
        invalid = [e for e in cleaned if not EMAIL_PATTERN.match(e)]
        if invalid:
            raise ValueError("Direcciones de correo no validas: " + ", ".join(invalid))
        return cleaned


class AudienceGroupResponse(BaseModel):
    """Respuesta de lectura: sin validacion estricta para no fallar con datos historicos."""

    id: str
    name: str
    description: str | None = None
    google_groups: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("google_groups", "emails", mode="before")
    @classmethod
    def _none_to_empty(cls, value):
        return value or []


class WorkspaceGroupItem(BaseModel):
    id: str = ""
    name: str = ""
    email: str
    description: str = ""


class WorkspaceGroupsResponse(BaseModel):
    source: str = Field(..., description="directory (Google Directory API) o known_users (grupos de usuarios ya conectados)")
    message: str = Field(default="", description="Aviso legible cuando se usa la lista alternativa")
    groups: list[WorkspaceGroupItem] = Field(default_factory=list)
