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
* Permite enviar opcionalmente `classroom_token` y `classroom_refresh_token` para sincronizacion de Google Classroom.
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

### 3.1 Estado Consolidado de Inicio (`GET /api/v1/app-state`)

Entrega en una sola llamada el estado de sesion, el feed de publicaciones (`feed`), los proximos eventos (`upcoming_events`) y los proximos plazos de Classroom (`upcoming_deadlines`) para que la aplicacion movil cargue la pantalla principal en el arranque en frio con una unica peticion.

* **Autenticacion:** Opcional (`Authorization: Bearer <token>`).
  * **Sin token:** `authenticated` es `false`, `user` es `null`, `feed` contiene exclusivamente publicaciones publicas de Instagram dirigidas a `ALL`, y `upcoming_events` y `upcoming_deadlines` retornan `[]`.
  * **Con token:** `authenticated` es `true`, `user` contiene el perfil del usuario, `feed` incluye noticias y avisos filtrados por grupo, `upcoming_events` entrega los eventos futuros con estado de inscripcion (`is_registered`, `registered_count`), y `upcoming_deadlines` entrega las tareas de Google Classroom.
* **Parametros Query Opcionales:**
  * `group`: Filtro por grupo o carrera (ej. `TIE`).
  * `limit`: Cantidad maxima de publicaciones y eventos (1 a 100, por defecto `20`).

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
    "has_classroom_token": true
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
    }
  ],
  "upcoming_events": [
    {
      "id": 2,
      "title": "¿Que significa seguir siendo humanos en la era de la IA?",
      "description": "Inteligencia artificial, decisiones, libertad y responsabilidad.",
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
      "created_at": "2026-10-21T10:00:00Z",
      "is_registered": true,
      "registered_count": 15
    }
  ],
  "upcoming_deadlines": [
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
}
```

### 3.2 Agenda Consolidada (`GET /api/v1/agenda`)

Consolida los eventos reales de calendario y los plazos academicos de Google Classroom ordenados cronologicamente, entregando tanto las listas especificas (`events`, `deadlines`) como una linea de tiempo unificada (`items`).

* **Encabezado Opcional:** `Authorization: Bearer <token>`
* **Parametros Query Opcionales:**
  * `group`: Filtro opcional por carrera o grupo (ej. `TIE`).
  * `upcoming_only`: Booleano (por defecto `true`).
  * `limit`: Cantidad maxima de eventos (1 a 200, por defecto `50`).

**Respuesta (`200 OK`):**
```json
{
  "events": [
    {
      "id": 2,
      "title": "¿Que significa seguir siendo humanos en la era de la IA?",
      "description": "Inteligencia artificial, decisiones, libertad y responsabilidad.",
      "summary": "holaa 👋 manana tenemos charla de 11 a 12, vayan pues",
      "event_start": "2026-10-22T11:00:00Z",
      "event_end": "2026-10-22T12:00:00Z",
      "location": "Auditorio Edificio 1, Piso 1",
      "has_registration": true,
      "is_pinned": true,
      "target_groups": ["ALL", "TIE", "Informatica"],
      "image_url": "",
      "permalink": "",
      "created_at": "2026-10-21T10:00:00Z",
      "is_registered": true,
      "registered_count": 1
    }
  ],
  "deadlines": [
    {
      "id": "654321098",
      "assignment_id": "654321098",
      "course_id": "123456789",
      "course": "Ingenieria de Software II",
      "course_name": "Ingenieria de Software II",
      "title": "Entrega de Arquitectura Backend REST",
      "description": "Documentacion OpenAPI y pruebas de integracion completas.",
      "due_date": {"year": 2026, "month": 10, "day": 28},
      "due_time": {"hours": 23, "minutes": 59},
      "due_date_formatted": "2026-10-28 23:59",
      "alternate_link": "https://classroom.google.com/c/123456789/a/654321098/details",
      "max_points": 100.0
    }
  ],
  "items": [
    {
      "item_type": "EVENT",
      "id": "2",
      "title": "¿Que significa seguir siendo humanos en la era de la IA?",
      "description": "Inteligencia artificial, decisiones, libertad y responsabilidad.",
      "timestamp": "2026-10-22T11:00:00+00:00",
      "sort_key": "2026-10-22 11:00",
      "location_or_course": "Auditorio Edificio 1, Piso 1",
      "link": "",
      "is_registered": true,
      "registered_count": 1
    },
    {
      "item_type": "DEADLINE",
      "id": "654321098",
      "title": "Entrega de Arquitectura Backend REST",
      "description": "Documentacion OpenAPI y pruebas de integracion completas.",
      "timestamp": "2026-10-28 23:59",
      "sort_key": "2026-10-28 23:59",
      "location_or_course": "Ingenieria de Software II",
      "link": "https://classroom.google.com/c/123456789/a/654321098/details",
      "is_registered": false,
      "registered_count": 0
    }
  ]
}
```

### 3.3 Perfil del Usuario Autenticado (`GET /api/auth/me`)

Retorna el perfil del usuario actual validando el token JWT.
* **Encabezado Obligatorio:** `Authorization: Bearer <token>`
* **Regla de Privacidad en Servidor:** Los campos `groups` y `google_groups` solo entregan elementos para la cuenta autorizada `pascal.thommen@upa.edu.py`; para cualquier otro usuario devuelven listas vacias `[]`.

### 3.4 Noticias Institucionales y CRUD Administrativo (`GET`, `POST`, `PUT`, `DELETE /api/news`)

* **`GET /api/news` y `GET /api/news/{post_id}`:** Lista o consulta el detalle de noticias vigentes filtradas segun el rol y los grupos del usuario. Requiere `Authorization: Bearer <token>`.
* **`POST /api/news` (Solo Admin):** Crea una nueva publicacion institucional (`201 Created`).
* **`PUT /api/news/{post_id}` (Solo Admin):** Actualiza una noticia existente y registra auditoria administrativa (`200 OK`).
* **`DELETE /api/news/{post_id}` (Solo Admin):** Elimina una noticia existente y registra auditoria administrativa (`200 OK`).

**Peticion de Actualizacion (`PUT /api/news/{post_id}`):**
```json
{
  "title": "Convocatoria de Becas de Investigacion UPA 2026 (Plazo Extendido)",
  "caption": "Postulaciones abiertas hasta el 15 de noviembre.",
  "content": "Los estudiantes de ingenieria pueden presentar sus proyectos en secretaria academica.",
  "is_pinned": true,
  "target_groups": ["ALL", "TIE"]
}
```

**Respuesta de Eliminacion (`DELETE /api/news/{post_id}`):**
```json
{
  "status": "deleted",
  "id": 1,
  "detail": "Publicacion de noticias eliminada correctamente."
}
```

### 3.5 Calendario de Eventos, Inscripcion RSVP y CRUD Administrativo (`/api/events`)

Entrega los eventos academicos e institucionales ordenados cronologicamente por `event_start`, incluyendo el estado de inscripcion del usuario actual (`is_registered: bool`) y el contador total de participantes (`registered_count: int`).

* **`GET /api/events` y `GET /api/events/{event_id}`:** Consulta eventos con `is_registered` y `registered_count`.
* **`POST /api/events/{event_id}/register`:** Inscribe de forma vinculante e idempotente al usuario autenticado en la tabla `event_registrations` y retorna el `EventResponse` actualizado (`is_registered: true`).
* **`DELETE /api/events/{event_id}/register`:** Cancela la inscripcion del usuario autenticado y retorna el `EventResponse` actualizado (`is_registered: false`).
* **`PUT /api/events/{event_id}` (Solo Admin):** Actualiza los datos de un evento existente (`200 OK`).
* **`DELETE /api/events/{event_id}` (Solo Admin):** Elimina un evento y sus registros asociados (`200 OK`).

**Respuesta de `GET /api/events/{event_id}` o `POST /api/events/{event_id}/register` (`200 OK`):**
```json
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
  "created_at": "2026-10-21T10:00:00Z",
  "is_registered": true,
  "registered_count": 1
}
```

### 3.6 Google Classroom y Auto-Refresh de Token (`GET /api/classroom/deadlines`, `GET /api/classroom/courses`, `POST /api/auth/classroom-token`)

Sincroniza y retorna las entregas academicas y los cursos activos del estudiante desde Google Classroom.
* **Encabezado Obligatorio:** `Authorization: Bearer <token>`
* **Auto-Refresh Transparente en Servidor:** La tabla `users` almacena `classroom_refresh_token`. Cuando el `classroom_token` expira tras 60 minutos y Google Classroom responde `HTTP 401`, el backend ejecuta automaticamente el flujo `grant_type=refresh_token` contra `https://oauth2.googleapis.com/token`, persiste el nuevo token en PostgreSQL, reintenta la consulta y entrega los datos al estudiante sin interrupcion (agregando el encabezado `X-Classroom-Token-Refreshed: true`).
* **Vinculacion Manual (`POST /api/auth/classroom-token`):**
```json
{
  "classroom_token": "ya29.a0AfH6SM_token_oauth_classroom",
  "classroom_refresh_token": "1//0gRefreshTokenOpcionalParaAutoRefresh"
}
```

### 3.7 Registro de Token Push para Dispositivos Moviles (`POST /api/users/device-token`)

Permite registrar el token FCM de Android / iOS / Web del dispositivo del usuario autenticado para el envio de notificaciones push.
* **Encabezado Obligatorio:** `Authorization: Bearer <token>`

**Peticion (`POST /api/users/device-token`):**
```json
{
  "device_token": "fcm_token_android_d8a92b3c4e5f6a7b8c9d0e1f2a3b4c5d",
  "platform": "android"
}
```

**Respuesta (`200 OK`):**
```json
{
  "user_id": 1,
  "device_token": "fcm_token_android_d8a92b3c4e5f6a7b8c9d0e1f2a3b4c5d",
  "platform": "android",
  "has_device_token": true,
  "updated_at": "2026-10-21T17:00:00Z"
}
```

### 3.8 Feed Hibrido del Campus (`GET /api/v1/feed`)

Entrega por separado los avisos de emergencia (`urgent_banners`) y las publicaciones generales (`posts`).
* **Encabezado Opcional:** `Authorization: Bearer <token>`

## 4. Manejo Estandarizado de Errores HTTP

Todos los errores de negocio, autenticacion y autorizacion retornan un objeto JSON uniforme con la clave `detail`:

```json
{
  "detail": "Descripcion clara del motivo del error"
}
```

| Codigo HTTP | Caso de Uso | Ejemplo de `detail` |
|---|---|---|
| `400 Bad Request` | Datos malformados, correo invalido, titulo vacio, rango de fechas incoherente o token de dispositivo vacio | `"El token de dispositivo (device_token) es invalido o esta vacio."` |
| `401 Unauthorized` | Encabezado `Authorization` ausente, token JWT malformado o sesion expirada | `"Autenticacion requerida (Bearer Token ausente)"` |
| `403 Forbidden` | Correo fuera de `@upa.edu.py`, usuario sin rol `admin` en endpoints CRUD o sin acceso al grupo del recurso | `"Acceso denegado: Se requieren permisos de administrador (Administrator-Rechte erforderlich)"` |
| `404 Not Found` | Recurso solicitado por ID inexistente o expirado (`/api/news/{id}`, `/api/events/{id}`, `/api/events/{id}/register`) | `"Evento no encontrado."` |
| `422 Unprocessable Entity` | Error de tipos en parametros query o cuerpo JSON incompleto | Detalle estructurado de validacion Pydantic |
| `503 Service Unavailable` | Timeout o caida temporal del servicio externo de validacion OAuth de Google | `"Tiempo de espera agotado al verificar el token con Google OAuth."` |

## 5. Garantias Anti-Conflicto para Clientes Tipados (Kotlin / TypeScript)

1. **Cero Nulos en Campos de Texto y Listas:** En `/api/v1/app-state`, `/api/v1/agenda`, `/api/auth/me`, `/api/news`, `/api/events`, `/api/classroom/deadlines` y `/api/users/device-token`, todos los campos `String`, `Boolean`, `Int`, `Float` y `List` entregan valores validos por defecto (`""`, `false`, `0`, `0.0`, `[]`) y nunca `null`.
2. **Fechas ISO-8601 con Zona Horaria UTC:** Todos los campos `datetime` (`created_at`, `published_at`, `event_start`, `event_end`, `updated_at`) se serializan siempre con zona horaria UTC (`Z` o `+00:00`).
3. **Compatibilidad Dual de Nombres de Campo:**
   * En `/api/events`: se entregan tanto `description` como `summary`, ademas de `is_registered` y `registered_count`.
   * En `/api/news`: se entregan tanto `image_url` como `media_url`, y tanto `summary` como `caption`.
   * En `/api/classroom/deadlines`: se entregan tanto `id` como `assignment_id`, y tanto `course` como `course_name`.
