# UPA App: Umfang, Rollenmodell und Architekturentscheidungen

Technisches Architektur und Strategiedokument | Universidad Paraguayo Alemana (UPA)  
Verantwortlich: Pascal Thommen  
Stand: 30. Oktober 2026  

## 1. Systemzweck und Designphilosophie
Ziel der Plattform UPA App ist die Konsolidierung des akademischen, kommunikativen und gemeinschaftlichen Campuslebens der Universidad Paraguayo Alemana in einer einzigen verlässlichen Datenquelle (Single Source of Truth).
* **Fokussierter Minimalismus:** Klare, schnelle und ablenkungsfreie Benutzeroberflaeche auf Mobilgeraeten und am Desktop.
* **Zero Mock Doktrin:** Jede Ansicht, jedes Formular und jeder Button ist direkt mit realer Backend Logik und PostgreSQL 16 verbunden.

## 2. Benutzerrollen im System
* **Studierende (`role = "user"`):** Nutzen die mobile Progressive Web App (`web-app/`), lesen Eilmeldungen und Campus News, melden sich mit einem Fingertipp zu Veranstaltungen an und verfolgen ihre Google Classroom Abgabefristen in der Agenda.
* **Dozierende:** Sehen zielgruppenspezifische Mitteilungen, akademische Termine und Veranstaltungen ihrer Fakultaet.
* **Redaktion und Marketing (`role = "editor"`):** Pflegen im Web Admin Cockpit (`web-admin/`) Publikationen, Veranstaltungen, Medienanhaenge und nutzen das multimodale KI Autocomplete.
* **Systemadministration (`role = "admin"`):** Verwaltet zusaetzlich Zielgruppen (`Grupos`), Berechtigungsrollen (`Roles`), den Google Gemini API Schluessel (`Control de IA`), Systemdiagnosen (`APIs`) und das Audit Protokoll (`Historial`).
* **Nicht angemeldete Besucher:** Sehen im oeffentlichen Modus der PWA ausschliesslich oeffentliche Instagram Beitraege (`@upalemana`) und koennen sich jederzeit mit ihrem institutionellen Konto `@upa.edu.py` ueber Google OAuth 2.0 anmelden.

## 3. Verbindliche Architekturentscheidungen

### 3.1. Mobiles Frontend: Progressive Web App (PWA) mit Desktop QR Code Landingpage
* **Entscheidung:** Die Plattform setzt verbindlich auf eine plattformuebergreifende Progressive Web App (`web-app/`) fuer Android (Chrome und Trusted Web Activity) und iOS (Safari Homescreen Web App) inklusive vorgeschalteter Desktop QR Code Landingpage anstelle separater nativer Store Apps.
* **Begruendung:** Sofortige Nutzbarkeit per Link ohne Installationszwang auf iOS und Android, einheitliche Codebasis ohne Store Freigabeverzoegerungen, vollstaendige Standalone Installation ueber `manifest.webmanifest`, Offline Shell Caching per Service Worker (`/sw.js`) sowie TWA Kompatibilitaet ueber `/.well-known/assetlinks.json`.

### 3.2. Persistenzmodell: PostgreSQL 16 im Backend und geschichteter Client Cache in der PWA
* **Entscheidung:** PostgreSQL 16 bildet den zentralen relationalen Datenspeicher im Backend (inklusive persistentem `classroom_deadlines_cache` pro Nutzer), waehrend die PWA einen Service Worker Shell Cache (`upa-campus-shell-1.0.0`) mit einem nutzergebundenen LocalStorage Datencache (`upa_campus_cache_*`) kombiniert.
* **Begruendung:** Transaktionssichere Speicherung von RSVP Anmeldungen, Beitragsaufrufen, Rollen und Audit Logs auf dem Server; gleichzeitige Offline Verfuegbarkeit der App Oberflaeche und der zuletzt synchronisierten Inhalte auf dem Smartphone mit sauberer Bereinigung beim Abmelden.

### 3.3. Drei Container Architektur mit Nginx Reverse Proxy
* **Entscheidung:** Betrieb in drei getrennten Docker Containern (`upa-postgres`, `upa-backend`, `upa-frontend`). Der Nginx Container liefert sowohl die Studenten PWA (`/`, `/campus/`, `/sw.js`, `/manifest.webmanifest`) als auch das Web Admin Cockpit (`/dashboard/`) statisch aus und leitet `/api/`, `/uploads/`, `/health`, `/docs` und `/openapi.json` an FastAPI weiter.
* **Begruendung:** Klare Trennung zwischen statischer Asset Auslieferung und API Ausfuehrung, einheitliche Origin fuer PWA und API ohne CORS Reibung im Produktivbetrieb sowie paralleler Betrieb einer isolierten Beta Umgebung (`docker-compose.beta.yml` auf Port 8185).

### 3.4. Zero Trust Netzwerkzugang ueber NetBird
* **Entscheidung:** Bereitstellung der Produktions und Beta Umgebung ueber verschluesselte NetBird Ingress Endpunkte (`https://upa.eu1.netbird.services` und `https://upa-beta.eu1.netbird.services`).
* **Begruendung:** Sichere TLS Terminierung und geschuetzte interne Containerkommunikation ohne offene Datenbankports im oeffentlichen Internet.

### 3.5. Institutionelle Authentifizierung ueber Google OAuth 2.0 (`@upa.edu.py`)
* **Entscheidung:** Ausschliessliche Anmeldung ueber Google OAuth 2.0 fuer die Domain `@upa.edu.py` mit Offline Refresh Token fuer Google Classroom, automatischer Google Workspace Gruppensynchronisation, JWT Sitzungstokens und striktem Datenschutzfilter (`groups: []` fuer regulaere Studierende).
* **Begruendung:** Keine lokale Passwortverwaltung, nahtlose Classroom Synchronisation mit automatischem Token Refresh im Hintergrund und Schutz interner E-Mail Verteilerlisten.

### 3.6. Multimodale Google Gemini Flash KI Integration
* **Entscheidung:** Einsatz von Google Gemini Flash fuer zwei Kernfunktionen:
  1. **Automatische Instagram Event Extraktion (`backend/src/services/ai_extractor.py`):** Analysiert neue Instagram Posts multimodal (Caption Text und Flyer Bild) und veroeffentlicht erkannte Veranstaltungen direkt mit `is_ai_generated = true` unter Einhaltung der Eintages Plausibilitaetsregel.
  2. **Smart Editor Autocomplete (`POST /api/publications/autocomplete-ai`):** Vervollstaendigt auf Klick im Editor (`Autocompletar con IA`) ausschliesslich noch leere Formularfelder anhand der vorhandenen Angaben und des hochgeladenen Plakats.
* **Begruendung:** Drastische Reduktion des manuellen Redaktionsaufwands bei gleichzeitiger Ausfallsicherheit (nahtloser Fallback auf Standard News Post bei deaktivierter KI oder API Timeout).
