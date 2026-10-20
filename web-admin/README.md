# Portal de Administracion Web y Dashboard Institucional (Escritorio)

Panel web institucional y sistema de gestión para la Universidad Paraguayo Alemana (UPA).

## Responsabilidades y Funciones
* Panel de control (Dashboard) con visualización de perfil verificado `@upa.edu.py`.
* Segmentación y visualización de grupos de Google Workspace (Mailgruppen: `ALL`, `TIE`, `PI`, `TI`, `PROF`).
* Integración bidireccional con Google Classroom: Cursos activos, asignaciones, tareas y fechas límite (deadlines).
* Acceso directo mediante enlaces a Google Classroom oficial para estudiantes y docentes.
* Conexión directa y resiliente contra la API REST del backend bajo estándar Zero-Mock.

## Componentes y Arquitectura
* `index.html`: Shell de la aplicación de una sola página (SPA) con diseño adaptativo.
* `app.js`: Lógica de autenticación, manejo de sesiones JWT y llamadas REST a endpoints del backend (`/api/auth/me`, `/api/classroom/deadlines`, `/api/classroom/courses`).
* `style.css`: Estilos visuales institucionales e indicadores de estado.

## Ejecución
El portal es servido automáticamente por el backend en `/dashboard/` y `/admin/`, o de forma independiente mediante cualquier servidor web estático.
