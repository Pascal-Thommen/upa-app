# UPA App Backend - API-Dokumentation

Vollständige Schnittstellendokumentation für die mobile Client-Entwicklung (Android / Theresa).
Zero-Mock-Standard: Alle Endpunkte sind produktiv implementiert, typisiert und an PostgreSQL 16 angebunden.

## Basis-URL
* Lokal: `http://localhost:8000`
* Interaktive Swagger-UI: `http://localhost:8000/docs`
* OpenAPI Spezifikation: `http://localhost:8000/openapi.json`

---

## 1. System & Health

### `GET /health`
Prüft den Zustand des Backends und der Datenbankverbindung.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "environment": "development",
  "service": "upa-app-backend"
}
```

---

## 2. Authentifizierung & Profil

### `POST /api/auth/google`
Authentifiziert den Benutzer mit einem Google ID-Token (aus der Android Google Sign-In SDK). Erzwingt die Domänen-Sperre `@upa.edu.py`.

**Request Body:**
```json
{
  "id_token": "eyJhbGciOiJSUzI1NiIs...",
  "classroom_access_token": "ya29.a0AfH6SM..."  // Optional für Classroom-Sync
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "pascal.thommen@upa.edu.py",
    "full_name": "Pascal Thommen",
    "role": "user",
    "groups": ["TIE", "Semester_4"]
  }
}
```

### `GET /api/auth/me`
Liefert das Profil des aktuell authentifizierten Benutzers.
* **Header:** `Authorization: Bearer <access_token>`

**Response (200 OK):**
```json
{
  "id": 1,
  "email": "pascal.thommen@upa.edu.py",
  "full_name": "Pascal Thommen",
  "role": "user",
  "groups": ["TIE", "Semester_4"],
  "created_at": "2026-10-20T14:00:00Z"
}
```

---

## 3. Campus Feed & News

### `GET /api/v1/feed`
Liefert den aggregierten Campus-Feed (Eilmeldungen als oberer Banner und chronologische Beiträge inklusive Instagram @upalemana).

* **Query Parameters:**
  * `group` (optional): Filter nach Studiengang/Gruppe (z. B. `TIE`)
  * `limit` (optional, default: 20): Anzahl der Einträge
  * `offset` (optional, default: 0): Paginierung

**Response (200 OK):**
```json
{
  "urgent_banners": [
    {
      "id": 1,
      "title": "Aviso meteorológico",
      "summary": "Suspensión de actividades presenciales...",
      "content": "Debido al temporal severo...",
      "post_type": "EMERGENCY_BANNER",
      "is_pinned": true,
      "target_groups": ["ALL"],
      "image_url": null,
      "permalink": null,
      "created_at": "2026-10-20T12:00:00Z",
      "published_at": "2026-10-20T12:00:00Z"
    }
  ],
  "posts": [
    {
      "id": 2,
      "title": "📢 ¡Estamos buscando Recepcionista!",
      "summary": "Si sos una persona proactiva y con vocación de atención...",
      "content": "Texto completo del post...",
      "post_type": "INSTAGRAM",
      "is_pinned": false,
      "target_groups": ["ALL"],
      "instagram_id": "DerQoIzjtYf",
      "image_url": "https://data-image.sociablekit.com/sources/instagram-feed/upalemana/DerQoIzjtYf-thumbnail.webp",
      "permalink": "https://www.instagram.com/p/DerQoIzjtYf/",
      "created_at": "2026-10-20T14:00:00Z",
      "published_at": "2026-10-20T14:00:00Z"
    }
  ],
  "total": 51,
  "page": 1,
  "has_more": true
}
```

### `GET /api/news`
Liefert eine Liste aller Campus-News.

* **Query Parameters:** `group`, `limit`, `offset`

---

## 4. Agenda & Kalender-Events

### `GET /api/events`
Liefert alle anstehenden Veranstaltungen und Termine chronologisch sortiert.

* **Query Parameters:**
  * `group` (optional): Filter nach Studiengang (z. B. `TIE`)
  * `from_date` (optional): Startdatum (ISO 8601)

**Response (200 OK):**
```json
[
  {
    "id": 3,
    "title": "¿Qué significa seguir siendo humanos en la era de la IA?",
    "summary": "Charla magistral de Daniel Romero sobre IA en la UPA",
    "event_start": "2026-10-21T18:00:00Z",
    "event_end": "2026-10-21T20:00:00Z",
    "location": "Auditorio Edificio 1",
    "has_registration": true,
    "target_groups": ["ALL", "TIE"],
    "created_at": "2026-10-20T10:00:00Z"
  }
]
```

---

## 5. Google Classroom Integration

### `GET /api/classroom/deadlines`
Liefert die anstehenden Hausaufgaben, Aufgaben und Abgabefristen des eingeloggten Nutzers direkt aus der Google Classroom API.
* **Header:** `Authorization: Bearer <access_token>`

**Response (200 OK):**
```json
{
  "deadlines": [
    {
      "course_id": "12345678",
      "course_name": "Wirtschaftsinformatik II",
      "assignment_id": "87654321",
      "title": "ERP Architektur Fallstudie",
      "description": "Erstellung eines Modells für Auftragsabwicklung...",
      "due_date": "2026-10-25T23:59:00Z",
      "alternate_link": "https://classroom.google.com/c/12345678/a/87654321/details"
    }
  ]
}
```

---

## 6. Social Media Sync

### `POST /api/social/sync`
Triggert die sofortige Synchronisation von Instagram (@upalemana) via SociableKIT (Embed-ID: 25723525).
* **Header:** `Authorization: Bearer <admin_access_token>` (Nur Administratoren)

**Response (200 OK):**
```json
{
  "status": "success",
  "synced_count": 50,
  "created_count": 2,
  "updated_count": 48
}
```

---

## Lokaler Start für Theresa
```bash
# 1. Repository klonen und in den Backend-Ordner wechseln
cd upa-app

# 2. Docker Compose Stack starten (PostgreSQL 16 + FastAPI)
docker compose up -d

# 3. Swagger UI im Browser öffnen
# http://localhost:8000/docs
```
Theresa benötigt keinerlei Dummy-Daten. Die Datenbank wird beim ersten Start automatisch migriert und mit realen Daten befüllt.
