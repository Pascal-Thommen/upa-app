# Android Applikation (Android Studio)

Natives Android-Frontend fuer Studierende und Dozenten der UPA.

## Technische Basis
* Sprache: Kotlin / Java
* Mindest-SDK: Android 8.0 (API Level 26)
* Ziel-SDK: Android 14+ (API Level 34)
* Architektur: MVVM (Model-View-ViewModel) mit Jetpack Compose oder XML Layouts.

## Menue-Struktur
1. `Inicio`: Campus-Feed, Eilmeldungs-Banner, Instagram-News, Charlas mit Anmeldebutton.
2. `Agenda`: Chronologische Terminliste oben, synchronisierter Monatskalender mit Punkten unten.
3. `Perfil`: Dark/Light Mode Umschalter, Filterkriterien, Nutzerinformationen.

## Kommunikation mit dem Backend
Das Android-Team greift auf die REST-API unter `http://<SERVER_IP>:8000/api/v1` zu.
Die interaktive Spezifikation der Endpunkte ist unter `/docs` einsehbar.
