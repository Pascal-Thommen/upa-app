import asyncio
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
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


async def refresh_classroom_access_token(
    user: User,
    db: Session,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """
    Renueva automaticamente el token OAuth 2.0 de Google Classroom mediante el
    classroom_refresh_token almacenado del usuario contra el endpoint oficial de Google.
    """
    refresh_token = (getattr(user, "classroom_refresh_token", None) or "").strip()
    if not refresh_token:
        return None

    form_data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        if client is not None:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data=form_data,
                headers=headers,
                timeout=10.0,
            )
        else:
            async with httpx.AsyncClient(timeout=10.0) as owned_client:
                token_resp = await owned_client.post(
                    "https://oauth2.googleapis.com/token",
                    data=form_data,
                    headers=headers,
                    timeout=10.0,
                )
    except Exception as exc:
        print(f"[Classroom Token Refresh Error] {exc}")
        return None

    if token_resp.status_code != 200:
        return None

    try:
        token_data = token_resp.json()
    except ValueError:
        return None

    if not isinstance(token_data, dict):
        return None

    new_access_token = str(token_data.get("access_token") or "").strip()
    if not new_access_token:
        return None

    new_refresh_token = str(token_data.get("refresh_token") or "").strip()
    user.classroom_token = new_access_token
    if new_refresh_token:
        user.classroom_refresh_token = new_refresh_token

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except Exception as exc:
        db.rollback()
        print(f"[Classroom Token DB Commit Error] {exc}")

    clear_classroom_cache(user.email)
    return new_access_token


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


async def fetch_user_classroom_deadlines(
    current_user: User,
    db: Session,
    response: Response | None = None,
) -> list[ClassroomDeadlineResponse]:
    """
    Obtiene y sincroniza los plazos academicos de Google Classroom para el usuario,
    ejecutando auto-refresh transparente del token OAuth si recibe HTTP 401.
    """
    token = (current_user.classroom_token or "").strip()
    refresh_token = (getattr(current_user, "classroom_refresh_token", None) or "").strip()
    if not token and not refresh_token:
        if response is not None:
            response.headers["X-Classroom-Status"] = "missing_token"
        return []

    cache_key = (current_user.email or "").lower()
    if token:
        user_cache = _DEADLINES_CACHE.get(cache_key)
        if user_cache and (time.time() - user_cache[0] < CACHE_TTL_SECONDS):
            if response is not None:
                response.headers["X-Classroom-Status"] = "cached"
            return user_cache[1]

    deadlines: list[ClassroomDeadlineResponse] = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if not token and refresh_token:
                refreshed = await refresh_classroom_access_token(current_user, db, client=client)
                if not refreshed:
                    if response is not None:
                        response.headers["X-Classroom-Status"] = "permission_denied"
                    return []
                token = refreshed
                if response is not None:
                    response.headers["X-Classroom-Token-Refreshed"] = "true"

            headers = {"Authorization": f"Bearer {token}"}
            courses_resp = await client.get(
                "https://classroom.googleapis.com/v1/courses?studentId=me&courseStates=ACTIVE",
                headers=headers,
                timeout=6.0,
            )

            if courses_resp.status_code == 401 and refresh_token:
                refreshed = await refresh_classroom_access_token(current_user, db, client=client)
                if refreshed:
                    token = refreshed
                    headers = {"Authorization": f"Bearer {token}"}
                    if response is not None:
                        response.headers["X-Classroom-Token-Refreshed"] = "true"
                    courses_resp = await client.get(
                        "https://classroom.googleapis.com/v1/courses?studentId=me&courseStates=ACTIVE",
                        headers=headers,
                        timeout=6.0,
                    )

            if courses_resp.status_code in (401, 403):
                if response is not None:
                    response.headers["X-Classroom-Status"] = "permission_denied"
                return []
            if courses_resp.status_code != 200:
                if response is not None:
                    response.headers["X-Classroom-Status"] = "api_error"
                return []

            courses_data = courses_resp.json()
            raw_courses = courses_data.get("courses") if isinstance(courses_data, dict) else []
            courses = [c for c in (raw_courses or []) if isinstance(c, dict)]
            if not courses:
                if response is not None:
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
                            str(work.get("alternateLink") or "").strip() or f"https://classroom.google.com/c/{c_id}"
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

        if response is not None:
            response.headers["X-Classroom-Status"] = "active"

        def _deadline_sort_key(item: ClassroomDeadlineResponse) -> str:
            return item.due_date_formatted if item.due_date_formatted else "9999-99-99"

        deadlines.sort(key=_deadline_sort_key)
        _DEADLINES_CACHE[cache_key] = (time.time(), deadlines)
        return deadlines

    except Exception as e:
        print(f"[Classroom Deadlines Sync Error] {e}")
        if response is not None:
            response.headers["X-Classroom-Status"] = "network_error"
        return []


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
    db: Session = Depends(get_db),
) -> list[ClassroomDeadlineResponse]:
    """
    Sincroniza tareas y plazos academicos de Google Classroom para el usuario autenticado.
    Incluye renovacion automatica del token de Classroom en caso de expiracion (HTTP 401).
    """
    return await fetch_user_classroom_deadlines(current_user=current_user, db=db, response=response)


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
    db: Session = Depends(get_db),
) -> list[ClassroomCourseResponse]:
    """
    Retorna la lista de cursos activos de Google Classroom para el usuario autenticado.
    Incluye renovacion automatica del token OAuth en caso de HTTP 401.
    """
    token = (current_user.classroom_token or "").strip()
    refresh_token = (getattr(current_user, "classroom_refresh_token", None) or "").strip()
    if not token and not refresh_token:
        response.headers["X-Classroom-Status"] = "missing_token"
        return []

    cache_key = (current_user.email or "").lower()
    if token:
        user_cache = _COURSES_CACHE.get(cache_key)
        if user_cache and (time.time() - user_cache[0] < CACHE_TTL_SECONDS):
            response.headers["X-Classroom-Status"] = "cached"
            return user_cache[1]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if not token and refresh_token:
                refreshed = await refresh_classroom_access_token(current_user, db, client=client)
                if not refreshed:
                    response.headers["X-Classroom-Status"] = "permission_denied"
                    return []
                token = refreshed
                response.headers["X-Classroom-Token-Refreshed"] = "true"

            headers = {"Authorization": f"Bearer {token}"}
            courses_resp = await client.get(
                "https://classroom.googleapis.com/v1/courses?studentId=me&courseStates=ACTIVE",
                headers=headers,
                timeout=10.0,
            )

            if courses_resp.status_code == 401 and refresh_token:
                refreshed = await refresh_classroom_access_token(current_user, db, client=client)
                if refreshed:
                    token = refreshed
                    headers = {"Authorization": f"Bearer {token}"}
                    response.headers["X-Classroom-Token-Refreshed"] = "true"
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
                alt_link = str(c.get("alternateLink") or "").strip() or f"https://classroom.google.com/c/{c_id}"
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
