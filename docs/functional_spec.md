# UPA App: Especificacion Funcional

## 1. Stack Tecnologico y Justificacion de Python (FastAPI)
* 60 por ciento menos codigo repetitivo frente a Java, priorizando cumplimiento de plazos y entrega del MVP.
* Integracion limpia y ligera con Google Workspace Admin SDK, Classroom API y feeds de redes sociales.
* Documentacion interactiva Swagger generada automaticamente (/docs) para el equipo de Android Studio.

## 2. Modulos y Funcionalidades Principales

### Modulo Inicio (Feed del Campus)
* Avisos de emergencia en formato banner superior ante situaciones imprevistas (ej. suspension por tormentas o granizo).
* Publicacion de conferencias (Charlas) y eventos con registro de inscripcion y cancelacion en 1 clic.
* Agregacion automatica de publicaciones oficiales de redes sociales mediante SociableKIT / Instagram API.

### Modulo Agenda (Calendario y Plazos)
* Lista cronologica de actividades en la parte superior y calendario mensual sincronizado con puntos indicadores abajo.
* Importacion automatica de fechas limite y entregas academicas desde Google Classroom.

### Modulo Perfil y Personalizacion
* Acceso exclusivo obligatorio con Google OAuth para cuentas @upa.edu.py.
* Configuracion de modo oscuro/claro, preferencias de notificaciones y filtro por carrera.

### Modulo Administracion Web (Marketing Escritorio)
* Fuente unica de verdad (Single Source of Truth): modelo de datos unificado para noticias y eventos de calendario.
* Segmentacion de destinatarios basada en grupos de Google Workspace sincronizados via Admin API.
