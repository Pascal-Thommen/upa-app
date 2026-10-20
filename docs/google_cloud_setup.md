# Guía de Configuración: Google Cloud Console y Google Workspace

Guía técnica paso a paso para la configuración del acceso OAuth 2.0 y Google Classroom bajo el principio de mínimo privilegio y mínimo esfuerzo administrativo (Octubre 2026).

---

## 1. Tipo de Usuario OAuth: "Interno" (Recomendado)

Al seleccionar el tipo de usuario **Interno** en Google Cloud Console para la organización `upa.edu.py`:
* **Acceso Exclusivo:** Únicamente cuentas con el dominio `@upa.edu.py` pueden iniciar sesión.
* **Sin Verificación Externa:** No requiere someter la aplicación a revisión ni auditoría por parte de Google.
* **Seguridad Estricta:** Las cuentas públicas de Gmail quedan automáticamente rechazadas a nivel criptográfico.

---

## 2. Pasos en Google Cloud Console

1. Acceder a [Google Cloud Console](https://console.cloud.google.com/) con una cuenta de administrador de `@upa.edu.py`.
2. Crear un nuevo proyecto o seleccionar el proyecto institucional (ej. `upa-campus-app`).
3. Ir a **APIs y servicios > Pantalla de consentimiento de OAuth**:
   * Tipo de usuario: Seleccionar **Interno**.
   * Nombre de la aplicación: `UPA Campus App`.
   * Correo electrónico de asistencia: Correo institucional de soporte.
4. Definir Permisos (Scopes) bajo el Principio de Mínimo Privilegio:
   * `openid`
   * `https://www.googleapis.com/auth/userinfo.email`
   * `https://www.googleapis.com/auth/userinfo.profile`
   * `https://www.googleapis.com/auth/classroom.courses.readonly`
   * `https://www.googleapis.com/auth/classroom.coursework.me.readonly`
5. Ir a **APIs y servicios > Biblioteca** y habilitar:
   * **Google Classroom API**
   * **Admin SDK API** (si se habilita sincronización de grupos)
6. Crear Credenciales:
   * **Cliente 1 (Servidor Backend):** Tipo "Aplicación web". Genera `Client ID` y `Client Secret`.
   * **Cliente 2 (Cliente Android):** Tipo "Android". Requiere el Nombre de Paquete (Package Name) y la Huella Digital SHA-1 del Keystore de compilación.

---

## 3. Capa Intermedia de Grupos (Target Groups Mapping)

Para evitar que el equipo de Marketing deba gestionar más de 200 grupos de Google, el backend implementa un catálogo de grupos lógicos simplificado:

* `ALL`: Toda la comunidad universitaria.
* `TIE`: Ingeniería Empresarial.
* `PI`: Ingeniería Industrial.
* `TI`: Tecnologías de la Información.
* `PROF`: Cuerpo docente y académico.

El backend resuelve las membresías internas mapeando los grupos de Google correspondientes hacia estas categorías maestras.
