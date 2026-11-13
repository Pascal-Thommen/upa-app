# Schnittstellenspezifikation: UPA Académico Umfragen und Notenabruf

## 1. Systemübersicht und Kontext
Das UPA Académico Portal (`https://academico.upa.edu.py`) basiert auf einem Laravel Backend mit serverseitigem HTML Rendering (Blade) und CSRF Schutz.
Am Ende jedes 5-Wochen-Modulblocks schaltet das Prüfungsamt Evaluationsumfragen frei. Die Noteneinsicht für das jeweilige Modul ist im Portal so lange gesperrt, bis sämtliche zugehörige Umfragen (Modul-Evaluation und Dozenten-Evaluation) vollständig ausgefüllt und eingereicht wurden.

Diese Dokumentation dient als verbindliche Vorlage zur späteren Implementierung in der UPA App, sobald die Hochschule die Token- und Entwicklungskosten freigibt. Alle persönlichen Identifikatoren, Passwörter und Tokens wurden vollständig bereinigt.

---

## 2. Authentifizierung und Session Handling

* **Basis URL:** `https://academico.upa.edu.py`
* **Session Cookies:** `XSRF-TOKEN`, `upa_academico_session`
* **CSRF Token:** Zu finden im HTML Head (`<meta name="csrf-token" content="...">`) sowie im JavaScript Kontext (`window.Laravel.csrfToken`).
* **Sicherheitsanforderung:** Für Scraping oder API Aufrufe muss der aktuelle CSRF Token bei jedem POST Aufruf im Formularfeld `_token` mitgesendet werden.

---

## 3. Workflow der Umfrageeinreichung

Jedes Modul besitzt eine Modulseite unter:
`GET https://academico.upa.edu.py/loggedInStudent/course/{course_id}`

Sind Umfragen aktiv, enthält die HTML Antwort entsprechende Formulare mit dem Ziel:
`POST https://academico.upa.edu.py/course/survey/{survey_id}/answer/post`

### 3.1 Modul Evaluation (`surveyType = subject`)
* **Endpoint:** `POST /course/survey/{survey_id}/answer/post`
* **Content-Type:** `application/x-www-form-urlencoded`
* **Statuscode bei Erfolg:** `HTTP 302 Found` (Redirect zurück auf die Kursseite)
* **Formularfelder:**
  * `_token`: Gültiger CSRF Token
  * `surveyType`: Fester Wert `subject`
  * `answer[1101]`: Radio Auswahl (`Si` / `No`)
  * `answer[1102]`: Pflicht Freitext (Begründung der Zielerreichung)
  * `answer[1103]` bis `answer[1118]`: Radio Bewertungsskala (Likert: `Totalmente de acuerdo`, `Generalmente de acuerdo`, `Generalmente en desacuerdo`, `Totalmente en desacuerdo`)
  * `answer[1119]`: Pflicht Freitext (Entwickelte Kompetenzen)
  * `answer[1120]`: Gesamtnote Skala (`1` bis `10`)
  * `answer[1121]`: Pflicht Freitext (Allgemeines Feedback / Verbesserungsvorschläge)

### 3.2 Dozenten Evaluation (`surveyType = teacher`)
Existieren mehrere Dozenten für ein Modul, wird für jeden Dozenten ein separates Formular mit eigener `survey_id` gerendert.
* **Endpoint:** `POST /course/survey/{survey_id}/answer/post`
* **Content-Type:** `application/x-www-form-urlencoded`
* **Statuscode bei Erfolg:** `HTTP 302 Found`
* **Formularfelder:**
  * `_token`: Gültiger CSRF Token
  * `surveyType`: Fester Wert `teacher`
  * `answer[2201]` bis `answer[2209]`: Radio Bewertungsskala (Likert)
  * `answer[2210]`: Dozenten Gesamtnote Skala (`1` bis `10`)
  * `answer[2211]`: Pflicht Freitext (Feedback zum Dozenten)

---

## 4. Validierungsregeln für Freitextfelder (Textareas)

Die client- und serverseitige Validierung der Textareas (`answer[1102]`, `answer[1119]`, `answer[1121]`, `answer[2211]`) erzwingt strikte Regeln:

* **HTML5 Pattern:**
  ```regex
  ^(\w+\b\W?[\s\w]?){3,60}.{1,}$
  ```
* **Regel 1 (Erstes Zeichen):** Das erste Zeichen muss ein Buchstabe oder eine Ziffer sein (`[a-zA-Z0-9_]`). Führende Bindestriche, Punkte, Leerzeichen oder Sonderzeichen führen zu einem Validierungsfehler.
* **Regel 2 (Wortanzahl):** Mindestens 3 Wörter und maximal 60 Wörter pro Eingabe.
* **Regel 3 (Mehrzeilige Texte):** Bei Zeilenumbrüchen (`\n`) validiert die Portal Funktion `fnValidateTextarea` jede Zeile separat. Jede Zeile muss die Kriterien erfüllen.

---

## 5. Notenabruf und Freischaltlogik

Sobald alle `POST` Anfragen der Umfragen erfolgreich verarbeitet wurden, ist die Modulnote im akademischen Notenblatt freigeschaltet.

* **Endpoint:**
  `GET https://academico.upa.edu.py/loggedInStudent/academic`
* **HTML Tabellenstruktur:**
  * Zeilen mit Klasse `.course-row`
  * Modulcode Spalte: z. B. `CE-PPT-26`
  * Modulname Spalte: z. B. `Proyecto Práctico TIC`
  * Note Paraguay Spalte: Ganzzahl `1` bis `5` (z. B. `5` für Sobresaliente)
  * Note Deutschland Spalte: Dezimalzahl (z. B. `1.0`)
  * Status Spalte: `SI` (Bestanden) bzw. `NO`
  * Acta Spalte: Prüfungsaktenstatus (z. B. `- sin acta -` oder Aktennummer)

---

## 6. Bereinigte Test Fixture
Die vollständige, anonymisierte Payload Struktur für automatisierte Unittests und Scraper Mocks ist hinterlegt unter:
`docs/fixtures/academico_survey_payload_sanitized.json`
