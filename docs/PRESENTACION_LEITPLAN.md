# UPA App: Leitplan und Regiebuch fuer die Abschlusspraesentation (Presentacion Final)

| Metadato / Parameter | Detalle / Vorgabe |
|---|---|
| **Institucion** | Universidad Paraguayo Alemana (UPA), San Lorenzo, Paraguay |
| **Proyecto** | UPA App: Plataforma Digital y Campus Movil |
| **Autores** | Pascal Thommen, Theresa Bauer, Natasha Colman |
| **Fecha de Presentacion** | Jueves, 5 de noviembre de 2026 (Donnerstag, 5. November 2026) |
| **Formato de Tiempo** | 10 Minutos Total: **5 Minutos Presentacion (7 Diapositivas)** + **5 Minutos Demostracion en Vivo** |
| **Archivo de Diapositivas** | `docs/UPA_App_Presentacion_Final.pptx` (Formato 16:9 Widescreen, Diseno Corporativo UPA) |
| **Entorno de Demo en Vivo** | Produccion: `https://upa.eu1.netbird.services` / Cockpit: `https://upa.eu1.netbird.services/dashboard/` |

---

## 1. Zeitplan und Struktur im 5+5 Minuten Format (Cronograma Ejecutivo)

Die zehnminuetige Abschlusspraesentation ist scharf in zwei Bloecke zu je 5 Minuten gegliedert. Die Folien 1 bis 4 fuehren in 3 Minuten in Problem, Loesung und den strategischen PWA-Pivot ein. Folie 5 leitet direkt in die 5-minuetige Live-Demonstration ueber. Nach der Live-Demo schliessen die Folien 6 und 7 in 90 Sekunden mit den KI-Learnings und der Roadmap ab.

| Phase | Folie / Station | Thema | Dauer | Zeitfenster |
|---|---|---|---|---|
| **Teil A: Vortrag (Start)** | **Folie 1** | Titelfolie: UPA App - Plataforma Digital y Campus Movil | 00:35 Min | `00:00 - 00:35` |
| **Teil A: Vortrag** | **Folie 2** | Problemstellung & Zielgruppe (Fragmentierte Kommunikation) | 00:45 Min | `00:35 - 01:20` |
| **Teil A: Vortrag** | **Folie 3** | Die Loesung (Single Source of Truth PWA + Web-Admin Cockpit) | 00:50 Min | `01:20 - 02:10` |
| **Teil A: Vortrag** | **Folie 4** | Strategischer Pivot (Warum PWA statt nativer Android-App) | 00:50 Min | `02:10 - 03:00` |
| **Teil A -> B (Bruecke)** | **Folie 5** | Live-Demonstration Leitplan (Ueberblick der 4 Demo-Stationen) | 00:30 Min | `03:00 - 03:30` |
| **Teil B: Live-Demo** | **Station 1** | QR-Code Scan am Desktop & Google OAuth Login (`@upa.edu.py`) | 01:00 Min | `03:30 - 04:30` |
| **Teil B: Live-Demo** | **Station 2** | PWA Feed, angepinnte Eilmeldung & Instagram-Integration | 01:15 Min | `04:30 - 05:45` |
| **Teil B: Live-Demo** | **Station 3** | 1-Klick RSVP Anmeldung & Agenda mit Google Classroom Sync | 01:15 Min | `05:45 - 07:00` |
| **Teil B: Live-Demo** | **Station 4** | Web-Admin KI-Plakat Extraktion (`Autocompletar con IA`) | 01:30 Min | `07:00 - 08:30` |
| **Teil A: Vortrag (Abschluss)** | **Folie 6** | Herausforderungen & KI-Entwicklung (Zero-Mock, Gemini 4 Argon) | 00:45 Min | `08:30 - 09:15` |
| **Teil A: Vortrag (Abschluss)** | **Folie 7** | Roadmap (30 Tage: UPA Domain/Hosting, 6 Monate: UPA Academico) | 00:45 Min | `09:15 - 10:00` |

---

## 2. Detaillierter Folien-Leitplan mit Stichpunkten und Timing fuer Pascal

### Folie 1: Titelfolie (Portada Institucional)
* **Timing:** `00:00 - 00:35` (35 Sekunden)
* **Folientitel (Spanisch):** `UPA App: Plataforma Digital y Campus Movil`
* **Untertitel:** `Fuente Unica de Verdad (Single Source of Truth) para la Universidad Paraguayo Alemana`
* **Autoren auf der Folie:** `Pascal Thommen, Theresa Bauer, Natasha Colman`
* **Kernaussagen & Stichpunkte fuer Pascal (Deutsch):**
  * Begruessung des Dozenten und des Plenums; Vorstellung des Teams (Pascal Thommen, Theresa Bauer, Natasha Colman).
  * Kurz-Pitch in einem Satz: Die UPA App ist die zentrale Campus-Plattform der UPA, die alle wichtigen Hochschul-Meldungen, Events und Google Classroom Abgabefristen in einer sofort nutzbaren Progressive Web App (PWA) mit einem KI-gestuetzten Redaktions-Cockpit vereint.
  * Hinweis zum Ablauf: 5 Minuten kompakter Architektur- und Strategie-Ueberblick, kombiniert mit 5 Minuten echter Live-Demonstration auf dem Produktivsystem.
* **Sprechvorlage (Spanisch):**
  * *"Buenos dias. Presentamos UPA App: nuestra Plataforma Digital y Campus Movil desarrollada por Pascal Thommen, Theresa Bauer y Natasha Colman."*
  * *"En los proximos diez minutos veremos por que creamos una Fuente Unica de Verdad para el campus y realizaremos una demostracion en vivo de cinco minutos sobre el sistema en produccion."*

---

### Folie 2: Problemstellung & Zielgruppe (Problema y Audiencia Objetivo)
* **Timing:** `00:35 - 01:20` (45 Sekunden)
* **Folientitel (Spanisch):** `El Problema y Audiencia Objetivo: Comunicacion Fragmentada en la UPA`
* **Visuelle Bloecke auf der Folie:**
  * **Status Quo (4 isolierte Kanaele):** WhatsApp-Gruppen, Instagram (`@upalemana`), E-Mail und Einzelkurse in Google Classroom fuer eine Hochschulgemeinschaft von **weniger als 1.000 Studierenden** (`menos de 1.000 estudiantes`).
  * **3 operative Kernprobleme:**
    1. **Informationsverlust:** Wichtige Campus-Meldungen, Raumwechsel oder kurzfristige Ausfaelle gehen in hunderten WhatsApp-Chats oder ungelesenen E-Mails unter.
    2. **Fehlende digitale Reichweite (Gang von Raum zu Raum):** Mitarbeiter muessen teils physisch durch das Gebaeude von Hoersaal zu Hoersaal gehen, um Studierende persoenlich an beginnende Vortraege zu erinnern.
    3. **Fehlendes RSVP & verstreute Fristen:** Keine zentrale Teilnahmebestaetigung (RSVP) fuer die Raumplanung und isolierte Abgabefristen in einzelnen Classroom-Kursen.
  * **Zielgruppen-Mehrwert:**
    * **Studierende & Dozierende:** Ein einziger verlaesslicher Ort fuer alle Meldungen, Events und Abgabefristen ohne Informationsflut.
    * **Mitarbeitende & Marketing:** Direktkanal an gezielte Studiengaenge (`TIE`, `PI`, `TI`) ohne manuelle Doppelpflege.
* **Sprechvorlage (Spanisch):**
  * *"En la UPA, con una comunidad de menos de mil estudiantes, la comunicacion actual esta fragmentada entre grupos de WhatsApp, Instagram, correos y Google Classroom."*
  * *"Esto provoca que anuncios criticos se pierdan y que el personal administrativo a veces tenga que recorrer aula por aula para avisar de charlas inminentes."*
  * *"Nuestra audiencia objetivo son tanto los estudiantes y docentes, que necesitan centralizar fechas y eventos, como el equipo de marketing y administracion, que requiere alcance directo y medible."*

---

### Folie 3: Die Loesung (La Solucion: Single Source of Truth PWA + Web-Admin Cockpit)
* **Timing:** `01:20 - 02:10` (50 Sekunden)
* **Folientitel (Spanisch):** `La Solucion: Fuente Unica de Verdad (PWA Estudiantil + Web-Admin Cockpit)`
* **Visuelle Bloecke auf der Folie:**
  * **Saeule 1: Campus PWA (`web-app/`) fuer Studierende & Dozierende**
    * Geschuetztes Google Workspace SSO (`@upa.edu.py`) plus oeffentlicher Gastmodus fuer offizielle Instagram-Beitraege.
    * Zentraler **Inicio-Feed** (angepinnte Eilmeldungen mit Ablaufdatum `expires_at`, Campus-News, `@upalemana` Instagram-Sync).
    * **1-Klick RSVP** mit klarem Zwei-Button-Muster (`Si, asistire` / `No asistire`) und **Agenda** mit automatischem Google Classroom Sync (`America/Asuncion`) inkl. DB-Fallback.
  * **Saeule 2: Web-Admin Cockpit (`/dashboard/`) fuer Marketing & Verwaltung**
    * **Single Source of Truth Editor:** Mitteilungen und Kalenderevents teilen sich dasselbe relationale Modell (`posts` in PostgreSQL 16 mit 9 bereinigten Tabellen) inkl. Deep Linking (`/dashboard/publicaciones/:id`).
    * **Multimodales KI-Autocomplete:** Plakat-Upload extrahiert per Klick auf `Autocompletar con IA` automatisch Titel, Datum, Uhrzeit, Ort und RSVP-Option.
    * **Governance & Sicherheit:** 6-Rechte Least-Privilege RBAC-Matrix (`publicaciones`, `grupos`, `roles`, `ia`, `apis`, `historial`) und unveraenderliches Audit-Log (`admin_audit_logs`).
* **Sprechvorlage (Spanisch):**
  * *"UPA App resuelve esto mediante una Fuente Unica de Verdad dividida en dos superficies conectadas a un mismo nucleo en FastAPI y PostgreSQL 16."*
  * *"Primero, la PWA estudiantil con login oficial @upa.edu.py, muro unificado con alertas urgentes e Instagram, confirmacion RSVP en un toque y agenda sincronizada con Google Classroom."*
  * *"Segundo, el Web-Admin Cockpit para marketing y administracion, con edicion centralizada, autocompletado multimodal por IA a partir de afiches y control de acceso granular de seis permisos."*

---

### Folie 4: Strategischer Pivot (Pivote Estrategico: Warum PWA statt nativer Android-App)
* **Timing:** `02:10 - 03:00` (50 Sekunden)
* **Folientitel (Spanisch):** `Pivote Estrategico: Por que PWA en lugar de una App Android Nativa`
* **Visuelle Bloecke auf der Folie (3 Entscheidungsachsen):**
  1. **Eliminierung der Store-Huerde (Zero Store Friction):**
     * Keine Apple Developer Gebuehren (99 USD/Jahr + Mac-Zwang) und keine mehrtaegigen Store-Freigabeprozesse.
     * Studierende laden ungern schwere Apps aus Stores fuer Campus-News; per QR-Code ist die PWA in 2 Sekunden offen und als App auf dem Homescreen installierbar (`manifest.webmanifest`, `sw.js` v1.0.3).
  2. **Plattformunabhaengigkeit (100% iOS, Android & Desktop):**
     * Ein grosser Teil der UPA-Studierenden nutzt iPhones (iOS). Eine reine Android-App haette iOS-Nutzer ausgeschlossen oder doppelte Entwicklung erfordert.
     * Eine einzige saubere Codebasis liefert 100 Prozent Funktionsparitaet auf iOS, Android und Desktop.
  3. **Deployment-Geschwindigkeit & KI-Synergie im Backend:**
     * Sofortige Live-Updates ueber den Service Worker ohne manuellen Update-Zwang fuer Nutzer; spaetere Play-Store-Paketierung via Trusted Web Activity (TWA, `assetlinks.json`) ist bereits vorbereitet.
     * Backend in **Python 3.11 (FastAPI)** statt schwergewichtigem Boilerplate: optimale native Integration von Google Gemini KI und schnelle Iteration fuer `< 1.000 Studierende`.
* **Sprechvorlage (Spanisch):**
  * *"Durante el proyecto realizamos un pivote arquitectonico clave: pasar de una aplicacion nativa solo para Android a una Progressive Web App multiplataforma."*
  * *"Tres razones fundamentan esta decision: primero, eliminamos por completo la friccion y costos de las tiendas App Store y Play Store; el alumno escanea un codigo QR y accede en dos segundos."*
  * *"Segundo, garantizamos compatibilidad total con iPhone, Android y escritorio con una sola base de codigo. Y tercero, logramos despliegues instantaneos sin obligar al estudiante a actualizar manualmente."*

---

### Folie 5: Live-Demonstration Leitplan (Guia de Demostracion en Vivo: 5-Minuten User Journey)
* **Timing:** `03:00 - 03:30` (30 Sekunden Folien-Intro) + `03:30 - 08:30` (**5 Minuten Live-Demonstration**)
* **Folientitel (Spanisch):** `Demostracion en Vivo (5 Minutos): El Recorrido Completo del Usuario`
* **Die 4 Stationen der 5-Minuten User Journey (auf der Folie & live vorgefuehrt):**
  1. **Station 1 (`Min 00:00 - 01:00` | Live: `03:30 - 04:30`): QR-Code Scan am Desktop & Login**
     * Aufruf von `https://upa.eu1.netbird.services` am Projektor: Links die interaktive Live-Smartphone-Vorschau, rechts der dynamische QR-Code.
     * Publikum/Dozent kann den QR-Code direkt scannen; Login mit `@upa.edu.py` Google OAuth Account.
  2. **Station 2 (`Min 01:00 - 02:15` | Live: `04:30 - 05:45`): PWA Feed & Eilmeldung**
     * Im Tab `Inicio`: Sichtbarkeit der rot hervorgehobenen **Eilmeldung (Aviso urgente)** ganz oben im Feed.
     * Durchscrollen durch interne UPA-Beitraege und die ueber SociableKIT synchronisierten offiziellen Instagram-Posts (`@upalemana`) sowie Filterung nach Kategorien.
  3. **Station 3 (`Min 02:15 - 03:30` | Live: `05:45 - 07:00`): 1-Klick RSVP & Agenda mit Classroom**
     * Bei einem Event im Feed: Klick auf `Si, asistire` (Zwei-Button-Muster mit `No asistire`, sofortiges visuelles Feedback; Teilnehmerliste ist aus Datenschutzgruenden nur fuer Admins im Cockpit sichtbar).
     * Wechsel in den Tab `Agenda`: Das zugesagte Event erscheint im Monatskalender direkt neben den synchronisierten **Google Classroom Abgabefristen** (Zeitzone `America/Asuncion`). Kurzer Blick in `Perfil` (3-Wege-Theme Hell/Dunkel/System).
  4. **Station 4 (`Min 03:30 - 05:00` | Live: `07:00 - 08:30`): Web-Admin KI-Plakat Extraktion**
     * Wechsel in das Web-Admin Cockpit (`/dashboard/publicaciones/nueva`).
     * Hochladen eines echten Veranstaltungsplakats (Flyer-Bild) und Klick auf den Button **`Autocompletar con IA`**.
     * Vorfuehrung: Das Backend skaliert das Bild optimal, analysiert es multimodal und fuellt in wenigen Sekunden **Titel, Kurztext, Beschreibung, Datum, Start-/Endzeit, Ort und RSVP-Haken** faktengetreu aus.
     * Klick auf `Guardar publicacion` -> sofortige Live-Sichtbarkeit im studentischen PWA-Feed und Eintrag im Audit-Log (`/dashboard/historial`).
* **Sprechvorlage zur Ueberleitung (Spanisch):**
  * *"Pasamos ahora a los cinco minutos de demostracion en vivo sobre nuestro entorno productivo. Recorreremos cuatro estaciones: el acceso por codigo QR, el muro con alertas urgentes, la confirmacion RSVP junto con Google Classroom en la agenda, y finalmente la extraccion automatica de un afiche con Inteligencia Artificial en el Web-Admin."*

---

### Folie 6: Herausforderungen & KI-Entwicklung (Desafios Tecnicos e Ingenieria con IA)
* **Timing:** `08:30 - 09:15` (45 Sekunden, direkt nach Ende der Live-Demo)
* **Folientitel (Spanisch):** `Desafios Tecnicos e Ingenieria Asistida por IA`
* **Visuelle Bloecke auf der Folie:**
  1. **Modell-Wechsel von Flash zu Gemini 4 Argon (Groesstes Learning):**
     * **Anfangsfehler:** In der ersten Projektphase wurde Code mit leichtgewichtigen Flash-Modellen generiert, was bei komplexen Aspekten (OAuth-Flows, State-Synchronisation, Layout) zu Qualitätsproblemen und Halluzinationen fuehrte.
     * **Loesung:** Strikter Wechsel auf **Gemini 4 Argon** fuer die Softwarearchitektur und Entwicklung (Flash-Modelle fuer den Coding-Agenten gesperrt). Im Produktiv-Backend zusaetzlich deterministisches Zero-Hallucination Grounding, 768px Bildoptimierung und `gemma-4-26b-a4b-it` Fallback fuer zuverlässige Antwortzeiten.
  2. **Strikte Zero-Mock Doktrin:**
     * Absolutes Verbot von Dummy-Buttons, statischen Scheindaten oder Mocks im Produktivkern.
     * Automatisierter Gatekeeper-Scanner (`scripts/audit_zero_mock.py`) prueft bei jedem Commit E2E-Persistenz, Timeouts und Healthchecks.
  3. **Autonome Entwicklungsschleife (Closed-Loop Engineering):**
     * Steuerung ueber Multica Issues mit Test-Driven Development: Ueber **230 automatisierte Tests** (Pytest Backend, Node.js PWA & Cockpit Tests, Pyright Typenpruefung, Ruff Linter) muessen vor jedem Merge zu 100 Prozent gruen sein.
* **Sprechvorlage (Spanisch):**
  * *"En cuanto a los desafios de ingenieria, nuestro mayor aprendizaje fue la eleccion del modelo de IA durante el desarrollo. Al inicio probamos modelos rapidos tipo Flash para programar, lo que genero inconsistencias. Cambiamos estrictamente a Gemini 4 Argon bajo desarrollo guiado por pruebas."*
  * *"Aplicamos ademas una doctrina de Cero Mocks verificada automaticamente con mas de 230 pruebas automatizadas en Python y JavaScript antes de cada despliegue."*

---

### Folie 7: Roadmap (Hoja de Ruta: 30 Tage & 6 Monate)
* **Timing:** `09:15 - 10:00` (45 Sekunden + Abschluss)
* **Folientitel (Spanisch):** `Hoja de Ruta (Roadmap): Proximos 30 Dias y 6 Meses`
* **Visuelle Bloecke auf der Folie:**
  1. **Horizont 1: Naechste 30 Tage (UPA Domain & Offizielles Hosting - Go-Live Readiness):**
     * **Offizielles UPA-Hosting & Domain:** Migration der 3 Docker-Container auf die eigene Serverinfrastruktur der UPA unter der offiziellen Subdomain **`app.upa.edu.py`**.
     * **Web-Push Aktivierung:** Scharfschaltung des bereits im Backend vorbereiteten Firebase Cloud Messaging (`backend/src/services/push.py` & Tabelle `device_tokens`) fuer Echtzeit-Push-Alarme bei geschlossener App.
     * **Offizielle Meta Graph API:** Ablösung der manuellen SociableKIT Free-Tier Synchronisation durch einen vollautomatischen Webhook-Sync ueber den offiziellen UPA-Meta-Business-Account.
  2. **Horizont 2: Naechste 6 Monate (Ausbau zum UPA Academico Portal):**
     * **Integration UPA Academico:** Direkte Anbindung an das akademische Kernsystem fuer Noteneinsicht, Pruefungsanmeldung, Kurseinschreibung und offizielle Bescheinigungen direkt in der PWA.
     * **Interaktives Campus-Leben & TWA Store-Listing:** Raumreservierung fuer Lerngruppen, digitaler Studierendenausweis mit QR-Verifikation sowie optionale Bereitstellung im Google Play Store mittels Trusted Web Activity (`assetlinks.json`).
* **Sprechvorlage (Spanisch):**
  * *"Para concluir, nuestra hoja de ruta se divide en dos horizontes concretos. En los proximos 30 dias, el objetivo es migrar los contenedores al servidor oficial de la universidad bajo el dominio app.upa.edu.py, activar las notificaciones push con Firebase y conectar la API oficial de Meta."*
  * *"A seis meses, la arquitectura modular permite evolucionar la aplicacion hacia el Portal UPA Academico completo, integrando calificaciones, inscripcion a materias y carnet estudiantil digital. Muchas gracias, quedamos atentos a sus preguntas."*

---

## 3. Optimierter Prompt fuer die Google Slides Gemini Sidebar

Der folgende Prompt ist speziell fuer die **Google Slides Gemini Sidebar** (*"Hilf mir beim Visualisieren"* / *"Create a slide"* / *"Ask Gemini in Google Slides"*) optimiert. Pascal kann entweder den **Master-Prompt (Variante A)** fuer das gesamte Deck oder die **Einzelfolien-Prompts (Variante B)** direkt in die Sidebar kopieren, um alternative Layouts, Infografiken oder Design-Varianten per Klick zu generieren.

### Variante A: Direkt-Prompt fuer die Google Slides Gemini Sidebar (Komplettes 7-Folien-Deck / Redesign)

```text
Actua como un disenador ejecutivo de presentaciones tecnologicas universitarias. Genera o mejora una presentacion compacta de exactamente 7 diapositivas en espanol para la defensa final del proyecto "UPA App: Plataforma Digital y Campus Movil" de la Universidad Paraguayo Alemana (UPA).

Reglas de Diseno Visual (Identidad Corporativa UPA):
- Paleta de colores estricta: Verde Institucional UPA (#6C9339), Azul Marino Oscuro (#0F172A), Azul Academico (#1E40AF), Fondo Claro Limpio (#F8FAFC) y Tarjetas Blancas (#FFFFFF) con bordes suaves (#CBD5E1).
- Tipografia limpia sin serifas (Inter o Arial), alto contraste, estilo ejecutivo moderno con tarjetas (cards), insignias de tiempo (badges) y maximo 4 puntos concisos por bloque.
- Formato de la exposicion: 10 minutos en total (5 minutos de explicacion en diapositivas + 5 minutos de demostracion en vivo).

Estructura exacta de las 7 diapositivas:
1. Portada: "UPA App: Plataforma Digital y Campus Movil" - Fuente Unica de Verdad (Single Source of Truth) para la Universidad Paraguayo Alemana. Autores: Pascal Thommen, Theresa Bauer, Natasha Colman. Fecha: Jueves, 5 de noviembre de 2026.
2. Problema y Audiencia Objetivo: Comunicacion fragmentada en WhatsApp, Instagram (@upalemana), correo y Google Classroom para menos de 1.000 estudiantes. Tres dolores reales: perdida de avisos urgentes, personal recorriendo aula por aula para recordar eventos, y falta de registro RSVP unificado. Beneficio directo para estudiantes y personal de marketing.
3. La Solucion (Single Source of Truth): Dos superficies conectadas a FastAPI (Python 3.11) y PostgreSQL 16 (9 tablas depuradas). Columna 1: Campus PWA (Login Google OAuth @upa.edu.py, muro unificado con alertas e Instagram, RSVP de 1 clic Si/No, Agenda con Google Classroom en America/Asuncion). Columna 2: Web-Admin Cockpit (Editor unificado con Deep Linking, Autocompletar con IA multimodal para afiches, matriz RBAC de 6 permisos e Historial de auditoria).
4. Pivote Estrategico (PWA vs. Android Nativo): Tabla comparativa en 3 ejes: (1) Cero friccion de tiendas (sin costos de App Store ni esperas de revision, acceso en 2 segundos por codigo QR), (2) Independencia de plataforma (100% compatible con iPhone iOS, Android y escritorio con un solo codigo), (3) Velocidad de despliegue (actualizaciones instantaneas via Service Worker v1.0.3 y soporte TWA para Play Store).
5. Guia de Demostracion en Vivo (5 Minutos User Journey): Linea de tiempo visual con 4 pasos numerados: Paso 1: Escaneo de codigo QR en la Landing Page de escritorio y login @upa.edu.py (1 min). Paso 2: Muro PWA y banner de aviso urgente fijado + feed de Instagram (1:15 min). Paso 3: Confirmacion RSVP en 1 clic y Agenda mensual sincronizada con Google Classroom (1:15 min). Paso 4: Web-Admin Cockpit subida de afiche y extraccion automatica con el boton "Autocompletar con IA" (1:30 min).
6. Desafios Tecnicos y Desarrollo con IA: Tres bloques de ingenieria: (1) Evolucion de modelos IA: transicion de modelos Flash iniciales (propensos a errores) hacia Gemini 4 Argon con anclaje factual sin alucinaciones y respaldo gemma-4-26b-a4b-it, (2) Doctrina Zero-Mock (cero datos falsos en produccion, verificada por auditor automatico), (3) Ciclo autonomo de calidad con mas de 230 pruebas automatizadas (Pytest, Node.js, Pyright, Ruff).
7. Hoja de Ruta (Roadmap): Dos horizontes visuales: Horizonte 30 Dias (Dominio oficial app.upa.edu.py, alojamiento en servidor UPA, activacion de notificaciones Web-Push FCM y API oficial de Meta) y Horizonte 6 Meses (Integracion con el Portal UPA Academico para calificaciones, inscripciones, encuestas y carnet digital).
```

### Variante B: Schnell-Prompts fuer einzelne Folien-Grafiken in Google Slides Gemini ("Help me visualize")

* **Prompt fuer Folie 3 (Architektur-Schaubild generieren):**
  ```text
  Crea un diagrama limpio de arquitectura moderna en formato horizontal con colores #0F172A (azul marino), #6C9339 (verde UPA) y #1E40AF (azul): a la izquierda dos tarjetas de clientes ("Campus PWA Movil" y "Web-Admin Cockpit"), en el centro un bloque "Nginx Reverse Proxy + FastAPI Python 3.11", y a la derecha "PostgreSQL 16 (9 Tablas)" conectado a "Google OAuth / Classroom / Gemini IA / Instagram".
  ```
* **Prompt fuer Folie 5 (Live-Demo Timeline als Infografik):**
  ```text
  Disena una infografia horizontal de proceso en 4 pasos numerados (5 minutos en total) con estilo corporativo limpio en verde #6C9339 y azul oscuro #0F172A: 1. Escaneo QR en Escritorio (01:00), 2. Feed PWA y Alerta Urgente (01:15), 3. Agenda y RSVP 1-Clic (01:15), 4. Web-Admin Extractor IA de Afiches (01:30).
  ```
* **Prompt fuer Folie 7 (Roadmap 30 Tage vs. 6 Monate):**
  ```text
  Crea una diapositiva de hoja de ruta (Roadmap) con dos tarjetas grandes comparativas: a la izquierda "30 Dias: Go-Live Institucional" (Dominio app.upa.edu.py, Servidor UPA, Push FCM, Meta API) en verde #6C9339, y a la derecha "6 Meses: Portal UPA Academico" (Calificaciones, Inscripcion a Materias, Carnet Digital, Play Store TWA) en azul #1E40AF sobre fondo blanco.
  ```
