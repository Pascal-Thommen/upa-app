"""
Servicio base de notificaciones push mediante Firebase Cloud Messaging (FCM HTTP v1).

Autenticacion: cuenta de servicio de Firebase (JSON en FCM_SERVICE_ACCOUNT_FILE). El servicio firma
un JWT RS256, lo canjea por un access token OAuth 2.0 y envia un mensaje por cada device token.
Todas las llamadas de red tienen timeout explicito. Un fallo de red o de FCM nunca interrumpe la
operacion de negocio que dispara la notificacion: el resultado queda en PushResult y en el log.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import jwt
from sqlalchemy.orm import Session

from ..config import settings
from ..models import DeviceToken, Post, User
from ..schemas.post import user_can_access_post

logger = logging.getLogger(__name__)

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
JWT_BEARER_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"
MAX_PARALLEL_SENDS = 10
TOKEN_REFRESH_MARGIN_SECONDS = 60
MAX_BODY_LENGTH = 240

EMERGENCY_BANNER = "EMERGENCY_BANNER"


class PushConfigurationError(Exception):
    """La cuenta de servicio FCM falta o es invalida."""


@dataclass
class PushResult:
    attempted: int = 0
    sent: int = 0
    failed: int = 0
    invalid_tokens: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


@dataclass
class _ServiceAccount:
    client_email: str
    private_key: str
    token_uri: str
    project_id: str


def load_service_account(path: str, project_id_override: str = "") -> _ServiceAccount:
    """Lee y valida la cuenta de servicio de Firebase desde disco."""
    file_path = Path(path)
    if not file_path.is_file():
        raise PushConfigurationError(f"Archivo de cuenta de servicio FCM no encontrado: {path}")
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PushConfigurationError(f"Cuenta de servicio FCM ilegible: {exc}") from exc

    for key in ("client_email", "private_key", "token_uri"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise PushConfigurationError(f"Cuenta de servicio FCM sin campo obligatorio '{key}'.")
    project_id = (project_id_override or data.get("project_id") or "").strip()
    if not project_id:
        raise PushConfigurationError("No hay FCM_PROJECT_ID ni project_id en la cuenta de servicio.")
    return _ServiceAccount(
        client_email=data["client_email"],
        private_key=data["private_key"],
        token_uri=data["token_uri"],
        project_id=project_id,
    )


def _extract_fcm_error_code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return ""
    for detail in error.get("details") or []:
        if isinstance(detail, dict) and detail.get("errorCode"):
            return str(detail["errorCode"])
    return str(error.get("status") or "")


class PushDispatcher:
    """Envia notificaciones a device tokens registrados via FCM HTTP v1."""

    def __init__(
        self,
        service_account_file: str,
        project_id: str = "",
        api_base_url: str = "https://fcm.googleapis.com",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._service_account_file = service_account_file
        self._project_id = project_id
        self._api_base_url = api_base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0

    @classmethod
    def from_settings(cls) -> "PushDispatcher":
        return cls(
            service_account_file=settings.FCM_SERVICE_ACCOUNT_FILE,
            project_id=settings.FCM_PROJECT_ID,
            api_base_url=settings.FCM_API_BASE_URL,
            timeout_seconds=settings.FCM_TIMEOUT_SECONDS,
        )

    async def _fetch_access_token(self, client: httpx.AsyncClient, account: _ServiceAccount) -> str:
        now = int(time.time())
        try:
            assertion = jwt.encode(
                {
                    "iss": account.client_email,
                    "scope": FCM_SCOPE,
                    "aud": account.token_uri,
                    "iat": now,
                    "exp": now + 3600,
                },
                account.private_key,
                algorithm="RS256",
            )
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise PushConfigurationError(f"Clave privada FCM invalida: {exc}") from exc

        response = await client.post(
            account.token_uri,
            data={"grant_type": JWT_BEARER_GRANT, "assertion": assertion},
        )
        if response.status_code != 200:
            raise httpx.HTTPStatusError(
                f"Google OAuth rechazo la cuenta de servicio (HTTP {response.status_code})",
                request=response.request,
                response=response,
            )
        payload = response.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise PushConfigurationError("Respuesta OAuth sin access_token.")
        expires_in = int(payload.get("expires_in") or 3600)
        self._access_token = token
        self._access_token_expires_at = time.time() + expires_in - TOKEN_REFRESH_MARGIN_SECONDS
        return token

    async def _get_access_token(self, client: httpx.AsyncClient, account: _ServiceAccount, force: bool = False) -> str:
        if not force and self._access_token and time.time() < self._access_token_expires_at:
            return self._access_token
        return await self._fetch_access_token(client, account)

    async def _send_one(
        self,
        client: httpx.AsyncClient,
        account: _ServiceAccount,
        device_token: str,
        message: dict[str, Any],
        result: PushResult,
    ) -> None:
        url = f"{self._api_base_url}/v1/projects/{account.project_id}/messages:send"
        body = {"message": {**message, "token": device_token}}
        try:
            access_token = await self._get_access_token(client, account)
            response = await client.post(url, json=body, headers={"Authorization": f"Bearer {access_token}"})
            if response.status_code == 401:
                # Access token vencido o revocado: renovar una vez y reintentar
                access_token = await self._get_access_token(client, account, force=True)
                response = await client.post(url, json=body, headers={"Authorization": f"Bearer {access_token}"})
        except (httpx.HTTPError, PushConfigurationError, ValueError) as exc:
            logger.error("[Push] Envio fallido (%s): %s", type(exc).__name__, exc)
            result.failed += 1
            return

        if response.status_code == 200:
            result.sent += 1
            return

        error_code = _extract_fcm_error_code(response)
        if response.status_code == 404 or error_code in ("UNREGISTERED", "INVALID_ARGUMENT"):
            logger.warning(
                "[Push] Device token invalido o dado de baja (HTTP %s, %s)", response.status_code, error_code
            )
            result.invalid_tokens.append(device_token)
        else:
            logger.error("[Push] FCM respondio HTTP %s (%s)", response.status_code, error_code)
        result.failed += 1

    async def send_to_tokens(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> PushResult:
        """Envia una notificacion a todos los device tokens indicados (sin duplicados)."""
        unique_tokens = list(dict.fromkeys(t.strip() for t in tokens if t and t.strip()))
        result = PushResult(attempted=len(unique_tokens))
        if not unique_tokens:
            result.skipped_reason = "no_recipients"
            logger.info("[Push] Sin destinatarios registrados, no se envia nada.")
            return result

        try:
            account = load_service_account(self._service_account_file, self._project_id)
        except PushConfigurationError as exc:
            result.skipped_reason = "not_configured"
            result.failed = len(unique_tokens)
            logger.error("[Push] FCM no configurado, %s notificaciones no enviadas: %s", len(unique_tokens), exc)
            return result

        message: dict[str, Any] = {
            "notification": {"title": title[:120], "body": body[:MAX_BODY_LENGTH]},
            "data": {str(k): str(v) for k, v in (data or {}).items()},
            "android": {"priority": "HIGH"},
        }

        semaphore = asyncio.Semaphore(MAX_PARALLEL_SENDS)
        timeout = httpx.Timeout(self._timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:

            async def guarded(device_token: str) -> None:
                async with semaphore:
                    await self._send_one(client, account, device_token, message, result)

            await asyncio.gather(*(guarded(t) for t in unique_tokens))

        logger.info(
            "[Push] Resultado attempted=%s sent=%s failed=%s invalid=%s",
            result.attempted,
            result.sent,
            result.failed,
            len(result.invalid_tokens),
        )
        return result


def collect_recipient_tokens(db: Session, target_groups: Any) -> list[str]:
    """
    Reune los device tokens de todos los usuarios autorizados para ver una publicacion con los
    grupos destino indicados (misma regla de acceso que /api/news). Incluye el token legado de User.
    """
    tokens: list[str] = []
    users = db.query(User).all()
    allowed_ids: set[int] = set()
    for user in users:
        if user_can_access_post(user, target_groups):
            allowed_ids.add(int(user.id))
            if user.device_token:
                tokens.append(user.device_token)
    if allowed_ids:
        rows = db.query(DeviceToken).filter(DeviceToken.user_id.in_(allowed_ids)).all()
        tokens.extend(row.device_token for row in rows)
    return list(dict.fromkeys(t for t in tokens if t))


def build_emergency_message(post: Post) -> tuple[str, str, dict[str, str]]:
    """Construye titulo, cuerpo y payload de datos para una Eilmeldung (EMERGENCY_BANNER)."""
    title = (post.title or "").strip() or "Comunicado urgente UPA"
    body = (post.caption or post.content or "").strip() or title
    data = {"type": EMERGENCY_BANNER, "post_id": str(post.id)}
    return title, body, data


async def dispatch_emergency_push(tokens: list[str], title: str, body: str, data: dict[str, str]) -> PushResult:
    """
    Punto de entrada para tareas en segundo plano. Registra el intento y nunca propaga excepciones,
    para que un fallo de FCM no afecte la publicacion ya guardada.
    """
    logger.info("[Push] Eilmeldung %s: %s destinatarios", data.get("post_id", "?"), len(tokens))
    try:
        return await PushDispatcher.from_settings().send_to_tokens(tokens, title, body, data)
    except Exception as exc:  # noqa: BLE001 - ninguna excepcion de red debe tumbar la tarea de fondo
        logger.exception("[Push] Error inesperado en el dispatcher: %s", exc)
        return PushResult(attempted=len(tokens), failed=len(tokens), skipped_reason="unexpected_error")
