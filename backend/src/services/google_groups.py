import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
import jwt

from ..config import settings

logger = logging.getLogger(__name__)

DIRECTORY_GROUP_SCOPE = "https://www.googleapis.com/auth/admin.directory.group.readonly"


def _load_service_account_credentials() -> dict[str, Any] | None:
    sa_path = Path(settings.GOOGLE_SERVICE_ACCOUNT_FILE)
    if not sa_path.is_absolute():
        for candidate in [
            sa_path,
            Path("/app") / sa_path,
            Path(__file__).resolve().parent.parent.parent / sa_path,
            Path(__file__).resolve().parent.parent / sa_path,
        ]:
            if candidate.exists():
                sa_path = candidate
                break

    if not sa_path.exists():
        logger.warning("Service account file not found at: %s", settings.GOOGLE_SERVICE_ACCOUNT_FILE)
        return None

    try:
        with open(sa_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to read service account JSON: %s", e)
        return None


async def get_google_groups_for_user(user_email: str) -> list[dict[str, str]]:
    """
    Fragt die realen Google Groups für einen Benutzer über die Google Workspace Directory API ab.
    Verwendet Domain-Wide Delegation mit dem hinterlegten Service Account.
    """
    sa = _load_service_account_credentials()
    if not sa:
        logger.warning("Google Groups Abfrage übersprungen: Service Account nicht verfügbar für %s", user_email)
        return []

    client_email = sa.get("client_email")
    private_key = sa.get("private_key")
    token_uri = sa.get("token_uri", "https://oauth2.googleapis.com/token")
    # Liste potentieller delegierter Super-Admin-Accounts (soporte.ti besitzt nachweislich Workspace-Admin-Rechte)
    candidates = []
    if settings.GOOGLE_ADMIN_DELEGATED_USER and settings.GOOGLE_ADMIN_DELEGATED_USER != "admin@upa.edu.py":
        candidates.append(settings.GOOGLE_ADMIN_DELEGATED_USER)
    candidates.extend(["soporte.ti@upa.edu.py", "admin@upa.edu.py"])
    # Deduplizieren unter Beibehaltung der Reihenfolge
    delegated_candidates = list(dict.fromkeys(candidates))

    if not client_email or not private_key:
        logger.error("Service Account JSON unvollständig (client_email oder private_key fehlt)")
        return []

    for delegated_user in delegated_candidates:
        now = int(time.time())
        payload = {
            "iss": client_email,
            "sub": delegated_user,
            "scope": DIRECTORY_GROUP_SCOPE,
            "aud": token_uri,
            "exp": now + 3600,
            "iat": now,
        }

        try:
            signed_jwt = jwt.encode(payload, private_key, algorithm="RS256")
        except Exception as e:
            logger.error("Fehler beim Signieren des Service Account JWTs: %s", e)
            continue

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                token_resp = await client.post(
                    token_uri,
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                        "assertion": signed_jwt,
                    },
                )
            except Exception as e:
                logger.error("Netzwerkfehler beim Anfordern des Service Account Tokens: %s", e)
                continue

            if token_resp.status_code != 200:
                logger.warning("Token Exchange für %s fehlgeschlagen (%d): %s", delegated_user, token_resp.status_code, token_resp.text)
                continue

            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                continue

            groups_url = f"https://admin.googleapis.com/admin/directory/v1/groups?userKey={user_email}"
            try:
                groups_resp = await client.get(
                    groups_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            except Exception as e:
                logger.error("Netzwerkfehler bei Google Groups Abfrage für %s: %s", user_email, e)
                continue

            if groups_resp.status_code == 200:
                data = groups_resp.json()
                raw_groups = data.get("groups", [])

                # Hierarchische / verschachtelte Gruppen rekursiv auflösen
                all_groups_map: dict[str, dict[str, str]] = {}
                queue: list[str] = []
                for g in raw_groups:
                    gemail = g.get("email", "")
                    if gemail:
                        item = {
                            "id": g.get("id", ""),
                            "name": g.get("name", ""),
                            "email": gemail,
                            "description": g.get("description", "") or "",
                        }
                        all_groups_map[gemail.lower()] = item
                        queue.append(gemail)

                visited: set[str] = set(all_groups_map.keys())
                while queue:
                    current_key = queue.pop(0)
                    parent_url = f"https://admin.googleapis.com/admin/directory/v1/groups?userKey={current_key}"
                    try:
                        p_resp = await client.get(
                            parent_url,
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        if p_resp.status_code == 200:
                            for pg in p_resp.json().get("groups", []):
                                p_email = pg.get("email", "")
                                if p_email and p_email.lower() not in visited:
                                    visited.add(p_email.lower())
                                    queue.append(p_email)
                                    all_groups_map[p_email.lower()] = {
                                        "id": pg.get("id", ""),
                                        "name": pg.get("name", ""),
                                        "email": p_email,
                                        "description": pg.get("description", "") or "",
                                    }
                    except Exception as err:
                        logger.debug("Fehler beim Abrufen der Elterngruppe fuer %s: %s", current_key, err)

                return list(all_groups_map.values())
            elif groups_resp.status_code == 403:
                logger.info("Delegierter User %s nicht autorisiert für Directory API, versuche nächsten...", delegated_user)
                continue
            else:
                logger.warning("Directory API Status %d für %s mit Admin %s", groups_resp.status_code, user_email, delegated_user)

    return []


def map_groups_to_logical_tags(groups: list[dict[str, str]]) -> list[str]:
    """
    Mappt Google Groups auf standardisierte System-Zielgruppen (z.B. TIE, ALL, PROF).
    Ermöglicht Content-Segmentierung im UPA Campus Feed.
    """
    tags = {"ALL"}
    for g in groups:
        name = g.get("name", "").lower()
        email = g.get("email", "").lower()

        if "tie" in name or "tie" in email:
            tags.add("TIE")
        if "industrial" in name or "pi" in email or "pi" in name:
            tags.add("PI")
        if "docente" in name or "prof" in name or "prof" in email:
            tags.add("PROF")
        if "informatica" in name or "software" in name:
            tags.add("TI")

        if g.get("name"):
            tags.add(g["name"])

    return sorted(list(tags))
