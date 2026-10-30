# UPA Campus PWA

Aplicacion web progresiva (PWA) para estudiantes y docentes de la Universidad Paraguayo Alemana (`@upa.edu.py`), compatible con Android (Chrome y Trusted Web Activity) e iOS (Safari).

## Estructura

* `index.html`: Shell de la aplicacion movil y pagina de bienvenida para escritorio con codigo QR dinamico.
* `campus.css`: Estilos mobile first con soporte de zonas seguras (`safe-area-inset-*`) y tema claro, oscuro o del sistema.
* `campus-core.js`: Logica de fechas (`America/Asuncion`), cliente de API con tiempos de espera, cache por usuario y generacion de QR.
* `campus.js`: Controlador de interfaz para `Inicio`, `Agenda` y `Perfil`.
* `sw.js`: Service Worker que precachea el shell estatico para apertura sin conexion.
* `manifest.webmanifest`: Manifiesto web con `display: "standalone"` e iconos adaptables (`maskable`).
* `.well-known/assetlinks.json`: Enlaces digitales de activos para empaquetado TWA en Google Play.

## Pruebas

```bash
cd web-app/tests
npm test
```
