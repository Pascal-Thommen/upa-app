"""Pruebas del endpoint POST /api/media/upload y de la entrega estatica bajo /uploads."""

import re
import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.media import get_upload_dir
from src.auth import create_access_token
from src.config import settings
from src.database import Base, get_db
from src.main import app
from src.models import User

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)

UUID_FILENAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp|pdf)$")


def _png_bytes() -> bytes:
    """PNG valido de 2x2 pixeles, construido byte a byte."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 2 for _ in range(2))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


PNG = _png_bytes()
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 64 + b"\xff\xd9"
WEBP = b"RIFF" + struct.pack("<I", 4 + 8 + 10) + b"WEBPVP8 " + struct.pack("<I", 10) + b"\x00" * 10
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


@pytest.fixture(autouse=True)
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.add_all(
        [
            User(id=1, email="admin@upa.edu.py", full_name="Admin UPA", role="admin", groups=["ALL"]),
            User(id=2, email="estudiante@upa.edu.py", full_name="Estudiante TIE", role="user", groups=["TIE"]),
        ]
    )
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def auth(user_id: int = 2) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}


def upload(content: bytes, content_type: str, filename: str = "archivo.bin", headers=None):
    return client.post(
        "/api/media/upload",
        files={"file": (filename, content, content_type)},
        headers=auth() if headers is None else headers,
    )


def upload_dir_entries() -> list[Path]:
    return sorted(get_upload_dir().iterdir())


@pytest.fixture
def clean_upload_dir():
    for entry in upload_dir_entries():
        entry.unlink()
    yield
    for entry in upload_dir_entries():
        entry.unlink()


# ---------------------------------------------------------------- Caso normal


@pytest.mark.parametrize(
    ("content", "content_type", "extension"),
    [
        (PNG, "image/png", ".png"),
        (JPEG, "image/jpeg", ".jpg"),
        (WEBP, "image/webp", ".webp"),
        (PDF, "application/pdf", ".pdf"),
    ],
)
def test_upload_returns_exact_business_payload_and_file_is_retrievable(
    clean_upload_dir, content, content_type, extension
):
    response = upload(content, content_type, filename="Plakate Sommerfest 2026.PNG")
    assert response.status_code == 201

    body = response.json()
    assert set(body) == {"url", "filename", "content_type", "size_bytes"}
    assert UUID_FILENAME.match(body["filename"])
    assert body["filename"].endswith(extension)
    assert body["content_type"] == content_type
    assert body["size_bytes"] == len(content)
    assert body["url"] == f"http://testserver/uploads/{body['filename']}"

    # Persistido en disco, identico byte a byte y sin restos temporales
    stored = get_upload_dir() / body["filename"]
    assert stored.read_bytes() == content
    assert [p.name for p in upload_dir_entries()] == [body["filename"]]

    # Accesible mediante la URL devuelta, con los encabezados correctos para clientes moviles
    fetched = client.get(body["url"].replace("http://testserver", ""))
    assert fetched.status_code == 200
    assert fetched.content == content
    assert fetched.headers["content-type"].split(";")[0] == content_type
    assert fetched.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert fetched.headers["x-content-type-options"] == "nosniff"
    assert fetched.headers["etag"]


def test_conditional_request_returns_304_with_cache_headers(clean_upload_dir):
    body = upload(PNG, "image/png").json()
    path = f"/uploads/{body['filename']}"
    first = client.get(path)
    second = client.get(path, headers={"If-None-Match": first.headers["etag"]})
    assert second.status_code == 304
    assert second.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_same_original_filename_never_collides(clean_upload_dir):
    first = upload(PNG, "image/png", filename="poster.png").json()
    second = upload(PNG, "image/png", filename="poster.png").json()
    assert first["filename"] != second["filename"]
    assert len(upload_dir_entries()) == 2


def test_client_filename_is_never_used_on_disk(clean_upload_dir):
    response = upload(PNG, "image/png", filename="../../etc/evil.png")
    assert response.status_code == 201
    body = response.json()
    assert UUID_FILENAME.match(body["filename"])
    assert [p.name for p in upload_dir_entries()] == [body["filename"]]


def test_admin_may_upload_too(clean_upload_dir):
    response = upload(PDF, "application/pdf", headers=auth(1))
    assert response.status_code == 201
    assert response.json()["content_type"] == "application/pdf"


def test_public_base_url_setting_is_used(clean_upload_dir, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://api.upa.edu.py/")
    body = upload(PNG, "image/png").json()
    assert body["url"] == f"https://api.upa.edu.py/uploads/{body['filename']}"


# ---------------------------------------------------------------- Seguridad


def test_upload_requires_authentication(clean_upload_dir):
    response = upload(PNG, "image/png", headers={})
    assert response.status_code == 401
    assert upload_dir_entries() == []


def test_upload_rejects_invalid_token(clean_upload_dir):
    response = upload(PNG, "image/png", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401
    assert upload_dir_entries() == []


def test_upload_rejects_token_of_unknown_user(clean_upload_dir):
    response = upload(PNG, "image/png", headers=auth(999))
    assert response.status_code == 401
    assert upload_dir_entries() == []


# ---------------------------------------------------------------- Casos de error


def test_executable_is_rejected_with_400(clean_upload_dir):
    response = upload(b"MZ\x90\x00\x03\x00\x00\x00", "application/x-msdownload", filename="setup.exe")
    assert response.status_code == 400
    assert "no permitido" in response.json()["detail"]
    assert upload_dir_entries() == []


def test_executable_disguised_as_png_is_rejected_by_content(clean_upload_dir):
    response = upload(b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 100, "image/png", filename="virus.png")
    assert response.status_code == 400
    assert "contenido" in response.json()["detail"]
    assert upload_dir_entries() == []


def test_declared_type_must_match_real_content(clean_upload_dir):
    response = upload(PNG, "image/jpeg", filename="mislabeled.jpg")
    assert response.status_code == 400
    assert upload_dir_entries() == []


@pytest.mark.parametrize("content_type", ["image/gif", "text/html", "image/svg+xml", "application/zip", ""])
def test_disallowed_mime_types_are_rejected(clean_upload_dir, content_type):
    response = upload(b"GIF89a<script>alert(1)</script>", content_type)
    assert response.status_code == 400
    assert upload_dir_entries() == []


def test_empty_file_is_rejected(clean_upload_dir):
    response = upload(b"", "image/png")
    assert response.status_code == 400
    assert "vacio" in response.json()["detail"]
    assert upload_dir_entries() == []


def test_missing_file_field_is_rejected_with_400(clean_upload_dir):
    response = client.post("/api/media/upload", data={"note": "sin archivo"}, headers=auth())
    assert response.status_code == 400
    assert "file" in response.json()["detail"]


def test_unavailable_storage_returns_500_and_not_a_crash(clean_upload_dir, monkeypatch, tmp_path):
    blocker = tmp_path / "es_un_archivo"
    blocker.write_text("no es un directorio")
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(blocker / "uploads"))
    response = upload(PNG, "image/png")
    assert response.status_code == 500
    assert "almacenamiento" in response.json()["detail"]


# ---------------------------------------------------------------- Valores limite


def test_file_of_exactly_10_mb_is_accepted(clean_upload_dir):
    limit = settings.MAX_UPLOAD_SIZE_BYTES
    assert limit == 10 * 1024 * 1024
    content = PDF + b"0" * (limit - len(PDF))
    assert len(content) == limit
    response = upload(content, "application/pdf")
    assert response.status_code == 201
    assert response.json()["size_bytes"] == limit
    assert (get_upload_dir() / response.json()["filename"]).stat().st_size == limit


def test_file_one_byte_over_10_mb_is_rejected_and_leaves_no_residue(clean_upload_dir):
    limit = settings.MAX_UPLOAD_SIZE_BYTES
    content = PDF + b"0" * (limit + 1 - len(PDF))
    assert len(content) == limit + 1
    response = upload(content, "application/pdf")
    assert response.status_code == 400
    assert "10 MB" in response.json()["detail"]
    assert upload_dir_entries() == []


def test_smallest_valid_file_of_one_chunk_boundary_is_stored_intact(clean_upload_dir):
    chunk = 64 * 1024
    content = PDF + b"x" * (chunk - len(PDF))  # justo en el limite de un bloque de lectura
    response = upload(content, "application/pdf")
    assert response.status_code == 201
    assert (get_upload_dir() / response.json()["filename"]).read_bytes() == content


# ---------------------------------------------------------------- Entrega estatica


def test_unknown_upload_returns_404():
    assert client.get("/uploads/00000000000000000000000000000000.png").status_code == 404


def test_path_traversal_is_not_served():
    assert client.get("/uploads/../src/main.py").status_code == 404
    assert client.get("/uploads/%2e%2e/src/main.py").status_code == 404


def test_directory_listing_is_not_exposed():
    response = client.get("/uploads/")
    assert response.status_code == 404
