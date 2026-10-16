# UPA App: Especificacion de Alcance, Usuarios y Matriz de Decisiones Arquitectonicas

Documento Tecnico y Estrategico de Ingenieria de Sistemas | Universidad Paraguayo Alemana (UPA)

## 1. Proposito del Sistema y Filosofia de Diseno
El objetivo de la UPA App es consolidar en un punto unico de acceso la vida academica, comunicacional y de eventos de la Universidad Paraguayo Alemana.
* Minimalismo Radical: Interfaz limpia, agil y directa, eliminando elementos accesorios.
* Doctrina Zero-Mock (Cero Simulaciones): Todo boton, formulario o vista esta conectado a logica real y fuentes autenticas.

## 2. Analisis Exhaustivo de Usuarios y Roles (Personas del Sistema)
* Estudiante de Grado (Segmentado por Carrera y Semestre): Visualiza avisos de emergencia, agenda con entregas de Google Classroom y charlas dirigidas a su carrera.
* Personal Docente y Catedraticos: Avisos institucionales para el claustro, cronograma de entregas de sus cursos y reservas academicas.
* Personal Administrativo y Equipo de Marketing: Gestion de contenidos desde el Portal Web Administrativo de escritorio, con asignacion al calendario y segmentacion por Google Groups.
* Usuario No Autenticado: Acceso bloqueado. Unicamente se presenta la pantalla de inicio de sesion con Google OAuth restringido al dominio @upa.edu.py.

## 3. Matriz de Decisiones Arquitectonicas y Evaluacion de Alternativas
* Por que PWA y no Nativo Dual ni Flutter: El 80% de los estudiantes usa iPhone. PWA elimina los 99 USD anuales de Apple, no requiere computadoras Mac para compilar y se instala al instante en Safari. Para la entrega academica, el mismo codigo se empaqueta con TWA en Android Studio.
* Por que Instagram y no TikTok, Facebook o LinkedIn: Instagram es el canal principal donde marketing de la UPA publica afiches y comunicados. TikTok es de entretenimiento vertical y Facebook no es utilizado por el segmento universitario de 18 a 24 anos en Paraguay.
* Por que Python (FastAPI) y no Java: Reduce un 60% el codigo repetitivo, genera documentacion Swagger nativa (/docs) y cuenta con librerias asincronas lideres para Google Workspace y APIs externas.
* Por que Google OAuth: Aprovecha la federacion de identidades oficial de la UPA y evita mantener servidores de correo y contrasenas propias.

## 4. Arquitectura Offline-First: Solucion al Problema de Mensajes Sin Conexion
* Carga Util Completa en Web Push (Full Payload): El evento push viaja con todo el texto y datos del mensaje.
* Activacion del Service Worker en Segundo Plano: Se despierta al recibir el push antes de que el usuario interactue.
* Almacenamiento Inmediato en IndexedDB y Cache Storage: El mensaje queda guardado en la base de datos local del navegador.
* Renderizado Offline: Al abrir la app sin internet, los datos se leen directamente desde IndexedDB. Cero pantallas en blanco.

## 5. Modelo Operativo del Equipo
* Pascal Thommen: Product Owner y Arquitecto de Integracion.
* Theresa y Natasha: Desarrollo de componentes de interfaz en GitHub.
* Mika (IA): Generacion de especificaciones, revision Zero-Mock y seguridad.
