# UPA App Backend - Documentación de la API REST

Documentación completa de endpoints para el equipo de desarrollo de clientes móviles (Android / Kotlin).
Estándar Zero-Mock: Todos los endpoints están productivamente implementados, tipados y conectados a PostgreSQL 16.

## URL Base
* Servicio Público NetBird (HTTPS con SSL): `https://upa-2vgh.eu1.netbird.services`
* Swagger UI público: `https://upa-2vgh.eu1.netbird.services/docs`
* Red interna NetBird Mesh: `http://acersrv.netbird.cloud:8000` o `http://100.110.128.107:8000`
* Desarrollo local: `http://localhost:8000`
* Interfaz interactiva Swagger UI: `http://localhost:8000/docs`
* Especificación OpenAPI: `http://localhost:8000/openapi.json`

---

## 1. Sistema y Diagnóstico (Healthcheck)

### `GET /health`
Verifica la disponibilidad operativa del backend y la conexión a la base de datos.

**Respuesta (200 OK):**
```json
{
  "status": "healthy",
  "environment": "production",
  "service": "upa-app-backend"
}
```

---

## 2. Autenticación y Perfil de Usuario

### `POST /api/auth/google`
Autentica al usuario mediante el ID Token emitido por Google Sign-In en Android. Aplica restricción obligatoria al dominio institucional `@upa.edu.py`.

**Cuerpo de la Petición:**
```json
{
  "id_token": "eyJhbGciOiJSUzI1NiIs...",
  "classroom_access_token": "ya29.a0AfH6SM..."  // Opcional para sincronización de Classroom
}
```

**Respuesta (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "estudiante@upa.edu.py",
    "full_name": "Nombre de Estudiante",
    "role": "user",
    "groups": ["TIE", "Semester_4"]
  }
}
```

### `GET /api/auth/me`
Retorna el perfil del usuario autenticado actualmente.
* **Encabezado:** `Authorization: Bearer <access_token>`

**Respuesta (200 OK):**
```json
{
  "id": 1,
  "email": "estudiante@upa.edu.py",
  "full_name": "Nombre de Estudiante",
  "role": "user",
  "groups": ["TIE", "Semester_4"],
  "created_at": "2026-10-20T14:00:00Z"
}
```

### `POST /api/auth/classroom-token`
Actualiza el token OAuth de Google Classroom para el usuario autenticado.
* **Encabezado:** `Authorization: Bearer <access_token>`

**Cuerpo de la Petición:**
```json
{
  "classroom_token": "ya29.a0AfH6SM..."
}
```

**Respuesta (200 OK):**
```json
{
  "id": 1,
  "email": "estudiante@upa.edu.py",
  "full_name": "Nombre de Estudiante",
  "role": "user",
  "groups": ["TIE", "Semester_4"],
  "has_classroom_token": true
}
```

---

## 3. Feed del Campus y Noticias

### `GET /api/v1/feed`
Retorna el feed institucional consolidado:
* **Modo Público (Sin Autenticación):** Si no se envía token de autorización, entrega exclusivamente los posts públicos de Instagram (@upalemana). Seguro para mostrar en pantallas previas al login.
* **Modo Autenticado:** Si se envía `Authorization: Bearer <access_token>`, entrega el feed completo incluyendo avisos de emergencia (banners superiores), noticias internas y eventos de la comunidad UPA.

* **Encabezado (Opcional):** `Authorization: Bearer <access_token>`
* **Parámetros de Consulta (Query):**
  * `group` (opcional): Filtro por carrera o grupo (ej. `TIE`)
  * `limit` (opcional, por defecto: 20): Cantidad de elementos
  * `offset` (opcional, por defecto: 0): Paginación

**Respuesta (200 OK):**
```json
{
  "urgent_banners": [
    {
      "id": 1,
      "title": "Aviso meteorológico",
      "summary": "Suspensión de actividades presenciales...",
      "content": "Debido al temporal severo...",
      "post_type": "EMERGENCY_BANNER",
      "is_pinned": true,
      "target_groups": ["ALL"],
      "image_url": null,
      "permalink": null,
      "created_at": "2026-10-20T12:00:00Z",
      "published_at": "2026-10-20T12:00:00Z"
    }
  ],
  "posts": [
    {
      "id": 2,
      "title": "📢 ¡Estamos buscando Recepcionista!",
      "summary": "Si sos una persona proactiva y con vocación de atención...",
      "content": "Texto completo del post...",
      "post_type": "INSTAGRAM",
      "is_pinned": false,
      "target_groups": ["ALL"],
      "instagram_id": "DerQoIzjtYf",
      "image_url": "https://data-image.sociablekit.com/sources/instagram-feed/upalemana/DerQoIzjtYf-thumbnail.webp",
      "permalink": "https://www.instagram.com/p/DerQoIzjtYf/",
      "created_at": "2026-10-20T14:00:00Z",
      "published_at": "2026-10-20T14:00:00Z"
    }
  ],
  "total": 51,
  "page": 1,
  "has_more": true
}
```

### `GET /api/news`
Retorna la lista de todas las noticias y avisos institucionales.
* **Seguridad:** Requiere autenticación institucional obligatoria.
* **Encabezado:** `Authorization: Bearer <access_token>`
* **Parámetros de Consulta:** `group`, `limit`, `offset`

---

## 4. Agenda y Calendario de Eventos

### `GET /api/events`
Retorna todos los eventos y conferencias académicas ordenados cronológicamente.
* **Seguridad:** Requiere autenticación institucional obligatoria.
* **Encabezado:** `Authorization: Bearer <access_token>`
* **Parámetros de Consulta:**
  * `group` (opcional): Filtro por carrera (ej. `TIE`)
  * `upcoming_only` (opcional, por defecto: `true`): Filtrar solo eventos futuros
  * `limit` (opcional, por defecto: 20)
  * `offset` (opcional, por defecto: 0)

**Respuesta (200 OK):**
```json
[
  {
    "id": 3,
    "title": "¿Qué significa seguir siendo humanos en la era de la IA?",
    "summary": "Charla magistral de Daniel Romero sobre IA en la UPA",
    "event_start": "2026-10-21T18:00:00Z",
    "event_end": "2026-10-21T20:00:00Z",
    "location": "Auditorio Edificio 1",
    "has_registration": true,
    "target_groups": ["ALL", "TIE"],
    "created_at": "2026-10-20T10:00:00Z"
  }
]
```

---

## 5. Integración con Google Classroom

### `GET /api/classroom/courses`
Retorna la lista de cursos académicos activos del estudiante o docente directamente desde Google Classroom.
* **Encabezado:** `Authorization: Bearer <access_token>`

**Respuesta (200 OK):**
```json
[
  {
    "id": "12345678",
    "name": "Ingeniería de Software II",
    "section": "Semestre 4 - Turno Noche",
    "alternate_link": "https://classroom.google.com/c/12345678",
    "room": "Aula 204"
  }
]
```

### `GET /api/classroom/deadlines`
Retorna las tareas, entregas y plazos académicos activos del estudiante autenticado directamente desde la API oficial de Google Classroom.
* **Encabezado:** `Authorization: Bearer <access_token>`

**Respuesta (200 OK):**
```json
{
  "deadlines": [
    {
      "course_id": "12345678",
      "course_name": "Ingeniería de Software II",
      "assignment_id": "87654321",
      "title": "Entrega de Caso de Estudio ERP",
      "description": "Especificación de arquitectura y flujos...",
      "due_date": "2026-10-25T23:59:00Z",
      "alternate_link": "https://classroom.google.com/c/12345678/a/87654321/details"
    }
  ]
}
```

---

## 6. Sincronización de Redes Sociales (Instagram)

### `POST /api/social/sync`
Ejecuta la sincronización inmediata del feed de Instagram (@upalemana) mediante SociableKIT (Embed-ID: 25723525).
* **Encabezado:** `Authorization: Bearer <admin_access_token>` (Solo administradores)

**Respuesta (200 OK):**
```json
{
  "status": "success",
  "synced_count": 50,
  "created_count": 2,
  "updated_count": 48
}
```

---

## Ejecución Local y Desarrollo de Cliente
```bash
# 1. Clonar el repositorio
git clone https://github.com/Pascal-Thommen/upa-app.git
cd upa-app

# 2. Iniciar el stack completo con Docker Compose (PostgreSQL 16 + FastAPI)
docker compose up -d

# 3. Acceder a la documentación interactiva en el navegador
# http://localhost:8000/docs
```

El desarrollo del cliente móvil se conecta directamente contra el backend real sin necesidad de datos simulados o mocks. La base de datos ejecuta migraciones automáticas al iniciar y carga datos representativos del campus.
