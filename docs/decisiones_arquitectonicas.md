# UPA App: Especificación de Alcance, Usuarios y Matriz de Decisiones Arquitectónicas (Versión v2 / v3)

Documento Técnico y Estratégico de Ingeniería de Sistemas | Universidad Paraguayo Alemana (UPA)  
Autores: Pascal Thommen, Theresa Bauer, Natasha Kolman  
Actualización: 25 de Octubre de 2026  

---

## 1. Propósito del Sistema y Filosofía de Diseño
El objetivo de la plataforma UPA App es consolidar en un punto único de acceso (Single Source of Truth) la vida académica, comunicacional y comunitaria de la Universidad Paraguayo Alemana.
* **Minimalismo Radical:** Interfaz limpia, ágil y directa, eliminando elementos accesorios o redundantes.
* **Doctrina Zero-Mock (Cero Simulaciones):** Todo botón, formulario o vista está conectado a lógica real y fuentes auténticas en el backend.

---

## 2. Análisis Exhaustivo de Usuarios y Roles (Personas del Sistema)
* **Estudiante de Grado (Segmentado por Carrera y Semestre):** Consulta avisos urgentes, agenda con fechas límite de Google Classroom y participa en eventos institucionales mediante la aplicación móvil nativa.
* **Personal Docente y Catedráticos:** Comunicación de avisos para el claustro, seguimiento de entregas académicas e interacción formativa.
* **Personal Administrativo y Equipo de Marketing:** Gestión integral de contenidos desde el Portal Web Administrativo de escritorio (noticias, eventos, afiches multimedia y segmentación por audiencias).
* **Usuario No Autenticado:** Acceso bloqueado. Únicamente se presenta la pantalla de inicio de sesión con Google OAuth 2.0 restringido al dominio `@upa.edu.py`.

---

## 3. Matriz de Decisiones Arquitectónicas Oficiales (Actualizado v2 &bull; 23 de Octubre 2026)

### 3.1. Frontend Móvil: Aplicación Nativa Android (Kotlin / Jetpack Compose)
* **Decisión:** Se determinó de forma definitiva desarrollar la solución móvil como aplicación nativa Android utilizando Kotlin y Jetpack Compose, descartando la alternativa de Progressive Web App (PWA).
* **Fundamentación:** Acceso directo a APIs del sistema operativo móvil, rendimiento optimizado en animaciones y renderizado de listas, ciclo de vida robusto en segundo plano para notificaciones y persistencia local nativa mediante Room/SQLite.

### 3.2. Modelo de Persistencia Dual: PostgreSQL (Backend) y SQLite / Room (Móvil)
* **Decisión:** PostgreSQL opera como motor relacional centralizado en el servidor, mientras que SQLite (vía Room) se reserva para la persistencia y caché local en el cliente móvil.
* **Fundamentación:** El backend gestiona alta concurrencia, transacciones seguras de inscripciones a eventos (RSVP) e integridad referencial de auditoría. El cliente móvil aprovecha SQLite para garantizar soporte offline inmediato en caso de intermitencias de red.

### 3.3. Desacoplamiento de Contenedores Frontend y Backend
* **Decisión:** Separar la interfaz web administrativa en su propio contenedor frontend independiente, desacoplándolo del contenedor de ejecución de la API en FastAPI.
* **Fundamentación:** Modularidad de despliegue, escalabilidad independiente de tráfico para recursos estáticos y aislamiento de seguridad de los componentes de presentación respecto al núcleo de la API.

### 3.4. Red Privada Mallada Zero-Trust (NetBird)
* **Decisión:** Despliegue de servidores sobre túneles seguros punto a punto con NetBird (`upa.eu1.netbird.services`).
* **Fundamentación:** Permite la comunicación segura y cifrada entre el entorno de desarrollo, el servidor staging y la red universitaria sin exponer puertos de bases de datos o servicios administrativos directamente a la Internet pública.

### 3.5. Autenticación y Federación de Identidades (Google OAuth 2.0)
* **Decisión:** Autenticación delegada exclusiva para el dominio institucional `@upa.edu.py`, con obtención de `refresh_token` (`prompt=consent select_account`) y emisión de tokens JWT propios de corta duración para la API interna.
* **Fundamentación:** Eliminación del riesgo de gestionar contraseñas locales y sincronización automática de permisos basada en los grupos de Google Workspace Admin Directory API.

### 3.6. Portal Web-Admin y Cockpit Editorial (En preparación para Documento v3)
* **Decisión:** Arquitectura modular con menú lateral institucional que separa el espacio futuro de los estudiantes (aplicación móvil de Theresa) de los cuatro módulos de gestión administrativa (Publicaciones y Eventos, Grupos y Audiencias, Consola de Administradores, Diagnóstico Técnico de APIs).

---

## 4. Modelo Operativo del Equipo
* **Pascal Thommen:** Product Owner, Arquitectura de Integración, Backend (FastAPI, PostgreSQL) e Infraestructura de Servidor (NetBird, Docker).
* **Theresa Bauer:** Desarrollo del Frontend Móvil Nativo Android (Kotlin, Jetpack Compose, Room/SQLite).
* **Natasha Kolman:** Soporte de proyecto y coordinación institucional.
* **Mika (Chief of Staff &bull; IA):** Coordinación técnica, bitácora de avances, especificaciones Zero-Mock y control de calidad CI/CD.