# Guia de Integracion Frontend y Clientes Moviles (UPA App API)

Este documento describe el contrato completo de integracion con el backend de la plataforma universitaria UPA App para el desarrollo de clientes moviles (Android / Kotlin) y aplicaciones web (PWA).

Todos los endpoints entregan estructuras JSON tipadas, libres de valores nulos inesperados y respaldadas por base de datos relacional PostgreSQL.

## 1. Direcciones Base y Especificacion OpenAPI

* **Servidor Publico HTTPS (NetBird):** `https://upa.eu1.netbird.services`
* **Servidor Alternativo HTTPS:** `https://upa-2vgh.eu1.netbird.services`
* **Desarrollo Local (Host):** `http://localhost:8000`
* **Emulador Android Studio (AVD):** `http://10.0.2.2:8000`
* **Documentacion Interactiva Swagger UI:** `/docs` (ej. `http://localhost:8000/docs`)
* **Esquema OpenAPI 3.1 JSON:** `/openapi.json` (ej. `http://localhost:8000/openapi.json`)

## 2. Autenticacion y Uso de `Authorization: Bearer <token>`

### 2.1 Login Provisorio de Desarrollo (`POST /api/auth/dev-login`)

Para agilizar el desarrollo del frontend sin depender de la configuracion de credenciales OAuth en Google Cloud Console, el endpoint `POST /api/auth/dev-login` genera una sesion JWT real y firmada utilizando cualquier correo institucional `@upa.edu.py`.

* Crea o actualiza el registro real del usuario en la base de datos.
* Consulta y sincroniza automaticamente los grupos de Google Workspace si el Service Account esta activo.
* Asigna el rol `admin` a cuentas administrativas (`pascal.thommen@upa.edu.py`, `soporte.ti@upa.edu.py`, `admin@upa.edu.py`) y el rol `user` a cuentas estudiantiles.
* Retorna exactamente la misma estructura `AuthResponse` que el flujo OAuth estandar.

**Peticion (`POST /api/auth/dev-login`):**
```http
POST /api/auth/dev-login HTTP/1.1
Content-Type: application/json

{
  "email": "pascal.thommen@upa.edu.py",
  "full_name": "Pascal Thommen"
}
```

**Respuesta Exitosa (`200 OK`):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZW1haWwiOiJwYXNjYWwudGhvbW1lbkB1cGEuZWR1LnB5Iiwicm9sZSI6ImFkbWluIiwiZXhwIjoxNzYxNzU2MDAwfQ.signature",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "pascal.thommen@upa.edu.py",
    "full_name": "Pascal Thommen",
    "role": "admin",
    "groups": [
      "ALL",
      "Semester_4",
      "TIE"
    ],
    "google_groups": [
      {
        "id": "01abc234def",
        "name": "Estudiantes TIE",
        "email": "estudiantes.tie@upa.edu.py",
        "description": "Grupo institucional de Ingenieria Empresarial"
      }
    ],
    "has_classroom_token": false
  }
}
```

**Ejemplo de Login como Estudiante Regular (`POST /api/auth/dev-login`):**
```json
{
  "email": "estudiante.tie@upa.edu.py",
  "full_name": "Estudiante TIE"
}
```

**Respuesta para Estudiante Regular (`200 OK`):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 2,
    "email": "estudiante.tie@upa.edu.py",
    "full_name": "Estudiante TIE",
    "role": "user",
    "groups": [],
    "google_groups": [],
    "has_classroom_token": false
  }
}
```

### 2.2 Como Enviar el Token en Peticiones Protegidas (`Authorization: Bearer <token>`)

Una vez obtenido el `access_token` desde `/api/auth/dev-login` o `/api/auth/google`, el cliente debe enviarlo en el encabezado HTTP `Authorization` en cada peticion a los endpoints protegidos:

```http
Authorization: Bearer <access_token>
```

#### Ejemplo con `curl`:
```bash
# 1. Obtener el token JWT mediante dev-login
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/dev-login \
  -H "Content-Type: application/json" \
  -d '{"email": "pascal.thommen@upa.edu.py"}' | jq -r '.access_token')

# 2. Consumir un endpoint protegido enviando el encabezado Authorization
curl -X GET http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json"
```

#### Ejemplo en TypeScript / JavaScript (`fetch`):
```typescript
async function fetchWithAuth(endpoint: string, token: string) {
  const response = await fetch(`https://upa.eu1.netbird.services${endpoint}`, {
    method: "GET",
    headers: {
      "Accept": "application/json",
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({ detail: "Error de red" }));
    throw new Error(errorBody.detail || `HTTP ${response.status}`);
  }

  return response.json();
}
```

#### Ejemplo en Android / Kotlin (`OkHttp Interceptor` + `Retrofit`):
```kotlin
class AuthInterceptor(private val tokenProvider: () -> String?) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val requestBuilder = chain.request().newBuilder()
            .header("Accept", "application/json")

        tokenProvider()?.takeIf { it.isNotBlank() }?.let { token ->
            requestBuilder.header("Authorization", "Bearer $token")
        }

        return chain.proceed(requestBuilder.build())
    }
}
```

## 3. Referencia Detallada de Endpoints y Ejemplos JSON

### 3.1 Estado Consolidado de la App (`GET /api/v1/app-state`)

Entrega en una sola llamada el estado de sesion y el feed de publicaciones.
* **Autenticacion:** Opcional (`Authorization: Bearer <token>`).
  * **Sin token:** `authenticated` es `false`, `user` es `null` y `feed` contiene exclusivamente publicaciones publicas de Instagram (`post_type = "INSTAGRAM"`) dirigidas a `ALL`.
  * **Con token:** `authenticated` es `true`, `user` contiene el perfil del usuario y `feed` incluye noticias internas, eventos y avisos filtrados segun el rol y los grupos del usuario.
* **Parametros Query Opcionales:**
  * `group`: Filtro por grupo o carrera (ej. `TIE`).
  * `limit`: Cantidad maxima de publicaciones (1 a 100, por defecto `20`).

**Respuesta Autenticada (`200 OK`):**
```json
{
  "portal": "UPA Mobile Campus Platform",
  "api_version": "1.0.0",
  "authenticated": true,
  "user": {
    "id": 1,
    "email": "pascal.thommen@upa.edu.py",
    "full_name": "Pascal Thommen",
    "role": "admin",
    "groups": [
      "ALL",
      "Semester_4",
      "TIE"
    ],
    "google_groups": [],
    "has_classroom_token": false
  },
  "feed": [
    {
      "id": 2,
      "title": "¿Que significa seguir siendo humanos en la era de la IA?",
      "summary": "holaa 👋 manana tenemos charla de 11 a 12, vayan pues",
      "content": "Inteligencia artificial, decisiones, libertad y responsabilidad.",
      "post_type": "MANUAL",
      "is_pinned": true,
      "target_groups": [
        "ALL",
        "TIE",
        "Informatica"
      ],
      "image_url": "",
      "permalink": "",
      "published_at": "2026-10-21T10:00:00+00:00"
    },
    {
      "id": 1,
      "title": "Busqueda Laboral: Recepcionista",
      "summary": "Estamos buscando Recepcionista. Envia tu CV a rrhh@upa.edu.py",
      "content": "Principales funciones: Atencion a padres, estudiantes y visitantes.",
      "post_type": "INSTAGRAM",
      "is_pinned": false,
      "target_groups": [
        "ALL"
      ],
      "image_url": "https://upa.edu.py/static/images/recepcionista_post.png",
      "permalink": "https://www.instagram.com/p/DerQoIzjtYf/",
      "published_at": "2026-10-20T14:00:00+00:00"
    }
  ]
}
```

### 3.2 Perfil del Usuario Autenticado (`GET /api/auth/me`)

Retorna el perfil del usuario actual validando el token JWT.
* **Encabezado Obligatorio:** `Authorization: Bearer <token>`
* **Regla de Privacidad en Servidor:** Los campos `groups` y `google_groups` solo entregan elementos para la cuenta autorizada `pascal.thommen@upa.edu.py`; para cualquier otro usuario devuelven listas vacias `[]`.

**Respuesta (`200 OK`):**
```json
{
  "id": 1,
  "email": "pascal.thommen@upa.edu.py",
  "full_name": "Pascal Thommen",
  "role": "admin",
  "groups": [
    "ALL",
    "Semester_4",
    "TIE"
  ],
  "google_groups": [
    {
      "id": "01abc234def",
      "name": "Estudiantes TIE",
      "email": "estudiantes.tie@upa.edu.py",
      "description": "Grupo institucional de Ingenieria Empresarial"
    }
  ],
  "has_classroom_token": false
}
```

### 3.3 Noticias Institucionales (`GET /api/news` y `GET /api/news/{post_id}`)

Retorna la lista de noticias y comunicados vigentes (excluye avisos cuya fecha `expires_at` haya vencido).
* **Encabezado Obligatorio:** `Authorization: Bearer <token>`
* **Filtrado por Rol en Servidor:** Un estudiante con rol `user` solo recibe publicaciones cuyo `target_groups` contenga `"ALL"` o coincida con sus grupos asignados. Un usuario con rol `admin` visualiza todas las publicaciones.
* **Parametros Query Opcionales (`GET /api/news`):**
  * `group`: Filtra por grupo (ej. `TIE`).
  * `limit`: Maximo de registros (1 a 100, por defecto `20`).
  * `offset`: Desplazamiento para paginacion (por defecto `0`).

**Respuesta (`GET /api/news` - `200 OK`):**
```json
[
  {
    "id": 1,
    "title": "Busqueda Laboral: Recepcionista",
    "summary": "Estamos buscando Recepcionista. Envia tu CV a rrhh@upa.edu.py",
    "content": "Principales funciones: Atencion a padres, estudiantes y visitantes.",
    "caption": "Estamos buscando Recepcionista. Envia tu CV a rrhh@upa.edu.py",
    "post_type": "INSTAGRAM",
    "is_pinned": false,
    "target_groups": [
      "ALL"
    ],
    "instagram_id": "insta_recepcionista_2026",
    "image_url": "https://upa.edu.py/static/images/recepcionista_post.png",
    "media_url": "https://upa.edu.py/static/images/recepcionista_post.png",
    "media_type": "IMAGE",
    "permalink": "https://www.instagram.com/p/DerQoIzjtYf/",
    "created_at": "2026-10-20T14:00:00Z",
    "published_at": "2026-10-20T14:00:00Z"
  }
]
```

**Detalle por ID (`GET /api/news/{post_id}`):**
* Retorna `200 OK` con el objeto `NewsResponse` si existe y el usuario tiene permiso.
* Retorna `403 Forbidden` si la noticia pertenece a un grupo restringido al que el usuario no pertenece.
* Retorna `404 Not Found` si el ID no existe o la publicacion ha expirado.

### 3.4 Creacion de Noticias (`POST /api/news`)

Permite publicar una nueva noticia o evento. Exclusivo para usuarios con rol `admin`.
* **Encabezado Obligatorio:** `Authorization: Bearer <admin_token>`

**Peticion (`POST /api/news`):**
```json
{
  "title": "Convocatoria de Becas de Investigacion UPA 2026",
  "caption": "Postulaciones abiertas hasta fin de mes.",
  "content": "Los estudiantes de ingenieria pueden presentar sus proyectos en secretaria academica.",
  "post_type": "MANUAL",
  "is_news": true,
  "is_event": false,
  "is_pinned": true,
  "target_groups": [
    "ALL",
    "TIE"
  ]
}
```

### 3.5 Calendario de Eventos (`GET /api/events` y `GET /api/events/{event_id}`)

Entrega los eventos academicos e institucionales ordenados cronologicamente por `event_start`.
* **Encabezado Obligatorio:** `Authorization: Bearer <token>`
* **Parametros Query Opcionales (`GET /api/events`):**
  * `group`: Filtro por carrera o grupo (ej. `TIE`).
  * `upcoming_only`: Booleano (por defecto `true`). Si es `true`, filtra solo eventos futuros.
  * `limit`: Maximo de registros (1 a 100, por defecto `20`).
  * `offset`: Desplazamiento para paginacion (por defecto `0`).

**Respuesta (`GET /api/events` - `200 OK`):**
```json
[
  {
    "id": 2,
    "title": "¿Que significa seguir siendo humanos en la era de la IA?",
    "description": "Inteligencia artificial, decisiones, libertad y responsabilidad. Disertante: Daniel Romero.",
    "summary": "holaa 👋 manana tenemos charla de 11 a 12, vayan pues",
    "event_start": "2026-10-22T11:00:00Z",
    "event_end": "2026-10-22T12:00:00Z",
    "location": "Auditorio Edificio 1, Piso 1",
    "has_registration": true,
    "is_pinned": true,
    "target_groups": [
      "ALL",
      "TIE",
      "Informatica"
    ],
    "image_url": "",
    "permalink": "",
    "created_at": "2026-10-21T10:00:00Z"
  }
]
```

**Detalle por ID (`GET /api/events/{event_id}`):**
* Retorna `200 OK` con el objeto `EventResponse`.
* Retorna `403 Forbidden` si el usuario no pertenece al grupo destinatario del evento.
* Retorna `404 Not Found` si el evento no existe.

### 3.6 Plazos y Entregas de Google Classroom (`GET /api/classroom/deadlines`)

Sincroniza y retorna las entregas academicas activas del estudiante desde Google Classroom.
* **Encabezado Obligatorio:** `Authorization: Bearer <token>`
* **Encabezado de Estado en Respuesta (`X-Classroom-Status`):**
  * `active`: Datos sincronizados en tiempo real desde Google Classroom.
  * `cached`: Datos entregados desde la cache en memoria (TTL 5 minutos).
  * `missing_token`: El usuario aun no ha vinculado un token OAuth de Classroom (retorna `[]`).
  * `no_courses`: El usuario no tiene cursos activos en el semestre (retorna `[]`).
  * `permission_denied`: El token de Classroom expiro o carece de permisos (retorna `[]`).
  * `api_error` / `network_error`: Fallo o timeout en el servicio externo de Google (retorna `[]`).

**Respuesta (`200 OK`):**
```json
[
  {
    "id": "654321098",
    "assignment_id": "654321098",
    "course_id": "123456789",
    "course": "Ingenieria de Software II",
    "course_name": "Ingenieria de Software II",
    "title": "Entrega de Arquitectura Backend REST",
    "description": "Documentacion OpenAPI y pruebas de integracion completas.",
    "due_date": {
      "year": 2026,
      "month": 10,
      "day": 28
    },
    "due_time": {
      "hours": 23,
      "minutes": 59
    },
    "due_date_formatted": "2026-10-28 23:59",
    "alternate_link": "https://classroom.google.com/c/123456789/a/654321098/details",
    "max_points": 100.0
  }
]
```

### 3.7 Cursos Activos de Google Classroom (`GET /api/classroom/courses`)

Retorna la lista de asignaturas activas del estudiante en Google Classroom.
* **Encabezado Obligatorio:** `Authorization: Bearer <token>`

**Respuesta (`200 OK`):**
```json
[
  {
    "id": "123456789",
    "name": "Ingenieria de Software II",
    "section": "Semestre 4",
    "alternate_link": "https://classroom.google.com/c/123456789",
    "room": "Aula 204"
  }
]
```

### 3.8 Vinculacion de Token de Classroom (`POST /api/auth/classroom-token`)

Permite registrar o actualizar el token OAuth 2.0 con alcances de Google Classroom para el usuario autenticado.
* **Encabezado Obligatorio:** `Authorization: Bearer <token>`

**Peticion:**
```json
{
  "classroom_token": "ya29.a0AfH6SM_token_oauth_classroom"
}
```

### 3.9 Feed Hibrido del Campus (`GET /api/v1/feed`)

Entrega por separado los avisos de emergencia (`urgent_banners`) y las publicaciones generales (`posts`).
* **Encabezado Opcional:** `Authorization: Bearer <token>`

**Respuesta (`200 OK`):**
```json
{
  "urgent_banners": [],
  "posts": [
    {
      "id": 1,
      "title": "Busqueda Laboral: Recepcionista",
      "caption": "Estamos buscando Recepcionista.",
      "content": "Principales funciones: Atencion al publico.",
      "summary": "Estamos buscando Recepcionista.",
      "post_type": "INSTAGRAM",
      "is_news": true,
      "is_event": false,
      "is_pinned": false,
      "expires_at": null,
      "event_start": null,
      "event_end": null,
      "location": "",
      "has_registration": false,
      "target_groups": [
        "ALL"
      ],
      "instagram_id": "insta_recepcionista_2026",
      "media_type": "IMAGE",
      "media_url": "https://upa.edu.py/static/images/recepcionista_post.png",
      "image_url": "https://upa.edu.py/static/images/recepcionista_post.png",
      "permalink": "https://www.instagram.com/p/DerQoIzjtYf/",
      "created_at": "2026-10-20T14:00:00Z",
      "published_at": "2026-10-20T14:00:00Z"
    }
  ]
}
```

## 4. Manejo Estandarizado de Errores HTTP

Todos los errores de negocio, autenticacion y autorizacion retornan un objeto JSON uniforme con la clave `detail`:

```json
{
  "detail": "Descripcion clara del motivo del error"
}
```

| Codigo HTTP | Caso de Uso | Ejemplo de `detail` |
|---|---|---|
| `400 Bad Request` | Datos malformados, correo invalido, titulo vacio o rango de fechas incoherente | `"Formato de correo electronico invalido."` |
| `401 Unauthorized` | Encabezado `Authorization` ausente, token JWT malformado o sesion expirada | `"Autenticacion requerida (Bearer Token ausente)"` |
| `403 Forbidden` | Correo fuera de `@upa.edu.py`, usuario sin rol `admin` o sin acceso al grupo del recurso | `"Acceso denegado: Solo se permiten correos institucionales @upa.edu.py."` |
| `404 Not Found` | Recurso solicitado por ID inexistente o expirado (`/api/news/{id}`, `/api/events/{id}`) | `"Evento no encontrado."` |
| `422 Unprocessable Entity` | Error de tipos en parametros query o cuerpo JSON incompleto | Detalle estructurado de validacion Pydantic |
| `503 Service Unavailable` | Timeout o caida temporal del servicio externo de validacion OAuth de Google | `"Tiempo de espera agotado al verificar el token con Google OAuth."` |

## 5. Garantias Anti-Conflicto para Clientes Tipados (Kotlin / TypeScript)

1. **Cero Nulos en Campos de Texto y Listas:** En `/api/v1/app-state`, `/api/auth/me`, `/api/news`, `/api/events` y `/api/classroom/deadlines`, todos los campos `String`, `Boolean`, `Float` y `List` entregan valores validos por defecto (`""`, `false`, `0.0`, `[]`) y nunca `null`.
2. **Fechas ISO-8601 con Zona Horaria UTC:** Todos los campos `datetime` (`created_at`, `published_at`, `event_start`, `event_end`) se serializan siempre con zona horaria UTC (`Z` o `+00:00`).
3. **Compatibilidad Dual de Nombres de Campo:**
   * En `/api/events`: se entregan tanto `description` como `summary`.
   * En `/api/news`: se entregan tanto `image_url` como `media_url`, y tanto `summary` como `caption`.
   * En `/api/classroom/deadlines`: se entregan tanto `id` como `assignment_id`, y tanto `course` como `course_name`.
