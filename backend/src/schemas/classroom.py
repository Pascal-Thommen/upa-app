from pydantic import BaseModel, ConfigDict, Field


class ClassroomDueDate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "year": 2026,
                "month": 10,
                "day": 28,
            }
        }
    )

    year: int = Field(default=0, description="Anio de la fecha de entrega")
    month: int = Field(default=0, description="Mes de la fecha de entrega (1 a 12)")
    day: int = Field(default=0, description="Dia de la fecha de entrega (1 a 31)")


class ClassroomDueTime(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "hours": 23,
                "minutes": 59,
            }
        }
    )

    hours: int = Field(default=23, description="Hora de entrega en formato 24h (0 a 23)")
    minutes: int = Field(default=59, description="Minutos de entrega (0 a 59)")


class ClassroomDeadlineResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "654321098",
                "assignment_id": "654321098",
                "course_id": "123456789",
                "course": "Ingenieria de Software II",
                "course_name": "Ingenieria de Software II",
                "title": "Entrega de Arquitectura Backend REST",
                "description": "Documentacion OpenAPI y pruebas de integracion completas.",
                "due_date": {"year": 2026, "month": 10, "day": 28},
                "due_time": {"hours": 23, "minutes": 59},
                "due_date_formatted": "2026-10-28 23:59",
                "alternate_link": "https://classroom.google.com/c/123456789/a/654321098/details",
                "max_points": 100.0,
            }
        }
    )

    id: str = Field(..., description="Identificador unico de la tarea en Classroom")
    assignment_id: str = Field(..., description="Alias compatible del identificador de la tarea")
    course_id: str = Field(..., description="Identificador del curso en Google Classroom")
    course: str = Field(..., description="Nombre del curso academico")
    course_name: str = Field(..., description="Alias compatible del nombre del curso academico")
    title: str = Field(..., description="Titulo de la tarea o entrega")
    description: str = Field(default="", description="Descripcion detallada de la tarea (nunca nulo)")
    due_date: ClassroomDueDate = Field(
        default_factory=ClassroomDueDate,
        description="Objeto estructurado con la fecha limite",
    )
    due_time: ClassroomDueTime = Field(
        default_factory=ClassroomDueTime,
        description="Objeto estructurado con la hora limite",
    )
    due_date_formatted: str = Field(
        default="",
        description="Fecha y hora formateada en ISO corto YYYY-MM-DD HH:MM (cadena vacia si no aplica)",
    )
    alternate_link: str = Field(
        default="",
        description="Enlace directo a la tarea en Google Classroom",
    )
    max_points: float = Field(
        default=0.0,
        description="Puntaje maximo asignado a la tarea (0.0 si no tiene calificacion)",
    )


class ClassroomCourseResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "123456789",
                "name": "Ingenieria de Software II",
                "section": "Semestre 4",
                "alternate_link": "https://classroom.google.com/c/123456789",
                "room": "Aula 204",
            }
        }
    )

    id: str = Field(..., description="Identificador unico del curso en Google Classroom")
    name: str = Field(..., description="Nombre oficial de la asignatura")
    section: str = Field(default="", description="Seccion o semestre del curso (nunca nulo)")
    alternate_link: str = Field(default="", description="Enlace directo al curso en Google Classroom")
    room: str = Field(default="", description="Aula o sala asignada (nunca nulo)")
