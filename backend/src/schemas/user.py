from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

REDUNDANT_GROUP_TAGS = {"ALL", "TIE"}


def sanitize_user_groups(groups: list[Any] | None) -> list[str]:
    """
    Limpia la lista de grupos de un usuario eliminando valores vacios, duplicados
    y las pseudo-etiquetas redundantes ALL y TIE aislado.
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for g in groups or []:
        if g is None:
            continue
        val = str(g).strip()
        if not val or val.upper() in REDUNDANT_GROUP_TAGS:
            continue
        if val not in seen:
            seen.add(val)
            cleaned.append(val)
    return cleaned


class GoogleGroupDetail(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "01abc234def",
                "name": "Estudiantes TIE 2025",
                "email": "estudiantes.tie@upa.edu.py",
                "description": "Grupo institucional de Ingenieria Empresarial",
            }
        }
    )

    id: str = Field(default="", description="ID del grupo en Google Workspace (nunca nulo)")
    name: str = Field(default="", description="Nombre del grupo institucional (nunca nulo)")
    email: str = Field(default="", description="Correo de la lista de distribucion (nunca nulo)")
    description: str = Field(default="", description="Descripcion del grupo (nunca nulo)")


class UserResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "email": "pascal.thommen@upa.edu.py",
                "full_name": "Pascal Thommen",
                "role": "admin",
                "groups": ["Semester_4", "Estudiantes TIE 2025"],
                "google_groups": [
                    {
                        "id": "01abc234def",
                        "name": "Estudiantes TIE 2025",
                        "email": "estudiantes.tie@upa.edu.py",
                        "description": "Grupo institucional de Ingenieria Empresarial",
                    }
                ],
                "has_classroom_token": False,
            }
        }
    )

    id: int = Field(..., description="Identificador unico del usuario en la base de datos")
    email: str = Field(..., description="Correo institucional @upa.edu.py")
    full_name: str = Field(..., description="Nombre completo del usuario (nunca nulo)")
    role: str = Field(..., description="Rol de autorizacion en el sistema: user o admin")
    groups: list[str] = Field(
        default_factory=list,
        description="Etiquetas de grupos visibles segun politica estricta de privacidad",
    )
    google_groups: list[GoogleGroupDetail] = Field(
        default_factory=list,
        description="Detalle de grupos de Google Workspace (exclusivo para administracion)",
    )
    has_classroom_token: bool = Field(
        default=False,
        description="Indica si el usuario tiene un token de Google Classroom registrado",
    )
    permissions: list[str] = Field(
        default_factory=list,
        description="Modulos del portal habilitados: publicaciones, grupos, roles, apis",
    )

    @model_validator(mode="after")
    def _enforce_privacy_and_clean_groups(self) -> "UserResponse":
        if (self.role or "").strip().lower() != "admin":
            self.groups = []
            self.google_groups = []
        else:
            self.groups = sanitize_user_groups(self.groups)
        return self
