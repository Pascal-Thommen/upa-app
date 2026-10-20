import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import User

# In-Memory SQLite Engine für isolierte Auth-Tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_auth_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # 1 Normaler Student
    student = User(
        id=10,
        email="student@upa.edu.py",
        full_name="Normaler Student",
        role="user",
        groups=["TIE"]
    )
    # 1 Administrator
    admin = User(
        id=20,
        email="admin@upa.edu.py",
        full_name="Admin User",
        role="admin",
        groups=["ALL"]
    )
    db.add(student)
    db.add(admin)
    db.commit()
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)

def test_jwt_creation_and_decoding():
    token = create_access_token(data={"sub": "10", "email": "student@upa.edu.py", "role": "user"})
    assert isinstance(token, str)
    assert len(token) > 20

def test_get_me_unauthorized_without_token():
    response = client.get("/api/auth/me")
    assert response.status_code == 401

def test_get_me_authorized_with_token():
    token = create_access_token(data={"sub": "10", "email": "student@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "student@upa.edu.py"
    assert data["role"] == "user"

def test_create_news_forbidden_for_normal_student():
    token = create_access_token(data={"sub": "10", "email": "student@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "title": "Versuchter Fake Post",
        "content": "Sollte blockiert werden",
        "is_news": True
    }
    response = client.post("/api/news", json=payload, headers=headers)
    assert response.status_code == 403
    assert "Administrator-Rechte erforderlich" in response.json()["detail"]

def test_create_news_allowed_for_admin():
    token = create_access_token(data={"sub": "20", "email": "admin@upa.edu.py", "role": "admin"})
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "title": "Offizieller Admin Post",
        "content": "Erfolgreich erstellt durch Administrator",
        "is_news": True,
        "is_pinned": True
    }
    response = client.post("/api/news", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Offizieller Admin Post"
    assert data["is_pinned"] is True

def test_get_my_groups_authorized():
    token = create_access_token(data={"sub": "10", "email": "student@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/auth/groups", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_map_groups_to_logical_tags():
    from src.services.google_groups import map_groups_to_logical_tags
    groups = [
        {"id": "1", "name": "Estudiantes TIE 2025", "email": "estudiantes.tie2025@upa.edu.py", "description": ""},
        {"id": "2", "name": "Profesores Ingenieria", "email": "prof.ingenieria@upa.edu.py", "description": ""}
    ]
    tags = map_groups_to_logical_tags(groups)
    assert "ALL" in tags
    assert "TIE" in tags
    assert "PROF" in tags
    assert "Estudiantes TIE 2025" in tags
