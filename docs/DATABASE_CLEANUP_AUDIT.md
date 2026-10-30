# Prüfbericht zur Datenbank- und Architekturbereinigung (Phase 1 Audit)

Technischer Bestandsaufnahmebericht gemäß dem Zwei-Phasen-Muster für das geplante Datenbank- und Architektur-Refactoring am Mittwoch.  
In dieser ersten Phase erfolgen keine destruktiven Schema- oder Code-Änderungen, um die volle Stabilität für die Live-Präsentation am Samstag zu gewährleisten.

---

## 1. Analyse der Datenbanktabellen und verwaisten Spalten

Die folgende Bestandsaufnahme umfasst sämtliche produktiven Tabellen in `backend/src/models.py` (`posts`, `users`, `audience_groups`, `admin_audit_logs` sowie die zugehörigen Tabellen `user_roles`, `device_tokens`, `event_registrations`, `post_views`, `app_settings`) nach Einführung der Studenten-PWA (`web-app/`), des vereinheitlichten Publikationsmodells (`/api/publications`), der persistenten Classroom-Synchronisation und der multimodalen Google Gemini Flash KI.

### 1.1 Tabellarische Aufstellung zu entfernender bzw. zu konsolidierender Spalten (Phase 2 am Mittwoch)

| Tabelle | Spalte / Eigenschaft | Typ | Status | Konkrete Begründung für die Entfernung am Mittwoch |
|---|---|---|---|---|
| `users` | `device_token` | `VARCHAR(512)` | Redundant (Legacy) | Wurde durch die 1:N-Beziehungstabelle `device_tokens` (Migration `003`) abgelöst, die mehrere Endgeräte (`android`, `ios`, `web`) pro Nutzer unterstützt. Wird aktuell nur noch doppelt in `POST /api/users/device-token` beschrieben und in `collect_recipient_tokens()` / `collect_event_reminder_tokens()` mitgelesen. |
| `posts` | `reminder_minutes_before` | `INTEGER` | Redundant (Legacy) | Wurde in Migration `005` durch das JSON-Array `posts.reminders` (z. B. `[30, 1440]`) ersetzt, damit Veranstaltungen mehrere gestaffelte Erinnerungen unterstützen. `effective_reminders()` nutzt bereits vorrangig `posts.reminders`. |
| `posts` | `push_notification_sent_at` | `TIMESTAMP WITH TIME ZONE` | Ungenutzt (Tot) | Wird im gesamten Backend- und Service-Code (`backend/src/services/push.py`, `backend/src/api/publications.py`, `backend/src/api/news.py`) an keiner Stelle beschrieben oder ausgewertet. |
| `posts` | `detail_text` | `TEXT` | Verwaist im Editor | Im Web-Admin-Cockpit (`web-admin/index.html`, `web-admin/editorial.js`) existiert kein Eingabefeld mehr für `detail_text`; Redakteure pflegen ausschließlich `caption` (Kurztext) und `content` (Haupttext). Das Feld bleibt bei neuen und bearbeiteten Beiträgen stets leer. |
| `posts` | ORM-Aliase `event_date`, `event_end_date`, `event_location`, `notify_push` | `@property` in `Post` | Tote Code-Aliase | Reine Kompatibilitäts-Properties auf dem SQLAlchemy-Modell `Post` (`backend/src/models.py:100-130`), die von keinem produktiven Endpunkt oder Schema mehr aufgerufen werden (nur noch in Alt-Tests unter `backend/tests/test_ai_extractor.py`). |
| `audience_groups` | `google_group` | `VARCHAR(255)` | Redundant (Legacy) | Wurde in Migration `005` durch die JSON-Liste `audience_groups.google_groups` abgelöst, da eine Zielgruppe mehreren Google-Workspace-Verteilern zugeordnet sein kann (z. B. `["estudiantes@upa.edu.py", "tie2025@upa.edu.py"]`). `google_group` speichert redundant nur noch `google_groups[0]`. |
| `audience_groups` | `is_system` | `BOOLEAN` | Veraltet (Obsolet) | Historisches Schutz-Flag. `seed_database()` setzt `is_system` aktiv für alle bestehenden Gruppen auf `False` (`backend/src/seed.py:180-181`), und `backend/src/api/groups.py` wertet das Flag bei `PUT`/`DELETE` nicht mehr aus. |
| `audience_groups` | `badge_class` | `VARCHAR(100)` | Ungenutzt im UI | Tailwind-CSS-Farbklassen-String aus einer früheren UI-Version. Weder die Gruppenverwaltung in `web-admin/app.js` noch die Studenten-PWA in `web-app/campus.js` rendern `badge_class`. |
| `user_roles` | `role` | `VARCHAR(50)` | Redundant (Abgeleitet) | Die Berechtigungsprüfung arbeitet vollständig über die kanonische Modulmatrix `user_roles.permissions` (`["publicaciones", "grupos", "roles", "apis", "historial"]`). Die Rolle (`admin` vs. `editor`) wird in `backend/src/api/roles.py` (`_derive_role`) und `backend/src/api/auth.py` (`_resolve_user_role`) dynamisch daraus abgeleitet, ob `"roles"` in `permissions` enthalten ist. |

### 1.2 Aktive Spalten in `posts`, `users`, `audience_groups` und `admin_audit_logs` (Beibehalten)

* **`posts` (Aktiv):** `id`, `title`, `caption`, `content`, `post_type`, `category`, `is_news`, `is_event`, `is_pinned`, `published_at`, `expires_at`, `event_start`, `event_end`, `location`, `target_groups`, `has_registration`, `send_push_notification`, `reminders`, `notify_groups`, `event_notify_groups`, `link_url`, `link_label`, `is_edited`, `is_ai_generated`, `instagram_id`, `media_type`, `media_url`, `permalink`, `author_id`, `created_at`, `updated_at`.
* **`users` (Aktiv):** `id`, `email`, `full_name`, `role`, `groups`, `google_groups`, `classroom_token`, `classroom_refresh_token`, `classroom_deadlines_cache`, `classroom_synced_at`, `created_at`, `updated_at`.
* **`audience_groups` (Aktiv):** `id`, `name`, `description`, `google_groups`, `emails`, `created_at`, `updated_at`.
* **`admin_audit_logs` (Aktiv):**
  * Alle Spalten (`id`, `admin_id`, `action`, `target_type`, `target_id`, `target_key`, `details`, `created_at`) werden aktiv durch `backend/src/services/audit.py` und `backend/src/api/history.py` genutzt (`target_id` für numerische `post`-Einträge, `target_key` für `group`- und `role`-Einträge).
  * **Datenbereinigung am Mittwoch:** Historische Einträge mit `target_type = 'event'` (aus dem Legacy-Router `/api/events`) werden per Datenmigration auf `target_type = 'post'` vereinheitlicht, sodass die Sonderweiche `POST_TARGET_TYPES = ("post", "event")` in `backend/src/api/history.py:17` entfallen kann.

---

## 2. Prüfung der Alembic-Migrationen und Rollback-Fähigkeit

### 2.1 Bestandsaufnahme aller bestehenden Migrationen (`001` bis `007` in `backend/alembic/versions/`)

| Datei | `revision` | `down_revision` | Inhalt (`upgrade`) | Befund (`downgrade` & Konsistenz) |
|---|---|---|---|---|
| `001_initial_schema.py` | `"001_initial_schema"` | `None` | Erstellt `users`, `posts`, `event_registrations`, `post_views`, `admin_audit_logs` samt Indizes. | **Unvollständig:** `users.google_groups` fehlt in `001` (steht aber in `models.py`). `downgrade()` löscht die 5 Tabellen ohne vorheriges `op.drop_index(...)`. |
| `002_add_classroom_token.py` | `"002_add_classroom_token"` | `"001_initial_schema"` | Fügt `users.classroom_token` hinzu. | Symmetrisch (`op.drop_column("users", "classroom_token")`). |
| `003_add_refresh_and_device_tokens.py` | `"003_add_refresh_and_device_tokens"` | `"002_add_classroom_token"` | Fügt `users.classroom_refresh_token`, `users.device_token` und Tabelle `device_tokens` hinzu. | Symmetrisch (löscht Indizes, Tabelle `device_tokens` und beide Spalten). |
| `004_add_post_category.py` | `"004_add_post_category"` | `"003_add_refresh_and_device_tokens"` | Fügt `posts.category` hinzu. | Symmetrisch (`op.drop_column("posts", "category")`). |
| `005_add_unified_post_fields.py` | `"005_add_unified_post_fields"` | `"004_add_post_category"` | Fügt `published_at`, `reminders`, `notify_groups`, `event_notify_groups`, `detail_text`, `link_url`, `link_label`, `is_edited` zu `posts` hinzu; außerdem `audience_groups.google_groups` und `admin_audit_logs.target_key`. | **Kritischer Fehler:** Setzt voraus, dass die Tabelle `audience_groups` bereits existiert, obwohl `audience_groups` und `user_roles` in keiner der Migrationen `001` bis `004` per `op.create_table` angelegt wurden! Auf einer leeren Datenbank ohne vorheriges `Base.metadata.create_all()` schlägt `alembic upgrade head` bei `005` fehl. |
| `006_add_app_settings.py` | `"006_add_app_settings"` | `"005_add_unified_post_fields"` | Erstellt Tabelle `app_settings`. | Symmetrisch (`op.drop_table("app_settings")`). |
| `007_add_ai_generated_flag.py` | `"007"` | `"006"` | Fügt `posts.is_ai_generated` hinzu. | **Kettenbruch (Broken Revision Chain):** `down_revision = "006"` referenziert eine nicht existierende Revision, da Migration `006` die ID `"006_add_app_settings"` trägt! Zudem weicht das Namensschema (`"007"` statt `"007_add_ai_generated_flag"`) ab. |

### 2.2 Fehlende Tabellen und Spalten in den bisherigen Alembic-Migrationen

Folgende produktive Datenbankstrukturen aus `backend/src/models.py` existieren derzeit **nicht** oder nur unvollständig in `backend/alembic/versions/` und wurden bisher ausschließlich über `Base.metadata.create_all()` bzw. Ad-hoc-DDL erzeugt:
1. **Tabelle `audience_groups`:** Kein `op.create_table("audience_groups", ...)` in `001`–`004` vorhanden (trotz `op.add_column("audience_groups", ...)` in `005`).
2. **Tabelle `user_roles`:** Kein `op.create_table("user_roles", ...)` in irgendeiner Migration vorhanden.
3. **Spalte `users.google_groups` (`JSON`):** In `models.py` definiert, fehlt jedoch in `001_initial_schema.py` und in `_COLUMN_UPGRADES`.
4. **Spalte `users.classroom_deadlines_cache` (`JSON`):** Nur in `_COLUMN_UPGRADES` (`backend/src/database.py:30`) und `ensure_schema_columns` (`backend/src/seed.py:24`), keine Alembic-Migration.
5. **Spalte `users.classroom_synced_at` (`DateTime(timezone=True)`):** Nur in `_COLUMN_UPGRADES` (`backend/src/database.py:31`) und `ensure_schema_columns` (`backend/src/seed.py:26`), keine Alembic-Migration.

### 2.3 Analyse der Ad-hoc-Schema-Upgrades in `backend/src/database.py` und `backend/src/seed.py`

Aktuell existieren zwei redundante Laufzeit-Mechanismen außerhalb von Alembic:
* `backend/src/database.py` (`_COLUMN_UPGRADES` und `ensure_schema_upgrades`, Zeilen 29–67): Führt beim App-Start (`lifespan` in `main.py:59`) manuelle `ALTER TABLE ... ADD COLUMN` Statements für 14 Spalten aus. Dabei werden `users.classroom_synced_at` und `posts.published_at` als `TIMESTAMP` (ohne Zeitzone) statt ` TIMESTAMP WITH TIME ZONE` angelegt, und für `admin_audit_logs.target_key` fehlt der Index `ix_admin_audit_logs_target_key`.
* `backend/src/seed.py` (`ensure_schema_columns`, Zeilen 11–29): Dupliziert `ensure_schema_upgrades(bind_engine)` und führt anschließend nochmals vier eigene `ALTER TABLE users ADD COLUMN ...` Statements für `classroom_refresh_token`, `device_token`, `classroom_deadlines_cache` und `classroom_synced_at` aus.

---

## 3. Code-Sackgassen, ungenutzte Endpunkte und veraltete Schemas

### 3.1 Tote bzw. redundante Backend-Endpunkte

| Endpunkt / Modul | Datei | Befund und Empfehlung für Mittwoch |
|---|---|---|
| `GET /api/news`, `GET /api/news/{post_id}`, `POST /api/news`, `PUT /api/news/{post_id}`, `DELETE /api/news/{post_id}` | `backend/src/api/news.py` | **Legacy-CRUD:** Weder die PWA (`web-app/` nutzt `/api/v1/feed`) noch das Web-Admin-Cockpit (`web-admin/` nutzt `/api/publications`) rufen die CRUD-Routen von `/api/news` auf. Zudem schreibt `POST /api/news` bei normalen Beiträgen keinen Audit-Log-Eintrag und ignoriert neue Felder wie `published_at`, `notify_groups` und `reminders`. **Achtung:** `POST /api/news/sync-instagram` wird aktiv vom Button `Sincronizar Instagram` in `web-admin/editorial-core.js:1073` genutzt und sollte nach `/api/publications/sync-instagram` (mit Alias) überführt werden. |
| `GET /api/events`, `GET /api/events/{event_id}`, `POST /api/events`, `PUT /api/events/{event_id}`, `DELETE /api/events/{event_id}`, `GET /api/events/{event_id}/registrations` | `backend/src/api/events.py` | **Legacy-CRUD:** Das Web-Admin-Cockpit verwaltet Veranstaltungen und Teilnehmerlisten vollständig über `/api/publications` und `/api/publications/{id}/registrations`. Die PWA liest Veranstaltungen über `/api/v1/feed` und `/api/v1/agenda`. **Wichtig (Aktiv in PWA):** `POST /api/events/{event_id}/register` und `DELETE /api/events/{event_id}/register` werden aktiv von `web-app/campus-core.js:132-133` für die 1-Klick-RSVP-Anmeldung aufgerufen und müssen erhalten bleiben (oder gemeinsam mit der PWA auf `/api/publications/{id}/rsvp` konsolidiert werden). |
| `POST /api/v1/feed/sync` | `backend/src/api/feed.py:87-105` | **Doppelter Endpunkt:** Identisch zu `POST /api/news/sync-instagram`, jedoch mit abweichender Berechtigungsprüfung (`require_admin` statt `require_permission("publicaciones")`). Wird von keinem Frontend aufgerufen. |
| `GET /api/auth/groups` | `backend/src/api/auth.py:490-500` | **Ungenutzter Endpunkt:** Wird weder von `web-app/` noch von `web-admin/` aufgerufen, da `google_groups` bereits in `GET /api/auth/me` enthalten ist und das Gruppenmodul `GET /api/groups/google-workspace` verwendet. |
| `GET /api/users/me` | `backend/src/api/users.py:19-29` | **Redundanter Alias:** Exakt identisch zu `GET /api/auth/me`. Sowohl `web-app/` als auch `web-admin/` nutzen ausschließlich `/api/auth/me`. |
| `GET /api/v1/app-state` | `backend/src/main.py:230-315` | **Ungenutzter Cold-Start-Endpunkt:** Wurde ursprünglich für die verworfene native Android-App gebaut. Die produktive PWA (`web-app/`) nutzt stattdessen modular `/api/v1/feed`, `/api/v1/agenda` und `/api/auth/me`. Im Web-Admin (`index.html:672`) wird er nur noch im Texttitel des Diagnose-JSON-Blocks erwähnt. |
| Nicht existierender Endpunkt `/api/classroom/sync` in Diagnose-Metadaten | `backend/src/api/diagnostics.py:91` | `get_system_diagnostics()` listet unter `classroom_api.endpoints` den Pfad `"/api/classroom/sync"` auf, der im Backend überhaupt nicht existiert. |

### 3.2 Veraltete Pydantic-Schemas und Hilfsfunktionen (`backend/src/schemas/`)

| Schema / Symbol | Datei | Befund |
|---|---|---|
| `PostBase`, `PostCreate`, `PostUpdate`, `NewsResponse` | `backend/src/schemas/post.py:108-295` | Werden ausschließlich vom Legacy-Router `backend/src/api/news.py` verwendet. Nach Konsolidierung auf `/api/publications` (`PublicationWrite`, `PublicationUpdate`, `PublicationResponse`) sind diese 4 Schemas obsolet. |
| `EventCreate`, `EventUpdate`, `EventRegistrationsResponse` | `backend/src/schemas/event.py:107-197` | Werden ausschließlich vom Legacy-Router `backend/src/api/events.py` genutzt (`PublicationRegistrationsResponse` in `schemas/publication.py` ersetzt `EventRegistrationsResponse`). `EventResponse` und `EventRegistrationEntry` bleiben aktiv. |
| `AppStateFeedItem`, `AppStateUser`, `AppStateResponse` | `backend/src/schemas/feed.py:179-322` | Werden ausschließlich vom ungenutzten Endpunkt `GET /api/v1/app-state` in `backend/src/main.py` benötigt. |
| `ExtractedEventData`, `GeminiEventSchema` | `backend/src/services/ai_extractor.py:132-133` | Ungenutzte Variablen-Aliase für `AIEventExtractionResult`, die im Produktivcode nirgendwo importiert werden. |

### 3.3 Ungenutzte Frontend-Routen, DOM-Elemente und Funktionen im Web-Admin-Cockpit (`web-admin/`)

1. **Verwaiste Kalender-DOM-Referenzen und Funktionen in `web-admin/app.js`:**
   * `DOM_ELEMENTS.calendarGrid` (`#calendar-grid`), `calMonthTitle` (`#cal-month-title`), `calPrev` (`#cal-prev`), `calNext` (`#cal-next`), `selectedDateLabel` (`#selected-date-label`) in `web-admin/app.js:40-44` sowie `state.currentMonth`, `state.currentYear`, `state.selectedDate` (`app.js:68-70`) und die gesamte Funktion `renderCalendar()` (`app.js:498-543`) sind **toter Code**: In `web-admin/index.html` existieren diese DOM-IDs nicht mehr (der Monatskalender befindet sich in der Studenten-PWA `web-app/`).
2. **Tote Navigations- und Container-Selektoren für `diagnostic`:**
   * `document.getElementById("nav-mod-diagnostic")` in `web-admin/app.js:2217` existiert nicht in `web-admin/index.html`.
   * `<section id="view-diagnostic" class="hidden" aria-hidden="true"></section>` in `web-admin/index.html:750` sowie dessen Umschaltung in `web-admin/app.js:1869` und `web-admin/editorial.js:1152` ist ein leerer Legacy-Container.
   * `<div id="mode-switch" class="hidden">` (`#mode-btn-editorial`, `#mode-btn-student`) in `web-admin/index.html:157-160` ist dauerhaft `hidden` und wird von keinem Benutzer gesehen; die Seitenleiste steuert alle Routen direkt.
3. **Ungenutzte Nginx-SPA-Route `/dashboard/historial`:**
   * In `docs/api_documentation.md:32` ist `/dashboard/historial` als eigene Subroute dokumentiert, in `web-admin/app.js` (`resolveRoute`, Zeilen 1716–1758) existiert jedoch keine Route `historial` (fällt per Redirect auf `/dashboard/publicaciones` zurück, da die Audit-Historie direkt unterhalb der Tabellen in `Publicaciones`, `Grupos` und `Roles` eingebettet ist).
   * Zudem leitet `resolveRoute()` folgende historische Alias-Pfade um, die nach dem Refactoring bereinigt werden können: `/dashboard/noticias`, `/dashboard/eventos`, `/dashboard/groups`, `/dashboard/admins`, `/dashboard/estudiantes`, `/dashboard/students`, `/dashboard/diagnostico`, `/dashboard/diagnostic`, `/dashboard/control`, `/dashboard/ai`, `/dashboard/control-ia`, `/dashboard/control-de-ia`, `/dashboard/inteligencia-artificial`.
   * `UpaRouter.ROUTES.DIAGNOSTICO` und `UpaRouter.ROUTES.ESTUDIANTES` (`web-admin/app.js:1929-1930`) zeigen beide redundant auf `"/dashboard/apis"`.
4. **Tote Legacy-Funktionen in `web-admin/editorial-core.js`:**
   * `validateNewsValues`, `buildNewsPayload`, `newsToFormValues`, `validateEventValues`, `buildEventPayload`, `eventToFormValues`, `renderNewsRows`, `renderEventRows` (`web-admin/editorial-core.js:693-880`) sowie die Client-Methoden `listNews`, `createNews`, `updateNews`, `deleteNews`, `listEvents`, `createEvent`, `updateEvent`, `deleteEvent`, `getEventRegistrations` (`editorial-core.js:1062-1071`) stammen aus der Zeit vor dem vereinheitlichten Editor (`validatePublicationValues`, `buildPublicationPayload`, `renderPublicationRows`) und werden von `web-admin/editorial.js` an keiner Stelle mehr aufgerufen.
5. **Verwaistes Verzeichnis `android/`:**
   * `android/README.md` ist ein Überbleibsel vor der Architekturentscheidung für die plattformübergreifende PWA (`web-app/`).

---

## 4. Migrations- und Rollback-Plan für Phase 2 (Mittwoch)

Für das Refactoring am Mittwoch wird folgendes mehrstufiges Vorgehen mit symmetrischen `upgrade()`- und `downgrade()`-Funktionen definiert:

### Schritt 1: Reparatur der bestehenden Alembic-Revisionskette (`001` bis `007`)
1. **Korrektur von `007_add_ai_generated_flag.py`:**
   * Setzen von `down_revision = "006_add_app_settings"` (Behebung des Kettenbruchs zu Migration `006`).
2. **Idempotente Vervollständigung der Basistabellen in den Migrationen:**
   * Sicherstellen, dass `audience_groups`, `user_roles` und `users.google_groups` sauber in der Migrationskette angelegt werden (mit Existenzprüfung über `sa.inspect(op.get_bind())`, damit sowohl bestehende Produktionsdatenbanken als auch frische Testdatenbanken ohne `create_all()` fehlerfrei durch `alembic upgrade head` und `alembic downgrade base` laufen).
   * Ergänzung expliziter `op.drop_index(...)`-Aufrufe in `001_initial_schema.py` (`downgrade()`).

### Schritt 2: Migration `008_consolidate_schema_and_drop_legacy_columns.py`
Erstellung einer neuen, vollständig reversiblen Alembic-Migration `008` (`Revises: 007`):

* **`upgrade()`:**
  1. **Überführung der Ad-hoc-Spalten in Alembic (falls auf Ziel-DB noch nicht vorhanden):**
     * `users.classroom_deadlines_cache` (`sa.JSON()`, ` nullable=False`, `server_default="[]"`)
     * `users.classroom_synced_at` (`sa.DateTime(timezone=True)`, `nullable=True`)
     * `users.google_groups` (`sa.JSON()`, `nullable=False`, `server_default="[]"`)
  2. **Datenmigration vor Spaltenlöschung (Zero Data Loss):**
     * Übertragung eventuell nur in `users.device_token` gespeicherter Tokens in die Tabelle `device_tokens` (`INSERT INTO device_tokens ... ON CONFLICT DO NOTHING`).
     * Übertragung von `posts.reminder_minutes_before` nach `posts.reminders` (`[reminder_minutes_before]`), sofern `posts.reminders IS NULL` und `is_event = TRUE`.
     * Übertragung von `audience_groups.google_group` in `audience_groups.google_groups`, sofern `google_groups IS NULL` und `google_group IS NOT NULL`.
     * Vereinheitlichung von `admin_audit_logs.target_type = 'event'` auf `'post'`.
  3. **Entfernung der verwaisten und redundanten Spalten (mit `op.batch_alter_table` für volle SQLite- und PostgreSQL-Kompatibilität):**
     * `users`: Drop `device_token`
     * `posts`: Drop `reminder_minutes_before`, `push_notification_sent_at`, `detail_text`
     * `audience_groups`: Drop `google_group`, `is_system`, `badge_class`
     * `user_roles`: Drop `role`

* **`downgrade()` (Vollständig symmetrischer Rollback):**
  1. Wiederherstellung der gelöschten Spalten mit ihren exakten Typen und Default-Werten:
     * `user_roles.role` (`sa.String(length=50)`, `nullable=False`, `server_default="editor"`) und Rückbefüllung (`role = 'admin'` wo `'roles'` in `permissions`, sonst `'editor'`).
     * `audience_groups.badge_class` (`sa.String(length=100)`, `nullable=False`, `server_default="bg-slate-100 text-slate-800 border-slate-200"`), `audience_groups.is_system` (`sa.Boolean()`, `nullable=False`, `server_default=sa.false()`), `audience_groups.google_group` (`sa.String(length=255)`, `nullable=True`).
     * `posts.detail_text` (`sa.Text()`, `nullable=True`), `posts.push_notification_sent_at` (`sa.DateTime(timezone=True)`, `nullable=True`), `posts.reminder_minutes_before` (`sa.Integer()`, `nullable=True`, `server_default="30"`).
     * `users.device_token` (`sa.String(length=512)`, `nullable=True`).

### Schritt 3: Ablösung von `_COLUMN_UPGRADES` und `ensure_schema_columns`
* Entfernung von `_COLUMN_UPGRADES` und `ensure_schema_upgrades()` aus `backend/src/database.py` sowie `ensure_schema_columns()` aus `backend/src/seed.py`.
* Ausführung von Alembic-Migrationen beim Start bzw. im Deployment-Prozess sowie ein automatisierter Pytest-Rollback-Test (`upgrade head` -> `downgrade base` -> `upgrade head`), der die Symmetrie aller Migrationen dauerhaft absichert.

### Schritt 4: Bereinigung toter Code-Pfade am Mittwoch
1. **Backend:**
   * Entfernung der ORM-Properties `event_date`, `event_end_date`, `event_location`, `notify_push` aus `backend/src/models.py`.
   * Konsolidierung von `backend/src/api/news.py`, `backend/src/api/events.py` und `POST /api/v1/feed/sync` zugunsten von `/api/publications` (unter Beibehaltung der von der PWA genutzten RSVP-Routen).
   * Entfernung von `GET /api/auth/groups`, `GET /api/users/me` und `GET /api/v1/app-state` samt `AppState*`-Schemas, `PostCreate`/`PostUpdate`/`NewsResponse` und `EventCreate`/`EventUpdate`.
   * Korrektur der `classroom_api.endpoints`-Liste in `backend/src/api/diagnostics.py`.
2. **Frontend (`web-admin/`):**
   * Entfernung des toten Kalender-Codes (`renderCalendar`, `calendarGrid` etc.), des leeren `#view-diagnostic`-Containers und des versteckten `#mode-switch`-Blocks aus `web-admin/app.js` und `web-admin/index.html`.
   * Entfernung der ungenutzten Legacy-Formularfunktionen (`validateNewsValues`, `buildNewsPayload`, `validateEventValues`, `buildEventPayload`, `renderNewsRows`, `renderEventRows`) aus `web-admin/editorial-core.js` und Anpassung der zugehörigen Unit-Tests in `web-admin/tests/editorial-core.test.js`.
3. **Verifikation:**
   * 100 % grüner Durchlauf von `pytest`, `ruff check`, `npm --prefix web-app/tests test`, `npm --prefix web-admin/tests test` und `python3 scripts/audit_zero_mock.py`.
