# Leitfaden fuer KI Agenten und Entwickler (AGENTS.md)

Dieses Dokument enthaelt die verbindlichen Arbeitsrichtlinien fuer alle autonomen Entwicklungsagenten und Entwickler des Projekts UPA App.

## 1. Systemuebersicht und Architektur
Die Plattform der Universidad Paraguayo Alemana (UPA) besteht aus drei produktiven Hauptkomponenten:
* `web-app/`: Responsive Studenten PWA (Mobile First fuer Android und iOS, Trusted Web Activity Ready) mit Desktop QR Code Landingpage, Service Worker (`/sw.js`) und Web App Manifest (`/manifest.webmanifest`).
* `web-admin/`: Administratives Desktop Cockpit (`/dashboard/`) fuer Redaktion (`Publicaciones` inkl. `Autocompletar con IA`), Zielgruppen (`Grupos`), Berechtigungsrollen (`Roles`), KI Steuerung (`Control de IA`), Systemdiagnose (`APIs`) und Audit Historie (`Historial`), ausgeliefert ueber Nginx.
* `backend/`: Python 3.11+ FastAPI REST Service mit PostgreSQL 16, Google OAuth 2.0 (`@upa.edu.py`), Google Classroom Synchronisation mit persistentem DB Fallback und multimodaler Google Gemini Flash KI Integration.
* `docs/`: Technische System, Architektur und OpenAPI Dokumentation.

## 2. Sicherheitsrichtlinie: Keine Geheimnisse im Repository
* Niemals echte API Schluessel, OAuth Client Secrets, Service Account JSON Dateien oder Passwoerter in Commits aufnehmen.
* Alle geheimen Konfigurationswerte werden ausschliesslich ueber `.env` Dateien oder die Serverdatenbank (`app_settings`) bezogen.

## 3. Architekturprinzipien
* **API First und OpenAPI 3.1:** Das Backend stellt unter `/docs` und `/openapi.json` die vollstaendige Spezifikation bereit.
* **Single Source of Truth:** Mitteilungen und Kalenderveranstaltungen teilen sich dasselbe relationale Datenmodell (`posts` ueber `/api/publications`).
* **Authentifizierung:** Ausschliesslich Google OAuth 2.0 fuer die Domain `@upa.edu.py` mit JWT Sitzungstokens.
* **Zero Mock Standard:** Produktivcode und Tests werden durch `scripts/audit_zero_mock.py` geprueft.

## 4. Wichtige Befehle
* Backend starten: `cd backend && uvicorn src.main:app --reload --port 8000`
* Backend Tests ausfuehren: `PYTHONPATH=backend pytest backend/tests tests/test_audit_zero_mock.py`
* PWA Tests ausfuehren: `npm --prefix web-app/tests test`
* Web Admin Tests ausfuehren: `npm --prefix web-admin/tests test`
* Zero Mock Audit ausfuehren: `python3 scripts/audit_zero_mock.py`
