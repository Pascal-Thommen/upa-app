# Bitácora de Decisiones Arquitectónicas y Evolución Técnica (LOGBOOK)

Este documento constituye el registro maestro cronológico de la evolución técnica, decisiones arquitectónicas, estándares de desarrollo y modificaciones críticas de la plataforma **UPA App** de la Universidad Paraguayo Alemana.

---

### Registro Cronológico de Hitos y Decisiones

1. **Arquitectura Base y Conexión OAuth 2.0 (Google Workspace / OIDC):**  
   * Establecimiento del protocolo de autenticación federada con Google Workspace mediante OAuth 2.0 para el dominio institucional `@upa.edu.py`.  
   * Configuración de la Service Account delegada para consulta de grupos (`admin.directory.group.readonly`).  
   * Separación de roles: `admin` (gestión institucional y redacción) y `user` (estudiantes/docentes).
2. **Sincronización Asíncrona con Google Classroom:**  
   * Integración de la API de Google Classroom (`courses.readonly`, `coursework.me.readonly`) con tokens offline delegados.  
   * Implementación de sincronización periódica en segundo plano para entrega de tareas y plazos académicos (`deadlines`) directamente agregados en la vista móvil.
3. **Módulo Editorial y Feed Institucional:**  
   * Rediseño del panel de redacción para creación de noticias y eventos universitarios con soporte de RSVP.  
   * Sincronización automática de publicaciones desde Instagram Graph API (`instagram_service.py`).
4. **Desacoplamiento en Microservicios y Contenedor Frontend Dedicado Nginx (SRV-150):**  
   * Desacoplamiento de la arquitectura monolítica original (donde FastAPI servía directamente los archivos estáticos de la interfaz web) hacia una arquitectura moderna de 3 capas.  
   * Contenedor Nginx Alpine optimizado para servir exclusivamente el portal administrativo (`web-admin`) y actuar como reverse proxy hacia el backend FastAPI (`http://backend:8000`).  
   * Preservación intacta del flujo de autenticación Google OAuth 2.0 y su URI de redirección (`https://upa.eu1.netbird.services/api/auth/google`).  
   * Infraestructura final en 3 contenedores productivos: `upa-postgres`, `upa-backend` y `upa-frontend`.
5. **Hardening de Producción y Rediseño Institucional UPA (SRV-152):**  
   * Incorporación del logotipo oficial de la UPA (Heidelberg - Asunción) y paleta institucional en verde oliva (#6c9339) en concordancia visual con la aplicación móvil.  
   * Corrección definitiva del bug de renderizado en API 2 (Google Mailgruppen), extrayendo propiedades de nombre y correo para eliminar el formato `[object Object]`.  
   * Optimización del flujo Google OAuth: cambio de `prompt=consent select_account` a `prompt=select_account`, eliminando la solicitud repetitiva de permisos cuando el usuario ya autorizó el acceso, preservando el `refresh_token` offline en PostgreSQL.  
   * Eliminación del parpadeo de inicio de sesión mediante detección inmediata de token en `localStorage`, cargando la interfaz administrativa de forma instantánea.  
   * Supresión radical de textos artificiales o marketing accesorio, adoptando un diseño minimalista y profesional.
6. **Purga Radical de AI Slop, Separación de Diagnóstico y Alineación Visual con App UPA (SRV-153):**  
   * **Encabezado institucional:** Eliminación definitiva de insignias de estado de APIs y etiquetas "EN VIVO", conservando logotipo oficial, título institucional y avatar con acción de logout.  
   * **Barra lateral sobria:** Supresión de tarjeta informativa sobre stack móvil Kotlin/Compose y sustitución de emojis por iconografía SVG minimalista.  
   * **Separación de diagnóstico y títulos funcionales:** Reubicación de visores y botones de volcado JSON al módulo exclusivo de Diagnóstico de APIs. Reemplazo de títulos técnicos de backend por títulos orientados a la gestión académica y universitaria.  
   * **Agenda académica estilo app móvil:** Lista cronológica limpia con insignias de fecha (ej. VIE 16, VIE 23) idéntica a la interfaz nativa.  
   * **Control de caché:** Cabeceras HTTP `Cache-Control: no-cache, must-revalidate` en Nginx y versionado `?v=1.1.0` en scripts y estilos.
7. **Enrutamiento URL Dedicado por Módulo y Persistencia de Subrutas (SRV-155):**  
   * **Enrutador History API:** Direcciones dedicadas para cada módulo (`/dashboard/publicaciones`, `/dashboard/grupos`, `/dashboard/roles`, `/dashboard/diagnostico`, `/dashboard/estudiantes`).  
   * **Navegación nativa:** Actualización fluida de la barra del navegador, historial de navegación (`popstate`) y persistencia del módulo activo tras recarga (F5).  
   * **Compatibilidad de enlaces directos (Deep Linking):** Soporte en Nginx y backend FastAPI para resolver y cargar directamente cualquier pestaña solicitada sin error 404, redirigiendo rutas no reconocidas a `/dashboard/publicaciones`.
8. **Persistencia Real en PostgreSQL para Grupos, Roles y Diagnóstico Técnico (SRV-157 - Zero Facade):**  
   * **Eliminación total de fachadas mock:** Supresión definitiva de llaves simuladas en `localStorage` (`upa_app_groups_v1` y `upa_app_admins_v1`).  
   * **Modelos relacionales en PostgreSQL:** Creación de tablas `audience_groups` y `user_roles` con inicialización semilla (seed) para grupos de sistema (`estudiantes`, `docentes`, `staff`, `egresados`) y administrador primario (`pascal.thommen@upa.edu.py`).  
   * **Endpoints REST en FastAPI:** Controladores `/api/groups` (GET, POST, DELETE), `/api/roles` (GET, POST, DELETE) con validación de dominios `@upa.edu.py` y protección de entidades críticas de sistema, junto con `/api/system/diagnostics` para telemetría en vivo del pool de base de datos y APIs externas.  
   * **Integración asíncrona en cliente web:** Sincronización transparente de grupos y roles contra backend real y vinculación dinámica en el formulario de redacción editorial.
9. **Refactorización UX Institucional, Unificación Editorial, Tablas de Grupos/Roles y Vista Aplicación (SRV-159):**  
   * **Encabezado compacto y menú interactivo de perfil:** Reducción de altura del encabezado eliminando duplicaciones visuales. Sustitución de la tarjeta fija de perfil por un menú flotante (dropdown) accesible al hacer clic en el avatar, con estado de cuenta, sincronización de Google Classroom, actualización manual y cierre de sesión.  
   * **Módulo unificado de Publicaciones y Eventos:** Ubicación de las tablas de contenidos en primer plano con miniaturas de afiches ampliadas (`5.5rem` / 88px) para máxima legibilidad. Formularios de redacción y programación colapsables mediante botones de acción directa (`+ Redactar Noticia`, `+ Programar Evento`).  
   * **Tabla administrativa y edición completa de Grupos:** Sustitución de tarjetas por tabla de datos de ancho completo con soporte de actualización directa (`PUT /api/groups/{id}`) en PostgreSQL mediante panel desplegable (`group-edit-panel`).  
   * **Matriz de permisos por casillas de verificación (Roles):** Reorganización de la consola de roles con casillas interactivas por módulo (`Publicaciones y Eventos`, `Grupos y Audiencias`, `Gestión de Roles`, `Diagnóstico de APIs`), barra superior simplificada de autorización y acción de revocación con icono de papelera.  
   * **Módulo de Vista Aplicación:** Incorporación de la pestaña y subruta `/dashboard/app` como vista previa reservada para la aplicación móvil del campus.  
   * **Telemetría en tiempo real:** Integración de tarjetas estructuradas para estado y latencia de PostgreSQL, sincronización de directorios Google Workspace, Classroom y certificación de doctrina Zero-Mock.
