import tempfile
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect, text
from src.database import Base, get_alembic_config, run_alembic_migrations
from src.models import (
    AdminAuditLog,
    AppSetting,
    AudienceGroup,
    DeviceToken,
    EventRegistration,
    Post,
    PostView,
    User,
    UserRole,
)


def test_models_metadata_registered():
    """Verify that all tables are properly registered in SQLAlchemy metadata and legacy columns are dropped."""
    tables = Base.metadata.tables
    for expected in (
        "users",
        "posts",
        "event_registrations",
        "post_views",
        "admin_audit_logs",
        "device_tokens",
        "audience_groups",
        "user_roles",
        "app_settings",
    ):
        assert expected in tables

    assert "device_token" not in tables["users"].c
    assert "classroom_deadlines_cache" in tables["users"].c
    assert "classroom_synced_at" in tables["users"].c

    for dropped_post_col in ("reminder_minutes_before", "push_notification_sent_at", "detail_text"):
        assert dropped_post_col not in tables["posts"].c
    assert "reminders" in tables["posts"].c

    for dropped_group_col in ("google_group", "is_system", "badge_class"):
        assert dropped_group_col not in tables["audience_groups"].c
    assert "google_groups" in tables["audience_groups"].c

    assert "role" not in tables["user_roles"].c

    for legacy_prop in ("event_date", "event_end_date", "event_location", "notify_push"):
        assert not hasattr(Post, legacy_prop)


def test_user_model_initialization():
    user = User(email="p.thommen@upa.edu.py", full_name="Pascal Thommen", role="admin", groups=["TIE", "Semester_4"])
    assert user.email == "p.thommen@upa.edu.py"
    assert user.role == "admin"
    assert "TIE" in user.groups


def test_post_model_with_event_and_reminders():
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
        reminders=[30, 1440],
    )
    assert post.title == "Charla de Innovación"
    assert post.is_event is True
    assert post.has_registration is True
    assert post.reminders == [30, 1440]


def test_event_registration_status():
    reg = EventRegistration(post_id=1, user_id=1, status="attending")
    assert reg.status == "attending"


def test_admin_audit_log_structure():
    log = AdminAuditLog(
        admin_id=1,
        action="TRIGGER_PUSH",
        target_type="post",
        target_id=1,
        details={"channel": "web_push", "recipients": 150},
    )
    assert log.action == "TRIGGER_PUSH"
    assert log.details["recipients"] == 150


def test_audience_group_user_role_and_app_setting_models():
    grp = AudienceGroup(id="estudiantes", name="Estudiantes", google_groups=["estudiantes@upa.edu.py"], emails=[])
    role = UserRole(email="admin@upa.edu.py", name="Admin", permissions=["roles", "publicaciones"], is_primary=True)
    setting = AppSetting(key="GEMINI_API_KEY", value="secret")
    dev_tok = DeviceToken(user_id=1, device_token="tok-123", platform="android")
    view = PostView(post_id=1, user_id=1)
    assert grp.id == "estudiantes"
    assert role.is_primary is True
    assert setting.key == "GEMINI_API_KEY"
    assert dev_tok.platform == "android"
    assert view.post_id == 1


def test_alembic_full_upgrade_downgrade_and_data_preservation():
    """Verifica upgrade head, downgrade -1, downgrade base y preservacion de datos en SQLite real."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "alembic_test.db"
        db_url = f"sqlite:///{db_file}"
        cfg = get_alembic_config(db_url)
        eng = create_engine(db_url)

        # 1. Subir hasta 007_add_ai_generated_flag e insertar datos heredados
        command.upgrade(cfg, "007_add_ai_generated_flag")
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, full_name, role, groups, google_groups, device_token) "
                    "VALUES (1, 'ana@upa.edu.py', 'Ana', 'user', '[\"TIE\"]', '[]', 'legacy-fcm-token-99')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO posts (id, title, post_type, is_news, is_event, is_pinned, target_groups, "
                    "has_registration, send_push_notification, reminder_minutes_before, is_edited, is_ai_generated) "
                    "VALUES (10, 'Foro UPA', 'MANUAL', 1, 1, 0, '[\"ALL\"]', 1, 0, 45, 1, 0)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO audience_groups (id, name, badge_class, google_group, emails, is_system) "
                    "VALUES ('tie', 'TIE', 'bg-blue', 'tie@upa.edu.py', '[]', 1)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO user_roles (id, email, name, role, permissions, is_primary) "
                    "VALUES (1, 'ana@upa.edu.py', 'Ana', 'admin', '[\"roles\", \"publicaciones\"]', 1)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO admin_audit_logs (id, admin_id, action, target_type, target_id, details) "
                    "VALUES (1, 1, 'CREATE_EVENT', 'event', 10, '{\"title\": \"Foro UPA\"}')"
                )
            )

        # 2. Upgrade a head (008): migra datos y elimina columnas obsoletas
        command.upgrade(cfg, "head")
        insp = inspect(eng)
        user_cols = {c["name"] for c in insp.get_columns("users")}
        post_cols = {c["name"] for c in insp.get_columns("posts")}
        group_cols = {c["name"] for c in insp.get_columns("audience_groups")}
        role_cols = {c["name"] for c in insp.get_columns("user_roles")}

        assert "device_token" not in user_cols
        assert {"classroom_deadlines_cache", "classroom_synced_at"} <= user_cols
        assert {"reminder_minutes_before", "push_notification_sent_at", "detail_text"}.isdisjoint(post_cols)
        assert {"google_group", "is_system", "badge_class"}.isdisjoint(group_cols)
        assert "role" not in role_cols

        with eng.connect() as conn:
             migrated_tok = conn.execute(
                 text("SELECT device_token FROM device_tokens WHERE user_id = 1")
             ).scalar()
             assert migrated_tok == "legacy-fcm-token-99"

             migrated_rem = conn.execute(text("SELECT reminders FROM posts WHERE id = 10")).scalar()
             assert "45" in str(migrated_rem)

             migrated_gg = conn.execute(
                 text("SELECT google_groups FROM audience_groups WHERE id = 'tie'")
             ).scalar()
             assert "tie@upa.edu.py" in str(migrated_gg)

             migrated_audit = conn.execute(
                 text("SELECT target_type FROM admin_audit_logs WHERE id = 1")
             ).scalar()
             assert migrated_audit == "post"

        # 3. Downgrade -1 (vuelve a 007) y restaura las columnas eliminadas
        command.downgrade(cfg, "-1")
        insp_down = inspect(eng)
        assert "device_token" in {c["name"] for c in insp_down.get_columns("users")}
        assert "reminder_minutes_before" in {c["name"] for c in insp_down.get_columns("posts")}
        assert "google_group" in {c["name"] for c in insp_down.get_columns("audience_groups")}
        assert "role" in {c["name"] for c in insp_down.get_columns("user_roles")}

        # 4. Upgrade de nuevo a head, luego downgrade hasta base y upgrade final
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        assert set(inspect(eng).get_table_names()) <= {"alembic_version"}

        run_alembic_migrations(eng)
        assert {
            "users",
            "posts",
            "event_registrations",
            "post_views",
            "admin_audit_logs",
            "device_tokens",
            "audience_groups",
            "user_roles",
            "app_settings",
        } <= set(inspect(eng).get_table_names())
        eng.dispose()
