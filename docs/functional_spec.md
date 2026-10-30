# UPA App: Funktionale Systemspezifikation

## 1. Technologiestack und Architekturprinzipien
* **PWA First (`web-app/`):** Responsive Progressive Web App fuer Studierende und Dozierende auf Android und iOS mit Desktop QR Code Landingpage, Web App Manifest (`manifest.webmanifest`), Service Worker (`/sw.js`) und Android TWA Unterstuetzung (`/.well-known/assetlinks.json`).
* **Python FastAPI Backend (`backend/`):** Asynchroner REST Service mit Pydantic v2 Validierung, SQLAlchemy 2.0 ORM, PostgreSQL 16 und automatisch generierter OpenAPI 3.1 Dokumentation unter `/docs`.
* **Multimodale KI (`Google Gemini Flash`):** Automatische Veranstaltungserkennung aus Instagram Beiträgen und intelligentes Ausfuellen leerer Editorfelder (`Autocompletar con IA`).

## 2. Kernmodule und Funktionen

### Modul Inicio (Campus Feed in der PWA)
* Dringende Eilmeldungen (`EMERGENCY_BANNER`) als prominente obere Banner mit automatischem Ablaufdatum (`expires_at`).
* Chronologischer Feed aus angepinnten Beitraegen, Campus Mitteilungen, Veranstaltungen und offiziellen Instagram Posts (`@upalemana`).
* Direkte 1 Klick Anmeldung und Abmeldung fuer Veranstaltungen (`Inscribirme` / `Cancelar inscripcion`) auf der Karte und in der Vollbild Detailansicht.

### Modul Agenda (Kalender und Abgabefristen in der PWA)
* Kombinierte Ansicht aus chronologischer Terminliste im oberen Bereich und kompaktem Monatskalender mit farbigen Tagespunkten im unteren Bereich.
* Automatische Synchronisation der persönlichen Google Classroom Aufgaben in der lokalen Zeitzone `America/Asuncion` inklusive persistentem Datenbank Fallback (`classroom_deadlines_cache`) bei Google API Timeouts.

### Modul Perfil (Einstellungen und Sitzung in der PWA)
* Verbindliche Anmeldung ueber Google OAuth 2.0 fuer Konten der Domain `@upa.edu.py` (`/api/auth/login-google?return_to=campus`).
* 3 Wege Design Umschalter (`Sistema`, `Modo Claro`, `Modo Oscuro`), Benachrichtigungsschalter fuer Events, Mitteilungen und Fristen sowie sicheres Abmelden mit Bereinigung des lokalen Caches.
* Strikter Datenschutz: Interne Zielgruppen und E-Mail Verteiler werden im Studentenprofil nicht angezeigt.

### Modul Web Admin Cockpit (`web-admin/` unter `/dashboard/`)
* **Publicaciones (`/dashboard/publicaciones`):** Vereinheitlichtes Datenmodell in `/api/publications` fuer Mitteilungen, Veranstaltungen und hybride Beitraege mit Upload fuer Bilder (`JPG`, `PNG`, `WEBP`), Videos (`MP4`, `WEBM`) und `PDF`, Pflichtablaufdatum beim Anpinnen (`is_pinned`), flexiblen Erinnerungen, Instagram Schreibschutz und dem Button `Autocompletar con IA`.
* **Grupos (`/dashboard/grupos`):** Alphabetisch sortierte Liste institutioneller Zielgruppen und realer Google Workspace Gruppen (`@upa.edu.py`) mit Echtzeit Suchfilter.
* **Roles (`/dashboard/roles`):** Berechtigungsmatrix nach dem Least Privilege Prinzip (`publicaciones`, `grupos`, `roles`, `apis`, `historial`) mit standardmaessig deaktivierten Checkboxen fuer neue Konten.
* **Control de IA (`/dashboard/ia`), APIs (`/dashboard/apis`) und Historial (`/dashboard/historial`):** Verwaltung und Live Test des Google Gemini API Schluessels, Echtzeit Systemdiagnose und lueckenlose Audit Historie.
