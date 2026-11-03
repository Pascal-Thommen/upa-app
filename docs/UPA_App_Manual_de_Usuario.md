# UNIVERSIDAD PARAGUAYO ALEMANA (UPA)

**Carrera:** Informática Empresarial (Business Informatics)  
**Documento:** Parte 2 de la Documentación del Proyecto: Manual de Usuario (Campus PWA y Web-Admin Cockpit)

| Metadato | Detalle Institucional |
|---|---|
| **Institución** | Universidad Paraguayo Alemana (UPA), San Lorenzo, Paraguay |
| **Proyecto** | UPA App: Plataforma Digital y Campus Móvil Centralizado |
| **Documento** | Manual de Usuario Paso a Paso (9 Vistas Clave Documentadas) |
| **Autores** | Pascal Thommen, Natasha Colman y Equipo de Desarrollo UPA |
| **Versión** | v4.0 (03 de noviembre de 2026) Producción y Beta |

## Introducción y Estructura del Manual

Este manual constituye la **Parte 2** de la documentación oficial de **UPA App** y ofrece una guía práctica, visual y directa para operar la plataforma en el día a día. El documento evita la teoría técnica innecesaria y se centra en instrucciones concretas paso a paso tanto para la comunidad universitaria como para el equipo administrativo.

El manual se divide en dos partes claramente diferenciadas que cubren las **9 vistas clave (Screens 1 a 9)** del sistema:

* **Parte A: Campus PWA (Aplicación Móvil y de Escritorio para Estudiantes y Docentes):** Explica el acceso mediante código QR, el inicio de sesión con cuenta institucional `@upa.edu.py`, la lectura de avisos urgentes y noticias en el muro, el uso de la agenda integrada con Google Classroom, la confirmación de asistencia a eventos en 1 clic (RSVP) y la configuración del perfil personal (Pantallas 1 a 4).
* **Parte B: Web-Admin Cockpit (Portal para Redacción y Administración):** Detalla la gestión de publicaciones y métricas reales, la extracción multimodal de afiches mediante Inteligencia Artificial (`Autocompletar con IA` con Google Gemini), la administración de grupos de audiencia sincronizados con Google Workspace, la matriz de 6 permisos por rol y la revisión del historial inmutable de auditoría (Pantallas 5 a 9).

| Nº de Vista | Parte | Nombre de la Vista Clave | Ruta en la Plataforma | Público Objetivo |
|---|---|---|---|---|
| **Screen 1** | Parte A (PWA) | Página de Aterrizaje de Escritorio (QR y Login) | `/` | Estudiantes y Docentes |
| **Screen 2** | Parte A (PWA) | Muro del Campus y Avisos Urgentes (Feed) | `/?app=1` (Pestaña `Inicio`) | Estudiantes y Docentes |
| **Screen 3** | Parte A (PWA) | Agenda Interactiva (Classroom y RSVP Sí/No) | `/?app=1` (Pestaña `Agenda`) | Estudiantes y Docentes |
| **Screen 4** | Parte A (PWA) | Perfil de Usuario (Identidad, Carrera y Tema) | `/?app=1` (Pestaña `Perfil`) | Estudiantes y Docentes |
| **Screen 5** | Parte B (Cockpit) | Vista General del Cockpit (Tabla, Filtros y Deep Links) | `/dashboard/publicaciones` | Redacción y Administración |
| **Screen 6** | Parte B (Cockpit) | Autocompletado Inteligente con IA (Gemini Multimodal) | `/dashboard/publicaciones/nueva` | Redacción y Marketing |
| **Screen 7** | Parte B (Cockpit) | Gestión de Grupos de Audiencia (Google Workspace) | `/dashboard/grupos` | Administración |
| **Screen 8** | Parte B (Cockpit) | Matriz de Roles y Permisos (6 Permisos Canónicos) | `/dashboard/roles` | Administración |
| **Screen 9** | Parte B (Cockpit) | Historial y Registros de Auditoría (`admin_audit_logs`) | `/dashboard/publicaciones`, `/grupos`, `/roles` | Administración y Auditoría |

## Parte A: Campus PWA (Móvil y Escritorio para Estudiantes y Docentes)

La **Aplicación Web Progresiva (PWA)** de UPA Campus está diseñada para abrirse al instante en cualquier teléfono Android o iPhone sin necesidad de descargar nada desde tiendas de aplicaciones, funcionando también desde cualquier navegador de computadora.

### Pantalla 1 (Screen 1): Página de Aterrizaje de Escritorio (Código QR e Inicio de Sesión)

Cuando abres la plataforma desde una computadora de escritorio o portátil, el sistema detecta automáticamente el tamaño de pantalla y muestra la página de bienvenida con acceso rápido al teléfono móvil.

#### Pasos de uso para el estudiante o docente

1. **Abrir en computadora:** Ingresa a `https://upa.eu1.netbird.services/` desde el navegador de tu computadora.
2. **Escanear con el celular (Recomendado):** Apunta la cámara de tu teléfono (Android o iPhone) al **Código QR** que aparece en la tarjeta derecha (`Escanea con tu celular para abrir la app`). La aplicación móvil se abrirá directamente en tu teléfono.
3. **Usar directamente en la computadora:** Interactúa con la vista previa del teléfono ubicada a la izquierda (`phone-mockup`) o abre la vista completa en el navegador añadiendo `/?app=1` (en la parte superior verás el botón `Volver al código QR` para regresar a la portada en cualquier momento).
4. **Iniciar sesión institucional:** Pulsa el botón **`Iniciar sesión con Google`** e ingresa exclusivamente con tu correo oficial **`@upa.edu.py`**. Las cuentas personales externas (`@gmail.com`) son rechazadas por seguridad.
5. **Instalar en la pantalla de inicio del teléfono:**
   * **En Android (Chrome):** Toca el botón **`Instalar`** en el banner superior `Instalar en pantalla de inicio`.
   * **En iPhone / iPad (Safari):** Toca el botón **Compartir** en la barra inferior de Safari y selecciona **`Añadir a pantalla de inicio`**.

```screen
screen_1
```

*Figura 1: Pantalla 1 (Screen 1) - Página de aterrizaje en escritorio con simulador móvil interactivo, código QR dinámico y acceso administrativo.*

> **[CONTENEDOR DE CAPTURA #1: Página de Aterrizaje de Escritorio (QR-Code y Login)]**  
> **Ruta a capturar:** `https://upa.eu1.netbird.services/` en un navegador de escritorio a pantalla completa.  
> **Qué mostrar en la imagen:** La pantalla dividida en dos columnas con el teléfono interactivo a la izquierda mostrando la app y la tarjeta del código QR a la derecha.  
> **Elementos UI a enfocar y marcar:**  
> 1. **Enfoque 1 (Izquierda):** El marco interactivo del teléfono (`phone-mockup`) con el aviso `Iniciar sesión con Google` (`@upa.edu.py`) y las tres pestañas inferiores (`Inicio`, `Agenda`, `Perfil`).  
> 2. **Enfoque 2 (Derecha centro):** El recuadro del código QR vectorial (`#qr-box`) junto al título `Escanea con tu celular para abrir la app`.  
> 3. **Enfoque 3 (Abajo a la derecha):** El enlace discreto `Acceso Administrativo` que dirige al equipo autorizado hacia `/dashboard/`.

### Pantalla 2 (Screen 2): Muro del Campus y Avisos Urgentes (Feed de Noticias, Eventos e Instagram)

Al ingresar desde tu teléfono móvil (o en `/?app=1`), la pestaña activa por defecto es **`Inicio`**. Aquí se concentran en un único muro todos los comunicados oficiales de la universidad y las publicaciones de Instagram, ordenados automáticamente por prioridad.

#### Cómo navegar e identificar cada tipo de publicación

1. **Leer Avisos Urgentes (Parte superior):** Si existe una emergencia o aviso crítico (por ejemplo, suspensión de clases por tormenta o cambio urgente de aula), aparecerá destacado en la parte superior dentro del bloque de **Avisos urgentes** (`#urgent-list`). Estos avisos desaparecen solos cuando vence su hora de vigencia (`expires_at`).
2. **Identificar Publicaciones Fijadas:** Justo debajo de las alertas urgentes verás los comunicados importantes que la universidad ha fijado temporalmente en la parte superior del muro.
3. **Distinguir Noticias, Eventos e Instagram en el muro:**
   * **Noticias del Campus:** Comunicados oficiales redactados por la universidad para toda la comunidad (`ALL`) o específicos para tu carrera.
   * **Eventos Universitarios:** Tarjetas que incluyen bloque de fecha, horario, ubicación física en el campus y botones directos de confirmación de asistencia.
   * **Publicaciones de Instagram (`@upalemana`):** Tarjetas sincronizadas desde la cuenta oficial de la UPA, identificadas con el ícono de cámara de Instagram.
4. **Abrir el detalle completo (`#detail`):** Toca cualquier tarjeta para abrir la vista a pantalla completa. Allí podrás ver el afiche sin recortes, leer el texto completo, reproducir videos subidos o pulsar el botón de enlace externo (`Ver en Instagram` o enlace adjunto). Para volver al muro, toca la flecha superior izquierda (`Volver`) o usa el gesto de retroceso de tu teléfono.
5. **Actualizar el contenido:** Toca el botón circular **`Actualizar`** en la esquina superior derecha de la barra superior para refrescar el muro al instante.

```screen
screen_2
```

*Figura 2: Pantalla 2 (Screen 2) - Muro principal en la pestaña Inicio con avisos urgentes, tarjetas de noticias, eventos e Instagram.*

> **[CONTENEDOR DE CAPTURA #2: Muro del Campus y Avisos Urgentes (Feed)]**  
> **Ruta a capturar:** `https://upa.eu1.netbird.services/?app=1` en vista móvil con sesión `@upa.edu.py` iniciada (Pestaña `Inicio`).  
> **Qué mostrar en la imagen:** La pestaña `Inicio` mostrando un aviso urgente o publicación fijada arriba, seguida de tarjetas de noticias, eventos e Instagram, y la barra de navegación inferior.  
> **Elementos UI a enfocar y marcar:**  
> 1. **Enfoque 1 (Parte superior):** El bloque de **Aviso urgente** o publicación fijada en el encabezado del muro (`#urgent-list`) y el botón superior derecho `Actualizar`.  
> 2. **Enfoque 2 (Cuerpo central):** Las etiquetas e insignias que diferencian cada tarjeta en el feed (**Noticia**, **Evento** con fecha/lugar e ícono de **Instagram `@upalemana`**).  
> 3. **Enfoque 3 (Barra inferior):** La barra de navegación móvil con la pestaña **`Inicio`** seleccionada.

### Pantalla 3 (Screen 3): Agenda Interactiva (Plazos de Google Classroom y RSVP en 1 Clic con Sí/No)

La plataforma unifica la confirmación de asistencia a eventos del campus con tus fechas de entrega académicas de **Google Classroom** para que no tengas que revisar múltiples aplicaciones.

#### Confirmación de asistencia en 1 clic (Patrón de dos botones Sí / No)

1. **Ubicar los botones de inscripción:** En cualquier tarjeta de evento (tanto en el muro `Inicio`, en el modal de detalle como al abrir un evento desde `Agenda`), verás dos botones claros en la parte inferior: **`Sí, asistiré`** y **`No asistiré`**.
2. **Confirmar asistencia (`Sí, asistiré`):** Toca **`Sí, asistiré`** para registrar tu participación en un solo toque. El botón cambiará a color activo confirmando tu inscripción.
3. **Indicar inasistencia o cancelar (`No asistiré`):** Si no puedes acudir, toca **`No asistiré`**. Al marcar esta opción, el sistema registra tu baja y silencia automáticamente los recordatorios futuros de ese evento para tu cuenta.
4. **Deshacer la selección:** Si tocas nuevamente el botón que ya tenías marcado, tu respuesta se retira y ambos botones vuelven al estado neutro.
5. **Privacidad garantizada:** Ningún estudiante puede ver cuántas personas ni quiénes se inscribieron a un evento. Solo tú ves el estado de tu propio botón.

#### Uso de la pestaña Agenda y entregas de Google Classroom

1. **Abrir la Agenda:** Toca la segunda pestaña inferior: **`Agenda`**.
2. **Revisar la lista cronológica superior (`Próximos eventos y tareas`):** En la mitad superior verás ordenados por fecha y hora (en horario oficial de Paraguay, `America/Asuncion`) tanto los eventos de la UPA como tus tareas pendientes de **Google Classroom**.
   * Al tocar un **Evento del campus**, se abre su ficha completa con los botones `Sí, asistiré` y `No asistiré`.
   * Al tocar una **Entrega de Google Classroom**, se abre directamente la tarea correspondiente en tu aplicación o web de Google Classroom.
3. **Filtrar por día en el calendario mensual inferior:** En la mitad inferior verás la cuadrícula del mes actual (`Calendario mensual`). Los días que tienen eventos o entregas de Classroom muestran puntos indicadores de color.
4. **Ver actividades de una fecha específica:** Toca cualquier día en el calendario para filtrar la lista superior. Para volver a ver todas las fechas del mes, toca el botón **`Ver todo`** que aparece junto al encabezado `Próximos eventos y tareas`.

```screen
screen_3
```

*Figura 3: Pantalla 3 (Screen 3) - Agenda interactiva con entregas de Google Classroom, calendario mensual y botones RSVP de 1 clic (`Sí, asistiré` / `No asistiré`).*

> **[CONTENEDOR DE CAPTURA #3: Agenda Interactiva y Confirmación RSVP en 1 Clic]**  
> **Ruta a capturar:** Pestaña `Agenda` en la PWA móvil (`https://upa.eu1.netbird.services/?app=1`) junto con el detalle de los botones RSVP de un evento.  
> **Qué mostrar en la imagen:** La vista de `Agenda` mostrando arriba la lista combinada de eventos UPA y entregas de Google Classroom, abajo el calendario mensual con puntos de actividad, y los dos botones de respuesta RSVP (`Sí, asistiré` / `No asistiré`).  
> **Elementos UI a enfocar y marcar:**  
> 1. **Enfoque 1 (Lista superior):** Diferenciación visual entre un **Evento institucional** y una **Tarea de Google Classroom** con materia y hora límite en `America/Asuncion`.  
> 2. **Enfoque 2 (Botones de acción RSVP):** El par de botones **`Sí, asistiré`** y **`No asistiré`** (1 clic, sin mostrar contadores públicos de asistentes).  
> 3. **Enfoque 3 (Calendario inferior):** La cuadrícula mensual (`#cal-grid`) con los indicadores de fechas activas, flechas de cambio de mes y el filtro rápido `Ver todo`.

### Pantalla 4 (Screen 4): Perfil de Usuario (Identidad Google Workspace, Carrera y Tema de 3 Vías)

En la tercera pestaña inferior, **`Perfil`**, puedes verificar tu cuenta institucional, personalizar el diseño visual de la aplicación y administrar tus preferencias de avisos.

#### Pasos de configuración en tu Perfil

1. **Verificar tu identidad y carrera / rol:** En la tarjeta superior (`#profile-user`) verás tu avatar con iniciales, tu nombre completo, tu correo verificado **`@upa.edu.py`** y tu insignia de perfil (`Estudiante`, `Docente`, `Redacción` o `Administración`). Tu carrera y grupos académicos (por ejemplo, `TIE`, `PI`, `TI`) se sincronizan automáticamente en segundo plano desde Google Workspace para mostrarte en el muro únicamente los avisos que te corresponden, manteniendo ocultas las listas internas de correo por privacidad.
2. **Cambiar el tema visual (Selector de 3 vías en `Diseño`):** Elige en cualquier momento cómo quieres ver la aplicación:
   * **`Sistema`:** Adapta los colores automáticamente según el modo claro u oscuro configurado en tu teléfono.
   * **`Modo Claro`:** Fija la interfaz con fondo blanco luminoso de alto contraste.
   * **`Modo Oscuro`:** Activa la paleta nocturna oscura para descansar la vista y ahorrar batería.
3. **Configurar tus avisos (`Notificaciones`):** Activa o desactiva con un toque los tres interruptores independientes según tus preferencias:
   * **`Eventos`:** Recordatorios sobre actividades y charlas del campus.
   * **`Avisos y comunicados`:** Alertas institucionales y noticias nuevas.
   * **`Fechas límite`:** Avisos sobre entregas académicas de Google Classroom.
4. **Cerrar sesión de forma segura:** Al tocar el botón rojo **`Cerrar sesión`**, se elimina tu sesión activa y se borra automáticamente toda la caché local almacenada en el navegador.

```screen
screen_4
```

*Figura 4: Pantalla 4 (Screen 4) - Pestaña Perfil con tarjeta de identidad `@upa.edu.py`, selector de diseño de 3 vías y preferencias de notificaciones.*

> **[CONTENEDOR DE CAPTURA #4: Perfil de Usuario, Identidad y Tema de 3 Vías]**  
> **Ruta a capturar:** Pestaña `Perfil` en la PWA móvil con sesión `@upa.edu.py` activa.  
> **Qué mostrar en la imagen:** La pantalla completa de `Perfil` mostrando la tarjeta del usuario arriba, el selector segmentado de `Diseño` en el centro, la lista de interruptores de `Notificaciones` y el botón `Cerrar sesión` abajo.  
> **Elementos UI a enfocar y marcar:**  
> 1. **Enfoque 1 (Tarjeta superior):** Avatar, nombre completo, correo institucional `@upa.edu.py` e insignia de rol vinculada a Google Workspace.  
> 2. **Enfoque 2 (Sección Diseño):** El control segmentado de 3 opciones: **`Sistema`**, **`Modo Claro`** y **`Modo Oscuro`**.  
> 3. **Enfoque 3 (Notificaciones y salida):** Los tres interruptores (`Eventos`, `Avisos y comunicados`, `Fechas límite`) y el botón **`Cerrar sesión`**.

## Parte B: Web-Admin Cockpit (Portal de Redacción y Administración)

El **Web-Admin Cockpit** (`/dashboard/`) es el centro de control de escritorio para el equipo de marketing, comunicación y administración de la UPA. Solo las cuentas `@upa.edu.py` autorizadas en la matriz de roles pueden ingresar; cualquier cuenta estudiantil sin permisos que intente abrir `/dashboard/` verá la pantalla de **Acceso Restringido** con un botón para regresar a UPA Campus.

### Pantalla 5 (Screen 5): Vista General del Web-Admin Cockpit (Tabla de Publicaciones, Filtros y Deep Links)

Al iniciar sesión en `https://upa.eu1.netbird.services/dashboard/publicaciones`, se presenta el módulo central de **Publicaciones**, donde se gestionan en una sola tabla todas las noticias, eventos, alertas urgentes y publicaciones importadas de Instagram.

#### Cómo gestionar el listado, filtrar y compartir enlaces directos

1. **Navegar entre módulos (Menú lateral izquierdo):** A la izquierda verás el botón principal **`Publicaciones`** y, debajo de la sección `Configuración`, los módulos habilitados según tus permisos: **`Grupos`**, **`Roles`**, **`APIs`** e **`IA`**. En la esquina superior derecha dispones del botón **`Ver Campus PWA ↗`** para abrir la aplicación estudiantil en una pestaña nueva.
2. **Filtrar por sección en 1 clic:** Usa el selector superior izquierdo de la tarjeta para alternar instantáneamente entre:
   * **`Todas`:** Muestra el catálogo completo de publicaciones.
   * **`Noticias`:** Filtra únicamente los comunicados que aparecen en el muro de `Inicio`.
   * **`Eventos`:** Filtra únicamente las actividades programadas en el calendario de `Agenda`.
3. **Analizar las columnas de la tabla de publicaciones:**
   * **`Publicación`:** Miniatura multimedia (con sello de respaldo `UPA` si no tiene imagen), título, extracto, fecha de publicación y fecha del evento.
   * **`Secciones`:** Etiquetas que indican si la entrada está activa como `Noticia`, `Evento` y/o `Fijado`.
   * **`Tipo`:** Origen del registro: `Manual`, `Instagram` o insignia **`IA`** cuando fue extraído automáticamente con Gemini.
   * **`Alcance y RSVP`:** Muestra en tiempo real el número de **lecturas únicas (`X vistas`)**, la cantidad de estudiantes confirmados (**`Y inscritos`**) y las bajas registradas (**`Z no asisten`**).
   * **`Estado`:** Indica si un post importado fue revisado por un redactor (**`Editado`**) o si aún está **`Pendiente`** de revisión editorial.
4. **Aprovechar los Enlaces Profundos (Deep Links):** Cada vista tiene su propia dirección URL en la barra del navegador:
   * `/dashboard/publicaciones`: Vista general de la tabla.
   * `/dashboard/publicaciones/nueva`: Abre directamente el formulario vacío de creación.
   * `/dashboard/publicaciones/:id` (por ejemplo, `/dashboard/publicaciones/60`): Abre directamente el editor de esa publicación. Puedes copiar y enviar esa URL por mensaje a otro miembro del equipo o recargar con `F5` sin perder tu pantalla actual.

```screen
screen_5
```

*Figura 5: Pantalla 5 (Screen 5) - Vista general del Web-Admin Cockpit con menú lateral, filtros rápidos, enlaces profundos y métricas reales de alcance y RSVP.*

> **[CONTENEDOR DE CAPTURA #5: Vista General del Web-Admin Cockpit (`/dashboard/publicaciones`)]**  
> **Ruta a capturar:** `https://upa.eu1.netbird.services/dashboard/publicaciones` en navegador de escritorio.  
> **Qué mostrar en la imagen:** El portal administrativo completo con la barra superior institucional, el menú lateral izquierdo (`Publicaciones`, `Grupos`, `Roles`, `APIs`, `IA`), la barra de filtros (`Todas`, `Noticias`, `Eventos`), el botón `+ Nueva publicación` y la tabla con métricas de vistas e inscripciones.  
> **Elementos UI a enfocar y marcar:**  
> 1. **Enfoque 1 (Navegación y URL):** La barra de direcciones con el Deep Link `/dashboard/publicaciones`, el menú lateral de módulos y el botón superior `Ver Campus PWA ↗`.  
> 2. **Enfoque 2 (Barra de herramientas):** El filtro rápido de 3 estados (`Todas` / `Noticias` / `Eventos`) y el botón primario **`+ Nueva publicación`**.  
> 3. **Enfoque 3 (Columnas de la tabla):** Las columnas **`Tipo`** (Manual, Instagram, insignia `IA`), **`Alcance y RSVP`** (`vistas`, `inscritos`, `no asisten`) y **`Estado`** (`Editado` / `Pendiente`).

### Pantalla 6 (Screen 6): Autocompletado Inteligente con IA (Extracción Multimodal de Afiches con Gemini)

El editor de publicaciones (`/dashboard/publicaciones/nueva` o `/dashboard/publicaciones/:id`) incorpora el asistente multimodal **`Autocompletar con IA`** impulsado por **Google Gemini Flash**, diseñado para que el equipo de marketing cree anuncios y eventos completos en pocos segundos a partir de un afiche gráfico.

#### Paso a paso para crear un evento o noticia asistido por IA

1. **Abrir el formulario:** Haz clic en **`+ Nueva publicación`** (ruta `/dashboard/publicaciones/nueva`).
2. **Subir el afiche o archivo multimedia (`Imagen o video`):** Arrastra el flyer del evento hacia la zona de carga (`Dropzone`) o haz clic en `seleccione desde su equipo`. Se admiten archivos `JPG`, `PNG`, `WEBP`, `MP4`, `WEBM` o `PDF` de hasta **`10 MB`**. Verás de inmediato la miniatura de vista previa.
3. **Pulsar `Autocompletar con IA`:** Haz clic en el botón **`Autocompletar con IA`** ubicado en la barra inferior del formulario.
   * El sistema optimiza la imagen y la analiza con Google Gemini Flash.
   * **Regla de respeto al redactor:** La IA rellena **únicamente los campos que estén vacíos** en ese momento. Si ya escribiste un título o seleccionaste un grupo, la IA conservará intacto tu texto y completará el resto.
   * **Campos que completa automáticamente a partir del afiche:** `Título`, `Resumen corto`, `Texto principal`, selección de `Grupos destinatarios`, casilla `Activar Evento`, `Inicio del evento (DD/MM/YYYY HH:mm)`, `Fin del evento (HH:mm)` y `Lugar`.
4. **Verificar inscripciones y recordatorios inteligentes:**
   * Al activarse `Activar Evento`, la casilla **`Permitir inscripción y baja en la app` (RSVP)** se marca automáticamente por defecto.
   * El sistema asigna recordatorios automáticos según el día de la semana: si el evento es de lunes a viernes, programa un aviso **`30 minutos antes`**; si cae en sábado o domingo, programa dos avisos: **`1 día antes` y `30 minutos antes`**. Puedes añadir o quitar recordatorios con `+ Agregar recordatorio`.
   * Si se trata de un aviso prioritario que debe quedar arriba en el muro, marca **`Fijar arriba en el feed`** e ingresa la fecha límite obligatoria en **`Vigente hasta *`**.
5. **Guardar y consultar la lista nominal de participantes:** Pulsa **`Guardar`**. Al abrir cualquier evento existente (`/dashboard/publicaciones/:id`), verás en la barra superior de métricas el botón **`Ver participantes`**, que despliega la lista nominal privada con nombre, correo `@upa.edu.py` y fecha de cada alumno inscrito.

```screen
screen_6
```

*Figura 6: Pantalla 6 (Screen 6) - Editor unificado de publicaciones con subida de afiche, botón `Autocompletar con IA` y programación automática de evento.*

> **[CONTENEDOR DE CAPTURA #6: Autocompletado Inteligente con IA en el Editor (`/dashboard/publicaciones/nueva`)]**  
> **Ruta a capturar:** `https://upa.eu1.netbird.services/dashboard/publicaciones/nueva` (o editando un evento en `/dashboard/publicaciones/:id`).  
> **Qué mostrar en la imagen:** El formulario de edición con un afiche cargado en la zona de imagen, las secciones `Activar Noticia` y `Activar Evento` desplegadas con los datos extraídos, la barra de métricas/participantes y el botón `Autocompletar con IA` abajo a la derecha.  
> **Elementos UI a enfocar y marcar:**  
> 1. **Enfoque 1 (Zona multimedia):** El área de carga (`Dropzone`) mostrando la vista previa del afiche subido (`JPG/PNG/WEBP/MP4/PDF` hasta `10 MB`).  
> 2. **Enfoque 2 (Sección Evento y RSVP):** La casilla `Permitir inscripción y baja en la app` activa por defecto y los campos `Inicio del evento`, `Fin del evento`, `Lugar` y `Recordatorios antes del inicio` completados por la IA.  
> 3. **Enfoque 3 (Barra de acción inferior):** El botón destacado **`Autocompletar con IA`** junto al botón `Guardar` (y el botón `Ver participantes` al editar un evento).

### Pantalla 7 (Screen 7): Gestión de Grupos de Audiencia (Audience Groups y Mapeo con Google Workspace)

El módulo **`Grupos`** (`/dashboard/grupos`) permite definir a qué segmentos de la comunidad universitaria se dirigen las noticias, los eventos y las notificaciones push, conectando los grupos internos de la aplicación con las listas oficiales de correo de **Google Workspace**.

#### Paso a paso para crear o configurar un grupo de audiencia

1. **Ingresar al módulo Grupos:** En el menú lateral izquierdo (`Configuración`), haz clic en **`Grupos`**.
2. **Buscar en el catálogo alfabético:** Utiliza la barra **`Filtrar grupos alfabéticamente...`** para localizar rápidamente cualquier audiencia (`ALL` para toda la comunidad, `estudiantes`, `docentes`, `staff`, `egresados` o carreras como `TIE`, `PI`, `TI`).
3. **Crear o editar un grupo:** Haz clic en **`+ Nuevo grupo`** o selecciona la fila de un grupo existente para abrir su panel de configuración:
   * Completa el **`Nombre *`** y una **`Descripción (opcional)`** clara para los redactores.
4. **Vincular con Grupos de Google Workspace (`@upa.edu.py`):**
   * En el bloque `Grupos de Google Workspace (@upa.edu.py)`, selecciona de la lista sincronizada los grupos institucionales del directorio de Google (por ejemplo, `estudiantes-activos@upa.edu.py` o `estudiantes-tie-2025@upa.edu.py`) o escribe un grupo adicional en el campo inferior y pulsa **`Agregar`**.
   * Todo usuario que pertenezca a ese grupo en Google Workspace quedará incluido automáticamente en la audiencia al iniciar sesión en la PWA.
5. **Añadir cuentas individuales (`@upa.edu.py`):** Si necesitas incluir a personas específicas que aún no figuran en la lista de correo de Google Workspace, escribe su dirección en `Cuentas individuales (@upa.edu.py)`, pulsa **`Agregar correo`** y confirma con **`Guardar`**.

```screen
screen_7
```

*Figura 7: Pantalla 7 (Screen 7) - Módulo de Grupos de Audiencia con filtro alfabético y mapeo directo hacia grupos de Google Workspace.*

> **[CONTENEDOR DE CAPTURA #7: Gestión de Grupos de Audiencia (`/dashboard/grupos`)]**  
> **Ruta a capturar:** `https://upa.eu1.netbird.services/dashboard/grupos` (vista de lista y/o editor de un grupo con mapeo de Google Workspace).  
> **Qué mostrar en la imagen:** El panel de `Grupos` con el buscador alfabético y el formulario de edición mostrando la vinculación con `Grupos de Google Workspace (@upa.edu.py)` y `Cuentas individuales (@upa.edu.py)`.  
> **Elementos UI a enfocar y marcar:**  
> 1. **Enfoque 1 (Cabecera y buscador):** El campo `Filtrar grupos alfabéticamente...` y el botón primario **`+ Nuevo grupo`**.  
> 2. **Enfoque 2 (Mapeo Google Workspace):** El selector `Grupos de Google Workspace (@upa.edu.py)` donde se vinculan las listas oficiales del directorio institucional con el grupo de la app.  
> 3. **Enfoque 3 (Cuentas individuales y guardado):** La sección `Cuentas individuales (@upa.edu.py)` para altas puntuales y el botón **`Guardar`**.

### Pantalla 8 (Screen 8): Matriz de Roles y Permisos (6 Permisos Canónicos)

El módulo **`Roles`** (`/dashboard/roles`) controla qué cuentas institucionales tienen acceso al Web-Admin Cockpit y qué módulos específicos puede utilizar cada persona, aplicando el **Principio de Mínimo Privilegio**.

#### Las 6 permisos canónicos de la matriz

| Columna en la Matriz | Clave Interna | Qué permite hacer al usuario autorizado |
|---|---|---|
| **`Publicaciones`** | `publicaciones` | Crear, editar y eliminar noticias y eventos, subir archivos, usar `Autocompletar con IA` y ver listas nominales de inscritos. |
| **`Grupos`** | `grupos` | Crear, editar y eliminar grupos de audiencia y mapear listas de Google Workspace. |
| **`Roles`** | `roles` | Autorizar nuevas cuentas en el Cockpit, modificar casillas de permisos y eliminar accesos (otorga rol `admin`). |
| **`APIs`** | `apis` | Consultar el estado en tiempo real de los conectores externos y la telemetría del backend en la pestaña `APIs`. |
| **`IA`** | `ia` | Configurar la clave `GEMINI_API_KEY`, ajustar los prompts del sistema y probar la conexión en vivo en la pestaña `IA`. |
| **`Historial`** | `historial` | Visualizar las tablas de auditoría (`Historial:`) con el detalle de quién creó o modificó cada registro. |

#### Paso a paso para autorizar cuentas y gestionar permisos

1. **Abrir el módulo Roles:** En el menú lateral izquierdo, haz clic en **`Roles`**.
2. **Autorizar una nueva cuenta `@upa.edu.py`:** En el recuadro superior `Correo institucional`, escribe el correo de la persona (por ejemplo, `nombre.apellido@upa.edu.py`) y pulsa **`Autorizar`**.
3. **Asignar permisos en la tabla:** Por seguridad, toda cuenta nueva se añade con las **6 casillas desmarcadas**. Marca únicamente las casillas de los módulos que esa persona necesita para su trabajo (por ejemplo, solo `Publicaciones` para un colaborador de marketing) y los cambios quedarán registrados de inmediato.
4. **Protección contra bloqueo administrativo:** El sistema impide desmarcar el permiso `Roles` o eliminar la cuenta si se trata del último administrador con acceso a `Roles`, garantizando que la universidad nunca pierda el control del portal.
5. **Módulos técnicos complementarios (`IA` y `APIs`):** Quienes posean los permisos `ia` y `apis` verán además en el menú lateral la pestaña **`IA`** (donde se guarda la clave de Google AI Studio enmascarada como `AIzaSy...` y se pulsa `Guardar configuración y probar conexión`) y la pestaña **`APIs`** (donde se verifica en vivo el estado `Activo` de Google OAuth, Google Directory, Google Classroom e Instagram).

```screen
screen_8
```

*Figura 8: Pantalla 8 (Screen 8) - Matriz interactiva de Roles y Permisos con las 6 capacidades canónicas por cuenta `@upa.edu.py`.*

> **[CONTENEDOR DE CAPTURA #8: Matriz de Roles y Permisos (`/dashboard/roles`)]**  
> **Ruta a capturar:** `https://upa.eu1.netbird.services/dashboard/roles` en navegador de escritorio.  
> **Qué mostrar en la imagen:** La vista completa del módulo `Roles` mostrando el formulario superior para autorizar un nuevo `Correo institucional` y la tabla inferior con las 6 columnas de casillas de verificación (`Publicaciones`, `Grupos`, `Roles`, `APIs`, `IA`, `Historial`).  
> **Elementos UI a enfocar y marcar:**  
> 1. **Enfoque 1 (Alta de cuenta):** El campo `Correo institucional` (`nombre.apellido@upa.edu.py`) y el botón **`Autorizar`** (toda cuenta inicia con 0 permisos marcados).  
> 2. **Enfoque 2 (Las 6 columnas de permisos):** Las seis casillas de verificación por fila: **`Publicaciones`**, **`Grupos`**, **`Roles`**, **`APIs`**, **`IA`** e **`Historial`**.  
> 3. **Enfoque 3 (Columna Acciones y protección):** Los controles de acción por fila y la protección automática del administrador principal (`Roles`).

### Pantalla 9 (Screen 9): Historial y Registros de Auditoría (Bitácora Inmutable de Acciones Administrativas)

Para garantizar una trazabilidad transparente sobre quién creó, editó o eliminó información oficial, la plataforma registra cada operación administrativa en una bitácora inmutable en base de datos (`admin_audit_logs`), visible para los usuarios con el permiso **`Historial`**.

#### Cómo consultar e interpretar el Historial de Auditoría

1. **Dónde se visualiza el Historial:** Cuando tu cuenta tiene activo el permiso `Historial`, aparece automáticamente el bloque **`Historial:`** (`.ed-audit-trail`) en la parte inferior de cada módulo administrativo:
   * **En `Publicaciones` (`/dashboard/publicaciones`):** Muestra las últimas acciones globales sobre noticias, eventos y sincronizaciones de Instagram, y al abrir una publicación específica (`/dashboard/publicaciones/:id`) muestra la historia exclusiva de ese post.
   * **En `Grupos` (`/dashboard/grupos`):** Muestra quién creó, modificó o eliminó grupos de audiencia y cambios en listas de correos.
   * **En `Roles` (`/dashboard/roles`):** Registra cada alta o baja de cuentas administrativas y las diferencias exactas de permisos otorgados o revocados (`permissions_diff`).
2. **Leer cada fila del registro inmutable:** Cada entrada de la tabla de auditoría presenta tres columnas claras:
   * **Fecha y hora (Formato 24h `DD/MM/YYYY HH:mm`):** Momento exacto en que se ejecutó el cambio.
   * **Autor (`admin_name` / `admin_email`):** Nombre o correo `@upa.edu.py` del editor o administrador responsable.
   * **Detalle de la acción y campos modificados:** Verbo de la operación (`creó`, `actualizó`, `eliminó`, `sincronizó`), nombre del elemento afectado y entre paréntesis la lista exacta de campos modificados (por ejemplo, `(title, event_start, location)` o los permisos añadidos/eliminados).

```screen
screen_9
```

*Figura 9: Pantalla 9 (Screen 9) - Registro inmutable de auditoría (`Historial:`) con marca temporal de 24 horas, responsable y campos modificados.*

> **[CONTENEDOR DE CAPTURA #9: Historial y Registros de Auditoría (`Historial:`)]**  
> **Ruta a capturar:** Bloque inferior `Historial:` en `/dashboard/publicaciones`, `/dashboard/publicaciones/:id`, `/dashboard/grupos` o `/dashboard/roles` con una cuenta que posea el permiso `Historial`.  
> **Qué mostrar en la imagen:** La tabla de auditoría (`Historial:`) mostrando múltiples filas cronológicas con fecha/hora en formato 24h, el administrador que ejecutó la acción y el detalle de la entidad y los campos modificados.  
> **Elementos UI a enfocar y marcar:**  
> 1. **Enfoque 1 (Columna Fecha y Hora):** La marca temporal exacta en formato de 24 horas (`DD/MM/YYYY HH:mm`).  
> 2. **Enfoque 2 (Columna Responsable):** El nombre o correo `@upa.edu.py` del administrador o editor que realizó el cambio.  
> 3. **Enfoque 3 (Columna Acción y Diferencias):** La descripción de la operación (`creó`, `actualizó`, `eliminó`) junto con el listado entre paréntesis de los campos o permisos modificados.

## Resumen Rápido de Referencia para Usuarios y Administradores

| Tarea Frecuente | Dónde ir | Acción en 1 Paso |
|---|---|---|
| **Abrir la app en el celular desde la PC** | `/` (Escritorio) | Escanear el **Código QR** en pantalla con la cámara del teléfono. |
| **Confirmar o descartar asistencia a un evento** | Pestaña `Inicio` o `Agenda` | Tocar **`Sí, asistiré`** o **`No asistiré`** en la tarjeta del evento. |
| **Consultar entregas de Google Classroom** | Pestaña `Agenda` | Revisar la lista superior o tocar un día con punto en el calendario mensual. |
| **Cambiar entre modo claro y oscuro** | Pestaña `Perfil` -> `Diseño` | Tocar **`Sistema`**, **`Modo Claro`** o **`Modo Oscuro`**. |
| **Crear un evento subiendo un afiche** | `/dashboard/publicaciones/nueva` | Subir imagen del flyer -> clic en **`Autocompletar con IA`** -> clic en **`Guardar`**. |
| **Ver quiénes se inscribieron a un evento** | `/dashboard/publicaciones/:id` | Hacer clic en **`Ver participantes`** en la barra superior de métricas del editor. |
| **Conectar un grupo de Google Workspace** | `/dashboard/grupos` | Editar grupo -> marcar lista en `Grupos de Google Workspace` -> **`Guardar`**. |
| **Dar acceso a un nuevo editor o admin** | `/dashboard/roles` | Ingresar correo `@upa.edu.py` -> **`Autorizar`** -> marcar casillas de permisos. |
| **Auditar quién modificó una publicación o rol** | Bloque inferior `Historial:` | Revisar fecha/hora, autor y campos modificados en la tabla de auditoría. |
