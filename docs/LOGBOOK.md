# Technisches Architektur Logbuch (LOGBOOK)

Chronologische Aufzeichnung der technischen Meilensteine, Architekturentscheidungen und Systemerweiterungen der Plattform **UPA App** der Universidad Paraguayo Alemana (UPA).

## Chronologie der Meilensteine

1. **Basisarchitektur und Google OAuth 2.0 (`@upa.edu.py`):**
   * Einrichtung der institutionellen Authentifizierung ueber Google OAuth 2.0 fuer die Domain `@upa.edu.py` mit JWT Sitzungstokens.
   * Anbindung des Google Workspace Directory Service Accounts (`admin.directory.group.readonly`) zur Gruppensynchronisation.
   * Rollentrennung zwischen `admin`, `editor` und `user`.

2. **Google Classroom Synchronisation mit Auto Refresh:**
   * Integration der Google Classroom API (`courses.readonly`, `coursework.me.readonly`) mit Offline Refresh Tokens (`classroom_refresh_token`).
   * Automatischer Token Refresh im Backend bei abgelaufenem Access Token (`HTTP 401`).

3. **Drei Schichten Container Architektur mit Nginx Frontend (`SRV-150` bis `SRV-176`):**
   * Trennung in drei produktive Container: `upa-postgres` (PostgreSQL 16), `upa-backend` (FastAPI) und `upa-frontend` (Nginx Alpine).
   * Bereitstellung einer isolierten Beta Umgebung (`docker-compose.beta.yml` auf Port 8185 / 8100 / 5433) und dynamische Aufloesung der `GOOGLE_REDIRECT_URI`.

4. **Persistente Datenbank Modelle fuer Gruppen, Rollen, Historie und Vereinheitlichte Publikationen (`SRV-157` bis `SRV-177`):**
   * Vollstaendige Persistenz in PostgreSQL (`posts`, `event_registrations`, `post_views`, `audience_groups`, `user_roles`, `admin_audit_logs`, `app_settings`).
   * Vereinheitlichter Publikations Editor (`/api/publications`) mit Bildupload, Videoupload (`MP4`, `WEBM`), Pflichtablaufdatum beim Anpinnen (`expires_at`), Instagram Schreibschutz und tabellarischer Audit Historie (`/api/history`).

5. **API Sicherheits Hardening (`SRV-186`):**
   * Vollstaendige Entfernung von `dev-login`, Absicherung von `GET /api/groups` mit Datenschutzfilter fuer E-Mail Listen, Beschraenkung von `POST /api/media/upload` auf Redakteure und Administratoren sowie Zugriffsschutz fuer `GET /api/system/diagnostics` (`apis` Berechtigung).

6. **UPA Campus PWA fuer Android und iOS mit Desktop QR Code Landingpage (`SRV-185` und `SRV-208`):**
   * Entwicklung der Progressive Web App unter `web-app/` (ausgeliefert ueber Nginx unter `/` und `/campus/`) mit `manifest.webmanifest`, Service Worker (`/sw.js`), Maskable Icons und Android TWA Asset Links (`/.well-known/assetlinks.json`).
   * Desktop Landingpage mit Smartphone Vorschau (`phone-mockup`), dynamischem SVG QR Code, Web Vorschau Modus (`/?app=1`) mit Rueckkehrleiste und dezentem Admin Zugang (`Acceso Administrativo`).
   * Mobile Oberflaeche mit `Inicio`, kompaktem `Agenda` Monatskalender, offiziellem Instagram Kamera Badge, deduplizierten Aktionsbuttons und bereinigtem `Perfil`.

7. **Classroom Datenbank Fallback und Strikter API Datenschutz (`SRV-207`):**
   * Persistente Speicherung synchronisierter Google Classroom Fristen in `users.classroom_deadlines_cache` mit nahtlosem Fallback (`X-Classroom-Cache: db_fallback`) bei Google API Timeouts und exakter Zeitzonenumrechnung auf `America/Asuncion`.
   * Bereinigung redundanter Gruppen Tags und strikte Ausgabe von `groups: []` fuer regulaere Studierende in `/api/auth/me` und `/api/users/me`.

8. **Multimodale Google Gemini Flash KI Integration (`SRV-179`, `SRV-180`, `SRV-181`):**
   * Neuer Reiter `Control de IA` (`/dashboard/ia`) im Web Admin Cockpit mit maskierter Speicherung des Gemini API Schluessels (`GET/POST /api/ai/config`) und Live Verbindungstest (`POST /api/ai/test-connection`).
   * Multimodale KI Event Extraktion (`backend/src/services/ai_extractor.py`) beim Instagram Sync: Analysiert Caption und Flyer Bild, prueft die Eintages Plausibilitaetsregel und veroeffentlicht erkannte Veranstaltungen direkt mit dem Badge `IA` (`is_ai_generated = true`).
   * Intelligenter Editor Button `Autocompletar con IA` (`POST /api/publications/autocomplete-ai`): Analysiert vorhandene Formulardaten sowie das hochgeladene Bild und fuellt ausschliesslich noch leere Formularfelder automatisch aus.
