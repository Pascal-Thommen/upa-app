# Leitfaden fuer KI-Agenten und Entwickler (AGENTS.md)

Dieses Dokument dient als zentrale Arbeitsanweisung fuer alle autonomen Coding-Agenten (Cursor, Claude Code, GitHub Copilot, Antigravity) sowie menschliche Entwickler im UPA App Projekt.

## 1. Projektuebersicht & Architektur
Das Projekt ist eine universitaere Plattform fuer die Universidad Paraguayo Alemana (UPA):
* `android/`: Native Android Applikation (Android Studio, Kotlin).
* `backend/`: REST API Service auf Basis von Python 3.11+ und FastAPI.
* `web-admin/`: Leichtgewichtiges Webportal fuer Redaktion und Marketing (Desktop).
* `docs/`: Schnittstellendefinitionen, Datenmodelle und Spezifikationen.

## 2. Sicherheitsrichtlinie: Keine Secrets im Repository
Alle Agenten muessen folgende Regeln strikt einhalten:
* Niemals echte API-Schluessel, OAuth-Client-Secrets, Service-Account-Dateien oder Passwoerter in Commits einfuegen.
* Konfigurationen erfolgen ausschliesslich ueber Umgebungsvariablen (.env).
* Vor jedem Commit ist sicherzustellen, dass keine privaten Daten oder Schluessel in Code, Logs oder Tests hardcodiert sind.
* Neue Umgebungsvariablen muessen mit Platzhaltern in `.env.example` dokumentiert werden.

## 3. Architekturprinzipien & Konventionen
* API First: Das Backend stellt unter `/docs` eine interaktive OpenAPI/Swagger-Spezifikation bereit. Schnittstellen aenderungen muessen abwaertskompatibel sein.
* Single Source of Truth: Beitraege und Kalendertermine teilen sich dasselbe relationale Datenmodell (Post/Event-Hybrid).
* Authentifizierung: Google OAuth 2.0 mit strikter E-Mail-Domaenen-Validierung (`@upa.edu.py`).
* Modularitaet: Jede Komponente (Android, Backend, Web-Admin) arbeitet unabhaengig und kommuniziert ueber die REST-Schnittstelle.

## 4. Befehle fuer Agenten
* Backend starten: `cd backend && uvicorn src.main:app --reload --port 8000`
* Tests ausfuehren: `pytest` im Backend-Verzeichnis.
