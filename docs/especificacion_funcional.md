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
* Terminologia: Cada elemento se denomina **Entrada** (con etiquetas de tipo: Aviso, Noticia de Instagram, Evento o Hibrido).
* Orden: Estrictamente cronologico (lo mas reciente arriba).
* Metricas de Alcance Real: Muestra impresiones unicas (cuantos estudiantes individuales vieron la entrada, no recuento bruto de clics).
* Metricas de Eventos: Contador de inscritos y desinscritos en tiempo real.
* Detalle de Participantes: Al abrir la entrada, se despliega la lista con nombres de los estudiantes confirmados y cancelados, junto con las carreras involucradas.

### B. Ventana Independiente de Gestion de Grupos
* Modulo separado para administradores.
* Permite crear meta-grupos combinando correos manuales con grupos sincronizados de Google Workspace Admin Console.
