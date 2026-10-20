import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone, timedelta

from src.main import app
from src.database import Base, get_db
from src.models import User, Post

# SQLite In-Memory Engine mit StaticPool für gemeinsamen Speicher aller Connections
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
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # User anlegen
    user = User(email="test@upa.edu.py", full_name="Test User", role="admin", groups=["TIE"])
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 1 News Post (Instagram)
    news = Post(
        title="Búsqueda Laboral: Recepcionista",
        caption="¡Estamos buscando Recepcionista!",
        content="Texto completo de funciones...",
        post_type="INSTAGRAM",
        is_news=True,
        is_event=False,
        is_pinned=False,
        target_groups=["ALL"],
        author_id=user.id
    )
    db.add(news)
    
    # 1 Event Post (Charla IA)
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    event = Post(
        title="¿Qué significa seguir siendo humanos en la era de la IA?",
        content="Charla magistral en auditorio...",
        post_type="MANUAL",
        is_news=True,
        is_event=True,
        is_pinned=True,
        event_start=tomorrow,
        location="Auditorio Edificio 1",
        has_registration=True,
        target_groups=["ALL", "TIE"],
        author_id=user.id
    )
    db.add(event)
    db.commit()
    
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)

def test_get_news_endpoint():
    response = client.get("/api/news")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # Beide sind is_news = True
    assert data[0]["is_pinned"] is True
    assert data[0]["title"] == "¿Qué significa seguir siendo humanos en la era de la IA?"
    assert data[1]["title"] == "Búsqueda Laboral: Recepcionista"

def test_get_events_endpoint():
    response = client.get("/api/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1  # Nur der Event
    assert data[0]["title"] == "¿Qué significa seguir siendo humanos en la era de la IA?"
    assert data[0]["location"] == "Auditorio Edificio 1"
    assert data[0]["has_registration"] is True

def test_filter_by_group():
    response = client.get("/api/news?group=TIE")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
