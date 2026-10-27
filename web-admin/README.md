# Portal de Administracion Web y Dashboard Institucional (Escritorio)

Panel web institucional y sistema de gestión para la Universidad Paraguayo Alemana (UPA).

## Responsabilidades y Funciones
* **Publicaciones (`/dashboard/publicaciones`):** Editor unificado para noticias, eventos e ítems híbridos con título obligatorio, publicación programada opcional (`ed-pub-scheduled`), inscripción RSVP desactivada por defecto, notificación push (`Notificar por push`), carga centralizada de foto o video (`JPG`, `PNG`, `WEBP`, `MP4`, `WEBM`, `PDF`), texto principal único (`ed-pub-content`), fecha de vigencia obligatoria al fijar en el feed (`ed-pub-pinned` + `ed-pub-expires`), recordatorios flexibles en minutos, horas o días y protección de solo lectura para publicaciones sincronizadas de Instagram (con resumen automático de dos líneas).
* **Grupos (`/dashboard/grupos`):** Lista plana ordenada alfabéticamente de audiencias y grupos reales de Google Workspace (`@upa.edu.py`) con filtro instantáneo en vivo y caché local en el backend para Google Directory API.
* **Roles (`/dashboard/roles`):** Matriz interactiva de permisos por módulo (`publicaciones`, `grupos`, `roles`, `apis`) con todas las casillas desmarcadas por defecto al autorizar una nueva cuenta institucional y sin botones de acceso rápido de desarrollo en la vista de inicio de sesión.
* **APIs (`/dashboard/apis`):** Estado en vivo de integraciones (Google OAuth, Google Directory, Google Classroom, Instagram Graph), cursos y entregas reales de Classroom y telemetría técnica.

## Componentes y Arquitectura
* `index.html`: Interfaz SPA con barra lateral de 4 módulos dinámicos según permisos.
* `editorial-core.js`: Validación pura, construcción de payloads, conversión de unidades de recordatorios, detección automática de imagen/video y cliente REST con timeout.
* `editorial.js`: Controlador del editor unificado de publicaciones, barrera de protección de Instagram y carga multimedia.
* `app.js`: Autenticación institucional `@upa.edu.py`, enrutador SPA (`UpaRouter`), gestión alfabética de grupos con filtro instantáneo y matriz de roles.
* `style.css` y `editorial.css`: Estilos institucionales e indicadores de estado.

## Ejecución
El portal es servido automáticamente por el backend en `/dashboard/` y `/admin/`, o de forma independiente mediante cualquier servidor web estático.
