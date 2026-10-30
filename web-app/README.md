# UPA Campus PWA (`web-app/`)

Progressive Web App (PWA) fuer Studierende und Dozierende der Universidad Paraguayo Alemana (`@upa.edu.py`), kompatibel mit Android (Chrome und Trusted Web Activity) sowie iOS (Safari Homescreen Web App).

## Dateistruktur

* `index.html`: Mobile App Shell (`Inicio`, `Agenda`, `Perfil`) und Desktop Landingpage mit Smartphone Vorschau (`phone-mockup`), dynamischem QR Code und dezentem Admin Link (`Acceso Administrativo`).
* `campus.css`: Mobile First Stylesheet mit Safe Area Unterstuetzung (`env(safe-area-inset-*)`), kompaktem Monatskalender (`grid-auto-rows: 30px`) und 3 Wege Theme System (`system`, `light`, `dark`).
* `campus-core.js`: Zeitzonenlogik (`America/Asuncion`), typisierter REST Client mit Timeout (`12000 ms`), JWT Fragment Parser (`parseAuthFragment`), nutzergebundener LocalStorage Cache (`upa_campus_cache_*`) und SVG QR Generator (`buildQr`).
* `campus.js`: UI Controller fuer Feed, Event RSVP, Kalenderfilter, Vollbild Detailansicht, Android Zurueck Navigation und Installationsbanner.
* `sw.js`: Service Worker fuer das Precache der statischen App Shell (`upa-campus-shell-1.0.0`).
* `manifest.webmanifest`: Web App Manifest mit `display: "standalone"` und adaptiven Icons (`any` und `maskable`).
* `.well-known/assetlinks.json`: Digital Asset Links fuer Android Trusted Web Activity (TWA).

## Automatisierte Tests

```bash
cd web-app/tests
npm test
```
