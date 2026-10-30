# UPA App: Campus Portal und Progressive Web App (PWA)

Zentrale Hochschulplattform fuer Studierende, Dozierende und das Redaktionsteam der Universidad Paraguayo Alemana (UPA). Das System kombiniert eine responsive Studenten PWA (Mobile First fuer Android und iOS, Trusted Web Activity Ready) inklusive Desktop QR Code Landingpage mit einem Web Admin Redaktionsportal und einem FastAPI REST Backend mit multimodaler Google Gemini KI Integration.

## Systemarchitektur

Die Plattform laeuft in drei isolierten Docker Containern (`upa-postgres`, `upa-backend`, `upa-frontend` bzw. auf der Beta Umgebung `upa-postgres-beta`, `upa-backend-beta`, `upa-frontend-beta`):

1. **Nginx Frontend Container (`web-admin/Dockerfile`, `web-admin/nginx.conf`):**
   * Liefert unter `/` die **UPA Campus PWA** (`web-app/`) aus. Auf Desktop Browsern erscheint automatisch die Landingpage mit Smartphone Vorschau, dynamischem QR Code zum direkten Oeffnen auf dem Mobilgeraet und dezentem Link zum Administrationsbereich (`Acceso Administrativo`). Auf Mobilgeraeten startet unmittelbar die App Oberflaeche.
   * Stellt den Service Worker (`/sw.js`), das Web App Manifest (`/manifest.webmanifest`), die Digital Asset Links fuer Android TWA (`/.well-known/assetlinks.json`) und die statischen PWA Assets (`/campus/`) bereit.
   * Liefert unter `/dashboard/` das **Web Admin Cockpit** (`web-admin/`) fuer Redaktion, Gruppenverwaltung, Rollenmatrix, KI Konfiguration und Systemdiagnose aus.
   * Fungiert als Reverse Proxy fuer `/api/`, `/uploads/`, `/health`, `/docs` und `/openapi.json` an den FastAPI Backend Container (`http://backend:8000`).

2. **FastAPI Backend Container (`backend/`):**
   * Stellt alle REST Endpunkte unter `/api/v1/` und `/api/` sowie die interaktive OpenAPI 3.1 Spezifikation unter `/docs` und `/openapi.json` bereit.
   * Verifiziert die institutionelle Anmeldung ueber Google OAuth 2.0 (`@upa.edu.py`), synchronisiert Google Workspace Gruppen sowie Google Classroom Kurse und Abgabefristen (inklusive automatischem Token Refresh und persistentem Datenbank Fallback).
   * Integriert Google Gemini Flash fuer die multimodale KI Event Extraktion aus Instagram Beiträgen (`backend/src/services/ai_extractor.py`) und fuer das intelligente Formular Autocomplete im Redaktionseditor (`POST /api/publications/autocomplete-ai`).

3. **PostgreSQL 16 Datenbank Container (`postgres:16-alpine`):**
   * Zentrale relationale Datenhaltung (Single Source of Truth) fuer Publikationen, Events, RSVP Teilnahmen, eindeutige Beitragsaufrufe, Zielgruppen, Berechtigungsrollen, Audit Historie, gespeicherte Classroom Fristen und globale Systemeinstellungen.

## Projektstruktur

```text
upa-app/
├── web-app/                    # Studenten PWA (Mobile First, Android, iOS Safari, TWA Ready)
│   ├── index.html              # App Shell und Desktop QR Code Landingpage
│   ├── campus.css              # Responsive Styles, Safe Area Insets und 3 Wege Theme System
│   ├── campus-core.js          # API Client mit Timeout, Session Logik, Cache und QR Generator
│   ├── campus.js               # UI Controller fuer Inicio, Agenda, Perfil und Vollbild Detail
│   ├── sw.js                   # Service Worker fuer Offline Shell Precache
│   ├── manifest.webmanifest    # PWA Manifest (standalone, maskable Icons)
│   ├── .well-known/            # Digital Asset Links (assetlinks.json) fuer Android TWA
│   └── tests/                  # Automatisierte Unit und DOM End to End Tests (Node.js)
├── web-admin/                  # Administrations und Redaktionsportal (Desktop SPA)
│   ├── index.html              # Cockpit Oberflaeche (Publicaciones, Grupos, Roles, Control de IA, APIs, Historial)
│   ├── app.js                  # SPA Router, Google OAuth Login, Gruppen, Rollen, KI Steuerung und Diagnose
│   ├── editorial-core.js       # Formularvalidierung, Payload Aufbau und REST Client
│   ├── editorial.js            # Editor Controller inkl. Autocompletar con IA und Instagram Schreibschutz
│   ├── nginx.conf              # Produktive Nginx Routing und Proxy Konfiguration
│   ├── Dockerfile              # Multi Asset Image fuer web-admin und web-app (/campus/)
│   └── tests/                  # Automatisierte Frontend Tests (Node.js)
├── backend/                    # Python FastAPI REST Service
│   ├── src/
│   │   ├── main.py             # FastAPI App, Lifespan, /health, /api/v1/app-state, /api/v1/agenda
│   │   ├── models.py           # SQLAlchemy Modelle (User, Post, EventRegistration, PostView, AudienceGroup, UserRole, AdminAuditLog, AppSetting)
│   │   ├── api/                # Modulare REST Router (auth, publications, feed, news, events, classroom, groups, roles, ai, media, history, diagnostics, users)
│   │   ├── schemas/            # Strikte Pydantic v2 Request und Response Schemas
│   │   └── services/           # Geschaeftslogik (gemini, ai_extractor, instagram, google_groups, push, scheduler, audit)
│   └── tests/                  # Pytest Testsuite (API, Auth, PWA E2E, KI Extraktion, Classroom, Push)
├── docs/                       # Technische System und API Dokumentation
│   ├── FRONTEND_INTEGRATION_GUIDE.md
│   ├── api_documentation.md
│   ├── decisiones_arquitectonicas.md
│   ├── functional_spec.md
│   ├── especificacion_funcional.md
│   ├── google_cloud_setup.md
│   └── LOGBOOK.md
├── scripts/
│   ├── audit_zero_mock.py      # Gatekeeper Zero Mock und Architektur Scanner
│   └── generar_iconos_pwa.py   # Generator fuer PWA und Apple Touch Icons
├── docker-compose.yml          # Produktions Stack (Port 8085 Frontend, Port 8000 Backend, Port 5432 DB)
└── docker-compose.beta.yml     # Isolierter Beta Stack (Port 8185 Frontend, Port 8100 Backend, Port 5433 DB)
```

## Kernmodule der Plattform

1. **Studenten PWA (`web-app/`):**
   * **Desktop QR Code Landingpage:** Zeigt auf Desktop Bildschirmen ein visuelles Smartphone Modell, einen dynamisch generierten SVG QR Code zur aktuellen Server URL, eine direkte Vorschau Option (`/?app=1`) mit Rueckkehrleiste und den dezenten Link `Acceso Administrativo` (`/dashboard/`).
   * **Inicio (Campus Feed):** Dringende Eilmeldungen (`EMERGENCY_BANNER`) oben, angepinnte Beitraege (`is_pinned`), kombinierter Stream aus Campus News, Veranstaltungen und offiziellen Instagram Posts (`@upalemana`) sowie direkte 1 Klick Event Anmeldung (`POST /api/events/{event_id}/register` bzw. `DELETE /api/events/{event_id}/register`).
   * **Agenda (Kalender und Abgabefristen):** Chronologische Terminliste im oberen Bereich und kompakter interaktiver Monatskalender mit Tagesmarkierungen im unteren Bereich. Synchronisiert persönliche Google Classroom Aufgaben in der Zeitzone `America/Asuncion` mit direktem Absprung zu Google Classroom.
   * **Perfil (Einstellungen und Sitzung):** Anzeige von Name, verifizierter E-Mail (`@upa.edu.py`) und Rolle, 3 Wege Design Umschalter (`Sistema`, `Modo Claro`, `Modo Oscuro`), Benachrichtigungsschalter fuer Events, Mitteilungen und Fristen sowie sicheres Abmelden mit Bereinigung des lokalen Nutzercaches.

2. **Web Admin Cockpit (`web-admin/`):**
   * **Publicaciones (`/dashboard/publicaciones`):** Vereinheitlichter Editor (Single Source of Truth) fuer News, Events und hybride Beitraege mit Bildupload (`JPG`, `PNG`, `WEBP`), Videoupload (`MP4`, `WEBM`) und `PDF` bis 10 MB, Pflichtablaufdatum beim Anpinnen (`expires_at`), Instagram Schreibschutz fuer synchronisierte Felder und dem Button `Autocompletar con IA` zur multimodalen Vervollstaendigung leerer Formularfelder.
   * **Grupos (`/dashboard/grupos`):** Alphabetisch sortierte Liste institutioneller Zielgruppen und realer Google Workspace Gruppen mit Live Filter.
   * **Roles (`/dashboard/roles`):** Berechtigungsmatrix nach dem Least Privilege Prinzip (`publicaciones`, `grupos`, `roles`, `apis`, `historial`).
   * **Control de IA (`/dashboard/ia`):** Verwaltung des Google Gemini API Schluessels (persistent in PostgreSQL maskiert gespeichert) und Live Verbindungstest (`POST /api/ai/test-connection`).
   * **APIs (`/dashboard/apis`) und Historial (`/dashboard/historial`):** Echtzeit Telemetrie fuer Datenbank Pool, Google Directory, Google Classroom, Instagram Sync und lueckenloses Audit Log aller administrativen Aenderungen.

## Sicherheitsrichtlinien

* Es duerfen niemals echte API Schluessel, OAuth Client Secrets, Service Account JSON Dateien oder personenbezogene Zugangsdaten im Repository committet werden.
* Alle sensiblen Parameter werden ueber `.env` Dateien ausserhalb der Versionskontrolle oder ueber die verschluesselte Serverkonfiguration geladen.
* Der gesamte Produktivcode unterliegt dem automatisierten Zero Mock Audit (`scripts/audit_zero_mock.py`).

## Lokale Entwicklungsumgebung und Tests

```bash
# 1. Gesamten Produktions Stack starten (Frontend auf Port 8085, Backend auf Port 8000)
docker compose up -d --build

# 2. Alternativ Beta Stack starten (Frontend auf Port 8185, Backend auf Port 8100)
docker compose -f docker-compose.beta.yml up -d --build

# 3. Backend Tests, PWA Tests, Web Admin Tests und Zero Mock Audit lokal ausfuehren
PYTHONPATH=backend pytest backend/tests tests/test_audit_zero_mock.py
npm --prefix web-app/tests test
npm --prefix web-admin/tests test
python3 scripts/audit_zero_mock.py
```

## Weiterfuehrende Dokumentation

* [PWA und Frontend Integrationsleitfaden](docs/FRONTEND_INTEGRATION_GUIDE.md)
* [REST API und Architektur Referenz](docs/api_documentation.md)
* [Architekturentscheidungen](docs/decisiones_arquitectonicas.md)
* [Funktionale Systemspezifikation](docs/functional_spec.md)
* [Operative Spezifikation](docs/especificacion_funcional.md)
* [Google Cloud und OAuth Konfiguration](docs/google_cloud_setup.md)
* [Technisches Logbuch (LOGBOOK)](docs/LOGBOOK.md)
