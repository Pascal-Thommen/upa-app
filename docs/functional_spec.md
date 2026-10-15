# UPA App: Funktionsspezifikation

## 1. Technologiestack & Begruendung Python (FastAPI)
* 60 Prozent weniger Boilerplate als Java, Fokus liegt auf Termintreue und MVP-Fertigstellung.
* Schlanke Anbindung von Google Workspace Admin SDK, Classroom API und Social Media Feeds.
* Automatisch generierte Swagger-Dokumentation (/docs) fuer das Android Studio Team.

## 2. Strukturierte Kernfunktionen

### Modul Inicio (Campus-Feed)
* Dringlichkeits-Eilmeldungen als Banner bei kurzfristigen Ereignissen (z.B. Hagel, Unwetter).
* Campus-Events und Fachvortraege (Charlas) mit nativer Ein-Klick-An- und Abmeldung.
* Social Media Aggregation der offiziellen Universitaetskanaele via SociableKIT / Instagram API.

### Modul Agenda (Termine & Fristen)
* Chronologische Liste anstehender Termine oben, synchronisierter Monatskalender mit Terminpunkten unten.
* Automatische Uebernahme akademischer Fristen via Google Classroom.

### Modul Profil & Personalisierung
* Google OAuth Zwangsanmeldung fuer @upa.edu.py Adressen.
* Verwaltung von Dark/Light Mode, Benachrichtigungseinstellungen und Studiengangsfilter.

### Modul Web-Administration (Marketing Desktop)
* Single Source of Truth: Einheitliches Datenmodell fuer News und Kalenderereignisse.
* Zielgruppen-Filterung basierend auf Google Workspace Gruppen.
