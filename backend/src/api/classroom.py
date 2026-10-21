import asyncio
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Response

from ..auth import get_current_user
from ..models import User
from ..schemas.classroom import (
    ClassroomCourseResponse,
    ClassroomDeadlineResponse,
    ClassroomDueDate,
    ClassroomDueTime,
)
from ..schemas.feed import ErrorResponse

router = APIRouter(prefix="/api/classroom", tags=["Classroom"])

# Cache en memoria con TTL de 5 minutos
_DEADLINES_CACHE: dict[str, tuple[float, list[ClassroomDeadlineResponse]]] = {}
_COURSES_CACHE: dict[str, tuple[float, list[ClassroomCourseResponse]]] = {}
CACHE_TTL_SECONDS = 300


def clear_classroom_cache(email: str | None = None) -> None:
    """Invalida la cache en memoria de Classroom para un usuario o globalmente."""
    if email:
        normalized = email.strip().lower()
        _DEADLINES_CACHE.pop(normalized, None)
        _COURSES_CACHE.pop(normalized, None)
    else:
        _DEADLINES_CACHE.clear()
        _COURSES_CACHE.clear()


def _parse_due_date_and_time(
    due_date_raw: Any,
    due_time_raw: Any,
) -> tuple[ClassroomDueDate, ClassroomDueTime, str]:
    """Normaliza fechas y horas de Classroom evitando valores nulos o formatos rotos."""
    due_date_obj = ClassroomDueDate(year=0, month=0, day=0)
    due_time_obj = ClassroomDueTime(hours=23, minutes=59)
    due_date_formatted = ""

    if isinstance(due_date_raw, dict):
        try:
            y = int(due_date_raw.get("year") or 0)
            m = int(due_date_raw.get("month") or 0)
            d = int(due_date_raw.get("day") or 0)
        except (TypeError, ValueError):
            y, m, d = 0, 0, 0
        due_date_obj = ClassroomDueDate(year=y, month=m, day=d)
        if y > 0 and 1 <= m <= 12 and 1 <= d <= 31:
            due_date_formatted = f"{y:04d}-{m:02d}-{d:02d}"
            if isinstance(due_time_raw, dict):
                try:
                    hh = int(due_time_raw.get("hours") or 0)
                    mm = int(due_time_raw.get("minutes") or 0)
                except (TypeError, ValueError):
                    hh, mm = 0, 0
                hh = max(0, min(23, hh))
                mm = max(0, min(59, mm))
                due_time_obj = ClassroomDueTime(hours=hh, minutes=mm)
                due_date_formatted += f" {hh:02d}:{mm:02d}"
    elif isinstance(due_date_raw, str) and due_date_raw.strip():
        due_date_formatted = due_date_raw.strip()
        date_part = due_date_formatted.split("T")[0].split(" ")[0]
        parts = date_part.split("-")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            due_date_obj = ClassroomDueDate(
                year=int(parts[0]),
                month=int(parts[1]),
                day=int(parts[2]),
            )

    return due_date_obj, due_time_obj, due_date_formatted


@router.get(
    "/deadlines",
    response_model=list[ClassroomDeadlineResponse],
    summary="Obtener entregas y plazos academicos de Google Classroom",
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Token JWT ausente, invalido o expirado",
        }
    },
)
async def get_classroom_deadlines(
    response: Response,
    current_user: User = Depends(get_current_user),
) -> list[ClassroomDeadlineResponse]:
    """
    Sincroniza tareas y plazos academicos de Google Classroom para el usuario autenticado.
    Garantiza objetos completamente tipados sin valores nulos.
    """
    token = (current_user.classroom_token or "").strip()
    if not token:
        response.headers["X-Classroom-Status"] = "missing_token"
        return []

    cache_key = (current_user.email or "").lower()
    user_cache = _DEADLINES_CACHE.get(cache_key)
    if user_cache and (time.time() - user_cache[0] < CACHE_TTL_SECONDS):
        response.headers["X-Classroom-Status"] = "cached"
        return user_cache[1]

    headers = {"Authorization": f"Bearer {token}"}
    deadlines: list[ClassroomDeadlineResponse] = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            courses_resp = await client.get(
                "https://classroom.googleapis.com/v1/courses?studentId=me&courseStates=ACTIVE",
                headers=headers,
                timeout=6.0,
            )
            if courses_resp.status_code in (401, 403):
                response.headers["X-Classroom-Status"] = "permission_denied"
                return []
            if courses_resp.status_code != 200:
                response.headers["X-Classroom-Status"] = "api_error"
                return []

            courses_data = courses_resp.json()
            raw_courses = courses_data.get("courses") if isinstance(courses_data, dict) else []
            courses = [c for c in (raw_courses or []) if isinstance(c, dict)]
            if not courses:
                response.headers["X-Classroom-Status"] = "no_courses"
                return []

            async def fetch_course_work(course: dict[str, Any]) -> list[ClassroomDeadlineResponse]:
                c_id = str(course.get("id") or "").strip()
                if not c_id:
                    return []
                c_name = str(course.get("name") or "Curso sin nombre").strip() or "Curso sin nombre"
                try:
                    work_resp = await client.get(
                        f"https://classroom.googleapis.com/v1/courses/{c_id}/courseWork?courseWorkStates=PUBLISHED",
                        headers=headers,
                        timeout=5.0,
                    )
                    if work_resp.status_code != 200:
                        return []
                    work_json = work_resp.json()
                    raw_works = work_json.get("courseWork") if isinstance(work_json, dict) else []
                    works = [w for w in (raw_works or []) if isinstance(w, dict)]
                    items: list[ClassroomDeadlineResponse] = []
                    for idx, work in enumerate(works):
                        work_id = str(work.get("id") or f"{c_id}_{idx}").strip()
                        title = str(work.get("title") or "Tarea sin titulo").strip() or "Tarea sin titulo"
                        description = str(work.get("description") or "").strip()
                        due_date_obj, due_time_obj, due_date_formatted = _parse_due_date_and_time(
                            work.get("dueDate"),
                            work.get("dueTime"),
                        )
                        alt_link = (
                            str(work.get("alternateLink") or "").strip()
                            or f"https://classroom.google.com/c/{c_id}"
                        )
                        raw_points = work.get("maxPoints")
                        try:
                            max_points = float(raw_points) if raw_points is not None else 0.0
                        except (TypeError, ValueError):
                            max_points = 0.0

                        items.append(
                            ClassroomDeadlineResponse(
                                id=work_id,
                                assignment_id=work_id,
                                course_id=c_id,
                                course=c_name,
                                course_name=c_name,
                                title=title,
                                description=description,
                                due_date=due_date_obj,
                                due_time=due_time_obj,
                                due_date_formatted=due_date_formatted,
                                alternate_link=alt_link,
                                max_points=max_points,
                            )
                        )
                    return items
                except Exception:
                    return []

            tasks = [fetch_course_work(c) for c in courses[:10]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    deadlines.extend(res)

        response.headers["X-Classroom-Status"] = "active"

        def _deadline_sort_key(item: ClassroomDeadlineResponse) -> str:
            return item.due_date_formatted if item.due_date_formatted else "9999-99-99"

        deadlines.sort(key=_deadline_sort_key)
        _DEADLINES_CACHE[cache_key] = (time.time(), deadlines)
        return deadlines

    except Exception as e:
        print(f"[Classroom Deadlines Sync Error] {e}")
        response.headers["X-Classroom-Status"] = "network_error"
        return []


@router.get(
    "/courses",
    response_model=list[ClassroomCourseResponse],
    summary="Obtener lista de cursos activos de Google Classroom",
    responses={
        401: {
            "model": ErrorResponse,
            "description": "Token JWT ausente, invalido o expirado",
        }
    },
)
async def get_classroom_courses(
    response: Response,
    current_user: User = Depends(get_current_user),
) -> list[ClassroomCourseResponse]:
    """
    Retorna la lista de cursos activos de Google Classroom para el usuario autenticado.
    Garantiza objetos tipados sin campos nulos.
    """
    token = (current_user.classroom_token or "").strip()
    if not token:
        response.headers["X-Classroom-Status"] = "missing_token"
        return []

    cache_key = (current_user.email or "").lower()
    user_cache = _COURSES_CACHE.get(cache_key)
    if user_cache and (time.time() - user_cache[0] < CACHE_TTL_SECONDS):
        response.headers["X-Classroom-Status"] = "cached"
        return user_cache[1]

    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            courses_resp = await client.get(
                "https://classroom.googleapis.com/v1/courses?studentId=me&courseStates=ACTIVE",
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
            raw_courses = courses_data.get("courses") if isinstance(courses_data, dict) else []
            courses = [c for c in (raw_courses or []) if isinstance(c, dict)]
            response.headers["X-Classroom-Status"] = "active" if courses else "no_courses"

            result: list[ClassroomCourseResponse] = []
            for idx, c in enumerate(courses):
                c_id = str(c.get("id") or f"course_{idx}").strip()
                c_name = str(c.get("name") or "Curso sin nombre").strip() or "Curso sin nombre"
                section = str(c.get("section") or "").strip()
                alt_link = (
                    str(c.get("alternateLink") or "").strip()
                    or f"https://classroom.google.com/c/{c_id}"
                )
                room = str(c.get("room") or "").strip()
                result.append(
                    ClassroomCourseResponse(
                        id=c_id,
                        name=c_name,
                        section=section,
                        alternate_link=alt_link,
                        room=room,
                    )
                )

            _COURSES_CACHE[cache_key] = (time.time(), result)
            return result
    except Exception as e:
        print(f"[Classroom Courses Sync Error] {e}")
        response.headers["X-Classroom-Status"] = "network_error"
        return []
