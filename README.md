# UPA App

Zentrale Campus-Plattform fuer Studierende und Dozenten der Universidad Paraguayo Alemana (UPA).

## Projektstruktur

```text
upa-app/
├── android/          # Native Android Applikation (Android Studio / Kotlin)
├── backend/          # REST API Service (Python, FastAPI, Pydantic, SQLAlchemy)
├── web-admin/        # Webportal fuer Marketing und Verwaltung (Desktop)
├── docs/             # Spezifikationen, Datenmodelle und Dozenten-Briefing
├── .github/          # CI/CD Workflows und Sicherheitschecks
├── AGENTS.md         # Arbeitsanweisungen fuer autonome Coding-Agenten
└── README.md
```

## Kernmodule & Funktionen

1. **Inicio (Campus-Feed):**
   * Dringlichkeits-Eilmeldungen als Banner (z.B. Unterrichtsausfall bei Unwetter).
   * Campus-Events und Fachvortraege (Charlas) mit 1-Klick An- und Abmeldung.
   * Social Media Aggregation der offiziellen Universitaetskanaele via SociableKIT / Instagram API.

2. **Agenda (Termine & Fristen):**
   * Kombinierte Ansicht: Chronologische Agenda oben, Monatskalender mit Terminpunkten unten.
   * Synchronisation akademischer Abgabefristen via Google Classroom.

3. **Profil & Einstellungen:**
   * Google OAuth Pflicht-Login mit Zwang zu `@upa.edu.py`.
   * Lokale Nutzerpraeferenzen (Dark/Light Mode, Benachrichtigungen, Studiengangsfilter).

4. **Web-Administration (Desktop Portal):**
   * Zentrales Redaktionssystem fuer das Marketing-Team.
   * Single Source of Truth: Ein Inhaltsobjekt kann Beitrag, Kalenderevent oder beides sein.
   * Zielgruppen-Aussteuerung basierend auf Google Groups via Google Workspace Admin API.

## Sicherheit & Open-Source-Richtlinie

Dieses Repository ist oeffentlich. Ausnahmslos alle Entwickler und KI-Agenten befolgen folgende Sicherheitsregeln:
* Keine echten API-Schluessel, Secrets oder personenbezogene Daten in Commits.
* Alle Konfigurationsparameter werden ueber `.env` Dateien verwaltet, die via `.gitignore` geschuetzt sind.
* Vorlagen fuer Konfigurationsvariablen sind in `.env.example` hinterlegt.

## Schnellstart Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Unter Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn src.main:app --reload --port 8000
```

Interaktive API-Dokumentation oeffnen unter: `http://localhost:8000/docs`
