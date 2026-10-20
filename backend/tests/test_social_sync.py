import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.main import app
from src.database import Base, get_db
from src.models import User, Post
from src.auth import create_access_token
from src.services.sociablekit import SociableKitService

# In-Memory SQLite Engine für isolierte Tests
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
def setup_social_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    admin = User(
        id=1,
        email="soporte.ti@upa.edu.py",
        full_name="Admin UPA",
        role="admin",
        groups=["ALL"]
    )
    student = User(
        id=2,
        email="estudiante@upa.edu.py",
        full_name="Student UPA",
        role="user",
        groups=["TIE"]
    )
    db.add(admin)
    db.add(student)
    db.commit()
    
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def test_sociablekit_sync_posts_insertion_and_deduplication():
    db = TestingSessionLocal()
    service = SociableKitService()
    
    mock_payload = [
        {
            "id": "ig_1001",
            "caption": "¡Charla sobre Inteligencia Artificial en el Aula Magna!\nNo te la pierdas.",
            "media_url": "https://cdn.instagram.com/pic1.jpg",
            "permalink": "https://www.instagram.com/p/ig_1001/",
            "media_type": "IMAGE"
        },
        {
            "id": "ig_1002",
            "caption": "Búsqueda laboral para egresados de Ingeniería Industrial.",
            "media_url": "https://cdn.instagram.com/pic2.jpg",
            "permalink": "https://www.instagram.com/p/ig_1002/",
            "media_type": "CAROUSEL_ALBUM"
        }
    ]
    
    # 1. Erstmalige Synchronisation (2 neue Posts)
    count1 = service.sync_posts(db, raw_posts=mock_payload)
    assert count1 == 2
    
    posts = db.query(Post).filter(Post.post_type == "INSTAGRAM").all()
    assert len(posts) == 2
    p1 = db.query(Post).filter(Post.instagram_id == "ig_1001").first()
    assert p1 is not None
    assert p1.title == "¡Charla sobre Inteligencia Artificial en el Aula Magna!"
    assert p1.is_news is True
    assert p1.media_url == "https://cdn.instagram.com/pic1.jpg"
    
    # 2. Zweite Synchronisation mit aktualisierter Caption (Deduplizierung)
    mock_payload[0]["caption"] = "Aktualisierte Caption für IA Charla"
    count2 = service.sync_posts(db, raw_posts=mock_payload)
    assert count2 == 2
    
    # Sicherstellen, dass keine Duplikate entstanden sind
    total_posts = db.query(Post).filter(Post.post_type == "INSTAGRAM").count()
    assert total_posts == 2
    updated_p1 = db.query(Post).filter(Post.instagram_id == "ig_1001").first()
    assert updated_p1.caption == "Aktualisierte Caption für IA Charla"
    db.close()


def test_sociablekit_resilience_empty_or_failed():
    db = TestingSessionLocal()
    service = SociableKitService(embed_id="")
    # Wenn keine ID gesetzt ist, liefert API leere Liste und stürzt nicht ab
    count = service.sync_posts(db)
    assert count == 0
    db.close()


def test_social_status_endpoint():
    response = client.get("/api/social/status")
    assert response.status_code == 200
    data = response.json()
    assert "sociablekit_configured" in data
    assert "total_instagram_posts" in data
    assert data["channel"] == "@upalemana"


def test_social_sync_requires_admin():
    student_token = create_access_token(data={"sub": "2", "email": "estudiante@upa.edu.py", "role": "user"})
    student_headers = {"Authorization": f"Bearer {student_token}"}
    
    # Student wird mit 403 abgewiesen
    response_student = client.post("/api/social/sync", headers=student_headers)
    assert response_student.status_code == 403
    
    admin_token = create_access_token(data={"sub": "1", "email": "soporte.ti@upa.edu.py", "role": "admin"})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Admin darf synchronisieren
    response_admin = client.post("/api/social/sync", headers=admin_headers)
    assert response_admin.status_code == 200
    data = response_admin.json()
    assert data["status"] == "success"
    assert "total_instagram_posts" in data


def test_feed_endpoint_with_synced_posts():
    db = TestingSessionLocal()
    service = SociableKitService()
    service.sync_posts(db, raw_posts=[{
        "id": "feed_post_1",
        "caption": "Noticia destacada UPA",
        "media_url": "https://upa.edu.py/noticia.jpg",
        "permalink": "https://instagram.com/p/feed1",
        "media_type": "IMAGE"
    }])
    db.close()
    
    response = client.get("/api/v1/feed")
    assert response.status_code == 200
    data = response.json()
    assert "urgent_banners" in data
    assert "posts" in data
    assert any(p["instagram_id"] == "feed_post_1" for p in data["posts"])
