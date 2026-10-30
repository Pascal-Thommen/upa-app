# UPA App: Operative und Funktionale Spezifikation (PWA und KI Stand)

Technisches Referenzdokument | Universidad Paraguayo Alemana (UPA)

## 1. Desktop Landingpage und Bereitstellung (`web-app/index.html`)
* **Schlanke Desktop Startseite:** Zeigt auf Desktop Bildschirmen links ein visuelles Smartphone Vorschaumodell (`phone-mockup`) mit der echten App Oberflaeche und rechts genau einen dynamisch generierten SVG QR Code (`#qr-box`), der direkt auf die URL der UPA Campus PWA verweist.
* **Direkte Web Vorschau und Rueckkehr:** Ueber den Link `Probar la versión web aquí` (`/?app=1`) laesst sich die mobile PWA direkt am Desktop testen; eine dezente Kopfleiste (`Volver al código QR`) fuehrt jederzeit zur QR Code Ansicht zurueck.
* **Administrativer Zugang:** Dezenter Link `Acceso Administrativo` im Footer mit Weiterleitung zum Web Admin Cockpit (`/dashboard/`).

## 2. Mobile Benutzeroberflaeche der Studenten PWA (`web-app/`)

### A. Reiter Inicio (Zentraler Campus Feed)
* **Eilmeldungen (`EMERGENCY_BANNER`):** Obere Warnbanner mit automatischer Ausblendung nach Erreichen des Ablaufzeitpunkts (`expires_at`).
* **Beitraege, Instagram und Veranstaltungen:** Karten mit offiziellem Instagram Kamera Badge fuer Social Media Posts, KI generierten Eventdaten und direktem 1 Klick Button fuer Event Anmeldungen (`POST /api/events/{event_id}/register`) und Abmeldungen (`DELETE /api/events/{event_id}/register`).
* **Vollbild Detailansicht:** Ein Tippen auf eine Karte oeffnet das Vollbild Overlay (`#detail`) mit hochaufloesendem Bild oder Video, komplettem Text, Metadaten, dedupliziertem Quellenbutton (`Ver en Instagram` bzw. `Abrir enlace`) und Unterstuetzung der Android Zurueck Geste (`createOverlayManager`).

### B. Reiter Agenda (Kalender und Google Classroom)
* **Zweigeteilte Ansicht:** Chronologische Liste der anstehenden Veranstaltungen und Aufgaben im oberen Bereich sowie ein kompakter Monatskalender (`grid-auto-rows: 30px`) mit Aktivitaetspunkten im unteren Bereich.
* **Google Classroom Aufgaben:** Zeigt Abgabefristen umgerechnet auf `America/Asuncion` mit direktem Link zur Aufgabe in Google Classroom. Bei Google API Verzoegerungen liefert das Backend automatisch den in PostgreSQL gespeicherten Stand (`classroom_deadlines_cache`).

### C. Reiter Perfil (Identitaet und Einstellungen)
* **Hochschulidentitaet:** Vollstaendiger Name, Initialen Avatar, verifizierte `@upa.edu.py` Adresse und Rollenbezeichnung (`Estudiante`, `Docente`, `Redacción`, `Administración`) ohne Offenlegung interner Zielgruppen.
* **Design und Benachrichtigungen:** 3 Wege Theme Auswahl (`Sistema`, `Modo Claro`, `Modo Oscuro`) sowie Schalter fuer `Eventos`, `Avisos y comunicados` und `Fechas límite`.
* **Sicheres Abmelden:** Loescht das JWT Token und leert den lokalen Nutzercache (`upa_campus_cache_*`).

## 3. Web Admin Cockpit (`web-admin/` unter `/dashboard/`)

### A. Vereinheitlichter Publikations Editor (`/dashboard/publicaciones`)
* **Single Source of Truth:** Jede Publikation kann gleichzeitig Mitteilung (`is_news`), Kalenderveranstaltung (`is_event`) oder beides sein.
* **Multimodales KI Autocomplete (`Autocompletar con IA`):** Sendet die bereits eingetragenen Felder und das ausgewählte Bild oder Plakat an `POST /api/publications/autocomplete-ai` (Google Gemini Flash) und fuellt ausschliesslich die noch leeren Felder aus.
* **Automatische KI Event Extraktion bei Instagram Sync:** Neue Instagram Posts werden beim Synchronisieren durch `backend/src/services/ai_extractor.py` multimodal analysiert. Erkannte Events werden direkt scharf geschaltet und mit dem Badge `IA` (`is_ai_generated = true`) markiert.
* **Instagram Schreibschutz:** Bei synchronisierten Instagram Beiträgen bleiben Originaltext, Medien URL, Permalink und Veröffentlichungsdatum schreibgeschuetzt; der Kurztext (`caption`) wird aus den ersten zwei Zeilen abgeleitet.
* **Reichweiten und RSVP Metriken:** Zeigt eindeutige Nutzeraufrufe (`views_count`) sowie Anmeldungen (`attending_count`) und Absagen (`declined_count`) in Echtzeit.

### B. Gruppen, Rollen, KI Steuerung und Audit Historie
* **Grupos (`/dashboard/grupos`):** Alphabetisch sortierte flache Liste der Zielgruppen und Google Workspace Gruppen mit Sofortfilter.
* **Roles (`/dashboard/roles`):** Berechtigungsmatrix (`publicaciones`, `grupos`, `roles`, `apis`, `historial`) mit Least Privilege Standard.
* **Control de IA (`/dashboard/ia`):** Maskierte Speicherung des Google Gemini API Schluessels und Live Verbindungstest (`POST /api/ai/test-connection`).
* **APIs (`/dashboard/apis`) und Historial (`/dashboard/historial`):** Live Telemetrie aller Backend Integrationen und chronologisches Audit Protokoll im 24 Stunden Format.
