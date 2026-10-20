from typing import Any

import httpx
from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..models import User

router = APIRouter(prefix="/api/classroom", tags=["Classroom"])

@router.get("/deadlines", response_model=list[dict[str, Any]])
async def get_classroom_deadlines(
    current_user: User = Depends(get_current_user)
):
    """
    Synchronisiert anstehende Aufgaben und Fristen aus Google Classroom für den authentifizierten Nutzer.
    Nutzt den beim Login gespeicherten Google Classroom Token des jeweiligen Studenten.
    """
    if not current_user.classroom_token:
        # Kein Google Classroom Token vorhanden (Nutzer hat Scope nicht freigegeben)
        return []

    headers = {"Authorization": f"Bearer {current_user.classroom_token}"}
    deadlines = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Aktive Kurse des Studenten abrufen
            courses_resp = await client.get(
                "https://classroom.googleapis.com/v1/courses?courseStates=ACTIVE",
                headers=headers
            )
            if courses_resp.status_code != 200:
                return []
            
            courses_data = courses_resp.json()
            courses = courses_data.get("courses", [])

            # 2. Aufgaben für jeden Kurs abrufen
            for course in courses[:5]:  # Obergrenze für Performance
                course_id = course.get("id")
                course_name = course.get("name")
                
                work_resp = await client.get(
                    f"https://classroom.googleapis.com/v1/courses/{course_id}/courseWork?courseWorkStates=PUBLISHED",
                    headers=headers
                )
                if work_resp.status_code == 200:
                    works = work_resp.json().get("courseWork", [])
                    for work in works:
                        due_date = work.get("dueDate")
                        if due_date:
                            deadlines.append({
                                "id": work.get("id"),
                                "course": course_name,
                                "title": work.get("title"),
                                "due_date": due_date,
                                "alternate_link": work.get("alternateLink")
                            })
    except Exception as e:
        print(f"[Classroom Sync Error] {e}")
        return []

    return deadlines
