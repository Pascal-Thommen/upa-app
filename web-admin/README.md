# Portal de Administracion Web y Dashboard Institucional (Escritorio)

Panel web institucional y sistema de gestión para la Universidad Paraguayo Alemana (UPA).

## Responsabilidades y Funciones
* Panel de control (Dashboard) con visualización de perfil verificado `@upa.edu.py`.
* Segmentación y visualización de grupos de Google Workspace (Mailgruppen: nombre y correo de cada grupo real).
* Integración bidireccional con Google Classroom: Cursos activos, asignaciones, tareas y fechas límite (deadlines).
* Acceso directo mediante enlaces a Google Classroom oficial para estudiantes y docentes.
* Conexión directa y resiliente contra la API REST del backend bajo estándar Zero-Mock.

## Componentes y Arquitectura
* `index.html`: Shell de la aplicación de una sola página (SPA) con diseño adaptativo.
* `app.js`: Lógica de autenticación, manejo de sesiones JWT y llamadas REST a endpoints del backend (`/api/auth/me`, `/api/classroom/deadlines`, `/api/classroom/courses`).
* `portal-core.js`: Lógica pura (grupos de Google Workspace, detección de sesión) usada por `app.js` y por las pruebas de Node.js.
* `style.css` e `institutional.css`: Estilos visuales institucionales (verde oliva UPA, tarjetas minimalistas) e indicadores de estado.
* `logo-upa.svg`: Logotipo institucional (UPA, Heidelberg - Asunción). Reemplazar por el archivo oficial vectorial si se dispone de él.

## Ejecución
El portal es servido automáticamente por el backend en `/dashboard/` y `/admin/`, o de forma independiente mediante cualquier servidor web estático.
