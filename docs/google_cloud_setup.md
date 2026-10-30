# Konfigurationsleitfaden: Google Cloud Console, OAuth 2.0 und Gemini KI

Technische Dokumentation fuer die Einrichtung von Google OAuth 2.0, Google Classroom, Google Workspace Directory und Google Gemini Flash nach dem Least Privilege Prinzip.

## 1. OAuth Nutzertyp: Intern (`upa.edu.py`)

Durch Auswahl des Nutzertyps **Intern** in der Google Cloud Console fuer die Organisation `upa.edu.py`:
* **Exklusiver Hochschulzugang:** Nur Konten der Domain `@upa.edu.py` koennen sich in der UPA Campus PWA und im Web Admin Cockpit anmelden (`hd=upa.edu.py`).
* **Kryptografische Ablehnung externer Konten:** Private `@gmail.com` Adressen werden bereits beim OAuth Handshake sowie zusaetzlich im Backend (`_validate_and_normalize_email`) abgewiesen.

## 2. Einrichtung in der Google Cloud Console

1. In der [Google Cloud Console](https://console.cloud.google.com/) mit einem Administratorkonto von `@upa.edu.py` anmelden und das Projekt auswaehlen.
2. Unter **APIs und Dienste > OAuth Zustimmungsbildschirm** konfigurieren:
   * Nutzertyp: **Intern**
   * Anwendungsname: `UPA Campus`
   * Autorisierte Domains: `upa.edu.py` sowie die NetBird Ingress Domain (`netbird.services`)
3. Folgende OAuth Scopes hinterlegen:
   * `openid`
   * `https://www.googleapis.com/auth/userinfo.email`
   * `https://www.googleapis.com/auth/userinfo.profile`
   * `https://www.googleapis.com/auth/classroom.courses.readonly`
   * `https://www.googleapis.com/auth/classroom.coursework.me.readonly`
4. Unter **APIs und Dienste > Bibliothek** aktivieren:
   * **Google Classroom API**
   * **Admin SDK API** (fuer Google Workspace Gruppensynchronisation)
5. Unter **APIs und Dienste > Anmeldedaten** einen OAuth 2.0 Client vom Typ **Webanwendung** fuer das FastAPI Backend erstellen:
   * Autorisierte Weiterleitungs URIs (`redirect_uri`):
     * Produktion: `https://upa.eu1.netbird.services/api/auth/google`
     * Beta: `https://upa-beta.eu1.netbird.services/api/auth/google`
     * Lokal: `http://localhost:8000/api/auth/google` und `http://localhost:8085/api/auth/google`
   * Sowohl die Studenten PWA (`/api/auth/login-google?return_to=campus`) als auch das Web Admin Cockpit (`/api/auth/login-google`) nutzen denselben zentralen Web OAuth Client ueber das Backend (`resolve_google_redirect_uri`).

## 3. Google Gemini API Schluessel fuer KI Funktionen

Fuer die multimodale Instagram Event Extraktion (`backend/src/services/ai_extractor.py`) und den Editor Button `Autocompletar con IA` (`POST /api/publications/autocomplete-ai`):
1. Unter `https://aistudio.google.com/app/apikey` einen API Schluessel erstellen.
2. Im Web Admin Cockpit unter `/dashboard/ia` (`Control de IA`) einfuegen, speichern (`POST /api/ai/config`) und per `Probar conexión` (`POST /api/ai/test-connection`) verifizieren. Alternativ kann die Umgebungsvariable `GEMINI_API_KEY` gesetzt werden.

## 4. Logische Zielgruppen Abbildung (Target Groups Mapping)

Um ueber 200 einzelne Google Workspace Verteiler fuer die Redaktion uebersichtlich zu halten, bildet das Backend (`backend/src/services/google_groups.py`) die Workspace Gruppen auf kuratierte Zielgruppen in `audience_groups` ab:
* `ALL`: Gesamte Hochschulgemeinschaft
* `estudiantes`, `docentes`, `staff`, `egresados`: Institutionelle Basisgruppen
* `TIE`: Ingenieria Empresarial
* `PI`: Ingenieria Industrial
* `TI`: Tecnologias de la Informacion
* `PROF`: Lehrkoerper
