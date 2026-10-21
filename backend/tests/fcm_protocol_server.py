"""
Servidor HTTP local real que habla el protocolo de FCM HTTP v1 y Google OAuth (JWT bearer).

No sustituye codigo de la aplicacion: es el extremo remoto del protocolo. Verifica de verdad la
firma RS256 de la assertion, el scope, la audiencia y el Bearer token de cada mensaje, y guarda
cada mensaje recibido para que las pruebas comprueben el contenido semantico enviado.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

PROJECT_ID = "upa-test-project"
CLIENT_EMAIL = "push@upa-test-project.iam.gserviceaccount.com"


def generate_rsa_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


class FcmProtocolServer:
    def __init__(self, public_key_pem: str) -> None:
        self.public_key_pem = public_key_pem
        self.messages: list[dict] = []
        self.oauth_requests = 0
        self.issued_tokens: list[str] = []
        self.reject_first_message_with_401 = False
        self._rejected_once = False
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silenciar el log de acceso en las pruebas
                return

            def _reply(self, status: int, payload: dict) -> None:
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                if self.path == "/token":
                    outer._handle_token(self, body)
                elif self.path == f"/v1/projects/{PROJECT_ID}/messages:send":
                    outer._handle_message(self, body)
                else:
                    self._reply(404, {"error": {"status": "NOT_FOUND", "message": "ruta desconocida"}})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _handle_token(self, handler, body: bytes) -> None:
        form = parse_qs(body.decode())
        if form.get("grant_type") != ["urn:ietf:params:oauth:grant-type:jwt-bearer"]:
            handler._reply(400, {"error": "unsupported_grant_type"})
            return
        try:
            claims = jwt.decode(
                form["assertion"][0],
                self.public_key_pem,
                algorithms=["RS256"],
                audience=f"{self.base_url}/token",
            )
        except jwt.PyJWTError as exc:
            handler._reply(400, {"error": "invalid_grant", "error_description": str(exc)})
            return
        if claims.get("iss") != CLIENT_EMAIL or claims.get("scope") != "https://www.googleapis.com/auth/firebase.messaging":
            handler._reply(400, {"error": "invalid_grant", "error_description": "claims incorrectos"})
            return
        with self._lock:
            self.oauth_requests += 1
            token = f"ya29.test-access-token-{self.oauth_requests}"
            self.issued_tokens.append(token)
        handler._reply(200, {"access_token": token, "expires_in": 3600, "token_type": "Bearer"})

    def _handle_message(self, handler, body: bytes) -> None:
        auth = handler.headers.get("Authorization", "")
        with self._lock:
            valid_tokens = list(self.issued_tokens)
            force_401 = self.reject_first_message_with_401 and not self._rejected_once
            if force_401:
                self._rejected_once = True
        if force_401 or not auth.startswith("Bearer ") or auth[7:] not in valid_tokens:
            handler._reply(401, {"error": {"status": "UNAUTHENTICATED", "message": "token invalido"}})
            return
        message = json.loads(body)["message"]
        device_token = message["token"]
        if device_token.startswith("slow"):
            time.sleep(2.0)
        if device_token.startswith("dead"):
            handler._reply(
                404,
                {
                    "error": {
                        "code": 404,
                        "status": "NOT_FOUND",
                        "message": "Requested entity was not found.",
                        "details": [
                            {
                                "@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError",
                                "errorCode": "UNREGISTERED",
                            }
                        ],
                    }
                },
            )
            return
        if device_token.startswith("boom"):
            handler._reply(500, {"error": {"code": 500, "status": "INTERNAL", "message": "fallo interno"}})
            return
        with self._lock:
            self.messages.append(message)
        handler._reply(200, {"name": f"projects/{PROJECT_ID}/messages/{len(self.messages)}"})
