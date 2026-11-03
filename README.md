# UPA App: Campus Portal und Progressive Web App (PWA)

Zentrale Hochschulplattform fuer Studierende, Dozierende und das Redaktionsteam der Universidad Paraguayo Alemana (UPA). Das System kombiniert eine responsive Studenten PWA (Mobile First fuer Android und iOS, Trusted Web Activity Ready) inklusive Desktop QR Code Landingpage mit einem Web Admin Redaktionsportal und einem FastAPI REST Backend mit multimodaler Google Gemini KI Integration.

## Systemarchitektur

Die Plattform laeuft in drei isolierten Docker Containern (`upa-postgres`, `upa-backend`, `upa-frontend` auf Produktion Port `8085` unter `https://upa.eu1.netbird.services` bzw. `upa-postgres-beta`, `upa-backend-beta`, `upa-frontend-beta` auf Beta Port `8185` unter `https://upa-beta.eu1.netbird.services`):

1. **Nginx Frontend Container (`web-admin/Dockerfile`, `web-admin/nginx.conf`):**
   * Liefert unter `/` die **UPA Campus PWA** (`web-app/`) aus. Auf Desktop Browsern erscheint automatisch die Landingpage mit Smartphone Vorschau, dynamischem QR Code zum direkten Oeffnen auf dem Mobilgeraet und dezentem Link zum Administrationsbereich (`Acceso Administrativo`). Auf Mobilgeraeten startet unmittelbar die App Oberflaeche.
   * Stellt den Service Worker (`/sw.js`, Version `1.0.3`), das Web App Manifest (`/manifest.webmanifest`), die Digital Asset Links fuer Android TWA (`/.well-known/assetlinks.json`) und die statischen PWA Assets (`/campus/`) bereit.
   * Liefert unter `/dashboard/` das **Web Admin Cockpit** (`web-admin/`) inklusive SPA Deep Linking (`/dashboard/publicaciones`, `/dashboard/publicaciones/nueva`, `/dashboard/publicaciones/:id`, `/dashboard/grupos`, `/dashboard/roles`, `/dashboard/ia`, `/dashboard/apis`) fuer Redaktion, Gruppenverwaltung, Rollenmatrix, KI Konfiguration und Systemdiagnose aus.
   * Fungiert als Reverse Proxy fuer `/api/`, `/uploads/`, `/health`, `/docs` und `/openapi.json` an den FastAPI Backend Container (`http://backend:8000`).

2. **FastAPI Backend Container (`backend/`):**
   * Stellt alle produktiven REST Endpunkte (`/api/v1/feed` bzw. `/api/feed`, `/api/v1/agenda`, `/api/publications`, `/api/events/{event_id}/register`, `/api/groups`, `/api/roles`, `/api/ai`, `/api/history`, `/api/media/upload`, `/api/system/diagnostics`) sowie die interaktive OpenAPI 3.1 Spezifikation unter `/docs` und `/openapi.json` bereit.
   * Verifiziert die institutionelle Anmeldung ueber Google OAuth 2.0 (`@upa.edu.py`), signiert JWT Sitzungstokens (`HS256`) und synchronisiert Google Workspace Gruppen sowie Google Classroom Kurse und Abgabefristen (inklusive automatischem Token Refresh und persistentem Datenbank Fallback in der Zeitzone `America/Asuncion`).
   * Integriert Google Gemini Flash fuer die multimodale KI Event Extraktion aus Instagram Beitraegen (`backend/src/services/ai_extractor.py`) und fuer das intelligente Formular Autocomplete im Redaktionseditor (`POST /api/publications/autocomplete-ai`).

3. **PostgreSQL 16 Datenbank Container (`postgres:16-alpine`):**
   * Zentrale relationale Datenhaltung (Single Source of Truth) fuer Publikationen, Events, RSVP Teilnahmen (`attending` / `declined`), eindeutige Beitragsaufrufe, Zielgruppen, Berechtigungsrollen, Audit Historie, gespeicherte Classroom Fristen und globale Systemeinstellungen.
   * Aus Sicherheitsgruenden ausschliesslich lokal an `127.0.0.1` gebunden (`127.0.0.1:5432:5432` in Produktion, `127.0.0.1:5433:5432` in Beta).

## Projektstruktur

```text
upa-app/
├── web-app/                    # Studenten PWA (Mobile First, Android, iOS Safari, TWA Ready)
│   ├── index.html              # App Shell und Desktop QR Code Landingpage
│   ├── campus.css              # Responsive Styles, Safe Area Insets und 3 Wege Theme System
│   ├── campus-core.js          # API Client mit Timeout, Session Logik, Cache und QR Generator
│   ├── campus.js               # UI Controller fuer Inicio, Agenda, Perfil und Vollbild Detail
│   ├── sw.js                   # Service Worker (v1.0.3) fuer Offline Shell Precache
│   ├── manifest.webmanifest    # PWA Manifest (standalone, maskable Icons)
│   ├── .well-known/            # Digital Asset Links (assetlinks.json) fuer Android TWA
│   └── tests/                  # Automatisierte Unit und DOM End to End Tests (Node.js)
├── web-admin/                  # Administrations und Redaktionsportal (Desktop SPA)
│   ├── index.html              # Cockpit Oberflaeche (Publicaciones, Grupos, Roles, Control de IA, APIs, Historial)
│   ├── app.js                  # SPA Router (inkl. Deep Linking /dashboard/publicaciones/:id), OAuth, Gruppen, Rollen, KI und Diagnose
│   ├── editorial-core.js       # Formularvalidierung, Payload Aufbau und REST Client
│   ├── editorial.js            # Editor Controller inkl. Autocompletar con IA und Instagram Schreibschutz
│   ├── nginx.conf              # Produktive Nginx Routing und Proxy Konfiguration
│   ├── Dockerfile              # Multi Asset Image fuer web-admin und web-app (/campus/)
│   └── tests/                  # Automatisierte Frontend Tests (Node.js)
├── backend/                    # Python FastAPI REST Service
│   ├── src/
│   │   ├── main.py             # FastAPI App, Lifespan, /health, /api/v1/agenda und SPA Mount
│   │   ├── config.py           # Zentrale Konfiguration (OAuth, JWT, PostgreSQL, Gemini KI, FCM, Instagram)
│   │   ├── permissions.py      # Kanonische 6 Rechte Matrix (publicaciones, grupos, roles, apis, ia, historial)
│   │   ├── models.py           # SQLAlchemy Modelle (User, Post, EventRegistration, PostView, AudienceGroup, UserRole, AdminAuditLog, AppSetting)
│   │   ├── api/                # Modulare REST Router (auth, publications, feed, news, events, classroom, groups, roles, ai, media, history, diagnostics, users)
│   │   ├── schemas/            # Strikte Pydantic v2 Request und Response Schemas
│   │   └── services/           # Geschaeftslogik (gemini, ai_extractor, instagram, google_groups, push, scheduler, audit)
│   └── tests/                  # Pytest Testsuite (API, Auth, PWA E2E, KI Extraktion, Classroom, Push)
├── docs/                       # Technische System, API und Projektspezifikation
│   ├── UPA_App_Documentacion_Arquitectura_v3.docx # Kompaktes Architektur-Hauptdokument Teil 1 (Word, Gelb-Markierung)
│   ├── UPA_App_Documentacion_Arquitectura_v3.md   # Markdown-Quelle des Architektur-Hauptdokuments Teil 1
│   ├── UPA_App_Documentacion_Arquitectura.docx # Offizielle Projektdokumentation (Word)
│   ├── UPA_App_Documentacion_Arquitectura.md   # Markdown-Quelle der Projektdokumentation
│   ├── UPA_App_Manual_de_Usuario.docx          # Offizielle Anwenderanleitung Teil 2 (Word)
│   ├── UPA_App_Manual_de_Usuario.md            # Markdown-Quelle der Anwenderanleitung Teil 2
│   ├── UPA_App_Informe_del_Proyecto.docx       # Offizieller Projektbericht und Fragenkatalog (Word)
│   ├── UPA_App_Informe_del_Proyecto.md         # Markdown-Quelle des Projektberichts (Teil 3)
│   ├── PFLICHTENHEFT.md        # Offizielles, verbindliches Pflichtenheft der UPA App
│   ├── FRONTEND_INTEGRATION_GUIDE.md
│   ├── api_documentation.md
│   ├── decisiones_arquitectonicas.md
│   ├── functional_spec.md
│   ├── especificacion_funcional.md
│   ├── google_cloud_setup.md
│   └── LOGBOOK.md
├── scripts/
│   ├── audit_zero_mock.py      # Gatekeeper Zero Mock und Architektur Scanner
│   ├── generar_documentacion_arquitectura.py # Generator fuer die offizielle Word-Dokumentation
│   ├── generar_manual_usuario.py             # Generator fuer die Anwenderanleitung (Manual de Usuario .docx)
│   ├── generar_informe_proyecto.py           # Generator fuer den Projektbericht (Teil 3)
│   └── generar_iconos_pwa.py   # Generator fuer PWA und Apple Touch Icons
├── .env.example                # Vollstaendige Konfigurationsvorlage analog zu backend/src/config.py
├── docker-compose.yml          # Produktions Stack (Port 8085 Frontend, Port 8000 Backend, 127.0.0.1:5432 DB)
└── docker-compose.beta.yml     # Isolierter Beta Stack (Port 8185 Frontend, Port 8100 Backend, 127.0.0.1:5433 DB)
```

## Kernmodule und Endpunkte der Plattform

1. **Studenten PWA (`web-app/`):**
   * **Desktop QR Code Landingpage:** Zeigt auf Desktop Bildschirmen ein visuelles Smartphone Modell, einen dynamisch generierten SVG QR Code zur aktuellen Server URL, eine direkte Vorschau Option (`/?app=1`) mit Rueckkehrleiste und den dezenten Link `Acceso Administrativo` (`/dashboard/`).
   * **Inicio (Campus Feed ueber `GET /api/v1/feed` bzw. `/api/feed`):** Dringende Eilmeldungen (`EMERGENCY_BANNER`) oben, angepinnte Beitraege (`is_pinned`), kombinierter Stream aus Campus News, Veranstaltungen und offiziellen Instagram Posts (`@upalemana`) sowie direkte 1 Klick RSVP Event Anmeldung im Zwei Button Muster (`Sí, asistiré` via `POST /api/events/{event_id}/register` und `No asistiré` via `DELETE /api/events/{event_id}/register`). Aus Datenschutzgruenden ist der Teilnehmerzaehler `registered_count` fuer Studierende stets auf `0` genullt.
   * **Agenda (Kalender und Abgabefristen ueber `GET /api/v1/agenda` und `/api/classroom/deadlines`):** Chronologische Terminliste im oberen Bereich und kompakter interaktiver Monatskalender mit Tagesmarkierungen im unteren Bereich. Synchronisiert persoenliche Google Classroom Aufgaben in der Zeitzone `America/Asuncion` mit direktem Absprung zu Google Classroom und persistentem DB Fallback (`classroom_deadlines_cache`).
   * **Perfil (Einstellungen und Sitzung ueber `GET /api/auth/me`):** Anzeige von Name, verifizierter E-Mail (`@upa.edu.py`) und Rolle, 3 Wege Design Umschalter (`Sistema`, `Modo Claro`, `Modo Oscuro`), Benachrichtigungsschalter fuer Events, Mitteilungen und Fristen sowie sicheres Abmelden mit Bereinigung des lokalen Nutzercaches.

2. **Web Admin Cockpit (`web-admin/`):**
   * **Publicaciones (`/dashboard/publicaciones`, `/dashboard/publicaciones/nueva`, `/dashboard/publicaciones/:id`):** Vereinheitlichter Single Source of Truth Editor (`GET/POST/PUT/DELETE /api/publications`) fuer News, Events und hybride Beitraege mit Deep Linking, Bildupload (`JPG`, `PNG`, `WEBP`), Videoupload (`MP4`, `WEBM`) und `PDF` bis 10 MB (`POST /api/media/upload`), Pflichtablaufdatum beim Anpinnen (`expires_at`), Instagram Schreibschutz fuer synchronisierte Felder (`POST /api/publications/sync-instagram`), Teilnehmerlisten (`GET /api/publications/{id}/registrations`) und dem Button `Autocompletar con IA` (`POST /api/publications/autocomplete-ai`).
   * **Grupos (`/dashboard/grupos`):** Alphabetisch sortierte Liste institutioneller Zielgruppen (`GET/POST/PUT/DELETE /api/groups`) und realer Google Workspace Gruppen (`GET /api/groups/google-workspace`) mit Live Filter.
   * **Roles (`/dashboard/roles`):** Granulare Berechtigungsmatrix (`GET/POST/PUT/DELETE /api/roles`) nach dem Least Privilege Prinzip mit allen **6 kanonischen Berechtigungen**:
     * `publicaciones`: Redaktionszugriff auf Publikationen, Events, Medienupload, KI Autocomplete und Teilnehmerlisten.
     * `grupos`: Verwaltung institutioneller Zielgruppen und Synchronisation der Google Workspace Gruppen.
     * `roles`: Verwaltung autorisierter Konten und Zuweisung der 6 Modulrechte (mindestens ein Konto behaelt stets `roles`).
     * `ia`: Zugriff auf das Modul `Control de IA` zur Konfiguration und Pruefung der Google Gemini Integration.
     * `apis`: Zugriff auf Echtzeit Systemdiagnose und Schnittstellen Telemetrie (`GET /api/system/diagnostics`).
     * `historial`: Einsicht in das revisionssichere Audit Protokoll (`GET /api/history/{entity_type}`).
   * **Control de IA (`/dashboard/ia`):** Verwaltung des Google Gemini API Schluessels (`GET/POST /api/ai/config`, persistent in PostgreSQL maskiert gespeichert), System Prompt Konfiguration und Live Verbindungstest (`POST /api/ai/test-connection`).
   * **APIs (`/dashboard/apis`) und Historial (`/api/history`):** Echtzeit Telemetrie fuer Datenbank Pool, Google Directory, Google Classroom, Instagram Sync und lueckenloses Audit Log aller administrativen Aenderungen.

## Sicherheitsrichtlinien und Konfiguration

* Es duerfen niemals echte API Schluessel, OAuth Client Secrets, Service Account JSON Dateien oder personenbezogene Zugangsdaten im Repository committet werden.
* Die Konfigurationsvorlagen `.env.example` und `backend/.env.example` bilden alle Parameter aus `backend/src/config.py` vollstaendig ab (Google OAuth 2.0 Parameter, JWT Secret und Algorithmus, PostgreSQL `DATABASE_URL`, Google Gemini API Key und Modellparameter, Instagram Sync sowie FCM Push Konfiguration).
* Der gesamte Produktivcode unterliegt dem automatisierten Zero Mock Audit (`scripts/audit_zero_mock.py`).

## Lokale Entwicklungsumgebung und Tests

Vor dem ersten Ausfuehren der lokalen Frontend Tests muessen die Node.js Abhaengigkeiten in `web-app/tests` und `web-admin/tests` installiert werden:

```bash
# 1. Node.js Test Abhaengigkeiten fuer PWA und Web Admin installieren
npm --prefix web-app/tests ci && npm --prefix web-admin/tests ci

# 2. Gesamten Produktions Stack starten (Frontend auf Port 8085, Backend auf Port 8000)
docker compose up -d --build

# 3. Alternativ Beta Stack starten (Frontend auf Port 8185, Backend auf Port 8100)
docker compose -f docker-compose.beta.yml up -d --build

# 4. Lokale Qualitaetskontrolle: Backend Tests, Frontend Tests, Linter, Typpruefung und Zero Mock Audit
PYTHONPATH=backend pytest backend/tests tests/test_audit_zero_mock.py
npm --prefix web-app/tests test
npm --prefix web-admin/tests test
ruff check .
cd backend && pyright
python3 scripts/audit_zero_mock.py
```

## Weiterfuehrende Dokumentation

* [Kompaktes Architektur-Hauptdokument v3 (Teil 1, Markdown)](docs/UPA_App_Documentacion_Arquitectura_v3.md)
* [Kompaktes Architektur-Hauptdokument v3 (Teil 1, MS Word .docx)](docs/UPA_App_Documentacion_Arquitectura_v3.docx)
* [Offizielle Architektur- und Projektdokumentation (Spanisch, Markdown)](docs/UPA_App_Documentacion_Arquitectura.md)
* [Offizielle Architektur- und Projektdokumentation (MS Word .docx)](docs/UPA_App_Documentacion_Arquitectura.docx)
* [Offizielle Anwenderanleitung Manual de Usuario Teil 2 (Spanisch, Markdown)](docs/UPA_App_Manual_de_Usuario.md)
* [Offizielle Anwenderanleitung Manual de Usuario Teil 2 (MS Word .docx)](docs/UPA_App_Manual_de_Usuario.docx)
* [Offizieller Projektbericht und Fragenkatalog (Teil 3, Markdown)](docs/UPA_App_Informe_del_Proyecto.md)
* [Offizieller Projektbericht und Fragenkatalog (Teil 3, MS Word .docx)](docs/UPA_App_Informe_del_Proyecto.docx)
* [Offizielles Pflichtenheft (PFLICHTENHEFT)](docs/PFLICHTENHEFT.md)
* [PWA und Frontend Integrationsleitfaden](docs/FRONTEND_INTEGRATION_GUIDE.md)
* [REST API und Architektur Referenz](docs/api_documentation.md)
* [Architekturentscheidungen](docs/decisiones_arquitectonicas.md)
* [Funktionale Systemspezifikation](docs/functional_spec.md)
* [Operative Spezifikation](docs/especificacion_funcional.md)
* [Google Cloud und OAuth Konfiguration](docs/google_cloud_setup.md)
* [Technisches Logbuch (LOGBOOK)](docs/LOGBOOK.md)
