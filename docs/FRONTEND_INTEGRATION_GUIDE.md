# Frontend Integrationsleitfaden fuer UPA Campus PWA und Web Admin (UPA App API)

Dieses Dokument beschreibt die technische Architektur und den gesamten REST API Vertrag der UPA Plattform fuer die Progressive Web App der Studierenden (`web-app/`) sowie das administrative Redaktionsportal (`web-admin/`). Alle Endpunkte liefern strikt typisierte JSON Strukturen ohne unerwartete Nullwerte und sind direkt mit PostgreSQL 16 verbunden.

## 1. Basis URLs und OpenAPI 3.1 Spezifikation

* **Oeffentlicher HTTPS Server (Produktion via NetBird):** `https://upa.eu1.netbird.services`
* **Beta HTTPS Server (NetBird):** `https://upa-beta.eu1.netbird.services`
* **Produktions Frontend Container (Host):** `http://localhost:8085`
* **Beta Frontend Container (Host):** `http://localhost:8185`
* **Lokaler FastAPI Backend Dienst:** `http://localhost:8000` (Produktion) bzw. `http://localhost:8100` (Beta)
* **Interaktive Swagger UI Dokumentation:** `/docs` (z.B. `http://localhost:8000/docs`)
* **OpenAPI 3.1 JSON Schema:** `/openapi.json` (z.B. `http://localhost:8000/openapi.json`)

```yaml
openapi: 3.1.0
info:
  title: UPA App API
  version: 1.0.0
  description: Offizielle REST API fuer die UPA Campus PWA und das Web Admin Cockpit.
servers:
  - url: https://upa.eu1.netbird.services
    description: Produktionsumgebung (HTTPS)
  - url: https://upa-beta.eu1.netbird.services
    description: Beta Umgebung (HTTPS)
  - url: http://localhost:8000
    description: Lokale Entwicklungsumgebung
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

## 2. PWA Client Architektur (`web-app/`)

### 2.1 Web App Manifest und TWA Bereitschaft (`web-app/manifest.webmanifest`)

Die Studenten PWA ist fuer Android (Chrome sowie Trusted Web Activity im Google Play Store) und iOS (Safari Homescreen Web App) ausgelegt:

* **Manifest Pfad:** `/manifest.webmanifest` (ausgeliefert durch Nginx mit `Content-Type: application/manifest+json`).
* **Darstellungsmodus:** `display: "standalone"`, `display_override: ["standalone", "minimal-ui"]`, `orientation: "portrait"`, `start_url: "/?source=pwa"`, `scope: "/"`, `lang: "es-PY"`.
* **Icons:** Beinhaltet Standard Icons (`192x192`, `512x512` mit `purpose: "any"`), ein adaptives Maskable Icon (`/campus/icons/icon-maskable-512.png` mit `purpose: "maskable"`), das Apple Touch Icon (`/campus/icons/apple-touch-icon.png`, `180x180`) sowie das Favicon (`/campus/icons/favicon-32.png`, `32x32`).
* **Trusted Web Activity (TWA):** Unter `/.well-known/assetlinks.json` (`web-app/.well-known/assetlinks.json`) stellt Nginx die Digital Asset Links bereit.
* **Safe Area und Theme Steuerung:** `web-app/index.html` nutzt `viewport-fit=cover` und `web-app/campus.css` beruecksichtigt `env(safe-area-inset-top)` sowie `env(safe-area-inset-bottom)`. Der 3 Wege Theme Umschalter (`system`, `light`, `dark`) aktualisiert `data-theme` und `<meta name="theme-color">` synchron.

### 2.2 Service Worker Caching und Offline Resilienz (`web-app/sw.js`)

Der unter `/sw.js` mit dem Header `Service-Worker-Allowed: "/"` ausgelieferte Service Worker trennt strikt zwischen statischem App Shell Caching und privaten Sitzungsdaten:

1. **App Shell Precache (`upa-campus-shell-1.0.0`):** Beim `install` Event werden `/`, `/manifest.webmanifest`, `/campus/campus.css?v=1.0.0`, `/campus/campus-core.js?v=1.0.0`, `/campus/vendor/qrcode.js?v=1.0.0`, `/campus/campus.js?v=1.0.0` und alle Icons im Cache abgelegt.
2. **Navigationsanfragen (`/` und `/index.html`):** Nutzen eine Network First Strategie mit automatischem Fallback auf die gecachte App Shell bei fehlender Internetverbindung.
3. **Statische PWA Assets (`/campus/*` und `/manifest.webmanifest`):** Nutzen Cache First mit Hintergrundaktualisierung (Stale While Revalidate).
4. **Strikter Ausschluss privater API Pfade:** Alle Anfragen unter `/api/*` und `/dashboard*` werden im Service Worker niemals zwischengespeichert.
5. **Nutzerspezifischer Applikationscache (`web-app/campus-core.js`):** `createCache(localStorage, "upa_campus_cache_")` speichert Feed und Agenda lokal fuer sofortiges Offline Lesen und loescht diese Eintraege beim Logout (`cache.clear()`) restlos.

### 2.3 Desktop QR Code Landingpage und Mobile Erkennung

`isMobileEnvironment(env)` in `web-app/campus-core.js` entscheidet beim Start:

* **Desktop Browser:** Zeigt die Landingpage (`#landing`) mit Smartphone Vorschau (`phone-mockup`), dynamisch berechnetem SVG QR Code (`buildQr` auf Basis der aktuellen URL), Direktlink zur Web Vorschau (`/?app=1` mit Rueckkehrleiste `Volver al código QR`) und dezentem Link `Acceso Administrativo` (`/dashboard/`).
* **Mobilgeraete, Standalone PWA oder `/?app=1`:** Startet direkt die mobile App Ansicht (`#app`) mit den drei Bereichen `Inicio`, `Agenda` und `Perfil`.

## 3. Authentifizierung und PWA Session Management ueber JWT

### 3.1 Web und PWA OAuth 2.0 Redirect Flow (`GET /api/auth/login-google`)

Die PWA und das Web Admin Cockpit nutzen den serverseitigen Google OAuth 2.0 Authorization Code Flow mit `access_type=offline`, Domain Beschraenkung `hd=upa.edu.py` und den Classroom Scopes (`classroom.courses.readonly`, `classroom.coursework.me.readonly`):

* **PWA Login Aufruf:** `GET /api/auth/login-google?return_to=campus` setzt `state=campus`.
* **OAuth Callback (`GET /api/auth/google`):** Tauscht den Autorisierungscode gegen Google Tokens aus, speichert `classroom_token` sowie `classroom_refresh_token` in PostgreSQL und leitet bei `state=campus` mit dem signierten JWT im URL Fragment an die PWA zurueck:
  * Erfolg: `/#token=<jwt_access_token>`
  * Fehler: `/#auth_error=<error_code>` (z.B. `forbidden_domain`, `access_denied`, `token_exchange_failed`)
* **Token Uebernahme in der PWA (`parseAuthFragment`):** `web-app/campus.js` liest das Fragment beim Start aus, entfernt den Hash sofort per `history.replaceState(null, "", location.pathname + location.search)` aus der Adresszeile, prueft die Gueltigkeit mit `isTokenExpired(token)` und speichert das Token unter `upa_campus_token` in `localStorage`.

### 3.2 Direkter Login mit Google ID Token (`POST /api/auth/google`)

Der Endpunkt `POST /api/auth/google` validiert ein Google ID Token kryptografisch fuer Konten der Domain `@upa.edu.py`, synchronisiert Google Workspace Gruppen und gibt `AuthResponse` zurueck.

**Anfrage (`POST /api/auth/google`):**
```http
POST /api/auth/google HTTP/1.1
Content-Type: application/json

{
  "id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjEifQ...",
  "classroom_token": "ya29.a0AfH6SM...",
  "classroom_refresh_token": "1//0gSampleRefreshToken..."
}
```

**Erfolgreiche Antwort (`200 OK`):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZW1haWwiOiJwYXNjYWwudGhvbW1lbkB1cGEuZWR1LnB5Iiwicm9sZSI6ImFkbWluIiwiZXhwIjoxNzYxNzU2MDAwfQ.signature",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "pascal.thommen@upa.edu.py",
    "full_name": "Pascal Thommen",
    "role": "admin",
    "groups": [
      "Semester_4",
      "Estudiantes TIE 2025"
    ],
    "google_groups": [
      {
        "id": "01abc234def",
        "name": "Estudiantes TIE",
        "email": "estudiantes.tie@upa.edu.py",
        "description": "Grupo institucional de Ingenieria Empresarial"
      }
    ],
    "has_classroom_token": true,
    "permissions": [
      "publicaciones",
      "grupos",
      "roles",
      "apis",
      "historial"
    ]
  }
}
```

### 3.3 Verwendung von `Authorization: Bearer <token>` im PWA API Client

Jeder geschuetzte Aufruf sendet das JWT im HTTP Header `Authorization: Bearer <access_token>`:

```http
Authorization: Bearer <access_token>
```

#### Beispiel mit `curl`:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/google \
  -H "Content-Type: application/json" \
  -d '{"id_token": "<GOOGLE_ID_TOKEN>"}' | jq -r '.access_token')

curl -X GET http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json"
```

#### Beispiel im PWA Client (`web-app/campus-core.js`):
```javascript
const api = UpaCampusCore.createApi({
  baseUrl: "",
  timeoutMs: 12000,
  getToken: () => localStorage.getItem("upa_campus_token"),
  onUnauthorized: () => {
    localStorage.removeItem("upa_campus_token");
  },
});

const feedData = await api.feed({ limit: 20, offset: 0 });
const agendaData = await api.agenda();
```

## 4. Mobile PWA und Backend Endpunkte im Detail

### 4.1 Konsolidierter App Startstatus (`GET /api/v1/app-state`)

Liefert in einem einzigen Aufruf den Sitzungsstatus, den Feed (`feed`), die kommenden Veranstaltungen (`upcoming_events`) und die anstehenden Google Classroom Abgabefristen (`upcoming_deadlines`).

* **Authentifizierung:** Optional (`Authorization: Bearer <token>`).
  * **Ohne Token:** `authenticated` ist `false`, `user` ist `null`, `feed` enthaelt ausschliesslich oeffentliche Instagram Beitraege fuer `ALL`, und `upcoming_events` sowie `upcoming_deadlines` sind `[]`.
  * **Mit Token:** `authenticated` ist `true`, `user` enthaelt das Benutzerprofil, `feed` liefert zielgruppengefilterte Beitraege, `upcoming_events` enthaelt den Anmeldestatus (`is_registered`, `registered_count`) und `upcoming_deadlines` liefert die synchronisierten Classroom Aufgaben.
* **Optionale Query Parameter:** `group` (z.B. `TIE`), `limit` (1 bis 100, Standard `20`).

**Antwort (`200 OK`):**
```json
{
  "portal": "UPA Mobile Campus Platform",
  "api_version": "1.0.0",
  "authenticated": true,
  "user": {
    "id": 3,
    "email": "estudiante@upa.edu.py",
    "full_name": "Estudiante UPA",
    "role": "user",
    "groups": [],
    "google_groups": [],
    "has_classroom_token": true
  },
  "feed": [
    {
      "id": 2,
      "title": "Foro de Ingenieria 2026",
      "summary": "Conferencia magistral en el campus",
      "content": "Inteligencia artificial, decisiones y liderazgo tecnologico.",
      "post_type": "MANUAL",
      "is_pinned": true,
      "target_groups": ["ALL", "TIE"],
      "image_url": "",
      "permalink": "",
      "published_at": "2026-10-30T10:00:00+00:00"
    }
  ],
  "upcoming_events": [
    {
      "id": 2,
      "title": "Foro de Ingenieria 2026",
      "description": "Inteligencia artificial, decisiones y liderazgo tecnologico.",
      "summary": "Conferencia magistral en el campus",
      "event_start": "2026-11-05T14:00:00Z",
      "event_end": "2026-11-05T16:00:00Z",
      "location": "Auditorio UPA",
      "has_registration": true,
      "is_pinned": true,
      "target_groups": ["ALL", "TIE"],
      "image_url": "",
      "permalink": "",
      "created_at": "2026-10-30T10:00:00Z",
      "is_registered": true,
      "registered_count": 15
    }
  ],
  "upcoming_deadlines": [
    {
      "id": "654321098",
      "assignment_id": "654321098",
      "course_id": "123456789",
      "course": "Ingenieria de Software II",
      "course_name": "Ingenieria de Software II",
      "title": "Entrega de Arquitectura PWA",
      "description": "Documentacion OpenAPI y pruebas extremo a extremo.",
      "due_date": {"year": 2026, "month": 11, "day": 6},
      "due_time": {"hours": 23, "minutes": 59},
      "due_date_formatted": "2026-11-06 23:59",
      "alternate_link": "https://classroom.google.com/c/123456789/a/654321098/details",
      "max_points": 100.0
    }
  ]
}
```

### 4.2 Hybrider Campus Feed (`GET /api/v1/feed`)

Hauptendpunkt der PWA Ansicht `Inicio`. Liefert dringende Eilmeldungen (`urgent_banners` vom Typ `EMERGENCY_BANNER`) getrennt von den regulaeren Feed Beitraegen (`posts`). Jeder Beitrag enthaelt auch `is_registered`, `registered_count`, `media_url`, `media_type`, `link_url` und `link_label`.

* **Header (Optional):** `Authorization: Bearer <token>`
* **Query Parameter:** `group`, `limit` (Standard `20`), `offset` (Standard `0`).

### 4.3 Konsolidierte Agenda (`GET /api/v1/agenda`)

Hauptendpunkt der PWA Ansicht `Agenda`. Kombiniert Hochschulveranstaltungen (`events`) und persönliche Google Classroom Aufgaben (`deadlines`) sowie eine chronologisch nach `America/Asuncion` sortierte Gesamtliste (`items`).

* **Header (Optional):** `Authorization: Bearer <token>`
* **Query Parameter:** `group`, `upcoming_only` (Standard `true`), `limit` (1 bis 200, Standard `50`).

**Antwort (`200 OK`):**
```json
{
  "events": [
    {
      "id": 2,
      "title": "Foro de Ingenieria 2026",
      "description": "Inteligencia artificial, decisiones y liderazgo tecnologico.",
      "summary": "Conferencia magistral en el campus",
      "event_start": "2026-11-05T14:00:00Z",
      "event_end": "2026-11-05T16:00:00Z",
      "location": "Auditorio UPA",
      "has_registration": true,
      "is_pinned": true,
      "target_groups": ["ALL", "TIE"],
      "image_url": "",
      "permalink": "",
      "created_at": "2026-10-30T10:00:00Z",
      "is_registered": true,
      "registered_count": 1
    }
  ],
  "deadlines": [
    {
      "id": "654321098",
      "assignment_id": "654321098",
      "course_id": "123456789",
      "course": "Ingenieria de Software II",
      "course_name": "Ingenieria de Software II",
      "title": "Entrega de Arquitectura PWA",
      "description": "Documentacion OpenAPI y pruebas extremo a extremo.",
      "due_date": {"year": 2026, "month": 11, "day": 6},
      "due_time": {"hours": 23, "minutes": 59},
      "due_date_formatted": "2026-11-06 23:59",
      "alternate_link": "https://classroom.google.com/c/123456789/a/654321098/details",
      "max_points": 100.0
    }
  ],
  "items": [
    {
      "item_type": "EVENT",
      "id": "2",
      "title": "Foro de Ingenieria 2026",
      "description": "Inteligencia artificial, decisiones y liderazgo tecnologico.",
      "timestamp": "2026-11-05T14:00:00+00:00",
      "sort_key": "2026-11-05 11:00",
      "location_or_course": "Auditorio UPA",
      "link": "",
      "is_registered": true,
      "registered_count": 1
    },
    {
      "item_type": "DEADLINE",
      "id": "654321098",
      "title": "Entrega de Arquitectura PWA",
      "description": "Documentacion OpenAPI y pruebas extremo a extremo.",
      "timestamp": "2026-11-06 23:59",
      "sort_key": "2026-11-06 23:59",
      "location_or_course": "Ingenieria de Software II",
      "link": "https://classroom.google.com/c/123456789/a/654321098/details",
      "is_registered": false,
      "registered_count": 0
    }
  ]
}
```

### 4.4 Benutzerprofil und Datenschutzfilter (`GET /api/auth/me` und `GET /api/users/me`)

Gibt das Profil des authentifizierten Nutzers anhand des JWT zurueck.
* **Pflicht Header:** `Authorization: Bearer <token>`
* **Strikte Datenschutzregel:** Fuer regulaere Studierende (`role != "admin"`) gibt der Server fuer `groups` und `google_groups` ausnahmslos leere Arrays `[]` zurueck, damit keine internen Verteilerlisten offengelegt werden.

### 4.5 Google Classroom Synchronisation, Auto Refresh und DB Fallback (`GET /api/classroom/deadlines`, `GET /api/classroom/courses`, `POST /api/auth/classroom-token`)

Synchronisiert die aktiven Kurse und Abgabefristen des Studierenden aus Google Classroom:

* **Pflicht Header:** `Authorization: Bearer <token>`
* **Transparenter OAuth Token Auto Refresh:** Die Tabelle `users` speichert `classroom_refresh_token`. Antwortet Google Classroom mit `HTTP 401`, erneuert das Backend das Access Token automatisch ueber `https://oauth2.googleapis.com/token` (`grant_type=refresh_token`), speichert das neue Token in PostgreSQL und setzt den Response Header `X-Classroom-Token-Refreshed: true`.
* **Persistenter Datenbank Fallback (`classroom_deadlines_cache`):** Erfolgreich abgerufene Fristen werden im Benutzerdatensatz in PostgreSQL persistiert (`classroom_deadlines_cache`, `classroom_synced_at`). Bei Google API Timeouts (`> 5s`), Rate Limits oder temporären Netzfehlern liefert der Endpunkt nahtlos die zuletzt gespeicherten Fristen aus (`X-Classroom-Cache: db_fallback`), sodass die Agenda in der PWA niemals leer laeuft.
* **Zeitzonen Normalisierung (`America/Asuncion`):** Von Google in UTC gelieferte `dueTime` Werte werden exakt auf die lokale Campus Zeitzone `America/Asuncion` umgerechnet, damit die Tageszuordnung im Kalender stimmt.
* **Manuelle Token Aktualisierung (`POST /api/auth/classroom-token`):**
```json
{
  "classroom_token": "ya29.a0AfH6SM_token_oauth_classroom",
  "classroom_refresh_token": "1//0gRefreshTokenOpcionalParaAutoRefresh"
}
```

### 4.6 Veranstaltungen und 1 Klick RSVP (`GET /api/events`, `POST /api/events/{event_id}/register`, `DELETE /api/events/{event_id}/register`, `PUT /api/events/{event_id}`, `DELETE /api/events/{event_id}`)

* **`GET /api/events` und `GET /api/events/{event_id}`:** Listet Veranstaltungen chronologisch nach `event_start` inklusive `is_registered` und `registered_count`.
* **`POST /api/events/{event_id}/register`:** Meldet den authentifizierten Nutzer idempotent fuer das Event in `event_registrations` an (`status = "attending"`) und gibt das aktualisierte `EventResponse` (`is_registered: true`) zurueck.
* **`DELETE /api/events/{event_id}/register`:** Storniert die Anmeldung des Nutzers und gibt `EventResponse` (`is_registered: false`) zurueck.
* **`PUT /api/events/{event_id}` (Redaktion/Admin):** Aktualisiert ein bestehendes Event (`200 OK`).
* **`DELETE /api/events/{event_id}` (Redaktion/Admin):** Loescht ein Event samt Anmeldungen (`200 OK`).

### 4.7 Campus News (`GET /api/news`, `POST /api/news`, `PUT /api/news/{post_id}`, `DELETE /api/news/{post_id}`)

* **`GET /api/news` und `GET /api/news/{post_id}`:** Liefert aktive Campus Mitteilungen gefiltert nach Nutzerberechtigung und Zielgruppe (`Authorization: Bearer <token>`).
* **`POST /api/news` (Redaktion/Admin):** Erstellt eine neue Mitteilung (`201 Created`).
* **`PUT /api/news/{post_id}` (Redaktion/Admin):** Aktualisiert eine Mitteilung und schreibt einen Audit Eintrag (`200 OK`).
* **`DELETE /api/news/{post_id}` (Redaktion/Admin):** Loescht eine Mitteilung (`200 OK`).

**Beispiel Aktualisierung (`PUT /api/news/{post_id}`):**
```json
{
  "title": "Convocatoria de Becas de Investigacion UPA 2026",
  "caption": "Postulaciones abiertas hasta el 15 de noviembre.",
  "content": "Los estudiantes de ingenieria pueden presentar sus proyectos en secretaria academica.",
  "is_pinned": true,
  "target_groups": ["ALL", "TIE"]
}
```

**Beispiel Loeschung (`DELETE /api/news/{post_id}`):**
```json
{
  "status": "deleted",
  "id": 1,
  "detail": "Publicacion de noticias eliminada correctamente."
}
```

### 4.8 Vereinheitlichte Publikationen und KI Autocomplete (`/api/publications`)

Das Web Admin Cockpit verwaltet Beitraege zentral ueber `/api/publications`:

* **`GET /api/publications` und `GET /api/publications/{publication_id}`:** Listet alle Publikationen inklusive Aufrufzaehler (`views_count`) und RSVP Statistik (`attending_count`, `declined_count`) sowie das Flag `is_ai_generated`.
* **`POST /api/publications` und `PUT /api/publications/{publication_id}`:** Erstellt oder aktualisiert eine Publikation. Wenn `is_pinned = true` gesetzt ist, ist `expires_at` verpflichtend.
* **`DELETE /api/publications/{publication_id}`:** Loescht eine Publikation.
* **`POST /api/publications/{publication_id}/rsvp` und `POST /api/publications/{publication_id}/view`:** Erfasst Teilnahmestatus (`attending` oder `declined`) bzw. eindeutige Beitragsansichten pro Nutzer.
* **`POST /api/publications/autocomplete-ai`:** Multimodaler KI Endpunkt (Google Gemini Flash) fuer den Button `Autocompletar con IA` im Editor. Nimmt aktuelle Formulardaten (als JSON oder `multipart/form-data` inklusive Bilddatei) entgegen und liefert Vorschlaege ausschliesslich fuer noch leere Formularfelder (`title`, `caption`, `content`, `is_event`, `event_start`, `event_end`, `location`, `target_groups`, `category`, `has_registration`, `link_label`, `link_url`), ohne bereits vom Redakteur ausgefuellte Felder zu ueberschreiben.

### 4.9 KI Steuerung im Web Admin (`GET /api/ai/config`, `POST /api/ai/config`, `POST /api/ai/test-connection`)

* **`GET /api/ai/config`:** Liefert den Status des Google Gemini API Schluessels (`configured`, `masked_key`, `source`, `model`).
* **`POST /api/ai/config` (Nur Admin):** Speichert einen neuen Gemini API Schluessel persistent in der Tabelle `app_settings`.
* **`POST /api/ai/test-connection` (Nur Admin):** Fuehrt einen Live Verbindungstest gegen Google Gemini aus und liefert Klartext Rueckmeldungen (`OK`, `NO_KEY`, `INVALID_KEY`, `QUOTA`, `TIMEOUT`, `NETWORK`).

### 4.10 Push Token Registrierung und Eilmeldungen (`POST /api/users/device-token`)

Registriert ein FCM Token (`platform`: `android`, `ios` oder `web`) fuer den angemeldeten Nutzer:

**Anfrage (`POST /api/users/device-token`):**
```json
{
  "device_token": "fcm_token_web_d8a92b3c4e5f6a7b8c9d0e1f2a3b4c5d",
  "platform": "web"
}
```

**Antwort (`200 OK`):**
```json
{
  "user_id": 1,
  "device_token": "fcm_token_web_d8a92b3c4e5f6a7b8c9d0e1f2a3b4c5d",
  "platform": "web",
  "has_device_token": true,
  "updated_at": "2026-10-30T17:00:00Z"
}
```

Beim Veröffentlichen einer Eilmeldung (`EMERGENCY_BANNER`) oder aktivierter Push Benachrichtigung versendet das Backend asynchron FCM Benachrichtigungen an alle registrierten Endgeraete der adressierten Zielgruppen.

### 4.11 Mediendateien hochladen und abrufen (`POST /api/media/upload`, `GET /uploads/{filename}`)

* **`POST /api/media/upload` (Redaktion/Admin):** Akzeptiert `multipart/form-data` (Feld `file`) fuer `JPG`, `PNG`, `WEBP`, `MP4`, `WEBM` und `PDF` bis 10 MB. Prueft den echten Dateiinhalt per Magic Bytes und vergibt kollisionsfreie UUID Dateinamen.
* **`GET /uploads/{filename}` (Oeffentlich):** Liefert hochgeladene Medien mit `Cache-Control: public, max-age=31536000, immutable` und `X-Content-Type-Options: nosniff` aus.

## 5. Standardisierte HTTP Fehlerbehandlung

Alle Fehlerantworten liefern ein JSON Objekt mit dem Schluessel `detail`:

```json
{
  "detail": "Klare Beschreibung der Fehlerursache"
}
```

| HTTP Status | Ursache | Beispiel fuer `detail` |
|---|---|---|
| `400 Bad Request` | Ungueltige Nutzdaten, leere Pflichtfelder, fehlendes `expires_at` bei `is_pinned` oder fehlender KI Key | `"El token de dispositivo (device_token) es invalido o esta vacio."` |
| `401 Unauthorized` | Fehlender `Authorization` Header, abgelaufenes oder ungueltiges JWT | `"Autenticacion requerida (Bearer Token ausente)"` |
| `403 Forbidden` | E-Mail ausserhalb `@upa.edu.py` oder fehlende Modulberechtigung | `"Acceso denegado: Se requieren permisos de administrador (Administrator-Rechte erforderlich)"` |
| `404 Not Found` | Angeforderte Ressource existiert nicht oder ist abgelaufen | `"Evento no encontrado."` |
| `422 Unprocessable Entity` | Ungueltige Query Parameter oder Schema Validierungsfehler | Strukturierte Pydantic Validierungsdetails |
| `502 Bad Gateway` | Upstream Fehler oder Timeout bei KI Autocomplete Anfrage | `"No se pudo autocompletar: Verifique la clave de IA en Control de IA (tiempo de espera agotado)."` |
| `503 Service Unavailable` | Timeout bei externer Google OAuth Validierung oder fehlende OAuth Client ID | `"Tiempo de espera agotado al verificar el token con Google OAuth."` |

## 6. Typgarantien fuer PWA und Web Admin Clients

1. **Keine unerwarteten Nullwerte:** In `/api/v1/app-state`, `/api/v1/agenda`, `/api/v1/feed`, `/api/auth/me`, `/api/news`, `/api/events`, `/api/classroom/deadlines` und `/api/users/device-token` liefern Textfelder, Booleans, Zahlen und Listen stets definierte Standardwerte (`""`, `false`, `0`, `0.0`, `[]`).
2. **UTC Zeitstempel nach ISO 8601:** Alle Datumsfelder (`created_at`, `published_at`, `expires_at`, `event_start`, `event_end`, `updated_at`) sind in UTC (`Z` bzw. `+00:00`) serialisiert; die Anzeige in der PWA erfolgt in `America/Asuncion`.
3. **Abwaertskompatible Feldnamen:**
   * In `/api/events`: sowohl `description` als auch `summary`, inklusive `is_registered` und `registered_count`.
   * In `/api/news`: sowohl `image_url` als auch `media_url` sowie `summary` und `caption`.
   * In `/api/classroom/deadlines`: sowohl `id` als auch `assignment_id` sowie `course` und `course_name`.
