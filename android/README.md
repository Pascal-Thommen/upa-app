# Aplicacion Android (Android Studio)

Frontend movil nativo para estudiantes y docentes de la UPA.

## Base Tecnica
* Lenguaje: Kotlin / Java
* SDK Minimo: Android 8.0 (API Level 26)
* SDK Objetivo: Android 14+ (API Level 34)
* Arquitectura: MVVM (Model-View-ViewModel) con Jetpack Compose o XML Layouts.

## Estructura de Navegacion (3 Menus)
1. `Inicio`: Feed del campus, banner de avisos de emergencia, publicaciones de Instagram, charlas con boton de inscripcion.
2. `Agenda`: Lista cronologica superior y calendario mensual sincronizado con puntos de actividad inferior.
3. `Perfil`: Selector de modo oscuro/claro, preferencias de usuario e informacion de perfil.

## Comunicacion con el Backend
El equipo de Android se conecta a la API REST en `http://<SERVER_IP>:8000/api/v1`.
La especificacion interactiva de los endpoints se encuentra disponible en `/docs`.
