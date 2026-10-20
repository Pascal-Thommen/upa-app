from src.database import Base
from src.models import User, Post, EventRegistration, PostView, AdminAuditLog

def test_models_metadata_registered():
    """Verify that all tables are properly registered in SQLAlchemy metadata."""
    tables = Base.metadata.tables
    assert "users" in tables
    assert "posts" in tables
    assert "event_registrations" in tables
    assert "post_views" in tables
    assert "admin_audit_logs" in tables

def test_user_model_initialization():
    user = User(
        email="p.thommen@upa.edu.py",
        full_name="Pascal Thommen",
        role="admin",
        groups=["TIE", "Semester_4"]
    )
    assert user.email == "p.thommen@upa.edu.py"
    assert user.role == "admin"
    assert "TIE" in user.groups

def test_post_model_with_event_and_reminder():
    post = Post(
        title="Charla de Innovación",
        caption="Acompáñanos este viernes",
        content="Contenido completo del evento en el auditorio.",
        post_type="INSTAGRAM",
        is_news=True,
        is_event=True,
        is_pinned=True,
        location="Campus Aula Magna",
        target_groups=["ALL"],
        has_registration=True,
        send_push_notification=True,
        reminder_minutes_before=30
    )
    assert post.title == "Charla de Innovación"
    assert post.is_event is True
    assert post.has_registration is True
    assert post.reminder_minutes_before == 30

def test_event_registration_status():
    reg = EventRegistration(
        post_id=1,
        user_id=1,
        status="attending"
    )
    assert reg.status == "attending"

def test_admin_audit_log_structure():
    log = AdminAuditLog(
        admin_id=1,
        action="TRIGGER_PUSH",
        target_type="post",
        target_id=1,
        details={"channel": "web_push", "recipients": 150}
    )
    assert log.action == "TRIGGER_PUSH"
    assert log.details["recipients"] == 150
