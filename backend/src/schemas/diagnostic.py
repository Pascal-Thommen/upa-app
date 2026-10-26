from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SystemDiagnosticsResponse(BaseModel):
    status: str
    timestamp: datetime
    database: dict[str, Any]
    directory_sync: dict[str, Any]
    classroom_api: dict[str, Any]
    application: dict[str, Any]
