# Bitácora de Desarrollo, Decisiones y Avances (Logbook)
## Proyecto: UPA App &bull; Plataforma Digital Universitaria
**Universidad Paraguayo Alemana (UPA)**  
**Repositorio Oficial:** https://github.com/Pascal-Thommen/upa-app  
**Equipo:** Pascal Thommen (Backend & Infraestructura), Equipo de Desarrollo Móvil (Frontend Móvil Android), Natasha Kolman  

---

## 1. Propósito de este Logbook
Este documento constituye el registro maestro cronológico de la plataforma UPA App. Su finalidad es documentar de forma continua:
* Las decisiones arquitectónicas y técnicas acordadas por el equipo.
* Los avances implementados y verificados en el código.
* La base de hechos para los informes semanales de avance y la actualización progresiva del documento de especificación formal (de v2 a v3).

---

## 2. Registro Histórico: Semana 1 (Cierre Viernes 23 de Octubre 2026 &bull; Versión v2)
*Documentación presentada oficialmente: `Avances Semanal 10.23.pdf` y `UPA-App v2.pdf`.*

### Decisiones Arquitectónicas Formalizadas:
1. **Frontend Móvil Nativo Android en lugar de PWA:**  
   Se determinó de forma definitiva desarrollar la solución móvil como aplicación nativa Android utilizando Kotlin, Jetpack Compose y almacenamiento local con Room/SQLite, descartando la alternativa de Progressive Web App (PWA).
2. **Modelo de Persistencia Dual:**  
   PostgreSQL actúa como base de datos relacional central en el servidor para concurrencia y consistencia global, mientras que SQLite/Room opera como motor local en el dispositivo móvil para soporte offline y caché rápido.
3. **Desacoplamiento de Contenedores:**  
   Se definió independizar el frontend web en su propio contenedor de staging y producción, separando la capa estática del núcleo de la API en FastAPI.
4. **Seguridad y Red Zero-Trust:**  
   Infraestructura conectada mediante la red privada mallada NetBird (`upa.eu1.netbird.services`), blindando el acceso administrativo.

### Hitos Implementados y Verificados (Semana 1):
* **Backend y Base de Datos:** PostgreSQL en contenedor Docker, esquemas SQLAlchemy, migraciones versionadas con Alembic y API REST FastAPI con Swagger interactivo en `/docs`.
* **Identidad y Acceso:** Inicio de sesión exclusivo con Google OAuth 2.0 (`@upa.edu.py`) y emisión de tokens JWT.
* **Integraciones Externas:** Feed de Instagram mediante SociableKIT, consulta de grupos de Google Workspace Admin Directory API y sincronización inicial de cursos de Google Classroom.
* **Contenido y Eventos:** Endpoints CRUD para noticias y eventos, sistema de confirmación de asistencia (RSVP) y subida de archivos multimedia hasta 10 MB en `/api/media/upload`.
* **App Móvil (Android Nativo):** Proyecto base estructurado en Android Studio con Kotlin y Compose listo para consumir la API REST.

---

## 3. Registro Actual: Semana 2 (Hacia la Entrega Viernes 30 de Octubre 2026 &bull; Versión v3)

### Tarea Especial / Pendiente de Documentación:
* **Inclusión del Portal Web-Admin:**  
  La implementación del Portal Web-Admin y Cockpit Editorial (gestión de contenidos, afiches, eventos y diagnóstico de APIs) no formó parte del informe del 23 de octubre. Queda formalmente registrada para su inclusión completa en el informe semanal del 30 de octubre y en el documento de arquitectura v3.

### Decisiones y Modificaciones Técnicas en Curso:
1. **Reestructuración de la Interfaz Web con Menú Lateral:**  
   * **Sección Estudiantil (Próximamente):** Panel reservado sin botones simulados, indicando el desarrollo de la app móvil nativa en curso.  
   * **Módulo A (Publicaciones y Eventos):** Consolidación unificada de noticias y eventos con insignias distintivas (`Noticia`, `Evento`, `Noticia + Evento`), carga de afiches hasta 10 MB y tabla en vivo de participantes confirmados (RSVP).  
   * **Módulo B (Grupos y Audiencias):** Gestión de grupos internos (`Estudiantes`, `Docentes`, `Staff`, `Egresados`) y asignación de correos `@upa.edu.py` o grupos de Google Workspace Admin Console.  
   * **Módulo C (Consola de Administradores):** Gestión granular de permisos por correo para las herramientas administrativas.  
   * **Módulo D (Diagnóstico de APIs para Desarrolladores):** Panel técnico restaurado para pruebas de backend.
2. **Corrección de Diagnóstico de Grupos de Google:**  
   * Eliminación de las etiquetas sintéticas (`ALL`, `TIE`) en el panel de desarrollador de Google Mailgruppen.  
   * Visualización fidedigna y estricta de los 3 grupos reales obtenidos de Google Workspace Directory API (`user.google_groups`: *Estudiantes - Activos*, *Estudiantes TIE 2025*, *Ing. Tecnologías - TODOS*).
3. **Persistencia y Renovación Continua de Google Classroom:**  
   * Actualización del flujo OAuth de Google en `/api/auth/login-google` incorporando `prompt=consent select_account` y `access_type=offline`. Esto asegura la entrega persistente del `refresh_token` y previene errores 401 en la lectura de tareas y fechas límite.
4. **Desacoplamiento Integral de Contenedores (SRV-150):**  
   * Separación física del frontend web en su propio contenedor independiente `upa-frontend` (Nginx Alpine) eliminando archivos estáticos de la imagen de producción de FastAPI.
   * Configuración de Nginx como Reverse Proxy en el puerto `8085` de la red NetBird: sirve el portal `/dashboard/` de manera estática y reenvía transparentemente el tráfico de `/api/`, `/health`, `/docs` y `/uploads/` hacia `http://backend:8000`.
   * Preservación intacta del flujo de autenticación Google OAuth 2.0 y su URI de redirección (`https://upa.eu1.netbird.services/api/auth/google`).
   * Infraestructura final en 3 contenedores productivos: `upa-postgres`, `upa-backend` y `upa-frontend`.
5. **Hardening y Rediseño Institucional del Portal Web-Admin (SRV-152):**  
   * Corrección del diagnóstico de Google Mailgruppen (API 2): los grupos llegan como objetos `{id, name, email, description}` y se mostraban como `[object Object]`; ahora se renderizan con nombre y correo reales (`web-admin/portal-core.js`).
   * Google OAuth: `/api/auth/login-google` ya no fuerza el consentimiento en cada acceso (`prompt=select_account`, `include_granted_scopes=true`). El consentimiento se solicita una sola vez, cuando el usuario no tiene `refresh_token` almacenado (o con `?consent=true`), y la renovación automática de Classroom sigue operando con ese token.
   * Eliminación del parpadeo de login: el script de arranque leía la clave `upa_auth_token` y estilos de ids inexistentes; ahora usa `upa_access_token`, oculta la página con `auth-pending` hasta validar la sesión y revela directamente el panel. Las cargas de perfil y salud del backend corren en paralelo y se eliminó el `@import` bloqueante de la fuente.
   * Identidad UPA: logotipo (`web-admin/logo-upa.svg`), verde oliva del campus (`#779a0b`) y tarjetas minimalistas (`web-admin/institutional.css`). Se eliminaron textos de marketing y mezclas de idioma.
