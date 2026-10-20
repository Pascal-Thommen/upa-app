from typing import Any

import httpx
from fastapi import APIRouter, Depends, Response

from ..auth import get_current_user
from ..models import User

router = APIRouter(prefix="/api/classroom", tags=["Classroom"])


@router.get("/deadlines", response_model=list[dict[str, Any]])
async def get_classroom_deadlines(
    response: Response,
    current_user: User = Depends(get_current_user),
):
    """
    Sincroniza tareas y plazos academicos de Google Classroom para el usuario autenticado.
    Utiliza el token de acceso a Classroom almacenado en la sesion del estudiante.
    """
    if not current_user.classroom_token:
        # Sin token de Classroom registrado para este usuario
        response.headers["X-Classroom-Status"] = "missing_token"
        return []

    headers = {"Authorization": f"Bearer {current_user.classroom_token}"}
    deadlines = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Obtener cursos activos del estudiante
            courses_resp = await client.get(
                "https://classroom.googleapis.com/v1/courses?courseStates=ACTIVE",
                headers=headers,
                timeout=10.0,
            )
            if courses_resp.status_code in (401, 403):
                response.headers["X-Classroom-Status"] = "permission_denied"
                return []
            if courses_resp.status_code != 200:
                response.headers["X-Classroom-Status"] = "api_error"
                return []

            courses_data = courses_resp.json()
            courses = courses_data.get("courses", [])
            if not courses:
                response.headers["X-Classroom-Status"] = "no_courses"
                return []

            # 2. Consultar tareas publicadas para cada curso activo
            for course in courses[:8]:
                course_id = course.get("id")
                course_name = course.get("name", "Curso sin nombre")

                work_resp = await client.get(
                    f"https://classroom.googleapis.com/v1/courses/{course_id}/courseWork?courseWorkStates=PUBLISHED",
                    headers=headers,
                    timeout=10.0,
                )
                if work_resp.status_code == 200:
                    works = work_resp.json().get("courseWork", [])
                    for work in works:
                        due_date = work.get("dueDate")
                        due_time = work.get("dueTime")

                        due_date_formatted = None
                        if isinstance(due_date, dict):
                            y = due_date.get("year", 0)
                            m = due_date.get("month", 0)
                            d = due_date.get("day", 0)
                            due_date_formatted = f"{y:04d}-{m:02d}-{d:02d}"
                            if isinstance(due_time, dict):
                                hh = due_time.get("hours", 0)
                                mm = due_time.get("minutes", 0)
                                due_date_formatted += f" {hh:02d}:{mm:02d}"
                        elif isinstance(due_date, str):
                            due_date_formatted = due_date

                        deadlines.append({
                            "id": str(work.get("id", "")),
                            "course_id": str(course_id),
                            "course": course_name,
                            "title": work.get("title", "Tarea sin título"),
                            "description": work.get("description", ""),
                            "due_date": due_date,
                            "due_time": due_time,
                            "due_date_formatted": due_date_formatted,
                            "alternate_link": work.get("alternateLink", ""),
                            "max_points": work.get("maxPoints"),
                        })

        response.headers["X-Classroom-Status"] = "active"

        # Ordenar cronológicamente por fecha límite
        def _deadline_sort_key(item: dict[str, Any]) -> str:
            return item.get("due_date_formatted") or "9999-99-99"

        deadlines.sort(key=_deadline_sort_key)
        return deadlines

    except Exception as e:
        print(f"[Classroom Deadlines Sync Error] {e}")
        response.headers["X-Classroom-Status"] = "network_error"
        return []


@router.get("/courses", response_model=list[dict[str, Any]])
async def get_classroom_courses(
    response: Response,
    current_user: User = Depends(get_current_user),
):
    """
    Retorna la lista de cursos activos de Google Classroom para el usuario autenticado.
    """
    if not current_user.classroom_token:
        response.headers["X-Classroom-Status"] = "missing_token"
        return []

    headers = {"Authorization": f"Bearer {current_user.classroom_token}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            courses_resp = await client.get(
                "https://classroom.googleapis.com/v1/courses?courseStates=ACTIVE",
                headers=headers,
                timeout=10.0,
            )
            if courses_resp.status_code in (401, 403):
                response.headers["X-Classroom-Status"] = "permission_denied"
                return []
            if courses_resp.status_code != 200:
                response.headers["X-Classroom-Status"] = "api_error"
                return []

            courses_data = courses_resp.json()
            courses = courses_data.get("courses", [])
            response.headers["X-Classroom-Status"] = "active" if courses else "no_courses"

            return [
                {
                    "id": str(c.get("id", "")),
                    "name": c.get("name", "Curso sin nombre"),
                    "section": c.get("section", ""),
                    "alternate_link": c.get("alternateLink", ""),
                    "room": c.get("room", ""),
                }
                for c in courses
            ]
    except Exception as e:
        print(f"[Classroom Courses Sync Error] {e}")
        response.headers["X-Classroom-Status"] = "network_error"
        return []
