# UPA App: Especificacion Funcional y Operativa (Version Final)

Documento vivo de ingenieria | Universidad Paraguayo Alemana (UPA)

## 1. Landing Page y Distribucion
* Pantalla de Escritorio Minimalista: Muestra exactamente UN solo codigo QR que redirige a la URL de la PWA para instalacion en movil.
* Galeria de Vista Previa: Dos capturas de pantalla de la app (estilo Play Store / App Store) que muestran el Feed y la Agenda.
* Acceso Administrativo: Enlace discreto para inicio de sesion de marketing y administradores desde la PC.

## 2. Experiencia de Usuario y Pantallas Moviles

### A. Modulo Inicio (Feed Central)
* Avisos de Emergencia: Banners superiores temporales con fecha y hora de expiracion automatica ("Visible hasta").
* Publicaciones y Charlas: Tarjetas interactivas con boton de 1 clic para Inscribirse y Cancelar inscripcion.
* Modal de Pantalla Completa Estandarizado: Al hacer clic en cualquier elemento (noticia, aviso, evento de calendario o tarea), se abre siempre un modal a pantalla completa con texto integro, imagen en alta resolucion y boton de cierre (X).

### B. Modulo Agenda (Calendario)
* Vista Dual: Lista cronologica arriba y calendario mensual abajo con puntos de actividad.
* Tareas de Google Classroom: Plazos oficiales con estado (Pendiente / Entregado) y enlace directo a Classroom.
* Gestion de Asistencia: Si el estudiante pulsa "No asistire", el evento se atenua visualmente y deja de recibir recordatorios.

### C. Modulo Perfil y Configuracion
* Identidad Universitaria: Nombre completo, foto de perfil, correo verificado (@upa.edu.py), carrera y semestre lectivo.
* Boton de Cierre de Sesion: Borrado seguro de tokens OAuth y vaciado de cache de sesion.
* Control de Almacenamiento Offline: Indicador de espacio ocupado en el dispositivo (ej. "3.2 MB usados") y boton "Vaciar y sincronizar datos locales".
* Preferencias: Selector de Modo Oscuro / Claro y conmutadores de notificaciones push.
* Version y Soporte: Numero de version (ej. v0.1.0) y enlace institucional de contacto.

## 3. Panel de Administracion y Marketing (Escritorio)

### A. Feed de Entradas Unificadas (Single Source of Truth)
* Terminologia: Cada elemento es una **Publicacion** unificada que puede activar la seccion de Noticia, la seccion de Evento o ambas simultaneamente.
* Editor Simplificado: Titulo obligatorio, publicacion programada opcional, inscripcion RSVP desactivada por defecto, campo unico de carga multimedia para imagen o video (`JPG`, `PNG`, `WEBP`, `MP4`, `WEBM`, `PDF`), resumen corto (`caption`), texto principal unico (`content`), enlace de accion modular y fecha de vigencia (`expires_at`) obligatoria exclusivamente al fijar la publicacion arriba (`is_pinned`).
* Barrera de Proteccion de Instagram: En publicaciones sincronizadas desde Instagram, el resumen corto toma automaticamente las dos primeras lineas del post y todos los campos sincronizados (`caption`, `content`, `media_url`, `permalink`, `published_at`) permanecen en modo de solo lectura.
* Seccion de Evento: Hora de inicio obligatoria, hora de fin y lugar opcionales, grupos destinatarios preseleccionados por defecto para recordatorios y configuracion flexible de recordatorios en minutos, horas o dias (30 minutos por defecto).
* Metricas de Alcance Real y Participantes: Muestra vistas unicas por usuario y conteo en tiempo real de inscritos y bajas.

### B. Gestion Alfabetica de Grupos y Matriz Segura de Roles
* Grupos Ordenados Alfabeticamente: Lista plana sin jerarquias plegables artificiales de los grupos institucionales y de Google Workspace (`@upa.edu.py`), con filtro instantaneo en vivo y cache local en el servidor para evitar latencias y limites de cuota de Google Directory API.
* Seguridad de Roles: Inicio de sesion limpio sin botones de acceso rapido de desarrollo y creacion de nuevos roles con todas las casillas de permisos (`publicaciones`, `grupos`, `roles`, `apis`) desmarcadas por defecto.
