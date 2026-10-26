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
    Consulta los grupos reales de un usuario mediante la Google Workspace Directory API
    empleando delegacion de dominio con la cuenta de servicio configurada.
    """
    sa = _load_service_account_credentials()
    if not sa:
        logger.warning("Consulta de Google Groups omitida: cuenta de servicio no disponible para %s", user_email)
        return []

    client_email = sa.get("client_email")
    private_key = sa.get("private_key")
    token_uri = sa.get("token_uri", "https://oauth2.googleapis.com/token")
    # Cuentas delegadas candidatas con permisos de administracion de directorio
    candidates = []
    if settings.GOOGLE_ADMIN_DELEGATED_USER and settings.GOOGLE_ADMIN_DELEGATED_USER != "admin@upa.edu.py":
        candidates.append(settings.GOOGLE_ADMIN_DELEGATED_USER)
    candidates.extend(["soporte.ti@upa.edu.py", "admin@upa.edu.py"])
    delegated_candidates = list(dict.fromkeys(candidates))

    if not client_email or not private_key:
        logger.error("JSON de cuenta de servicio incompleto (falta client_email o private_key)")
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
                    timeout=10.0,
                )
            except Exception as e:
                logger.error("Netzwerkfehler beim Anfordern des Service Account Tokens: %s", e)
                continue

            if token_resp.status_code != 200:
                logger.warning(
                    "Token Exchange für %s fehlgeschlagen (%d): %s",
                    delegated_user,
                    token_resp.status_code,
                    token_resp.text,
                )
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
                    timeout=10.0,
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
                            timeout=10.0,
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
                logger.info(
                    "Delegierter User %s nicht autorisiert für Directory API, versuche nächsten...", delegated_user
                )
                continue
            else:
                logger.warning(
                    "Directory API Status %d für %s mit Admin %s", groups_resp.status_code, user_email, delegated_user
                )

    return []


def map_groups_to_logical_tags(groups: list[dict[str, str]]) -> list[str]:
    """
    Asocia los grupos de Google Workspace a etiquetas institucionales estandarizadas (ej. TIE, ALL, PROF)
    para la segmentacion de contenido en el feed del campus.
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


class WorkspaceDirectoryUnavailable(Exception):
    """El listado de grupos de Google Workspace no esta disponible (sin credenciales, red o permisos)."""


async def list_workspace_groups(domain: str | None = None) -> list[dict[str, str]]:
    """
    Lista todos los grupos del dominio mediante la Google Directory API (Service Account con delegacion).
    Lanza WorkspaceDirectoryUnavailable con un mensaje legible si no es posible obtener el listado.
    """
    sa = _load_service_account_credentials()
    if not sa:
        raise WorkspaceDirectoryUnavailable("Google Workspace no está conectado (falta la cuenta de servicio).")

    client_email = sa.get("client_email")
    private_key = sa.get("private_key")
    token_uri = sa.get("token_uri", "https://oauth2.googleapis.com/token")
    if not client_email or not private_key:
        raise WorkspaceDirectoryUnavailable("La cuenta de servicio de Google está incompleta.")

    candidates = []
    if settings.GOOGLE_ADMIN_DELEGATED_USER and settings.GOOGLE_ADMIN_DELEGATED_USER != "admin@upa.edu.py":
        candidates.append(settings.GOOGLE_ADMIN_DELEGATED_USER)
    candidates.extend(["soporte.ti@upa.edu.py", "admin@upa.edu.py"])
    target_domain = domain or settings.ALLOWED_EMAIL_DOMAIN

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for delegated_user in dict.fromkeys(candidates):
                now = int(time.time())
                assertion = jwt.encode(
                    {
                        "iss": client_email,
                        "sub": delegated_user,
                        "scope": DIRECTORY_GROUP_SCOPE,
                        "aud": token_uri,
                        "exp": now + 3600,
                        "iat": now,
                    },
                    private_key,
                    algorithm="RS256",
                )
                token_resp = await client.post(
                    token_uri,
                    data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
                    timeout=10.0,
                )
                if token_resp.status_code != 200:
                    continue
                access_token = token_resp.json().get("access_token")
                if not access_token:
                    continue

                groups: list[dict[str, str]] = []
                page_token: str | None = None
                while True:
                    params = {"domain": target_domain, "maxResults": "200"}
                    if page_token:
                        params["pageToken"] = page_token
                    resp = await client.get(
                        "https://admin.googleapis.com/admin/directory/v1/groups",
                        params=params,
                        headers={"Authorization": f"Bearer {access_token}"},
                        timeout=10.0,
                    )
                    if resp.status_code == 403:
                        break  # este usuario delegado no es administrador: probar el siguiente
                    if resp.status_code != 200:
                        raise WorkspaceDirectoryUnavailable(f"Google Directory respondió con el estado {resp.status_code}.")
                    data = resp.json()
                    for item in data.get("groups", []):
                        email = (item.get("email") or "").strip().lower()
                        if email:
                            groups.append(
                                {
                                    "id": item.get("id", "") or "",
                                    "name": item.get("name", "") or email,
                                    "email": email,
                                    "description": item.get("description", "") or "",
                                }
                            )
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        return sorted(groups, key=lambda g: g["name"].lower())
    except httpx.TimeoutException as exc:
        raise WorkspaceDirectoryUnavailable("Google Workspace no respondió a tiempo.") from exc
    except httpx.HTTPError as exc:
        raise WorkspaceDirectoryUnavailable("No se pudo contactar con Google Workspace.") from exc
    except (ValueError, jwt.PyJWTError) as exc:
        raise WorkspaceDirectoryUnavailable("Respuesta no válida de Google Workspace.") from exc

    raise WorkspaceDirectoryUnavailable("Ninguna cuenta delegada tiene permiso para listar los grupos.")
