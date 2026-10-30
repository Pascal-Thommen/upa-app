# Web Admin Cockpit und Redaktionsportal (`web-admin/`)

Administratives Desktop Portal der Universidad Paraguayo Alemana (UPA), erreichbar unter `/dashboard/`.

## Module und Funktionen
* **Publicaciones (`/dashboard/publicaciones`):** Vereinheitlichter Editor fuer Mitteilungen, Veranstaltungen und hybride Beitraege mit Pflichtfeld Titel, optionaler Zeitplanung (`ed-pub-scheduled`), RSVP Schalter, Push Benachrichtigung, Medienupload (`JPG`, `PNG`, `WEBP`, `MP4`, `WEBM`, `PDF`), Pflichtablaufdatum beim Anpinnen (`ed-pub-pinned` + `ed-pub-expires`), Instagram Schreibschutz fuer synchronisierte Felder, `IA` Badge fuer automatisch extrahierte Instagram Events und dem Button `Autocompletar con IA` (`POST /api/publications/autocomplete-ai`).
* **Grupos (`/dashboard/grupos`):** Alphabetisch sortierte Liste institutioneller Zielgruppen und realer Google Workspace Gruppen (`@upa.edu.py`) mit Echtzeit Filter.
* **Roles (`/dashboard/roles`):** Berechtigungsmatrix pro Modul (`publicaciones`, `grupos`, `roles`, `apis`, `historial`) nach dem Least Privilege Prinzip.
* **Control de IA (`/dashboard/ia`):** Verwaltung des Google Gemini API Schluessels (`GET/POST /api/ai/config`) und Live Verbindungstest (`POST /api/ai/test-connection`).
* **APIs (`/dashboard/apis`) und Historial (`/dashboard/historial`):** Echtzeit Systemdiagnose (`/api/system/diagnostics`) und tabellarisches Audit Log (`/api/history`).

## Komponenten
* `index.html`: SPA Oberflaeche mit rollenbasierter Seitenleiste.
* `editorial-core.js`: Formularvalidierung, Payload Erstellung, Erinnerungsumrechnung, Medienerkennung und REST Client mit Timeout.
* `editorial.js`: Controller des Publikations Editors inklusive `Autocompletar con IA` und Instagram Schreibschutz.
* `app.js`: Google OAuth Anmeldung (`@upa.edu.py`), SPA Router (`UpaRouter`), Gruppenverwaltung, Rollenmatrix, KI Steuerung und Diagnoseansicht.
* `nginx.conf` und `Dockerfile`: Nginx Produktionskonfiguration fuer die Auslieferung der Studenten PWA (`/`) und des Web Admin Cockpits (`/dashboard/`).

## Automatisierte Tests

```bash
cd web-admin/tests
npm test
```
